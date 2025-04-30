"""
Resolution Patterns - Alternative Implementation

This implementation captures solution knowledge and resolution strategies,
enabling the system to recommend proven fix approaches for similar incidents.
"""

import pandas as pd
import logging
from py2neo import Graph, Node, Relationship
from collections import Counter
import re

from src.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger(__name__)

class ResolutionPatternsGraphConstructor:
    def __init__(self, base_constructor):
        """Initialize with the base graph constructor to extend its functionality"""
        self.base = base_constructor
        self.graph = self.base.graph
        self.incidents_df = None
        self.technicians_df = None
    
    def build_graph(self):
        """Build the resolution patterns graph by first creating the base graph, then adding resolution knowledge"""
        # Build the base graph first
        self.base.build_graph()
        
        # Load data again for resolution analysis
        self.incidents_df = self.base.incidents_df
        
        # Load technicians data if available (assuming it's in the base constructor)
        try:
            self.technicians_df = self.base.technicians_df
        except AttributeError:
            # Extract technician info from incidents
            techs = self.graph.run("MATCH (t:Technician) RETURN t.technician_id, t.name, t.expertise").data()
            self.technicians_df = pd.DataFrame(techs)
        
        # Add resolution pattern structures
        self.extract_resolution_steps()
        self.create_resolution_templates()
        self.link_technician_expertise()
        self.create_resolution_effectiveness()
        
        logger.info("Resolution patterns graph construction complete")
    
    def extract_resolution_steps(self):
        """Extract resolution steps from incident descriptions and resolution notes"""
        logger.info("Extracting resolution steps from incidents...")
        
        # Extract resolution information from the graph
        result = self.graph.run("""
        MATCH (i:Incident)-[:RESOLVED_BY]->(t:Technician)
        RETURN i.incident_id, i.description, i.resolution, t.technician_id, i.asset_type
        """).data()
        
        # Process each incident
        step_count = 0
        for record in result:
            # Skip if no resolution text
            if not record.get('i.resolution'):
                continue
            
            # Extract steps using simple heuristics (in a real system, this would use NLP)
            # Here we're naively splitting by periods and numbering
            resolution_text = record['i.resolution']
            
            # Different ways steps might be separated in text
            steps = []
            
            # Try to find numbered steps
            numbered_steps = re.findall(r'\d+\.\s+([^.!?]+[.!?])', resolution_text)
            if numbered_steps:
                steps = numbered_steps
            else:
                # Otherwise split by sentences
                steps = [s.strip() for s in re.split(r'[.!?]', resolution_text) if s.strip()]
            
            # Create step nodes
            for i, step_text in enumerate(steps):
                # Skip very short steps
                if len(step_text) < 10:
                    continue
                    
                step_node = Node(
                    "ResolutionStep",
                    text=step_text,
                    step_number=i+1,
                    step_id=f"{record['i.incident_id']}_STEP_{i+1}",
                    asset_type=record['i.asset_type']
                )
                self.graph.create(step_node)
                
                # Connect step to incident
                query = """
                MATCH (i:Incident {incident_id: $incident_id}), 
                      (s:ResolutionStep {step_id: $step_id})
                CREATE (i)-[:HAS_STEP {order: $order}]->(s)
                """
                self.graph.run(
                    query,
                    incident_id=record['i.incident_id'],
                    step_id=f"{record['i.incident_id']}_STEP_{i+1}",
                    order=i+1
                )
                
                # Connect step to technician
                query = """
                MATCH (t:Technician {technician_id: $tech_id}), 
                      (s:ResolutionStep {step_id: $step_id})
                CREATE (s)-[:CREATED_BY]->(t)
                """
                self.graph.run(
                    query,
                    tech_id=record['t.technician_id'],
                    step_id=f"{record['i.incident_id']}_STEP_{i+1}"
                )
                
                step_count += 1
        
        logger.info(f"Extracted {step_count} resolution steps from incidents")
    
    def create_resolution_templates(self):
        """Create resolution templates by grouping similar resolution approaches"""
        logger.info("Creating resolution templates...")
        
        # Group resolution steps by asset type and look for patterns
        query = """
        MATCH (s:ResolutionStep)
        WITH s.asset_type AS asset_type, COLLECT(s) AS steps
        WHERE size(steps) > 1
        RETURN asset_type, steps
        """
        
        result = self.graph.run(query).data()
        
        template_count = 0
        for record in result:
            asset_type = record['asset_type']
            
            # In a real system, this would use NLP for clustering similar steps
            # Here we'll use a simple approach - creating one template per asset type
            template_node = Node(
                "ResolutionTemplate",
                asset_type=asset_type,
                template_id=f"TEMPLATE_{asset_type}",
                name=f"{asset_type} Resolution Template",
                step_count=len(record['steps'])
            )
            self.graph.create(template_node)
            
            # Connect template to steps
            for step in record['steps']:
                query = """
                MATCH (s:ResolutionStep {step_id: $step_id}),
                      (t:ResolutionTemplate {template_id: $template_id})
                CREATE (t)-[:INCLUDES_STEP]->(s)
                """
                self.graph.run(
                    query,
                    step_id=step['step_id'],
                    template_id=f"TEMPLATE_{asset_type}"
                )
            
            template_count += 1
        
        logger.info(f"Created {template_count} resolution templates")
        
        # Connect resolution templates to incident types
        query = """
        MATCH (i:Incident)-[:HAS_STEP]->(s:ResolutionStep)<-[:INCLUDES_STEP]-(t:ResolutionTemplate)
        WHERE i.asset_type = t.asset_type
        WITH t, i, COUNT(DISTINCT s) AS overlap
        WHERE overlap > 0
        CREATE (i)-[:FOLLOWS_TEMPLATE {confidence: toFloat(overlap) / t.step_count}]->(t)
        """
        self.graph.run(query)
        
        # Count incident-template relationships
        template_rel_count = self.graph.evaluate("""
        MATCH ()-[r:FOLLOWS_TEMPLATE]->() 
        RETURN count(r)
        """)
        logger.info(f"Created {template_rel_count} incident-template relationships")
    
    def link_technician_expertise(self):
        """Create expertise relationships between technicians and resolution patterns"""
        logger.info("Linking technician expertise to resolution patterns...")
        
        # Find technicians who have successfully resolved specific types of incidents
        query = """
        MATCH (t:Technician)<-[:RESOLVED_BY]-(i:Incident)-[:FOLLOWS_TEMPLATE]->(rt:ResolutionTemplate)
        WITH t, rt, COUNT(i) AS resolution_count
        WHERE resolution_count > 0
        CREATE (t)-[:HAS_EXPERTISE {
            asset_type: rt.asset_type,
            resolution_count: resolution_count,
            expertise_level: CASE 
                WHEN resolution_count > 5 THEN 'Expert'
                WHEN resolution_count > 2 THEN 'Intermediate'
                ELSE 'Beginner'
            END
        }]->(rt)
        """
        self.graph.run(query)
        
        # Count expertise relationships
        expertise_count = self.graph.evaluate("""
        MATCH ()-[r:HAS_EXPERTISE]->() 
        RETURN count(r)
        """)
        logger.info(f"Created {expertise_count} technician expertise relationships")
    
    def create_resolution_effectiveness(self):
        """Analyze and create resolution effectiveness metrics"""
        logger.info("Creating resolution effectiveness metrics...")
        
        # Calculate time to resolution for each template
        query = """
        MATCH (i:Incident)-[:FOLLOWS_TEMPLATE]->(rt:ResolutionTemplate)
        WHERE i.duration_minutes IS NOT NULL
        WITH rt, AVG(i.duration_minutes) AS avg_resolution_time
        SET rt.avg_resolution_time = avg_resolution_time
        """
        self.graph.run(query)
        
        # Create effectiveness scoring for templates
        query = """
        MATCH (rt:ResolutionTemplate)
        OPTIONAL MATCH (i:Incident)-[ft:FOLLOWS_TEMPLATE]->(rt)
        WITH rt, 
             COUNT(i) AS usage_count,
             AVG(ft.confidence) AS avg_confidence,
             rt.avg_resolution_time AS avg_time
        WHERE usage_count > 0
        SET rt.effectiveness_score = (usage_count * avg_confidence) / 
                                    (CASE WHEN avg_time > 0 THEN sqrt(avg_time) ELSE 1 END)
        """
        self.graph.run(query)
        
        # Create RecommendedApproach nodes for high-effectiveness templates
        query = """
        MATCH (rt:ResolutionTemplate)
        WHERE rt.effectiveness_score > 1.0
        CREATE (ra:RecommendedApproach {
            asset_type: rt.asset_type,
            approach_id: 'RECOMMENDED_' + rt.asset_type,
            name: rt.asset_type + ' Recommended Approach',
            effectiveness_score: rt.effectiveness_score,
            avg_resolution_time: rt.avg_resolution_time
        })
        """
        self.graph.run(query)
        
        # Connect recommended approaches to templates
        query = """
        MATCH (ra:RecommendedApproach), (rt:ResolutionTemplate)
        WHERE ra.asset_type = rt.asset_type
        CREATE (ra)-[:BASED_ON]->(rt)
        """
        self.graph.run(query)
        
        # Count recommended approaches
        rec_count = self.graph.evaluate("MATCH (ra:RecommendedApproach) RETURN count(ra)")
        logger.info(f"Created {rec_count} recommended approach nodes")
        
        # Create failure prediction nodes (failures likely to occur after a specific incident)
        query = """
        MATCH (i1:Incident)-[:AFFECTS]->(a:Asset)<-[:AFFECTS]-(i2:Incident)
        WHERE i1.timestamp < i2.timestamp
        WITH a, i1, i2, duration.inDays(datetime(i1.timestamp), datetime(i2.timestamp)).days AS days_between
        WHERE days_between < 30
        WITH a.asset_type AS asset_type, i1.asset_type AS failure_type, COUNT(DISTINCT i2) AS subsequent_failures
        WHERE subsequent_failures > 1
        CREATE (fp:FailurePrediction {
            asset_type: asset_type,
            initial_failure: failure_type,
            prediction_id: 'PREDICT_' + asset_type + '_AFTER_' + failure_type,
            subsequent_failure_count: subsequent_failures,
            likelihood: CASE 
                WHEN subsequent_failures > 5 THEN 'High'
                WHEN subsequent_failures > 2 THEN 'Medium'
                ELSE 'Low'
            END
        })
        """
        self.graph.run(query)
        
        # Count prediction nodes
        pred_count = self.graph.evaluate("MATCH (fp:FailurePrediction) RETURN count(fp)")
        logger.info(f"Created {pred_count} failure prediction nodes")

def main():
    """Main function to build a resolution patterns graph"""
    from src.graph_construction import GraphConstructor
    
    # Create base constructor
    base_constructor = GraphConstructor()
    
    # Create resolution patterns constructor that extends the base
    resolution_constructor = ResolutionPatternsGraphConstructor(base_constructor)
    
    # Build the enhanced graph
    resolution_constructor.build_graph()

if __name__ == "__main__":
    main() 