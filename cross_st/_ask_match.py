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

def _strip_stopwords(text):
    """Lower-case *text* and drop English stop words, so the fuzzy score
    reflects meaningful tokens rather than the shared question prefix."""
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    tokens = [t for t in text.lower().split() if t not in ENGLISH_STOP_WORDS]
    # If everything was a stop word, fall back to the raw text so the
    # comparison still has something to work with.
    return " ".join(tokens) if tokens else text.lower()

def find_matches(query, faq_entries, top_k=3):
    """
    Returns top_k FAQ entries matching the query.
    Each entry: {"id": ..., "question": ..., "answer": ...}
    """
    TfidfVectorizer, rapidfuzz = _lazy_imports()
    questions = [entry["question"] for entry in faq_entries]
    # Drop English stop words ("how", "do", "i", "a", …) so shared filler
    # in every FAQ question ("How do I … cross-st?") doesn't inflate the
    # score of an unrelated query. Fall back to no stop-word list if the
    # filtered vocabulary would be empty (e.g. a corpus of only stop words).
    try:
        vectorizer = TfidfVectorizer(stop_words="english").fit(questions)
    except ValueError:
        vectorizer = TfidfVectorizer().fit(questions)
    query_vec = vectorizer.transform([query])
    faq_vecs = vectorizer.transform(questions)
    scores = (faq_vecs * query_vec.T).toarray().flatten()
    # Combine with rapidfuzz token_set_ratio, ignoring shared stop words so
    # the fuzzy component isn't dominated by the common question prefix.
    fuzz_scores = [
        rapidfuzz.fuzz.token_set_ratio(
            _strip_stopwords(query), _strip_stopwords(q)
        ) / 100
        for q in questions
    ]
    combined = [(0.7*s + 0.3*f, i) for i, (s, f) in enumerate(zip(scores, fuzz_scores))]
    combined.sort(reverse=True)
    results = []
    for score, idx in combined[:top_k]:
        entry = dict(faq_entries[idx])
        entry["_score"] = score
        results.append(entry)
    return results

