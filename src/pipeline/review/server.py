from __future__ import annotations

from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from sqlalchemy.orm import Session

from src.pipeline.review.workflow import ReviewTaskSummary, ReviewWorkflowError, ReviewWorkflowService, review_task_detail_asdict


_TASK_LIMIT_MIN = 1
_TASK_LIMIT_MAX = 1000


@dataclass(frozen=True)
class ReviewServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    status: str = "open"
    route: str | None = None
    limit: int = 100


def _serialize_task_summary(task: ReviewTaskSummary) -> dict[str, Any]:
    payload = asdict(task)
    payload["created_at"] = task.created_at.isoformat()
    return payload


def build_review_server_html(*, initial_status: str, initial_route: str | None, initial_limit: int) -> str:
    initial_state = {
        "status": initial_status,
        "route": initial_route,
        "limit": initial_limit,
    }
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SEC Review Workbench</title>
  <style>
    :root {{
      --bg: #f2ede6;
      --paper: #fffdf8;
      --ink: #1b1813;
      --muted: #6d6458;
      --accent: #165a72;
      --accent-soft: #dbeef5;
      --line: #ddd2c4;
      --warning: #a8562a;
      --shadow: 0 18px 40px rgba(52, 36, 19, 0.09);
      --mono: "SFMono-Regular", "Menlo", monospace;
      --sans: "Georgia", "Iowan Old Style", serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, #fff5e7, transparent 30%),
        linear-gradient(180deg, #efe7db 0%, var(--bg) 100%);
      font-family: var(--sans);
    }}
    .layout {{
      display: grid;
      grid-template-columns: 320px 1fr;
      min-height: 100vh;
    }}
    .sidebar {{
      padding: 24px 20px;
      border-right: 1px solid var(--line);
      background: rgba(255, 253, 248, 0.78);
      backdrop-filter: blur(8px);
    }}
    .sidebar h1 {{
      margin: 0 0 8px;
      font-size: 1.5rem;
    }}
    .sidebar p {{
      margin: 0 0 18px;
      color: var(--muted);
      line-height: 1.5;
    }}
    .filters {{
      display: grid;
      gap: 12px;
      margin-bottom: 18px;
    }}
    .filters label {{
      display: grid;
      gap: 6px;
      font-size: 0.9rem;
      color: var(--muted);
    }}
    input, select, textarea, button {{
      font: inherit;
    }}
    input, select, textarea {{
      width: 100%;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: var(--paper);
      color: var(--ink);
    }}
    button {{
      border: 0;
      border-radius: 999px;
      padding: 10px 14px;
      cursor: pointer;
      background: var(--accent);
      color: #f7fcff;
    }}
    button.secondary {{
      background: #44545d;
    }}
    .task-list {{
      display: grid;
      gap: 10px;
    }}
    .task-item {{
      width: 100%;
      text-align: left;
      padding: 14px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: var(--paper);
      color: var(--ink);
      box-shadow: var(--shadow);
    }}
    .task-item.active {{
      outline: 2px solid var(--accent);
      background: #f4fbfe;
    }}
    .task-item small {{
      display: block;
      color: var(--muted);
      margin-top: 4px;
      font-family: var(--mono);
    }}
    .content {{
      padding: 28px;
      display: grid;
      gap: 22px;
    }}
    .hero {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: start;
    }}
    .hero h2 {{
      margin: 0 0 4px;
      font-size: 1.6rem;
    }}
    .hero p {{
      margin: 0;
      color: var(--muted);
    }}
    .status-chip {{
      padding: 8px 12px;
      border-radius: 999px;
      background: #183828;
      color: #effaf2;
      font-family: var(--mono);
      font-size: 0.78rem;
      text-transform: uppercase;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
    }}
    .meta-card, .panel, .action-card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
    }}
    .meta-card {{
      padding: 14px 16px;
    }}
    .meta-card span {{
      display: block;
      color: var(--muted);
      font-size: 0.8rem;
      margin-bottom: 6px;
    }}
    .split {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }}
    .panel {{
      padding: 18px;
      min-height: 360px;
    }}
    .panel.evidence {{
      background: linear-gradient(180deg, #fff8ef 0%, #f7eddf 100%);
    }}
    .panel.result {{
      background: linear-gradient(180deg, #f2f8ff 0%, #eaf2fb 100%);
    }}
    .panel-label {{
      margin: 0 0 8px;
      font-family: var(--mono);
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .panel h3 {{
      margin: 0 0 12px;
      font-size: 1.2rem;
    }}
    .field-grid {{
      display: grid;
      grid-template-columns: 120px 1fr;
      gap: 8px 12px;
      margin-bottom: 16px;
    }}
    .field-grid dt {{
      color: var(--muted);
      font-size: 0.86rem;
    }}
    .field-grid dd {{
      margin: 0;
      word-break: break-word;
    }}
    .code-block {{
      border-radius: 18px;
      overflow: hidden;
      border: 1px solid rgba(61, 43, 28, 0.12);
      background: rgba(255, 255, 255, 0.66);
      margin-top: 14px;
    }}
    .code-title {{
      padding: 10px 14px;
      border-bottom: 1px solid rgba(61, 43, 28, 0.12);
      font-family: var(--mono);
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }}
    pre {{
      margin: 0;
      padding: 14px;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: var(--mono);
      font-size: 0.85rem;
      line-height: 1.5;
    }}
    .action-card {{
      padding: 18px;
    }}
    .action-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .notice {{
      margin-top: 10px;
      min-height: 24px;
      color: var(--warning);
      font-size: 0.92rem;
    }}
    @media (max-width: 1080px) {{
      .layout {{ grid-template-columns: 1fr; }}
      .split, .meta-grid, .action-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <h1>Review Workbench</h1>
      <p>Local side-by-side review surface for SEC extraction tasks.</p>
      <div class="filters">
        <label>Status
          <select id="filter-status">
            <option value="open">open</option>
            <option value="corrected">corrected</option>
            <option value="reject">reject</option>
            <option value="not_applicable">not_applicable</option>
            <option value="accept">accept</option>
          </select>
        </label>
        <label>Route
          <select id="filter-route">
            <option value="">all</option>
            <option value="issuer">issuer</option>
            <option value="owner">owner</option>
            <option value="holding">holding</option>
          </select>
        </label>
        <label>Limit
          <input id="filter-limit" type="number" min="1" max="1000" value="{initial_limit}" />
        </label>
        <button id="filter-apply">Refresh Tasks</button>
      </div>
      <div class="task-list" id="task-list"></div>
    </aside>
    <main class="content">
      <section class="hero">
        <div>
          <h2 id="task-title">No task selected</h2>
          <p id="task-subtitle">Select a review task from the left panel.</p>
        </div>
        <div class="status-chip" id="task-status">idle</div>
      </section>
      <section class="meta-grid" id="task-meta"></section>
      <section class="split">
        <article class="panel evidence">
          <p class="panel-label">Evidence Pane</p>
          <h3>Source Context</h3>
          <dl class="field-grid" id="evidence-fields"></dl>
          <div class="code-block">
            <div class="code-title">Locator JSON</div>
            <pre id="evidence-locator-json"></pre>
          </div>
          <div class="code-block">
            <div class="code-title">Heading Path</div>
            <pre id="evidence-heading-path"></pre>
          </div>
          <div class="code-block">
            <div class="code-title">Block Offsets</div>
            <pre id="evidence-block-offsets"></pre>
          </div>
          <div class="code-block">
            <div class="code-title">Adequacy Signals</div>
            <pre id="evidence-adequacy-signals"></pre>
          </div>
          <div class="code-block">
            <div class="code-title">Retry History</div>
            <pre id="evidence-retry-history"></pre>
          </div>
          <div class="code-block">
            <div class="code-title">Selection Trace</div>
            <pre id="evidence-selection-trace"></pre>
          </div>
          <div class="code-block">
            <div class="code-title">Raw Value</div>
            <pre id="evidence-raw"></pre>
          </div>
          <div class="code-block">
            <div class="code-title">Normalized Value</div>
            <pre id="evidence-normalized"></pre>
          </div>
        </article>
        <article class="panel result">
          <p class="panel-label">Extracted Result</p>
          <h3>Persisted Fact</h3>
          <div class="code-block">
            <div class="code-title">Fact Payload</div>
            <pre id="fact-payload"></pre>
          </div>
          <div class="code-block">
            <div class="code-title">Filing Payload</div>
            <pre id="filing-payload"></pre>
          </div>
        </article>
      </section>
      <section class="action-card">
        <h3>Review Actions</h3>
        <div class="action-grid">
          <label>Reviewer
            <input id="reviewer" type="text" placeholder="reviewer name" />
          </label>
          <label>Assignee
            <input id="assignee" type="text" placeholder="assign to" />
          </label>
          <label>Decision
            <select id="decision">
              <option value="accept">accept</option>
              <option value="corrected">corrected</option>
              <option value="reject">reject</option>
              <option value="not_applicable">not_applicable</option>
            </select>
          </label>
          <label>Error Code
            <input id="error-code" type="text" placeholder="required for non-accept" />
          </label>
        </div>
        <label style="display:block; margin-top:16px;">Corrected JSON
          <textarea id="corrected-json" rows="5" placeholder='{{"value_numeric": 123.0}}'></textarea>
        </label>
        <label style="display:block; margin-top:16px;">Comment
          <textarea id="comment" rows="4" placeholder="optional review note"></textarea>
        </label>
        <div style="display:flex; gap:12px; margin-top:16px; flex-wrap:wrap;">
          <button id="assign-button" class="secondary">Assign Task</button>
          <button id="resolve-button">Resolve Task</button>
        </div>
        <div class="notice" id="notice"></div>
      </section>
    </main>
  </div>
  <script>
    const initialState = {json.dumps(initial_state, ensure_ascii=False)};
    const elements = {{
      taskList: document.getElementById("task-list"),
      title: document.getElementById("task-title"),
      subtitle: document.getElementById("task-subtitle"),
      status: document.getElementById("task-status"),
      meta: document.getElementById("task-meta"),
      evidenceFields: document.getElementById("evidence-fields"),
      evidenceLocatorJson: document.getElementById("evidence-locator-json"),
      evidenceHeadingPath: document.getElementById("evidence-heading-path"),
      evidenceBlockOffsets: document.getElementById("evidence-block-offsets"),
      evidenceAdequacySignals: document.getElementById("evidence-adequacy-signals"),
      evidenceRetryHistory: document.getElementById("evidence-retry-history"),
      evidenceSelectionTrace: document.getElementById("evidence-selection-trace"),
      evidenceRaw: document.getElementById("evidence-raw"),
      evidenceNormalized: document.getElementById("evidence-normalized"),
      factPayload: document.getElementById("fact-payload"),
      filingPayload: document.getElementById("filing-payload"),
      reviewer: document.getElementById("reviewer"),
      assignee: document.getElementById("assignee"),
      decision: document.getElementById("decision"),
      errorCode: document.getElementById("error-code"),
      correctedJson: document.getElementById("corrected-json"),
      comment: document.getElementById("comment"),
      notice: document.getElementById("notice"),
      filterStatus: document.getElementById("filter-status"),
      filterRoute: document.getElementById("filter-route"),
      filterLimit: document.getElementById("filter-limit"),
    }};
    let currentTaskId = null;
    let currentTasks = [];

    elements.filterStatus.value = initialState.status || "open";
    elements.filterRoute.value = initialState.route || "";

    function pretty(value) {{
      return JSON.stringify(value ?? null, null, 2);
    }}

    function setNotice(message, isError = true) {{
      elements.notice.textContent = message || "";
      elements.notice.style.color = isError ? "var(--warning)" : "#235739";
    }}

    async function fetchJson(url, options = undefined) {{
      const response = await fetch(url, options);
      const text = await response.text();
      let payload = null;
      try {{
        payload = text ? JSON.parse(text) : null;
      }} catch (error) {{
        throw new Error(text || `Invalid JSON response: ${{response.status}}`);
      }}
      if (!response.ok) {{
        throw new Error(payload?.error || payload?.detail || text || `HTTP ${{response.status}}`);
      }}
      return payload;
    }}

    function renderTaskList(tasks) {{
      currentTasks = tasks;
      elements.taskList.innerHTML = "";
      if (!tasks.length) {{
        const empty = document.createElement("div");
        empty.className = "task-item";
        empty.textContent = "No tasks matched the current filters.";
        elements.taskList.appendChild(empty);
        return;
      }}
      for (const task of tasks) {{
        const button = document.createElement("button");
        button.className = "task-item";
        if (task.task_id === currentTaskId) {{
          button.classList.add("active");
        }}
        button.innerHTML = `<strong>${{task.field_name}}</strong><small>${{task.subject_key}} · ${{task.route}} · ${{task.status}}</small>`;
        button.addEventListener("click", () => loadTask(task.task_id));
        elements.taskList.appendChild(button);
      }}
    }}

    function renderMeta(detail) {{
      const filing = detail.filing || {{}};
      const task = detail.task;
      const cards = [
        ["Accession", task.accession_no],
        ["CIK", filing.cik || ""],
        ["Form", filing.form_type || ""],
        ["Created", task.created_at],
      ];
      elements.meta.innerHTML = cards.map(([label, value]) => `<div class="meta-card"><span>${{label}}</span><strong>${{value ?? ""}}</strong></div>`).join("");
    }}

    function renderFields(target, values) {{
      target.innerHTML = "";
      for (const [label, value] of values) {{
        const dt = document.createElement("dt");
        dt.textContent = label;
        const dd = document.createElement("dd");
        dd.textContent = value ?? "";
        target.appendChild(dt);
        target.appendChild(dd);
      }}
    }}

    async function loadTasks() {{
      setNotice("");
      const params = new URLSearchParams();
      params.set("status", elements.filterStatus.value || "open");
      if (elements.filterRoute.value) {{
        params.set("route", elements.filterRoute.value);
      }}
      params.set("limit", elements.filterLimit.value || "100");
      const tasks = await fetchJson(`/api/tasks?${{params.toString()}}`);
      renderTaskList(tasks);
      if (tasks.length) {{
        await loadTask(tasks[0].task_id);
      }} else {{
        currentTaskId = null;
        elements.title.textContent = "No task selected";
        elements.subtitle.textContent = "Select a review task from the left panel.";
        elements.status.textContent = "idle";
        elements.meta.innerHTML = "";
        elements.evidenceFields.innerHTML = "";
        elements.evidenceLocatorJson.textContent = "";
        elements.evidenceHeadingPath.textContent = "";
        elements.evidenceBlockOffsets.textContent = "";
        elements.evidenceAdequacySignals.textContent = "";
        elements.evidenceRetryHistory.textContent = "";
        elements.evidenceSelectionTrace.textContent = "";
        elements.evidenceRaw.textContent = "";
        elements.evidenceNormalized.textContent = "";
        elements.factPayload.textContent = "";
        elements.filingPayload.textContent = "";
      }}
    }}

    async function loadTask(taskId) {{
      currentTaskId = taskId;
      const detail = await fetchJson(`/api/tasks/${{taskId}}`);
      const task = detail.task;
      const evidence = detail.primary_evidence || {{}};
      elements.title.textContent = `${{task.field_name}} · ${{task.subject_key}}`;
      elements.subtitle.textContent = `${{task.route}} · task ${{task.task_id}}`;
      elements.status.textContent = task.status;
      renderMeta(detail);
      renderFields(elements.evidenceFields, [
        ["Locator", evidence.locator_kind || ""],
        ["XPath / Path", evidence.source_xpath || ""],
        ["Span", evidence.source_span || ""],
        ["Section", evidence.source_section || ""],
        ["Item", evidence.source_item_no || ""],
      ]);
      elements.evidenceLocatorJson.textContent = pretty(evidence.source_locator_json);
      elements.evidenceHeadingPath.textContent = pretty(evidence.source_heading_path_json);
      elements.evidenceBlockOffsets.textContent = pretty(evidence.source_block_offsets_json);
      elements.evidenceAdequacySignals.textContent = pretty(evidence.adequacy_signals_json);
      elements.evidenceRetryHistory.textContent = pretty(evidence.retry_history_json);
      elements.evidenceSelectionTrace.textContent = pretty(evidence.selection_trace_json);
      elements.evidenceRaw.textContent = pretty(evidence.raw_value);
      elements.evidenceNormalized.textContent = pretty(evidence.normalized_value);
      elements.factPayload.textContent = pretty(detail.fact || {{}});
      elements.filingPayload.textContent = pretty(detail.filing || {{}});
      renderTaskList(currentTasks);
    }}

    async function assignTask() {{
      if (!currentTaskId) {{
        setNotice("No task selected.");
        return;
      }}
      await fetchJson(`/api/tasks/${{currentTaskId}}/assign`, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ assignee: elements.assignee.value }}),
      }});
      setNotice("Task assigned.", false);
      await loadTasks();
    }}

    async function resolveTask() {{
      if (!currentTaskId) {{
        setNotice("No task selected.");
        return;
      }}
      let correctedJson = null;
      if (elements.correctedJson.value.trim()) {{
        try {{
          correctedJson = JSON.parse(elements.correctedJson.value);
        }} catch (error) {{
          setNotice("Corrected JSON must be valid JSON.");
          return;
        }}
      }}
      await fetchJson(`/api/tasks/${{currentTaskId}}/resolve`, {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{
          decision: elements.decision.value,
          reviewer: elements.reviewer.value,
          error_code: elements.errorCode.value,
          comment: elements.comment.value,
          corrected_json: correctedJson,
        }}),
      }});
      setNotice("Task resolved.", false);
      elements.correctedJson.value = "";
      elements.comment.value = "";
      elements.errorCode.value = "";
      await loadTasks();
    }}

    document.getElementById("filter-apply").addEventListener("click", loadTasks);
    document.getElementById("assign-button").addEventListener("click", assignTask);
    document.getElementById("resolve-button").addEventListener("click", resolveTask);
    loadTasks().catch((error) => setNotice(error.message));
  </script>
