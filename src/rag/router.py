"""
Query Understanding, Retrieval Planner, and Multi-Modal Adaptive Retrieval Router
Selects the minimum sufficient retrieval strategy based on query intent,
canonical page/document metadata, and available modalities.
Evaluates multi-factor evidence sufficiency and escalates conditionally.
"""

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from src.config import get_settings
from src.rag.canonical_page import PageType, get_canonical_page_store
from src.rag.fusion import fuse_and_deduplicate
from src.rag.knowledge_graph import get_knowledge_graph
from src.rag.lexical_store import get_lexical_store
from src.rag.ocr_engine import get_ocr_engine
from src.rag.vector_store import get_vector_store
from src.rag.visual_engine import get_visual_engine


class RetrievalIntent(StrEnum):
    SEMANTIC_LOOKUP = "semantic_lookup"
    EXACT_SYMBOL = "exact_symbol"
    RELATIONSHIP_DEPENDENCY = "relationship_dependency"
    IMPACT_ANALYSIS = "impact_analysis"
    MULTI_HOP_ARCHITECTURE = "multi_hop_architecture"
    COMPLEX_DEBUGGING = "complex_debugging"
    SCANNED_TEXT = "scanned_text"
    VISUAL_QUESTION = "visual_question"
    MIXED_MODAL = "mixed_modal"


class RetrievalPlan(BaseModel):
    query: str
    intent: RetrievalIntent
    query_type: str = "semantic_text"
    modalities: list[str] = Field(default_factory=lambda: ["text"])
    selected_strategies: list[str]  # e.g. ["vector"], ["lexical", "vector"], ["graph"], ["ocr"]
    use_vector: bool = True
    use_bm25: bool = False
    use_graph: bool = False
    use_ocr: bool = False
    use_visual: bool = False
    max_hops: int = 0
    graph_max_hops: int = 0  # backward-compatibility alias
    top_k: int = 5
    target_entities: list[str] = Field(default_factory=list)
    target_pages: list[int] = Field(default_factory=list)
    escalation_allowed: bool = True
    rationale: str = ""
    reason: str = ""  # backward-compatibility alias
    confidence: float | None = None
    fallback_strategy: str = "vector_and_bm25"


# Deterministic pattern matchers
RELATIONSHIP_PATTERNS = [
    re.compile(r"(?i)\b(who|what)\s+(imports|uses|calls|depends\s+on)\b"),
    re.compile(r"(?i)\b(dependencies|dependents|callers|imports)\s+of\b"),
    re.compile(r"(?i)\b(where\s+is\s+.*\s+called)\b"),
    re.compile(r"(?i)\b(what\s+does\s+.*\s+import)\b"),
]

IMPACT_PATTERNS = [
    re.compile(r"(?i)\b(what\s+(could|will|would)\s+break\s+if)\b"),
    re.compile(r"(?i)\b(impact\s+of\s+(changing|modifying|removing|deleting))\b"),
    re.compile(r"(?i)\b(blast\s+radius|affected\s+components)\b"),
]

MULTI_HOP_PATTERNS = [
    re.compile(r"(?i)\b(how\s+does\s+.*\s+flow\s+(from|to|into))\b"),
    re.compile(r"(?i)\b(end[- ]to[- ]end\s+(flow|path|pipeline)\s+of)\b"),
    re.compile(r"(?i)\b(lifecycle\s+of)\b"),
]

DEBUGGING_PATTERNS = [
    re.compile(r"(?i)\b(why\s+does\s+.*\s+(fail|crash|raise|error))\b"),
    re.compile(r"(?i)\b(debugging|root\s+cause\s+of)\b"),
]

SCANNED_PATTERNS = [
    re.compile(r"(?i)\b(scanned|handwritten|receipt|invoice scan|scan of|ocr)\b"),
]

VISUAL_PATTERNS = [
    re.compile(r"(?i)\b(diagram|flowchart|architecture chart|drawing|plot|visual layout|figure)\b"),
]

SEMANTIC_STARTERS = re.compile(
    r"(?i)^(explain|describe|overview|what\s+is|how\s+(does|do|can|to)\b|tell\s+me\s+about|summary\s+of|discuss|details\s+of)\b"
)


