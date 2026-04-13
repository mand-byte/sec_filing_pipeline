from typing import Any

from src.pipeline.route_runtime import RouteProcessor


class OwnerRouter:
    name = "owner"

    def __init__(self, processor: RouteProcessor):
        """Bind the shared route processor for owner work."""
        self._processor = processor

    def run(self, *, security: Any, context: Any) -> None:
        """Run the owner route for one security."""
        self._processor.run(
            security=security,
            route=self.name,
            run_id=str(context["run_id"]),
        )
