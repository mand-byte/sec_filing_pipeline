from typing import Any


class HoldingRouter:
    name = "holding"

    def run(self, *, security: Any) -> None:
        del security
