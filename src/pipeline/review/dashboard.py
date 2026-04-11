from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re
from typing import Any

from src.pipeline.review.workflow import ReviewWorkflowService, review_task_detail_asdict


_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_name(value: object, *, fallback: str) -> str:
    text = str(value).strip()
    if not text:
        return fallback
    sanitized = _NAME_RE.sub("_", text).strip("._")
    return sanitized or fallback


def _json_pretty(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def build_review_dashboard_packets(
    *,
    service: ReviewWorkflowService,
    status: str = "open",
    route: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    packets: list[dict[str, Any]] = []
    for task in service.list_tasks(status=status, route=route, limit=limit):
        packets.append(review_task_detail_asdict(service.get_task_detail(task_id=task.task_id)))
    return packets


def _render_task_card(packet: dict[str, Any]) -> str:
    task = packet["task"]
    filing = packet.get("filing") or {}
    fact = packet.get("fact") or {}
    evidence = packet.get("primary_evidence") or {}
    task_title = f"{task['field_name']} · {task['subject_key']} · task {task['task_id']}"

    return f"""
<section class="task-card" id="task-{escape(str(task['task_id']))}">
  <header class="task-header">
    <div>
      <p class="eyebrow">{escape(str(task['route']))}</p>
      <h2>{escape(task_title)}</h2>
    </div>
    <div class="meta-chip">{escape(str(task['status']))}</div>
  </header>
  <div class="task-meta-grid">
    <div><span>Accession</span><strong>{escape(str(task['accession_no']))}</strong></div>
    <div><span>CIK</span><strong>{escape(str(filing.get('cik', '')))}</strong></div>
    <div><span>Form</span><strong>{escape(str(filing.get('form_type', '')))}</strong></div>
    <div><span>Created</span><strong>{escape(str(task['created_at']))}</strong></div>
  </div>
  <div class="split-pane">
    <article class="pane pane-evidence">
      <p class="pane-label">Evidence Pane</p>
      <h3>Source Context</h3>
      <dl>
        <dt>Locator</dt><dd>{escape(str(evidence.get('locator_kind', '')))}</dd>
        <dt>XPath / Path</dt><dd>{escape(str(evidence.get('source_xpath', '')))}</dd>
        <dt>Span</dt><dd>{escape(str(evidence.get('source_span', '')))}</dd>
        <dt>Section</dt><dd>{escape(str(evidence.get('source_section', '')))}</dd>
        <dt>Item</dt><dd>{escape(str(evidence.get('source_item_no', '')))}</dd>
      </dl>
      <div class="code-block">
        <div class="code-title">Locator JSON</div>
        <pre>{escape(_json_pretty(evidence.get('source_locator_json')))}</pre>
      </div>
      <div class="code-block">
        <div class="code-title">Heading Path</div>
        <pre>{escape(_json_pretty(evidence.get('source_heading_path_json')))}</pre>
      </div>
      <div class="code-block">
        <div class="code-title">Block Offsets</div>
        <pre>{escape(_json_pretty(evidence.get('source_block_offsets_json')))}</pre>
      </div>
      <div class="code-block">
        <div class="code-title">Adequacy Signals</div>
        <pre>{escape(_json_pretty(evidence.get('adequacy_signals_json')))}</pre>
      </div>
      <div class="code-block">
        <div class="code-title">Retry History</div>
        <pre>{escape(_json_pretty(evidence.get('retry_history_json')))}</pre>
      </div>
      <div class="code-block">
        <div class="code-title">Raw Value</div>
        <pre>{escape(_json_pretty(evidence.get('raw_value')))}</pre>
      </div>
      <div class="code-block">
        <div class="code-title">Normalized Value</div>
        <pre>{escape(_json_pretty(evidence.get('normalized_value')))}</pre>
      </div>
    </article>
    <article class="pane pane-result">
      <p class="pane-label">Extracted Result</p>
      <h3>Persisted Fact</h3>
      <div class="code-block">
        <div class="code-title">Fact Payload</div>
        <pre>{escape(_json_pretty(fact))}</pre>
      </div>
      <div class="code-block">
        <div class="code-title">Review Guidance</div>
        <pre>{escape(_json_pretty({
            'assign': f"uv run python main.py review-assign {task['task_id']} <assignee>",
            'accept': f"uv run python main.py review-resolve {task['task_id']} --decision accept --reviewer <name>",
            'corrected': f"uv run python main.py review-resolve {task['task_id']} --decision corrected --reviewer <name> --error-code <code> --corrected-json '{{}}'",
            'reject': f"uv run python main.py review-resolve {task['task_id']} --decision reject --reviewer <name> --error-code <code>",
        }))}</pre>
      </div>
    </article>
  </div>
</section>
"""


def render_review_dashboard_html(*, packets: list[dict[str, Any]]) -> str:
    nav_links = "\n".join(
        f'<a href="#task-{escape(str(packet["task"]["task_id"]))}">{escape(packet["task"]["field_name"])} · {escape(packet["task"]["subject_key"])}</a>'
        for packet in packets
    ) or "<span>No tasks</span>"
    task_cards = "\n".join(_render_task_card(packet) for packet in packets) or "<p class=\"empty-state\">No review tasks matched the current filters.</p>"
    summary = {
        "task_count": len(packets),
        "task_ids": [packet["task"]["task_id"] for packet in packets],
    }

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SEC Review Dashboard</title>
  <style>
    :root {{
      --bg: #f4efe7;
      --paper: #fffdf8;
      --ink: #1a1814;
      --muted: #6f6558;
      --accent: #aa5a2d;
      --accent-soft: #f3d8c7;
      --line: #dfd2c2;
      --shadow: 0 18px 40px rgba(63, 41, 20, 0.08);
      --mono: "SFMono-Regular", "Menlo", monospace;
      --sans: "Georgia", "Iowan Old Style", serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #fff6e7, transparent 34%),
        linear-gradient(180deg, #efe7db 0%, var(--bg) 100%);
      font-family: var(--sans);
    }}
    .shell {{
      display: grid;
      grid-template-columns: 280px 1fr;
      min-height: 100vh;
    }}
    .sidebar {{
      padding: 28px 22px;
      border-right: 1px solid var(--line);
      background: rgba(255, 253, 248, 0.72);
      backdrop-filter: blur(10px);
      position: sticky;
      top: 0;
      align-self: start;
      min-height: 100vh;
    }}
    .sidebar h1 {{
      margin: 0 0 8px;
      font-size: 1.6rem;
    }}
    .sidebar p {{
      margin: 0 0 22px;
      color: var(--muted);
      line-height: 1.5;
    }}
    .nav {{
      display: grid;
      gap: 10px;
    }}
    .nav a, .nav span {{
      display: block;
      text-decoration: none;
      color: var(--ink);
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px 14px;
      box-shadow: var(--shadow);
      font-size: 0.95rem;
    }}
    .summary {{
      margin-top: 20px;
      padding: 14px;
      border-radius: 16px;
      background: var(--accent-soft);
      border: 1px solid #e4b89a;
      font-family: var(--mono);
      font-size: 0.85rem;
      white-space: pre-wrap;
    }}
    .content {{
      padding: 32px;
      display: grid;
      gap: 28px;
    }}
    .task-card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 26px;
      box-shadow: var(--shadow);
      padding: 24px;
    }}
    .task-header {{
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 20px;
      margin-bottom: 18px;
    }}
    .task-header h2 {{
      margin: 4px 0 0;
      font-size: 1.5rem;
    }}
    .eyebrow {{
      margin: 0;
      font-family: var(--mono);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--accent);
    }}
    .meta-chip {{
      padding: 8px 12px;
      border-radius: 999px;
      background: #1f3b2d;
      color: #f2fbf5;
      font-family: var(--mono);
      font-size: 0.78rem;
      text-transform: uppercase;
    }}
    .task-meta-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .task-meta-grid div {{
      padding: 12px 14px;
      border-radius: 16px;
      background: #fbf5ec;
      border: 1px solid var(--line);
    }}
    .task-meta-grid span {{
      display: block;
      font-size: 0.8rem;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .split-pane {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }}
    .pane {{
      padding: 18px;
      border-radius: 22px;
      border: 1px solid var(--line);
      min-height: 320px;
    }}
    .pane-evidence {{
      background: linear-gradient(180deg, #fff8ef 0%, #f9efe1 100%);
    }}
    .pane-result {{
      background: linear-gradient(180deg, #f4f8ff 0%, #edf3fb 100%);
    }}
    .pane-label {{
      margin: 0 0 8px;
      font-family: var(--mono);
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .pane h3 {{
      margin: 0 0 14px;
      font-size: 1.2rem;
    }}
    dl {{
      margin: 0 0 18px;
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 8px 12px;
    }}
    dt {{
      color: var(--muted);
      font-size: 0.86rem;
    }}
    dd {{
      margin: 0;
      word-break: break-word;
    }}
    .code-block {{
      margin-top: 14px;
      border-radius: 18px;
      overflow: hidden;
      border: 1px solid rgba(60, 43, 28, 0.12);
      background: rgba(255, 255, 255, 0.62);
    }}
    .code-title {{
      padding: 10px 14px;
      border-bottom: 1px solid rgba(60, 43, 28, 0.12);
      font-family: var(--mono);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }}
    pre {{
      margin: 0;
      padding: 14px;
      overflow: auto;
      font-family: var(--mono);
      font-size: 0.86rem;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .empty-state {{
      padding: 36px;
      border-radius: 24px;
      border: 1px dashed var(--line);
      background: rgba(255,255,255,0.5);
      color: var(--muted);
      text-align: center;
    }}
    @media (max-width: 980px) {{
      .shell {{ grid-template-columns: 1fr; }}
      .sidebar {{ min-height: auto; position: static; border-right: 0; border-bottom: 1px solid var(--line); }}
      .split-pane, .task-meta-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <h1>Review Desk</h1>
      <p>Static side-by-side review export for SEC filing extraction tasks.</p>
      <nav class="nav">{nav_links}</nav>
      <div class="summary">{escape(_json_pretty(summary))}</div>
    </aside>
    <main class="content">
      {task_cards}
    </main>
  </div>
</body>
</html>"""


def write_review_dashboard(
    *,
    output_dir: Path,
    packets: list[dict[str, Any]],
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "packets.json").write_text(
        json.dumps(packets, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "index.html").write_text(
        render_review_dashboard_html(packets=packets),
        encoding="utf-8",
    )
    return output_dir.resolve()
