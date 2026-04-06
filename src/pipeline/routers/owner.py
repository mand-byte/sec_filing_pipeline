from typing import Any


class OwnerRouter:
    name = "owner"

    def run(self, *, security: Any) -> None:
        del security
