.PHONY: setup services services-stop run serve smoke clean

# Uniform targets for The Playbooks. The book's commands (pip install -r requirements.txt,
# the docker run commands for Neo4j and Redis in the README, python main.py --mode ...,
# python -m streamlit run src/streamlit_app.py) still work as printed.

# Install the locked dependencies into .venv.
setup:
	uv sync --frozen

# Make sure Neo4j and Redis are running. If they already answer (started with the README's
# docker run commands, installed locally, or as CI service containers), nothing is started.
# If neither is running, they are started with docker-compose.yml, and this waits until both
# are healthy. Anything in between (one running, or a wrong password) stops with a message.
services: setup
	@uv run --frozen python scripts/check_services.py; status=$$?; \
	if [ $$status -eq 0 ]; then :; \
	elif [ $$status -ne 1 ]; then exit $$status; \
	elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
		echo "Starting Neo4j and Redis with docker compose (docker-compose.yml)..."; \
		docker compose up -d --wait --wait-timeout 300; \
	else \
		echo "Neo4j and Redis are not running, and Docker is not available."; \
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

# Smoke tests (CPU, a few minutes). The graph and cache tests need Neo4j 2026.x and Redis running.
smoke:
	uv run pytest -q

clean:
	rm -rf embeddings .pytest_cache