</body>
</html>"""


class ReviewApi:
    def __init__(self, *, session_factory: Callable[[], Any], status: str, route: str | None, limit: int) -> None:
        self.session_factory = session_factory
        self.default_status = status
        self.default_route = route
        self.default_limit = limit

    def list_tasks(self, *, status: str | None = None, route: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        effective_status = self.default_status if status is None else status
        effective_route = self.default_route if route is None else route
        effective_limit = self.default_limit if limit is None else limit
        with self.session_factory() as session:
            service = ReviewWorkflowService(session)
            return [
                _serialize_task_summary(task)
                for task in service.list_tasks(status=effective_status, route=effective_route, limit=effective_limit)
            ]

    def get_task(self, *, task_id: int) -> dict[str, Any]:
        with self.session_factory() as session:
            service = ReviewWorkflowService(session)
            return review_task_detail_asdict(service.get_task_detail(task_id=task_id))

    def assign_task(self, *, task_id: int, assignee: str) -> dict[str, Any]:
        with self.session_factory() as session:
            service = ReviewWorkflowService(session)
            task = service.assign_task(task_id=task_id, assignee=assignee)
            return _serialize_task_summary(task)

    def resolve_task(self, *, task_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        corrected_value = payload.get("corrected_json")
        corrected_json = None
        if corrected_value is not None:
            corrected_json = corrected_value if isinstance(corrected_value, str) else json.dumps(corrected_value, ensure_ascii=False)
        with self.session_factory() as session:
            service = ReviewWorkflowService(session)
            task = service.resolve_task(
                task_id=task_id,
                decision=str(payload.get("decision", "")),
                reviewer=str(payload.get("reviewer", "")),
                error_code=payload.get("error_code"),
                comment=payload.get("comment"),
                corrected_json=corrected_json,
            )
            return _serialize_task_summary(task)


def _json_response(handler: BaseHTTPRequestHandler, *, status: HTTPStatus, payload: dict[str, Any] | list[Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status.value)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _text_response(handler: BaseHTTPRequestHandler, *, status: HTTPStatus, content_type: str, body: str) -> None:
    data = body.encode("utf-8")
    handler.send_response(status.value)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def create_review_http_handler(
    *,
    api: ReviewApi,
) -> type[BaseHTTPRequestHandler]:
    class ReviewHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlsplit(self.path)
            if parsed.path == "/":
                _text_response(
                    self,
                    status=HTTPStatus.OK,
                    content_type="text/html; charset=utf-8",
                    body=build_review_server_html(
                        initial_status=api.default_status,
                        initial_route=api.default_route,
                        initial_limit=api.default_limit,
                    ),
                )
                return

            if parsed.path == "/api/tasks":
                params = parse_qs(parsed.query)
                status = params.get("status", [None])[0]
                route = params.get("route", [None])[0]
                limit_raw = params.get("limit", [None])[0]
                limit = None
                if limit_raw:
                    try:
                        limit = int(limit_raw)
                    except ValueError:
                        _json_response(self, status=HTTPStatus.BAD_REQUEST, payload={"error": "limit must be an integer"})
                        return
                    if limit < _TASK_LIMIT_MIN or limit > _TASK_LIMIT_MAX:
                        _json_response(
                            self,
                            status=HTTPStatus.BAD_REQUEST,
                            payload={"error": f"limit must be between {_TASK_LIMIT_MIN} and {_TASK_LIMIT_MAX}"},
                        )
                        return
                _json_response(
                    self,
                    status=HTTPStatus.OK,
                    payload=api.list_tasks(status=status, route=route or None, limit=limit),
                )
                return

            if parsed.path.startswith("/api/tasks/"):
                suffix = parsed.path.removeprefix("/api/tasks/")
                if suffix.isdigit():
                    try:
                        payload = api.get_task(task_id=int(suffix))
                    except ReviewWorkflowError as exc:
                        _json_response(self, status=HTTPStatus.NOT_FOUND, payload={"error": str(exc)})
                        return
                    _json_response(self, status=HTTPStatus.OK, payload=payload)
                    return

            _json_response(self, status=HTTPStatus.NOT_FOUND, payload={"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlsplit(self.path)
            if not parsed.path.startswith("/api/tasks/"):
                _json_response(self, status=HTTPStatus.NOT_FOUND, payload={"error": "not found"})
                return

            suffix = parsed.path.removeprefix("/api/tasks/")
            if suffix.endswith("/assign"):
                task_id_text = suffix.removesuffix("/assign")
                action = "assign"
            elif suffix.endswith("/resolve"):
                task_id_text = suffix.removesuffix("/resolve")
                action = "resolve"
            else:
                _json_response(self, status=HTTPStatus.NOT_FOUND, payload={"error": "not found"})
                return

            if not task_id_text.isdigit():
                _json_response(self, status=HTTPStatus.BAD_REQUEST, payload={"error": "task id must be numeric"})
                return

            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
            try:
                payload = json.loads(raw_body)
            except json.JSONDecodeError:
                _json_response(self, status=HTTPStatus.BAD_REQUEST, payload={"error": "request body must be valid json"})
                return
            if not isinstance(payload, dict):
                _json_response(self, status=HTTPStatus.BAD_REQUEST, payload={"error": "request body must be a JSON object"})
                return

            task_id = int(task_id_text)
            try:
                if action == "assign":
                    response = api.assign_task(task_id=task_id, assignee=str(payload.get("assignee", "")))
                else:
                    response = api.resolve_task(task_id=task_id, payload=payload)
            except ReviewWorkflowError as exc:
                _json_response(self, status=HTTPStatus.BAD_REQUEST, payload={"error": str(exc)})
                return

            _json_response(self, status=HTTPStatus.OK, payload=response)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    return ReviewHandler


def run_review_server(
    *,
    session_factory: Callable[[], Any],
    config: ReviewServerConfig,
) -> None:
    api = ReviewApi(
        session_factory=session_factory,
        status=config.status,
        route=config.route,
        limit=config.limit,
    )
    handler = create_review_http_handler(api=api)
    server = ThreadingHTTPServer((config.host, config.port), handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()
