-- PostgreSQL database initialization script.
-- Uses the root user and the Knowhere database.

-- Create extensions if they are needed.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Set the database encoding.
SET client_encoding = 'UTF8';

-- Set the timezone.
SET timezone = 'UTC';

-- Set the search path.
ALTER DATABASE "Knowhere" SET search_path TO public;
