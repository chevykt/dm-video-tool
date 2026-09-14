from config import Config


def duration_for(text: str, cfg: Config) -> float:
    """Seconds this message should stay on screen.

    Takes the larger of a word-based and a character-based estimate so that
    a short line of long words is not under-timed, then clamps.
    """
    words = len(text.split())
    chars = len(text)
    by_word = cfg.base + cfg.per_word * words
    by_char = cfg.base + chars / cfg.chars_per_sec
    return min(max(by_word, by_char, cfg.min_duration), cfg.max_duration)
