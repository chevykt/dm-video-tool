import csv
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
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


def extract_zips(zip_paths: list[Path], dest: Path) -> list[Path]:
    """Flatten every PNG from every zip into dest. Returns the extracted paths."""
    dest.mkdir(parents=True, exist_ok=True)
    out = []
    for zp in zip_paths:
        with zipfile.ZipFile(zp) as z:
            for member in z.namelist():
                if not member.lower().endswith(".png"):
                    continue
                member_path = Path(member)
                if "__MACOSX" in member_path.parts:
                    continue
                if member_path.name.startswith("._"):
                    continue
                target = dest / member_path.name
                with z.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
                out.append(target)
    return out


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in TRUTHY


REQUIRED_COLUMNS = ("conversation_id", "message")


def _normalize_row(row: dict) -> dict:
    return {(k or "").strip().lower(): v for k, v in row.items()}


def _rows_by_id(csv_path: Path) -> dict[int, list[dict]]:
    groups: dict[int, list[dict]] = {}
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        found = sorted({(fn or "").strip().lower() for fn in (reader.fieldnames or []) if (fn or "").strip()})
        missing = [c for c in REQUIRED_COLUMNS if c not in found]
        if missing:
            raise ValueError(
                f"Sheet CSV is missing required column(s): {', '.join(missing)}. "
                f"Columns found: {found or '(none)'}. "
                "If this looks wrong, you may have exported the wrong tab from the Google Sheet."
            )
        # Row 1 is the header, so the first data row is CSV line 2.
        for line_no, raw_row in enumerate(reader, start=2):
            row = _normalize_row(raw_row)
            raw_id = (row.get("conversation_id") or "").strip()
            message = (row.get("message") or "").strip()
            if not raw_id or not message:
                continue
            try:
                cid = int(raw_id)
            except ValueError:
                raise ValueError(
                    f"Non-numeric conversation_id {raw_id!r} on CSV line {line_no}."
                ) from None
            groups.setdefault(cid, []).append(row)
    return groups


def build_scenes(image_paths: list[Path], csv_path: Path, cfg: Config) -> list[Scene]:
    groups = _rows_by_id(csv_path)

    # Check for duplicate image ids
    ids = [scene_id_from_filename(p.name) for p in image_paths]
    duplicates = sorted(sid for sid, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(
            f"Duplicate images for ids: {duplicates}. "
            f"Each conversation_<id>.png must appear exactly once across all uploaded zips."
        )

    images = {scene_id_from_filename(p.name): Path(p) for p in image_paths}

    orphan_images = sorted(set(images) - set(groups))
    orphan_rows = sorted(set(groups) - set(images))
    if orphan_images or orphan_rows:
        raise ValueError(
            f"Image and sheet do not line up. "
            f"Images with no row: {orphan_images}. Rows with no image: {orphan_rows}."
        )
    if not images:  # and so no rows either: nothing lines up wrongly, there is nothing
        raise ValueError("No messages found — check the CSV and the zip(s).")

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


def retime(scenes, cfg: Config, overrides: dict[int, float]) -> None:
    """Recompute every scene's duration from the rule, keeping hand-set ones."""
    for scene in scenes:
        scene.duration = overrides.get(scene.id, duration_for(scene.text, cfg))
