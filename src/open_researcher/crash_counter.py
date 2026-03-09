"""Crash counter -- pause experiments after N consecutive crashes."""


class CrashCounter:
    def __init__(self, max_crashes: int = 3):
        self.max_crashes = max_crashes
        self.consecutive = 0

    def record(self, status: str) -> bool:
        """Record result. Returns True if crash limit reached."""
        if status == "crash":
            self.consecutive += 1
            return self.consecutive >= self.max_crashes
        self.consecutive = 0
        return False

    def reset(self) -> None:
        self.consecutive = 0
