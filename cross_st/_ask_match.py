"""
FAQ matcher for st-ask: TF-IDF + rapidfuzz token-set ratio.
Implements: find_matches(query, faq_entries, top_k=3)
"""

# Lazy import for scikit-learn and rapidfuzz
import importlib

def _lazy_imports():
    global TfidfVectorizer, rapidfuzz
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
    except ImportError:
        print("scikit-learn not installed. Run: pip install scikit-learn")
        raise
    try:
        import rapidfuzz
    except ImportError:
        print("rapidfuzz not installed. Run: pip install rapidfuzz")
        raise
    return TfidfVectorizer, rapidfuzz

def find_matches(query, faq_entries, top_k=3):
    """
    Returns top_k FAQ entries matching the query.
    Each entry: {"id": ..., "question": ..., "answer": ...}
    """
    TfidfVectorizer, rapidfuzz = _lazy_imports()
    questions = [entry["question"] for entry in faq_entries]
    vectorizer = TfidfVectorizer().fit(questions)
    query_vec = vectorizer.transform([query])
    faq_vecs = vectorizer.transform(questions)
    scores = (faq_vecs * query_vec.T).toarray().flatten()
    # Combine with rapidfuzz token_set_ratio
    fuzz_scores = [rapidfuzz.fuzz.token_set_ratio(query, q)/100 for q in questions]
    combined = [(0.7*s + 0.3*f, i) for i, (s, f) in enumerate(zip(scores, fuzz_scores))]
    combined.sort(reverse=True)
    results = []
    for score, idx in combined[:top_k]:
        entry = dict(faq_entries[idx])
        entry["_score"] = score
        results.append(entry)
    return results

