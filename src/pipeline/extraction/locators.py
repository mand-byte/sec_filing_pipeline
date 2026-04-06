from __future__ import annotations

from typing import Any, Callable


def _try_obj(filing: Any) -> dict[str, Any] | None:
    value = filing.obj() if hasattr(filing, "obj") else None
    if value is None:
        return None
    return {"value": value, "locator_kind": "obj", "locator_path": "obj"}


def _try_xbrl_xml(filing: Any) -> dict[str, Any] | None:
    value = filing.xbrl() if hasattr(filing, "xbrl") else None
    if value is None:
        return None
    return {"value": value, "locator_kind": "xbrl_xml", "locator_path": "xbrl"}


def _try_sections_search(filing: Any) -> dict[str, Any] | None:
    value = filing.sections() if hasattr(filing, "sections") else None
    if not value:
        return None
    return {
        "value": value,
        "locator_kind": "sections_search",
        "locator_path": "sections",
    }


def _try_parse_text(filing: Any) -> dict[str, Any] | None:
    parsed = filing.parse() if hasattr(filing, "parse") else None
    if parsed is None and hasattr(filing, "text"):
        parsed = filing.text()
    if parsed is None:
        return None
    return {
        "value": parsed,
        "locator_kind": "parse_text",
        "locator_path": "parse/text",
    }


def run_locator_chain(*, filing: Any, locators: list[str]) -> dict[str, Any] | None:
    handlers: dict[str, Callable[[Any], dict[str, Any] | None]] = {
        "obj": _try_obj,
        "xbrl_xml": _try_xbrl_xml,
        "sections_search": _try_sections_search,
        "parse_text": _try_parse_text,
    }

    for locator in locators:
        handler = handlers.get(locator)
        if handler is None:
            continue
        result = handler(filing)
        if result is not None:
            return result

    return None
