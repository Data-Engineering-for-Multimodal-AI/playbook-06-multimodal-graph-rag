import time
import hashlib
import logging
from typing import Callable, Dict, Any, List, Optional, Tuple, Union

from PIL import Image

from src.hybrid_retrieval import HybridRetriever
from src.edge_cache import EdgeAwareCache
from src.config import TOP_K, TEXT_TTL, IMAGE_TTL

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RetrievalSystem:
    def __init__(self):
        """Initialize the retrieval system with hybrid retriever and edge-aware cache"""
        self.retriever = HybridRetriever()
        self.cache = EdgeAwareCache()
    
    def retrieve(self, 
                query: str, 
                top_k: int = TOP_K, 
                zone_filter: Optional[str] = None,
                time_range: Optional[Tuple[str, str]] = None,
                priority_filter: Optional[str] = None,
                use_cache: bool = True) -> Dict[str, Any]:
        """
        Main retrieval function with caching
        
        Args:
            query: The incident description query
            top_k: Number of top results to return
            zone_filter: Optional filter for specific zone
            time_range: Optional time range filter
            priority_filter: Optional priority filter
            use_cache: Whether to use the cache (default: True)
            
        Returns:
            Dictionary containing results, metadata, and performance information
        """
        start_time = time.time()
        cache_hit = False
        cache_age = None
        results = None
        
        # Generate cache key
        cache_key = self.cache.generate_cache_key(
            query=query,
            zone_filter=zone_filter,
            time_range=time_range,
            priority_filter=priority_filter
        )
        
        # Try to get from cache if enabled
        if use_cache:
            cache_result = self.cache.get_from_cache(cache_key)
            if cache_result:
                results, cache_timestamp = cache_result
                cache_hit = True
                cache_age = time.time() - cache_timestamp
                logger.info(f"Cache hit! Age: {cache_age:.2f} seconds")
        
        # If cache miss or cache disabled, perform retrieval
        if results is None:
            logger.info("Cache miss or cache disabled, performing full retrieval...")
            results = self.retriever.retrieve(
                query=query,
                top_k=top_k,
                zone_filter=zone_filter,
                time_range=time_range,
                priority_filter=priority_filter
            )
            
            # Store in cache if retrieval was successful
            if results and use_cache:
                self.cache.store_in_cache(results, cache_key)
        
        end_time = time.time()
        retrieval_time = end_time - start_time
        
        # Create response with results and metadata
        response = {
            'results': results,
            'metadata': {
                'query': query,
                'zone_filter': zone_filter,
                'time_range': time_range,
                'priority_filter': priority_filter,
                'top_k': top_k,
                'result_count': len(results) if results else 0,
            },
            'performance': {
                'retrieval_time_ms': round(retrieval_time * 1000, 2),
                'cache_hit': cache_hit,
                'cache_age_seconds': round(cache_age, 2) if cache_age else None
            }
        }
        
        return response

    def _cached(self, kind: str, key: str, ttl: int, compute: Callable[[], List[Dict[str, Any]]],
                use_cache: bool) -> Dict[str, Any]:
        """Look up `kind` results in the cache, or compute and store them with the given TTL"""
        start_time = time.time()
        cache_key = self.cache.generate_cache_key(query=key, kind=kind)
        cached = self.cache.get_from_cache(cache_key) if use_cache else None
        results = cached[0] if cached else compute()
        if results and use_cache and not cached:
            self.cache.store_in_cache(results, cache_key, ttl=ttl)
        return {
            'results': results,
            'performance': {
                'retrieval_time_ms': round((time.time() - start_time) * 1000, 2),
                'cache_hit': cached is not None,
            }
        }
    
    def search_photos(self, query: Union[str, Image.Image], top_k: int = 3, use_cache: bool = True) -> Dict[str, Any]:
        """Drone photos matching a description or a photo, cached with the image TTL"""
        if isinstance(query, str):
            key = f"text:{query}:{top_k}"
        else:
            key = f"image:{hashlib.md5(query.convert('RGB').tobytes()).hexdigest()}:{top_k}"
        return self._cached("photos", key, IMAGE_TTL,
                            lambda: self.retriever.search_images(query, top_k=top_k), use_cache)
    
    def similar_resolutions(self, query: str, use_cache: bool = True) -> Dict[str, Any]:
        """How the nearest resolved incidents were fixed, cached with the text TTL"""
        return self._cached("resolutions", query, TEXT_TTL,
                            lambda: self.retriever.similar_resolutions(query), use_cache)

def main():
    """Test the retrieval system"""
    system = RetrievalSystem()
    
    # Example query
    query = "Tower packet loss"
    
    # First query (cache miss)
    logger.info("Performing first query (expected cache miss)...")
    result1 = system.retrieve(
        query=query,
        top_k=3,
        zone_filter="Zone 11"
    )
    
    print(f"Query: {query}")
    print(f"Cache hit: {result1['performance']['cache_hit']}")
    print(f"Retrieval time: {result1['performance']['retrieval_time_ms']} ms")
    print(f"Results: {len(result1['results'])}")
    
    # Second query (should be cache hit)
    logger.info("\nPerforming second query (expected cache hit)...")
    result2 = system.retrieve(
        query=query,
        top_k=3,
        zone_filter="Zone 11"
    )
    
    print(f"Query: {query}")
    print(f"Cache hit: {result2['performance']['cache_hit']}")
    print(f"Cache age: {result2['performance']['cache_age_seconds']} seconds")
    print(f"Retrieval time: {result2['performance']['retrieval_time_ms']} ms")
    print(f"Results: {len(result2['results'])}")
    
    # Show a sample result
    if result2['results']:
        sample = result2['results'][0]
        print(f"\nSample result:")
        print(f"Incident ID: {sample['incident_id']}")
        print(f"Description: {sample['description']}")
        print(f"Similarity Score: {sample['similarity_score']:.4f}")
        
        if sample['image']:
            print(f"Image: {sample['image']['filename']}")
        
        if sample['related_incidents']:
            print(f"Related incidents: {len(sample['related_incidents'])}")

if __name__ == "__main__":
    main() 