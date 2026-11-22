"""Checks for the "Use your own data" adapter (scripts/own_data.py). No Neo4j, Redis or models."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from own_data import check  # noqa: E402

SAMPLES = ROOT / "data"
PHOTO = SAMPLES / "drone-images" / "INC909_tower_muddy_base_flooded.jpeg"

GOOD = {
    "incidents.csv": "incident_id,description,zone,asset_type,asset_id,timestamp,priority,status,resolution_summary\n"
                     "X1,Fiber cut near the hub.,North,Router,R1,2026-01-05T10:00:00,High,Resolved,Spliced the fiber.\n"
                     "X2,Router reboots every night.,North,Router,R1,2026-01-06T09:00:00,Low,Open,\n",
    "assets.csv": "asset_id,asset_name,asset_type,zone_id\nR1,Router_R1,Router,North\n",
    "zones.csv": "zone_id,region,supervisor\nNorth,North,Sam P.\n",
    "technicians.csv": "incident_id,technician_id\nX1,Tech_1\n",
    "images.csv": "incident_id,image_filename,caption\nX1,x1.jpeg,Hub cabinet after the repair.\n",
}


def make_folder(path, **changes):
    """A small valid folder, with some files replaced (str or bytes) or removed (None)."""
    files = dict(GOOD, **changes)
    (path / "drone-images").mkdir(parents=True)
    shutil.copy(PHOTO, path / "drone-images" / "x1.jpeg")
    for name, content in files.items():
        if content is None:
            continue
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    return path


def test_samples_pass():
    summary, problems = check(SAMPLES)
    assert problems == []
    assert summary == {"incidents": 100, "assets": 96, "zones": 3, "technicians": 51, "images": 20}


def test_good_folder(tmp_path):
    summary, problems = check(make_folder(tmp_path))
    assert problems == []
    assert summary["incidents"] == 2 and summary["images"] == 1


@pytest.mark.parametrize("changes,expected", [
    ({"zones.csv": None}, "zones.csv: missing"),
    ({"incidents.csv": GOOD["incidents.csv"].replace(",priority", ",prio")}, "missing column(s) priority"),
    ({"technicians.csv": "incident_id,technician_id\nX1,T\xe9ch\n".encode("latin-1")}, "not UTF-8"),
    ({"incidents.csv": GOOD["incidents.csv"].replace("2026-01-06T09:00:00", "06/01/2026 09:00")},
     "timestamp '06/01/2026 09:00' is not YYYY-MM-DDTHH:MM:SS"),
    ({"incidents.csv": GOOD["incidents.csv"].replace("X2,", "X1,")}, "duplicate incident_id X1"),
    ({"incidents.csv": GOOD["incidents.csv"].replace(",North,Router,R1,2026-01-06", ",South,Router,R1,2026-01-06")},
     "zone 'South' is not in zones.csv"),
    ({"incidents.csv": GOOD["incidents.csv"].replace("Router,R1,2026-01-06", "Tower,R1,2026-01-06")},
     "asset R1 (Tower, North) is not in assets.csv"),
    ({"technicians.csv": "incident_id,technician_id\nX9,Tech_1\n"}, "incident X9 is not in incidents.csv"),
    ({"images.csv": GOOD["images.csv"] + "X1,x1.jpeg,Again.\n"}, "second photo for X1"),
    ({"images.csv": "incident_id,image_filename,caption\nX1,missing.jpeg,Gone.\n"}, "not found"),
    ({"images.csv": "incident_id,image_filename,caption\nX1,x1.gif,Gif.\n"}, "not a photo type"),
    ({"drone-images/x1.jpeg": b"version https://git-lfs.github.com/spec/v1\n"}, "Git LFS pointer"),
    ({"drone-images/x1.jpeg": b"not a photo"}, "can't open as an image"),
    ({"incidents.csv": GOOD["incidents.csv"].replace("Fiber cut near the hub.", "")}, "empty description"),
])
def test_problems_are_reported(tmp_path, changes, expected):
    _, problems = check(make_folder(tmp_path, **changes))
    assert any(expected in p for p in problems), problems


def test_tiny_photo(tmp_path):
    folder = make_folder(tmp_path)
    Image.new("RGB", (16, 16)).save(folder / "drone-images" / "x1.jpeg")
    _, problems = check(folder)
    assert problems == ["drone-images/x1.jpeg: too small (16x16), needs at least 32x32"]


def test_sample_file_names_work(tmp_path):
    folder = make_folder(tmp_path, **{"assets.csv": None, "assets (1).csv": GOOD["assets.csv"]})
    assert check(folder)[1] == []


def test_check_only_writes_nothing_and_fails_on_problems(tmp_path):
    folder = make_folder(tmp_path / "in", **{"zones.csv": None})
    before = sorted(p.relative_to(folder) for p in folder.rglob("*"))
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "own_data.py"), "--dir", str(folder)],
                         capture_output=True, text=True, cwd=ROOT)
    assert run.returncode == 1
    assert "nothing was written" in run.stdout and "zones.csv: missing" in run.stdout
    assert sorted(p.relative_to(folder) for p in folder.rglob("*")) == before
