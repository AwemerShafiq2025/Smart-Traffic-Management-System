from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Protocol, Sequence, runtime_checkable

from src.database.db_handler import DatabaseHandler
from src.models.traffic_signal import TrafficSignal, TrafficSignalState


@dataclass(frozen=True, slots=True)
class SignalStateChangeEvent:
    signal_id: int
    old_state: TrafficSignalState
    new_state: TrafficSignalState
    occurred_at: datetime
    details: Optional[str] = None


class TrafficObserver(Protocol):
    def on_signal_state_changed(self, event: SignalStateChangeEvent) -> None: ...


@runtime_checkable
class TimerStrategy(Protocol):
    name: str

    def calculate_green_duration(
        self, *, vehicle_count: int, current_green_s: int, min_green_s: int, max_green_s: int
    ) -> int: ...


class NormalModeStrategy:
    name = "Normal Mode"

    def calculate_green_duration(
        self, *, vehicle_count: int, current_green_s: int, min_green_s: int, max_green_s: int
    ) -> int:
        # Keep close to baseline; small nudges only.
        if vehicle_count <= 5:
            return max(min_green_s, current_green_s - 3)
        if vehicle_count <= 15:
            return current_green_s
        return min(max_green_s, current_green_s + 3)


class HighTrafficModeStrategy:
    name = "High Traffic Mode"

    def calculate_green_duration(
        self, *, vehicle_count: int, current_green_s: int, min_green_s: int, max_green_s: int
    ) -> int:
        # More aggressive increase under heavy congestion.
        if vehicle_count >= 60:
            return min(max_green_s, current_green_s + 20)
        if vehicle_count >= 40:
            return min(max_green_s, current_green_s + 12)
        return min(max_green_s, current_green_s + 6)


class DatabaseTrafficLogObserver:
    def __init__(self, db: Optional[DatabaseHandler] = None) -> None:
        self._db = db or DatabaseHandler()

    def on_signal_state_changed(self, event: SignalStateChangeEvent) -> None:
        self._db.insert_traffic_log(
            signal_id=event.signal_id,
            event_type="STATE_CHANGE",
            old_state=event.old_state.value,
            new_state=event.new_state.value,
            details=event.details,
        )


