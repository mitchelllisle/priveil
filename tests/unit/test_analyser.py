"""Unit tests for the async detection engine.

_to_entity is a pure function — tested directly with Span + BaseRecogniser.
AsyncAnalyser.analyse is tested against the regex-only engine (no GLiNER2 in tests).
No mocks.
"""

from priveil.domain.detection import DetectionRequest
from priveil.domain.entities import EntityType
from priveil.engine.analyser import AsyncAnalyser, _to_entity
from priveil.recognisers.au_tfn import AUTFNRecogniser
from priveil.recognisers.base import Span
from priveil.recognisers.email import EmailRecogniser

# ── _to_entity ────────────────────────────────────────────────────────────────

def test_to_entity_sets_fields_from_recogniser() -> None:
    rec = EmailRecogniser()
    span = Span(text="hello@example.com", start=0, end=17, score=0.85)
    entity = _to_entity(span, rec)
    assert entity.entity_type == EntityType.EMAIL_ADDRESS
    assert entity.text == "hello@example.com"
    assert entity.start == 0
    assert entity.end == 17
    assert entity.score == 0.85
    assert entity.is_pii is True
    assert entity.sensitivity == "medium"
    assert entity.verification == "trust"


def test_to_entity_critical_type() -> None:
    rec = AUTFNRecogniser()
    span = Span(text="123 456 782", start=5, end=16, score=0.95)
    entity = _to_entity(span, rec)
    assert entity.sensitivity == "critical"
    assert entity.is_pii is True
    assert entity.entity_type == EntityType.AU_TFN


# ── AsyncAnalyser ─────────────────────────────────────────────────────────────

async def test_analyse_detects_email(analyser: AsyncAnalyser) -> None:
    req = DetectionRequest(text="Contact us at support@example.com for help.")
    result = await analyser.analyse(req)
    types = {e.entity_type for e in result.entities}
    assert EntityType.EMAIL_ADDRESS in types


async def test_analyse_input_hash_is_stable(analyser: AsyncAnalyser) -> None:
    req = DetectionRequest(text="hello world")
    r1 = await analyser.analyse(req)
    r2 = await analyser.analyse(req)
    assert r1.input_hash == r2.input_hash
    assert r1.input_hash.startswith("hmac-sha256:")


async def test_analyse_entities_sorted_by_start(analyser: AsyncAnalyser) -> None:
    req = DetectionRequest(text="Email jane@x.com or call 0412 345 678 today.")
    result = await analyser.analyse(req)
    starts = [e.start for e in result.entities]
    assert starts == sorted(starts)


async def test_analyse_no_critical_pii_in_clean_text(analyser: AsyncAnalyser) -> None:
    req = DetectionRequest(text="The fixed interest rate is 5.5 percent per annum.")
    result = await analyser.analyse(req)
    critical = [e for e in result.entities if e.sensitivity == "critical"]
    assert len(critical) == 0


async def test_analyse_detects_tfn(analyser: AsyncAnalyser) -> None:
    req = DetectionRequest(text="My TFN is 123 456 782.")
    result = await analyser.analyse(req)
    tfns = [e for e in result.entities if e.entity_type == EntityType.AU_TFN]
    assert len(tfns) == 1
    assert tfns[0].text == "123 456 782"
