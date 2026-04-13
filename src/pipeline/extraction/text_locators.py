from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import inspect
from collections.abc import Mapping, Sequence
from typing import Callable, NotRequired, TypedDict, cast

from src.pipeline.extraction.text_contracts import TextLocatorKind


class TextLocatorHit(TypedDict):
    value: str
    locator_kind: TextLocatorKind
    locator_path: str
    window_base: int
    source_section: NotRequired[str]
    source_item_no: NotRequired[str]
    item_body_offset: NotRequired[int]
    section_body_offset: NotRequired[int]


LocatorHandler = Callable[[object, tuple[str, ...]], TextLocatorHit | None]


def _call_quietly(method: Callable[[], object]) -> object:
    """Call a provider method without leaking stdout or stderr noise."""
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return method()


def _get_zero_arg_method(target: object, name: str) -> Callable[[], object] | None:
    """Return a safe zero-argument bound method when the target exposes it."""
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


def _score_anchor_occurrence(text: str, *, anchor_start: int, anchor_end: int) -> int:
    """Score one anchor occurrence so heading-like matches beat TOC noise."""
    line_start = text.rfind("\n", 0, anchor_start) + 1
    line_end = text.find("\n", anchor_end)
    if line_end < 0:
        line_end = len(text)

    line_text = text[line_start:line_end]
    lowered_line = line_text.lower()
    anchor_line_start = anchor_start - line_start
    anchor_line_end = anchor_end - line_start

    before_anchor = lowered_line[:anchor_line_start]
    after_anchor = lowered_line[anchor_line_end:]

    score = 0

    if not before_anchor.strip():
        score += 4
    if after_anchor.lstrip().startswith(":"):
        score += 3
    elif after_anchor.lstrip().startswith("-"):
        score += 1
    if len(line_text.strip()) <= 140:
        score += 1

    nearby_before = text[max(0, anchor_start - 120):anchor_start].lower()
    nearby_window = text[max(0, anchor_start - 120):min(len(text), anchor_end + 120)].lower()

    if "table of contents" in nearby_window:
        score -= 8
    if "index only" in nearby_window or "for index" in nearby_window:
        score -= 4
    if "table of contents" in nearby_before and after_anchor.lstrip().startswith(":"):
        score -= 3

    return score


def _window_around_anchor(text: str, anchor: str, radius: int = 220) -> tuple[str, int, int] | None:
    """Return the best-scoring text window around one anchor term."""
    lowered_text = text.lower()
    lowered_anchor = anchor.lower()

    if not lowered_anchor:
        return None

    best_idx: int | None = None
    best_score: int | None = None

    idx = lowered_text.find(lowered_anchor)
    while idx >= 0:
        anchor_end = idx + len(anchor)
        score = _score_anchor_occurrence(text, anchor_start=idx, anchor_end=anchor_end)
        if best_score is None or score > best_score or (score == best_score and (best_idx is None or idx < best_idx)):
            best_idx = idx
            best_score = score
        idx = lowered_text.find(lowered_anchor, idx + 1)

    if best_idx is None:
        return None

    start = max(0, best_idx - radius)
    end = min(len(text), best_idx + len(anchor) + radius)
    return text[start:end], start, end


def _try_item_window(filing: object, anchors: tuple[str, ...]) -> TextLocatorHit | None:
    """Resolve anchors against filing.items when that structured surface exists."""
    items = getattr(filing, "items", None)
    if not isinstance(items, Mapping):
        return None

    normalized_items = [(str(key), str(value)) for key, value in items.items()]

    for anchor in anchors:
        lowered_anchor = anchor.lower()

        for key_text, value_text in normalized_items:
            if lowered_anchor not in key_text.lower():
                continue
            candidate = f"{key_text}\n{value_text}"
            return {
                "value": candidate,
                "locator_kind": "item_window",
                "locator_path": f"items[{key_text}]",
                "source_section": key_text,
                "source_item_no": key_text,
                "window_base": 0,
                "item_body_offset": len(key_text) + 1,
            }

        for key_text, value_text in normalized_items:
            if lowered_anchor not in value_text.lower():
                continue
            candidate = f"{key_text}\n{value_text}"
            return {
                "value": candidate,
                "locator_kind": "item_window",
                "locator_path": f"items[{key_text}]",
                "source_section": key_text,
                "source_item_no": key_text,
                "window_base": 0,
                "item_body_offset": len(key_text) + 1,
            }

    return None


def _try_section_window(filing: object, anchors: tuple[str, ...]) -> TextLocatorHit | None:
    """Resolve anchors against filing.sections content or headings."""
    sections_method = _get_zero_arg_method(filing, "sections")
    if sections_method is None:
        return None

    try:
        sections = _call_quietly(sections_method)
    except Exception:
        return None

    if sections is None:
        return None

    if isinstance(sections, Mapping):
        normalized_sections = [(str(section_name), str(section_value)) for section_name, section_value in sections.items()]

        for anchor in anchors:
            lowered_anchor = anchor.lower()

            for section_name_text, section_text in normalized_sections:
                if lowered_anchor not in section_name_text.lower():
                    continue
                section_header = section_name_text
                candidate = f"{section_header}\n{section_text}"
                return {
                    "value": candidate,
                    "locator_kind": "section_window",
                    "locator_path": f"sections[{section_name_text}]",
                    "source_section": section_name_text,
                    "window_base": 0,
                    "section_body_offset": len(section_header) + 1,
                }

            for section_name_text, section_text in normalized_sections:
                if lowered_anchor not in section_text.lower():
                    continue
                section_header = section_name_text
                candidate = f"{section_header}\n{section_text}"
                return {
                    "value": candidate,
                    "locator_kind": "section_window",
                    "locator_path": f"sections[{section_name_text}]",
                    "source_section": section_name_text,
                    "window_base": 0,
                    "section_body_offset": len(section_header) + 1,
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
                "source_section": anchor,
                "window_base": start,
            }

    if isinstance(sections, Sequence):
        for anchor in anchors:
            for index, section in enumerate(sections):
                section_text = str(section)
                hit = _window_around_anchor(section_text, anchor)
                if hit is None:
                    continue
                window, start, _ = hit
                section_header = section_text.splitlines()[0].strip() if section_text.splitlines() else str(index)
                return {
                    "value": window,
                    "locator_kind": "section_window",
                    "locator_path": f"sections[{index}]",
                    "source_section": section_header or str(index),
                    "window_base": start,
                }

    return None


def _try_parse_text_window(filing: object, anchors: tuple[str, ...]) -> TextLocatorHit | None:
    """Resolve anchors against parsed full-text content."""
    parse_method = _get_zero_arg_method(filing, "parse")
    parsed_text: object | None = None
    source_path = "parse"

    if parse_method is not None:
        try:
            parsed_text = _call_quietly(parse_method)
        except Exception:
            parsed_text = None

    if not isinstance(parsed_text, str):
        text_method = _get_zero_arg_method(filing, "text")
        if text_method is not None:
            try:
                parsed_text = _call_quietly(text_method)
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


def run_text_locator(*, filing: object, locator: str, anchors: Sequence[str]) -> TextLocatorHit | None:
    """Run one named text locator strategy against the filing."""
    handlers: dict[str, LocatorHandler] = {
        "item_window": _try_item_window,
        "section_window": _try_section_window,
        "parse_text_window": _try_parse_text_window,
    }
    normalized_anchors = tuple(anchor.strip() for anchor in anchors if anchor.strip())
    if not normalized_anchors:
        return None

    handler = handlers.get(locator)
    if handler is None:
        return None

    return handler(filing, normalized_anchors)
