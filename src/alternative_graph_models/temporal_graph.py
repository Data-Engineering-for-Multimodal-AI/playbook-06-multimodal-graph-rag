"""
Temporal Graph Model - Alternative Implementation

This implementation enhances the base graph with temporal relationships,
creating sequential patterns between incidents.
"""

import pandas as pd
import logging
from py2neo import Graph, Node, Relationship
from datetime import datetime

from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger(__name__)

class TemporalGraphConstructor:
    def __init__(self, base_constructor):
        """Initialize with the base graph constructor to extend its functionality"""
        self.base = base_constructor
        self.graph = self.base.graph
        self.incidents_df = None
    
    def build_graph(self):
        """Build the temporal graph by first creating the base graph, then adding temporal edges"""
        # Build the base graph first
        self.base.build_graph()
        
        # Load incident data again for temporal processing
        self.incidents_df = self.base.incidents_df
        
        # Add temporal edges
        self.create_temporal_edges()
        self.create_incident_patterns()
        
        logger.info("Temporal graph construction complete")
    
    def create_temporal_edges(self):
        """Create temporal edges based on incident sequences and patterns"""
        logger.info("Creating temporal edges between incidents...")
        
        # Group incidents by zone
        edge_count = 0
        for zone_id, group in self.incidents_df.groupby('zone'):
            # Sort by timestamp
            sorted_incidents = group.sort_values('timestamp')
            
            # Create sequential edges
            for i in range(len(sorted_incidents) - 1):
                current = sorted_incidents.iloc[i]['incident_id']
                next_inc = sorted_incidents.iloc[i+1]['incident_id']
                
                # Calculate time delta
                current_time = pd.to_datetime(sorted_incidents.iloc[i]['timestamp'])
                next_time = pd.to_datetime(sorted_incidents.iloc[i+1]['timestamp'])
                time_diff = (next_time - current_time).total_seconds() / 3600
                         
                # Create FOLLOWED_BY relationship
                query = """
                MATCH (i1:Incident {incident_id: $id1}), (i2:Incident {incident_id: $id2})
                CREATE (i1)-[:FOLLOWED_BY {zone: $zone, time_diff_hours: $time_diff}]->(i2)
                """
                self.graph.run(query, id1=current, id2=next_inc, zone=zone_id, time_diff=time_diff)
                edge_count += 1
        
        logger.info(f"Created {edge_count} temporal 'FOLLOWED_BY' edges between incidents")
    
    def create_incident_patterns(self):
        """Create pattern nodes connecting recurring incident types"""
        logger.info("Creating incident pattern nodes...")
        
        # Create pattern nodes for recurring issues
        query = """
        MATCH (i1:Incident)-[:AFFECTS]->(a:Asset)<-[:AFFECTS]-(i2:Incident)
        WHERE i1.asset_type = i2.asset_type AND i1.incident_id <> i2.incident_id
        WITH a.asset_type AS asset_type, 
             COLLECT(DISTINCT i1.description) AS descriptions, 
             COUNT(DISTINCT i1) AS incident_count
        WHERE incident_count > 1
        CREATE (p:IncidentPattern {
            asset_type: asset_type,
            pattern_id: 'PATTERN_' + asset_type,
            incident_count: incident_count,
            description: 'Recurring incidents on ' + asset_type + ' assets'
        })
        """
        self.graph.run(query)
        
        # Connect incidents to patterns
        query = """
        MATCH (i:Incident), (p:IncidentPattern)
        WHERE i.asset_type = p.asset_type
        CREATE (i)-[:PART_OF_PATTERN]->(p)
        """
        self.graph.run(query)
        
        # Count the patterns created
        pattern_count = self.graph.evaluate("MATCH (p:IncidentPattern) RETURN count(p)")
        logger.info(f"Created {pattern_count} incident pattern nodes")

def main():
    """Main function to build a temporal graph"""
    from src.graph_construction import GraphConstructor
    
    # Create base constructor
    base_constructor = GraphConstructor()
    
    # Create temporal constructor that extends the base
    temporal_constructor = TemporalGraphConstructor(base_constructor)
    
    # Build the enhanced graph
    temporal_constructor.build_graph()

if __name__ == "__main__":
    main() 