class TrafficController:
    """
    Coordinates a set of TrafficSignal objects and applies state transitions.

    Observer Pattern:
    - when a signal changes state, the controller notifies registered observers
      (e.g., a DatabaseTrafficLogObserver that writes to traffic_logs).
    """

    def __init__(
        self,
        signals: Optional[Sequence[TrafficSignal]] = None,
        *,
        observers: Optional[Sequence[TrafficObserver]] = None,
        red_duration_s: int = 10,
        green_duration_s: int = 2,        # Fast dynamic: 2s min green
        yellow_duration_s: int = 2,       # Fast presentation: 2s yellow
        seconds_per_car_s: int = 1,       # 1s per car
        max_green_duration_s: int = 6,    # 6s max green
        db_handler: Optional[DatabaseHandler] = None,
    ) -> None:
        self._signals: List[TrafficSignal] = list(signals or [])
        self._observers: List[TrafficObserver] = list(observers or [])

        self._durations = {
            TrafficSignalState.RED: red_duration_s,
            # Kept for backward compatibility with `calculate_dynamic_timer()`.
            # Round-robin GREEN timing is now fully dynamic and computed in `manage_traffic()`.
            TrafficSignalState.GREEN: green_duration_s,
            TrafficSignalState.YELLOW: yellow_duration_s,
        }

        # Dynamic green allocation parameters.
        # `green_duration_s` acts as the minimum green duration for the formula.
        self._min_green_s = int(green_duration_s)
        self._seconds_per_car_s = int(seconds_per_car_s)
        self._max_green_s = int(max_green_duration_s)

        # Latest on-screen queue snapshot from TrafficSimulation.
        self._live_queue_counts_by_signal_id: Dict[int, int] = {}
        self._live_emergencies_by_signal_id: Dict[int, bool] = {}

        # Convenient default observer if none provided.
        if not self._observers:
            self._observers.append(DatabaseTrafficLogObserver(db_handler))

        self._db = db_handler or DatabaseHandler()

        self._active_index: int = 0
        self._normalize_round_robin_states()

    def _normalize_round_robin_states(self) -> None:
        """
        Enforce the invariant:
        - exactly one signal is active (GREEN or YELLOW)
        - all other signals are RED
        """
        if not self._signals:
            self._active_index = 0
            return

        # Prefer an existing GREEN/YELLOW signal as the active one; otherwise default to index 0.
        active_idx: Optional[int] = None
        for i, s in enumerate(self._signals):
            if s.state in (TrafficSignalState.GREEN, TrafficSignalState.YELLOW):
                active_idx = i
                break
        if active_idx is None:
            active_idx = 0
            active_signal = self._signals[active_idx]
            old = active_signal.state
            green_timer = self._calculate_dynamic_green_time(active_signal.id)
            active_signal.set_state(TrafficSignalState.GREEN, green_timer)
            self._notify_signal_state_changed(
                active_signal,
                old,
                active_signal.state,
                details=f"Round-robin init: allocating GREEN={green_timer}s based on current queue snapshot.",
            )

        self._active_index = active_idx

        # Lock others to RED.
        for i, s in enumerate(self._signals):
            if i == self._active_index:
                continue
            if s.state != TrafficSignalState.RED:
                old = s.state
                s.set_state(TrafficSignalState.RED, int(self._durations[TrafficSignalState.RED]))
                self._notify_signal_state_changed(
                    s, old, s.state, details="Round-robin controller: locking non-active signals to RED."
                )

    def _get_live_queue_count(self, signal_id: int) -> int:
        return int(self._live_queue_counts_by_signal_id.get(signal_id, 0))

    def _calculate_dynamic_green_time(self, signal_id: int) -> int:
        """
        calculated_time = min_green_time + (queue_count * seconds_per_car), capped to max_green_time.
        """
        queue_count = self._get_live_queue_count(signal_id)
        calculated_time = self._min_green_s + (queue_count * self._seconds_per_car_s)
        if calculated_time < self._min_green_s:
            calculated_time = self._min_green_s
        return min(self._max_green_s, int(calculated_time))

    @property
    def signals(self) -> List[TrafficSignal]:
        return self._signals

    def add_signal(self, signal: TrafficSignal) -> None:
        self._signals.append(signal)

    def add_observer(self, observer: TrafficObserver) -> None:
        self._observers.append(observer)

    def _get_signal_by_id(self, signal_id: int) -> Optional[TrafficSignal]:
        for s in self._signals:
            if s.id == signal_id:
                return s
        return None

    def _notify_signal_state_changed(
        self, signal: TrafficSignal, old_state: TrafficSignalState, new_state: TrafficSignalState, *, details: str | None
    ) -> None:
        event = SignalStateChangeEvent(
            signal_id=signal.id,
            old_state=old_state,
            new_state=new_state,
            occurred_at=datetime.now(timezone.utc),
            details=details,
        )
        for observer in self._observers:
            observer.on_signal_state_changed(event)

    def apply_live_congestion_ai(
        self,
        queue_counts_by_signal_id: Dict[int, int],
        *,
        emergency_by_signal_id: Optional[Dict[int, bool]] = None,
        **_: object,
    ) -> None:
        """
        Live congestion input from TrafficSimulation.

        This method now only updates the latest queue snapshot for each signal.
        The actual GREEN timer allocation is performed deterministically inside `manage_traffic()`
        exactly at the moment a signal transitions to GREEN.
        """
        if not queue_counts_by_signal_id:
            return
        # Keep only ids we know about (optional safety).
        signal_ids = {s.id for s in self._signals}
        self._live_queue_counts_by_signal_id = {
            int(signal_id): int(count) for signal_id, count in queue_counts_by_signal_id.items() if int(signal_id) in signal_ids
        }
        if emergency_by_signal_id is not None:
            self._live_emergencies_by_signal_id = {
                int(signal_id): bool(has_emer) 
                for signal_id, has_emer in emergency_by_signal_id.items() 
                if int(signal_id) in signal_ids
            }

    def _next_state(self, current: TrafficSignalState) -> TrafficSignalState:
        if current == TrafficSignalState.RED:
            return TrafficSignalState.GREEN
        if current == TrafficSignalState.GREEN:
            return TrafficSignalState.YELLOW
        return TrafficSignalState.RED

    def manage_traffic(self, *, tick_seconds: int = 1) -> None:
        """
        Strict round-robin controller:
        - ONLY ONE signal can be GREEN or YELLOW at any given time.
        - The other signals are locked to RED.
        - When the active signal finishes YELLOW and turns RED, the NEXT signal immediately turns GREEN.
        """
        if tick_seconds <= 0:
            raise ValueError("tick_seconds must be > 0")

        if not self._signals:
            return

        self._normalize_round_robin_states()
        active = self._signals[self._active_index]

        # Check for active emergency
        emergency_signal_id = None
        for sig_id, has_emergency in self._live_emergencies_by_signal_id.items():
            if has_emergency:
                emergency_signal_id = sig_id
                break

        if emergency_signal_id is not None and active.id != emergency_signal_id:
            # Force active signal to smoothly transition if it's currently GREEN.
            if active.state == TrafficSignalState.GREEN:
                active.timer = 0  # Force to 0 so it immediately transitions to YELLOW on next block

        # Tick only the active signal.
        active.tick(tick_seconds)
        if active.timer > 0:
            return

        # Active timer finished -> transition.
        if active.state == TrafficSignalState.GREEN:
            old = active.state
            active.set_state(TrafficSignalState.YELLOW, int(self._durations[TrafficSignalState.YELLOW]))
            self._notify_signal_state_changed(
                active,
                old,
                active.state,
                details="Round-robin: GREEN timer finished -> YELLOW.",
            )
            return

        if active.state == TrafficSignalState.YELLOW:
            # YELLOW finished -> RED and immediately advance next to GREEN.
            old = active.state
            active.set_state(TrafficSignalState.RED, int(self._durations[TrafficSignalState.RED]))
            self._notify_signal_state_changed(
                active,
                old,
                active.state,
                details="Round-robin: YELLOW timer finished -> RED; advancing to next signal.",
            )

            # Check if there is an active emergency to jump to.
            next_active_index = (self._active_index + 1) % len(self._signals)
            is_override = False
            for i, s in enumerate(self._signals):
                if self._live_emergencies_by_signal_id.get(s.id, False):
                    next_active_index = i
                    is_override = True
                    break

            self._active_index = next_active_index
            next_signal = self._signals[self._active_index]

            # Lock everyone else to RED (safety invariant).
            for i, s in enumerate(self._signals):
                if i == self._active_index:
                    continue
                if s.state != TrafficSignalState.RED:
                    prev = s.state
                    s.set_state(TrafficSignalState.RED, int(self._durations[TrafficSignalState.RED]))
                    self._notify_signal_state_changed(
                        s, prev, s.state, details="Round-robin: locking non-active signal to RED."
                    )

            if is_override:
                allocated_seconds = 10  # Generous fixed Green time for emergency
                details = f"Emergency override: allocating GREEN={allocated_seconds}s for Ambulance."
                self._db.insert_traffic_log(
                    signal_id=next_signal.id,
                    event_type="EMERGENCY_OVERRIDE",
                    old_state=TrafficSignalState.RED.value,
                    new_state=TrafficSignalState.GREEN.value,
                    details=details
                )
                next_signal.set_state(TrafficSignalState.GREEN, allocated_seconds)
                self._notify_signal_state_changed(
                    next_signal, TrafficSignalState.RED, TrafficSignalState.GREEN, details=details
                )
                print(f"🚨 ACTIVE EMERGENCY OVERRIDE on Signal {next_signal.id} 🚨")
            else:
                # Dynamic GREEN allocation happens EXACTLY at the moment we transition into GREEN.
                queue_count = self._get_live_queue_count(next_signal.id)
                allocated_seconds = self._calculate_dynamic_green_time(next_signal.id)
                
                # Updated clean console log 
                print(
                    f"Live AI: Signal [{next_signal.id}] turning GREEN. Queue: [{queue_count}] cars. "
                    f"Allocating [{allocated_seconds}] seconds (Max 6s)."
                )
                
                self._db.insert_traffic_log(
                    signal_id=next_signal.id,
                    event_type="AI_DECISION",
                    old_state=f"RED_TIMER={next_signal.timer}s",
                    new_state=f"GREEN_TIMER={allocated_seconds}s",
                    details=(
                        f"Dynamic timer allocation: min_green={self._min_green_s}s + "
                        f"(queue_count={queue_count} * seconds_per_car={self._seconds_per_car_s}s) "
                        f"= allocated={allocated_seconds}s (capped at {self._max_green_s}s)."
                    ),
                )

                prev = next_signal.state
                next_signal.set_state(TrafficSignalState.GREEN, allocated_seconds)
                self._notify_signal_state_changed(
                    next_signal,
                    prev,
                    next_signal.state,
                    details=(
                        f"Round-robin: next signal activated -> GREEN with dynamic allocation "
                        f"{allocated_seconds}s based on queue_count={queue_count}."
                    ),
                )
            return

        # If active somehow isn't GREEN/YELLOW, normalize and continue next tick.
        self._normalize_round_robin_states()

    def predict_congestion(self) -> None:
        """
        Placeholder for future AI logic:
        - analyze vehicle density / camera feeds / sensors
        - adjust self._durations or individual signal timers accordingly
        - optionally store results in congestion_data
        """
        return

    def calculate_dynamic_timer(
        self,
        *,
        location: str,
        road_segment: Optional[str] = None,
        signal_id: int = 0,
        high_traffic_threshold: int = 30,
        min_green_s: int = 10,
        max_green_s: int = 120,
        normal_strategy: TimerStrategy | None = None,
        high_traffic_strategy: TimerStrategy | None = None,
    ) -> int:
        """
        Reads the latest congestion_data for a road and adjusts the GREEN duration dynamically.

        Strategy Pattern:
        - Uses 'Normal Mode' strategy under low/medium traffic
        - Switches to 'High Traffic Mode' strategy once vehicle_count crosses the threshold

        Logs each "AI decision" into traffic_logs so you can show it in the presentation.
        """
        row = self._db.fetch_latest_congestion(location=location, road_segment=road_segment)
        if row is None:
            self._db.insert_traffic_log(
                signal_id=signal_id,
                event_type="AI_DECISION",
                details=(
                    f"No congestion_data found for location='{location}'"
                    + (f", road_segment='{road_segment}'" if road_segment else "")
                    + ". Green duration unchanged."
                ),
            )
            return int(self._durations[TrafficSignalState.GREEN])

        vehicle_count = int(row["vehicle_count"])
        current_green_s = int(self._durations[TrafficSignalState.GREEN])

        normal = normal_strategy or NormalModeStrategy()
        high = high_traffic_strategy or HighTrafficModeStrategy()
        strategy: TimerStrategy = high if vehicle_count >= high_traffic_threshold else normal

        new_green_s = int(
            strategy.calculate_green_duration(
                vehicle_count=vehicle_count,
                current_green_s=current_green_s,
                min_green_s=min_green_s,
                max_green_s=max_green_s,
            )
        )

        self._durations[TrafficSignalState.GREEN] = new_green_s

        self._db.insert_traffic_log(
            signal_id=signal_id,
            event_type="AI_DECISION",
            old_state=f"GREEN={current_green_s}s",
            new_state=f"GREEN={new_green_s}s",
            details=(
                f"Strategy='{strategy.name}', vehicle_count={vehicle_count}, threshold={high_traffic_threshold}, "
                f"location='{location}'"
                + (f", road_segment='{road_segment}'" if road_segment else "")
                + "."
            ),
        )

        return new_green_s