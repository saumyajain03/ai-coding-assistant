"""
Tests for Semantic Visual RAG Capability.
Validates:
1. Normal text PDF still follows existing vector route
2. Scanned PDF still uses real OCR
3. Visual diagram invokes Visual RAG
4. Paraphrased/natural-language visual queries work without keyword overlap (e.g. Heart diagram)
5. Complex architecture diagrams and mixed PDFs route to visual processing when required
6. OCR-only success is NOT counted as semantic visual success
7. Lazy visual processing and disk cache reuse
8. Router decisions do NOT depend on a single keyword such as "diagram"
9. Safe graceful fallback without fabrication when Visual RAG is disabled
"""

from pathlib import Path
from unittest.mock import patch

from src.config import get_settings
from src.rag.canonical_page import VisualStatus, get_canonical_page_store
from src.rag.router import (
    RetrievalIntent,
    build_retrieval_plan,
    execute_adaptive_retrieval,
)
from src.rag.visual_engine import (
    DiagramTextExtractor,
    LazyVisualRAGEngine,
    SemanticVisualEngine,
    VisualRegionExtractor,
    VisualSemantics,
    get_visual_engine,
)


# 1. Normal text PDF still follows existing route
def test_01_normal_pdf_still_follows_existing_vector_route():
    query = "What is the primary storage voucher encryption algorithm in targeted_text_only.pdf?"
    plan = build_retrieval_plan(query)
    assert plan.intent == RetrievalIntent.SEMANTIC_LOOKUP
    assert plan.selected_strategies == ["vector"]
    assert "visual" not in plan.selected_strategies
    assert "ocr" not in plan.selected_strategies


# 2. Scanned PDF still uses real OCR
def test_02_scanned_pdf_still_uses_ocr():
    query = "What does the scanned document say about the incident in targeted_scanned.pdf?"
    plan = build_retrieval_plan(query)
    assert plan.intent == RetrievalIntent.SCANNED_TEXT
    assert "ocr" in plan.selected_strategies


# 3. Visual diagram invokes Visual RAG
def test_03_visual_diagram_invokes_visual_rag():
    settings = get_settings()
    with patch.object(settings, "ENABLE_VISUAL_RAG", True):
        v_engine = get_visual_engine()
        with patch.object(v_engine, "_model_loaded", True):
            query = "What is shown in the performance analysis diagram in targeted_visual_heavy.pdf?"
            plan = build_retrieval_plan(query)
            assert plan.intent == RetrievalIntent.VISUAL_QUESTION
            assert "visual" in plan.selected_strategies


# 4. Paraphrased/natural-language visual queries work without keyword overlap (Heart Diagram Example)
def test_04_paraphrased_natural_language_visual_queries_work_without_keyword_overlap():
    """
    Heart diagram contains label 'Right Atrium'.
    Query asks: 'Which chamber receives blood returning from the body?'
    No literal word from the query ('chamber', 'receives', 'blood', 'returning', 'body')
    is present in the diagram label 'Right Atrium'.
    Semantic Visual Engine must retrieve the visual evidence via functional understanding.
    """
    settings = get_settings()
    with patch.object(settings, "ENABLE_VISUAL_RAG", True):
        v_engine = LazyVisualRAGEngine()
        with patch.object(v_engine, "_model_loaded", True):
            custom_heart_region = [
                {
                    "region_id": "heart_diag_1",
                    "doc_id": "doc_heart_test",
                    "filename": "cardiac_anatomy.pdf",
                    "page_number": 1,
                    "bounding_box": (0.1, 0.1, 0.9, 0.8),
                    "region_type": "DIAGRAM",
                    "image_hash": "sha_heart_001",
                    "caption": "Circulatory System: Cardiac Chambers and Flow",
                    "diagram_text": "Superior Vena Cava\nInferior Vena Cava\nRight Atrium\nTricuspid Valve\nRight Ventricle\nPulmonary Artery\nPulmonary Veins\nLeft Atrium\nMitral Valve\nLeft Ventricle\nAorta",
                    "embedding_model": "deterministic-histogram-v1",
                    "has_genuine_embedding": True,
                }
            ]

            v_engine.clear_cache("doc_heart_test")
            processed = v_engine.process_page_visual(
                doc_id="doc_heart_test",
                filename="cardiac_anatomy.pdf",
                page_number=1,
                custom_regions=custom_heart_region,
            )

            assert processed["status"] == VisualStatus.COMPLETED.value
            assert len(processed["regions"]) == 1
            region = processed["regions"][0]
            assert "semantics" in region

            # Test semantic query without literal label match
            query = "Which chamber receives blood returning from the body?"

            # Verify literal overlap with "Right Atrium" is zero
            label_tokens = {"right", "atrium"}
            query_tokens = {"which", "chamber", "receives", "blood", "returning", "from", "the", "body"}
            assert len(label_tokens.intersection(query_tokens)) == 0

            # Score query through SemanticVisualEngine
            sem_engine = SemanticVisualEngine()
            score, is_semantic_match = sem_engine.score_query(
                query=query,
                region=region,
                semantics=region["semantics"],
            )

            assert score >= 0.70
            assert is_semantic_match is True


