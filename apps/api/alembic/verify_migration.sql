-- ============================================================================
-- Migration Verification SQL
-- File: f1a2b3c4d5e6_add_foreign_keys_to_new_user_table.py
-- Purpose: Verify foreign key constraints before and after migration
-- ============================================================================

-- ============================================================================
-- BEFORE MIGRATION
-- ============================================================================
-- Run these queries BEFORE running: alembic upgrade head
-- Expected: Foreign keys pointing to 'users' table (UUID type)
-- ============================================================================

-- 1. Check all foreign key constraints that involve user_id columns
SELECT 
    tc.table_name,
    kcu.column_name,
    tc.constraint_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    rc.delete_rule,
    'BEFORE MIGRATION' AS status
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
  AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
  AND ccu.table_schema = tc.table_schema
JOIN information_schema.referential_constraints rc
  ON rc.constraint_name = tc.constraint_name
  AND rc.constraint_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY' 
  AND kcu.column_name = 'user_id'
  AND tc.table_name IN ('user_balances', 'jobs', 'credits_transactions', 'api_keys', 'usage_logs', 'payment_records')
ORDER BY tc.table_name;

-- Expected BEFORE migration:
-- table_name            | column_name | constraint_name                | foreign_table_name | foreign_column_name | delete_rule
-- ----------------------|-------------|--------------------------------|--------------------|---------------------|-------------
-- api_keys              | user_id     | api_keys_user_id_fkey          | users              | id                  | CASCADE
-- credits_transactions  | user_id     | credits_transactions_user_id_fkey | users           | id                  | CASCADE
-- jobs                  | user_id     | jobs_user_id_fkey              | users              | id                  | CASCADE
-- payment_records       | user_id     | payment_records_user_id_fkey   | users              | id                  | CASCADE
-- usage_logs            | user_id     | usage_logs_user_id_fkey        | users              | id                  | CASCADE
-- (user_balances may not have a foreign key yet)


-- 2. Check column data types
SELECT 
    table_name,
    column_name,
    data_type,
    udt_name,
    'BEFORE MIGRATION' AS status
FROM information_schema.columns
WHERE table_name IN ('user_balances', 'jobs', 'credits_transactions', 'api_keys', 'usage_logs', 'payment_records')
  AND column_name = 'user_id'
ORDER BY table_name;

-- Expected BEFORE migration: user_id columns should be 'text' type


-- 3. Check if 'user' table exists (from Next.js Dashboard)
SELECT 
    table_name,
    table_type,
    'BEFORE MIGRATION' AS status
FROM information_schema.tables
WHERE table_name IN ('user', 'users')
  AND table_schema = 'public'
ORDER BY table_name;

-- Expected: Both 'user' and 'users' tables should exist


-- 4. Count of records (to verify no data loss after migration)
SELECT 'user_balances' AS table_name, COUNT(*) AS record_count FROM user_balances
UNION ALL
SELECT 'jobs', COUNT(*) FROM jobs
UNION ALL
SELECT 'credits_transactions', COUNT(*) FROM credits_transactions
UNION ALL
SELECT 'api_keys', COUNT(*) FROM api_keys
UNION ALL
SELECT 'usage_logs', COUNT(*) FROM usage_logs
UNION ALL
SELECT 'payment_records', COUNT(*) FROM payment_records;

-- Save these counts to compare after migration


-- ============================================================================
-- AFTER MIGRATION
-- ============================================================================
-- Run these queries AFTER running: alembic upgrade head
-- Expected: Foreign keys pointing to 'user' table (text type)
-- ============================================================================

-- 1. Check all foreign key constraints (should now point to 'user' table)
SELECT 
    tc.table_name,
    kcu.column_name,
    tc.constraint_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name,
    rc.delete_rule,
    'AFTER MIGRATION' AS status
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
  AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
  AND ccu.table_schema = tc.table_schema
JOIN information_schema.referential_constraints rc
  ON rc.constraint_name = tc.constraint_name
  AND rc.constraint_schema = tc.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY' 
  AND kcu.column_name = 'user_id'
  AND tc.table_name IN ('user_balances', 'jobs', 'credits_transactions', 'api_keys', 'usage_logs', 'payment_records')
