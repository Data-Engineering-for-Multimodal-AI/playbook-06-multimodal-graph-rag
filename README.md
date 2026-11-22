# Playbook 06: Retrieve past incidents with vectors, a graph and a cache
**How to build graph-augmented retrieval with edge-aware caching.** Chapter 6 of [*Data Engineering for Multimodal AI*](https://oreil.ly/data-engineering-multimodal) (O'Reilly, 2026), pages 201–216.

An agent triaging a network incident needs similar past incidents, the context around them, and a fast answer the next time it asks. In this repo, we explore this with TelMo, a fictional telecom company, and a synthetic incident dataset. Follow along to combine vector search, metadata filters and a graph, then add a cache that serves repeat questions quickly.

**The problem.** A good answer needs similar past cases, the right filters, how those cases relate to each other, and speed, and no single database gives you all four.

**What you'll work with.** You'll combine vector search with metadata filters, enrich the results with relationships from a graph, and cache answers close to where they are used.

> Following the book? Its Steps 1–7 are in [Run it the way the book does](#run-it-the-way-the-book-does) and still work as printed. Want the code exactly as printed? Use the `first-edition` tag. This branch is the 2026 maintenance update; see [Differences from the printed book](#differences-from-the-printed-book).

## Run it

You need [uv](https://docs.astral.sh/uv/), `make` and Docker (for Neo4j and Redis). Or open the repo in a GitHub Codespace, where all of them are ready. On Windows without `make`, use a Codespace or the book's steps below. The times below are from a Mac (Python 3.13) with the two models already downloaded; the first run downloads them from Hugging Face (about 700 MB).

**1. Get the code.**

```bash
git clone https://github.com/Data-Engineering-for-Multimodal-AI/playbook-06-multimodal-graph-rag.git
cd playbook-06-multimodal-graph-rag
```

**2. Start Neo4j and Redis.** Installs the locked dependencies (`uv sync`) and starts Neo4j 2026.10 and Redis 8 with `docker compose up -d --wait`, the same containers as the book's `docker run` commands. If both already answer with the settings in [`.env.example`](.env.example), nothing is started. This took 37 s on a Mac with the images already pulled.

```bash
make services
```

You should see both containers become healthy:

```
 Container 06-multimodal-graph-rag-redis-1  Healthy
 Container 06-multimodal-graph-rag-neo4j-1  Healthy
```

If Neo4j or Redis already runs on your machine (`make services` then stops with an `AuthError` or says a port is taken), use other ports in this terminal and the next ones: `export NEO4J_HTTP_PORT=7475 NEO4J_BOLT_PORT=7688 REDIS_PORT=6380 NEO4J_URI=bolt://localhost:7688`.

**3. Build the graph and run the pipeline.** Runs the book's modes in order: `python main.py --mode embeddings`, `graph`, `retrieval`, `photos`, `cache` and `full`. It embeds the 100 incidents and 20 drone photos, builds the Neo4j graph with the embeddings on the nodes, and runs a filtered search, a photo search and the cache. This took 1 min 55 s on a Mac. Like `--mode graph`, it replaces everything in the Neo4j database it connects to.

```bash
make run
```

You should see the three Zone 11 results for "Packet loss observed on Tower", then the cache at the end:

```
Result 1:
Incident ID: INC903
Description: Packet loss observed on Tower T93. Issue reported by monitoring system.
Similarity Score: 0.7607
...
Query: Tower packet loss
Cache hit: True
Retrieval time: 6.02 ms
```

The first `Tower packet loss` query of a fresh Redis is a miss (2233.88 ms on a Mac); the second is answered from Redis in about 6 ms. Within 12 hours both are hits.

**4. Search it yourself.** Describe an incident, optionally with a zone and a priority. The search goes through the cache, like `--mode full`.

```bash
make search Q="router keeps rebooting after a firmware update" PRIORITY=High
```

```
Incidents like 'router keeps rebooting after a firmware update' (priority High):
  0.6947  INC957  Zone 11  High   Open     Firmware update failure observed on Router R57. ...
  0.5606  INC990  Zone 12  High   Open     Firmware update failure observed on Repeater R63. ...
  0.5202  INC947  Zone 12  High   Resolved Firmware update failure observed on Tower T95. ...
          fixed by Tech_120
  ...
Cache miss, 3044 ms
```

Run the same command again and the last line is `Cache hit, 17 ms`. Each result shows the graph context: the technician from `RESOLVED_BY`, the photo from `HAS_IMAGE` and related incidents from `RELATED_TO`. Find drone photos from a description or from another photo:

```bash
make photos Q="water pooling around the tower base"
make photos IMAGE=data/drone-images/INC917_tower_overgrown_branches_zone14.jpeg
```

```
Drone photos matching data/drone-images/INC917_tower_overgrown_branches_zone14.jpeg:
  1.0000  INC917_tower_overgrown_branches_zone14.jpeg  (INC917, Open)
  0.8963  INC900_tower_forest_inspection.jpeg  (INC900, Resolved)
  0.8837  INC912_tower_forest_canopy_obstructed.jpeg  (INC912, Resolved)
  ...
```

The photo finds itself first, then the other forest towers. Add `ZONE="Zone 12"` to a search, or try your own descriptions.

**5. Open the UI.** Starts the Streamlit app (`python main.py --mode app`) on http://127.0.0.1:8501, with the incident search, the graph view and search by photo. Stop it with Ctrl+C.

```bash
make serve
```

```
  You can now view your Streamlit app in your browser.

  URL: http://127.0.0.1:8501
```

**6. Clean up.**

```bash
make services-stop
make clean
```

`make services-stop` stops and removes the two containers (`docker compose down`); after the next `make services`, run `make run` again before searching. `make clean` deletes the generated embeddings in `embeddings/` and the test cache. The models stay in the Hugging Face cache.

## How much time do you have?

| Time | What to do |
|---|---|
| 15 minutes | [Run it](#run-it), steps 1 to 4. On a Mac, step 2 took 37 s and step 3 took 1 min 55 s. |
| 1 hour | The three [Try this](#try-this) experiments (under 20 s each, no Docker), then your own searches and the UI. |
| 1 day | [Use your own data](#use-your-own-data): build the graph from your own incidents and photos, then work through [Before production](#before-production). |

## Try this

Each experiment changes one thing and measures the effect. None needs Docker. The numbers below are from a Mac on 2026-11-21; yours will differ.

**1. How many vector candidates does a filtered search need?** `semantic_search()` asks the vector index for the nearest incidents first and applies the zone and priority filters after. This repeats those steps in NumPy for six filtered searches and compares each answer with filtering first.

```bash
make try-filter-candidates
```

```
candidates  results returned  same as filtering first
         5          2 of 30                       7%
        10          5 of 30                      17%
        20         19 of 30                      63%
        50         27 of 30                      90%
       100         30 of 30                     100%

Scoring every vector instead (the exact answer) at larger sizes, in NumPy:
        100 incidents:     0.01 ms per query
     10,000 incidents:     1.36 ms per query
  1,000,000 incidents:   483.66 ms per query
```

The code asks for 100 candidates, which is every incident in the sample, so its answers are exact. With 10 candidates, the same filtered searches return 5 results out of 30. On a real incident history, the candidate count has to grow with how selective the filters are. Change `QUERIES` in `experiments/filter_candidates.py` to try other filters.

**2. How often does the cache hit when people phrase a question differently?** The cache key is an MD5 of the exact query text and filters. This replays 36 questions (6 questions, each asked 6 ways: repeated, in lower case, with extra spaces or punctuation, and reworded) through the code's key and three alternatives.

```bash
make try-cache-keys
```

```
key rule            hits  hit rate  wrong hits
exact (the code)       6       17%           0
normalized            19       53%           3
semantic >= 0.95      21       58%           3
semantic >= 0.90      24       67%           5
semantic >= 0.80      27       75%           7
semantic >= 0.70      30       83%          10
```

Only exact repeats hit the code's cache. Lowercasing and removing punctuation and extra spaces triples the hit rate. A "wrong hit" returns top 5 incidents that a fresh search for that exact wording would not: matching questions by embedding gets more hits and more wrong answers as the threshold drops. Change `normalize()` or the thresholds and run it again.

**3. How wide should the RELATED_TO window be?** Two incidents on the same asset get a `RELATED_TO` edge when they are at most 72 hours apart (`RELATED_WINDOW_HOURS` in `src/graph_construction.py`). This runs the code's `create_related_incident_edges()` with other windows and counts the edges instead of writing them.

```bash
make try-related-window
```

```
100 incidents on 79 asset IDs; 17 IDs have more than one incident

  window  RELATED_TO edges  incidents with a related one  median gap  edges across two assets
    24 h                 1                             2    0.4 days                        1
    72 h                 1                             2    0.4 days                        1
     7 d                 2                             4    3.0 days                        2
    30 d                18                            29   16.9 days                       16
    90 d                25                            38   23.3 days                       21
```

With the 72-hour window, 2 of the 100 incidents have a related incident, so the graph adds little context here. A wider window links more of them, but most edges join two different assets: the code groups incidents by `asset_id` alone, and the sample reuses IDs (R96 is a Router in Zone 11, a Router in Zone 14 and a Repeater in Zone 14). Group by `asset_id`, `asset_type` and `zone` together and run it again.

## Use your own data

Put your incidents in a folder with the same files as `data/`:

```
my_incidents/
  incidents.csv     incident_id, description, zone, asset_type, asset_id, timestamp,
                    priority, status, resolution_summary   (timestamp as 2026-03-02T07:15:00)
  assets.csv        asset_id, asset_name, asset_type, zone_id
  zones.csv         zone_id, region, supervisor
  technicians.csv   incident_id, technician_id              (who resolved what)
  images.csv        incident_id, image_filename, caption    (one photo per incident)
  drone-images/     the photos images.csv names: .jpg .jpeg .png
```

The files are UTF-8 CSV with a header row. `assets (1).csv` and `technicians (1).csv`, the sample names, work too. Check the folder first. This reads every file and writes nothing:

```bash
make check-data DIR=my_incidents
```

```
my_incidents: 10 incidents, 6 assets, 2 zones, 7 technician links, 3 photos. All checks passed.
```

It reports every problem with the file and the reason, and stops before anything is written. These are from a copy of that folder with mistakes put in on purpose:

```
8 problem(s) in broken; nothing was written:
  technicians.csv: not UTF-8 text (byte 39)
  incidents.csv line 10: duplicate incident_id N107
  incidents.csv line 4: timestamp '05/03/2026 15:10' is not YYYY-MM-DDTHH:MM:SS
  incidents.csv line 7: zone 'Valley' is not in zones.csv
  incidents.csv line 7: asset P4 (Repeater, Valley) is not in assets.csv
  images.csv line 5: second photo for N106 (one photo per incident)
  drone-images/n109_vegetation.jpeg: Git LFS pointer, not the photo (run git lfs pull)
  drone-images/n106_second.png: listed in images.csv line 5 but not found
```

It also checks for missing files and columns, empty IDs and descriptions, technicians and photos for incidents that don't exist, and photos that won't open or are smaller than 32x32. An unknown zone or asset would not stop the graph step: the incident would be stored without its `OCCURRED_IN` or `AFFECTS` edge. When everything passes, build the graph from it (Neo4j and Redis running) and search it:

```bash
make load DIR=my_incidents
make search Q="storm knocked out power at the tower"
```

```
Loaded 10 incidents and 3 photos. Search them with make search Q="..." (use make run to go back to the samples).
...
Incidents like 'storm knocked out power at the tower':
  0.7826  N101  Harbor   High   Resolved Tower T7 lost power during the storm.
          fixed by Tech_A
```

`make load` runs `python main.py --mode embeddings` and `--mode graph` with `DATA_DIR` set to your folder (22 s for this folder on a Mac), then deletes this playbook's cached answers in Redis, which describe the old graph. Like `--mode graph`, it replaces everything in the Neo4j database. `make run` puts the samples back.

## What you end up with

A Neo4j graph of your incidents, assets, zones, technicians and photos, with vector indexes on the text and photo embeddings, a Redis cache in front of it, and a search you can run from the command line or the UI.

Skills you'll practice:
- Embedding text and photos with two models and storing the vectors on graph nodes
- Combining vector search with structured filters in one query, and seeing what post-filtering loses
- Adding graph context (who fixed it, what else broke nearby) to search results
- Designing cache keys and TTLs, and measuring the hit rate they give
- Checking incident data for the mistakes that silently drop graph edges

## Before production

This playbook runs on one machine with 100 sample incidents. Before you run something like it for real:

1. **Size the vector search for the filters.** `semantic_search()` asks the index for `max(top_k, 100)` candidates and filters afterwards, which is exact only because the sample has 100 incidents. With 10 candidates, six filtered searches returned 5 of 30 results ([Try this 1](#try-this)). Raise the candidate count with the filter's selectivity, or filter inside the index. *Chapter 6, "Hybrid Storage and Retrieval" (page 189); Chapter 6, "Vector Databases" (page 180).*
2. **Put everything that changes the answer in the cache key.** The key covers the query and filters but not `top_k`: after `--mode full` cached 3 results, `make search Q="Tower packet loss" ZONE="Zone 11"` asked for 5 and got the 3 from the cache. *Chapter 6, "Caching Design Decisions" (page 199).*
3. **Invalidate the cache when the graph changes.** `--mode graph` rebuilds the graph but leaves the cache: after a rebuild, `--mode full` returned answers cached 491 s earlier, from the old graph. `make load` deletes the cached answers; a production rebuild should too, or version the keys. *Chapter 6, "Dynamic Caching" (page 196).*
4. **Normalize queries before they become keys.** Only exact repeats hit the cache: 17% of 36 rephrased questions, against 53% after lowercasing and removing punctuation ([Try this 2](#try-this)). *Chapter 6, "Caching Strategies and Inference on the Edge" (page 193).*
5. **Link incidents on the physical asset.** `RELATED_TO` groups incidents by `asset_id` alone, while Asset nodes are keyed on ID, type and zone. With a 30-day window, 16 of 18 edges joined two different assets ([Try this 3](#try-this)). *Chapter 6, "Graph Databases and Knowledge Graphs" (page 184).*
6. **Validate data where it enters.** The graph step creates an incident even when its zone or asset doesn't exist, and silently skips the edge. `make check-data` catches this for a folder; a production loader should reject or quarantine such rows. *Chapter 4, "Validation, Transformation, Observability, and Annotation Across Modalities" (page 119).*
7. **Update the graph instead of replacing it.** `--mode graph` deletes every node (`MATCH (n) DETACH DELETE n`) and writes one row per Cypher call; it took 22 s for 100 incidents on a Mac. Load new incidents with `MERGE` in batches (`UNWIND`), so the graph stays available. *Chapter 8, "Continuous Data Integration for Multimodal Systems" (page 282).*
8. **Record which model made each vector.** The vector indexes store only the dimensions (384 and 512). Store the model name and version with the embeddings, so a model change means a planned re-embed. *Chapter 8, "Data Versioning and Experiment Tracking for Multimodal AI" (page 276).*
9. **Lock down the services.** Neo4j uses the placeholder password `changeThisPassword`, Redis has no password, and both publish their ports on every interface in `docker-compose.yml`. *Chapter 11, "Protecting Data Across the Pipeline" (page 421).*
10. **Watch the cache and the search.** Track hit rate, retrieval time and cache age, which `--mode full` prints once but nothing records. *Chapter 2, "Monitoring and Observability" (page 53).*

## What it costs

| Where you run it | Cost |
|---|---|
| Your machine | $0. Everything runs locally: no API keys, no paid services. About 3.5 GB of disk on a Mac: 1.2 GB for the environment, 1.2 GB for the two models in the Hugging Face cache, and 1.3 GB for the Neo4j and Redis images. |
| A GitHub Codespace (4 cores, 16 GB, the size this repo asks for) | Estimated $0.36 per hour at GitHub's list price (November 2026). A free personal account includes 120 core-hours a month, about 30 hours on this machine. In CI, `make run` in a clean devcontainer (starting Neo4j and Redis included) took 87 s; the whole job, with the container build, took 3 to 5 minutes. |

## How it works

The sample data is 100 incident reports, 20 drone inspection photos, and the assets, zones and technicians they involve.

- **Multimodal embeddings**: sentence embeddings (all-MiniLM-L6-v2) for incident descriptions and CLIP embeddings for drone photos
- **Knowledge graph in Neo4j**: incidents, assets, zones, technicians and images, with the embeddings stored on the nodes and indexed for vector search
- **Hybrid retrieval**: vector search with structured filters (zone, priority, time) in one Cypher query, then graph context for each result (zone, asset, technician, photo, related incidents)
- **Photo search**: find drone photos from a description ("solar panels covered in desert dust") or from another photo
- **How similar incidents were resolved**: the nearest resolved incidents, grouped by fix, with the technicians who applied it
- **Edge-aware caching in Redis**: per-modality TTLs (text 1 h, images 6 h, graph context 12 h) and fingerprinted cache keys
- **Streamlit UI**: incident search with images and graph views, and search by photo
- **Alternative graph models**: five ways to extend the base graph (temporal, hierarchical, image features, spatial, resolution patterns)

Everything runs on a laptop CPU with the bundled sample data. Neo4j and Redis run locally (installed, or in Docker). The first run downloads the two models from Hugging Face (about 700 MB).

## Run it the way the book does

These are the book's Steps 1–7 (pages 204–211), with the fixes listed in [Differences from the printed book](#differences-from-the-printed-book).

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

- `make services`, `make run`, `make search`, `make photos` and `make serve`: see [Run it](#run-it). `make check-data` and `make load`: see [Use your own data](#use-your-own-data). `make try-*`: see [Try this](#try-this).

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
| `DATA_DIR` | `data` (the folder the embeddings and graph steps read; `make load DIR=...` sets it) |
| `NEO4J_HTTP_PORT`, `NEO4J_BOLT_PORT` | `7474`, `7687` (host ports `docker-compose.yml` publishes; Redis uses `REDIS_PORT`) |

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

The "First edition" column is the code at the `first-edition` tag, which the book describes.

| What | First edition | Now | Why |
|---|---|---|---|
| Python | 3.8+ | 3.12+ | Current dependencies |
| `pip install -r requirements.txt` | Failed on Python 3.12 and later (torch 2.0.1 has no wheels for them) | Works; pinned from `uv.lock`, PyTorch CPU build on Linux | Install on current Python |
| Neo4j library | py2neo | The official `neo4j` driver, through a small `src/graph_db.py` | py2neo is end of life (its maintainers recommend the official driver) |
| Neo4j server | 4.x (its constraint syntax; 4.4 reached end of life in November 2025); the book names no version | 2026.x | Current release; vector indexes and the `SEARCH` clause |
| Graph constraints | `CREATE CONSTRAINT ON ... ASSERT` | `CREATE CONSTRAINT IF NOT EXISTS FOR ... REQUIRE` | The old syntax was removed in Neo4j 5; on 4.4 a second `--mode graph` failed |
| Image embeddings | Every image failed on current Transformers and the step still finished (0 image embeddings) | All 20 images; the step fails if any image fails | Transformers 5 returns an output object from `get_image_features` |
| Vector search | NumPy and scikit-learn over the `.npy` files, filters in pandas | Embeddings stored on the nodes; Neo4j vector index and `SEARCH`, filters in the same query | Retrieval and graph in one place, as current Neo4j supports; the scores are unchanged |
| Images in retrieval | Computed but not used | Photo search from text or a photo (`--mode photos`, UI tab), and matching photos under each search | Make the retrieval multimodal, as the chapter describes |
| How similar incidents were resolved | Not in the book | Under each search (CLI and UI) | Show the graph (RESOLVED_BY) shaping the answer |
| Resolution-patterns model | Created nothing (read a property that doesn't exist) | 51 steps, 4 templates, 48 expertise links | Bug |
| Cache expiry | An entry whose results had expired still counted as a hit, with fewer or no results | It counts as a miss | Bug |
| Clear Cache (UI) | Erased the whole Redis database (`FLUSHDB`) | Deletes this system's keys only | It could erase other data in the same Redis |
| `redis` calls | `setex` | `set(..., ex=...)` | `setex` is deprecated in redis-py 8 |
| Streamlit UI | `streamlit run` from the shell, listening on every network interface | The book's `python -m streamlit run src/streamlit_app.py` (page 211) or `python main.py --mode app`, on 127.0.0.1 (`.streamlit/config.toml`; `HOST` with `--mode app`) | Works without the venv on PATH; local by default |
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

From a fresh clone on 2026-10-23, macOS 26.5.1 (arm64), Python 3.12.15, Neo4j 2026.10.1, Redis 8.10.2. Log lines and progress bars are left out. This is the output of this version; it may differ from the output printed in the book, and that's okay.

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

- **`Failed to connect to Neo4j` or `Connection refused` on port 6379**: start Neo4j and Redis first (`make services`, or see [Run it the way the book does](#run-it-the-way-the-book-does)), and check the connection settings.
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
├── scripts/
│   ├── check_services.py       # make services: are Neo4j and Redis answering?
│   ├── search.py               # make search, make photos: search by hand through the cache
│   └── own_data.py             # make check-data, make load: check your own folder and build the graph
├── experiments/                # make try-*: the three Try this experiments
├── tests/
│   ├── test_smoke.py           # make smoke
│   └── test_own_data.py        # checks for make check-data
├── main.py                     # Entry point (--mode ...)
├── pyproject.toml, uv.lock     # Dependencies and lock file
├── requirements.txt            # Pinned, exported from uv.lock
├── .env.example
├── docker-compose.yml          # Neo4j and Redis for make services
├── Makefile                    # make services, run, search, photos, serve, check-data, load, try-*, smoke, clean
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
