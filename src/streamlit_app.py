import streamlit as st
import pandas as pd
import os
import time
from datetime import datetime, timedelta
from PIL import Image
import matplotlib.pyplot as plt
import networkx as nx
from io import BytesIO

from src.retrieval_system import RetrievalSystem
from src.config import DATA_DIR

# Initialize the retrieval system
@st.cache_resource
def get_retrieval_system():
    return RetrievalSystem()

def load_image(image_filename):
    """Load an image from the data directory"""
    try:
        image_path = os.path.join(DATA_DIR, "drone-images", image_filename)
        return Image.open(image_path)
    except Exception as e:
        st.error(f"Error loading image: {e}")
        return None

def visualize_graph(incident_id, related_incidents):
    """Create a graph visualization for an incident and its related incidents"""
    G = nx.DiGraph()
    
    # Add the main incident node
    G.add_node(incident_id, color='red', size=1500)
    
    # Add related incident nodes and edges
    for related in related_incidents:
        related_id = related['incident_id']
        G.add_node(related_id, color='blue', size=1000)
        G.add_edge(incident_id, related_id, 
                   weight=1, 
                   label=f"{related['reason']}\n{related['time_diff_hours']:.1f}h")
    
    # Create the figure and draw the graph
    plt.figure(figsize=(10, 7))
    
    # Get node positions using spring layout
    pos = nx.spring_layout(G, seed=42)
    
    # Get node colors and sizes
    node_colors = [data['color'] for _, data in G.nodes(data=True)]
    node_sizes = [data['size'] for _, data in G.nodes(data=True)]
    
    # Draw nodes and edges
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes, alpha=0.8)
    nx.draw_networkx_edges(G, pos, width=2, alpha=0.5, arrowsize=20)
    nx.draw_networkx_labels(G, pos, font_size=12, font_weight='bold')
    
    # Draw edge labels
    edge_labels = {(u, v): d['label'] for u, v, d in G.edges(data=True)}
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=10)
    
    plt.title(f"Incident Graph: {incident_id}", fontsize=16)
    plt.axis('off')
    
    # Convert plot to image
    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches='tight')
    plt.close()
    buf.seek(0)
    
    return Image.open(buf)

def show_photos(photos, skip_filename=None):
    """Drone photos with their incidents, three to a row"""
    photos = [p for p in photos if p['filename'] != skip_filename]
    for column, photo in zip(st.columns(3), photos):
        with column:
            image = load_image(photo['filename'])
            if image:
                st.image(image, caption=photo['caption'])
            st.markdown(f"**{photo['incident_id']}** ({photo['status']}), similarity {photo['similarity_score']:.4f}")
            st.markdown(photo['description'])
            if photo['resolution_summary']:
                st.markdown(f"**Fix:** {photo['resolution_summary']}")

def photo_search(use_cache):
    """Find incidents whose drone photos look like a sample photo or an uploaded one"""
    sample_files = sorted(os.listdir(os.path.join(DATA_DIR, "drone-images")))
    uploaded = st.file_uploader("Upload a drone photo", type=["jpg", "jpeg", "png"])
    sample = st.selectbox("Or pick a sample photo:", sample_files)
    if uploaded is not None:
        photo, skip = Image.open(uploaded), None
    else:
        photo, skip = load_image(sample), sample
    st.image(photo, caption="Query photo", width=300)
    if st.button("Find similar photos"):
        with st.spinner("Searching..."):
            # One extra result, since a sample photo finds itself first
            result = get_retrieval_system().search_photos(photo, top_k=4, use_cache=use_cache)
        st.metric("Retrieval Time", f"{result['performance']['retrieval_time_ms']} ms")
        show_photos(result['results'][:4 if skip else 3], skip_filename=skip)

