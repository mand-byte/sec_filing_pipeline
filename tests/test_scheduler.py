from __future__ import annotations

from types import SimpleNamespace

from src.pipeline.scheduler import run_single_tick


class _FakeSession:
    def __init__(self) -> None:
        self.rollback_calls = 0

    def rollback(self) -> None:
        self.rollback_calls += 1


class _FakeRepo:
    def __init__(self) -> None:
        self.session = _FakeSession()
        self.logs: list[dict[str, object]] = []

    def write_log(self, **payload: object) -> None:
        self.logs.append(payload)


class _FailingRouter:
    name = "issuer"

    def run(self, *, security: object, context: object) -> None:
        raise RuntimeError(f"boom for {getattr(security, 'cik', 'unknown')}")


class _RecordingRouter:
    name = "owner"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, *, security: object, context: object) -> None:
        self.calls.append(getattr(security, "cik"))


def test_run_single_tick_rolls_back_after_router_failure_and_continues() -> None:
    security = SimpleNamespace(cik="0000789019")
    repo = _FakeRepo()
    next_router = _RecordingRouter()

    run_single_tick(
        run_id="run-123",
        securities=[security],
        routers=[_FailingRouter(), next_router],
        repo=repo,
    )

    assert repo.session.rollback_calls == 1
    assert next_router.calls == ["0000789019"]
    assert repo.logs == [
        {
            "run_id": "run-123",
            "route": "issuer",
            "cik": "0000789019",
            "stage": "extract",
            "level": "ERROR",
            "message": "router failed",
            "error_type": "RuntimeError",
            "error_detail": repo.logs[0]["error_detail"],
        }
    ]
    assert "boom for 0000789019" in str(repo.logs[0]["error_detail"])


def test_run_single_tick_tolerates_rollback_failure() -> None:
    security = SimpleNamespace(cik="0000320193")
    repo = _FakeRepo()
    next_router = _RecordingRouter()

    def broken_rollback() -> None:
        raise RuntimeError("rollback failed")

    repo.session.rollback = broken_rollback  # type: ignore[method-assign]

    run_single_tick(
        run_id="run-456",
        securities=[security],
        routers=[_FailingRouter(), next_router],
        repo=repo,
    )

    assert next_router.calls == ["0000320193"]
    assert len(repo.logs) == 1
    assert repo.logs[0]["route"] == "issuer"
