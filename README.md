# Smart Traffic Management System

A Python-based **Smart Traffic Management System** that simulates a 4-way intersection using **Pygame** and manages signal timing with a **round-robin controller** plus **live “AI-like” congestion input**.  
It also supports **emergency (ambulance) override** and logs events to a **MySQL** database.

## Key Features

- **4-way intersection simulation (Pygame UI)**
- **Strict round-robin signal controller**
  - Only **one signal** can be **GREEN/YELLOW** at a time, others remain **RED**
- **Dynamic green time allocation**
  - Green duration is calculated from live queued vehicles:
    - `allocated = min_green + (queue_count * seconds_per_car)` (capped)
- **Emergency override (Ambulance)**
  - If an ambulance is detected waiting/approaching, controller prioritizes that lane with a generous GREEN window
- **Database logging (MySQL)**
  - Signal state transitions and AI decisions are stored in `traffic_logs`
  - Optional congestion snapshots in `congestion_data`
- **Docker support** (Python 3.12 slim)

---

## Project Structure

```
Smart-Traffic-Management-System/
├─ main.py
├─ requirements.txt
├─ Dockerfile
├─ schema.sql
└─ src/
   ├─ controllers/
   │  └─ traffic_controller.py
   ├─ database/
   │  └─ db_handler.py
   ├─ models/
   │  ├─ traffic_signal.py
   │  └─ vehicle.py
   └─ views/
      └─ simulation.py
```

---

## How It Works (High Level)

### Simulation (`src/views/simulation.py`)
- Runs a Pygame window and spawns vehicles from all four directions.
- Every 1 second it triggers a tick that calls:
  - `TrafficController.manage_traffic(tick_seconds=1)`
- Every few seconds it analyzes queued vehicles and sends live data to controller:
  - queued cars per signal (1..4)
  - emergency presence per signal (ambulance detection)

### Controller (`src/controllers/traffic_controller.py`)
- Maintains signal states and timers.
- Enforces invariant: **exactly one active (GREEN/YELLOW)** signal.
- When a signal becomes GREEN, it allocates duration dynamically based on queue snapshot.
- Logs:
  - `STATE_CHANGE`
  - `AI_DECISION`
  - `EMERGENCY_OVERRIDE`

### Database (`src/database/db_handler.py`)
- Uses MySQL via env-based configuration (`.env` supported).
- Provides methods like:
  - `insert_traffic_log(...)`
  - `insert_congestion_data(...)`
  - `fetch_latest_congestion(...)`

---

## Requirements

- Python **3.10+** recommended (Docker uses **3.12**)
- MySQL Server (XAMPP MySQL is fine)
- Pygame for simulation UI

Install dependencies:
```bash
pip install -r requirements.txt
```

> Note: Repo installs `pygame==2.6.1`. If you run into system-level SDL errors on Linux, install SDL dependencies for your OS.

---

## Database Setup (MySQL)

1. Create database:
```sql
CREATE DATABASE smart_traffic
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

2. Use it and create tables from `schema.sql`:
```sql
USE smart_traffic;
-- then run contents of schema.sql
```

Tables created:
- `traffic_logs` (state changes, AI decisions, emergency overrides)
- `congestion_data` (optional congestion snapshots)

---

## Environment Variables

Create a `.env` file (you can copy from `.env.example` if present):

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=smart_traffic
```

---

## Run Locally (Recommended)

```bash
python main.py
```

What you should see:
- A Pygame window with intersection
- Vehicles spawning randomly
- Signals switching with timers
- Console logs showing queue analysis + AI allocation
- MySQL logs inserted into `traffic_logs`

---

## Run with Docker

Build:
```bash
docker build -t smart-traffic .
```

Run:
```bash
docker run --rm smart-traffic
```

### Important Docker Notes
- This project uses a **Pygame UI**, which usually needs a display.
- The Dockerfile sets `SDL_VIDEODRIVER=dummy` to allow **headless** runs, but you may not see the UI inside Docker.
- If you want the UI, run locally (or configure X11 forwarding / VNC).

Also, if your MySQL is on your host machine, container networking may require:
- using `host.docker.internal` (on macOS/Windows) for `DB_HOST`
- or Docker network setup (on Linux)

---

## Signal IDs Mapping

The simulation and controller use 4 signals with IDs:

- **Signal 1**: Top approach (vehicles moving DOWN)
- **Signal 2**: Bottom approach (vehicles moving UP)
- **Signal 3**: Left approach (vehicles moving RIGHT)
- **Signal 4**: Right approach (vehicles moving LEFT)

---

## Customization

You can tweak simulation behavior in `SimulationConfig` inside:
- `src/views/simulation.py`

Examples:
- `ai_analyze_interval_ms` (how often queue analysis happens)
- spawn interval range
- speed ranges
- road size / visuals

You can tweak controller timing defaults in:
- `src/controllers/traffic_controller.py` (`min_green`, `max_green`, `yellow`, etc.)

---

## Troubleshooting

### 1) MySQL connection error
- Ensure MySQL is running
- Verify `.env` values
- Confirm database and tables exist (`schema.sql` applied)

### 2) Pygame not opening / SDL error
- Try running locally (not in Docker)
- Install OS dependencies for SDL (Linux)
- Ensure you have a graphical environment

---

## Future Improvements (Ideas)
- Real ML model integration for congestion prediction
- Sensors/camera feed integration
- Multi-intersection coordination
- REST API (FastAPI dependencies already present in `requirements.txt`)

---

## License
Add your license here (MIT/Apache-2.0/etc.)
