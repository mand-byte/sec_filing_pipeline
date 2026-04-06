from __future__ import annotations

from typing import Any

from src.pipeline.extraction.locators import run_locator_chain


class _FakeFiling:
    def __init__(
        self,
        *,
        obj_value: Any = None,
        xbrl_value: Any = None,
        sections_value: Any = None,
        parse_value: Any = None,
        text_value: Any = None,
    ) -> None:
        self.calls: list[str] = []
        self._obj_value = obj_value
        self._xbrl_value = xbrl_value
        self._sections_value = sections_value
        self._parse_value = parse_value
        self._text_value = text_value

    def obj(self) -> Any:
        self.calls.append("obj")
        return self._obj_value

    def xbrl(self) -> Any:
        self.calls.append("xbrl_xml")
        return self._xbrl_value

    def sections(self) -> Any:
        self.calls.append("sections_search")
        return self._sections_value

    def parse(self) -> Any:
        self.calls.append("parse")
        return self._parse_value

    def text(self) -> Any:
        self.calls.append("text")
        return self._text_value


class _SparseFiling:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.obj = "not-callable"  # validates callable guard

    def xbrl(self) -> dict[str, int]:
        self.calls.append("xbrl_xml")
        return {"value": 7}


class _OnlyTextFiling:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def text(self) -> str:
        self.calls.append("text")
        return "from-text"


def test_locator_chain_uses_fixed_order_and_stops_on_first_hit() -> None:
    filing = _FakeFiling(obj_value=None, xbrl_value={"value": 10}, sections_value=[1], parse_value=999)

    result = run_locator_chain(
        filing=filing,
        locators=["obj", "xbrl_xml", "sections_search", "parse_text"],
    )

    assert result == {
        "value": {"value": 10},
        "locator_kind": "xbrl_xml",
        "locator_path": "xbrl",
    }
    assert filing.calls == ["obj", "xbrl_xml"]


def test_locator_chain_skips_missing_and_non_callable_methods() -> None:
    filing = _SparseFiling()

    result = run_locator_chain(filing=filing, locators=["obj", "xbrl_xml"])

    assert result == {
        "value": {"value": 7},
        "locator_kind": "xbrl_xml",
        "locator_path": "xbrl",
    }
    assert filing.calls == ["xbrl_xml"]


def test_locator_chain_parse_text_falls_back_to_text_method() -> None:
    filing = _OnlyTextFiling()

    result = run_locator_chain(filing=filing, locators=["parse_text"])

    assert result == {
        "value": "from-text",
        "locator_kind": "parse_text",
        "locator_path": "parse/text",
    }
    assert filing.calls == ["text"]


def test_locator_chain_ignores_unknown_locator_entries() -> None:
    filing = _FakeFiling(obj_value="hit")

    result = run_locator_chain(filing=filing, locators=["unknown", "obj"])

    assert result == {
        "value": "hit",
        "locator_kind": "obj",
        "locator_path": "obj",
    }
    assert filing.calls == ["obj"]


def test_locator_chain_returns_none_when_all_locators_miss() -> None:
    filing = _FakeFiling(obj_value=None, xbrl_value=None, sections_value=[], parse_value=None, text_value=None)

    result = run_locator_chain(
        filing=filing,
        locators=["obj", "xbrl_xml", "sections_search", "parse_text"],
    )

    assert result is None
    assert filing.calls == ["obj", "xbrl_xml", "sections_search", "parse", "text"]
