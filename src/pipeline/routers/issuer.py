from typing import Any


class IssuerRouter:
    name = "issuer"

    def run(self, *, security: Any, context: Any) -> None:
        del security, context
