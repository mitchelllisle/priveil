"""Detection accuracy tests — obvious patterns, ambiguous near-misses, and true negatives.

Exercises the regex-only recogniser stack via the session-scoped ``analyser`` fixture
(no GLiNER2, so PERSON / LOCATION / DATE_TIME entities are not tested here).

Structure
---------
- ``TestObviousDetections`` — canonical inputs that must trigger the right entity type.
- ``TestTrueNegatives`` — inputs that must NOT trigger a specific entity type (checksum
  failures, wrong format, no context words for low-precision recognisers).
- ``TestAmbiguous`` — near-misses and edge cases that probe boundary behaviour.
- ``TestMixedDocument`` — realistic multi-entity documents.
"""

from __future__ import annotations

import pytest

from priveil.domain.detection import DetectionRequest
from priveil.domain.entities import EntityType
from priveil.engine.analyser import AsyncAnalyser

# ── helpers ───────────────────────────────────────────────────────────────────


def _types(entities: tuple) -> set[str]:
    return {e.entity_type.value for e in entities}


async def _detect(analyser: AsyncAnalyser, text: str) -> tuple:
    result = await analyser.analyse(DetectionRequest(text=text))
    return result.entities


# ── obvious detections ────────────────────────────────────────────────────────


class TestObviousDetections:
    """Canonical inputs — every case must detect the stated entity type."""

    # Email
    @pytest.mark.parametrize("text", [
        "Please email us at billing@acme.com.au",
        "Send your query to first.last@company.com",
        "Contact dev+tag@sub.example.org for support",
    ])
    async def test_email_detected(self, analyser: AsyncAnalyser, text: str) -> None:
        entities = await _detect(analyser, text)
        assert "EMAIL_ADDRESS" in _types(entities), f"Expected EMAIL_ADDRESS in: {text!r}"

    # AU TFN — spaced format (canonical ATO printed format)
    @pytest.mark.parametrize("text", [
        "My TFN is 123 456 782.",
        "Tax File Number: 123 456 782",
        "tfn 123 456 782 applies to this return",
    ])
    async def test_au_tfn_spaced_detected(self, analyser: AsyncAnalyser, text: str) -> None:
        entities = await _detect(analyser, text)
        assert "AU_TFN" in _types(entities), f"Expected AU_TFN in: {text!r}"

    # AU TFN — compact format (with context to avoid false-positive noise)
    async def test_au_tfn_compact_detected(self, analyser: AsyncAnalyser) -> None:
        entities = await _detect(analyser, "TFN 123456782 is attached")
        assert "AU_TFN" in _types(entities)

    # AU ABN
    @pytest.mark.parametrize("text", [
        "ABN 51 824 753 556 is registered",
        "Our Australian business number ABN 51 824 753 556",
    ])
    async def test_au_abn_detected(self, analyser: AsyncAnalyser, text: str) -> None:
        entities = await _detect(analyser, text)
        assert "AU_ABN" in _types(entities), f"Expected AU_ABN in: {text!r}"

    # AU ACN (Telstra: 004 085 616)
    @pytest.mark.parametrize("text", [
        "ACN 004 085 616 is listed on ASIC",
        "company number 004 085 616",
    ])
    async def test_au_acn_detected(self, analyser: AsyncAnalyser, text: str) -> None:
        entities = await _detect(analyser, text)
        assert "AU_ACN" in _types(entities), f"Expected AU_ACN in: {text!r}"

    # AU Medicare — spaced format
    # 2123 45670 1: weighted_sum(first 8 digits)=170, 170%10=0=digits[8] ✓
    @pytest.mark.parametrize("text", [
        "Medicare number: 2123 45670 1",
        "Your medicare card number is 2123 45670 1",
        "Health insurance card: 2123 45670 1",
    ])
    async def test_au_medicare_detected(self, analyser: AsyncAnalyser, text: str) -> None:
        entities = await _detect(analyser, text)
        assert "AU_MEDICARE" in _types(entities), f"Expected AU_MEDICARE in: {text!r}"

    # AU Phone — mobile (04xx local format)
    @pytest.mark.parametrize("text", [
        "Call me on 0412 345 678 anytime",
        "Mobile: 0412-345-678",
    ])
    async def test_au_phone_mobile_detected(self, analyser: AsyncAnalyser, text: str) -> None:
        entities = await _detect(analyser, text)
        assert "AU_PHONE" in _types(entities), f"Expected AU_PHONE in: {text!r}"


    # AU Phone — landline (state-based 02/03/07/08)
    @pytest.mark.parametrize("text", [
        "Office: 03 9876 5432",
        "Fax 08 9876 5432 for inquiries",
    ])
    async def test_au_phone_landline_detected(self, analyser: AsyncAnalyser, text: str) -> None:
        entities = await _detect(analyser, text)
        assert "AU_PHONE" in _types(entities), f"Expected AU_PHONE in: {text!r}"

    # Credit card — Visa test number (Luhn valid: sum=30)
    async def test_visa_card_detected(self, analyser: AsyncAnalyser) -> None:
        entities = await _detect(analyser, "Card number 4111111111111111 on file")
        assert "CREDIT_CARD" in _types(entities)

    # Credit card — Mastercard (Luhn valid: 5500005555555559)
    async def test_mastercard_detected(self, analyser: AsyncAnalyser) -> None:
        entities = await _detect(analyser, "Charge card 5500005555555559 please")
        assert "CREDIT_CARD" in _types(entities)

    # BSB — with context words (score boosted to 0.95, bypasses advisor at 0.9 threshold)
    @pytest.mark.parametrize("text", [
        "BSB 062-000 for this transfer",
        "Bank state branch code 062-000 applies",
        "routing via bsb 062-000",
    ])
    async def test_au_bsb_with_context_detected(self, analyser: AsyncAnalyser, text: str) -> None:
        entities = await _detect(analyser, text)
        assert "AU_BSB" in _types(entities), f"Expected AU_BSB in: {text!r}"


