from backend.app.retrieval import BM25Retriever, HybridRetrieverV2, expand_query


def test_query_expansion_adds_domain_aliases():
    assert "pathological complete response" in expand_query("HER2 pCR")


def test_bm25_and_hybrid_return_ranked_documents():
    docs = ["PIK3CA mutation and pCR", "unrelated survival study"]
    assert BM25Retriever(docs).search("PIK3CA", 1)[0][0] == 0
    assert HybridRetrieverV2(docs).search("PIK3CA", 1)[0][0] == 0
