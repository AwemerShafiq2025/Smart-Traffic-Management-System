from __future__ import annotations

import os
from dataclasses import dataclass
from threading import RLock
from typing import Any, Mapping, Optional, TYPE_CHECKING

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # Agar python-dotenv install nahi hai toh OS env vars use honge

try:
    import mysql.connector  # type: ignore[import-not-found]
    from mysql.connector import Error as MySQLError  # type: ignore[import-not-found]
    from mysql.connector.connection import MySQLConnection  # type: ignore[import-not-found]
except ModuleNotFoundError as exc:  # pragma: no cover
    raise RuntimeError(
        "mysql-connector-python is not installed. Install it with: pip install mysql-connector-python"
    ) from exc

if TYPE_CHECKING:  # pragma: no cover
    pass


@dataclass(frozen=True, slots=True)
class DBConfig:
    # Ab yeh hardcoded nahi hain, balkay .env file se data uthayenge
    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", 3306))
    user: str = os.getenv("DB_USER", "root")
    password: str = os.getenv("DB_PASSWORD", "")
    database: str = os.getenv("DB_NAME", "smart_traffic")


class DatabaseHandler:
    _instance: Optional["DatabaseHandler"] = None
    _instance_lock: RLock = RLock()

    def __new__(cls, config: Optional[DBConfig] = None) -> "DatabaseHandler":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._config = config or DBConfig()
                    obj._conn = None
                    obj._conn_lock = RLock()
                    cls._instance = obj
        return cls._instance

    def __init__(self, config: Optional[DBConfig] = None) -> None:
        if config is not None:
            self._config = config

    def connect(self) -> MySQLConnection:
        with self._conn_lock:
            if self._conn is not None and self._conn.is_connected():
                return self._conn

            try:
                self._conn = mysql.connector.connect(
                    host=self._config.host,
                    port=self._config.port,  # Port bhi dynamic kar diya gaya hai
                    user=self._config.user,
                    password=self._config.password,
                    database=self._config.database,
                    autocommit=False,
                )
                return self._conn
            except MySQLError as exc:
                self._conn = None
                raise RuntimeError(f"Failed to connect to MySQL database '{self._config.database}'.") from exc

    def _execute_insert(self, query: str, params: Mapping[str, Any]) -> int:
        conn = self.connect()
        try:
            with self._conn_lock:
                cursor = conn.cursor()
                try:
                    cursor.execute(query, params)
                    conn.commit()
                    return int(cursor.lastrowid or 0)
                finally:
                    cursor.close()
        except MySQLError as exc:
            try:
                conn.rollback()
            except MySQLError:
                pass
            raise RuntimeError("Database insert failed.") from exc

    def fetch_latest_congestion(
        self, *, location: str, road_segment: Optional[str] = None
    ) -> Optional[Mapping[str, Any]]:
        """
        Returns the latest row from congestion_data for the given location/(optional) road_segment.
        """
        conn = self.connect()
        query = """
            SELECT id, location, road_segment, vehicle_count, average_speed_kmh, congestion_level, recorded_at
            FROM congestion_data
            WHERE location = %(location)s
              AND (%(road_segment)s IS NULL OR road_segment = %(road_segment)s)
            ORDER BY recorded_at DESC, id DESC
            LIMIT 1
        """
        params: Mapping[str, Any] = {"location": location, "road_segment": road_segment}

        try:
            with self._conn_lock:
                cursor = conn.cursor(dictionary=True)
                try:
                    cursor.execute(query, params)
                    row = cursor.fetchone()
                    return row
                finally:
                    cursor.close()
        except MySQLError as exc:
            raise RuntimeError("Database query failed.") from exc

    def insert_traffic_log(
        self,
        *,
        signal_id: int,
        event_type: str,
        old_state: Optional[str] = None,
        new_state: Optional[str] = None,
        details: Optional[str] = None,
    ) -> int:
        query = """
            INSERT INTO traffic_logs (signal_id, event_type, old_state, new_state, details)
            VALUES (%(signal_id)s, %(event_type)s, %(old_state)s, %(new_state)s, %(details)s)
        """
        return self._execute_insert(
            query,
            {
                "signal_id": signal_id,
                "event_type": event_type,
                "old_state": old_state,
                "new_state": new_state,
                "details": details,
            },
        )

    def insert_congestion_data(
        self,
        *,
        location: str,
        vehicle_count: int,
        congestion_level: int,
        road_segment: Optional[str] = None,
        average_speed_kmh: Optional[float] = None,
    ) -> int:
        query = """
            INSERT INTO congestion_data (
                location, road_segment, vehicle_count, average_speed_kmh, congestion_level
            )
            VALUES (
                %(location)s, %(road_segment)s, %(vehicle_count)s, %(average_speed_kmh)s, %(congestion_level)s
            )
        """
        return self._execute_insert(
            query,
            {
                "location": location,
                "road_segment": road_segment,
                "vehicle_count": vehicle_count,
                "average_speed_kmh": average_speed_kmh,
                "congestion_level": congestion_level,
            },
        )

    def close(self) -> None:
        with self._conn_lock:
            if self._conn is None:
                return
            try:
                if self._conn.is_connected():
                    self._conn.close()
            except MySQLError:
                pass
            finally:
                self._conn = None