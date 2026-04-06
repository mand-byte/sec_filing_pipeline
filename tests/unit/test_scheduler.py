import re
from dataclasses import dataclass

from src.pipeline.scheduler import build_blocking_scheduler, make_run_id, run_single_tick


@dataclass
class _Security:
    cik: str


class _RecordingRouter:
    def __init__(self, name: str, calls: list[tuple[str, str]], should_raise: bool = False):
        self.name = name
        self._calls = calls
        self._should_raise = should_raise

    def run(self, *, security: _Security) -> None:
        self._calls.append((self.name, security.cik))
        if self._should_raise:
            raise RuntimeError("boom")


class _RecordingRepo:
    def __init__(self):
        self.logs: list[dict[str, object]] = []

    def write_log(self, **kwargs) -> None:
        self.logs.append(kwargs)


class _FailingLogRepo:
    def __init__(self):
        self.write_attempts = 0

    def write_log(self, **kwargs) -> None:
        self.write_attempts += 1
        raise RuntimeError("log sink down")


def test_run_single_tick_calls_routers_in_order_for_each_security():
    calls: list[tuple[str, str]] = []
    routers = [
        _RecordingRouter("issuer", calls),
        _RecordingRouter("owner", calls),
        _RecordingRouter("holding", calls),
    ]

    run_single_tick(
        run_id="run-001",
        securities=[_Security(cik="0000320193"), _Security(cik="0000789019")],
        routers=routers,
        repo=_RecordingRepo(),
    )

    assert calls == [
        ("issuer", "0000320193"),
        ("owner", "0000320193"),
        ("holding", "0000320193"),
        ("issuer", "0000789019"),
        ("owner", "0000789019"),
        ("holding", "0000789019"),
    ]


def test_run_single_tick_logs_router_failed_with_required_fields_and_continues():
    calls: list[tuple[str, str]] = []
    repo = _RecordingRepo()
    routers = [
        _RecordingRouter("issuer", calls),
        _RecordingRouter("owner", calls, should_raise=True),
        _RecordingRouter("holding", calls),
    ]

    run_single_tick(
        run_id="run-002",
        securities=[_Security(cik="0000320193"), _Security(cik="0000789019")],
        routers=routers,
        repo=repo,
    )

    assert calls == [
        ("issuer", "0000320193"),
        ("owner", "0000320193"),
        ("holding", "0000320193"),
        ("issuer", "0000789019"),
        ("owner", "0000789019"),
        ("holding", "0000789019"),
    ]

    assert len(repo.logs) == 2
    assert repo.logs[0]["message"] == "router failed"
    assert repo.logs[0]["stage"] == "extract"
    assert repo.logs[0]["level"] == "ERROR"
    assert repo.logs[0]["cik"] == "0000320193"

    assert repo.logs[1]["message"] == "router failed"
    assert repo.logs[1]["stage"] == "extract"
    assert repo.logs[1]["level"] == "ERROR"
    assert repo.logs[1]["cik"] == "0000789019"


def test_run_single_tick_continues_when_router_and_log_write_both_fail():
    calls: list[tuple[str, str]] = []
    routers = [
        _RecordingRouter("issuer", calls),
        _RecordingRouter("owner", calls, should_raise=True),
        _RecordingRouter("holding", calls),
    ]

    run_single_tick(
        run_id="run-003",
        securities=[_Security(cik="0000320193")],
        routers=routers,
        repo=_FailingLogRepo(),
    )

    assert calls == [
        ("issuer", "0000320193"),
        ("owner", "0000320193"),
        ("holding", "0000320193"),
    ]


def test_build_blocking_scheduler_registers_phase1_tick_job_id():
    scheduler = build_blocking_scheduler(interval_minutes=5, tick_callable=lambda: None)

    job = scheduler.get_job("phase1-tick")

    assert job is not None
    assert job.id == "phase1-tick"
    assert len(scheduler.get_jobs()) == 1


def test_make_run_id_returns_non_empty_timestamp_like_string():
    run_id = make_run_id()

    assert run_id
    assert re.fullmatch(r"\d{8}T\d{12}Z", run_id)
