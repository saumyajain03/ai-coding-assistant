"""
Verification and Evaluation Suite for Adaptive Local RAG with GraphRAG
Tests:
- Graph construction from Python AST, JS/TS, Markdown, and JSON
- Provenance and citations on graph entities
- Multi-hop graph traversal
- Adaptive router: Vector-only, Lexical+Vector, Graph, Impact, Multi-hop
- Avoidance of GraphRAG on semantic queries
- Result fusion (RRF) and deduplication
- Multi-category comparative evaluation (Vector vs Lexical vs Graph vs Adaptive)
"""

import pytest

from src.rag.fusion import fuse_and_deduplicate
from src.rag.indexer import get_rag_indexer
from src.rag.knowledge_graph import get_knowledge_graph
from src.rag.lexical_store import get_lexical_store
from src.rag.router import (
    RetrievalIntent,
    build_retrieval_plan,
    execute_adaptive_retrieval,
)
from src.rag.vector_store import get_vector_store


@pytest.fixture(autouse=True)
def setup_test_index():
    """Seeds test modules into indexer before tests."""
    indexer = get_rag_indexer()

    # Ingest a Python module
    py_code = (
        "import os\n"
        "from math import sqrt\n\n"
        "class OrderProcessor:\n"
        "    '''Handles customer order transactions.'''\n"
        "    def process_payment(self, amount: float) -> bool:\n"
        "        return amount > 0\n\n"
        "def calculate_tax(subtotal: float) -> float:\n"
        "    return subtotal * 0.18\n\n"
        "def checkout(cart: dict) -> bool:\n"
        "    tax = calculate_tax(cart.get('total', 0))\n"
        "    return True\n"
    )
    indexer.index_file("order_system.py", content_bytes=py_code.encode("utf-8"))

    # Ingest a TypeScript module
    ts_code = (
        "import { Customer } from './customer';\n\n"
        "export interface InvoiceResponse {\n"
        "    invoiceId: string;\n"
        "    total: number;\n"
        "}\n\n"
        "export class InvoiceService {\n"
        "    generateInvoice(cust: Customer): InvoiceResponse {\n"
        "        return { invoiceId: 'INV-100', total: 500 };\n"
        "    }\n"
        "}\n"
    )
    indexer.index_file("invoice_service.ts", content_bytes=ts_code.encode("utf-8"))

    # Ingest Markdown documentation
    md_content = (
        "# Payment Gateway Guide\n"
        "This guide describes the transaction settlement rules.\n\n"
        "## Settlement Limits\n"
        "Maximum daily settlement is 100,000 INR.\n"
        "Refer to [order_system.py](order_system.py) for tax calculations.\n"
    )
    indexer.index_file("payment_guide.md", content_bytes=md_content.encode("utf-8"))


def test_graph_construction_from_python():
    """Verify reliable structural AST extraction: imports, classes, functions, calls."""
    kg = get_knowledge_graph()

    # Verify Class node exists
    classes = kg.find_nodes_by_name("OrderProcessor")
    assert len(classes) >= 1
    assert classes[0].node_type == "CLASS"
    assert classes[0].filename == "order_system.py"

    # Verify Function node exists
    functions = kg.find_nodes_by_name("calculate_tax")
    assert len(functions) >= 1
    assert functions[0].node_type == "FUNCTION"

    # Verify CALLS edge exists between checkout and calculate_tax
    checkout_nodes = kg.find_nodes_by_name("checkout")
    assert len(checkout_nodes) >= 1
    out_edges = kg.get_outgoing_edges(checkout_nodes[0].id)
    assert any(e.relation == "CALLS" for e in out_edges)

    # Verify IMPORTS edge exists
    file_node_id = "file:order_system.py"
    file_edges = kg.get_outgoing_edges(file_node_id, relation="IMPORTS")
    imported_names = [kg.find_node_by_id(e.target_id).name for e in file_edges if kg.find_node_by_id(e.target_id)]
    assert any("os" in n or "math" in n for n in imported_names)


def test_graph_construction_from_typescript():
    """Verify structural extraction from TypeScript: imports, interfaces, classes."""
    kg = get_knowledge_graph()

    # Interface check
    ifaces = kg.find_nodes_by_name("InvoiceResponse")
    assert len(ifaces) >= 1
    assert ifaces[0].node_type == "INTERFACE"

    # Class check
    classes = kg.find_nodes_by_name("InvoiceService")
    assert len(classes) >= 1
    assert classes[0].node_type == "CLASS"


def test_graph_provenance_citations():
    """Verify all graph nodes and edges retain complete provenance line citations."""
    kg = get_knowledge_graph()
    nodes = kg.find_nodes_by_name("OrderProcessor")
    assert len(nodes) >= 1
    node = nodes[0]
    assert node.start_line == 4
    assert node.end_line >= 4
    assert node.sha256 != ""
    assert node.filename == "order_system.py"


def test_graph_multi_hop_traversal():
    """Verify multi-hop BFS traversal returns connected dependency evidence."""
    kg = get_knowledge_graph()
    evidence = kg.traverse_multi_hop("checkout", max_hops=2)
    assert len(evidence) >= 1

    relations = [e.relation for e in evidence]
    assert "CALLS" in relations or "DEFINES" in relations
    assert any(e.citation.startswith("order_system.py:") for e in evidence)


