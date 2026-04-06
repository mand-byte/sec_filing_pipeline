from typing import Any


class HoldingRouter:
    name = "holding"

    def run(self, *, security: Any, context: Any) -> None:
        del security, context