# ── true negatives ────────────────────────────────────────────────────────────


class TestTrueNegatives:
    """Inputs that must NOT produce a specific entity — checksum failures, wrong format."""

    # TFN checksum failures
    @pytest.mark.parametrize("text", [
        "Call us at 123 456 789",  # matches format, fails mod-11 checksum (sum=323)
        "Reference 987 654 321",   # matches format, fails mod-11 checksum
        "Legacy TFN 12 345 678",   # 8-digit — does not match 9-digit regex
    ])
    async def test_invalid_tfn_not_detected(self, analyser: AsyncAnalyser, text: str) -> None:
        entities = await _detect(analyser, text)
        assert "AU_TFN" not in _types(entities), f"Should NOT detect AU_TFN in: {text!r}"

    # ABN checksum failures
    @pytest.mark.parametrize("text", [
        "ABN 12 345 678 901",   # fails mod-89 checksum
        "business number 00 000 000 000",  # all zeros — fails checksum
    ])
    async def test_invalid_abn_not_detected(self, analyser: AsyncAnalyser, text: str) -> None:
        entities = await _detect(analyser, text)
        assert "AU_ABN" not in _types(entities), f"Should NOT detect AU_ABN in: {text!r}"

    # Medicare checksum failures
    @pytest.mark.parametrize("text", [
        "Medicare 2123 45679 9",  # wrong check digit (should be 0)
        "Health card 9999 99999 9",  # starts with 9, outside [2-6] → no pattern match
        "Medicare 1234 56789 0",  # first digit 1, outside [2-6] → no match
    ])
    async def test_invalid_medicare_not_detected(self, analyser: AsyncAnalyser, text: str) -> None:
        entities = await _detect(analyser, text)
        assert "AU_MEDICARE" not in _types(entities), f"Should NOT detect AU_MEDICARE in: {text!r}"

    # Credit card Luhn failures
    @pytest.mark.parametrize("text", [
        "Card 4111111111111112",  # last digit incremented — Luhn sum=31 fails
        "Swipe 4000000000000001",  # Luhn fails (sum=29)
    ])
    async def test_invalid_credit_card_not_detected(self, analyser: AsyncAnalyser, text: str) -> None:
        entities = await _detect(analyser, text)
        assert "CREDIT_CARD" not in _types(entities), f"Should NOT detect CREDIT_CARD in: {text!r}"

    # BSB without context — pattern matches but no context boost; still detected
    # but at base score 0.8 (routes to advisor in advisor mode). The entity IS
    # returned (fail-open) — the true negative here is the score, not absence.
    async def test_bsb_without_context_has_low_score(self, analyser: AsyncAnalyser) -> None:
        entities = await _detect(analyser, "The sequence 062-000 appears here with no banking context")
        bsbs = [e for e in entities if e.entity_type == EntityType.AU_BSB]
        # BSB format matches; score must be the base score (no context boost)
        assert all(e.score == pytest.approx(0.8) for e in bsbs)
        # And verification must be "advisor" (routes to LLM for contextual check)
        assert all(e.verification == "advisor" for e in bsbs)

    # Purely numeric text — should not trigger PII
    async def test_financial_rates_not_pii(self, analyser: AsyncAnalyser) -> None:
        text = "The fixed interest rate is 5.5 percent per annum over a 30-year term."
        entities = await _detect(analyser, text)
        pii_entities = [e for e in entities if e.is_pii]
        assert len(pii_entities) == 0, f"No PII expected; got: {pii_entities}"

    # Clean text
    async def test_clean_paragraph_no_pii(self, analyser: AsyncAnalyser) -> None:
        text = (
            "The board resolved to approve the annual report for the financial year ended "
            "30 June. Net revenue increased by 12 percent compared to the prior period. "
            "No material changes to capital structure were noted."
        )
        entities = await _detect(analyser, text)
        pii_entities = [e for e in entities if e.is_pii]
        assert len(pii_entities) == 0


