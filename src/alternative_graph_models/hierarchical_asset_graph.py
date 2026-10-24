"""
Hierarchical Asset Classification - Alternative Implementation

This implementation adds hierarchical asset classification and failure type taxonomy
to enhance the graph's retrieval capabilities.
"""

import pandas as pd
import logging
from src.graph_db import Graph, Node

from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger(__name__)

class HierarchicalAssetGraphConstructor:
    def __init__(self, base_constructor):
        """Initialize with the base graph constructor to extend its functionality"""
        self.base = base_constructor
        self.graph = self.base.graph
        self.assets_df = None
        self.incidents_df = None
    
    def build_graph(self):
        """Build the hierarchical graph by first creating the base graph, then adding taxonomy"""
        # Build the base graph first
        self.base.build_graph()
        
        # Load data again for hierarchical processing
        self.assets_df = self.base.assets_df
        self.incidents_df = self.base.incidents_df
        
        # Add hierarchical structures
        self.create_asset_hierarchy()
        self.create_failure_taxonomy()
        
        logger.info("Hierarchical asset graph construction complete")
    
    def create_asset_hierarchy(self):
        """Create hierarchical asset classification"""
        logger.info("Creating asset type hierarchy...")
        
        # Create asset type nodes
        asset_types = self.assets_df['asset_type'].unique()
        for asset_type in asset_types:
            self.graph.create(Node("AssetType", name=asset_type))
            
        # Create IS_TYPE relationships
        type_rel_count = 0
        for _, asset in self.assets_df.iterrows():
            query = """
            MATCH (a:Asset {asset_unique_id: $asset_unique_id}), 
                  (t:AssetType {name: $asset_type})
            CREATE (a)-[:IS_TYPE]->(t)
            """
            self.graph.run(query, 
                           asset_unique_id=asset['asset_unique_id'], 
                           asset_type=asset['asset_type'])
            type_rel_count += 1
                   
        logger.info(f"Created {len(asset_types)} asset type nodes and {type_rel_count} IS_TYPE relationships")
        
        # Create equipment category nodes (higher level abstraction)
        equipment_categories = {
            "Network": ["Router", "Repeater"],
            "Infrastructure": ["Tower", "BTS"]
        }
        
        for category, types in equipment_categories.items():
            # Create category node
            category_node = Node("EquipmentCategory", name=category)
            self.graph.create(category_node)
            
            # Link asset types to category
            for asset_type in types:
                query = """
                MATCH (t:AssetType {name: $asset_type}), 
                      (c:EquipmentCategory {name: $category})
                CREATE (t)-[:IN_CATEGORY]->(c)
                """
                self.graph.run(query, asset_type=asset_type, category=category)
        
        logger.info(f"Created equipment category hierarchy with {len(equipment_categories)} categories")
    
    def create_failure_taxonomy(self):
        """Create failure type taxonomy and classify incidents"""
        logger.info("Creating failure type taxonomy...")
        
        # Create failure type nodes
        failure_types = ["Hardware", "Software", "Network", "Power", "Environmental"]
        for failure in failure_types:
            self.graph.create(Node("FailureType", name=failure))
        
        # Define keywords for classification
        keywords = {
            "Hardware": ["faulty", "damaged", "broken", "hardware", "module", "panel"],
            "Software": ["firmware", "update", "software", "configuration"],
            "Network": ["packet loss", "latency", "disconnection", "signal", "port flapping"],
            "Power": ["power", "energy", "voltage", "battery"],
            "Environmental": ["storm", "heat", "cold", "weather", "vegetation"]
        }
        
        # Connect incidents to failure types
        classification_count = 0
        for _, incident in self.incidents_df.iterrows():
            desc = incident['description'].lower()
            
            for failure_type, words in keywords.items():
                if any(word in desc for word in words):
                    query = """
                    MATCH (i:Incident {incident_id: $incident_id}), 
                          (f:FailureType {name: $failure_type})
                    CREATE (i)-[:CLASSIFIED_AS]->(f)
                    """
                    self.graph.run(query, 
                                  incident_id=incident['incident_id'], 
                                  failure_type=failure_type)
                    classification_count += 1
                    break  # Only classify under one category
        
        logger.info(f"Created failure taxonomy with {len(failure_types)} types and classified {classification_count} incidents")
        
        # Create failure statistics nodes
        query = """
        MATCH (a:AssetType)<-[:IS_TYPE]-(:Asset)<-[:AFFECTS]-(i:Incident)-[:CLASSIFIED_AS]->(f:FailureType)
        WITH a.name AS asset_type, f.name AS failure_type, COUNT(i) AS incident_count
        WHERE incident_count > 0
        CREATE (fs:FailureStatistic {
            asset_type: asset_type,
            failure_type: failure_type,
            incident_count: incident_count,
            statistic_id: asset_type + '_' + failure_type
        })
        """
        self.graph.run(query)
        
        # Count statistics nodes
        stat_count = self.graph.evaluate("MATCH (fs:FailureStatistic) RETURN count(fs)")
        logger.info(f"Created {stat_count} failure statistics nodes")

def main():
    """Main function to build a hierarchical asset graph"""
    from src.graph_construction import GraphConstructor
    
    # Create base constructor
    base_constructor = GraphConstructor()
    
    # Create hierarchical constructor that extends the base
    hierarchical_constructor = HierarchicalAssetGraphConstructor(base_constructor)
    
    # Build the enhanced graph
    hierarchical_constructor.build_graph()

if __name__ == "__main__":
    main() 