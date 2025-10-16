-- PostgreSQL 数据库初始化脚本
-- 使用root用户，数据库名为Knowhere

-- 创建扩展（如果需要）
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- 设置数据库编码
SET client_encoding = 'UTF8';

-- 设置时区
SET timezone = 'UTC';

-- 设置搜索路径
ALTER DATABASE "Knowhere" SET search_path TO public;
