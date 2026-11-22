"""Try this 2: how often does the cache hit when people phrase a question differently? (make try-cache-keys)

The cache key (EdgeAwareCache.generate_cache_key in src/edge_cache.py) is an MD5 of the exact
query text and filters, so "Tower packet loss" and "tower packet loss" are two keys. This
replays a log of 36 questions (6 questions, each asked 6 ways) through three key rules:

  exact       the code's key, unchanged
  normalized  lowercase, punctuation and extra spaces removed, before the same key
  semantic    reuse a cached answer when the question's embedding is close enough to one
              already cached (cosine at least the threshold)

A hit is "wrong" when the cached top 5 incidents are not the ones a fresh search for that
exact question returns (in any order).
Retrieval runs in NumPy over the sample incidents. No Docker needed.
"""

import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.edge_cache import EdgeAwareCache  # noqa: E402

LOG = [
    ["Tower packet loss", "Tower packet loss", "tower packet loss", "Tower  packet loss ",
     "Tower packet loss?", "packet loss on a tower"],
    ["Router keeps disconnecting", "Router keeps disconnecting", "router keeps disconnecting",
     "Router keeps disconnecting!", "router disconnects frequently", "frequent disconnections on router"],
    ["Firmware update failed", "Firmware update failed", "firmware update failed",
     "Firmware update failed.", "the firmware upgrade did not work", "firmware update failure"],
    ["Latency spikes on repeater", "Latency spikes on repeater", "latency spikes on repeater",
     "Latency  spikes on repeater", "repeater has high latency", "slow responses from the repeater"],
    ["Port flapping on BTS", "Port flapping on BTS", "port flapping on bts", "Port flapping on BTS.",
     "BTS port keeps going up and down", "port flapping observed on BTS"],
    ["Signal degradation on tower", "Signal degradation on tower", "signal degradation on tower",
     "Signal degradation on tower!", "weak signal from the tower", "tower signal is degrading"],
]
TOP_K = 5


def normalize(q):
    return " ".join(re.sub(r"[^\w\s]", " ", q.lower()).split())


def main():
    import logging
    logging.disable(logging.WARNING)  # model-loading logs; the table is the output
    from transformers.utils import logging as hf_logging
    hf_logging.disable_progress_bar()
    from sentence_transformers import SentenceTransformer

    incidents = pd.read_csv(ROOT / "data" / "incidents.csv")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    vectors = model.encode(incidents["description"].tolist(), normalize_embeddings=True, show_progress_bar=False)
    log = [q for group in LOG for q in group]
    qvecs = dict(zip(log, model.encode(log, normalize_embeddings=True, show_progress_bar=False)))

    def search(q):
        return frozenset(np.argsort(-(vectors @ qvecs[q]))[:TOP_K].tolist())

    # The code's key function; it doesn't use the Redis connection, so no Redis is needed here
    def key(q):
        return EdgeAwareCache.generate_cache_key(None, q, zone_filter="Zone 11")

    rules = [("exact (the code)", lambda q: key(q), None),
             ("normalized", lambda q: key(normalize(q)), None)]
    rules += [(f"semantic >= {t:.2f}", None, t) for t in (0.95, 0.90, 0.80, 0.70)]

    print(f"{len(log)} questions ({len(LOG)} asked 6 ways each), replayed in order\n")
    print(f"{'key rule':<18} {'hits':>5} {'hit rate':>9} {'wrong hits':>11}")
    for name, keyfn, threshold in rules:
        cache, hits, wrong = {}, 0, 0
        for q in log:
            if keyfn:
                k = keyfn(q)
            else:  # nearest cached question by embedding
                k = max(cache, key=lambda c: float(qvecs[c] @ qvecs[q]), default=None)
                if k is not None and float(qvecs[k] @ qvecs[q]) < threshold:
                    k = None
            if k is not None and k in cache:
                hits += 1
                wrong += cache[k] != search(q)
            else:
                cache[keyfn(q) if keyfn else q] = search(q)
        print(f"{name:<18} {hits:>5} {hits / len(log):>9.0%} {wrong:>11}")


if __name__ == "__main__":
    main()
