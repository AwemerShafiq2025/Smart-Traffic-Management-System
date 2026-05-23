from __future__ import annotations

from src.controllers.traffic_controller import TrafficController
from src.database.db_handler import DatabaseHandler
from src.models.traffic_signal import TrafficSignal, TrafficSignalState
from src.views.simulation import TrafficSimulation


def main() -> None:
    # Initialize DB singleton (connection will open on first use).
    _db = DatabaseHandler()

    # Create 4 traffic signals (IDs 1..4) with initial states.
    # Strict round-robin controller expects only ONE active signal at startup.
    signals = [
        TrafficSignal(id=1, state=TrafficSignalState.GREEN, timer=2), # Start with fast timer
        TrafficSignal(id=2, state=TrafficSignalState.RED, timer=10),
        TrafficSignal(id=3, state=TrafficSignalState.RED, timer=10),
        TrafficSignal(id=4, state=TrafficSignalState.RED, timer=10),
    ]

    # Let the TrafficController use its newly updated fast presentation defaults
    # (min_green=2s, max_green=6s, yellow=2s)
    controller = TrafficController(
        signals=signals,
        observers=[],
    )

    simulation = TrafficSimulation(controller)
    simulation.run()


if __name__ == "__main__":
    main()