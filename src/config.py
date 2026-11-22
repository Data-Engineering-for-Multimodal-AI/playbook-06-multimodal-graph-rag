import os
from pathlib import Path

# Directory paths
ROOT_DIR = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# The sample data, or your own folder in the same layout (make load DIR=..., see scripts/own_data.py)
DATA_DIR = Path(os.environ.get("DATA_DIR", str(ROOT_DIR / "data"))).resolve()
EMBEDDINGS_DIR = ROOT_DIR / "embeddings"

# Ensure directories exist
EMBEDDINGS_DIR.mkdir(exist_ok=True)

# Neo4j configuration
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "changeThisPassword")  # Set via environment variable in production

# Redis configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))

# TTL values (in seconds)
TEXT_TTL = 3600  # 1 hour
IMAGE_TTL = 21600  # 6 hours
GRAPH_TTL = 43200  # 12 hours

# Retrieval parameters
TOP_K = 5

# Neo4j vector indexes over the embeddings stored on the nodes
TEXT_VECTOR_INDEX = "incident_text_embedding"   # Incident.text_embedding, all-MiniLM-L6-v2, 384 numbers
IMAGE_VECTOR_INDEX = "image_clip_embedding"     # Image.clip_embedding, CLIP ViT-B/32, 512 numbers 


def data_file(name):
    """Path of a data CSV. The samples use 'assets (1).csv' and 'technicians (1).csv' (names from the
    original export); a folder of your own may use 'assets.csv' and 'technicians.csv' instead."""
    exported = DATA_DIR / f"{name} (1).csv"
    return exported if exported.exists() or not (DATA_DIR / f"{name}.csv").exists() else DATA_DIR / f"{name}.csv"
