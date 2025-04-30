# Graph-Augmented Retrieval and Edge-Aware Caching for Multimodal AI

This project implements a functional hybrid memory system that enables real-time, context-aware retrieval over a multimodal dataset of infrastructure incidents. The system supports semantic search, graph enrichment, and caching strategies optimized for edge-aware AI workloads.

## Features

- **Multimodal Embedding Pipelines**: Generate BERT embeddings for incident descriptions and CLIP embeddings for drone images
- **Graph Construction**: Build a knowledge graph in Neo4j with incidents, assets, zones, technicians, and images
- **Hybrid Retrieval**: Perform semantic search with structured filters and graph enrichment
- **Edge-Aware Caching**: Cache results with modality-specific TTLs in Redis
- **Streamlit UI**: Interactive interface for querying and visualizing results
- **Alternative Graph Models**: Various graph construction approaches for different use cases

## System Architecture

The system consists of five main components:

1. **Multimodal Embedding Pipelines**
   - Text: BERT embeddings for incident descriptions
   - Images: CLIP embeddings for drone images

2. **Graph Construction (Neo4j)**
   - Nodes: Incident, Asset, Zone, Technician, Image
   - Edges: occurred_in, affects, resolved_by, has_image, related_to

3. **Hybrid Retrieval Function**
   - Semantic search with structured filters
   - Graph enrichment for context and relationships

4. **Edge-Aware Caching (Redis)**
   - Modality-specific TTLs: Text (1h), Images (6h), Graph traces (12h)
   - Fingerprint-based cache keys with zone awareness

5. **Query Interface (Streamlit)**
   - Search with filters and parameters
   - Result visualization with images and graph traversals
   - Performance metrics (cache hit/miss, latency)

## Alternative Graph Models

The project includes several alternative graph construction approaches, each with unique capabilities:

1. **Temporal Graph Model**
   - Adds temporal relationships between incidents
   - Creates pattern nodes for recurring issues
   - Enables time-based querying and analysis

2. **Hierarchical Asset Classification**
   - Creates a taxonomy of assets and failure types
   - Adds failure classification to incidents
   - Enables hierarchical queries across asset categories

3. **Multimodal Image Integration**
   - Extracts image features and links them to incidents
   - Creates visual similarity relationships between assets
   - Enables visual feature-based queries

4. **Spatial Integration**
   - Adds geographic coordinates to zone nodes
   - Creates proximity relationships between zones
   - Enables location-based analysis and regional patterns

5. **Resolution Patterns**
   - Extracts resolution steps from incident descriptions
   - Creates templates for common problem solutions
   - Links technicians to their expertise areas
   - Enables recommendation of proven fix approaches

These can be used individually or in combination for different use cases.

## Requirements

- Python 3.8+
- Neo4j (running locally or remotely)
- Redis (running locally or remotely)
- Dependencies listed in requirements.txt

## Setup

1. **Create and activate a virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. **Install dependencies**

```bash
pip install -r requirements.txt
```

3. **Set up Neo4j**

- Install Neo4j: [Neo4j Download](https://neo4j.com/download/)
- Start Neo4j and create a new database
- Update the Neo4j connection details in `src/config.py` or set environment variables

4. **Set up Redis**

- Install Redis: [Redis Download](https://redis.io/download)
- Start Redis server
- Update the Redis connection details in `src/config.py` or set environment variables

## Environment Variables

The following environment variables can be used to configure the system:

- `NEO4J_URI`: URI for the Neo4j database (default: "bolt://localhost:7687")
- `NEO4J_USER`: Username for Neo4j (default: "neo4j")
- `NEO4J_PASSWORD`: Password for Neo4j
- `REDIS_HOST`: Hostname for Redis (default: "localhost")
- `REDIS_PORT`: Port for Redis (default: 6379)
- `REDIS_DB`: Redis database number (default: 0)

## Usage

The project can be run in different modes using the `main.py` script:

```bash
python main.py --mode [mode]
```

Available modes:

- `embeddings`: Generate embeddings for incident descriptions and images
- `graph`: Build the Neo4j graph with all relationships
- `retrieval`: Test the hybrid retrieval system
- `cache`: Test the edge-aware caching system
- `full`: Test the complete system with retrieval and caching
- `app`: Launch the Streamlit UI
- `all`: Run all components in sequence

### Example: Running the Complete System

```bash
# Start Neo4j and Redis servers first
python main.py --mode all
```

### Example: Running Just the Streamlit UI

```bash
python main.py --mode app
```

### Using Alternative Graph Models

To use one of the alternative graph construction approaches:

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

## Dataset

The system works with a synthetic but realistic dataset of infrastructure incidents:

- `incidents.csv`: Incident descriptions, metadata, resolution info
- `assets.csv`: Registry of infrastructure assets
- `technicians.csv`: Links incidents to technician IDs
- `zones.csv`: Metadata for operational zones
- `images.csv`: Drone inspection images linked to incidents
- `logs.jsonl`: Semi-structured asset-level logs
- `drone-images/`: 20 drone inspection images

## Project Structure

```
.
├── data/                  # Dataset files
│   ├── incidents.csv
│   ├── assets.csv
│   ├── technicians.csv
│   ├── zones.csv
│   ├── images.csv
│   ├── logs.jsonl
│   └── drone-images/     # Drone inspection images
├── embeddings/            # Generated embeddings
├── src/                   # Source code
│   ├── config.py          # Configuration settings
│   ├── embedding_pipeline.py  # Embedding generation
│   ├── graph_construction.py  # Neo4j graph building
│   ├── hybrid_retrieval.py    # Semantic search + graph
│   ├── edge_cache.py      # Redis caching with TTLs
│   ├── retrieval_system.py    # Combined system
│   ├── streamlit_app.py   # Web interface
│   └── alternative_graph_models/  # Alternative graph approaches
│       ├── temporal_graph.py
│       ├── hierarchical_asset_graph.py
│       ├── multimodal_image_graph.py
│       ├── spatial_graph.py
│       ├── resolution_patterns.py
│       └── README.md
├── main.py                # Main entry point
├── requirements.txt       # Dependencies
├── LICENSE                # MIT License
└── README.md              # This file
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- This project uses Hugging Face models for embeddings
- Graph functionality provided by Neo4j
- Caching functionality provided by Redis
- UI powered by Streamlit 