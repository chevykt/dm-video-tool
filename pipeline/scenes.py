import csv
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from config import Config
from pipeline.timing import duration_for

SCENE_FILENAME = re.compile(r"^conversation_(\d+)\.png$", re.IGNORECASE)
TRUTHY = {"true", "yes", "1", "x", "y"}


@dataclass
class Scene:
    id: int
    image_path: Path
    text: str
    speaker: str
    duration: float
    zoom: bool = False
    shake: bool = False
    sfx: str = "pop"


def scene_id_from_filename(name: str) -> int:
    m = SCENE_FILENAME.match(Path(name).name)
    if not m:
        raise ValueError(
            f"Unexpected image filename: {Path(name).name!r}. "
            "Expected conversation_<id>.png as produced by the sheet."
        )
    return int(m.group(1))


def extract_zips(zip_paths, dest: Path) -> list[Path]:
    """Flatten every PNG from every zip into dest. Returns the extracted paths."""
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for zp in zip_paths:
        with zipfile.ZipFile(zp) as z:
            for member in z.namelist():
                if not member.lower().endswith(".png"):
                    continue
                target = dest / Path(member).name
                with z.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                out.append(target)
    return out


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in TRUTHY


def _rows_by_id(csv_path: Path) -> dict[int, list[dict]]:
    groups: dict[int, list[dict]] = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            raw_id = (row.get("conversation_id") or "").strip()
            message = (row.get("message") or "").strip()
            if not raw_id or not message:
                continue
            groups.setdefault(int(raw_id), []).append(row)
    return groups


def build_scenes(image_paths, csv_path: Path, cfg: Config) -> list[Scene]:
    groups = _rows_by_id(csv_path)
    images = {scene_id_from_filename(p.name): Path(p) for p in image_paths}

    orphan_images = sorted(set(images) - set(groups))
    orphan_rows = sorted(set(groups) - set(images))
    if orphan_images or orphan_rows:
        raise ValueError(
            f"Image and sheet do not line up. "
            f"Images with no row: {orphan_images}. Rows with no image: {orphan_rows}."
        )

    scenes = []
    for sid in sorted(images):
        rows = groups[sid]
        text = " ".join((r.get("message") or "").strip() for r in rows)
        scenes.append(
            Scene(
                id=sid,
                image_path=images[sid],
                text=text,
                speaker=(rows[0].get("name") or "").strip(),
                duration=duration_for(text, cfg),
                zoom=_truthy(rows[0].get("zoom")),
                shake=_truthy(rows[0].get("shake")),
                sfx=cfg.default_sfx,
            )
        )
    return scenes
