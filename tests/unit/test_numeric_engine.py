from src.pipeline.extraction.contracts import NumericFieldSpec
from src.pipeline.extraction.engine import NumericExtractionEngine


class _Filing:
    def __init__(self, value):
        self._value = value

    def obj(self):
        return {"value": self._value}

    def xbrl(self):
        return None

    def sections(self):
        return []

    def parse(self):
        return None


class _NoHitFiling(_Filing):
    def obj(self):
        return None


def test_engine_returns_field_not_found_error_when_no_candidate() -> None:
    spec = NumericFieldSpec(
        field_name="total_revenue",
        route="issuer",
        form_families=("10-K",),
        value_type="float",
        locators=("obj",),
        qa_rules={},
    )
    engine = NumericExtractionEngine()

    outcome = engine.extract_field(filing=_NoHitFiling(None), field_spec=spec)

    assert outcome["status"] == "error"
    assert outcome["error_code"] == "FIELD_NOT_FOUND"


def test_engine_applies_min_max_qa() -> None:
    spec = NumericFieldSpec(
        field_name="diluted_eps",
        route="issuer",
        form_families=("10-K",),
        value_type="float",
        locators=("obj",),
        qa_rules={"min": -100.0, "max": 100.0},
    )
    engine = NumericExtractionEngine()

    good = engine.extract_field(filing=_Filing(2.5), field_spec=spec)
    bad = engine.extract_field(filing=_Filing(200.0), field_spec=spec)

    assert good["status"] == "ok"
    assert good["value_raw"] == 2.5
    assert good["value_normalized"] == 2.5
    assert good["locator_kind"] == "obj"
    assert good["locator_path"] == "obj"

    assert bad["status"] == "error"
    assert bad["error_code"] == "VALUE_OUT_OF_RANGE"


def test_engine_applies_nonnegative_qa_rule() -> None:
    spec = NumericFieldSpec(
        field_name="operating_cash_flow",
        route="issuer",
        form_families=("10-K",),
        value_type="float",
        locators=("obj",),
        qa_rules={"nonnegative": True},
    )
    engine = NumericExtractionEngine()

    ok = engine.extract_field(filing=_Filing(0.0), field_spec=spec)
    violation = engine.extract_field(filing=_Filing(-0.01), field_spec=spec)

    assert ok["status"] == "ok"
    assert violation["status"] == "error"
    assert violation["error_code"] == "VALUE_OUT_OF_RANGE"


def test_engine_returns_type_mismatch_for_non_numeric_value() -> None:
    spec = NumericFieldSpec(
        field_name="total_revenue",
        route="issuer",
        form_families=("10-K",),
        value_type="float",
        locators=("obj",),
        qa_rules={},
    )
    engine = NumericExtractionEngine()

    outcome = engine.extract_field(filing=_Filing("not-a-number"), field_spec=spec)

    assert outcome["status"] == "error"
    assert outcome["error_code"] == "TYPE_MISMATCH"


def test_engine_returns_type_mismatch_for_fractional_int_field() -> None:
    spec = NumericFieldSpec(
        field_name="shares_outstanding",
        route="issuer",
        form_families=("10-K",),
        value_type="int",
        locators=("obj",),
        qa_rules={},
    )
    engine = NumericExtractionEngine()

    outcome = engine.extract_field(filing=_Filing("10.5"), field_spec=spec)

    assert outcome["status"] == "error"
    assert outcome["error_code"] == "TYPE_MISMATCH"


def test_engine_returns_type_mismatch_for_non_finite_values() -> None:
    spec = NumericFieldSpec(
        field_name="total_revenue",
        route="issuer",
        form_families=("10-K",),
        value_type="float",
        locators=("obj",),
        qa_rules={},
    )
    engine = NumericExtractionEngine()

    nan_outcome = engine.extract_field(filing=_Filing("nan"), field_spec=spec)
    inf_outcome = engine.extract_field(filing=_Filing("inf"), field_spec=spec)

    assert nan_outcome["status"] == "error"
    assert nan_outcome["error_code"] == "TYPE_MISMATCH"
    assert inf_outcome["status"] == "error"
    assert inf_outcome["error_code"] == "TYPE_MISMATCH"


def test_engine_ignores_boolean_min_max_qa_thresholds() -> None:
    spec = NumericFieldSpec(
        field_name="operating_income",
        route="issuer",
        form_families=("10-K",),
        value_type="float",
        locators=("obj",),
        qa_rules={"min": True, "max": False},
    )
    engine = NumericExtractionEngine()

    outcome = engine.extract_field(filing=_Filing(0.5), field_spec=spec)

    assert outcome["status"] == "ok"
    assert outcome["value_normalized"] == 0.5
