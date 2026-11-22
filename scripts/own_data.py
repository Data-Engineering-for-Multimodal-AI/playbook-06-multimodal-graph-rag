"""Check a folder of your own incident data, then build the graph from it.

    make check-data DIR=my_incidents   # check every file, write nothing
    make load DIR=my_incidents         # check it, then embeddings + graph from it

The folder has the same layout as data/:

    my_incidents/
      incidents.csv     incident_id, description, zone, asset_type, asset_id, timestamp,
                        priority, status, resolution_summary
      assets.csv        asset_id, asset_name, asset_type, zone_id
      zones.csv         zone_id, region, supervisor
      technicians.csv   incident_id, technician_id
      images.csv        incident_id, image_filename, caption
      drone-images/     the photos images.csv names (.jpg .jpeg .png)

`assets (1).csv` and `technicians (1).csv`, the sample names, work too.

The checks are the things that break this pipeline or quietly lose data in it: files that
are missing or not UTF-8, missing columns, empty or duplicate IDs, timestamps the graph step
can't parse, zones and assets an incident names but that don't exist (the edge would be
silently missing), more than one photo per incident (the photo embeddings are matched by
incident ID), and photos that are missing, unreadable, tiny or Git LFS pointers. Every
problem is reported with the file and the reason. If there is any problem, nothing is written.

`make load` runs `python main.py --mode embeddings` and `--mode graph` with DATA_DIR set to
your folder, then deletes this system's cached answers in Redis (they describe the old graph).
Like `--mode graph`, it replaces everything in the Neo4j database it connects to.
"""

import argparse
import csv
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COLUMNS = {
    "incidents": ["incident_id", "description", "zone", "asset_type", "asset_id", "timestamp",
                  "priority", "status", "resolution_summary"],
    "assets": ["asset_id", "asset_name", "asset_type", "zone_id"],
    "zones": ["zone_id", "region", "supervisor"],
    "technicians": ["incident_id", "technician_id"],
    "images": ["incident_id", "image_filename", "caption"],
}
NOT_EMPTY = {"incidents": ["incident_id", "description", "zone", "asset_type", "asset_id", "timestamp"],
             "assets": ["asset_id", "asset_type", "zone_id"], "zones": ["zone_id"],
             "technicians": ["incident_id", "technician_id"], "images": ["incident_id", "image_filename"]}
TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"  # what graph_construction.py parses
IMAGE_TYPES = {".jpg", ".jpeg", ".png"}
MIN_SIDE = 32
MAX_IMAGE_MB = 50


def csv_path(folder, name):
    """The CSV for `name`; for assets and technicians also the sample's '<name> (1).csv'."""
    for candidate in (folder / f"{name}.csv", folder / f"{name} (1).csv"):
        if candidate.exists():
            return candidate
    return folder / f"{name}.csv"


def read_csv(path, name, problems):
    """Rows of a CSV as dicts, or None after recording why it can't be used."""
    rel = path.name
    if not path.exists():
        problems.append(f"{rel}: missing (needs columns {', '.join(COLUMNS[name])})")
        return None
    raw = path.read_bytes()
    if raw.startswith(b"version https://git-lfs"):
        problems.append(f"{rel}: Git LFS pointer, not the file (run git lfs pull)")
        return None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        problems.append(f"{rel}: not UTF-8 text (byte {e.start})")
        return None
    reader = csv.DictReader(text.splitlines())
    missing = [c for c in COLUMNS[name] if c not in (reader.fieldnames or [])]
    if missing:
        problems.append(f"{rel}: missing column(s) {', '.join(missing)}")
        return None
    rows = list(reader)
    if not rows:
        problems.append(f"{rel}: no rows")
        return None
    for line, row in enumerate(rows, start=2):
        if None in row:
            problems.append(f"{rel} line {line}: more values than columns")
        for col in NOT_EMPTY[name]:
            if not (row.get(col) or "").strip():
                problems.append(f"{rel} line {line}: empty {col}")
    return rows


def duplicates(rows, key):
    seen, dup = set(), []
    for line, row in enumerate(rows, start=2):
        value = row[key]
        if value in seen:
            dup.append((line, value))
        seen.add(value)
    return dup


def check_image(path):
    """A problem description, or None if CLIP can read the photo."""
    if path.stat().st_size == 0:
        return "empty file"
    if path.read_bytes()[:40].startswith(b"version https://git-lfs"):
        return "Git LFS pointer, not the photo (run git lfs pull)"
    if path.stat().st_size > MAX_IMAGE_MB * 1024 * 1024:
        return f"larger than {MAX_IMAGE_MB} MB"
    from PIL import Image
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            if min(im.size) < MIN_SIDE:
                return f"too small ({im.size[0]}x{im.size[1]}), needs at least {MIN_SIDE}x{MIN_SIDE}"
    except Exception as e:
        return f"can't open as an image ({e.__class__.__name__})"
    return None


