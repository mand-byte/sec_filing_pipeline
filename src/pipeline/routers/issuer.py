from typing import Any

from src.pipeline.route_runtime import RouteProcessor


class IssuerRouter:
    name = "issuer"

    def __init__(self, processor: RouteProcessor):
        self._processor = processor

    def run(self, *, security: Any, context: Any) -> None:
        self._processor.run(
            security=security,
            route=self.name,
            run_id=str(context["run_id"]),
        )
