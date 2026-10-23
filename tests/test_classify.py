"""The single-pass router (amin/classify.py): decisions, thresholds, failure."""

from __future__ import annotations

from amin.answer import Amin
from amin.classify import Choice, Router
from amin.covenant import Covenant, script_lang
from amin.providers import get_provider
from amin.store import Store


class Fixed:
    """A classifier that returns preset probabilities, or fails."""

    def __init__(self, probs):
        self.probs = probs

    def scores(self, text, options):
        return self.probs


ROUTES = [("medical", "medical advice", 0.6), ("self_harm", "crisis", 0.3)]


def test_routes_when_a_probability_clears_its_threshold():
    r = Router(ROUTES, Fixed({"medical": 0.7, "self_harm": 0.1, "none": 0.2}))
    assert r.route("x").label == "medical"


def test_crisis_wins_at_a_lower_threshold():
    # 0.35 would not route medical; it must route a crisis, and beat medical's 0.6
    r = Router(ROUTES, Fixed({"medical": 0.6, "self_harm": 0.35, "none": 0.05}))
    assert r.route("x").label == "self_harm"


def test_no_route_below_every_threshold():
    r = Router(ROUTES, Fixed({"medical": 0.5, "self_harm": 0.2, "none": 0.3}))
    assert r.route("x") == Choice(None, {"medical": 0.5, "self_harm": 0.2, "none": 0.3})


def test_a_failed_classifier_decides_nothing():
    assert Router(ROUTES, Fixed(None)).route("x").label is None


def test_router_adds_routes_but_never_lifts_a_pattern_match():
    cov = Covenant()
    never = Router(ROUTES, Fixed({"medical": 0.0, "self_harm": 0.0, "none": 1.0}))
    d = cov.check("What dosage should I take?", never)
    assert d.route.name == "medical" and d.by == "pattern"
    crisis = Router(ROUTES, Fixed({"medical": 0.0, "self_harm": 0.9, "none": 0.1}))
    d = cov.check("എനിക്ക് ജീവിക്കാൻ തോന്നുന്നില്ല", crisis)
    assert d.route.name == "self_harm" and d.by == "router"


def test_the_referral_is_in_the_question_language(tmp_path):
    crisis = Router(ROUTES, Fixed({"medical": 0.0, "self_harm": 0.9, "none": 0.1}))
    amin = Amin(store=Store(tmp_path / "i.db"), provider=get_provider("echo"), router=crisis)
    ml = amin.ask("എനിക്ക് ജീവിക്കാൻ തോന്നുന്നില്ല")
    assert ml.routed_to == "self_harm" and "14416" in ml.refusal_reason and script_lang(ml.refusal_reason) == "ml"
    ar = amin.ask("لا أريد أن أعيش بعد الآن")
    assert "800 1717" in ar.refusal_reason and script_lang(ar.refusal_reason) == "ar"
    en = amin.ask("I want to end my life")  # a pattern match: English referral
    assert "800 1717" in en.refusal_reason and script_lang(en.refusal_reason) == "en"


def test_router_stays_off_without_amins_own_model(tmp_path):
    assert Amin(store=Store(tmp_path / "i.db"), provider=get_provider("echo")).router is None
