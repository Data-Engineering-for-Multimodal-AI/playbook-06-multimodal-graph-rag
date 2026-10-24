import redis
import json
import hashlib
import logging
import time
from typing import Dict, Any, Optional, List, Tuple

from src.config import REDIS_HOST, REDIS_PORT, REDIS_DB, TEXT_TTL, IMAGE_TTL, GRAPH_TTL

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EdgeAwareCache:
    def __init__(self):
        self.redis_client = None
        self.connect_to_redis()
    
    def connect_to_redis(self):
        """Connect to Redis server"""
        try:
            logger.info(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
            self.redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=False  # Keep binary data for storing complex objects
            )
            self.redis_client.ping()  # Test connection
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def generate_cache_key(self, 
                         query: str, 
                         zone_filter: Optional[str] = None,
                         time_range: Optional[Tuple[str, str]] = None,
                         priority_filter: Optional[str] = None,
                         kind: str = "query") -> str:
        """
        Generate a deterministic cache key based on query parameters
        
        Args:
            query: The incident description query
            zone_filter: Optional zone filter
            time_range: Optional time range filter
            priority_filter: Optional priority filter
            kind: Key prefix, one per kind of result ("query", "photos", "resolutions")
            
        Returns:
            A cache key string
        """
        # Create a dictionary of query parameters
        query_params = {
            'query': query,
            'zone_filter': zone_filter,
            'time_range': time_range,
            'priority_filter': priority_filter
        }
        
        # Convert to JSON string and hash
        params_json = json.dumps(query_params, sort_keys=True)
        hash_obj = hashlib.md5(params_json.encode())
        return f"{kind}:{hash_obj.hexdigest()}"
    
    def store_in_cache(self, results: List[Dict[str, Any]], cache_key: str, ttl: Optional[int] = None) -> None:
        """
        Store results in Redis with modality-specific TTLs
        
        Args:
            results: The result list to cache
            cache_key: The cache key
            ttl: Optional TTL for every result, in place of the per-result modality rule
        """
        try:
            # Apply modality-specific TTLs for each result
            max_ttl = ttl or TEXT_TTL
            for i, result in enumerate(results):
                # Store each result individually with its modality-specific TTL
                result_key = f"{cache_key}:result:{i}"
                
                # Check which modalities are present in the result
                has_text = True  # All results have text
                has_image = 'image' in result and result['image'] is not None
                has_graph = ('related_incidents' in result and result['related_incidents']) or \
                            ('zone_details' in result and result['zone_details']) or \
                            ('asset_details' in result and result['asset_details']) or \
                            ('technician' in result and result['technician'])
                
                # Determine TTL based on modalities present
                if ttl:
                    result_ttl = ttl
                elif has_graph:
                    result_ttl = GRAPH_TTL  # Graph data has longest TTL (12 hours)
                elif has_image:
                    result_ttl = IMAGE_TTL  # Image data has medium TTL (6 hours)
                else:
                    result_ttl = TEXT_TTL  # Text-only data has shortest TTL (1 hour)
                
                max_ttl = max(max_ttl, result_ttl)
                
                # Store the result with appropriate TTL
                self.redis_client.set(result_key, json.dumps(result).encode(), ex=result_ttl)
                
                logger.debug(f"Stored result {i} with TTL {result_ttl} seconds")
            
            # Store the number of results and set a master key
            self.redis_client.set(
                f"{cache_key}:count",
                str(len(results)).encode(),
                ex=max_ttl  # Use the longest result TTL for the count
            )
            
            # Store cache timestamp
            self.redis_client.set(
                f"{cache_key}:timestamp",
                str(time.time()).encode(),
                ex=max_ttl  # Use the longest result TTL for the timestamp
            )
            
            logger.info(f"Cached {len(results)} results with key {cache_key}")
            
        except Exception as e:
            logger.error(f"Error storing results in cache: {e}")
    
    def get_from_cache(self, cache_key: str) -> Optional[Tuple[List[Dict[str, Any]], float]]:
        """
        Retrieve results from cache
        
        Args:
            cache_key: The cache key
            
        Returns:
            Tuple of (cached results, cache timestamp) or None if not in cache
        """
        try:
            # Check if we have results for this cache key
            count_key = f"{cache_key}:count"
            if not self.redis_client.exists(count_key):
                logger.info(f"Cache miss for key {cache_key}")
                return None
            
            # Get the number of results
            count = int(self.redis_client.get(count_key).decode())
            
            # Get the timestamp
            timestamp_key = f"{cache_key}:timestamp"
            timestamp = float(self.redis_client.get(timestamp_key).decode())
            
            # Retrieve all results
            results = []
            for i in range(count):
                result_key = f"{cache_key}:result:{i}"
                if self.redis_client.exists(result_key):
                    result_json = self.redis_client.get(result_key)
                    result = json.loads(result_json)
                    results.append(result)
                else:
                    logger.warning(f"Result {i} missing from cache for key {cache_key}")
            
            if len(results) != count:
                # Some results have expired (shorter TTL): treat it as a miss so the caller fetches fresh results
                logger.warning(f"Expected {count} results but found {len(results)} for key {cache_key}")
                return None
            
            logger.info(f"Cache hit for key {cache_key}, retrieved {len(results)} results")
            return results, timestamp
            
        except Exception as e:
            logger.error(f"Error retrieving results from cache: {e}")
            return None
    
    def clear_cache(self) -> None:
        """Clear all cache entries"""
        try:
            self.redis_client.flushdb()
            logger.info("Cache cleared")
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")

def main():
    """Test the edge-aware cache"""
    # Sample test data
    test_data = [
        {
            "incident_id": "INC903",
            "description": "Packet loss observed on Tower T93. Issue reported by monitoring system.",
            "similarity_score": 0.945,
            "zone": "Zone 11",
            "status": "Resolved",
            "image": {
                "filename": "INC903_repeater_missing_panel_zone11.jpeg",
                "caption": "Repeater with missing panel, partially obscured in vegetation of Zone 11."
            },
            "related_incidents": [
                {
                    "incident_id": "INC915",
                    "description": "Port flapping observed on Tower T93. Issue reported by monitoring system.",
                    "priority": "Medium",
                    "status": "Resolved",
                    "reason": "same_asset_time_proximity",
                    "time_diff_hours": 68.5
                }
            ]
        }
    ]
    
    # Test caching
    cache = EdgeAwareCache()
    
    # Generate a cache key
    cache_key = cache.generate_cache_key(
        query="Packet loss on Tower",
        zone_filter="Zone 11"
    )
    
    # Store in cache
    cache.store_in_cache(test_data, cache_key)
    
    # Retrieve from cache
    cached_results, timestamp = cache.get_from_cache(cache_key)
    
    if cached_results:
        print("Cache hit!")
        print(f"Retrieved at: {timestamp}")
        print(f"Result count: {len(cached_results)}")
        print(f"Sample result: {cached_results[0]['incident_id']}")
    else:
        print("Cache miss!")

if __name__ == "__main__":
    main() 