import os
import numpy as np
import pandas as pd
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from PIL import Image
import torch
from transformers import CLIPProcessor, CLIPModel
import logging

from src.config import DATA_DIR, EMBEDDINGS_DIR

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EmbeddingPipeline:
    def __init__(self):
        self.text_model = None
        self.image_model = None
        self.image_processor = None
        
    def load_text_model(self):
        """Load BERT model for text embeddings"""
        logger.info("Loading text embedding model...")
        self.text_model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("Text embedding model loaded.")
        
    def load_image_model(self):
        """Load CLIP model for image embeddings"""
        logger.info("Loading image embedding model...")
        model_name = "openai/clip-vit-base-patch32"
        self.image_model = CLIPModel.from_pretrained(model_name)
        self.image_processor = CLIPProcessor.from_pretrained(model_name)
        logger.info("Image embedding model loaded.")
    
    def generate_text_embeddings(self):
        """Generate embeddings for incident descriptions"""
        if self.text_model is None:
            self.load_text_model()
            
        # Load incidents data
        incidents_path = os.path.join(DATA_DIR, "incidents.csv")
        incidents_df = pd.read_csv(incidents_path)
        
        # Generate embeddings for incident descriptions
        logger.info(f"Generating embeddings for {len(incidents_df)} incident descriptions...")
        descriptions = incidents_df['description'].tolist()
        incident_ids = incidents_df['incident_id'].tolist()
        
        # Generate embeddings in batches
        embeddings = self.text_model.encode(descriptions, show_progress_bar=True)
        
        # Save embeddings and corresponding incident IDs
        text_embeddings_path = os.path.join(EMBEDDINGS_DIR, "text_embeddings.npy")
        text_incident_ids_path = os.path.join(EMBEDDINGS_DIR, "text_incident_ids.npy")
        
        np.save(text_embeddings_path, embeddings)
        np.save(text_incident_ids_path, incident_ids)
        
        logger.info(f"Text embeddings saved to {text_embeddings_path}")
        logger.info(f"Text incident IDs saved to {text_incident_ids_path}")
        
        return embeddings, incident_ids
    
    def generate_image_embeddings(self):
        """Generate CLIP embeddings for drone images"""
        if self.image_model is None or self.image_processor is None:
            self.load_image_model()
            
        # Load images data
        images_path = os.path.join(DATA_DIR, "images.csv")
        images_df = pd.read_csv(images_path)
        
        # Initialize lists to store embeddings and corresponding incident IDs
        all_embeddings = []
        incident_ids = []
        
        # Generate embeddings for each image
        logger.info(f"Generating embeddings for {len(images_df)} drone images...")
        for _, row in tqdm(images_df.iterrows(), total=len(images_df)):
            incident_id = row['incident_id']
            image_filename = row['image_filename']
            
            # Load and preprocess image
            image_path = os.path.join(DATA_DIR, "drone-images", image_filename)
            try:
                image = Image.open(image_path).convert('RGB')
                inputs = self.image_processor(images=image, return_tensors="pt")
                
                # Generate image embedding
                with torch.no_grad():
                    outputs = self.image_model.get_image_features(**inputs)
                    embedding = outputs.detach().cpu().numpy()[0]
                
                all_embeddings.append(embedding)
                incident_ids.append(incident_id)
            except Exception as e:
                logger.error(f"Error processing image {image_filename}: {e}")
        
        # Convert list of embeddings to numpy array
        embeddings_array = np.array(all_embeddings)
        
        # Save embeddings and corresponding incident IDs
        image_embeddings_path = os.path.join(EMBEDDINGS_DIR, "image_embeddings.npy")
        image_incident_ids_path = os.path.join(EMBEDDINGS_DIR, "image_incident_ids.npy")
        
        np.save(image_embeddings_path, embeddings_array)
        np.save(image_incident_ids_path, incident_ids)
        
        logger.info(f"Image embeddings saved to {image_embeddings_path}")
        logger.info(f"Image incident IDs saved to {image_incident_ids_path}")
        
        return embeddings_array, incident_ids

def main():
    """Main function to generate all embeddings"""
    pipeline = EmbeddingPipeline()
    
    # Generate text embeddings
    pipeline.generate_text_embeddings()
    
    # Generate image embeddings
    pipeline.generate_image_embeddings()
    
if __name__ == "__main__":
    main() 