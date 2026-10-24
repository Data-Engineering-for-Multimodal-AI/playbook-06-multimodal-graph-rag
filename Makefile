.PHONY: smoke clean

# Smoke tests (CPU, a few minutes). The graph and cache tests need Neo4j 2026.x and Redis running.
smoke:
	uv run pytest -q

clean:
	rm -rf embeddings .pytest_cache