def extract_target_entities(query: str) -> list[str]:
    """
    Extracts high-confidence code symbols, filenames, snake_case tokens, and PascalCase classes.
    Avoids false positives on capitalized English sentence starters.
    """
    entities: list[str] = []

    # 1. Backtick enclosed identifiers: `foo_bar`
    for bt in re.findall(r"`([^`]+)`", query):
        entities.append(bt.strip())

    # 2. Explicit code keyword declarations: class Foo, def bar, interface Baz
    for m in re.finditer(r"\b(?:class|def|function|interface|type)\s+([a-zA-Z0-9_$]+)", query, re.IGNORECASE):
        entities.append(m.group(1))

    # 3. Code identifiers: filenames, snake_case, PascalCase, camelCase
    words = re.findall(r"[a-zA-Z0-9_\.\-]+", query)
    stop_words = {"the", "what", "how", "why", "who", "where", "which", "and", "for", "with", "from", "into", "that", "this", "page"}

    for w in words:
        clean_w = w.strip()
        if not clean_w or clean_w.lower() in stop_words:
            continue
        # Filename (e.g. order_system.py, spec.pdf)
        if re.match(r"^[\w\-]+\.(?:py|js|ts|json|md|yaml|txt|pdf)$", clean_w):
            entities.append(clean_w)
        # snake_case with underscore (e.g. calculate_tax)
        elif "_" in clean_w and len(clean_w) > 2:
            entities.append(clean_w)
        # PascalCase or camelCase (e.g. OrderProcessor, processPayment)
        elif re.search(r"[a-z][A-Z]", clean_w) or re.search(r"^[A-Z][a-z]+[A-Z]", clean_w):
            entities.append(clean_w)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for e in entities:
        if e.lower() not in seen:
            seen.add(e.lower())
            unique.append(e)
    return unique


def extract_target_pages(query: str) -> list[int]:
    """Extracts explicit page number references (e.g. 'page 4', 'Page #2')."""
    pages: list[int] = []
    matches = re.findall(r"(?i)\bpage\s*#?\s*(\d+)\b", query)
    for m in matches:
        try:
            pages.append(int(m))
        except ValueError:
            pass
    return sorted(set(pages))


