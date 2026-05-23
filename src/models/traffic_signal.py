from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TrafficSignalState(str, Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"


@dataclass(slots=True)
class TrafficSignal:
    id: int
    state: TrafficSignalState
    timer: int  # seconds remaining in the current state

    def tick(self, seconds: int = 1) -> None:
        if seconds < 0:
            raise ValueError("seconds must be >= 0")
        self.timer = max(0, self.timer - seconds)

    def set_state(self, state: TrafficSignalState, timer: int) -> None:
        if timer < 0:
            raise ValueError("timer must be >= 0")
        self.state = state
        self.timer = timer

