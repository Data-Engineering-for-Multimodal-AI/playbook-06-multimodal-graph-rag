# Changelog

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
