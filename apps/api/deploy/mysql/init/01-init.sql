-- 创建数据库和用户（如果不存在）
CREATE DATABASE IF NOT EXISTS aismart_bid CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 创建用户（如果不存在）
CREATE USER IF NOT EXISTS 'aismart_user'@'%' IDENTIFIED BY 'aismart123';

-- 授权
GRANT ALL PRIVILEGES ON aismart_bid.* TO 'aismart_user'@'%';

-- 刷新权限
FLUSH PRIVILEGES;

-- 使用数据库
USE aismart_bid;

-- 设置字符集
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;
