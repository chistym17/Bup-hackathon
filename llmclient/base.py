class LLMClient:
    name: str = "base"

    def complete(self, system: str, user: str) -> str:
        raise NotImplementedError
