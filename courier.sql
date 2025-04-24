-- Create Database
CREATE DATABASE IF NOT EXISTS CourierDB;
USE CourierDB;

-- 1. Users Table
CREATE TABLE IF NOT EXISTS Users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(100) NOT NULL
);

-- 2. Couriers Table
CREATE TABLE IF NOT EXISTS Couriers (
    courier_id INT AUTO_INCREMENT PRIMARY KEY,
    sender_name VARCHAR(100) NOT NULL,
    receiver_name VARCHAR(100) NOT NULL,
    delivery_address TEXT NOT NULL,
    status ENUM('Pending', 'In Transit', 'Delivered') DEFAULT 'Pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Courier Status History (optional - for logs)
CREATE TABLE IF NOT EXISTS CourierStatusHistory (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    courier_id INT,
    status ENUM('Pending', 'In Transit', 'Delivered'),
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (courier_id) REFERENCES Couriers(courier_id) ON DELETE CASCADE
);

-- ========================
-- STORED PROCEDURES
-- ========================

-- Add New User
DELIMITER //
CREATE PROCEDURE AddUser(IN uname VARCHAR(50), IN upass VARCHAR(100))
BEGIN
    INSERT INTO Users(username, password) VALUES (uname, upass);
END;
//
DELIMITER ;

-- Login User
DELIMITER //
CREATE PROCEDURE LoginUser(IN uname VARCHAR(50), IN upass VARCHAR(100))
BEGIN
    SELECT user_id, username FROM Users WHERE username = uname AND password = upass;
END;
//
DELIMITER ;

-- Add Courier
DELIMITER //
CREATE PROCEDURE AddCourier(
    IN sender VARCHAR(100), 
    IN receiver VARCHAR(100), 
    IN address TEXT
)
BEGIN
    INSERT INTO Couriers(sender_name, receiver_name, delivery_address)
    VALUES (sender, receiver, address);
END;
//
DELIMITER ;

-- Update Courier Status
DELIMITER //
CREATE PROCEDURE UpdateCourierStatus(
    IN cid INT,
    IN new_status ENUM('Pending', 'In Transit', 'Delivered')
)
BEGIN
    UPDATE Couriers SET status = new_status WHERE courier_id = cid;
    INSERT INTO CourierStatusHistory(courier_id, status) VALUES (cid, new_status);
END;
//
DELIMITER ;

-- Get Courier By ID
DELIMITER //
CREATE PROCEDURE GetCourierById(IN cid INT)
BEGIN
    SELECT * FROM Couriers WHERE courier_id = cid;
END;
//
DELIMITER ;

-- Get All Couriers
DELIMITER //
CREATE PROCEDURE GetAllCouriers()
BEGIN
    SELECT * FROM Couriers ORDER BY created_at DESC;
END;
//
DELIMITER ;
