from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal, TypedDict, cast


LocatorKind = Literal["obj", "xbrl_xml", "sections_search", "parse_text"]
LocatorPath = Literal["obj", "xbrl", "sections", "parse/text"]


class LocatorResult(TypedDict):
    value: object
    locator_kind: LocatorKind
    locator_path: LocatorPath


LocatorHandler = Callable[[object], LocatorResult | None]


def _get_zero_arg_method(target: object, name: str) -> Callable[[], object] | None:
    candidate = getattr(target, name, None)
    if not callable(candidate):
        return None
    return cast(Callable[[], object], candidate)


def _try_obj(filing: object) -> LocatorResult | None:
    obj = _get_zero_arg_method(filing, "obj")
    if obj is None:
        return None

    value = obj()
    if value is None:
        return None

    return {"value": value, "locator_kind": "obj", "locator_path": "obj"}


def _try_xbrl_xml(filing: object) -> LocatorResult | None:
    xbrl = _get_zero_arg_method(filing, "xbrl")
    if xbrl is None:
        return None

    value = xbrl()
    if value is None:
        return None

    return {"value": value, "locator_kind": "xbrl_xml", "locator_path": "xbrl"}


def _try_sections_search(filing: object) -> LocatorResult | None:
    sections = _get_zero_arg_method(filing, "sections")
    if sections is None:
        return None

    value = sections()
    if not value:
        return None

    return {
        "value": value,
        "locator_kind": "sections_search",
        "locator_path": "sections",
    }


def _try_parse_text(filing: object) -> LocatorResult | None:
    parsed: object | None = None
    parse = _get_zero_arg_method(filing, "parse")
    if parse is not None:
        parsed = parse()

    if parsed is None:
        text = _get_zero_arg_method(filing, "text")
        if text is not None:
            parsed = text()

    if parsed is None:
        return None

    return {
        "value": parsed,
        "locator_kind": "parse_text",
        "locator_path": "parse/text",
    }


def run_locator_chain(*, filing: object, locators: Sequence[str]) -> LocatorResult | None:
    handlers: dict[str, LocatorHandler] = {
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
