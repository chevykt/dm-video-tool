import pytest
from config import Config
from pipeline.timing import duration_for, frames_for

CFG = Config()


def test_short_message_uses_word_rule():
    # "coin says no" = 3 words, 12 chars
    # by_word = 1.0 + 0.34*3 = 2.02 ; by_char = 1.0 + 12/17 = 1.706
    assert round(duration_for("coin says no", CFG), 2) == 2.02


def test_long_word_is_rescued_by_char_rule():
    # "obviously" = 1 word, 9 chars
    # by_word = 1.34 ; by_char = 1.0 + 9/17 = 1.529 -> char rule wins
    assert round(duration_for("obviously", CFG), 2) == 1.53


def test_very_long_message_hits_the_ceiling():
    text = ("like this video, subscribe for more mha text stories, and comment "
            "if you think deku and uraraka make a good couple")
    assert duration_for(text, CFG) == CFG.max_duration


def test_floor_applies_when_config_is_tuned_down():
    cfg = Config(base=0.2, per_word=0.1)
    assert duration_for("hi", cfg) == cfg.min_duration


def test_frames_for_rounds_to_the_nearest_whole_frame():
    assert frames_for(2.0, 30) == 60
    assert frames_for(2.02, 30) == 61
    assert frames_for(1.529, 30) == 46
    assert frames_for(2.067, 30) == 62
    # durations where the old `-t` rounding over-counted by a whole frame on
    # FFmpeg 9.0.1 (46 and 101 frames instead of the correct 45/100)
    assert frames_for(1.51, 30) == 45
    assert frames_for(3.34, 30) == 100
    assert frames_for(2.333, 30) == 70
    assert frames_for(0.01, 30) == 1
