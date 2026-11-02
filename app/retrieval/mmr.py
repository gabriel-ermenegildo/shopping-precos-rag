"""Maximum Marginal Relevance — diversidade entre os chunks selecionados."""

from __future__ import annotations

import numpy as np


def mmr_select(query_vec, candidate_vecs, k: int, lambda_: float = 0.5) -> list[int]:
    q = np.asarray(query_vec, dtype="float32")
    cand = np.asarray(candidate_vecs, dtype="float32")
    q = q / (np.linalg.norm(q) or 1.0)
    norms = np.linalg.norm(cand, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    cand = cand / norms

    sim_query = cand @ q
    sim_pair = cand @ cand.T
    selected: list[int] = []
    remaining = list(range(len(cand)))

    while remaining and len(selected) < k:
        if not selected:
            best = int(np.argmax(sim_query[remaining]))
            selected.append(remaining.pop(best))
            continue
        mmr_scores = [
            lambda_ * sim_query[i] - (1 - lambda_) * max(sim_pair[i][j] for j in selected)
            for i in remaining
        ]
        best = int(np.argmax(mmr_scores))
        selected.append(remaining.pop(best))
    return selected
