import argparse
import logging
import os
import sys
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Add src directory to path
src_dir = Path(__file__).resolve().parent
sys.path.append(str(src_dir))

def run_embedding_pipeline():
    """Run the embedding pipeline to generate text and image embeddings"""
    from src.embedding_pipeline import main as embedding_main
    logger.info("Running embedding pipeline...")
    embedding_main()
    logger.info("Embedding pipeline completed.")

def run_graph_construction():
    """Run the graph construction pipeline to build the Neo4j graph"""
    from src.graph_construction import main as graph_main
    logger.info("Running graph construction...")
    graph_main()
    logger.info("Graph construction completed.")

def run_retrieval_test():
    """Run a test of the hybrid retrieval system"""
    from src.hybrid_retrieval import main as retrieval_main
    logger.info("Running hybrid retrieval test...")
    retrieval_main()
    logger.info("Hybrid retrieval test completed.")

def run_cache_test():
    """Run a test of the edge-aware cache"""
    from src.edge_cache import main as cache_main
    logger.info("Running edge-aware cache test...")
    cache_main()
    logger.info("Edge-aware cache test completed.")

def run_full_system_test():
    """Run a test of the full retrieval system with caching"""
    from src.retrieval_system import main as system_main
    logger.info("Running full system test...")
    system_main()
    logger.info("Full system test completed.")

def run_streamlit_app():
    """Run the Streamlit app"""
    logger.info("Starting Streamlit app...")
    # Set PYTHONPATH to include the current directory for proper imports
    current_dir = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.copy()
    env["PYTHONPATH"] = current_dir
    os.system(f"PYTHONPATH={current_dir} streamlit run {current_dir}/src/streamlit_app.py")

def main():
    """Main entry point for the application"""
    parser = argparse.ArgumentParser(description='Graph-Augmented Retrieval and Edge-Aware Caching System')
    
    parser.add_argument('--mode', type=str, required=True, 
                        choices=['embeddings', 'graph', 'retrieval', 'cache', 'full', 'app', 'all'],
                        help='Which component to run')
    
    args = parser.parse_args()
    
    if args.mode == 'embeddings':
        run_embedding_pipeline()
    elif args.mode == 'graph':
        run_graph_construction()
    elif args.mode == 'retrieval':
        run_retrieval_test()
    elif args.mode == 'cache':
        run_cache_test()
    elif args.mode == 'full':
        run_full_system_test()
    elif args.mode == 'app':
        run_streamlit_app()
    elif args.mode == 'all':
        # Run all components in sequence
        run_embedding_pipeline()
        run_graph_construction()
        run_retrieval_test()
        run_cache_test()
        run_full_system_test()
        run_streamlit_app()

if __name__ == "__main__":
    main() 