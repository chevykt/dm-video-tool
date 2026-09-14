# tests/test_runner.py
import sys

import pytest

from pipeline.runner import FFmpegFailed, FFmpegMissing, ensure_ffmpeg, run


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_nonzero_exit_raises_with_stderr_text():
    cmd = _py("import sys; sys.stderr.write('boom went the render\\n'); sys.exit(1)")
    with pytest.raises(FFmpegFailed, match="boom went the render"):
        run(cmd)


def test_only_last_20_stderr_lines_are_kept():
    code = (
        "import sys\n"
        "for i in range(1, 31):\n"
        "    sys.stderr.write(f'line {i}\\n')\n"
        "sys.exit(1)\n"
    )
    with pytest.raises(FFmpegFailed) as exc_info:
        run(_py(code))
    message = str(exc_info.value)
    assert "line 30" in message
    assert "line 10" not in message


def test_non_ascii_stderr_is_decoded_as_utf8_not_mojibake():
    code = (
        "import sys\n"
        "sys.stderr.buffer.write('Á José 日本'.encode('utf-8'))\n"
        "sys.exit(1)\n"
    )
    with pytest.raises(FFmpegFailed) as exc_info:
        run(_py(code))
    message = str(exc_info.value)
    assert "Á José 日本" in message


def test_empty_stderr_with_nonzero_exit_still_names_exit_code():
    cmd = _py("import sys; sys.exit(3)")
    with pytest.raises(FFmpegFailed, match="3"):
        run(cmd)


def test_ensure_ffmpeg_missing_mentions_winget(monkeypatch):
    monkeypatch.setattr("pipeline.runner.shutil.which", lambda name: None)
    with pytest.raises(FFmpegMissing, match="winget install Gyan.FFmpeg"):
        ensure_ffmpeg()
