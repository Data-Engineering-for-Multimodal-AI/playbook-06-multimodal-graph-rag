import os
import pandas as pd
from datetime import datetime, timedelta
from py2neo import Graph, Node, Relationship
import logging
from tqdm import tqdm

from src.config import DATA_DIR, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GraphConstructor:
    def __init__(self):
        self.graph = None
        self.connect_to_graph()
    
    def connect_to_graph(self):
        """Connect to Neo4j database"""
        try:
            logger.info(f"Connecting to Neo4j at {NEO4J_URI}...")
            self.graph = Graph(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            logger.info("Connected to Neo4j successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise
    
    def clear_graph(self):
        """Clear all nodes and relationships in the graph"""
        logger.info("Clearing the graph database...")
        self.graph.run("MATCH (n) DETACH DELETE n")
        logger.info("Graph database cleared")
    
    def setup_constraints(self):
        """Setup necessary constraints for the graph"""
        logger.info("Setting up Neo4j constraints...")
        
        # Drop any existing constraints first to avoid conflicts
        try:
            self.graph.run("SHOW CONSTRAINTS").data()
            self.graph.run("DROP CONSTRAINT ON (z:Zone) ASSERT z.zone_id IS UNIQUE")
        except:
            logger.info("No Zone constraint to drop")
            
        try:
            self.graph.run("DROP CONSTRAINT ON (a:Asset) ASSERT a.asset_id IS UNIQUE")
        except:
            logger.info("No Asset constraint to drop")
            
        try:
            self.graph.run("DROP CONSTRAINT ON (i:Incident) ASSERT i.incident_id IS UNIQUE")
        except:
            logger.info("No Incident constraint to drop")
        
        # Create new constraints with proper uniqueness
        self.graph.run("CREATE CONSTRAINT ON (z:Zone) ASSERT z.zone_id IS UNIQUE")
        logger.info("Created Zone constraint")
        
        # For Assets, we'll create a composite unique constraint on asset_unique_id
        self.graph.run("CREATE CONSTRAINT ON (a:Asset) ASSERT a.asset_unique_id IS UNIQUE")
        logger.info("Created Asset constraint")
        
        self.graph.run("CREATE CONSTRAINT ON (i:Incident) ASSERT i.incident_id IS UNIQUE")
        logger.info("Created Incident constraint")
        
        logger.info("Neo4j constraints setup complete")
    
    def load_data(self):
        """Load all data from CSV files"""
        logger.info("Loading data from CSV files...")
        
        # Load incidents data
        incidents_path = os.path.join(DATA_DIR, "incidents.csv")
        self.incidents_df = pd.read_csv(incidents_path)
        logger.info(f"Loaded {len(self.incidents_df)} incidents")
        
        # Load assets data
        assets_path = os.path.join(DATA_DIR, "assets (1).csv")
        self.assets_df = pd.read_csv(assets_path)
        logger.info(f"Loaded {len(self.assets_df)} assets")
        
        # Load zones data
        zones_path = os.path.join(DATA_DIR, "zones.csv")
        self.zones_df = pd.read_csv(zones_path)
        logger.info(f"Loaded {len(self.zones_df)} zones")
        
        # Load technicians data
        technicians_path = os.path.join(DATA_DIR, "technicians (1).csv")
        self.technicians_df = pd.read_csv(technicians_path)
        logger.info(f"Loaded {len(self.technicians_df)} technician assignments")
        
        # Load images data
        images_path = os.path.join(DATA_DIR, "images.csv")
        self.images_df = pd.read_csv(images_path)
        logger.info(f"Loaded {len(self.images_df)} images")
    
    def create_zone_nodes(self):
        """Create Zone nodes in Neo4j"""
        logger.info("Creating Zone nodes...")
        
        for _, zone in self.zones_df.iterrows():
            zone_node = Node(
                "Zone",
                zone_id=zone['zone_id'],
                region=zone['region'],
                supervisor=zone['supervisor']
            )
            self.graph.create(zone_node)
        
        logger.info("Zone nodes created")
    
    def create_asset_nodes(self):
        """Create Asset nodes in Neo4j"""
        logger.info("Creating Asset nodes...")
        
        # Get unique assets by combining asset_id, asset_type, and zone_id
        # This ensures we don't create duplicate nodes for the same logical asset
        self.assets_df['asset_unique_id'] = self.assets_df['asset_id'] + '_' + self.assets_df['asset_type'] + '_' + self.assets_df['zone_id']
        unique_assets = self.assets_df.drop_duplicates(subset=['asset_unique_id'])
        
        logger.info(f"Creating {len(unique_assets)} unique asset nodes")
        
        for _, asset in unique_assets.iterrows():
            asset_node = Node(
                "Asset",
                asset_id=asset['asset_id'],
                asset_name=asset['asset_name'],
                asset_type=asset['asset_type'],
                zone_id=asset['zone_id'],
                asset_unique_id=asset['asset_unique_id']
            )
            self.graph.create(asset_node)
            
            # Create relationship with Zone
            query = """
            MATCH (a:Asset {asset_unique_id: $asset_unique_id}), (z:Zone {zone_id: $zone_id})
            MERGE (a)-[:LOCATED_IN]->(z)
            """
            self.graph.run(query, asset_unique_id=asset['asset_unique_id'], zone_id=asset['zone_id'])
        
        logger.info("Asset nodes created")
    
    def create_incident_nodes(self):
        """Create Incident nodes in Neo4j"""
        logger.info("Creating Incident nodes...")
        
        for _, incident in tqdm(self.incidents_df.iterrows(), total=len(self.incidents_df)):
            # Convert timestamp string to datetime object
            timestamp = datetime.strptime(incident['timestamp'], '%Y-%m-%dT%H:%M:%S')
            
            incident_node = Node(
                "Incident",
                incident_id=incident['incident_id'],
                description=incident['description'],
                zone=incident['zone'],
                asset_type=incident['asset_type'],
                asset_id=incident['asset_id'],
                timestamp=timestamp.strftime('%Y-%m-%dT%H:%M:%S'),
                priority=incident['priority'],
                status=incident['status'],
                resolution_summary=incident['resolution_summary'] if pd.notna(incident['resolution_summary']) else ""
            )
            self.graph.create(incident_node)
            
            # Create relationship with Zone
            query = """
            MATCH (i:Incident {incident_id: $incident_id}), (z:Zone {zone_id: $zone})
            CREATE (i)-[:OCCURRED_IN]->(z)
            """
            self.graph.run(query, incident_id=incident['incident_id'], zone=incident['zone'])
            
            # Find the correct asset using asset_id, asset_type, and zone
            # Create relationship with Asset using asset_unique_id
            asset_unique_id = incident['asset_id'] + '_' + incident['asset_type'] + '_' + incident['zone']
            query = """
            MATCH (i:Incident {incident_id: $incident_id}), 
                  (a:Asset {asset_unique_id: $asset_unique_id})
            CREATE (i)-[:AFFECTS]->(a)
            """
            self.graph.run(
                query, 
                incident_id=incident['incident_id'], 
                asset_unique_id=asset_unique_id
            )
        
        logger.info("Incident nodes created")
    
    def create_technician_relationships(self):
        """Create relationships between Incidents and Technicians"""
        logger.info("Creating Technician relationships...")
        
        for _, tech in self.technicians_df.iterrows():
            # Create Technician node if it doesn't exist
            query = """
            MERGE (t:Technician {technician_id: $technician_id})
            """
            self.graph.run(query, technician_id=tech['technician_id'])
            
            # Create relationship with Incident
            query = """
            MATCH (i:Incident {incident_id: $incident_id}), (t:Technician {technician_id: $technician_id})
            CREATE (i)-[:RESOLVED_BY]->(t)
            """
            self.graph.run(query, incident_id=tech['incident_id'], technician_id=tech['technician_id'])
        
        logger.info("Technician relationships created")
    
    def create_image_nodes(self):
        """Create Image nodes and relationships"""
        logger.info("Creating Image nodes and relationships...")
        
        for _, image in self.images_df.iterrows():
            image_node = Node(
                "Image",
                image_filename=image['image_filename'],
                caption=image['caption'],
                incident_id=image['incident_id']
            )
            self.graph.create(image_node)
            
            # Create relationship with Incident
            query = """
            MATCH (img:Image {incident_id: $incident_id}), (i:Incident {incident_id: $incident_id})
            CREATE (i)-[:HAS_IMAGE]->(img)
            """
            self.graph.run(query, incident_id=image['incident_id'])
        
        logger.info("Image nodes and relationships created")
    
    def create_related_incident_edges(self):
        """Create 'RELATED_TO' edges between incidents based on shared assets and time proximity"""
        logger.info("Creating 'RELATED_TO' edges between incidents...")
        
        # Convert timestamps to datetime objects
        self.incidents_df['timestamp'] = pd.to_datetime(self.incidents_df['timestamp'])
        
        # Group incidents by asset_id
        asset_groups = self.incidents_df.groupby('asset_id')
        
        edge_count = 0
        for asset_id, group in asset_groups:
            if len(group) <= 1:
                continue
            
            # Sort incidents by timestamp
            sorted_incidents = group.sort_values('timestamp')
            
            # Create edges between incidents that occur within 72 hours of each other
            for i in range(len(sorted_incidents)):
                current_incident = sorted_incidents.iloc[i]
                current_id = current_incident['incident_id']
                current_time = current_incident['timestamp']
                
                for j in range(i+1, len(sorted_incidents)):
                    next_incident = sorted_incidents.iloc[j]
                    next_id = next_incident['incident_id']
                    next_time = next_incident['timestamp']
                    
                    # Calculate time difference in hours
                    time_diff = (next_time - current_time).total_seconds() / 3600
                    
                    # If within 72 hours, create a RELATED_TO edge
                    if time_diff <= 72:
                        query = """
                        MATCH (i1:Incident {incident_id: $id1}), (i2:Incident {incident_id: $id2})
                        CREATE (i1)-[:RELATED_TO {reason: 'same_asset_time_proximity', time_diff_hours: $time_diff}]->(i2)
                        """
                        self.graph.run(query, id1=current_id, id2=next_id, time_diff=time_diff)
                        edge_count += 1
        
        logger.info(f"Created {edge_count} 'RELATED_TO' edges between incidents")
    
    def build_graph(self):
        """Build the complete graph with all nodes and relationships"""
        logger.info("Building Neo4j graph...")
        
        # Load all data
        self.load_data()
        
        # Clear the existing graph
        self.clear_graph()
        
        # Setup constraints
        self.setup_constraints()
        
        # Create nodes and relationships
        self.create_zone_nodes()
        self.create_asset_nodes()
        self.create_incident_nodes()
        self.create_technician_relationships()
        self.create_image_nodes()
        self.create_related_incident_edges()
        
        logger.info("Graph construction complete")

def main():
    """Main function to build the graph"""
    constructor = GraphConstructor()
    constructor.build_graph()

if __name__ == "__main__":
    main() 