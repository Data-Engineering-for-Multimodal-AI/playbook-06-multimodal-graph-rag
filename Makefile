.PHONY: setup services services-stop run serve search photos check-data load try-filter-candidates try-cache-keys try-related-window smoke clean

# A bare `make` runs the smoke test, as it did before the uniform targets were added.
.DEFAULT_GOAL := smoke

# Uniform targets for The Playbooks. The book's commands (pip install -r requirements.txt,
# the docker run commands for Neo4j and Redis in the README, python main.py --mode ...,
# python -m streamlit run src/streamlit_app.py) still work as printed.

# Install the locked dependencies into .venv.
setup:
	uv sync --frozen

# In a fresh Codespace the Docker daemon can take a little while to start: wait up to 2 minutes.
WAIT_FOR_DOCKER := (for i in $$(seq 24); do if docker info >/dev/null 2>&1; then exit 0; fi; sleep 5; done; exit 1)

# Make sure Neo4j and Redis are running. If they already answer (started with the README's
# docker run commands, installed locally, or as CI service containers), nothing is started.
# If neither is running, they are started with docker-compose.yml, and this waits until both
# are healthy. Anything in between (one running, or a wrong password) stops with a message.
services: setup
	@uv run --frozen python scripts/check_services.py; status=$$?; \
	if [ $$status -eq 0 ]; then :; \
	elif [ $$status -ne 1 ]; then exit $$status; \
	elif command -v docker >/dev/null 2>&1 && $(WAIT_FOR_DOCKER); then \
		echo "Starting Neo4j and Redis with docker compose (docker-compose.yml)..."; \
		docker compose up -d --wait --wait-timeout 300; \
	else \
		echo "Neo4j and Redis are not running, and Docker is not available."; \
		if [ -f /tmp/dockerd.log ]; then echo "Last lines of /tmp/dockerd.log:"; tail -n 25 /tmp/dockerd.log; fi; \
		echo "Start them as the README's Quick start describes, then run this again."; \
		exit 1; \
	fi

# Stop the containers that `make services` started. Their data is kept until `docker compose down -v`.
services-stop:
	docker compose down

# The pipeline end to end: embeddings, the Neo4j graph, hybrid retrieval, photo search, the cache,
# and retrieval with caching. These are the README's modes in order, without the UI (see serve).
# Like `python main.py --mode graph`, this replaces everything in the Neo4j database it connects to.
run: services
	uv run --frozen python main.py --mode embeddings
	uv run --frozen python main.py --mode graph
	uv run --frozen python main.py --mode retrieval
	uv run --frozen python main.py --mode photos
	uv run --frozen python main.py --mode cache
	uv run --frozen python main.py --mode full

# The Streamlit UI on http://127.0.0.1:8501 (set HOST to listen elsewhere). Run `make run` first
# to build the graph.
serve: services
	uv run --frozen python main.py --mode app

# Search by hand, through the cache (needs the graph from make run). Run one twice: the second is a cache hit.
#   make search Q="tower packet loss" ZONE="Zone 11" PRIORITY=High
#   make photos Q="solar panels covered in desert dust"   or   make photos IMAGE=path/to/photo.jpg
search: services
	@test -n "$(Q)" || { echo 'Usage: make search Q="a description" [ZONE="Zone 11"] [PRIORITY=High]'; exit 2; }
	@uv run --frozen python scripts/search.py --query "$(Q)" $(if $(ZONE),--zone "$(ZONE)") $(if $(PRIORITY),--priority "$(PRIORITY)")

photos: services
	@if [ -n "$(IMAGE)" ]; then uv run --frozen python scripts/search.py --image "$(IMAGE)"; \
	elif [ -n "$(Q)" ]; then uv run --frozen python scripts/search.py --photos --query "$(Q)"; \
	else echo 'Usage: make photos Q="a description"  or  make photos IMAGE=path/to/photo.jpg'; exit 2; fi

# Your own incidents, in the layout of data/ (see README, "Use your own data").
# check-data checks every file and writes nothing; load builds the embeddings and the graph from DIR.
check-data: setup
	@test -n "$(DIR)" || { echo "Usage: make check-data DIR=path/to/folder"; exit 2; }
	@uv run --frozen python scripts/own_data.py --dir "$(DIR)" --check-only

load: services
	@test -n "$(DIR)" || { echo "Usage: make load DIR=path/to/folder"; exit 2; }
	@uv run --frozen python scripts/own_data.py --dir "$(DIR)"

# Try this: three measured experiments (see README, "Try this"). No Docker needed.
try-filter-candidates: setup
	@uv run --frozen python experiments/filter_candidates.py

try-cache-keys: setup
	@uv run --frozen python experiments/cache_keys.py

try-related-window: setup
	@uv run --frozen python experiments/related_window.py

# Smoke tests (CPU, a few minutes). The graph and cache tests need Neo4j 2026.x and Redis running.
smoke:
	uv run pytest -q

# Delete the generated embeddings and test caches. Neo4j, Redis and their data are left alone
# (stop them with make services-stop).
clean:
	rm -rf embeddings .pytest_cache
