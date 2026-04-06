from src.pipeline.scheduler import run_single_tick


class _RecordingRouter:
    def __init__(self, name: str, calls: list[tuple[str, str]], should_raise: bool = False):
        self.name = name
        self._calls = calls
        self._should_raise = should_raise

    def run(self, *, security: str) -> None:
        self._calls.append((self.name, security))
        if self._should_raise:
            raise RuntimeError("boom")


class _RecordingRepo:
    def __init__(self):
        self.logs: list[dict[str, str]] = []

    def write_log(self, **kwargs) -> None:
        self.logs.append(kwargs)


def test_run_single_tick_calls_routers_in_order_for_each_security():
    calls: list[tuple[str, str]] = []
    routers = [
        _RecordingRouter("issuer", calls),
        _RecordingRouter("owner", calls),
        _RecordingRouter("holding", calls),
    ]

    run_single_tick(
        run_id="run-001",
        securities=["AAPL", "MSFT"],
        routers=routers,
        repo=_RecordingRepo(),
    )

    assert calls == [
        ("issuer", "AAPL"),
        ("owner", "AAPL"),
        ("holding", "AAPL"),
        ("issuer", "MSFT"),
        ("owner", "MSFT"),
        ("holding", "MSFT"),
    ]


def test_run_single_tick_logs_router_failed_and_continues():
    calls: list[tuple[str, str]] = []
    repo = _RecordingRepo()
    routers = [
        _RecordingRouter("issuer", calls),
        _RecordingRouter("owner", calls, should_raise=True),
        _RecordingRouter("holding", calls),
    ]

    run_single_tick(
        run_id="run-002",
        securities=["AAPL"],
        routers=routers,
        repo=repo,
    )

    assert calls == [
        ("issuer", "AAPL"),
        ("owner", "AAPL"),
        ("holding", "AAPL"),
    ]
    assert len(repo.logs) == 1
    assert repo.logs[0]["message"] == "router failed"
