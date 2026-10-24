"""Smoke tests: data, embeddings, the Neo4j graph and vector search, photo search, the Redis cache and the UI.

Run with `make smoke` (or `uv run pytest -q`). CPU only, a few minutes. The first run downloads
all-MiniLM-L6-v2 and CLIP ViT-B/32 from Hugging Face (about 700 MB).

The graph and cache tests need Neo4j 2026.x and Redis (see the README). They are skipped when the
services aren't reachable, unless REQUIRE_SERVICES=1 (as in CI). Like `python main.py --mode graph`,
they replace everything in the Neo4j database the settings point to.
"""

import csv
import json
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
sys.path.insert(0, ROOT)


def main_py(*args, timeout=900):
    result = subprocess.run([sys.executable, "main.py", *args], cwd=ROOT, capture_output=True, text=True,
                            timeout=timeout)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return result.stdout


def service_or_skip(check, name):
    try:
        check()
    except Exception as e:
        if os.environ.get("REQUIRE_SERVICES") == "1":
            raise
        pytest.skip(f"{name} not reachable ({type(e).__name__}); start it to run this test")


# ------------------------------------------------------------------ data and packaging (no services)

def test_sample_data_complete_and_documented():
    with open(os.path.join(DATA, "README.md")) as fh:
        readme = fh.read()
    with open(os.path.join(DATA, "images.csv")) as fh:
        images = list(csv.DictReader(fh))
    assert len(images) == 20
    for row in images:
        assert os.path.exists(os.path.join(DATA, "drone-images", row["image_filename"]))
    for name in os.listdir(DATA):
        if name != "README.md":
            assert f"`{name}" in readme, name
    with open(os.path.join(DATA, "logs.jsonl")) as fh:
        assert len([json.loads(line) for line in fh]) == 150
    with open(os.path.join(DATA, "multimodal_image_features.json")) as fh:
        assert "/Users/" not in fh.read()


def test_no_end_of_life_neo4j_library():
    with open(os.path.join(ROOT, "requirements.txt")) as fh:
        assert not [line for line in fh if line.startswith("py2neo")]
    for path in ["main.py"] + [os.path.join(d, f) for d, _, files in os.walk(os.path.join(ROOT, "src"))
                               for f in files if f.endswith(".py")]:
        with open(os.path.join(ROOT, path)) as fh:
            source = fh.read()
        assert "import py2neo" not in source and "from py2neo" not in source, path


def test_printed_modes_still_exist():
    out = main_py("--help", timeout=60)
    for mode in ["embeddings", "graph", "retrieval", "cache", "full", "app", "all", "photos"]:
        assert mode in out


# ------------------------------------------------------------------ cache (Redis)

def test_cache_ttls_and_partial_entries():
    from src.config import GRAPH_TTL, IMAGE_TTL, TEXT_TTL
    from src.edge_cache import EdgeAwareCache
    cache = None

    def connect():
        nonlocal cache
        cache = EdgeAwareCache()
    service_or_skip(connect, "Redis")

    key = cache.generate_cache_key("smoke test", kind="smoke")
    assert key.startswith("smoke:") and cache.generate_cache_key("smoke test").startswith("query:")
    cache.store_in_cache([{"incident_id": "A"}, {"incident_id": "B", "image": {"filename": "x"}}], key)
    r = cache.redis_client
    assert r.ttl(f"{key}:result:0") <= TEXT_TTL and r.ttl(f"{key}:result:1") > TEXT_TTL
    assert IMAGE_TTL - 5 <= r.ttl(f"{key}:count") <= IMAGE_TTL < GRAPH_TTL   # lives as long as the longest result
    results, _ = cache.get_from_cache(key)
    assert [x["incident_id"] for x in results] == ["A", "B"]
    r.delete(f"{key}:result:0")                                              # as if the text result had expired
    assert cache.get_from_cache(key) is None
    r.delete(f"{key}:result:1", f"{key}:count", f"{key}:timestamp")


def test_cache_mode():
    service_or_skip(lambda: __import__("src.edge_cache", fromlist=["x"]).EdgeAwareCache(), "Redis")
    out = main_py("--mode", "cache", timeout=120)
    assert "Cache hit!" in out and "Sample result: INC903" in out


# ------------------------------------------------------------------ embeddings, graph, retrieval (Neo4j)

@pytest.fixture(scope="module")
def graph():
    from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
    from src.graph_db import Graph
    db = None

    def connect():
        nonlocal db
        db = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    service_or_skip(connect, "Neo4j")
    import numpy as np
    main_py("--mode", "embeddings")
    assert np.load(os.path.join(ROOT, "embeddings", "text_embeddings.npy")).shape == (100, 384)
    assert np.load(os.path.join(ROOT, "embeddings", "image_embeddings.npy")).shape == (20, 512)
    main_py("--mode", "graph")
    main_py("--mode", "graph")           # a rebuild must work too (the first edition's constraints failed)
    yield db
    db.close()