# ── ambiguous / edge cases ────────────────────────────────────────────────────


class TestAmbiguous:
    """Near-miss inputs that probe boundary conditions and entity routing metadata."""

    async def test_au_phone_e164_not_matched_by_regex(self, analyser: AsyncAnalyser) -> None:
        # Known limitation: the AUPhoneRecogniser uses \b before \+61, but \b cannot
        # open at a non-word character (+).  International E.164 format prefixed with
        # a space/colon is therefore not matched by the current regex.  This test
        # documents the boundary rather than asserts a bug away.
        entities = await _detect(analyser, "International mobile: +61 412 345 678")
        assert "AU_PHONE" not in _types(entities), (
            "AU_PHONE should NOT be detected for +61 prefixed numbers (\\b anchoring gap). "
            "If this starts failing the recogniser has been fixed — update the test."
        )

    async def test_tfn_without_context_words_still_detected(self, analyser: AsyncAnalyser) -> None:
        # TFN is trust-verified; context words only boost score, not block detection
        entities = await _detect(analyser, "Her number is 123 456 782.")
        assert "AU_TFN" in _types(entities)

    async def test_tfn_has_critical_sensitivity(self, analyser: AsyncAnalyser) -> None:
        entities = await _detect(analyser, "TFN 123 456 782")
        tfns = [e for e in entities if e.entity_type == EntityType.AU_TFN]
        assert all(e.sensitivity == "critical" for e in tfns)
        assert all(e.is_pii for e in tfns)

    async def test_abn_is_not_pii(self, analyser: AsyncAnalyser) -> None:
        # ABN is a business number — flagged as non-PII, low sensitivity
        entities = await _detect(analyser, "ABN 51 824 753 556")
        abns = [e for e in entities if e.entity_type == EntityType.AU_ABN]
        assert len(abns) >= 1
        assert all(not e.is_pii for e in abns)
        assert all(e.sensitivity == "low" for e in abns)

    async def test_acn_is_not_pii(self, analyser: AsyncAnalyser) -> None:
        entities = await _detect(analyser, "ACN 004 085 616")
        acns = [e for e in entities if e.entity_type == EntityType.AU_ACN]
        assert all(not e.is_pii for e in acns)

    async def test_bsb_with_context_has_boosted_score(self, analyser: AsyncAnalyser) -> None:
        # BSB with context word "bsb" → score 0.95 (>= advisor_score_threshold 0.9)
        # so it bypasses the LLM advisor even though verification="advisor"
        entities = await _detect(analyser, "Please transfer to BSB 062-000 account")
        bsbs = [e for e in entities if e.entity_type == EntityType.AU_BSB]
        assert len(bsbs) >= 1
        assert all(e.score >= 0.9 for e in bsbs), "BSB with context should have score ≥ 0.9"
        assert all(e.verification == "advisor" for e in bsbs)  # recogniser declaration unchanged

    async def test_email_sensitivity_is_medium(self, analyser: AsyncAnalyser) -> None:
        entities = await _detect(analyser, "Contact: admin@example.com")
        emails = [e for e in entities if e.entity_type == EntityType.EMAIL_ADDRESS]
        assert all(e.sensitivity == "medium" for e in emails)

    async def test_credit_card_sensitivity_is_critical(self, analyser: AsyncAnalyser) -> None:
        entities = await _detect(analyser, "Charge card 4111111111111111")
        cards = [e for e in entities if e.entity_type == EntityType.CREDIT_CARD]
        assert all(e.sensitivity == "critical" for e in cards)

    async def test_medicare_sensitivity_is_critical(self, analyser: AsyncAnalyser) -> None:
        entities = await _detect(analyser, "Medicare 2123 45670 1")
        meds = [e for e in entities if e.entity_type == EntityType.AU_MEDICARE]
        assert all(e.sensitivity == "critical" for e in meds)

    async def test_entities_sorted_by_start(self, analyser: AsyncAnalyser) -> None:
        text = "Email me at hello@example.com or call 0412 345 678, TFN is 123 456 782."
        result = await analyser.analyse(DetectionRequest(text=text))
        starts = [e.start for e in result.entities]
        assert starts == sorted(starts), "Entities must be sorted by start offset"

    async def test_overlapping_patterns_deduplicated(self, analyser: AsyncAnalyser) -> None:
        # TFN compact and spaced patterns can both match the same span; only one entity should appear
        text = "TFN 123 456 782"
        entities = await _detect(analyser, text)
        tfns = [e for e in entities if e.entity_type == EntityType.AU_TFN]
        assert len(tfns) == 1, "Overlapping recogniser patterns must be deduplicated to a single span"

    async def test_audit_hash_is_hmac_prefixed(self, analyser: AsyncAnalyser) -> None:
        result = await analyser.analyse(DetectionRequest(text="test@example.com"))
        assert result.input_hash.startswith("hmac-sha256:")

    async def test_audit_hash_stable_across_calls(self, analyser: AsyncAnalyser) -> None:
        req = DetectionRequest(text="Billing: billing@example.com, TFN 123 456 782")
        r1 = await analyser.analyse(req)
        r2 = await analyser.analyse(req)
        assert r1.input_hash == r2.input_hash, "Audit hash must be deterministic for the same input"


