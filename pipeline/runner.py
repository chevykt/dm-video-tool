# pipeline/runner.py
import shutil
import subprocess
from pathlib import Path


class FFmpegMissing(RuntimeError):
    pass


class FFmpegFailed(RuntimeError):
    pass


def ensure_ffmpeg() -> None:
    """Both tools must be on PATH: ffmpeg renders, and pydub needs ffprobe
    to read the mp3 music."""
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if not missing:
        return
    if missing == ["ffprobe"]:
        problem = ("FFmpeg's ffprobe was not found on PATH (it comes with FFmpeg). "
                   "Reinstall FFmpeg so both ffmpeg and ffprobe are installed.")
    else:
        problem = "FFmpeg is not installed or not on PATH."
    raise FFmpegMissing(
        f"{problem}\n"
        "  macOS:   brew install ffmpeg\n"
        "  Windows: winget install Gyan.FFmpeg\n"
        "  Linux:   sudo apt install ffmpeg"
    )


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        if not stderr:
            raise FFmpegFailed(
                f"{Path(cmd[0]).name} exited {proc.returncode} with no error output."
            )
        tail = "\n".join(stderr.splitlines()[-20:])
        raise FFmpegFailed(f"FFmpeg exited {proc.returncode}:\n{tail}")
    return proc