def main():
    st.title("Graph-Augmented Retrieval")
    
    # Initialize session state for cache toggle
    if 'use_cache' not in st.session_state:
        st.session_state.use_cache = True
    
    # Sidebar for cache control only
    st.sidebar.header("Cache Settings")
    use_cache = st.sidebar.checkbox("Use Cache", value=st.session_state.use_cache)
    st.session_state.use_cache = use_cache
    
    if not use_cache:
        st.sidebar.warning("Cache is disabled. Queries will be slower but always fresh.")
    
    # Clear cache button
    if st.sidebar.button("Clear Cache"):
        retrieval_system = get_retrieval_system()
        retrieval_system.cache.clear_cache()
        st.sidebar.success("Cache cleared successfully!")
    
    tab_incidents, tab_photos = st.tabs(["Search incidents", "Search by photo"])
    
    with tab_incidents:
        # Main query interface
        query = st.text_input("Enter your query:", 
                             placeholder="e.g., Tower packet loss in forest area")
    
        top_k = st.slider("Number of results:", min_value=1, max_value=10, value=3)
    
        search_button = st.button("Search")
    
        # Display results
        if search_button and query:
            with st.spinner("Searching..."):
                retrieval_system = get_retrieval_system()
            
                # Perform retrieval
                result = retrieval_system.retrieve(
                    query=query,
                    top_k=top_k,
                    zone_filter=None,
                    priority_filter=None,
                    time_range=None,
                    use_cache=use_cache
                )
            
                # Display performance metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Retrieval Time", f"{result['performance']['retrieval_time_ms']} ms")
                with col2:
                    st.metric("Cache Hit", "Yes" if result['performance']['cache_hit'] else "No")
                with col3:
                    if result['performance']['cache_hit']:
                        st.metric("Cache Age", f"{result['performance']['cache_age_seconds']} s")
                    else:
                        st.metric("Results", len(result['results']))
            
                # Display results
                if result['results']:
                    st.subheader(f"Found {len(result['results'])} results:")
                
                    for i, res in enumerate(result['results']):
                        with st.expander(f"Result {i+1}: {res['incident_id']} - {res['description'][:80]}...", expanded=i==0):
                            # Metadata section
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.markdown(f"**Similarity:** {res['similarity_score']:.4f}")
                            with col2:
                                st.markdown(f"**Priority:** {res['priority']}")
                            with col3:
                                st.markdown(f"**Status:** {res['status']}")
                        
                            st.markdown(f"**Description:**\n{res['description']}")
                        
                            # Display asset and zone details
                            if 'asset_details' in res and res['asset_details']:
                                st.markdown(f"**Asset:** {res['asset_details']['asset_name']} ({res['asset_details']['asset_type']})")
                        
                            if 'zone_details' in res and res['zone_details']:
                                st.markdown(f"**Zone:** {res['zone_details']['zone_id']} ({res['zone_details']['region']})")
                                st.markdown(f"**Supervisor:** {res['zone_details']['supervisor']}")
                        
                            # Display technician info
                            if 'technician' in res and res['technician']:
                                st.markdown(f"**Resolved by:** {res['technician']['technician_id']}")
                        
                            # Display image - moved up for visibility
                            if 'image' in res and res['image']:
                                st.subheader("Drone Inspection Image")
                                image = load_image(res['image']['filename'])
                                if image:
                                    st.image(image, caption=res['image']['caption'])
                                st.markdown(f"**Caption:** {res['image']['caption']}")
                        
                            # Display related incidents
                            if 'related_incidents' in res and res['related_incidents']:
                                st.subheader(f"Related Incidents ({len(res['related_incidents'])})")
                            
                                # Create a graph visualization
                                graph_image = visualize_graph(res['incident_id'], res['related_incidents'])
                                st.image(graph_image, caption=f"Graph visualization for {res['incident_id']}")
                            
                                # Show related incidents table
                                related_df = pd.DataFrame(res['related_incidents'])
                                st.dataframe(related_df)
                
                    # How the nearest resolved incidents were fixed (graph: RESOLVED_BY)
                    st.subheader("How similar resolved incidents were fixed")
                    resolutions = retrieval_system.similar_resolutions(query, use_cache=use_cache)['results']
                    if resolutions:
                        st.dataframe(pd.DataFrame(resolutions), hide_index=True)
                    else:
                        st.info("No resolved incidents to compare with.")
                    
                    # Drone photos for the same description (CLIP text-to-image search)
                    st.subheader("Drone photos matching the query")
                    show_photos(retrieval_system.search_photos(query, top_k=3, use_cache=use_cache)['results'])
                else:
                    st.warning("No results found. Try a different query.")
    
    with tab_photos:
        photo_search(use_cache)

if __name__ == "__main__":
    main() 