"""Search the incident graph by hand, through the cache (make search, make photos).

    make search Q="fiber cut after the storm"                  # incidents, any zone
    make search Q="tower power failure" ZONE="Zone 12" PRIORITY=High
    make photos Q="tower overgrown by trees"                   # drone photos from a description
    make photos IMAGE=data/drone-images/INC909_tower_muddy_base_flooded.jpeg

Needs Neo4j and Redis running and the graph built (make run, or make load DIR=...).
Run the same search twice: the second answer comes from Redis.
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--query", help="a description of the incident (or of the photo, with --photos)")
    parser.add_argument("--image", help="a photo to find similar drone photos for")
    parser.add_argument("--photos", action="store_true", help="search drone photos instead of incidents")
    parser.add_argument("--zone", help='only this zone, for example "Zone 11"')
    parser.add_argument("--priority", help="only this priority: High, Medium or Low")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if not args.query and not args.image:
        parser.error("give --query or --image")

    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    logging.disable(logging.WARNING)  # keep the answer readable; errors still raise
    from transformers.utils import logging as hf_logging
    hf_logging.disable_progress_bar()
    from src.retrieval_system import RetrievalSystem
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)  # no progress bar per query
    system = RetrievalSystem()

    if args.photos or args.image:
        from PIL import Image
        query = Image.open(args.image) if args.image else args.query
        response = system.search_photos(query, top_k=args.top_k)
        print(f"Drone photos matching {args.image or repr(args.query)}:")
        for p in response["results"]:
            print(f"  {p['similarity_score']:.4f}  {p['filename']}  ({p['incident_id']}, {p['status']})")
    else:
        response = system.retrieve(args.query, top_k=args.top_k, zone_filter=args.zone,
                                   priority_filter=args.priority)
        filters = ", ".join(f"{k} {v}" for k, v in (("zone", args.zone), ("priority", args.priority)) if v)
        print(f"Incidents like {args.query!r}{' (' + filters + ')' if filters else ''}:")
        for r in response["results"]:
            extra = []
            if r.get("image"):
                extra.append(f"photo {r['image']['filename']}")
            if r.get("technician"):
                extra.append(f"fixed by {r['technician']['technician_id']}")
            if r.get("related_incidents"):
                extra.append("related " + ", ".join(x["incident_id"] for x in r["related_incidents"]))
            print(f"  {r['similarity_score']:.4f}  {r['incident_id']}  {r['zone']:<8} {r['priority']:<6} "
                  f"{r['status']:<8} {r['description']}")
            if extra:
                print(f"          {'; '.join(extra)}")
        if not response["results"]:
            print("  no incidents match these filters")
    perf = response["performance"]
    print(f"{'Cache hit' if perf['cache_hit'] else 'Cache miss'}, {perf['retrieval_time_ms']:.0f} ms")


if __name__ == "__main__":
    main()
