# pipeline/runner.py
import shutil
import subprocess
from pathlib import Path


class FFmpegMissing(RuntimeError):
    pass


class FFmpegFailed(RuntimeError):
    pass


def ensure_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise FFmpegMissing(
            "FFmpeg is not installed or not on PATH.\n"
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
