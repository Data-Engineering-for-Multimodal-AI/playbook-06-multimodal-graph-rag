# Sample data

The book's author, Vasundra Srinivasan, created everything in this folder: the drone inspection images and the synthetic incident, asset, zone, technician and log records. The incidents, assets, towers, zones, supervisors ("Alice J.", "Bob K.", "Chandra M.") and technicians are fictional. Like the code, the data is released under the MIT License (see [LICENSE](../LICENSE)).

| File | What it is | Used by |
|---|---|---|
| `incidents.csv` (100 rows) | Incident ID, description, zone, asset type and ID, timestamp (January to April 2025), priority, status, resolution summary (empty when open) | Embeddings, graph, retrieval |
| `assets (1).csv` (96 rows) | Asset ID, name, type (Router, Tower, Repeater, BTS) and zone | Graph |
| `zones.csv` (3 rows) | Zone, region and supervisor | Graph |
| `technicians (1).csv` (51 rows) | Which technician resolved which incident | Graph |
| `images.csv` (20 rows) | Drone image file name, caption and incident ID | Embeddings, graph, retrieval |
| `drone-images/` (20 JPEGs, 2048×2048, 17 MB) | Drone inspection photos for incidents INC900 to INC919 | Image embeddings, photo search, Streamlit UI |
| `logs.jsonl` (150 lines) | Asset log lines (log level and message) | Not read by the code; an example of semi-structured data next to the incidents |
| `multimodal_image_features.json` | Hand-labelled visual features per image (for example Vegetation, Structural) and summary counts | Not read by the code; the multimodal image graph model labels images from their captions instead |

The `(1)` in two file names comes from the original export; the code uses these names, so they are kept.

The screenshots in [`../screenshots`](../screenshots) come from the author's runs of the first edition (April 2025) and are MIT-licensed as well.