def check(folder):
    """Check a data folder. Returns (summary counts, [problems])."""
    folder = Path(folder)
    problems = []
    if not folder.is_dir():
        return {}, [f"{folder}: not a folder"]
    tables = {name: read_csv(csv_path(folder, name), name, problems) for name in COLUMNS}
    inc, assets, zones, techs, images = (tables[n] for n in COLUMNS)
    name = {n: csv_path(folder, n).name for n in COLUMNS}

    for table, key in (("incidents", "incident_id"), ("zones", "zone_id")):
        for line, value in duplicates(tables[table] or [], key):
            problems.append(f"{name[table]} line {line}: duplicate {key} {value}")

    zone_ids = {z["zone_id"] for z in zones or []}
    asset_keys = {(a["asset_id"], a["asset_type"], a["zone_id"]) for a in assets or []}
    incident_ids = {i["incident_id"] for i in inc or []}
    for line, row in enumerate(inc or [], start=2):
        ts = (row["timestamp"] or "").strip()
        if ts:
            try:
                datetime.strptime(ts, TIME_FORMAT)
            except ValueError:
                problems.append(f"{name['incidents']} line {line}: timestamp {ts!r} is not YYYY-MM-DDTHH:MM:SS")
        if zones is not None and row["zone"] and row["zone"] not in zone_ids:
            problems.append(f"{name['incidents']} line {line}: zone {row['zone']!r} is not in {name['zones']}")
        if assets is not None and row["asset_id"] and \
                (row["asset_id"], row["asset_type"], row["zone"]) not in asset_keys:
            problems.append(f"{name['incidents']} line {line}: asset {row['asset_id']} ({row['asset_type']}, "
                            f"{row['zone']}) is not in {name['assets']}")
    for line, row in enumerate(assets or [], start=2):
        if zones is not None and row["zone_id"] and row["zone_id"] not in zone_ids:
            problems.append(f"{name['assets']} line {line}: zone {row['zone_id']!r} is not in {name['zones']}")
    for table in ("technicians", "images"):
        for line, row in enumerate(tables[table] or [], start=2):
            if inc is not None and row["incident_id"] and row["incident_id"] not in incident_ids:
                problems.append(f"{name[table]} line {line}: incident {row['incident_id']} is not in "
                                f"{name['incidents']}")
    for line, value in duplicates(images or [], "incident_id"):
        problems.append(f"{name['images']} line {line}: second photo for {value} (one photo per incident)")

    photo_dir = folder / "drone-images"
    for line, row in enumerate(images or [], start=2):
        filename = (row["image_filename"] or "").strip()
        if not filename:
            continue
        path = photo_dir / filename
        rel = f"drone-images/{filename}"
        if path.suffix.lower() not in IMAGE_TYPES:
            problems.append(f"{rel}: not a photo type this pipeline reads (.jpg .jpeg .png)")
        elif not path.exists():
            problems.append(f"{rel}: listed in {name['images']} line {line} but not found")
        else:
            reason = check_image(path)
            if reason:
                problems.append(f"{rel}: {reason}")

    summary = {n: len(tables[n] or []) for n in COLUMNS}
    return summary, problems


def main():
    parser = argparse.ArgumentParser(description="Check a folder of incident data and build the graph from it.")
    parser.add_argument("--dir", required=True)
    parser.add_argument("--check-only", action="store_true", help="check the files, write nothing")
    args = parser.parse_args()
    folder = Path(args.dir).resolve()

    summary, problems = check(folder)
    if problems:
        print(f"{len(problems)} problem(s) in {args.dir}; nothing was written:")
        for p in problems:
            print(f"  {p}")
        sys.exit(1)
    print(f"{args.dir}: {summary['incidents']} incidents, {summary['assets']} assets, {summary['zones']} zones, "
          f"{summary['technicians']} technician links, {summary['images']} photos. All checks passed.")
    if args.check_only:
        return

    env = dict(os.environ, DATA_DIR=str(folder))
    print("Building embeddings and the Neo4j graph from it (this replaces the graph in Neo4j)...")
    for mode in ("embeddings", "graph"):
        subprocess.run([sys.executable, str(ROOT / "main.py"), "--mode", mode], env=env, check=True, cwd=ROOT)
    # Cached answers still describe the old graph: delete this system's keys (nothing else in Redis)
    sys.path.insert(0, str(ROOT))
    from src.edge_cache import EdgeAwareCache
    EdgeAwareCache().clear_cache()
    print(f"Loaded {summary['incidents']} incidents and {summary['images']} photos. "
          "Search them with make search Q=\"...\" (use make run to go back to the samples).")


if __name__ == "__main__":
    main()
