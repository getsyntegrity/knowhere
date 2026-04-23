-- Create the database and user if they do not already exist.
CREATE DATABASE IF NOT EXISTS aismart_bid CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Create the user if it does not already exist.
CREATE USER IF NOT EXISTS 'aismart_user'@'%' IDENTIFIED BY 'aismart123';

-- Grant privileges.
GRANT ALL PRIVILEGES ON aismart_bid.* TO 'aismart_user'@'%';

-- Flush privileges.
FLUSH PRIVILEGES;

-- Select the database.
USE aismart_bid;

-- Set the character set.
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;
