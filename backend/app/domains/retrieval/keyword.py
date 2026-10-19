def score_text(query: str, text: str) -> float:
    terms = [item for item in query.lower().split() if item]
    return sum(text.lower().count(term) for term in terms)
