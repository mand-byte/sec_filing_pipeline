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
    ) -> None:
        self.calls: list[str] = []
        self._obj_value = obj_value
        self._xbrl_value = xbrl_value
        self._sections_value = sections_value
        self._parse_value = parse_value

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
        self.calls.append("parse_text")
        return self._parse_value


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


def test_locator_chain_falls_back_to_parse_text_in_order() -> None:
    filing = _FakeFiling(obj_value=None, xbrl_value=None, sections_value=[], parse_value="42")

    result = run_locator_chain(
        filing=filing,
        locators=["obj", "xbrl_xml", "sections_search", "parse_text"],
    )

    assert result == {
        "value": "42",
        "locator_kind": "parse_text",
        "locator_path": "parse/text",
    }
    assert filing.calls == ["obj", "xbrl_xml", "sections_search", "parse_text"]
