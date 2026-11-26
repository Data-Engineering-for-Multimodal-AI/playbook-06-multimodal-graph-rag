# Changelog

## v1.1.0 (2026-11-26)

Nothing the book shows has changed.

### Added
- `make search Q=... [ZONE=...] [PRIORITY=...]` and `make photos Q=...` or `IMAGE=...`: search the
  graph by hand through the cache (`scripts/search.py`).
- `make check-data DIR=...` and `make load DIR=...`: check a folder of your own incidents and photos
  in the layout of `data/`, then build the embeddings and the graph from it (`scripts/own_data.py`,
  `tests/test_own_data.py`). `DATA_DIR` (default `data`) sets the folder the pipeline reads; a folder
  of your own may name its files `assets.csv` and `technicians.csv`.
- Three measured experiments: `make try-filter-candidates`, `make try-cache-keys`,
  `make try-related-window` (`experiments/`). None needs Docker.
- `NEO4J_HTTP_PORT`, `NEO4J_BOLT_PORT` and `REDIS_PORT` set the host ports in `docker-compose.yml`
  (same defaults), for machines that already run Neo4j or Redis.
- README: numbered Run it steps, time tiers, Try this, Use your own data, What you end up with,
  Before production, What it costs.
- CI: the Run it searches, Try this 1-3, the own-data checks, and the time to first output in a
  clean devcontainer.
- `make setup`, `make services`, `make services-stop`, `make run` and `make serve`. `make run`
  makes sure Neo4j and Redis are running, then runs the modes `embeddings`, `graph`, `retrieval`,
  `photos`, `cache` and `full` in order. `make serve` starts the Streamlit UI. `make smoke` and
  `make clean` are unchanged.
- `docker-compose.yml` with the same Neo4j and Redis as the README's `docker run` commands.
  `make services` uses it only when neither service is running.
- `.devcontainer/` so the repo opens in GitHub Codespaces, with Docker-in-Docker for the services.
- CI: a weekly scheduled run, a `make run` step, and a job that builds the devcontainer and runs
  `make run` inside it.
- `DATA_SOURCES.md`: the datasets and models this playbook uses, with their licenses and citations.
- `make run` writes `.playbook-done` when it passes (ignored by git). `make card` in the
  organization's `.github` repository reads these files and draws a completion card.

### Fixed
- `make smoke` reported success without saying that the graph and cache tests were skipped when
  Neo4j or Redis was not reachable. It now prints one line saying how many were skipped and why.

### Changed
- README: "What you'll build" is now "How it works", and "Quick start" is now "Run it the way the
  book does", with the same commands.
- `src/graph_construction.py`: the 72-hour `RELATED_TO` window is the constant `RELATED_WINDOW_HOURS`
  (same value).
- README opening: a title that says what you'll do, three sentences on why, the example and what you'll do, then the data engineering problem and what you'll work with.
- Book page numbers now match the printed book (they were Early Release page numbers).
- README: a header image (light and dark), badges for CI, Python, license and Codespaces, a diagram at
  the top of "How it works", and a footer that links the book, all playbooks, and the previous and
  next playbook.
- `src/graph_db.py` passes the Neo4j notification setting as the driver's enum.

## 2026.10.1 (2026-10-27)

Checked against the book (Early Release, pages 204–218).

### Changed
- `.streamlit/config.toml`: the book's `python -m streamlit run src/streamlit_app.py` (page 214)
  listens on 127.0.0.1, like `python main.py --mode app`.
- README: page numbers; the differences table's left column is the first edition.

## 2026.10 (2026-10-23): 2026 maintenance update

The printed version is tagged `first-edition`.

### Fixed
- **`pip install -r requirements.txt` failed on Python 3.12 and later**: torch 2.0.1 has no wheels for them. The requirements are now pinned from `uv.lock` for Python 3.12+.
- **Image embeddings**: on current Transformers every drone image failed (`get_image_features` returns an output object) and the step still finished, with 0 image embeddings. All 20 are embedded now, and the step fails if any image fails.
- **Graph build on current Neo4j**: `CREATE CONSTRAINT ON ... ASSERT` was removed in Neo4j 5. The constraints use `CREATE CONSTRAINT IF NOT EXISTS FOR ... REQUIRE`, which also fixes a second `--mode graph` failing on Neo4j 4.4.
- **Resolution-patterns model created nothing**: it read `resolution` instead of `resolution_summary`. It now creates 51 steps, 4 templates and 48 technician expertise links from the sample data.
- **Cache**: an entry whose results had expired (text after 1 h, images after 6 h) still counted as a hit, with fewer or no results; it counts as a miss now. The count and timestamp keys expire with the longest-lived result instead of always after 12 h.
- **Clear Cache** erased the whole Redis database (`FLUSHDB`); it now deletes this system's keys only.
- `setex` (deprecated in redis-py 8) replaced by `set(..., ex=...)`.

### Added
- **Vector search in Neo4j**: the text and image embeddings are stored on the Incident and Image nodes with two vector indexes, and `semantic_search` runs the Cypher `SEARCH` clause with the zone, priority and time filters in the same query. The scores are the same as before.
- **Photo search**: find drone photos from a description or from another photo (CLIP), with the incident each belongs to: `python main.py --mode photos`, a "Search by photo" tab in the UI, and matching photos under each incident search.
- **How similar incidents were resolved**: the 10 nearest resolved incidents grouped by fix, with their technicians (through RESOLVED_BY), in the retrieval output and the UI.
- Photo and resolution results are cached too (image TTL and text TTL); cache keys carry a kind prefix (`query:`, `photos:`, `resolutions:`).
- `data/README.md`: source (created by the author) and license (MIT) of every data file, and what uses it.
- `.env.example`, `pyproject.toml`, `uv.lock`, `tests/test_smoke.py`, `make smoke`, and GitHub Actions on Python 3.12 and 3.13 with Neo4j 2026.10 and Redis 8, including the printed `pip install -r requirements.txt` path.

### Changed
- **py2neo → the official `neo4j` driver** (py2neo is end of life). `src/graph_db.py` keeps the `run().data()`, `evaluate()` and `create(Node(...))` calls the code uses. Needs Neo4j 2026.x.
- The Streamlit UI starts with `python -m streamlit` (no need for the venv on PATH) and listens on 127.0.0.1 unless `HOST` is set.
- `data/logs.jsonl` is valid JSON Lines (it held Python dict reprs); `data/multimodal_image_features.json` has paths relative to the repository instead of absolute paths from the author's computer. Same records.
- README: Python 3.12+, clone step, Neo4j and Redis setup (installed or Docker), the actual data file names, expected output from a run, troubleshooting.

### Removed
- py2neo and scikit-learn (no longer used) from the dependencies.
