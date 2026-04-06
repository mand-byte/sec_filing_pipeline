import re

from src.pipeline.extraction.text_contracts import TextFieldSpec
from src.pipeline.extraction.text_engine import TextExtractionEngine


class _Filing:
    def __init__(
        self,
        *,
        items: dict[str, str] | None = None,
        sections_value: object = None,
        parse_value: object = None,
        text_value: object = None,
    ) -> None:
        self.items = items or {}
        self._sections_value = sections_value
        self._parse_value = parse_value
        self._text_value = text_value

    def sections(self) -> object:
        if isinstance(self._sections_value, Exception):
            raise self._sections_value
        return self._sections_value

    def parse(self) -> object:
        if isinstance(self._parse_value, Exception):
            raise self._parse_value
        return self._parse_value

    def text(self) -> object:
        if isinstance(self._text_value, Exception):
            raise self._text_value
        return self._text_value


def test_text_engine_returns_window_not_found() -> None:
    spec = TextFieldSpec(
        field_name="event_text",
        route="issuer",
        form_families=("8-K",),
        locators=("item_window", "section_window", "parse_text_window"),
        anchor_terms=("material definitive agreement",),
        regex_patterns=(r"(?i)\bagreement\b",),
        output_kind="text",
        qa_rules={},
    )
    engine = TextExtractionEngine()
    filing = _Filing(items={}, sections_value={}, parse_value="No relevant disclosure.")

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "error"
    assert outcome["error_code"] == "WINDOW_NOT_FOUND"


