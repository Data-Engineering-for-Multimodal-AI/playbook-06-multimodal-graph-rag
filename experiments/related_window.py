"""Try this 3: how wide should the RELATED_TO window be? (make try-related-window)

The graph links two incidents on the same asset with a RELATED_TO edge when they are at
most 72 hours apart (RELATED_WINDOW_HOURS in src/graph_construction.py). The retrieval
step shows these edges as "Related Incidents" under each result. This runs the code's own
create_related_incident_edges() with other windows, against a stand-in for Neo4j that
counts the edges it would create, and reports how many incidents get any related incident.
It also counts edges between two different physical assets: the edges group incidents by
asset_id alone, while Asset nodes are keyed by asset_id, asset_type and zone together, and
the sample reuses IDs (R96 is a Router in Zone 11, a Router in Zone 14 and a Repeater in Zone 14).
No Docker needed.
"""

import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
logging.disable(logging.WARNING)
import src.graph_construction as gc  # noqa: E402


class CountingGraph:
    """Records the RELATED_TO edges instead of writing them to Neo4j."""

    def __init__(self):
        self.edges = []

    def run(self, query, **params):
        self.edges.append((params["id1"], params["id2"], params["time_diff"]))


def main():
    incidents = pd.read_csv(ROOT / "data" / "incidents.csv")
    per_asset = incidents.groupby("asset_id").size()
    print(f"{len(incidents)} incidents on {len(per_asset)} asset IDs; "
          f"{int((per_asset > 1).sum())} IDs have more than one incident\n")
    physical = {r.incident_id: (r.asset_id, r.asset_type, r.zone) for r in incidents.itertuples()}
    print(f"{'window':>8} {'RELATED_TO edges':>17} {'incidents with a related one':>29} {'median gap':>11} "
          f"{'edges across two assets':>24}")
    for hours in (24, 72, 168, 720, 2160):
        constructor = gc.GraphConstructor.__new__(gc.GraphConstructor)  # no Neo4j connection
        constructor.graph = CountingGraph()
        constructor.incidents_df = incidents.copy()
        gc.RELATED_WINDOW_HOURS = hours
        constructor.create_related_incident_edges()
        edges = constructor.graph.edges
        linked = {i for a, b, _ in edges for i in (a, b)}
        gap = f"{pd.Series([d for _, _, d in edges]).median() / 24:.1f} days" if edges else "-"
        label = f"{hours} h" if hours < 168 else f"{hours // 24} d"
        across = sum(physical[a] != physical[b] for a, b, _ in edges)
        print(f"{label:>8} {len(edges):>17} {len(linked):>29} {gap:>11} {across:>24}")


if __name__ == "__main__":
    main()
