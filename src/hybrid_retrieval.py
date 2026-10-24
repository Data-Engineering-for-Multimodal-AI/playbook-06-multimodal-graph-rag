import logging
from typing import List, Dict, Any, Optional, Tuple, Union

import numpy as np
import pandas as pd
import torch
from PIL import Image
from sentence_transformers import SentenceTransformer
from transformers import CLIPModel, CLIPProcessor

from src.graph_db import Graph
from src.config import (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, TOP_K,
                        TEXT_VECTOR_INDEX, IMAGE_VECTOR_INDEX)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CLIP_MODEL = "openai/clip-vit-base-patch32"


def cosine(score: float) -> float:
    """Neo4j reports cosine similarity rescaled to 0..1 as (1 + cos) / 2; return the cosine itself"""
    return 2 * score - 1


class HybridRetriever:
    def __init__(self):
        self.text_model = None
        self.clip_model = None
        self.clip_processor = None
        self.graph = None
        
        # Load necessary data
        self.load_data()
        self.connect_to_graph()
    
    def load_data(self):
        """Load the query embedding model (the embeddings themselves are stored in Neo4j)"""
        logger.info("Loading text embedding model...")
        self.text_model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("Data loading complete")
    
    def load_clip(self):
        """Load CLIP on first use: it embeds text queries and photos into the drone images' space"""
        if self.clip_model is None:
            logger.info("Loading CLIP model...")
            self.clip_model = CLIPModel.from_pretrained(CLIP_MODEL)
            self.clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL)
    
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
        
        # Vector search in Neo4j, then the structured filters on the incident properties.
        # The sample graph has 100 incidents, so every incident is a candidate and filtering stays exact.
        start_time, end_time = time_range if time_range else (None, None)
        to_iso = lambda t: pd.to_datetime(t).strftime('%Y-%m-%dT%H:%M:%S') if t else None
        results = self.graph.run(f"""
        MATCH (i:Incident)
          SEARCH i IN (VECTOR INDEX {TEXT_VECTOR_INDEX} FOR $embedding LIMIT $candidates)
          SCORE AS score
        WHERE ($zone IS NULL OR i.zone = $zone)
          AND ($priority IS NULL OR i.priority = $priority)
          AND ($start IS NULL OR i.timestamp >= $start)
          AND ($end IS NULL OR i.timestamp <= $end)
        RETURN i.incident_id AS incident_id, score AS similarity_score, i.description AS description,
               i.zone AS zone, i.asset_type AS asset_type, i.asset_id AS asset_id, i.timestamp AS timestamp,
               i.priority AS priority, i.status AS status, i.resolution_summary AS resolution_summary
        ORDER BY score DESC
        LIMIT $top_k
        """, embedding=query_embedding, candidates=max(top_k, 100), top_k=top_k,
            zone=zone_filter, priority=priority_filter, start=to_iso(start_time), end=to_iso(end_time))
        
        for result in results:
            result['similarity_score'] = cosine(result['similarity_score'])
        if zone_filter:
            logger.info(f"Applied zone filter: {zone_filter}")
        if time_range:
            logger.info(f"Applied time range filter: {start_time} to {end_time}")
        if priority_filter:
            logger.info(f"Applied priority filter: {priority_filter}")
        
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

    def embed_for_images(self, query: Union[str, Image.Image]) -> np.ndarray:
        """CLIP embedding of a text query or a photo, comparable with the drone image embeddings"""
        self.load_clip()
        with torch.no_grad():
            if isinstance(query, str):
                inputs = self.clip_processor(text=[query], return_tensors="pt", padding=True)
                outputs = self.clip_model.get_text_features(**inputs)
            else:
                inputs = self.clip_processor(images=query.convert('RGB'), return_tensors="pt")
                outputs = self.clip_model.get_image_features(**inputs)
        return getattr(outputs, "pooler_output", outputs)[0].numpy()
    
    def search_images(self, query: Union[str, Image.Image], top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Find drone images that match a text description or look like a given photo,
        with the incident each image belongs to
        """
        logger.info("Searching drone images...")
        return [dict(r, similarity_score=cosine(r['similarity_score'])) for r in self.graph.run(f"""
        MATCH (img:Image)
          SEARCH img IN (VECTOR INDEX {IMAGE_VECTOR_INDEX} FOR $embedding LIMIT $top_k)
          SCORE AS score
        MATCH (i:Incident)-[:HAS_IMAGE]->(img)
        RETURN img.image_filename AS filename, img.caption AS caption, score AS similarity_score,
               i.incident_id AS incident_id, i.description AS description, i.zone AS zone,
               i.status AS status, i.resolution_summary AS resolution_summary
        ORDER BY score DESC
        """, embedding=self.embed_for_images(query), top_k=top_k)]
    
    def similar_resolutions(self, query: str, neighbors: int = 10) -> List[Dict[str, Any]]:
        """
        How were incidents like this resolved? Takes the most similar resolved incidents,
        follows RESOLVED_BY to the technicians, and groups them by resolution
        """
        logger.info("Looking up how similar incidents were resolved...")
        return self.graph.run(f"""
        MATCH (i:Incident)
          SEARCH i IN (VECTOR INDEX {TEXT_VECTOR_INDEX} FOR $embedding LIMIT 100)
          SCORE AS score
        WHERE i.status = 'Resolved' AND i.resolution_summary <> ''
        WITH i, score ORDER BY score DESC LIMIT $neighbors
        OPTIONAL MATCH (i)-[:RESOLVED_BY]->(t:Technician)
        WITH i.resolution_summary AS resolution, i, score, t
        ORDER BY score DESC
        RETURN resolution, count(DISTINCT i) AS incidents, collect(DISTINCT i.incident_id) AS incident_ids,
               collect(DISTINCT t.technician_id) AS technicians, round(2 * max(score) - 1, 4) AS best_similarity
        ORDER BY incidents DESC, best_similarity DESC
        """, embedding=self.embed_query(query), neighbors=neighbors)

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
    
    # How similar resolved incidents were fixed (through the RESOLVED_BY edges)
    print(f"\nHow similar resolved incidents were fixed:")
    for row in retriever.similar_resolutions(test_query):
        print(f"  {row['incidents']} x {row['resolution']} "
              f"({', '.join(row['incident_ids'])}; technicians: {', '.join(row['technicians']) or 'none recorded'})")
    
    # Drone images that match a visual description (CLIP text-to-image search)
    image_query = "tower overgrown by trees in a forest"
    print(f"\nDrone images matching '{image_query}':")
    for photo in retriever.search_images(image_query, top_k=3):
        print(f"  {photo['similarity_score']:.4f} {photo['filename']} ({photo['incident_id']}, {photo['status']})")

if __name__ == "__main__":
    main() 