# 5. Complex architecture diagrams: natural language query without keyword overlap
def test_05_complex_architecture_diagram_semantic_query():
    """
    targeted_visual_heavy.pdf diagram contains 'Service A -> Service B -> Database Write Lock Bottleneck at 4500 IOPS'.
    Query: 'Where does the system stall under high concurrency transaction volume?'
    Words 'stall', 'concurrency', 'transaction', 'volume' are NOT in the diagram labels.
    """
    settings = get_settings()
    with patch.object(settings, "ENABLE_VISUAL_RAG", True):
        v_engine = get_visual_engine()
        with patch.object(v_engine, "_model_loaded", True):
            store = get_canonical_page_store()
            p_rec = store.get_page("targeted_visual_heavy.pdf", 1)

            vis_res = v_engine.process_page_visual(
                doc_id=p_rec.doc_id,
                filename=p_rec.filename,
                page_number=1,
            )
            assert vis_res["status"] == VisualStatus.COMPLETED.value
            reg = vis_res["regions"][0]

            query = "Where does the system stall under high concurrency transaction volume?"
            score, is_semantic = v_engine.semantic_engine.score_query(
                query=query,
                region=reg,
                semantics=reg.get("semantics", {}),
            )

            assert score >= 0.70
            assert is_semantic is True



# 6. Mixed PDF can route to visual processing when required (Page 3 diagram)
def test_06_mixed_pdf_routes_to_visual_processing_when_required():
    """
    targeted_mixed.pdf has Page 3 as a MIXED_PAGE with visual modality.
    Query asks about high availability failover promotion.
    """
    settings = get_settings()
    with patch.object(settings, "ENABLE_VISUAL_RAG", True):
        v_engine = get_visual_engine()
        with patch.object(v_engine, "_model_loaded", True):
            v_engine.clear_cache()
            query = "How does the failover promote standby backup node on Page 3 in targeted_mixed.pdf?"
            plan = build_retrieval_plan(query)
            assert plan.intent == RetrievalIntent.VISUAL_QUESTION
            assert "visual" in plan.selected_strategies

            results, plan_res, trace = execute_adaptive_retrieval(query, top_k=3)
            assert any(r.get("source_type") == "visual" for r in results)
            vis_result = next(r for r in results if r.get("source_type") == "visual")
            assert "Page 3" in vis_result["citation"]



# 7. OCR-only success is NOT counted as semantic visual success
def test_07_ocr_only_success_is_not_counted_as_semantic_visual_success():
    """
    Literal keyword matches without semantic understanding must report
    is_semantic_match=False.
    """
    sem_engine = SemanticVisualEngine()
    region = {
        "diagram_text": "Invoice Number 1042 Total Balance Due $500",
        "region_type": "DIAGRAM",
    }
    semantics = sem_engine.analyze_semantics(region["diagram_text"], region["region_type"])

    # Literal keyword query
    literal_query = "Invoice Number 1042 Total Balance Due"
    score, is_semantic = sem_engine.score_query(literal_query, region, semantics)
    assert score >= 0.70
    # Literal keyword match should NOT be marked as semantic match
    assert is_semantic is False


