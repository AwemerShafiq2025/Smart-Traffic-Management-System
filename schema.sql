-- Smart Traffic Management System (XAMPP MySQL)
-- Create a database first (example): CREATE DATABASE smart_traffic CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
-- Then select it (example): USE smart_traffic;

CREATE TABLE IF NOT EXISTS traffic_logs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  signal_id BIGINT UNSIGNED NOT NULL,
  event_type VARCHAR(50) NOT NULL,
  old_state VARCHAR(10) NULL,
  new_state VARCHAR(10) NULL,
  details TEXT NULL,
  logged_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_traffic_logs_signal_time (signal_id, logged_at),
  KEY idx_traffic_logs_event_time (event_type, logged_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS congestion_data (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  location VARCHAR(255) NOT NULL,
  road_segment VARCHAR(255) NULL,
  vehicle_count INT UNSIGNED NOT NULL,
  average_speed_kmh DECIMAL(6,2) NULL,
  congestion_level TINYINT UNSIGNED NOT NULL,
  recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_congestion_location_time (location, recorded_at),
  KEY idx_congestion_level_time (congestion_level, recorded_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

