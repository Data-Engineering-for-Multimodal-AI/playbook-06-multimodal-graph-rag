"""Check that Neo4j and Redis answer with the configured settings. Used by `make services`.

The settings come from src/config.py (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, REDIS_HOST,
REDIS_PORT, REDIS_DB). Exit codes:
  0  both answer
  1  neither port is open, so they can be started (make services does that with Docker)
  2  something else: one is up and one is not, or a port is open but the connection fails
     (for example another Neo4j with a different password)
"""

import os
import socket
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config import (NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, REDIS_DB, REDIS_HOST,  # noqa: E402
                        REDIS_PORT)


def port_open(host, port):
    try:
        socket.create_connection((host, port), timeout=2).close()
        return True
    except OSError:
        return False


def check_neo4j():
    from neo4j import GraphDatabase
    with GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)) as driver:
        driver.verify_connectivity()


def check_redis():
    import redis
    redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, socket_timeout=5).ping()


neo4j_url = urlparse(NEO4J_URI)
services = [("Neo4j", neo4j_url.hostname or "localhost", neo4j_url.port or 7687, check_neo4j),
            ("Redis", REDIS_HOST, REDIS_PORT, check_redis)]

if not any(port_open(host, port) for _, host, port, _ in services):
    print("Neo4j and Redis are not running.")
    sys.exit(1)

problems = []
for name, host, port, check in services:
    if not port_open(host, port):
        problems.append(f"{name}: nothing listens on {host}:{port}")
        continue
    # A container that was just started may need a little while before it accepts connections
    for attempt in range(12):
        try:
            check()
            break
        except Exception as e:
            error = e
            if "auth" in type(e).__name__.lower() or attempt == 11:
                problems.append(f"{name} at {host}:{port}: {type(e).__name__}: {error}")
                break
            time.sleep(5)
if problems:
    print("Neo4j and Redis are not both usable with the settings in src/config.py:")
    for problem in problems:
        print("  " + problem)
    print("Start the missing service, or stop what holds the port, or set the variables in .env.example.")
    sys.exit(2)
print("Neo4j and Redis are running.")
