from typing import Any


class IssuerRouter:
    name = "issuer"

    def run(self, *, security: Any) -> None:
        del security