def classify_query_intent(query: str) -> tuple[RetrievalIntent, list[str], list[int], str]:
    """
    Classifies the user query into a typed retrieval intent considering:
    - Query syntax and semantics
    - Target entities and page references
    - Canonical page store metadata and repository modality availability
    """
    q_clean = query.strip()
    entities = extract_target_entities(q_clean)
    target_pages = extract_target_pages(q_clean)
    page_store = get_canonical_page_store()
    target_filename = next((e for e in entities if e.endswith(".pdf")), None)

    # 1. Page-Specific Metadata Inspection
    if target_pages:
        for p_num in target_pages:
            page_rec = page_store.get_page(target_filename, p_num) if target_filename else None
            if not page_rec:
                # Search across all documents in page store for this page number
                matching = [p for p in page_store.find_pages_by_type(PageType.SCANNED_PAGE) if p.page_number == p_num]
                if matching:
                    page_rec = matching[0]

            if page_rec:
                if page_rec.page_type == PageType.SCANNED_PAGE:
                    return (
                        RetrievalIntent.SCANNED_TEXT,
                        entities,
                        target_pages,
                        f"Page {p_num} is classified in canonical store as SCANNED_PAGE; routing to OCR pipeline.",
                    )
                if page_rec.page_type == PageType.VISUAL_HEAVY_PAGE:
                    return (
                        RetrievalIntent.VISUAL_QUESTION,
                        entities,
                        target_pages,
                        f"Page {p_num} is classified in canonical store as VISUAL_HEAVY_PAGE; routing to Visual RAG pipeline.",
                    )
                if page_rec.page_type == PageType.TEXT_PAGE:
                    return (
                        RetrievalIntent.SEMANTIC_LOOKUP,
                        entities,
                        target_pages,
                        f"Page {p_num} is classified as standard TEXT_PAGE; routing to cheap text vector retrieval.",
                    )

    # 2. Multi-hop architecture
    for pat in MULTI_HOP_PATTERNS:
        if pat.search(q_clean):
            return (
                RetrievalIntent.MULTI_HOP_ARCHITECTURE,
                entities,
                target_pages,
                "Query asks for end-to-end data/architectural flow across multiple components.",
            )

    # 3. Impact analysis
    for pat in IMPACT_PATTERNS:
        if pat.search(q_clean):
            return (
                RetrievalIntent.IMPACT_ANALYSIS,
                entities,
                target_pages,
                "Query asks for breaking changes or blast radius analysis.",
            )

    # 4. Relationship / Dependency
    for pat in RELATIONSHIP_PATTERNS:
        if pat.search(q_clean):
            return (
                RetrievalIntent.RELATIONSHIP_DEPENDENCY,
                entities,
                target_pages,
                "Query explicitly asks for imports, callers, or dependency edges.",
            )

    # 5. Complex debugging
    for pat in DEBUGGING_PATTERNS:
        if pat.search(q_clean):
            return (
                RetrievalIntent.COMPLEX_DEBUGGING,
                entities,
                target_pages,
                "Query asks for root cause or failure diagnosis.",
            )

    # 6. Scanned text intent (Cross-referenced with document store)
    for pat in SCANNED_PATTERNS:
        if pat.search(q_clean):
            scanned_pages = page_store.find_pages_by_type(PageType.SCANNED_PAGE)
            if scanned_pages:
                return (
                    RetrievalIntent.SCANNED_TEXT,
                    entities,
                    target_pages,
                    f"Query requests scanned content and repository contains {len(scanned_pages)} scanned page(s).",
                )
            # Safe fallback if no scanned pages exist
            return (
                RetrievalIntent.SEMANTIC_LOOKUP,
                entities,
                target_pages,
                "Query mentions scanned concepts, but no scanned pages exist in repository; falling back to text retrieval.",
            )

    # 7. Visual question intent (Cross-referenced with Visual RAG active capability)
    for pat in VISUAL_PATTERNS:
        if pat.search(q_clean):
            visual_engine = get_visual_engine()
            visual_pages = page_store.find_pages_by_type(PageType.VISUAL_HEAVY_PAGE)
            if visual_engine.is_visual_active() and visual_pages:
                return (
                    RetrievalIntent.VISUAL_QUESTION,
                    entities,
                    target_pages,
                    "Query requests visual diagram interpretation and Visual RAG is active with visual pages.",
                )
            return (
                RetrievalIntent.SEMANTIC_LOOKUP,
                entities,
                target_pages,
                "Query asks about diagrams/charts, but Visual RAG is inactive or no visual pages exist; routing safely to text + BM25.",
            )

    # 8. Semantic question starters (e.g. "Explain how transaction settlement rules work")
    if SEMANTIC_STARTERS.search(q_clean):
        return (
            RetrievalIntent.SEMANTIC_LOOKUP,
            entities,
            target_pages,
            "Query begins with an explanatory/concept question starter.",
        )

    # 9. Exact symbol / definition lookup
    if re.search(r"(?i)\b(where\s+is\s+.*(defined|located))\b", q_clean) or (
        len(entities) > 0 and len(q_clean.split()) <= 5
    ):
        return (
            RetrievalIntent.EXACT_SYMBOL,
            entities,
            target_pages,
            "Query targets exact function/class/file symbol definition or location.",
        )

    # 10. Default: Semantic concept lookup
    return (
        RetrievalIntent.SEMANTIC_LOOKUP,
        entities,
        target_pages,
        "General semantic question about concepts, documentation, or behavior.",
    )


