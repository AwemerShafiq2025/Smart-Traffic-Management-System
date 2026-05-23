from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Tuple

import pygame  # type: ignore[import-not-found]

from src.controllers.traffic_controller import TrafficController
from src.models.traffic_signal import TrafficSignalState
from src.models.vehicle import Direction, TurnIntention, Vehicle, VehicleType


Color = Tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    width: int = 800
    height: int = 600
    fps: int = 60
    tick_interval_ms: int = 1000

    road_color: Color = (45, 45, 45)
    background_color: Color = (34, 139, 34)  # Realistic Grass Green
    lane_color: Color = (235, 235, 235)

    vehicle_spawn_min_ms: int = 600
    vehicle_spawn_max_ms: int = 1400
    vehicle_min_speed: float = 1.6
    vehicle_max_speed: float = 3.0
    vehicle_gap_px: int = 10
    ai_analyze_interval_ms: int = 3000
    stop_line_color: Color = (250, 250, 250)
    stop_line_thickness: int = 8
    vehicle_safe_buffer_px: int = 10


class TrafficSimulation:
    """
    Pygame visualization for the Smart Traffic Management System.

    Owns the window, event loop, and rendering; receives a TrafficController instance
    so the simulation always reflects real-time signal states.
    """

    _TICK_EVENT: int = pygame.USEREVENT + 1

    def __init__(self, controller: TrafficController, *,
                 config: SimulationConfig | None = None) -> None:
        self._controller = controller
        self._config = config or SimulationConfig()

        pygame.init()
        pygame.font.init()
        # Digital style font for timers
        self._font = pygame.font.SysFont("Courier New", 18, bold=True)

        self._screen = pygame.display.set_mode((self._config.width, self._config.height))
        pygame.display.set_caption("Smart Traffic Management System - Simulation")
        self._clock = pygame.time.Clock()

        # Fire an internal event every 1 second to advance the controller timers.
        pygame.time.set_timer(self._TICK_EVENT, self._config.tick_interval_ms)

        self._vehicles: list[Vehicle] = []
        self._next_spawn_at_ms: int = pygame.time.get_ticks() + self._rand_spawn_delay_ms()
        self._last_ai_analyze_ms: int = 0

        self._running = False

    def run(self) -> None:
        """
        Main simulation loop.
        """
        self._running = True
        while self._running:
            self._handle_events()
            self._spawn_vehicle()
            self._update_vehicles()
            self._analyze_traffic_and_apply_ai()
            self._render()
            self._clock.tick(self._config.fps)

        pygame.quit()

    def stop(self) -> None:
        self._running = False

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.stop()
                continue

            if event.type == self._TICK_EVENT:
                # Advance the traffic controller once per second.
                self._controller.manage_traffic(tick_seconds=1)

    def _render(self) -> None:
        self._screen.fill(self._config.background_color)

        self._draw_intersection()
        self._draw_signals()
        self._draw_vehicles()

        pygame.display.flip()

    def _draw_intersection(self) -> None:
        w, h = self._config.width, self._config.height

        road_thickness = 220  # WIDER ROADS
        cx, cy = w // 2, h // 2

        # Two roads crossing (vertical + horizontal).
        vertical = pygame.Rect(cx - road_thickness // 2, 0, road_thickness, h)
        horizontal = pygame.Rect(0, cy - road_thickness // 2, w, road_thickness)
        pygame.draw.rect(self._screen, self._config.road_color, vertical)
        pygame.draw.rect(self._screen, self._config.road_color, horizontal)

        self._draw_lane_markings(cx=cx, cy=cy, road_thickness=road_thickness)
        self._draw_zebra_crossings(cx=cx, cy=cy, road_thickness=road_thickness)
        self._draw_stop_lines(cx=cx, cy=cy, road_thickness=road_thickness)

    def _draw_zebra_crossings(self, *, cx: int, cy: int, road_thickness: int) -> None:
        """
        Draw realistic zebra crossings just behind the stop lines.
        """
        half = road_thickness // 2
        offset = half + 15  # Position slightly behind stop lines
        stripe_w = 8
        stripe_l = 24
        gap = 12
        color = (220, 220, 220)

        # Horizontal Roads (Left and Right approaches)
        y_start = cy - half + 12
        y_end = cy + half - 12
        y = y_start
        while y < y_end:
            # Left side
            pygame.draw.rect(self._screen, color, (cx - offset - stripe_l, y, stripe_l, stripe_w))
            # Right side
            pygame.draw.rect(self._screen, color, (cx + offset, y, stripe_l, stripe_w))
            y += stripe_w + gap

        # Vertical Roads (Top and Bottom approaches)
        x_start = cx - half + 12
        x_end = cx + half - 12
        x = x_start
        while x < x_end:
            # Top side
            pygame.draw.rect(self._screen, color, (x, cy - offset - stripe_l, stripe_w, stripe_l))
            # Bottom side
            pygame.draw.rect(self._screen, color, (x, cy + offset, stripe_w, stripe_l))
            x += stripe_w + gap

    def _draw_stop_lines(self, *, cx: int, cy: int, road_thickness: int) -> None:
        """
        Draw thick stop lines where vehicles must wait at RED/YELLOW.
        """
        half = road_thickness // 2
        thickness = self._config.stop_line_thickness
        color = self._config.stop_line_color
        pad = 6

        y_top = cy - half - pad
        y_bottom = cy + half + pad
        x_left = cx - half - pad
        x_right = cx + half + pad

        # Top approach
        pygame.draw.line(self._screen, color, (cx - half, y_top), (cx + half, y_top), thickness)
        # Bottom approach
        pygame.draw.line(self._screen, color, (cx - half, y_bottom),
                         (cx + half, y_bottom), thickness)
        # Left approach
        pygame.draw.line(self._screen, color, (x_left, cy - half), (x_left, cy + half), thickness)
        # Right approach
        pygame.draw.line(self._screen, color, (x_right, cy - half), (x_right, cy + half), thickness)

    def _draw_lane_markings(self, *, cx: int, cy: int, road_thickness: int) -> None:
        """
        Draw simple white dashed markings on the center of each road.
        """
        dash_len = 18
        gap = 14
        lane_w = 4
        lane_color = self._config.lane_color
        w, h = self._config.width, self._config.height

        # Horizontal dashed line
        y = cy
        x = 0
        while x < w:
            if x < cx - road_thickness // 2 or x > cx + road_thickness // 2:
                pygame.draw.rect(
                    self._screen, lane_color, pygame.Rect(
                        x, y - lane_w // 2, dash_len, lane_w))
            x += dash_len + gap

        # Vertical dashed line
        x = cx
        y = 0
        while y < h:
            if y < cy - road_thickness // 2 or y > cy + road_thickness // 2:
                pygame.draw.rect(
                    self._screen, lane_color, pygame.Rect(
                        x - lane_w // 2, y, lane_w, dash_len))
            y += dash_len + gap

        # Outer Edge lane separators
        inset = road_thickness // 4
        edge_lane_w = 2
        for offset in (-inset, inset):
            pygame.draw.line(self._screen, (120, 120, 120),
                             (cx + offset, 0), (cx + offset, h), edge_lane_w)
            pygame.draw.line(self._screen, (120, 120, 120),
                             (0, cy + offset), (w, cy + offset), edge_lane_w)

    def _draw_signals(self) -> None:
        """
        Draw traffic signals placed next to their respective stop lines.
        """
        w, h = self._config.width, self._config.height
        cx, cy = w // 2, h // 2
        road_thickness = 220
        half = road_thickness // 2
        pad = 6

        y_top = cy - half - pad
        y_bottom = cy + half + pad
        x_left = cx - half - pad
        x_right = cx + half + pad

        def get_signal_info(signal_id: int) -> Tuple[TrafficSignalState, int]:
            for s in self._controller.signals:
                if s.id == signal_id:
                    return s.state, s.timer
            return TrafficSignalState.RED, 0

        state1, timer1 = get_signal_info(1)
        state2, timer2 = get_signal_info(2)
        state3, timer3 = get_signal_info(3)
        state4, timer4 = get_signal_info(4)

        # Sync RED lights to show the maximum active timer
        active_timer = max(timer1, timer2, timer3, timer4)

        display_timer1 = timer1 if state1 != TrafficSignalState.RED else active_timer
        display_timer2 = timer2 if state2 != TrafficSignalState.RED else active_timer
        display_timer3 = timer3 if state3 != TrafficSignalState.RED else active_timer
        display_timer4 = timer4 if state4 != TrafficSignalState.RED else active_timer

        # Top
        self._draw_signal_light(
            x=cx + half + 30,
            y=y_top - 25,
            state=state1,
            timer=display_timer1,
            rotation_degrees=0,
            is_top=True)
        # Bottom
        self._draw_signal_light(
            x=cx - half - 30,
            y=y_bottom + 25,
            state=state2,
            timer=display_timer2,
            rotation_degrees=0,
            is_top=False)
        # Left
        self._draw_signal_light(
            x=x_left - 25,
            y=cy - half - 30,
            state=state3,
            timer=display_timer3,
            rotation_degrees=90,
            is_top=True)
        # Right
        self._draw_signal_light(
            x=x_right + 25,
            y=cy + half + 30,
            state=state4,
            timer=display_timer4,
            rotation_degrees=90,
            is_top=False)

    def _analyze_traffic_and_apply_ai(self) -> None:
        """
        Every few seconds, estimate congestion from on-screen queued vehicles.
        """
        now = pygame.time.get_ticks()
        if now - self._last_ai_analyze_ms < self._config.ai_analyze_interval_ms:
            return
        self._last_ai_analyze_ms = now

        def front_pos(v: Vehicle) -> float:
            if v.direction == Direction.DOWN:
                return v.y + v.height
            if v.direction == Direction.UP:
                return v.y
            if v.direction == Direction.RIGHT:
                return v.x + v.width
            return v.x

        queued_by_signal_id = {1: 0, 2: 0, 3: 0, 4: 0}
        emergency_by_signal_id = {1: False, 2: False, 3: False, 4: False}
        for v in self._vehicles:
            stop_line = float(self._stop_line_for_vehicle(v))
            f = float(front_pos(v))

            # Detect approaching or waiting ambulances
            is_ambulance = getattr(v, "v_type", VehicleType.CAR) == VehicleType.AMBULANCE

            approaching_or_waiting = False
            if v.direction == Direction.DOWN and f <= stop_line + 2:
                approaching_or_waiting = True
                signal_id = 1
            elif v.direction == Direction.UP and f >= stop_line - 2:
                approaching_or_waiting = True
                signal_id = 2
            elif v.direction == Direction.RIGHT and f <= stop_line + 2:
                approaching_or_waiting = True
                signal_id = 3
            elif v.direction == Direction.LEFT and f >= stop_line - 2:
                approaching_or_waiting = True
                signal_id = 4
            else:
                signal_id = 0

            if approaching_or_waiting and signal_id > 0:
                if is_ambulance:
                    emergency_by_signal_id[signal_id] = True
                if v.speed == 0:
                    queued_by_signal_id[signal_id] += 1

        print(
            f"[AI] Live queued vehicles: {queued_by_signal_id}, Emergencies: {emergency_by_signal_id}")
        self._controller.apply_live_congestion_ai(
            queued_by_signal_id, emergency_by_signal_id=emergency_by_signal_id)

    def _rand_spawn_delay_ms(self) -> int:
        return random.randint(self._config.vehicle_spawn_min_ms, self._config.vehicle_spawn_max_ms)

    def _spawn_vehicle(self) -> None:
        """
        Randomly spawns vehicles at the road edges heading toward the intersection.
        """
        now = pygame.time.get_ticks()
        if now < self._next_spawn_at_ms:
            return

        w, h = self._config.width, self._config.height
        cx, cy = w // 2, h // 2
        road_thickness = 220
        half = road_thickness // 2
        lane_offset = road_thickness // 4

        direction = random.choice([Direction.DOWN, Direction.UP, Direction.RIGHT, Direction.LEFT])

        type_roll = random.random()
        if type_roll < 0.05:
            # Ambulance (Longer, fast)
            v_type = VehicleType.AMBULANCE
            length = 40
            thickness = 20
            speed = random.uniform(3.0, 4.0)
            color = (255, 255, 255)
        elif type_roll < 0.25:
            # Bus (Large, slow)
            v_type = VehicleType.BUS
            length = 65
            thickness = 24
            speed = random.uniform(1.0, 1.6)
            color = random.choice([(220, 200, 40), (40, 100, 200), (200, 40, 40)])
        elif type_roll < 0.45:
            # Motorcycle (Small, fast)
            v_type = VehicleType.MOTORCYCLE
            length = 20
            thickness = 10
            speed = random.uniform(2.5, 3.5)
            color = random.choice([(20, 20, 20), (200, 200, 200), (255, 50, 50)])
        else:
            # Car (Normal)
            v_type = VehicleType.CAR
            length = 34
            thickness = 18
            speed = random.uniform(1.8, 2.6)
            color = random.choice([(40, 170, 255), (255, 120, 40),
                                  (200, 200, 200), (180, 80, 255), (90, 220, 120)])

        if direction == Direction.DOWN:
            x = cx - lane_offset - (thickness // 2)
            y = -100
            width = thickness
            height = length
        elif direction == Direction.UP:
            x = cx + lane_offset - (thickness // 2)
            y = h + 100
            width = thickness
            height = length
        elif direction == Direction.RIGHT:
            x = -100
            y = cy + lane_offset - (thickness // 2)
            width = length
            height = thickness
        else:  # LEFT
            x = w + 100
            y = cy - lane_offset - (thickness // 2)
            width = length
            height = thickness

        # Keep within the road area.
        if direction in (Direction.DOWN, Direction.UP):
            x = max(cx - half + 10, min(x, cx + half - 30))
        else:
            y = max(cy - half + 10, min(y, cy + half - 30))

        roll = random.random()
        if roll < 0.60:
            turn_intention = TurnIntention.STRAIGHT
        elif roll < 0.80:
            turn_intention = TurnIntention.LEFT
        else:
            turn_intention = TurnIntention.RIGHT

        candidate = Vehicle(
            x=float(x),
            y=float(y),
            width=width,
            height=height,
            speed=float(speed),
            desired_speed=float(speed),
            color=color,
            direction=direction,
            turn_intention=turn_intention,
            has_turned=False,
            entered_intersection=False,
            v_type=v_type
        )

        safe = max(self._config.vehicle_gap_px, self._config.vehicle_safe_buffer_px)
        candidate_rect = pygame.Rect(int(candidate.x), int(
            candidate.y), candidate.width, candidate.height)
        for other in self._vehicles:
            if other.direction != candidate.direction:
                continue
            other_rect = pygame.Rect(int(other.x), int(other.y), other.width,
                                     other.height).inflate(safe * 2, safe * 2)
            if candidate_rect.colliderect(other_rect):
                self._next_spawn_at_ms = now + random.randint(150, 300)
                return

        self._vehicles.append(candidate)
        self._next_spawn_at_ms = now + self._rand_spawn_delay_ms()

    def _get_signal_for_direction(self, direction: Direction) -> TrafficSignalState:
        direction_to_id = {
            Direction.DOWN: 1,
            Direction.UP: 2,
            Direction.RIGHT: 3,
            Direction.LEFT: 4,
        }
        target_id = direction_to_id[direction]
        for s in self._controller.signals:
            if s.id == target_id:
                return s.state
        return TrafficSignalState.RED

    def _stop_line_for_vehicle(self, v: Vehicle) -> int:
        w, h = self._config.width, self._config.height
        cx, cy = w // 2, h // 2
        road_thickness = 220
        half = road_thickness // 2
        pad = 6

        if v.direction == Direction.DOWN:
            return cy - half - pad
        if v.direction == Direction.UP:
            return cy + half + pad
        if v.direction == Direction.RIGHT:
            return cx - half - pad
        return cx + half + pad

    def _can_cross_intersection(self, v: Vehicle) -> bool:
        state = self._get_signal_for_direction(v.direction)
        if state == TrafficSignalState.GREEN:
            return True
        return False

    def _update_vehicles(self) -> None:
        """
        Moves vehicles every frame using a strict 3-rule look-ahead approach.
        Fully uncompressed and readable version.
        """
        lane_gap_px = 5
        w, h = self._config.width, self._config.height
        cx, cy = w // 2, h // 2

        def rect_of(v: Vehicle) -> pygame.Rect:
            return pygame.Rect(int(v.x), int(v.y), v.width, v.height)

        def next_rect_of(v: Vehicle, step: float) -> pygame.Rect:
            if step <= 0:
                return rect_of(v)
            if v.direction == Direction.DOWN:
                return pygame.Rect(int(v.x), int(v.y + step), v.width, v.height)
            if v.direction == Direction.UP:
                return pygame.Rect(int(v.x), int(v.y - step), v.width, v.height)
            if v.direction == Direction.RIGHT:
                return pygame.Rect(int(v.x + step), int(v.y), v.width, v.height)
            return pygame.Rect(int(v.x - step), int(v.y), v.width, v.height)

        def front_position(v: Vehicle) -> float:
            if v.direction == Direction.DOWN:
                return v.y + v.height
            if v.direction == Direction.UP:
                return v.y
            if v.direction == Direction.RIGHT:
                return v.x + v.width
            return v.x  # LEFT

        def apply_step(v: Vehicle, step: float) -> None:
            if step <= 0:
                v.speed = 0.0
                return
            v.speed = v.desired_speed
            if v.direction == Direction.DOWN:
                v.y += step
            elif v.direction == Direction.UP:
                v.y -= step
            elif v.direction == Direction.RIGHT:
                v.x += step
            else:
                v.x -= step

        def maybe_turn_at_center(v: Vehicle, step: float) -> None:
            if v.has_turned or v.turn_intention == TurnIntention.STRAIGHT:
                return
            if not v.entered_intersection:
                return

            vx = v.x + v.width / 2.0
            vy = v.y + v.height / 2.0

            if v.direction in (Direction.UP, Direction.DOWN):
                if abs(vy - cy) <= max(1.0, step):
                    v.y = float(cy) - v.height / 2.0
                    if v.direction == Direction.UP:
                        v.direction = Direction.RIGHT if v.turn_intention == TurnIntention.RIGHT else Direction.LEFT
                    else:  # DOWN
                        v.direction = Direction.LEFT if v.turn_intention == TurnIntention.RIGHT else Direction.RIGHT

                    v.width, v.height = v.height, v.width
                    v.has_turned = True
            else:
                if abs(vx - cx) <= max(1.0, step):
                    v.x = float(cx) - v.width / 2.0
                    if v.direction == Direction.RIGHT:
                        v.direction = Direction.DOWN if v.turn_intention == TurnIntention.RIGHT else Direction.UP
                    else:  # LEFT
                        v.direction = Direction.UP if v.turn_intention == TurnIntention.RIGHT else Direction.DOWN

                    v.width, v.height = v.height, v.width
                    v.has_turned = True

        for direction in (Direction.DOWN, Direction.UP, Direction.RIGHT, Direction.LEFT):
            lane = [v for v in self._vehicles if v.direction == direction]
            if not lane:
                continue

            if direction == Direction.DOWN:
                lane.sort(key=lambda v: v.y, reverse=True)
            elif direction == Direction.UP:
                lane.sort(key=lambda v: v.y)
            elif direction == Direction.RIGHT:
                lane.sort(key=lambda v: v.x, reverse=True)
            else:  # LEFT
                lane.sort(key=lambda v: v.x)

            for idx, v in enumerate(lane):
                step = float(v.desired_speed)
                stop_line = float(self._stop_line_for_vehicle(v))
                f_now = float(front_position(v))

                if direction in (Direction.DOWN, Direction.RIGHT):
                    before_line = f_now <= stop_line
                    after_line = f_now > stop_line
                    f_next = f_now + step
                    crosses_line_next = before_line and f_next > stop_line
                else:
                    before_line = f_now >= stop_line
                    after_line = f_now < stop_line
                    f_next = f_now - step
                    crosses_line_next = before_line and f_next < stop_line

                if not v.entered_intersection:
                    if before_line:
                        if not self._can_cross_intersection(v) and crosses_line_next:
                            step = 0.0
                    elif after_line:
                        v.entered_intersection = True

                if step > 0.0 and idx > 0:
                    leader = lane[idx - 1]
                    next_rect = next_rect_of(v, step)

                    leader_rect = rect_of(leader).inflate(lane_gap_px * 2, lane_gap_px * 2)
                    if next_rect.colliderect(leader_rect):
                        step = 0.0

                apply_step(v, step)
                maybe_turn_at_center(v, step)

        margin = 100
        self._vehicles = [
            v
            for v in self._vehicles
            if not (
                v.x < -margin
                or v.x > w + margin
                or v.y < -margin
                or v.y > h + margin
            )
        ]

    def _draw_vehicles(self) -> None:
        """
        Draw vehicles with detailed procedural graphics. Fully expanded version.
        """
        for v in self._vehicles:
            rect = pygame.Rect(int(v.x), int(v.y), v.width, v.height)
            pygame.draw.rect(self._screen, v.color, rect, border_radius=4)

            glass_color = (20, 20, 30)
            headlight_color = (255, 255, 200)
            brake_light_color = (255, 30, 30)

            v_type = getattr(v, "v_type", VehicleType.CAR)
            is_motorcycle = v_type == VehicleType.MOTORCYCLE
            is_ambulance = v_type == VehicleType.AMBULANCE

            if is_ambulance:
                # Add a flashing siren on top
                siren_color_1 = (255, 0, 0)
                siren_color_2 = (0, 0, 255)
                siren_color = siren_color_1 if pygame.time.get_ticks() % 500 < 250 else siren_color_2

                if v.direction in (Direction.UP, Direction.DOWN):
                    siren_rect = (v.x + 2, v.y + v.height // 2 - 4, v.width - 4, 8)
                else:
                    siren_rect = (v.x + v.width // 2 - 4, v.y + 2, 8, v.height - 4)

                pygame.draw.rect(self._screen, siren_color, siren_rect, border_radius=2)

            if not is_motorcycle:
                if v.direction == Direction.UP:
                    pygame.draw.rect(self._screen, glass_color, (v.x + 2, v.y + 6, v.width - 4, 8))
                    pygame.draw.rect(self._screen, headlight_color, (v.x + 2, v.y, 4, 4))
                    pygame.draw.rect(self._screen, headlight_color, (v.x + v.width - 6, v.y, 4, 4))
                    if v.speed == 0:
                        pygame.draw.rect(self._screen, brake_light_color,
                                         (v.x + 2, v.y + v.height - 4, 6, 4))
                        pygame.draw.rect(self._screen, brake_light_color,
                                         (v.x + v.width - 8, v.y + v.height - 4, 6, 4))

                elif v.direction == Direction.DOWN:
                    pygame.draw.rect(
                        self._screen, glass_color, (v.x + 2, v.y + v.height - 14, v.width - 4, 8))
                    pygame.draw.rect(self._screen, headlight_color,
                                     (v.x + 2, v.y + v.height - 4, 4, 4))
                    pygame.draw.rect(self._screen, headlight_color,
                                     (v.x + v.width - 6, v.y + v.height - 4, 4, 4))
                    if v.speed == 0:
                        pygame.draw.rect(self._screen, brake_light_color, (v.x + 2, v.y, 6, 4))
                        pygame.draw.rect(self._screen, brake_light_color,
                                         (v.x + v.width - 8, v.y, 6, 4))

                elif v.direction == Direction.LEFT:
                    pygame.draw.rect(self._screen, glass_color, (v.x + 6, v.y + 2, 8, v.height - 4))
                    pygame.draw.rect(self._screen, headlight_color, (v.x, v.y + 2, 4, 4))
                    pygame.draw.rect(self._screen, headlight_color, (v.x, v.y + v.height - 6, 4, 4))
                    if v.speed == 0:
                        pygame.draw.rect(self._screen, brake_light_color,
                                         (v.x + v.width - 4, v.y + 2, 4, 6))
                        pygame.draw.rect(self._screen, brake_light_color,
                                         (v.x + v.width - 4, v.y + v.height - 8, 4, 6))

                elif v.direction == Direction.RIGHT:
                    pygame.draw.rect(
                        self._screen, glass_color, (v.x + v.width - 14, v.y + 2, 8, v.height - 4))
                    pygame.draw.rect(self._screen, headlight_color,
                                     (v.x + v.width - 4, v.y + 2, 4, 4))
                    pygame.draw.rect(self._screen, headlight_color,
                                     (v.x + v.width - 4, v.y + v.height - 6, 4, 4))
                    if v.speed == 0:
                        pygame.draw.rect(self._screen, brake_light_color, (v.x, v.y + 2, 4, 6))
                        pygame.draw.rect(self._screen, brake_light_color,
                                         (v.x, v.y + v.height - 8, 4, 6))
            else:
                if v.direction == Direction.UP:
                    pygame.draw.rect(self._screen, headlight_color,
                                     (v.x + v.width // 2 - 2, v.y, 4, 4))
                elif v.direction == Direction.DOWN:
                    pygame.draw.rect(self._screen, headlight_color,
                                     (v.x + v.width // 2 - 2, v.y + v.height - 4, 4, 4))
                elif v.direction == Direction.LEFT:
                    pygame.draw.rect(self._screen, headlight_color,
                                     (v.x, v.y + v.height // 2 - 2, 4, 4))
                elif v.direction == Direction.RIGHT:
                    pygame.draw.rect(self._screen, headlight_color,
                                     (v.x + v.width - 4, v.y + v.height // 2 - 2, 4, 4))

    def _draw_signal_light(self, *, x: int, y: int, state: TrafficSignalState,
                           timer: int, rotation_degrees: int = 0, is_top: bool = True) -> None:
        box_w, box_h = 34, 92
        radius = 10
        padding = 8

        horizontal = (rotation_degrees % 180) == 90
        if horizontal:
            box_w, box_h = box_h, box_w

        # Draw the Pole (Khamba)
        pole_color = (60, 60, 60)
        if not horizontal:
            if is_top:
                pygame.draw.rect(self._screen, pole_color, (x - 4, y + box_h // 2, 8, 30))
            else:
                pygame.draw.rect(self._screen, pole_color, (x - 4, y - box_h // 2 - 30, 8, 30))
        else:
            if is_top:
                pygame.draw.rect(self._screen, pole_color, (x + box_w // 2, y - 4, 30, 8))
            else:
                pygame.draw.rect(self._screen, pole_color, (x - box_w // 2 - 30, y - 4, 30, 8))

        # Housing
        rect = pygame.Rect(x - box_w // 2, y - box_h // 2, box_w, box_h)
        pygame.draw.rect(self._screen, (20, 20, 20), rect, border_radius=6)
        pygame.draw.rect(self._screen, (200, 180, 0), rect,
                         width=2, border_radius=6)  # Yellow border

        if not horizontal:
            centers = [
                (x, rect.top + padding + radius),
                (x, rect.top + padding + radius * 3 + 6),
                (x, rect.top + padding + radius * 5 + 12),
            ]
        else:
            centers = [
                (rect.left + padding + radius, y),
                (rect.left + padding + radius * 3 + 6, y),
                (rect.left + padding + radius * 5 + 12, y),
            ]

        on = {
            TrafficSignalState.RED: ((255, 40, 40), (80, 0, 0)),
            TrafficSignalState.YELLOW: ((255, 210, 0), (80, 60, 0)),
            TrafficSignalState.GREEN: ((0, 220, 0), (0, 70, 0)),
        }

        # Draw lights
        pygame.draw.circle(self._screen, on[TrafficSignalState.RED][1], centers[0], radius)
        pygame.draw.circle(self._screen, on[TrafficSignalState.YELLOW][1], centers[1], radius)
        pygame.draw.circle(self._screen, on[TrafficSignalState.GREEN][1], centers[2], radius)

        if state == TrafficSignalState.RED:
            pygame.draw.circle(self._screen, on[TrafficSignalState.RED][0], centers[0], radius)
        elif state == TrafficSignalState.YELLOW:
            pygame.draw.circle(self._screen, on[TrafficSignalState.YELLOW][0], centers[1], radius)
        else:
            pygame.draw.circle(self._screen, on[TrafficSignalState.GREEN][0], centers[2], radius)

        # Smart Timer Placement (Away from cars/crossings)
        if timer >= 0:
            text_color = on[state][0] if state != TrafficSignalState.RED else on[TrafficSignalState.RED][0]
            text_surface = self._font.render(f"{timer:02d}", True, text_color)
            text_rect = text_surface.get_rect()

            if not horizontal:
                if is_top:
                    text_rect.midbottom = (x, rect.top - 8)
                else:
                    text_rect.midtop = (x, rect.bottom + 8)
            else:
                if is_top:
                    text_rect.midright = (rect.left - 8, y)
                else:
                    text_rect.midleft = (rect.right + 8, y)

            bg_rect = text_rect.inflate(8, 4)
            pygame.draw.rect(self._screen, (10, 10, 10), bg_rect, border_radius=4)
            pygame.draw.rect(self._screen, (100, 100, 100), bg_rect, width=1, border_radius=4)
            self._screen.blit(text_surface, text_rect)
