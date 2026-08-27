def rrf_score(rank: int, k: int = 60) -> float:
    return 1.0 / (k + rank + 1)