def test_graph_contents(graph):
    counts = {r["label"]: r["n"] for r in graph.run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n")}
    assert counts == {"Zone": 3, "Asset": 96, "Incident": 100, "Technician": 38, "Image": 20}
    assert graph.evaluate("MATCH ()-[r:RELATED_TO]->() RETURN count(r)") == 1
    indexes = {r["name"]: r["state"] for r in graph.run("SHOW VECTOR INDEXES YIELD name, state")}
    assert indexes["incident_text_embedding"] == indexes["image_clip_embedding"] == "ONLINE"


def score(text, label):
    return float(re.search(rf"{label}: ([0-9.]+)", text).group(1))


def test_retrieval_mode(graph):
    out = main_py("--mode", "retrieval")
    first = out.split("Result 1:")[1].split("Result 2:")[0]
    # The first edition's run: INC903 0.7607, INC998 0.7372, INC933 0.6121 (sklearn cosine on the same embeddings)
    assert "Incident ID: INC903" in first and score(first, "Similarity Score") == pytest.approx(0.7607, abs=0.002)
    assert "Incident ID: INC998" in out and "Incident ID: INC933" in out
    assert "How similar resolved incidents were fixed:" in out
    photos = out.split("Drone images matching")[1]
    assert {"INC917", "INC912", "INC916"} <= set(re.findall(r"\((INC\d+),", photos))


def test_filters(graph):
    from src.hybrid_retrieval import HybridRetriever
    retriever = HybridRetriever()
    results = retriever.semantic_search("antenna misaligned", top_k=10, zone_filter="Zone 12", priority_filter="High")
    assert results and all(r["zone"] == "Zone 12" and r["priority"] == "High" for r in results)
    results = retriever.semantic_search("antenna misaligned", top_k=100, time_range=("2025-03-01", "2025-03-31T23:59:59"))
    assert results and all("2025-03-01" <= r["timestamp"] <= "2025-03-31T23:59:59" for r in results)
    scores = [r["similarity_score"] for r in results]
    assert scores == sorted(scores, reverse=True)
    fixes = retriever.similar_resolutions("Packet loss observed on Tower")
    assert sum(f["incidents"] for f in fixes) == 10 and all(f["technicians"] for f in fixes)


def test_photo_mode(graph):
    out = main_py("--mode", "photos")
    blocks = out.split("\nPhotos ")
    assert "INC911_repeater_dusty_solar_array" in blocks[1].splitlines()[1]
    assert "INC909_tower_muddy_base_flooded" in blocks[2].splitlines()[1]
    similar = blocks[3].strip().splitlines()[1:]
    assert len(similar) == 3 and not any("INC909" in line for line in similar)   # the query photo is left out


def test_full_mode_cache_hit(graph):
    service_or_skip(lambda: __import__("src.edge_cache", fromlist=["x"]).EdgeAwareCache().clear_cache(), "Redis")
    out = main_py("--mode", "full")
    assert "Cache hit: False" in out and "Cache hit: True" in out


@pytest.mark.parametrize("model, expected", [
    ("temporal_graph", "Created 97 temporal 'FOLLOWED_BY' edges"),
    ("hierarchical_asset_graph", "classified 100 incidents"),
    ("multimodal_image_graph", "Created 7 HAS_VISUAL_FEATURE relationships"),
    ("spatial_graph", "Created 3 regional clusters"),
    ("resolution_patterns", "Extracted 51 resolution steps"),
])
def test_alternative_graph_models(graph, model, expected):
    result = subprocess.run([sys.executable, "-m", f"src.alternative_graph_models.{model}"], cwd=ROOT,
                            capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stderr[-3000:]
    assert expected in result.stderr
    main_py("--mode", "graph")           # back to the base graph for the next test


def test_streamlit_app(graph):
    service_or_skip(lambda: __import__("src.edge_cache", fromlist=["x"]).EdgeAwareCache(), "Redis")
    from streamlit.testing.v1 import AppTest
    os.environ["PYTHONPATH"] = ROOT
    at = AppTest.from_file(os.path.join(ROOT, "src", "streamlit_app.py"), default_timeout=300)
    at.run()
    assert [t.label for t in at.tabs] == ["Search incidents", "Search by photo"]
    at.text_input[0].input("tower overgrown by trees in a forest")
    next(b for b in at.button if b.label == "Search").click().run()
    assert not at.exception
    assert [s.value for s in at.subheader] == ["Found 3 results:", "How similar resolved incidents were fixed",
                                               "Drone photos matching the query"]
    at.selectbox[0].select("INC909_tower_muddy_base_flooded.jpeg")
    next(b for b in at.button if b.label == "Find similar photos").click().run()
    assert not at.exception
    shown = [m.value for m in at.markdown if m.value.startswith("**INC")]
    assert len(shown) == 3 and not any(m.startswith("**INC909**") for m in shown)
