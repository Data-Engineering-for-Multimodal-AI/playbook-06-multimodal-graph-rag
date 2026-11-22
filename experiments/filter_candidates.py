"""Try this 1: how many vector candidates does a filtered search need? (make try-filter-candidates)

semantic_search() in src/hybrid_retrieval.py asks the vector index for the nearest
`candidates` incidents (SEARCH ... LIMIT $candidates), then applies the zone and priority
filters (WHERE), then keeps the top 5. Filters that run after the vector search can only
keep what the search returned. The code uses 100 candidates, every incident in the sample.

This runs the same three steps in NumPy over the same all-MiniLM-L6-v2 embeddings, for
several candidate counts, and compares each answer with filtering first (the exact answer).
No Docker needed.
"""

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TOP_K = 5
QUERIES = [
    ("Packet loss observed on Tower", "Zone 11", None),
    ("Packet loss observed on Tower", "Zone 12", "High"),
    ("Router keeps disconnecting", "Zone 14", "High"),
    ("Firmware update failed on the base station", "Zone 12", "Medium"),
    ("Latency spikes on the repeater", "Zone 11", "Low"),
    ("Antenna signal getting weaker", "Zone 14", "Medium"),
]


def main():
    import logging
    logging.disable(logging.WARNING)  # model-loading logs; the table is the output
    from transformers.utils import logging as hf_logging
    hf_logging.disable_progress_bar()
    from sentence_transformers import SentenceTransformer

    incidents = pd.read_csv(ROOT / "data" / "incidents.csv")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    vectors = model.encode(incidents["description"].tolist(), normalize_embeddings=True, show_progress_bar=False)
    queries = model.encode([q for q, _, _ in QUERIES], normalize_embeddings=True, show_progress_bar=False)

    def keep(zone, priority):
        mask = incidents["zone"] == zone
        if priority:
            mask &= incidents["priority"] == priority
        return mask.to_numpy()

    counts = (5, 10, 20, 50, 100)
    returned = {c: 0 for c in counts}
    correct = {c: 0 for c in counts}
    exact_total = 0
    for qv, (_, zone, priority) in zip(queries, QUERIES):
        scores = vectors @ qv
        order = np.argsort(-scores)
        ok = keep(zone, priority)
        exact = [i for i in order if ok[i]][:TOP_K]  # filter first, then rank
        exact_total += len(exact)
        for c in counts:
            got = [i for i in order[:c] if ok[i]][:TOP_K]  # rank, keep c, then filter (as the Cypher does)
            returned[c] += len(got)
            correct[c] += len(set(got) & set(exact))

    print(f"{len(QUERIES)} filtered searches over {len(incidents)} incidents, top {TOP_K} each "
          f"({exact_total} results when filtering first)\n")
    print(f"{'candidates':>10}  {'results returned':>16}  {'same as filtering first':>23}")
    for c in counts:
        print(f"{c:>10}  {returned[c]:>9} of {exact_total:<4} {correct[c] / exact_total:>22.0%}")

    # How the cost of a candidate grows: time to score and sort a larger index in NumPy
    print("\nScoring every vector instead (the exact answer) at larger sizes, in NumPy:")
    rng = np.random.default_rng(0)
    for n in (100, 10_000, 1_000_000):
        big = rng.standard_normal((n, vectors.shape[1]), dtype=np.float32)
        start = time.perf_counter()
        for _ in range(5):
            np.argsort(-(big @ queries[0]))[:TOP_K]
        print(f"  {n:>9,} incidents: {(time.perf_counter() - start) / 5 * 1000:8.2f} ms per query")


if __name__ == "__main__":
    main()
