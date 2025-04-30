import numpy as np
import pandas as pd
import os
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sentence_transformers import SentenceTransformer
from py2neo import Graph
from sklearn.metrics.pairwise import cosine_similarity

from src.config import DATA_DIR, EMBEDDINGS_DIR, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, TOP_K

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HybridRetriever:
    def __init__(self):
        self.text_model = None
        self.text_embeddings = None
        self.text_incident_ids = None
        self.image_embeddings = None
        self.image_incident_ids = None
        self.graph = None
        self.incidents_df = None
        self.images_df = None
        
        # Load necessary data
        self.load_data()
        self.connect_to_graph()
    
    def load_data(self):
        """Load embeddings and dataset"""
        logger.info("Loading embeddings and dataset...")
        
        # Load text embeddings
        text_embeddings_path = os.path.join(EMBEDDINGS_DIR, "text_embeddings.npy")
        text_incident_ids_path = os.path.join(EMBEDDINGS_DIR, "text_incident_ids.npy")
        
        self.text_embeddings = np.load(text_embeddings_path)
        self.text_incident_ids = np.load(text_incident_ids_path, allow_pickle=True)
        
        # Load image embeddings
        image_embeddings_path = os.path.join(EMBEDDINGS_DIR, "image_embeddings.npy")
        image_incident_ids_path = os.path.join(EMBEDDINGS_DIR, "image_incident_ids.npy")
        
        self.image_embeddings = np.load(image_embeddings_path)
        self.image_incident_ids = np.load(image_incident_ids_path, allow_pickle=True)
        
        # Load incident data
        incidents_path = os.path.join(DATA_DIR, "incidents.csv")
        self.incidents_df = pd.read_csv(incidents_path)
        
        # Load images data
        images_path = os.path.join(DATA_DIR, "images.csv")
        self.images_df = pd.read_csv(images_path)
        
        # Load text model for query embedding
        logger.info("Loading text embedding model...")
        self.text_model = SentenceTransformer('all-MiniLM-L6-v2')
        
        logger.info("Data loading complete")
    
    def connect_to_graph(self):
        """Connect to Neo4j database"""
        try:
            logger.info(f"Connecting to Neo4j at {NEO4J_URI}...")
            self.graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            logger.info("Connected to Neo4j successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
    
    def embed_query(self, query: str) -> np.ndarray:
        """Generate embedding for the query text"""
        query_embedding = self.text_model.encode([query])[0]
        return query_embedding
    
    def semantic_search(self, 
                      query: str, 
                      top_k: int = TOP_K, 
                      zone_filter: Optional[str] = None,
                      time_range: Optional[Tuple[str, str]] = None,
                      priority_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Perform semantic search with optional structured filters
        
        Args:
            query: Incident description query
            top_k: Number of top results to return
            zone_filter: Optional filter for specific zone
            time_range: Optional time range filter (start_time, end_time) in ISO format
            priority_filter: Optional priority filter (High, Medium, Low)
            
        Returns:
            List of top-k semantically similar incidents with metadata
        """
        logger.info(f"Performing semantic search for query: '{query}'")
        
        # Embed the query
        query_embedding = self.embed_query(query)
        
        # Calculate similarity scores with text embeddings
        similarity_scores = cosine_similarity([query_embedding], self.text_embeddings)[0]
        
        # Convert to dataframe for filtering
        results_df = pd.DataFrame({
            'incident_id': self.text_incident_ids,
            'similarity_score': similarity_scores
        })
        
        # Merge with incidents dataframe to apply structured filters
        results_df = results_df.merge(self.incidents_df, on='incident_id', how='inner')
        
        # Apply zone filter if provided
        if zone_filter:
            results_df = results_df[results_df['zone'] == zone_filter]
            logger.info(f"Applied zone filter: {zone_filter}")
        
        # Apply time range filter if provided
        if time_range:
            start_time, end_time = time_range
            results_df['timestamp'] = pd.to_datetime(results_df['timestamp'])
            results_df = results_df[
                (results_df['timestamp'] >= pd.to_datetime(start_time)) & 
                (results_df['timestamp'] <= pd.to_datetime(end_time))
            ]
            logger.info(f"Applied time range filter: {start_time} to {end_time}")
        
        # Apply priority filter if provided
        if priority_filter:
            results_df = results_df[results_df['priority'] == priority_filter]
            logger.info(f"Applied priority filter: {priority_filter}")
        
        # Sort by similarity score and get top-k results
        results_df = results_df.sort_values('similarity_score', ascending=False).head(top_k)
        
        # Convert to list of dictionaries
        results = results_df.to_dict('records')
        
        logger.info(f"Retrieved {len(results)} results from semantic search")
        return results
    
    def enrich_with_graph_context(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enrich results with graph context from Neo4j"""
        logger.info("Enriching results with graph context...")
        
        enriched_results = []
        
        for result in results:
            incident_id = result['incident_id']
            
            # Get related incidents
            related_incidents_query = """
            MATCH (i:Incident {incident_id: $incident_id})-[r:RELATED_TO]->(related:Incident)
            RETURN related.incident_id as incident_id, related.description as description, 
                   related.priority as priority, related.status as status, 
                   r.reason as reason, r.time_diff_hours as time_diff_hours
            """
            related_incidents = self.graph.run(related_incidents_query, incident_id=incident_id).data()
            
            # Get technician information
            technician_query = """
            MATCH (i:Incident {incident_id: $incident_id})-[:RESOLVED_BY]->(t:Technician)
            RETURN t.technician_id as technician_id
            """
            technician = self.graph.run(technician_query, incident_id=incident_id).data()
            
            # Get zone information
            zone_query = """
            MATCH (i:Incident {incident_id: $incident_id})-[:OCCURRED_IN]->(z:Zone)
            RETURN z.zone_id as zone_id, z.region as region, z.supervisor as supervisor
            """
            zone_info = self.graph.run(zone_query, incident_id=incident_id).data()
            
            # Get asset information
            asset_query = """
            MATCH (i:Incident {incident_id: $incident_id})-[:AFFECTS]->(a:Asset)
            RETURN a.asset_id as asset_id, a.asset_name as asset_name, a.asset_type as asset_type
            """
            asset_info = self.graph.run(asset_query, incident_id=incident_id).data()
            
            # Get image information
            image_query = """
            MATCH (i:Incident {incident_id: $incident_id})-[:HAS_IMAGE]->(img:Image)
            RETURN img.image_filename as filename, img.caption as caption
            """
            image_info = self.graph.run(image_query, incident_id=incident_id).data()
            
            # Combine all information
            enriched_result = result.copy()
            enriched_result['related_incidents'] = related_incidents
            enriched_result['technician'] = technician[0] if technician else None
            enriched_result['zone_details'] = zone_info[0] if zone_info else None
            enriched_result['asset_details'] = asset_info[0] if asset_info else None
            enriched_result['image'] = image_info[0] if image_info else None
            
            # Get supplementary image info from images_df if not found in graph
            if not enriched_result['image']:
                image_row = self.images_df[self.images_df['incident_id'] == incident_id]
                if not image_row.empty:
                    enriched_result['image'] = {
                        'filename': image_row.iloc[0]['image_filename'],
                        'caption': image_row.iloc[0]['caption']
                    }
            
            enriched_results.append(enriched_result)
        
        logger.info("Graph enrichment complete")
        return enriched_results
    
    def retrieve(self, 
               query: str, 
               top_k: int = TOP_K, 
               zone_filter: Optional[str] = None,
               time_range: Optional[Tuple[str, str]] = None,
               priority_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Main retrieval function combining semantic search and graph enrichment
        
        Args:
            query: Incident description query
            top_k: Number of top results to return
            zone_filter: Optional filter for specific zone
            time_range: Optional time range filter (start_time, end_time) in ISO format
            priority_filter: Optional priority filter (High, Medium, Low)
            
        Returns:
            List of enriched results
        """
        # 1. Perform semantic search with structured filters
        search_results = self.semantic_search(
            query, 
            top_k=top_k, 
            zone_filter=zone_filter,
            time_range=time_range,
            priority_filter=priority_filter
        )
        
        # 2. Enrich results with graph context
        enriched_results = self.enrich_with_graph_context(search_results)
        
        return enriched_results

def main():
    """Test the hybrid retriever"""
    retriever = HybridRetriever()
    
    test_query = "Packet loss observed on Tower"
    results = retriever.retrieve(
        query=test_query,
        top_k=3,
        zone_filter="Zone 11"
    )
    
    # Print results
    print(f"Query: {test_query}")
    print(f"Retrieved {len(results)} results:")
    
    for i, result in enumerate(results):
        print(f"\nResult {i+1}:")
        print(f"Incident ID: {result['incident_id']}")
        print(f"Description: {result['description']}")
        print(f"Similarity Score: {result['similarity_score']:.4f}")
        print(f"Zone: {result['zone']}")
        print(f"Status: {result['status']}")
        
        if result['image']:
            print(f"Image: {result['image']['filename']}")
            print(f"Caption: {result['image']['caption']}")
        
        if result['related_incidents']:
            print("\nRelated Incidents:")
            for related in result['related_incidents']:
                print(f"  - {related['incident_id']}: {related['description']}")
        
        if result['zone_details']:
            print(f"\nZone Details:")
            print(f"  Region: {result['zone_details']['region']}")
            print(f"  Supervisor: {result['zone_details']['supervisor']}")

if __name__ == "__main__":
    main() 