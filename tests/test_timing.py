import pytest
from config import Config
from pipeline.timing import duration_for

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
