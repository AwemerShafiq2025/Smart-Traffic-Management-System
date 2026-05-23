from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


Color = Tuple[int, int, int]


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"


class TurnIntention(str, Enum):
    STRAIGHT = "STRAIGHT"
    LEFT = "LEFT"
    RIGHT = "RIGHT"


class VehicleType(str, Enum):
    CAR = "CAR"
    BUS = "BUS"
    MOTORCYCLE = "MOTORCYCLE"
    AMBULANCE = "AMBULANCE"


@dataclass(slots=True)
class Vehicle:
    x: float
    y: float
    width: int
    height: int
    speed: float  # pixels per frame (current)
    color: Color
    direction: Direction
    turn_intention: TurnIntention
    has_turned: bool
    entered_intersection: bool

    desired_speed: float
    v_type: VehicleType = VehicleType.CAR  # NEW: To identify car, bus, or motorcycle

    def rect(self) -> tuple[float, float, int, int]:
        return (self.x, self.y, self.width, self.height)