ORDER BY tc.table_name;

-- Expected AFTER migration:
-- table_name            | column_name | constraint_name                      | foreign_table_name | foreign_column_name | delete_rule
-- ----------------------|-------------|--------------------------------------|--------------------|---------------------|-------------
-- api_keys              | user_id     | fk_api_keys_user_id                  | user               | id                  | CASCADE
-- credits_transactions  | user_id     | fk_credits_transactions_user_id      | user               | id                  | CASCADE
-- jobs                  | user_id     | fk_jobs_user_id                      | user               | id                  | CASCADE
-- payment_records       | user_id     | fk_payment_records_user_id           | user               | id                  | CASCADE
-- usage_logs            | user_id     | fk_usage_logs_user_id                | user               | id                  | CASCADE
-- user_balances         | user_id     | fk_user_balances_user_id             | user               | id                  | CASCADE


-- 2. Verify all 6 tables have the new foreign keys
SELECT 
    tc.table_name,
    COUNT(*) AS fk_count
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
  AND kcu.column_name = 'user_id'
  AND ccu.table_name = 'user'
  AND tc.table_name IN ('user_balances', 'jobs', 'credits_transactions', 'api_keys', 'usage_logs', 'payment_records')
GROUP BY tc.table_name
ORDER BY tc.table_name;

-- Expected: 6 rows, each with fk_count = 1


-- 3. Check indexes were created
SELECT 
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename IN ('user_balances', 'jobs', 'credits_transactions', 'api_keys', 'usage_logs', 'payment_records')
  AND indexname LIKE 'idx_%user_id%'
ORDER BY tablename;

-- Expected: At least 6 indexes (one for each table)
-- idx_user_balances_user_id
-- idx_jobs_user_id
-- idx_credits_transactions_user_id
-- idx_api_keys_user_id
-- idx_usage_logs_user_id
-- idx_payment_records_user_id


-- 4. Verify no foreign keys still pointing to old 'users' table
SELECT 
    tc.table_name,
    kcu.column_name,
    tc.constraint_name,
    ccu.table_name AS foreign_table_name
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
  AND kcu.column_name = 'user_id'
  AND ccu.table_name = 'users'  -- Old table
ORDER BY tc.table_name;

-- Expected: 0 rows (no foreign keys should point to old 'users' table)


-- 5. Count of records (verify no data loss)
SELECT 'user_balances' AS table_name, COUNT(*) AS record_count FROM user_balances
UNION ALL
SELECT 'jobs', COUNT(*) FROM jobs
UNION ALL
SELECT 'credits_transactions', COUNT(*) FROM credits_transactions
UNION ALL
SELECT 'api_keys', COUNT(*) FROM api_keys
UNION ALL
SELECT 'usage_logs', COUNT(*) FROM usage_logs
UNION ALL
SELECT 'payment_records', COUNT(*) FROM payment_records;

-- Compare with BEFORE counts - should be identical


-- ============================================================================
-- QUICK VALIDATION SUMMARY
-- ============================================================================

-- Run this single query to get a quick overview AFTER migration
SELECT 
    'Total FKs to user table' AS check_description,
    COUNT(*) AS result,
    '6' AS expected
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
  AND kcu.column_name = 'user_id'
  AND ccu.table_name = 'user'
  AND tc.table_name IN ('user_balances', 'jobs', 'credits_transactions', 'api_keys', 'usage_logs', 'payment_records')

UNION ALL

SELECT 
    'Total FKs to users table (old)',
    COUNT(*),
    '0'
FROM information_schema.table_constraints AS tc 
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
  AND kcu.column_name = 'user_id'
  AND ccu.table_name = 'users'

UNION ALL

SELECT 
    'Total indexes on user_id',
    COUNT(*),
    '6'
FROM pg_indexes
WHERE tablename IN ('user_balances', 'jobs', 'credits_transactions', 'api_keys', 'usage_logs', 'payment_records')
  AND indexname LIKE 'idx_%user_id%';

-- All 'result' values should match 'expected' values
