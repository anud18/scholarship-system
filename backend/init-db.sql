-- Initialize scholarship database
-- This script sets up the basic database structure

-- Create extension for UUID generation if not exists
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create extension for PostgreSQL functions
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Set timezone
SET timezone = 'UTC';

-- Database is ready for Alembic migrations