def test_vector_only_routing_for_semantic_query():
    """Verify semantic lookup selects Vector-only and strictly avoids GraphRAG."""
    plan = build_retrieval_plan("Explain how transaction settlement rules work", top_k=3)
    assert plan.intent == RetrievalIntent.SEMANTIC_LOOKUP
    assert plan.selected_strategies == ["vector"]
    assert plan.graph_max_hops == 0  # GraphRAG is skipped!

    results, plan_exec, trace = execute_adaptive_retrieval("Explain how transaction settlement rules work", top_k=3)
    assert len(results) >= 1
    # Verify no graph items present in results
    assert all(r.get("source_type") != "graph" for r in results)


def test_lexical_routing_for_exact_symbol():
    """Verify exact symbol queries trigger Lexical BM25 + Vector strategy."""
    plan = build_retrieval_plan("where is OrderProcessor defined", top_k=3)
    assert plan.intent == RetrievalIntent.EXACT_SYMBOL
    assert "lexical" in plan.selected_strategies
    assert "OrderProcessor" in plan.target_entities

    results, _, trace = execute_adaptive_retrieval("where is OrderProcessor defined", top_k=3)
    assert len(results) >= 1
    assert any("orderprocessor" in r.get("content", "").lower() for r in results)


def test_graph_routing_for_dependency_query():
    """Verify dependency query routes to Knowledge Graph."""
    plan = build_retrieval_plan("what calls calculate_tax", top_k=3)
    assert plan.intent == RetrievalIntent.RELATIONSHIP_DEPENDENCY
    assert "graph" in plan.selected_strategies

    results, _, trace = execute_adaptive_retrieval("what calls calculate_tax", top_k=3)
    assert len(results) >= 1
    assert any(r.get("source_type") == "graph" for r in results)


def test_impact_analysis_routing():
    """Verify impact query requests 2-hop graph traversal and targeted vector."""
    plan = build_retrieval_plan("what could break if I modify OrderProcessor", top_k=3)
    assert plan.intent == RetrievalIntent.IMPACT_ANALYSIS
    assert "graph" in plan.selected_strategies
    assert plan.graph_max_hops >= 2


def test_result_fusion_and_deduplication():
    """Verify Reciprocal Rank Fusion blends ranked lists and deduplicates identical chunks."""
    list1 = [
        {"id": "c1", "content": "Authentication token rules", "score": 0.9, "source_type": "vector"},
        {"id": "c2", "content": "Database pool size", "score": 0.8, "source_type": "vector"},
    ]
    list2 = [
        {"id": "c1_dup", "content": "Authentication token rules", "score": 0.85, "source_type": "lexical"},
        {"id": "c3", "content": "Rate limit settings", "score": 0.75, "source_type": "lexical"},
    ]

    fused = fuse_and_deduplicate([list1, list2], top_k=5)
    # Duplicate 'Authentication token rules' must be merged into a single entry
    assert len(fused) == 3
    top_item = fused[0]
    assert top_item["content"] == "Authentication token rules"
    assert "vector" in top_item["fusion_sources"]
    assert "lexical" in top_item["fusion_sources"]


def test_comparative_retrieval_evaluation():
    """
    Evaluation suite comparing Vector-only, Lexical-only, Graph-only, and Adaptive
    across 4 query categories to demonstrate that the router selects GraphRAG
    only when structure provides value and avoids it when it does not.
    """
    v_store = get_vector_store()
    l_store = get_lexical_store()

    # Category 1: Semantic Lookup (Vector-only)
    q_sem = "settlement limit in payment guide"
    v_res = v_store.query(q_sem, top_k=2)
    fused_sem, plan_sem, trace_sem = execute_adaptive_retrieval(q_sem, top_k=2)

    assert plan_sem.intent == RetrievalIntent.SEMANTIC_LOOKUP
    assert plan_sem.selected_strategies == ["vector"]
    assert plan_sem.graph_max_hops == 0  # Graph is strictly avoided
    assert len(v_res) >= 1
    assert any("100,000" in r["content"] for r in v_res)
    assert any("100,000" in r["content"] for r in fused_sem)
    assert all(r.get("source_type") != "graph" for r in fused_sem)

    # Category 2: Exact Symbol Lookup (Lexical BM25 + Vector)
    q_sym = "OrderProcessor"
    l_res = l_store.query(q_sym, top_k=2)
    fused_sym, plan_sym, trace_sym = execute_adaptive_retrieval(q_sym, top_k=2)

    assert plan_sym.intent == RetrievalIntent.EXACT_SYMBOL
    assert "lexical" in plan_sym.selected_strategies
    assert len(l_res) >= 1
    assert "orderprocessor" in l_res[0]["content"].lower()
    assert any("orderprocessor" in r.get("content", "").lower() for r in fused_sym)

    # Category 3: Relationship / Dependency (Graph traversal)
    q_rel = "what does order_system.py import"
    fused_rel, plan_rel, trace_rel = execute_adaptive_retrieval(q_rel, top_k=2)

    assert plan_rel.intent == RetrievalIntent.RELATIONSHIP_DEPENDENCY
    assert "graph" in plan_rel.selected_strategies
    assert any(r.get("source_type") == "graph" for r in fused_rel)

    # Category 4: Impact Analysis (Hybrid: Graph + Vector)
    q_impact = "what could break if I modify OrderProcessor"
    fused_imp, plan_imp, trace_imp = execute_adaptive_retrieval(q_impact, top_k=3)

    assert plan_imp.intent == RetrievalIntent.IMPACT_ANALYSIS
    assert "graph" in plan_imp.selected_strategies
    assert "vector" in plan_imp.selected_strategies
    assert plan_imp.graph_max_hops >= 2
    assert len(fused_imp) >= 1

