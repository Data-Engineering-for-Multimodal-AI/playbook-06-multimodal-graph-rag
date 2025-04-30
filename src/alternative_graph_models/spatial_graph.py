"""
Spatial Integration - Alternative Implementation

This implementation enhances the graph with spatial relationships and geographic analysis,
enabling location-based insights and regional patterns.
"""

import pandas as pd
import logging
from py2neo import Graph, Node, Relationship
import math
import numpy as np

from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger(__name__)

class SpatialGraphConstructor:
    def __init__(self, base_constructor):
        """Initialize with the base graph constructor to extend its functionality"""
        self.base = base_constructor
        self.graph = self.base.graph
        self.zones_df = None
        self.incidents_df = None
    
    def build_graph(self):
        """Build the spatial graph by first creating the base graph, then adding spatial relationships"""
        # Build the base graph first
        self.base.build_graph()
        
        # Generate mock coordinates for zones (in a real system, these would come from real data)
        self.generate_spatial_data()
        
        # Add spatial enrichment
        self.add_spatial_properties()
        self.create_proximity_relationships()
        self.create_regional_clusters()
        
        logger.info("Spatial graph construction complete")
    
    def generate_spatial_data(self):
        """Generate mock coordinate data for zones (in a real system, this would be real geodata)"""
        logger.info("Generating spatial data for zones...")
        
        # Get zones from Neo4j
        result = self.graph.run("MATCH (z:Zone) RETURN z.zone_id AS zone_id").data()
        zones = [record['zone_id'] for record in result]
        
        # Create a mock coordinate system (longitude and latitude)
        # In a real system, these would be actual GPS coordinates
        np.random.seed(42)  # For reproducibility
        
        # Create a dataframe with zone coordinates
        coords = {}
        for i, zone_id in enumerate(zones):
            # Generate coordinates in a grid-like pattern
            row = i // 5
            col = i % 5
            
            # Add some randomness
            lat = 34.0 + (row * 0.5) + np.random.random() * 0.2
            lon = -118.0 + (col * 0.5) + np.random.random() * 0.2
            
            coords[zone_id] = {
                'zone_id': zone_id,
                'latitude': lat,
                'longitude': lon,
                'elevation': 100 + np.random.randint(0, 500)  # Elevation in meters
            }
        
        self.zones_df = pd.DataFrame(coords).T
        logger.info(f"Generated spatial data for {len(self.zones_df)} zones")
    
    def add_spatial_properties(self):
        """Add spatial properties to zone nodes"""
        logger.info("Adding spatial properties to zone nodes...")
        
        # Update zone nodes with spatial properties
        for _, zone in self.zones_df.iterrows():
            query = """
            MATCH (z:Zone {zone_id: $zone_id})
            SET z.latitude = $lat,
                z.longitude = $lon,
                z.elevation = $elev,
                z.location = $location
            """
            self.graph.run(
                query, 
                zone_id=zone['zone_id'], 
                lat=zone['latitude'],
                lon=zone['longitude'],
                elev=zone['elevation'],
                location=f"POINT({zone['longitude']} {zone['latitude']})"
            )
        
        logger.info(f"Added spatial properties to {len(self.zones_df)} zone nodes")
    
    def haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calculate the great circle distance between two points on earth (specified in decimal degrees)"""
        # Convert decimal degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        r = 6371  # Radius of earth in kilometers
        return c * r
    
    def create_proximity_relationships(self):
        """Create proximity relationships between zones based on distance"""
        logger.info("Creating proximity relationships between zones...")
        
        # Create a distance matrix
        zones = self.zones_df.index.tolist()
        proximity_count = 0
        
        for i, zone1 in enumerate(zones):
            z1_lat = self.zones_df.loc[zone1, 'latitude']
            z1_lon = self.zones_df.loc[zone1, 'longitude']
            
            for zone2 in zones[i+1:]:
                z2_lat = self.zones_df.loc[zone2, 'latitude']
                z2_lon = self.zones_df.loc[zone2, 'longitude']
                
                # Calculate distance
                distance = self.haversine_distance(z1_lat, z1_lon, z2_lat, z2_lon)
                
                # If zones are closer than 30km, create a NEAR relationship
                if distance < 30:
                    query = """
                    MATCH (z1:Zone {zone_id: $zone_id1}), (z2:Zone {zone_id: $zone_id2})
                    CREATE (z1)-[:NEAR {distance_km: $distance}]->(z2),
                           (z2)-[:NEAR {distance_km: $distance}]->(z1)
                    """
                    self.graph.run(
                        query,
                        zone_id1=zone1,
                        zone_id2=zone2,
                        distance=round(distance, 2)
                    )
                    proximity_count += 2  # Two directional relationships
        
        logger.info(f"Created {proximity_count} proximity relationships between zones")
    
    def create_regional_clusters(self):
        """Create regional cluster nodes and connect zones to them"""
        logger.info("Creating regional clusters...")
        
        # Define regions (in a real system this could be based on a clustering algorithm)
        # Here we'll use a simple grid-based approach
        regions = {
            "North": [],
            "South": [],
            "East": [],
            "West": [],
            "Central": []
        }
        
        # Determine the center point of all zones
        center_lat = self.zones_df['latitude'].mean()
        center_lon = self.zones_df['longitude'].mean()
        
        # Assign zones to regions
        for zone_id, zone in self.zones_df.iterrows():
            lat = zone['latitude']
            lon = zone['longitude']
            
            if lat > center_lat and lon > center_lon:
                regions["North"].append(zone_id)
            elif lat < center_lat and lon < center_lon:
                regions["South"].append(zone_id)
            elif lat > center_lat and lon < center_lon:
                regions["West"].append(zone_id)
            elif lat < center_lat and lon > center_lon:
                regions["East"].append(zone_id)
            else:
                regions["Central"].append(zone_id)
        
        # Create region nodes and connect zones
        for region_name, zone_ids in regions.items():
            if not zone_ids:
                continue
                
            # Create region node
            region_node = Node(
                "Region", 
                name=region_name,
                zone_count=len(zone_ids)
            )
            self.graph.create(region_node)
            
            # Connect zones to region
            for zone_id in zone_ids:
                query = """
                MATCH (z:Zone {zone_id: $zone_id}), (r:Region {name: $region})
                CREATE (z)-[:IN_REGION]->(r)
                """
                self.graph.run(query, zone_id=zone_id, region=region_name)
        
        logger.info(f"Created {len([r for r, z in regions.items() if z])} regional clusters")
        
        # Create incident heatmap by region
        query = """
        MATCH (i:Incident)-[:AFFECTS]->(:Asset)-[:LOCATED_IN]->(z:Zone)-[:IN_REGION]->(r:Region)
        WITH r.name AS region, COUNT(i) AS incident_count
        CREATE (h:RegionalHeatmap {
            region: region,
            incident_count: incident_count,
            heatmap_id: 'HEATMAP_' + region
        })
        """
        self.graph.run(query)
        
        # Connect heatmaps to regions
        query = """
        MATCH (h:RegionalHeatmap), (r:Region)
        WHERE h.region = r.name
        CREATE (h)-[:MEASURES]->(r)
        """
        self.graph.run(query)
        
        # Count heatmap nodes
        heatmap_count = self.graph.evaluate("MATCH (h:RegionalHeatmap) RETURN count(h)")
        logger.info(f"Created {heatmap_count} regional heatmap nodes")

def main():
    """Main function to build a spatial graph"""
    from src.graph_construction import GraphConstructor
    
    # Create base constructor
    base_constructor = GraphConstructor()
    
    # Create spatial constructor that extends the base
    spatial_constructor = SpatialGraphConstructor(base_constructor)
    
    # Build the enhanced graph
    spatial_constructor.build_graph()

if __name__ == "__main__":
    main() 