# ── mixed documents ────────────────────────────────────────────────────────────


class TestMixedDocument:
    """Realistic multi-entity documents exercising the full recogniser stack at once."""

    async def test_home_loan_application(self, analyser: AsyncAnalyser) -> None:
        text = (
            "Applicant email: jane.doe@email.com.au\n"
            "Mobile: 0412 345 678\n"
            "TFN: 123 456 782\n"
            "Medicare: 2123 45670 1\n"
            "ABN 51 824 753 556\n"
            "BSB 062-000 account 12345678"
        )
        entities = await _detect(analyser, text)
        found = _types(entities)
        assert "EMAIL_ADDRESS" in found
        assert "AU_PHONE" in found
        assert "AU_TFN" in found
        assert "AU_MEDICARE" in found
        assert "AU_ABN" in found
        assert "AU_BSB" in found

    async def test_pii_entities_are_marked_is_pii(self, analyser: AsyncAnalyser) -> None:
        text = "Email: x@y.com, TFN 123 456 782, Medicare 2123 45670 1, mobile 0412 345 678"
        entities = await _detect(analyser, text)
        personal = [e for e in entities if e.entity_type in (
            EntityType.EMAIL_ADDRESS, EntityType.AU_TFN,
            EntityType.AU_MEDICARE, EntityType.AU_PHONE,
        )]
        assert all(e.is_pii for e in personal), "Personal identifiers must all have is_pii=True"

    async def test_business_identifiers_are_not_pii(self, analyser: AsyncAnalyser) -> None:
        text = "ABN 51 824 753 556. ACN 004 085 616."
        entities = await _detect(analyser, text)
        business = [e for e in entities if e.entity_type in (EntityType.AU_ABN, EntityType.AU_ACN)]
        assert len(business) >= 1
        assert all(not e.is_pii for e in business), "Business identifiers must have is_pii=False"

    async def test_financial_report_no_false_pii(self, analyser: AsyncAnalyser) -> None:
        # A realistic paragraph that contains no PII — should yield zero is_pii entities
        text = (
            "Total revenue for Q4 was $4.2M, up 8.3% year-on-year. "
            "Operating costs were contained at $1.7M. EBIT margin improved to 17.5%. "
            "The board declared a dividend of $0.12 per share, payable on 15 March."
        )
        entities = await _detect(analyser, text)
        pii = [e for e in entities if e.is_pii]
        assert len(pii) == 0, f"No PII expected in financial report; got: {pii}"


