from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import inspect
import io
from collections.abc import Callable, Sequence
from typing import Literal, TypedDict, cast


LocatorKind = Literal["obj", "xbrl_xml", "sections_search", "parse_text"]
LocatorPath = Literal["obj", "xbrl", "sections", "parse/text"]


class LocatorResult(TypedDict):
    value: object
    locator_kind: LocatorKind
    locator_path: LocatorPath


LocatorHandler = Callable[[object], LocatorResult | None]


def _call_quietly(method: Callable[[], object]) -> object:
    """Call a provider method without leaking stdout or stderr noise."""
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return method()


def _get_zero_arg_method(target: object, name: str) -> Callable[[], object] | None:
    """Return a bound zero-argument method when the target exposes one safely."""
    candidate = getattr(target, name, None)
    if not callable(candidate):
        return None

    try:
        inspect.signature(candidate).bind()
    except TypeError:
        return None
    except ValueError:
        return None

    return cast(Callable[[], object], candidate)


def _try_obj(filing: object) -> LocatorResult | None:
    """Resolve the filing's object-backed extraction surface."""
    obj = _get_zero_arg_method(filing, "obj")
    if obj is None:
        return None

    value = _call_quietly(obj)
    if value is None:
        return None

    return {"value": value, "locator_kind": "obj", "locator_path": "obj"}


def _try_xbrl_xml(filing: object) -> LocatorResult | None:
    """Resolve the filing's XBRL extraction surface."""
    xbrl = _get_zero_arg_method(filing, "xbrl")
    if xbrl is None:
        return None

    value = _call_quietly(xbrl)
    if value is None:
        return None

    return {"value": value, "locator_kind": "xbrl_xml", "locator_path": "xbrl"}


def _try_sections_search(filing: object) -> LocatorResult | None:
    """Resolve the filing's section-search extraction surface."""
    sections = _get_zero_arg_method(filing, "sections")
    if sections is None:
        return None

    value = _call_quietly(sections)
    if not value:
        return None

    return {
        "value": value,
        "locator_kind": "sections_search",
        "locator_path": "sections",
    }


def _try_parse_text(filing: object) -> LocatorResult | None:
    """Resolve parsed or plain-text extraction content from the filing."""
    parsed: object | None = None
    parse = _get_zero_arg_method(filing, "parse")
    if parse is not None:
        parsed = _call_quietly(parse)

    if parsed is None:
        text = _get_zero_arg_method(filing, "text")
        if text is not None:
            parsed = _call_quietly(text)

    if parsed is None:
        return None

    return {
        "value": parsed,
        "locator_kind": "parse_text",
        "locator_path": "parse/text",
    }


def run_locator_chain(*, filing: object, locators: Sequence[str]) -> LocatorResult | None:
    """Try locator strategies in order and return the first available result."""
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
