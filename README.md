# Engineering Graph-Augmented Retrieval and Edge-Aware Caching for Multimodal AI

**Chapter 6 playbook** from *Data Engineering for Multimodal AI* (O'Reilly, 2026). Page numbers to be confirmed.
Book: https://oreil.ly/data-engineering-multimodal

> Want the code exactly as printed? Use the `first-edition` tag. This branch is the 2026 maintenance update; see [Differences from the printed book](#differences-from-the-printed-book).

## What you'll build

A hybrid memory system for real-time, context-aware retrieval over a multimodal dataset of telecom infrastructure incidents: 100 incident reports, 20 drone inspection photos, and the assets, zones and technicians they involve. It combines semantic search, a knowledge graph and caching tuned for edge-style workloads.

- **Multimodal embeddings**: sentence embeddings (all-MiniLM-L6-v2) for incident descriptions and CLIP embeddings for drone photos
- **Knowledge graph in Neo4j**: incidents, assets, zones, technicians and images, with the embeddings stored on the nodes and indexed for vector search
- **Hybrid retrieval**: vector search with structured filters (zone, priority, time) in one Cypher query, then graph context for each result (zone, asset, technician, photo, related incidents)
- **Photo search**: find drone photos from a description ("solar panels covered in desert dust") or from another photo
- **How similar incidents were resolved**: the nearest resolved incidents, grouped by fix, with the technicians who applied it
- **Edge-aware caching in Redis**: per-modality TTLs (text 1 h, images 6 h, graph context 12 h) and fingerprinted cache keys
- **Streamlit UI**: incident search with images and graph views, and search by photo
- **Alternative graph models**: five ways to extend the base graph (temporal, hierarchical, image features, spatial, resolution patterns)

Everything runs on a laptop CPU with the bundled sample data. Neo4j and Redis run locally (installed, or in Docker). The first run downloads the two models from Hugging Face (about 700 MB).

## Quick start

You need Python 3.12 or newer, about 2 GB of disk space (1.4 GB for the environment, 0.7 GB for the models), and Neo4j 2026.x and Redis running locally.

```bash
# Clone the repository
git clone https://github.com/Data-Engineering-for-Multimodal-AI/playbook-06-multimodal-graph-rag.git
cd playbook-06-multimodal-graph-rag

# Create and activate a virtual environment, then install dependencies
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Start Neo4j and Redis.** Install them ([Neo4j](https://neo4j.com/deployment-center/), [Redis](https://redis.io/downloads/)) and start them, or run them in Docker:

```bash
docker run -d --name pb06-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/changeThisPassword neo4j:2026.10
docker run -d --name pb06-redis -p 6379:6379 redis:8
```

The code needs a Neo4j release with the Cypher `SEARCH` clause for vector indexes (tested on 2026.10.1). The connection settings default to the values above; to change them, export the variables in [`.env.example`](.env.example) (for example `export NEO4J_PASSWORD=...`).

> **Use an empty database.** `python main.py --mode graph` deletes everything in the Neo4j database it connects to before building the graph, as in the book. The cache only adds and removes its own keys in Redis.

**Run the playbook:**

```bash
python main.py --mode embeddings   # text and image embeddings -> embeddings/
python main.py --mode graph        # build the Neo4j graph, store the embeddings, create the vector indexes
python main.py --mode retrieval    # hybrid retrieval for a sample query
python main.py --mode photos       # photo search from descriptions and from a photo
python main.py --mode cache        # the edge-aware cache on its own
python main.py --mode full         # retrieval with caching: a miss, then a hit
python main.py --mode app          # Streamlit UI at http://127.0.0.1:8501
```

`python main.py --mode all` runs them all in order and ends with the UI. The UI listens on this machine only; set `HOST=0.0.0.0` to open it to your network.

### Checks

```bash
make smoke        # or: uv run pytest -q
```

The smoke tests check the data, packaging, embeddings, graph, vector search and filters, photo search, cache, the five alternative graph models and the UI (about 3 minutes). The Neo4j and Redis tests are skipped if the services aren't running. GitHub Actions runs everything on Python 3.12 and 3.13 with Neo4j 2026.10 and Redis 8, plus the printed `pip install -r requirements.txt` path.

## System architecture

The system has five main components:

1. **Multimodal embedding pipelines** (`src/embedding_pipeline.py`)
   - Text: all-MiniLM-L6-v2 sentence embeddings (384 numbers) for incident descriptions
   - Images: CLIP ViT-B/32 embeddings (512 numbers) for drone photos

2. **Graph construction in Neo4j** (`src/graph_construction.py`)
   - Nodes: Incident, Asset, Zone, Technician, Image
   - Edges: OCCURRED_IN, AFFECTS, LOCATED_IN, RESOLVED_BY, HAS_IMAGE, RELATED_TO (same asset within 72 hours)
   - Vector indexes: `incident_text_embedding` on `Incident.text_embedding`, `image_clip_embedding` on `Image.clip_embedding`

3. **Hybrid retrieval** (`src/hybrid_retrieval.py`)
   - `semantic_search`: vector search with structured filters, in Cypher:
     ```cypher
     MATCH (i:Incident)
       SEARCH i IN (VECTOR INDEX incident_text_embedding FOR $embedding LIMIT $candidates)
       SCORE AS score
     WHERE ($zone IS NULL OR i.zone = $zone) AND ...
     ```
   - `enrich_with_graph_context`: related incidents, technician, zone, asset and photo for each result
   - `search_images`: drone photos for a text description or a photo (CLIP puts both in the same space)
   - `similar_resolutions`: the 10 most similar resolved incidents, grouped by resolution, with technicians through RESOLVED_BY

4. **Edge-aware caching in Redis** (`src/edge_cache.py`, `src/retrieval_system.py`)
   - Modality-specific TTLs: text 1 h, images 6 h, graph traces 12 h
   - Fingerprint-based cache keys (an MD5 of the query and filters), prefixed by kind: `query:`, `photos:`, `resolutions:`

5. **Query interface in Streamlit** (`src/streamlit_app.py`)
   - **Search incidents**: results with metadata, drone photo, graph view of related incidents, how similar incidents were fixed, and matching photos
   - **Search by photo**: pick a sample drone photo or upload one, and see incidents with similar-looking photos
   - Performance metrics: retrieval time, cache hit or miss, cache age

## Alternative graph models

The project includes several alternative graph construction approaches, each with unique capabilities:

1. **Temporal graph model**: temporal relationships between incidents, pattern nodes for recurring issues, time-based querying
2. **Hierarchical asset classification**: a taxonomy of assets and failure types, failure classification for incidents, hierarchical queries across asset categories
3. **Multimodal image integration**: image features linked to incidents, visual similarity relationships between assets, feature-based queries
4. **Spatial integration**: (mock) geographic coordinates for zones, proximity relationships, regional patterns
5. **Resolution patterns**: resolution steps from incidents, templates for common fixes, technician expertise, recommended approaches

Each one builds the base graph and then extends it:

```bash
python -m src.alternative_graph_models.temporal_graph
```

```python
from src.graph_construction import GraphConstructor
from src.alternative_graph_models.temporal_graph import TemporalGraphConstructor

# Create base constructor
base_constructor = GraphConstructor()

# Create temporal constructor that extends the base
temporal_constructor = TemporalGraphConstructor(base_constructor)

# Build the enhanced graph
temporal_constructor.build_graph()
```

See [src/alternative_graph_models/README.md](src/alternative_graph_models/README.md) for details and for combining them. With the sample data, the spatial model creates no proximity edges (the mock zone coordinates are more than 30 km apart), and the resolution-patterns model creates no recommended-approach or failure-prediction nodes (its thresholds need more incidents per template and per asset).

## Environment variables

| Variable | Default |
|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` |
| `NEO4J_USER` | `neo4j` |
| `NEO4J_PASSWORD` | `changeThisPassword` (a placeholder: set your own) |
| `REDIS_HOST` | `localhost` |
| `REDIS_PORT` | `6379` |
| `REDIS_DB` | `0` |
| `HOST` | `127.0.0.1` (the address the Streamlit UI listens on) |

## Tested on

| | |
|---|---|
| Date | 2026-10-23 |
| OS | macOS 26.5.1 (arm64); GitHub Actions `ubuntu-latest` |
| Python | 3.12.15 (macOS and CI) and 3.13 (CI) |
| Services | Neo4j 2026.10.1 and Redis 8.10.2 (Docker images `neo4j:2026.10`, `redis:8`) |
| Key packages | neo4j 6.4.1, redis 8.1.0, sentence-transformers 6.2.0, transformers 5.20.2, torch 2.14.1, streamlit 1.66.1, numpy 2.5.4, pandas 3.1.0 |
| Install time | `pip install -r requirements.txt`: 76 s |
| Run time | Embeddings 100 s on the first run (includes the model downloads); graph 11 s; retrieval 24 s and photos 19 s (mostly loading the models) |

Every command in this README was run from a fresh clone of this branch on Python 3.12. The retrieval scores are the same as with the first-edition code (INC903 0.7607, INC998 0.7372, INC933 0.6121).

## Differences from the printed book

| What | Printed book | Now | Why |
|---|---|---|---|
| Python | 3.8+ | 3.12+ | Current dependencies |
| `pip install -r requirements.txt` | Failed on Python 3.12 and later (torch 2.0.1 has no wheels for them) | Works; pinned from `uv.lock`, PyTorch CPU build on Linux | Install on current Python |
| Neo4j library | py2neo | The official `neo4j` driver, through a small `src/graph_db.py` | py2neo is end of life (its maintainers recommend the official driver) |
| Neo4j server | 4.x (its constraint syntax; 4.4 reached end of life in November 2025) | 2026.x | Current release; vector indexes and the `SEARCH` clause |
| Graph constraints | `CREATE CONSTRAINT ON ... ASSERT` | `CREATE CONSTRAINT IF NOT EXISTS FOR ... REQUIRE` | The old syntax was removed in Neo4j 5; on 4.4 a second `--mode graph` failed |
| Image embeddings | Every image failed on current Transformers and the step still finished (0 image embeddings) | All 20 images; the step fails if any image fails | Transformers 5 returns an output object from `get_image_features` |
| Vector search | NumPy and scikit-learn over the `.npy` files, filters in pandas | Embeddings stored on the nodes; Neo4j vector index and `SEARCH`, filters in the same query | Retrieval and graph in one place, as current Neo4j supports; the scores are unchanged |
| Images in retrieval | Computed but not used | Photo search from text or a photo (`--mode photos`, UI tab), and matching photos under each search | Make the retrieval multimodal, as the chapter describes |
| How similar incidents were resolved | Not in the book | Under each search (CLI and UI) | Show the graph (RESOLVED_BY) shaping the answer |
| Resolution-patterns model | Created nothing (read a property that doesn't exist) | 51 steps, 4 templates, 48 expertise links | Bug |
| Cache expiry | An entry whose results had expired still counted as a hit, with fewer or no results | It counts as a miss | Bug |
| Clear Cache (UI) | Erased the whole Redis database (`FLUSHDB`) | Deletes this system's keys only | It could erase other data in the same Redis |
| `redis` calls | `setex` | `set(..., ex=...)` | `setex` is deprecated in redis-py 8 |
| Streamlit UI | `streamlit run` from the shell, listening on every network interface | `python -m streamlit`, on 127.0.0.1 (`HOST` to change) | Works without the venv on PATH; local by default |
| `--mode` choices | embeddings, graph, retrieval, cache, full, app, all | Same, plus `photos` | New photo search |
| `data/logs.jsonl` | Python dict reprs (not JSON) | JSON Lines, same records | Valid JSON |
| `data/multimodal_image_features.json` | Absolute paths from the author's computer | Paths relative to the repository | Portable, no personal paths |
| README file names | `assets.csv`, `technicians.csv` | `assets (1).csv`, `technicians (1).csv` | The names the files and the code actually have |

Details are in [CHANGELOG.md](CHANGELOG.md).

## Data and licenses

| Files | Source | License |
|---|---|---|
| `data/drone-images/` (20 photos) | Created by the author | MIT |
| `data/*.csv`, `data/logs.jsonl`, `data/multimodal_image_features.json` | Synthetic, generated by the author; all incidents, assets, zones, supervisors and technicians are fictional | MIT |
| `screenshots/` | The author's runs of the first edition (April 2025) | MIT |
| Models (downloaded at run time) | [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2) (Apache-2.0), [openai/clip-vit-base-patch32](https://huggingface.co/openai/clip-vit-base-patch32) (no license tag on Hugging Face; OpenAI's [CLIP repository](https://github.com/openai/CLIP) is MIT) | As listed |

[data/README.md](data/README.md) lists every file and what uses it.

## Expected output

From a fresh clone on 2026-10-23, macOS 26.5.1 (arm64), Python 3.12.15, Neo4j 2026.10.1, Redis 8.10.2. Log lines and progress bars are left out.

`python main.py --mode graph` (log, last lines):

```
Created 1 'RELATED_TO' edges between incidents
Stored 100 Incident embeddings (384 numbers) in index incident_text_embedding
Stored 20 Image embeddings (512 numbers) in index image_clip_embedding
```

`python main.py --mode retrieval`:

```
Query: Packet loss observed on Tower
Retrieved 3 results:

Result 1:
Incident ID: INC903
Description: Packet loss observed on Tower T93. Issue reported by monitoring system.
Similarity Score: 0.7607
Zone: Zone 11
Status: Resolved
Image: INC903_repeater_missing_panel_zone11.jpeg
Caption: Repeater with missing panel, partially obscured in vegetation of Zone 11.

Zone Details:
  Region: Northwest
  Supervisor: Alice J.

Result 2:
Incident ID: INC998
Description: Packet loss observed on Tower T35. Issue reported by monitoring system.
Similarity Score: 0.7372
Zone: Zone 11
Status: Open

Zone Details:
  Region: Northwest
  Supervisor: Alice J.

Result 3:
Incident ID: INC933
Description: Packet loss observed on Repeater R41. Issue reported by monitoring system.
Similarity Score: 0.6121
Zone: Zone 11
Status: Resolved

Zone Details:
  Region: Northwest
  Supervisor: Alice J.

How similar resolved incidents were fixed:
  2 x Cleared the error logs and restored functionality. (INC927, INC932; technicians: Tech_199, Tech_102)
  2 x Restarted the device and restored functionality. (INC933, INC941; technicians: Tech_121, Tech_137)
  2 x Rolled back firmware and restored functionality. (INC962, INC900; technicians: Tech_141, Tech_151)
  2 x Realigned antenna and restored functionality. (INC950, INC955; technicians: Tech_132, Tech_188)
  1 x Updated routing table and restored functionality. (INC903; technicians: Tech_192)
  1 x Replaced faulty module and restored functionality. (INC946; technicians: Tech_159)

Drone images matching 'tower overgrown by trees in a forest':
  0.3383 INC917_tower_overgrown_branches_zone14.jpeg (INC917, Open)
  0.3216 INC912_tower_forest_canopy_obstructed.jpeg (INC912, Resolved)
  0.3089 INC916_tower_forest_zone12_moisture.jpeg (INC916, Resolved)
```

The sample incidents' resolutions are spread evenly across the six fixes, so no single fix dominates here; with real incident history the grouping shows which fix usually works. CLIP text-to-image scores sit around 0.25 to 0.35 even for good matches; compare them with each other, not with the text scores.

`python main.py --mode photos`:

```
Photos matching 'solar panels covered in desert dust':
  0.3141 INC911_repeater_dusty_solar_array.jpeg (INC911, Open)
  0.2939 INC908_bts_environmental_fatigue_desert.jpeg (INC908, Open)
  0.2736 INC901_bts_environmental_fatigue_desert.jpeg (INC901, Open)

Photos matching 'flooded tower base with standing water':
  0.2843 INC909_tower_muddy_base_flooded.jpeg (INC909, Resolved)
  0.2822 INC913_tower_structural_tilt_hilltop.jpeg (INC913, Open)
  0.2631 INC919_tower_alignment_issue_high_winds.jpeg (INC919, Resolved)

Photos that look like INC909_tower_muddy_base_flooded.jpeg:
  0.8559 INC905_bts_desert_solar_damage.jpeg (INC905, Open)
  0.8270 INC911_repeater_dusty_solar_array.jpeg (INC911, Open)
  0.8263 INC906_bts_standing_water_foundation.jpeg (INC906, Open)
```

`python main.py --mode cache`:

```
Cache hit!
Retrieved at: 1792806502.459543
Result count: 1
Sample result: INC903
```

`python main.py --mode full` (times vary):

```
Query: Tower packet loss
Cache hit: False
Retrieval time: 1989.76 ms
Results: 3
Query: Tower packet loss
Cache hit: True
Cache age: 0.01 seconds
Retrieval time: 6.65 ms
Results: 3

Sample result:
Incident ID: INC903
Description: Packet loss observed on Tower T93. Issue reported by monitoring system.
Similarity Score: 0.6941
Image: INC903_repeater_missing_panel_zone11.jpeg
```

Run it again within 12 hours and both queries are cache hits.

## Troubleshooting

- **`Failed to connect to Neo4j` or `Connection refused` on port 6379**: start Neo4j and Redis first (see the Quick start), and check the connection settings.
- **A Cypher syntax error at `SEARCH`**: the Neo4j server is too old for the vector `SEARCH` clause. Use 2026.x.
- **`... not found: run python main.py --mode embeddings first`**: the graph step stores the embeddings on the nodes, so run the embeddings step before it.
- **Neo4j authentication failure**: set `NEO4J_PASSWORD` (and `NEO4J_USER`) to your database's credentials.
- **Hugging Face rate-limit warning** ("unauthenticated requests"): harmless; set `HF_TOKEN` if downloads are slow.

## Project structure

```
.
├── data/                       # Sample data (see data/README.md)
│   ├── incidents.csv
│   ├── assets (1).csv
│   ├── technicians (1).csv
│   ├── zones.csv
│   ├── images.csv
│   ├── logs.jsonl
│   ├── multimodal_image_features.json
│   └── drone-images/           # 20 drone inspection photos
├── embeddings/                 # Generated embeddings (not in git)
├── screenshots/                # UI and Neo4j screenshots from the first edition
├── src/
│   ├── config.py               # Settings (environment variables), TTLs, index names
│   ├── graph_db.py             # Small layer over the official Neo4j driver
│   ├── embedding_pipeline.py   # Text and image embeddings
│   ├── graph_construction.py   # Neo4j graph, embeddings on nodes, vector indexes
│   ├── hybrid_retrieval.py     # Vector search + graph context, photo search, similar resolutions
│   ├── edge_cache.py           # Redis caching with per-modality TTLs
│   ├── retrieval_system.py     # Retrieval with caching
│   ├── streamlit_app.py        # Web interface
│   └── alternative_graph_models/
├── tests/test_smoke.py
├── main.py                     # Entry point (--mode ...)
├── pyproject.toml, uv.lock     # Dependencies and lock file
├── requirements.txt            # Pinned, exported from uv.lock
├── .env.example
├── Makefile
├── CHANGELOG.md
└── LICENSE                     # MIT
```

## Acknowledgments

- This project uses Hugging Face models for embeddings
- Graph functionality provided by Neo4j
- Caching functionality provided by Redis
- UI powered by Streamlit

## License

This project is licensed under the MIT License; see the [LICENSE](LICENSE) file for details.
