from changeproof.adapters.base import Adapter

REQUIRED = ("language", "parse", "diff", "run")  # RENAME: MEMBERS EVERY ADAPTER MUST PROVIDE


class AdapterRegistry:
    # PURPOSE: STARTS WITH NO ADAPTERS; CALLERS REGISTER THE ONES THEY SHIP
    def __init__(self) -> None:
        self._by_language: dict[str, Adapter] = {}

    # PURPOSE: ADDS AN ADAPTER AFTER CHECKING IT IMPLEMENTS THE FULL INTERFACE
    def register(self, adapter: Adapter) -> None:
        missing = [name for name in REQUIRED if not hasattr(adapter, name)]
        if missing:
            raise TypeError(f"{type(adapter).__name__} is missing {', '.join(missing)}")
        if adapter.language in self._by_language:
            raise ValueError(f"an adapter for '{adapter.language}' is already registered")
        self._by_language[adapter.language] = adapter

    # PURPOSE: LOOKS UP THE ADAPTER FOR A COMPONENT'S LANGUAGE KEY
    def get(self, language: str) -> Adapter:
        try:
            return self._by_language[language]
        except KeyError:
            raise KeyError(f"no adapter for language '{language}'") from None
