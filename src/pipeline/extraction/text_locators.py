from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from typing import Callable, TypedDict, cast

from src.pipeline.extraction.text_contracts import TextLocatorKind


class TextLocatorHit(TypedDict):
    value: str
    locator_kind: TextLocatorKind
    locator_path: str
    window_base: int


LocatorHandler = Callable[[object, tuple[str, ...]], TextLocatorHit | None]


def _get_zero_arg_method(target: object, name: str) -> Callable[[], object] | None:
    try:
        candidate = getattr(target, name, None)
    except Exception:
        return None

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

    search_from = idx + 1
    while search_from < len(lowered_text):
        next_idx = lowered_text.find(lowered_anchor, search_from)
        if next_idx < 0:
            break
        idx = next_idx
        search_from = next_idx + 1

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
                "value": candidate,
                "locator_kind": "item_window",
                "locator_path": f"items[{key_text}]",
                "window_base": 0,
            }

    return None


def _try_section_window(filing: object, anchors: tuple[str, ...]) -> TextLocatorHit | None:
    sections_method = _get_zero_arg_method(filing, "sections")
    if sections_method is None:
        return None

    try:
        sections = sections_method()
    except Exception:
        return None

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
                    "window_base": 0,
                }

    if isinstance(sections, str):
        for anchor in anchors:
            hit = _window_around_anchor(sections, anchor)
            if hit is None:
                continue
            window, start, _ = hit
            return {
                "value": window,
                "locator_kind": "section_window",
                "locator_path": "sections",
                "window_base": start,
            }

    return None


def _try_parse_text_window(filing: object, anchors: tuple[str, ...]) -> TextLocatorHit | None:
    parse_method = _get_zero_arg_method(filing, "parse")
    parsed_text: object | None = None
    source_path = "parse"

    if parse_method is not None:
        try:
            parsed_text = parse_method()
        except Exception:
            parsed_text = None

    if parsed_text is None:
        text_method = _get_zero_arg_method(filing, "text")
        if text_method is not None:
            try:
                parsed_text = text_method()
                source_path = "text"
            except Exception:
                parsed_text = None
                source_path = "text"

    if not isinstance(parsed_text, str):
        return None

    for anchor in anchors:
        hit = _window_around_anchor(parsed_text, anchor)
        if hit is None:
            continue
        window, start, _ = hit
        return {
            "value": window,
            "locator_kind": "parse_text_window",
            "locator_path": source_path,
            "window_base": start,
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
