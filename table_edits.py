# table_edits.py
"""The scene table shown in st.data_editor, and pure reconciliation of the
editor's output back onto the scenes.

No streamlit import here: app.py is the only module that imports streamlit,
so this logic can be unit tested without a Streamlit runtime.
"""
from dataclasses import dataclass

import pandas as pd

TABLE_COLUMNS = ["id", "speaker", "message", "words", "seconds", "hand-set",
                 "zoom", "shake", "sfx"]


def scene_table(scenes, overrides: dict[int, float]) -> pd.DataFrame:
    """One row per scene, in scene order: what the editor starts from."""
    return pd.DataFrame(
        [
            {"id": s.id, "speaker": s.speaker, "message": s.text[:60],
             "words": len(s.text.split()),
             "seconds": round(s.duration, 2), "hand-set": s.id in overrides,
             "zoom": s.zoom, "shake": s.shake, "sfx": s.sfx}
            for s in scenes
        ],
        columns=TABLE_COLUMNS,
    )


@dataclass(frozen=True)
class TableChanges:
    """What a round of editor output changed.

    `durations` means a seconds cell was typed: the caller must give the
    editor a fresh key, or the editor re-applies that stale number on top
    of durations the sliders recalculate later. `flags` (zoom, shake, sfx)
    needs no fresh key: the next run's table already holds the new value,
    so the editor's remembered edit compares equal and is not applied twice.
    """
    durations: bool = False
    flags: bool = False

    def __bool__(self) -> bool:
        return self.durations or self.flags


def apply_table_edits(scenes, overrides: dict[int, float], before: pd.DataFrame,
                      edited: pd.DataFrame) -> TableChanges:
    """Fold the editor's output into `overrides` and onto `scenes`, in place.

    Rows are matched by the `id` column, never by position: the table can be
    sorted in the UI, so `edited` may not be in the same row order as `before`.
    A cleared cell (None / NaN) is ignored rather than written to a scene.
    """
    by_id = {s.id: s for s in scenes}
    before_by_id = before.set_index("id")
    durations = flags = False

    for _, row in edited.iterrows():
        sid = int(row["id"])
        scene = by_id[sid]
        if not pd.isna(row["seconds"]) and float(row["seconds"]) != before_by_id.at[sid, "seconds"]:
            overrides[sid] = float(row["seconds"])
            durations = True
        for col in ("zoom", "shake"):
            if pd.isna(row[col]):
                continue
            if bool(row[col]) != bool(before_by_id.at[sid, col]):
                setattr(scene, col, bool(row[col]))
                flags = True
        if not pd.isna(row["sfx"]) and str(row["sfx"]) != str(before_by_id.at[sid, "sfx"]):
            scene.sfx = str(row["sfx"])
            flags = True

    return TableChanges(durations=durations, flags=flags)