def build_retrieval_plan(query: str, top_k: int = 5) -> RetrievalPlan:
    """
    Constructs an inspectable retrieval plan selecting the minimum sufficient strategy.
    """
    settings = get_settings()
    intent, entities, target_pages, reason = classify_query_intent(query)

    strategies: list[str] = []
    modalities: list[str] = ["text"]
    query_type = "semantic_text"
    graph_hops = 0
    use_vector = True
    use_bm25 = False
    use_graph = False
    use_ocr = False
    use_visual = False
    confidence = 0.90
    fallback = "vector_and_bm25"

    if intent == RetrievalIntent.SEMANTIC_LOOKUP:
        strategies = ["vector"]
        modalities = ["text"]
        query_type = "semantic_text"
        use_vector = True
        graph_hops = 0
        fallback = "vector_and_bm25"

    elif intent == RetrievalIntent.EXACT_SYMBOL:
        strategies = ["lexical", "vector"]
        modalities = ["text", "lexical"]
        query_type = "exact_symbol"
        use_bm25 = True
        use_vector = True
        graph_hops = 0
        fallback = "vector"

    elif intent == RetrievalIntent.SCANNED_TEXT:
        strategies = ["ocr", "vector"]
        modalities = ["ocr", "text"]
        query_type = "scanned_text"
        use_ocr = True
        use_vector = True
        graph_hops = 0
        fallback = "vector_and_bm25"

    elif intent == RetrievalIntent.VISUAL_QUESTION:
        strategies = ["visual", "vector"]
        modalities = ["visual", "text"]
        query_type = "visual_question"
        use_visual = True
        use_vector = True
        graph_hops = 0
        fallback = "vector_and_bm25"

    elif intent == RetrievalIntent.RELATIONSHIP_DEPENDENCY:
        strategies = ["graph"]
        modalities = ["graph"]
        query_type = "dependency_question"
        use_graph = True
        use_vector = False
        graph_hops = 1
        fallback = "vector"

    elif intent == RetrievalIntent.IMPACT_ANALYSIS:
        strategies = ["graph", "vector"]
        modalities = ["graph", "text"]
        query_type = "impact_analysis"
        use_graph = True
        use_vector = True
        graph_hops = min(settings.GRAPH_MAX_HOPS_DEFAULT, 2)
        fallback = "vector"

    elif intent == RetrievalIntent.MULTI_HOP_ARCHITECTURE:
        strategies = ["graph", "vector"]
        modalities = ["graph", "text"]
        query_type = "multi_hop_architecture"
        use_graph = True
        use_vector = True
        graph_hops = min(settings.GRAPH_MAX_HOPS_DEFAULT, 3)
        fallback = "vector_and_bm25"

    elif intent == RetrievalIntent.COMPLEX_DEBUGGING:
        strategies = ["vector", "lexical", "graph"]
        modalities = ["text", "lexical", "graph"]
        query_type = "complex_debugging"
        use_vector = True
        use_bm25 = True
        use_graph = True
        graph_hops = 1
        fallback = "vector"

    return RetrievalPlan(
        query=query,
        intent=intent,
        query_type=query_type,
        modalities=modalities,
        selected_strategies=strategies,
        use_vector=use_vector,
        use_bm25=use_bm25,
        use_graph=use_graph,
        use_ocr=use_ocr,
        use_visual=use_visual,
        max_hops=graph_hops,
        graph_max_hops=graph_hops,
        top_k=top_k,
        target_entities=entities,
        target_pages=target_pages,
        escalation_allowed=True,
        rationale=reason,
        reason=reason,
        confidence=confidence,
        fallback_strategy=fallback,
    )


def evaluate_evidence_sufficiency(
    results: list[dict[str, Any]],
    plan: RetrievalPlan,
) -> tuple[bool, str]:
    """
    Evaluates retrieval sufficiency using multi-factor signals rather than
    a hardcoded universal vector score.
    """
    settings = get_settings()

    if not results:
        return False, "Zero results retrieved."

    # 1. Result count check
    if len(results) < settings.RETRIEVAL_SUFFICIENCY_MIN_RESULTS and plan.top_k > 1:
        return False, f"Retrieved {len(results)} results, below sufficiency minimum of {settings.RETRIEVAL_SUFFICIENCY_MIN_RESULTS}."

    top_score = results[0].get("score", 0.0)

    # 2. Similarity baseline check
    if top_score < settings.RETRIEVAL_SUFFICIENCY_MIN_SCORE:
        return False, f"Top score ({top_score:.4f}) is below sufficiency baseline ({settings.RETRIEVAL_SUFFICIENCY_MIN_SCORE})."

    # 3. Score margin check
    if len(results) >= 2:
        margin = top_score - results[1].get("score", 0.0)
        if top_score < 0.70 and margin < settings.RETRIEVAL_SUFFICIENCY_MIN_MARGIN:
            return False, f"Low score margin ({margin:.4f}) indicates ambiguous/diffuse retrieval confidence."

    # 4. Exact symbol verification
    if plan.intent == RetrievalIntent.EXACT_SYMBOL and plan.target_entities:
        target_str = plan.target_entities[0].lower()
        found_exact = any(target_str in r.get("content", "").lower() for r in results)
        if not found_exact:
            return False, f"Exact symbol '{plan.target_entities[0]}' not present in retrieved snippet content."

    return True, f"Evidence sufficient: top_score={top_score:.4f}, count={len(results)}."


