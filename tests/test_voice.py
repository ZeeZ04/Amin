"""Voice mode: the wake phrase match (amin/voice.py). Whisper itself is not run here."""

import pytest

from amin.voice import WAKE


@pytest.mark.parametrize("heard, rest", [
    ("Hey Amin.", ""),
    ("Hey Amin, when does my lease end?", "when does my lease end?"),
    ("hi ameen", ""),
    ("Amin, what time is it?", "what time is it?"),
    ("يا أمين، متى ينتهي العقد؟", "متى ينتهي العقد؟"),
    ("ഹേ അമീൻ, വാടക എത്രയാണ്?", "വാടക എത്രയാണ്?"),
])
def test_wakes_on_the_name_first(heard, rest):
    m = WAKE.match(heard)
    assert m and heard[m.end():].strip() == rest


@pytest.mark.parametrize("heard", [
    "Hey Siri.", "Hey, I mean it.", "Amina called earlier.", "I'd like a mint tea, please.",
    "Tell Amin I said hi.", "The meeting is at 9.", "",
])
def test_stays_quiet_otherwise(heard):
    assert not WAKE.match(heard)