def test_text_engine_returns_pattern_not_matched() -> None:
    spec = TextFieldSpec(
        field_name="cash_impact_text",
        route="issuer",
        form_families=("8-K",),
        locators=("item_window",),
        anchor_terms=("item 2.02",),
        regex_patterns=(r"\$([0-9,]+)",),
        output_kind="text",
        qa_rules={},
    )
    engine = TextExtractionEngine()
    filing = _Filing(
        items={
            "Item 2.02": "Item 2.02 Results of Operations and Financial Condition. No dollar value is disclosed.",
        }
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "error"
    assert outcome["error_code"] == "PATTERN_NOT_MATCHED"


def test_text_engine_extracts_text_and_evidence() -> None:
    spec = TextFieldSpec(
        field_name="intent_text",
        route="owner",
        form_families=("13D",),
        locators=("parse_text_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)(board seat representation)",),
        output_kind="text",
        qa_rules={"min_len": 5, "max_len": 80},
    )
    engine = TextExtractionEngine()
    filing = _Filing(
        parse_value=(
            "Cover Page. Purpose of Transaction: the reporting person seeks Board Seat Representation "
            "through constructive engagement with management."
        )
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["value_text"].lower() == "board seat representation"
    assert outcome["value_json"] is None
    assert outcome["locator_kind"] == "parse_text_window"
    assert outcome["locator_path"] == "parse"

    start_text, end_text = outcome["source_span"].split(":")
    start = int(start_text)
    end = int(end_text)
    assert start >= 0
    assert end > start


def test_text_engine_returns_multiple_candidates() -> None:
    spec = TextFieldSpec(
        field_name="candidate_text",
        route="issuer",
        form_families=("8-K",),
        locators=("item_window",),
        anchor_terms=("item 1.01",),
        regex_patterns=(r"(?i)(alpha|beta)",),
        output_kind="text",
        qa_rules={},
    )
    engine = TextExtractionEngine()
    filing = _Filing(items={"Item 1.01": "Item 1.01 disclosure includes alpha and beta references."})

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "error"
    assert outcome["error_code"] == "MULTIPLE_CANDIDATES"


def test_text_engine_returns_qa_failed() -> None:
    spec = TextFieldSpec(
        field_name="qa_text",
        route="owner",
        form_families=("13D",),
        locators=("parse_text_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)(board seat representation)",),
        output_kind="text",
        qa_rules={"max_len": 5},
    )
    engine = TextExtractionEngine()
    filing = _Filing(parse_value="Purpose of Transaction: Board Seat Representation.")

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "error"
    assert outcome["error_code"] == "QA_FAILED"


def test_text_engine_falls_back_after_ambiguous_pattern() -> None:
    spec = TextFieldSpec(
        field_name="fallback_ambiguous",
        route="issuer",
        form_families=("8-K",),
        locators=("item_window",),
        anchor_terms=("item 1.01",),
        regex_patterns=(r"(?i)(alpha|beta)", r"(?i)(board seat representation)"),
        output_kind="text",
        qa_rules={"min_len": 5},
    )
    engine = TextExtractionEngine()
    filing = _Filing(
        items={
            "Item 1.01": "Item 1.01 disclosure includes alpha, beta, and board seat representation.",
        }
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["value_text"].lower() == "board seat representation"


def test_text_engine_falls_back_after_qa_failure() -> None:
    spec = TextFieldSpec(
        field_name="fallback_qa",
        route="owner",
        form_families=("13D",),
        locators=("parse_text_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)(board seat representation)", r"(?i)(constructive)",),
        output_kind="text",
        qa_rules={"max_len": 12},
    )
    engine = TextExtractionEngine()
    filing = _Filing(
        parse_value=(
            "Purpose of Transaction: Board Seat Representation through constructive engagement."
        )
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["value_text"].lower() == "constructive"


def test_text_engine_reports_deterministic_failure_priority_when_all_patterns_fail() -> None:
    spec = TextFieldSpec(
        field_name="all_failures",
        route="owner",
        form_families=("13D",),
        locators=("parse_text_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(
            r"(?i)(alpha|beta)",
            r"(?i)(board seat representation)",
            r"(?i)(nope)",
        ),
        output_kind="text",
        qa_rules={"max_len": 5},
    )
    engine = TextExtractionEngine()
    filing = _Filing(
        parse_value="Purpose of Transaction: alpha, beta, and Board Seat Representation were discussed."
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "error"
    assert outcome["error_code"] == "QA_FAILED"


def test_section_window_extracts_from_list_sections_with_deterministic_locator_path() -> None:
    spec = TextFieldSpec(
        field_name="intent_text",
        route="owner",
        form_families=("13D",),
        locators=("section_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)(board seat representation)",),
        output_kind="text",
        qa_rules={},
    )
    engine = TextExtractionEngine()
    filing = _Filing(
        sections_value=[
            "Cover page and summary content only.",
            "Purpose of Transaction: Board Seat Representation through engagement.",
        ]
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["locator_kind"] == "section_window"
    assert outcome["locator_path"] == "sections[1]"


def test_parse_text_window_falls_back_to_text_when_parse_returns_non_string() -> None:
    spec = TextFieldSpec(
        field_name="intent_text",
        route="owner",
        form_families=("13D",),
        locators=("parse_text_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)(board seat representation)",),
        output_kind="text",
        qa_rules={},
    )
    engine = TextExtractionEngine()

    class _ParsedDocument:
        pass

    filing = _Filing(
        parse_value=_ParsedDocument(),
        text_value="Purpose of Transaction: Board Seat Representation through engagement.",
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["locator_path"] == "text"


def test_parse_text_window_falls_back_to_text_with_text_locator_path() -> None:
    spec = TextFieldSpec(
        field_name="intent_text",
        route="owner",
        form_families=("13D",),
        locators=("parse_text_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)(board seat representation)",),
        output_kind="text",
        qa_rules={},
    )
    engine = TextExtractionEngine()
    filing = _Filing(
        parse_value=None,
        text_value="Purpose of Transaction: Board Seat Representation through engagement.",
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["locator_path"] == "text"


def test_text_engine_reports_source_local_offsets_for_windowed_parse_text() -> None:
    spec = TextFieldSpec(
        field_name="intent_text",
        route="owner",
        form_families=("13D",),
        locators=("parse_text_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)(board seat representation)",),
        output_kind="text",
        qa_rules={},
    )
    engine = TextExtractionEngine()
    long_prefix = "X" * 400
    parse_text = (
        f"{long_prefix}Purpose of Transaction: the reporting person seeks Board Seat Representation "
        "through constructive engagement."
    )
    filing = _Filing(parse_value=parse_text)

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["locator_path"] == "parse"
    full_match = re.search(r"(?i)(board seat representation)", parse_text)
    assert full_match is not None
    expected_start, expected_end = full_match.span(1)
    assert outcome["source_span"] == f"{expected_start}:{expected_end}"


def test_text_engine_rejects_json_output_kind_deterministically() -> None:
    spec = TextFieldSpec(
        field_name="intent_json",
        route="owner",
        form_families=("13D",),
        locators=("parse_text_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)(board seat representation)",),
        output_kind="json",
        qa_rules={},
    )
    engine = TextExtractionEngine()
    filing = _Filing(
        parse_value="Purpose of Transaction: Board Seat Representation through engagement.",
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "error"
    assert outcome["error_code"] == "NORMALIZATION_FAILED"


def test_text_engine_does_not_crash_when_parse_sections_and_text_raise() -> None:
    spec = TextFieldSpec(
        field_name="resilient_locator_chain",
        route="owner",
        form_families=("13D",),
        locators=("section_window", "parse_text_window"),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)(board seat representation)",),
        output_kind="text",
        qa_rules={},
    )
    engine = TextExtractionEngine()
    filing = _Filing(
        sections_value=RuntimeError("sections failed"),
        parse_value=RuntimeError("parse failed"),
        text_value=RuntimeError("text failed"),
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "error"
    assert outcome["error_code"] == "WINDOW_NOT_FOUND"


def test_parse_text_window_prefers_section_like_anchor_over_later_mention() -> None:
    spec = TextFieldSpec(
        field_name="intent_text",
        route="owner",
        form_families=("13D",),
        locators=("parse_text_window",),
        anchor_terms=("purpose of transaction",),
        regex_patterns=(r"(?i)(board seat representation)",),
        output_kind="text",
        qa_rules={},
    )
    engine = TextExtractionEngine()
    parse_text = (
        "Purpose of Transaction: Board Seat Representation is sought through engagement.\n"
        + ("X" * 500)
        + "The filing references the Purpose of Transaction section later for context only."
    )
    filing = _Filing(parse_value=parse_text)

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["value_text"].lower() == "board seat representation"
    assert outcome["locator_kind"] == "parse_text_window"
    assert outcome["locator_path"] == "parse"

    full_match = re.search(r"(?i)(board seat representation)", parse_text)
    assert full_match is not None
    expected_start, expected_end = full_match.span(1)
    assert outcome["source_span"] == f"{expected_start}:{expected_end}"


def test_item_window_includes_header_for_regex_matching() -> None:
    spec = TextFieldSpec(
        field_name="item_header_text",
        route="issuer",
        form_families=("8-K",),
        locators=("item_window",),
        anchor_terms=("item 5.02",),
        regex_patterns=(r"(?i)(item 5\.02)",),
        output_kind="text",
        qa_rules={},
    )
    engine = TextExtractionEngine()
    filing = _Filing(
        items={
            "Item 5.02 Departure of Directors or Certain Officers": "The body text omits the anchor phrase.",
        }
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["value_text"].lower() == "item 5.02"
    assert outcome["locator_kind"] == "item_window"
    assert outcome["locator_path"] == "items[Item 5.02 Departure of Directors or Certain Officers]"
    assert outcome["source_span"] == "header:0:9"


def test_item_window_reports_body_relative_source_span() -> None:
    spec = TextFieldSpec(
        field_name="item_body_text",
        route="issuer",
        form_families=("8-K",),
        locators=("item_window",),
        anchor_terms=("item 5.02",),
        regex_patterns=(r"(?i)(chief financial officer)",),
        output_kind="text",
        qa_rules={},
    )
    engine = TextExtractionEngine()
    body_text = "The board appointed a new Chief Financial Officer effective immediately."
    filing = _Filing(
        items={
            "Item 5.02 Departure of Directors or Certain Officers": body_text,
        }
    )

    outcome = engine.extract_field(filing=filing, field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["value_text"].lower() == "chief financial officer"
    assert outcome["locator_kind"] == "item_window"
    assert outcome["source_span"].count(":") == 1
    assert not outcome["source_span"].startswith("header:")

    body_match = re.search(r"(?i)(chief financial officer)", body_text)
    assert body_match is not None
    expected_start, expected_end = body_match.span(1)
    assert outcome["source_span"] == f"{expected_start}:{expected_end}"
