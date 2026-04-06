from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from typing import Callable, TypedDict, cast

from src.pipeline.extraction.text_contracts import TextLocatorKind


class TextLocatorHit(TypedDict):
    value: str
    locator_kind: TextLocatorKind
    locator_path: str


LocatorHandler = Callable[[object, tuple[str, ...]], TextLocatorHit | None]


def _get_zero_arg_method(target: object, name: str) -> Callable[[], object] | None:
    candidate = getattr(target, name, None)
    if not callable(candidate):
        return None

    try:
        inspect.signature(candidate).bind()
    except (TypeError, ValueError):
        return None

    return cast(Callable[[], object], candidate)


def _window_around_anchor(text: str, anchor: str, radius: int = 220) -> tuple[str, int, int] | None:
    lowered_text = text.lower()
    lowered_anchor = anchor.lower()
    idx = lowered_text.find(lowered_anchor)
    if idx < 0:
        return None

    start = max(0, idx - radius)
    end = min(len(text), idx + len(anchor) + radius)
    return text[start:end], start, end


def _try_item_window(filing: object, anchors: tuple[str, ...]) -> TextLocatorHit | None:
    items = getattr(filing, "items", None)
    if not isinstance(items, Mapping):
        return None

    for anchor in anchors:
        for key, value in items.items():
            key_text = str(key)
            value_text = str(value)
            candidate = f"{key_text}\n{value_text}"
            if anchor.lower() not in candidate.lower():
                continue
            return {
                "value": value_text,
                "locator_kind": "item_window",
                "locator_path": f"items[{key_text}]",
            }

    return None


def _try_section_window(filing: object, anchors: tuple[str, ...]) -> TextLocatorHit | None:
    sections_method = _get_zero_arg_method(filing, "sections")
    if sections_method is None:
        return None

    sections = sections_method()
    if sections is None:
        return None

    if isinstance(sections, Mapping):
        for anchor in anchors:
            for section_name, section_value in sections.items():
                section_name_text = str(section_name)
                section_text = str(section_value)
                combined = f"{section_name_text}\n{section_text}"
                if anchor.lower() not in combined.lower():
                    continue
                return {
                    "value": section_text,
                    "locator_kind": "section_window",
                    "locator_path": f"sections[{section_name_text}]",
                }

    if isinstance(sections, str):
        for anchor in anchors:
            hit = _window_around_anchor(sections, anchor)
            if hit is None:
                continue
            window, _, _ = hit
            return {
                "value": window,
                "locator_kind": "section_window",
                "locator_path": "sections",
            }

    return None


def _try_parse_text_window(filing: object, anchors: tuple[str, ...]) -> TextLocatorHit | None:
    parse_method = _get_zero_arg_method(filing, "parse")
    parsed_text: object | None = parse_method() if parse_method is not None else None

    if parsed_text is None:
        text_method = _get_zero_arg_method(filing, "text")
        parsed_text = text_method() if text_method is not None else None

    if not isinstance(parsed_text, str):
        return None

    for anchor in anchors:
        hit = _window_around_anchor(parsed_text, anchor)
        if hit is None:
            continue
        window, _, _ = hit
        return {
            "value": window,
            "locator_kind": "parse_text_window",
            "locator_path": "parse",
        }

    return None


def run_text_locator_chain(*, filing: object, locators: Sequence[str], anchors: Sequence[str]) -> TextLocatorHit | None:
    handlers: dict[str, LocatorHandler] = {
        "item_window": _try_item_window,
        "section_window": _try_section_window,
        "parse_text_window": _try_parse_text_window,
    }
    normalized_anchors = tuple(anchor.strip() for anchor in anchors if anchor.strip())
    if not normalized_anchors:
        return None

    for locator in locators:
        handler = handlers.get(locator)
        if handler is None:
            continue

        hit = handler(filing, normalized_anchors)
        if hit is not None:
            return hit

    return None
