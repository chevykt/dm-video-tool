# table_edits.py
"""Pure reconciliation of st.data_editor's output against the scene table.

No streamlit import here: app.py is the only module that imports streamlit,
so this logic can be unit tested without a Streamlit runtime.
"""
import pandas as pd


def apply_table_edits(scenes, overrides: dict[int, float], before: pd.DataFrame,
                      edited: pd.DataFrame) -> bool:
    """Fold the editor's output into `overrides` and onto `scenes`, in place.

    Rows are matched by the `id` column, never by position: the table can be
    sorted in the UI, so `edited` may not be in the same row order as `before`.
    Returns True if anything changed.
    """
    by_id = {s.id: s for s in scenes}
    before_by_id = before.set_index("id")
    changed = False

    for _, row in edited.iterrows():
        sid = int(row["id"])
        scene = by_id[sid]
        if not pd.isna(row["seconds"]) and float(row["seconds"]) != before_by_id.at[sid, "seconds"]:
            overrides[sid] = float(row["seconds"])
            changed = True
        for col in ("zoom", "shake"):
            if bool(row[col]) != bool(before_by_id.at[sid, col]):
                setattr(scene, col, bool(row[col]))
                changed = True
        if str(row["sfx"]) != str(before_by_id.at[sid, "sfx"]):
            scene.sfx = str(row["sfx"])
            changed = True

    return changed