# 8. Lazy visual processing and disk cache reuse
def test_08_lazy_visual_processing_and_cache_reuse():
    settings = get_settings()
    with patch.object(settings, "ENABLE_VISUAL_RAG", True):
        v_engine = LazyVisualRAGEngine()
        with patch.object(v_engine, "_model_loaded", True):
            store = get_canonical_page_store()
            p_rec = store.get_page("targeted_visual_heavy.pdf", 1)

            # Clear cache to guarantee first run computes from scratch
            v_engine.clear_cache(p_rec.doc_id)
            res1 = v_engine.process_page_visual(p_rec.doc_id, p_rec.filename, 1)
            assert res1["cached"] is False

            cache_file = Path(settings.VISUAL_CACHE_DIR) / f"{p_rec.doc_id}_p1.json"
            assert cache_file.exists()

            # Second run: cache hit
            res2 = v_engine.process_page_visual(p_rec.doc_id, p_rec.filename, 1)
            assert res2["cached"] is True
            assert len(res2["regions"]) == len(res1["regions"])


# 9. Router decisions do NOT depend on a single keyword such as "diagram"
def test_09_router_does_not_depend_on_single_keyword_diagram():
    """
    Verifies that queries without the word 'diagram' (e.g. 'which chamber', 'bottleneck stall')
    correctly route to Visual RAG when targeting visual documents.
    """
    settings = get_settings()
    with patch.object(settings, "ENABLE_VISUAL_RAG", True):
        v_engine = get_visual_engine()
        with patch.object(v_engine, "_model_loaded", True):
            queries_without_diagram_keyword = [
                "Which chamber receives blood returning from the body in targeted_visual_heavy.pdf?",
                "Where is the write lock bottleneck under high IOPS in targeted_visual_heavy.pdf?",
                "What is shown on Page 3 in targeted_mixed.pdf?",
            ]
            for q in queries_without_diagram_keyword:
                plan = build_retrieval_plan(q)
                assert plan.intent == RetrievalIntent.VISUAL_QUESTION
                assert "visual" in plan.selected_strategies


# 10. Fallback remains only as a safe failure mode without fabrication
def test_10_fallback_remains_safe_failure_mode_without_fabrication():
    """
    When ENABLE_VISUAL_RAG=False, the router gracefully degrades to text vector/BM25
    without throwing exceptions and without fabricating fake visual embeddings.
    """
    settings = get_settings()
    with patch.object(settings, "ENABLE_VISUAL_RAG", False):
        query = "What does the architecture chart show in targeted_visual_heavy.pdf?"
        plan = build_retrieval_plan(query)
        assert plan.intent == RetrievalIntent.SEMANTIC_LOOKUP
        assert "visual" not in plan.selected_strategies
        assert "vector" in plan.selected_strategies

        results, plan_res, trace = execute_adaptive_retrieval(query, top_k=2)
        assert len(results) > 0
        # No fake visual results fabricated
        assert all(r.get("source_type") != "visual" for r in results)


# 11. Separation of Concerns: OCR, Region Extraction, and Semantic Understanding
def test_11_separation_of_concerns_modular_subsystems():
    """
    Asserts distinct subsystem components exist and have distinct responsibilities.
    """
    text_extractor = DiagramTextExtractor()
    region_extractor = VisualRegionExtractor()
    semantic_engine = SemanticVisualEngine()

    assert hasattr(text_extractor, "extract_diagram_text")
    assert hasattr(region_extractor, "extract_pixel_features")
    assert hasattr(semantic_engine, "analyze_semantics")
    assert hasattr(semantic_engine, "score_query")

    # Semantic analysis produces structured VisualSemantics dynamically
    semantics = semantic_engine.analyze_semantics(
        "Service A -> Service B -> Database Write Lock Bottleneck at 4500 IOPS",
        "DIAGRAM",
    )
    assert isinstance(semantics, VisualSemantics)
    assert len(semantics.relationships) >= 1
    assert "Database Write Lock Bottleneck at 4500 IOPS" in semantics.components
    assert len(semantics.semantic_concepts) >= 1