def execute_adaptive_retrieval(
    query: str,
    top_k: int = 5,
    filter_filename: str | None = None,
) -> tuple[list[dict[str, Any]], RetrievalPlan, list[str]]:
    """
    Executes query-adaptive retrieval following the minimum sufficient strategy
    and escalates conditionally if evidence is insufficient.
    """
    settings = get_settings()
    plan = build_retrieval_plan(query, top_k=top_k)
    trace: list[str] = [f"Initial Plan: {plan.query_type} via {plan.selected_strategies} ({plan.rationale})"]

    vector_store = get_vector_store()
    lexical_store = get_lexical_store()
    kg = get_knowledge_graph()
    page_store = get_canonical_page_store()
    ocr_engine = get_ocr_engine()
    visual_engine = get_visual_engine()

    strategy_results: list[list[dict[str, Any]]] = []

    # 1. Vector Search
    if "vector" in plan.selected_strategies:
        v_res = vector_store.query(
            query,
            top_k=top_k,
            filter_metadata={"filename": filter_filename} if filter_filename else None,
        )
        for r in v_res:
            r["source_type"] = "vector"
        strategy_results.append(v_res)
        trace.append(f"Vector search returned {len(v_res)} items")

    # 2. Lexical Search
    if "lexical" in plan.selected_strategies:
        l_res = lexical_store.query(query, top_k=top_k, filter_filename=filter_filename)
        strategy_results.append(l_res)
        trace.append(f"Lexical BM25 search returned {len(l_res)} items")

    # 3. Graph Search
    if "graph" in plan.selected_strategies:
        g_items: list[dict[str, Any]] = []
        target = plan.target_entities[0] if plan.target_entities else query
        evidence_list = kg.traverse_multi_hop(target, max_hops=plan.graph_max_hops)
        for ev in evidence_list:
            g_items.append(
                {
                    "content": f"Graph Relation: {ev.source_node.name} ({ev.source_node.node_type}) -> {ev.relation} -> {ev.target_node.name} ({ev.target_node.node_type})\nContext: {ev.snippet}",
                    "citation": ev.citation,
                    "score": round(1.0 / (1.0 + ev.hop_depth * 0.3), 4),
                    "source_type": "graph",
                    "metadata": {
                        "filename": ev.source_node.filename,
                        "start_line": ev.provenance_line,
                        "end_line": ev.provenance_line,
                        "relation": ev.relation,
                    },
                }
            )
        strategy_results.append(g_items)
        trace.append(f"Graph traversal returned {len(g_items)} relation edges")

    # 4. Lazy OCR Search (On Demand)
    if "ocr" in plan.selected_strategies:
        ocr_items: list[dict[str, Any]] = []
        # Find target scanned pages
        scanned_pages = page_store.find_pages_by_type(PageType.SCANNED_PAGE, filename=filter_filename)
        if plan.target_pages:
            scanned_pages = [p for p in scanned_pages if p.page_number in plan.target_pages]

        for p_rec in scanned_pages[: settings.MAX_OCR_PAGES_PER_REQUEST]:
            ocr_res = ocr_engine.process_page_ocr(
                doc_id=p_rec.doc_id,
                filename=p_rec.filename,
                page_number=p_rec.page_number,
            )
            if ocr_res.get("text"):
                ocr_items.append(
                    {
                        "id": f"ocr_{p_rec.doc_id}_{p_rec.page_number}",
                        "content": ocr_res["text"],
                        "citation": f"{p_rec.filename}:Page {p_rec.page_number} [OCR]",
                        "score": ocr_res.get("confidence", 0.85),
                        "source_type": "ocr",
                        "metadata": {
                            "filename": p_rec.filename,
                            "page": p_rec.page_number,
                            "cached": ocr_res.get("cached", False),
                        },
                    }
                )
        if ocr_items:
            strategy_results.append(ocr_items)
            trace.append(f"Lazy OCR returned {len(ocr_items)} page extraction(s)")

    # 5. Lazy Visual RAG (On Demand)
    if "visual" in plan.selected_strategies:
        vis_items: list[dict[str, Any]] = []
        visual_pages = page_store.find_pages_by_type(PageType.VISUAL_HEAVY_PAGE, filename=filter_filename)
        if plan.target_pages:
            visual_pages = [p for p in visual_pages if p.page_number in plan.target_pages]

        for p_rec in visual_pages[: settings.MAX_VISUAL_PAGES_PER_REQUEST]:
            vis_res = visual_engine.process_page_visual(
                doc_id=p_rec.doc_id,
                filename=p_rec.filename,
                page_number=p_rec.page_number,
            )
            for reg in vis_res.get("regions", []):
                vis_items.append(
                    {
                        "id": f"vis_{p_rec.doc_id}_{p_rec.page_number}_{reg['region_id']}",
                        "content": f"Visual Region ({reg.get('region_type', 'DIAGRAM')}): {reg.get('caption', '')}",
                        "citation": f"{p_rec.filename}:Page {p_rec.page_number} [Visual Region {reg['region_id']}]",
                        "score": 0.85,
                        "source_type": "visual",
                        "metadata": {
                            "filename": p_rec.filename,
                            "page": p_rec.page_number,
                            "region_id": reg["region_id"],
                        },
                    }
                )
        if vis_items:
            strategy_results.append(vis_items)
            trace.append(f"Lazy Visual RAG returned {len(vis_items)} visual region(s)")

    # 6. Blend Initial Results
    fused = fuse_and_deduplicate(strategy_results, top_k=top_k)

    # 7. Evaluate Evidence Sufficiency
    is_sufficient, suff_reason = evaluate_evidence_sufficiency(fused, plan)
    trace.append(f"Sufficiency Evaluation: {is_sufficient} ({suff_reason})")

    # 8. Adaptive Escalation
    if not is_sufficient and plan.escalation_allowed:
        trace.append("Initiating Adaptive Escalation...")
        escalated_lists: list[list[dict[str, Any]]] = list(strategy_results)

        # Escalate to Lexical if vector was used alone
        if "vector" in plan.selected_strategies and "lexical" not in plan.selected_strategies:
            l_esc = lexical_store.query(query, top_k=top_k, filter_filename=filter_filename)
            if l_esc:
                escalated_lists.append(l_esc)
                trace.append(f"Escalation added {len(l_esc)} BM25 results")

        # Escalate to OCR if target document contains scanned pages and text was insufficient
        if "ocr" not in plan.selected_strategies:
            candidate_scanned = page_store.find_pages_by_type(PageType.SCANNED_PAGE, filename=filter_filename)
            if candidate_scanned:
                p = candidate_scanned[0]
                ocr_esc = ocr_engine.process_page_ocr(doc_id=p.doc_id, filename=p.filename, page_number=p.page_number)
                if ocr_esc.get("text"):
                    escalated_lists.append(
                        [
                            {
                                "id": f"ocr_{p.doc_id}_{p.page_number}",
                                "content": ocr_esc["text"],
                                "citation": f"{p.filename}:Page {p.page_number} [OCR]",
                                "score": 0.70,
                                "source_type": "ocr",
                                "metadata": {"filename": p.filename, "page": p.page_number},
                            }
                        ]
                    )
                    trace.append(f"Escalation added OCR fallback for {p.filename}:Page {p.page_number}")

        # Escalate to Graph if target entities exist
        if "graph" not in plan.selected_strategies and plan.target_entities:
            for ent in plan.target_entities:
                evs = kg.traverse_multi_hop(ent, max_hops=1)
                g_esc = [
                    {
                        "content": f"{e.source_node.name} {e.relation} {e.target_node.name}",
                        "citation": e.citation,
                        "score": 0.50,
                        "source_type": "graph_escalation",
                        "metadata": {
                            "filename": e.source_node.filename,
                            "start_line": e.provenance_line,
                            "end_line": e.provenance_line,
                        },
                    }
                    for e in evs
                ]
                if g_esc:
                    escalated_lists.append(g_esc)
                    trace.append(f"Escalation added {len(g_esc)} graph edge(s) for '{ent}'")

        fused = fuse_and_deduplicate(escalated_lists, top_k=top_k)
        trace.append(f"Final post-escalation fused results: {len(fused)}")

    return fused, plan, trace
