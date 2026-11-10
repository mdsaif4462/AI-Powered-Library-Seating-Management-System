CREATE DATABASE IF NOT EXISTS library_seating CHARACTER SET utf8mb4;
USE library_seating;

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('student','admin') NOT NULL DEFAULT 'student',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS seats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    seat_code VARCHAR(10) NOT NULL UNIQUE,
    zone VARCHAR(50) NOT NULL,
    has_power TINYINT(1) NOT NULL DEFAULT 0,
    near_window TINYINT(1) NOT NULL DEFAULT 0,
    is_quiet TINYINT(1) NOT NULL DEFAULT 0,
    status ENUM('active','maintenance') NOT NULL DEFAULT 'active'
);

-- Slots are whole hours: start_hour (inclusive) to end_hour (exclusive), 24h clock
CREATE TABLE IF NOT EXISTS bookings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    seat_id INT NOT NULL,
    booking_date DATE NOT NULL,
    start_hour TINYINT NOT NULL,
    end_hour TINYINT NOT NULL,
    status ENUM('booked','checked_in','completed','cancelled','no_show') NOT NULL DEFAULT 'booked',
    no_show_risk FLOAT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_slot (seat_id, booking_date, start_hour, end_hour),
    INDEX idx_user (user_id, booking_date),
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (seat_id) REFERENCES seats(id)
);

CREATE TABLE IF NOT EXISTS occupancy_history (
    id INT AUTO_INCREMENT PRIMARY KEY,
    record_date DATE NOT NULL,
    hour TINYINT NOT NULL,
    day_of_week TINYINT NOT NULL,
    occupied INT NOT NULL,
    total_seats INT NOT NULL,
    is_exam_period TINYINT(1) NOT NULL DEFAULT 0,
    UNIQUE KEY uq_slot (record_date, hour)
);