# ── span exactness ────────────────────────────────────────────────────────────


class TestSpanExactness:
    """A detected span must cover the whole identifier.

    Asserting only on entity type lets a truncated span pass: the type is present
    but pseudonymisation leaves the remainder in the clear (``<EMAIL>.au``).
    These cases pin the exact matched text.
    """

    @pytest.mark.parametrize("text,expected", [
        ("Email billing@acme.com.au today", "billing@acme.com.au"),
        ("Contact dev+tag@sub.example.org now", "dev+tag@sub.example.org"),
        ("Write to x@y.co.uk please", "x@y.co.uk"),
        ("Simple a@b.com here", "a@b.com"),
        ("Trailing stop a@b.com.", "a@b.com"),
    ])
    async def test_email_span_is_complete(
        self, analyser: AsyncAnalyser, text: str, expected: str
    ) -> None:
        entities = await _detect(analyser, text)
        emails = [e.text for e in entities if e.entity_type is EntityType.EMAIL_ADDRESS]
        assert expected in emails, f"Expected exact span {expected!r} in {emails!r}"

    @pytest.mark.parametrize("text,expected", [
        ("Call +1 212 555 0123 now", "+1 212 555 0123"),
        ("Ring (212) 555-0123 today", "(212) 555-0123"),
        ("Dial 212-555-0123 please", "212-555-0123"),
        ("Freecall 1-800-555-0199 now", "1-800-555-0199"),
    ])
    async def test_phone_span_is_complete(
        self, analyser: AsyncAnalyser, text: str, expected: str
    ) -> None:
        entities = await _detect(analyser, text)
        phones = [e.text for e in entities if e.entity_type is EntityType.PHONE_NUMBER]
        assert expected in phones, f"Expected exact span {expected!r} in {phones!r}"

    @pytest.mark.parametrize("text,expected", [
        ("London office +44 20 7946 0958 answers", "+44 20 7946 0958"),
        ("Berlin desk +49 30 901820 answers", "+49 30 901820"),
    ])
    async def test_international_phone_detected(
        self, analyser: AsyncAnalyser, text: str, expected: str
    ) -> None:
        """A '+'-prefixed international number must not pass through unredacted."""
        entities = await _detect(analyser, text)
        phones = [e.text for e in entities if e.entity_type is EntityType.PHONE_NUMBER]
        assert expected in phones, f"Expected exact span {expected!r} in {phones!r}"

    async def test_credit_card_not_matched_as_phone(self, analyser: AsyncAnalyser) -> None:
        """The phone lookarounds must not carve a 10-digit span out of a longer number."""
        entities = await _detect(analyser, "Card 4111111111111111 on file")
        phones = [e.text for e in entities if e.entity_type is EntityType.PHONE_NUMBER]
        assert phones == [], f"Expected no PHONE_NUMBER spans; got {phones!r}"

    async def test_partial_match_does_not_displace_full_span(
        self, analyser: AsyncAnalyser
    ) -> None:
        """AU_BSB matches '212-555' inside a phone number; the full span must win.

        Losing the tie redacts only the prefix ('XXX-XXX-0123'), leaking the rest.
        """
        entities = await _detect(analyser, "Dial 212-555-0123 please")
        covering = [e for e in entities if e.start <= 5 and e.end >= 17]
        assert covering, f"No entity covers the whole number; got {[(e.text, e.entity_type.value) for e in entities]}"
