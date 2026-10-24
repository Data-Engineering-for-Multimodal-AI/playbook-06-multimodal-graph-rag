"""
Multimodal Image Graph - Alternative Implementation

This implementation creates a richer integration between image features and incidents,
enabling visual feature-based queries and analysis.
"""

import pandas as pd
import logging
from src.graph_db import Graph, Node

from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, DATA_DIR

logger = logging.getLogger(__name__)

class MultimodalImageGraphConstructor:
    def __init__(self, base_constructor):
        """Initialize with the base graph constructor to extend its functionality"""
        self.base = base_constructor
        self.graph = self.base.graph
        self.images_df = None
    
    def build_graph(self):
        """Build the multimodal graph by first creating the base graph, then adding image features"""
        # Build the base graph first
        self.base.build_graph()
        
        # Load data again for image processing
        self.images_df = self.base.images_df
        
        # Add image feature integration
        self.integrate_image_features()
        self.create_visual_patterns()
        
        logger.info("Multimodal image graph construction complete")
    
    def integrate_image_features(self):
        """Create image feature nodes integrated with incidents"""
        logger.info("Creating image feature nodes...")
        
        # Create image feature categories
        features = ["Damage", "Corrosion", "Alignment", "Obstruction", "Normal"]
        for feature in features:
            self.graph.create(Node("ImageFeature", name=feature))
        
        # Connect images to features (in a real system, this would use computer vision)
        # Use simple keyword matching as a mock implementation
        feature_keywords = {
            "Damage": ["damage", "broken", "missing", "damaged"],
            "Corrosion": ["rust", "corrosion", "weathered", "dusty"],
            "Alignment": ["alignment", "misaligned", "tilted", "angle"],
            "Obstruction": ["obstruction", "obscured", "blocked", "vegetation"],
            "Normal": ["normal", "functional", "operational", "clear"]
        }
        
        feature_count = 0
        for _, image in self.images_df.iterrows():
            caption = image['caption'].lower()
            
            for feature, keywords in feature_keywords.items():
                if any(keyword in caption for keyword in keywords):
                    query = """
                    MATCH (img:Image {image_filename: $filename}),
                          (f:ImageFeature {name: $feature})
                    CREATE (img)-[:SHOWS]->(f)
                    """
                    self.graph.run(query, 
                                  filename=image['image_filename'],
                                  feature=feature)
                    feature_count += 1
        
        logger.info(f"Created {len(features)} feature types and {feature_count} SHOWS relationships")
        
        # Create direct relationships between incidents and visual features
        query = """
        MATCH (i:Incident)-[:HAS_IMAGE]->(img:Image)-[:SHOWS]->(f:ImageFeature)
        CREATE (i)-[:HAS_VISUAL_FEATURE {via_image: img.image_filename}]->(f)
        """
        self.graph.run(query)
        
        # Count visual feature relationships
        visual_count = self.graph.evaluate("""
        MATCH ()-[r:HAS_VISUAL_FEATURE]->() 
        RETURN count(r)
        """)
        logger.info(f"Created {visual_count} HAS_VISUAL_FEATURE relationships between incidents and features")
    
    def create_visual_patterns(self):
        """Create visual pattern nodes connecting assets with similar visual features"""
        logger.info("Creating visual pattern nodes...")
        
        # Find assets with similar visual features
        query = """
        MATCH (a1:Asset)<-[:AFFECTS]-(i1:Incident)-[:HAS_VISUAL_FEATURE]->(f:ImageFeature),
              (a2:Asset)<-[:AFFECTS]-(i2:Incident)-[:HAS_VISUAL_FEATURE]->(f)
        WHERE a1.asset_type = a2.asset_type AND i1.incident_id <> i2.incident_id
        WITH a1, a2, f.name AS feature, COUNT(DISTINCT i1) AS count
        WHERE count > 0
        CREATE (a1)-[:SHARES_VISUAL_ISSUE {feature: feature, count: count}]->(a2)
        """
        self.graph.run(query)
        
        # Count visual pattern relationships
        pattern_count = self.graph.evaluate("""
        MATCH ()-[r:SHARES_VISUAL_ISSUE]->() 
        RETURN count(r)
        """)
        logger.info(f"Created {pattern_count} SHARES_VISUAL_ISSUE relationships between assets")
        
        # Create visual correlation nodes
        query = """
        MATCH (f:ImageFeature)<-[:SHOWS]-(img:Image)<-[:HAS_IMAGE]-(i:Incident)-[:AFFECTS]->(a:Asset)
        WITH f.name AS feature, a.asset_type AS asset_type, COUNT(DISTINCT i) AS incident_count
        WHERE incident_count > 0
        CREATE (vc:VisualCorrelation {
            feature: feature,
            asset_type: asset_type,
            correlation_id: feature + '_' + asset_type,
            incident_count: incident_count
        })
        """
        self.graph.run(query)
        
        # Connect visual correlations to features and asset types
        query = """
        MATCH (vc:VisualCorrelation), (f:ImageFeature)
        WHERE vc.feature = f.name
        CREATE (vc)-[:CORRELATES_WITH]->(f)
        """
        self.graph.run(query)
        
        query = """
        MATCH (vc:VisualCorrelation), (at:AssetType)
        WHERE vc.asset_type = at.name
        CREATE (vc)-[:APPLIES_TO]->(at)
        """
        self.graph.run(query)
        
        # Count correlation nodes
        corr_count = self.graph.evaluate("MATCH (vc:VisualCorrelation) RETURN count(vc)")
        logger.info(f"Created {corr_count} visual correlation nodes")

def main():
    """Main function to build a multimodal image graph"""
    from src.graph_construction import GraphConstructor
    
    # Create base constructor
    base_constructor = GraphConstructor()
    
    # Create multimodal constructor that extends the base
    multimodal_constructor = MultimodalImageGraphConstructor(base_constructor)
    
    # Build the enhanced graph
    multimodal_constructor.build_graph()

if __name__ == "__main__":
    main() 