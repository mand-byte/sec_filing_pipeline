from typing import Any


class OwnerRouter:
    name = "owner"

    def run(self, *, security: Any, context: Any) -> None:
        del security, context
