"""add foreign keys with dummy user strategy

Revision ID: abc123def456
Revises: e8b123456789
Create Date: 2026-02-03 21:30:00.000000

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = 'abc123def456'
down_revision: Union[str, Sequence[str], None] = 'e8b123456789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Dummy user ID for development data
DUMMY_USER_ID = 'dev_placeholder_user'


def upgrade() -> None:
    """
    Dummy user migration strategy:
   1. Create placeholder user in Dashboard's user table
    2. Rename deprecated tables (preserve all data)
    3. Link existing data to dummy user
    4. Add foreign keys with RESTRICT
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    timestamp = datetime.now().strftime('%Y%m%d')
    
    print("=" * 70)
    print("MIGRATION: Dummy User Strategy")
    print("=" * 70)
    
    # STEP 1: Create dummy user in Dashboard's user table
    print(f"\n[STEP 1] Creating placeholder user: {DUMMY_USER_ID}")
    
    # Check if user table exists
    if 'user' not in inspector.get_table_names():
        raise Exception("Dashboard's 'user' table not found! Ensure Dashboard migrations ran first.")
    
    # Check if dummy user already exists
    result = bind.execute(text(f"SELECT COUNT(*) FROM \"user\" WHERE id = '{DUMMY_USER_ID}'"))
    if result.scalar() == 0:
        print(f"  Creating dummy user...")
        bind.execute(text(f"""
            INSERT INTO "user" (id, email, name, "createdAt", "updatedAt")
            VALUES (
                '{DUMMY_USER_ID}',
                'dev-placeholder@knowhere.internal',
                'Development Placeholder User',
                NOW(),
                NOW()
            )
        """))
        print(f"  ✓ Dummy user created: {DUMMY_USER_ID}")
    else:
        print(f"  ✓ Dummy user already exists")
    
    # STEP 2: Rename deprecated tables
    print("\n[STEP 2] Renaming deprecated tables...")
    deprecated_tables = ['users', 'oauth_providers', 'email_logs', 'subscriptions', 'roles']
    
    for table_name in deprecated_tables:
        if table_name in inspector.get_table_names():
            new_name = f"_deprecated_{table_name}_{timestamp}"
            print(f"  {table_name} → {new_name}")
            op.rename_table(table_name, new_name)
        else:
            print(f"  Skipping {table_name} (doesn't exist)")
    
    # STEP 3: Drop old FK constraints on user_id
    print("\n[STEP 3] Dropping old foreign key constraints...")
    tables_with_user_id = [
        'jobs', 'credits_transactions',
        'api_keys', 'usage_logs', 'payment_records', 'webhook_secrets'
    ]
    
    for table_name in tables_with_user_id:
        if table_name not in inspector.get_table_names():
            print(f"  Skipping {table_name} (doesn't exist)")
            continue
        
        fks = inspector.get_foreign_keys(table_name)
        for fk in fks:
            if 'user_id' in fk.get('constrained_columns', []):
                fk_name = fk['name']
                if fk_name:
                    print(f"  Dropping {table_name}.{fk_name}")
                    try:
                        op.drop_constraint(fk_name, table_name, type_='foreignkey')
                    except Exception as e:
                        print(f"    Warning: {e}")
    
    # STEP 4: Convert UUID → Text and link to dummy user
    print("\n[STEP 4] Converting UUID → Text and linking to dummy user...")
    
    for table_name in tables_with_user_id:
        if table_name not in inspector.get_table_names():
            continue
        
        columns = inspector.get_columns(table_name)
        user_id_col = next((c for c in columns if c['name'] == 'user_id'), None)
        
        if user_id_col:
            col_type = str(user_id_col['type']).upper()
            
            # Convert UUID to Text if needed
            if 'UUID' in col_type:
                print(f"  {table_name}.user_id: UUID → Text + link to dummy user")
                bind.execute(text(f"""
                    ALTER TABLE {table_name} 
                    ALTER COLUMN user_id TYPE TEXT 
                    USING '{DUMMY_USER_ID}'
                """))
            else:
                # Already Text, just update to dummy user
                print(f"  {table_name}: Linking all records to dummy user")
                bind.execute(text(f"""
                    UPDATE {table_name} SET user_id = '{DUMMY_USER_ID}'
                """))
    
    # STEP 5: Add new FK constraints
    print("\n[STEP 5] Adding foreign key constraints (all RESTRICT)...")
    fk_configs = [
        {
            'table': 'jobs',
            'fk': 'fk_jobs_user_id',
            'index': 'idx_jobs_user_id'
        },
        {
            'table': 'credits_transactions',
            'fk': 'fk_credits_transactions_user_id',
            'index': 'idx_credits_transactions_user_id'
        },
        {
            'table': 'api_keys',
            'fk': 'fk_api_keys_user_id',
            'index': 'idx_api_keys_user_id'
        },
        {
            'table': 'usage_logs',
            'fk': 'fk_usage_logs_user_id',
            'index': 'idx_usage_logs_user_id'
        },
        {
            'table': 'payment_records',
            'fk': 'fk_payment_records_user_id',
            'index': 'idx_payment_records_user_id'
        },
        {
            'table': 'webhook_secrets',
            'fk': 'fk_webhook_secrets_user_id',
            'index': 'idx_webhook_secrets_user_id'
        }
    ]
    
    for config in fk_configs:
        table = config['table']
        if table not in inspector.get_table_names():
            continue
        
        # Add FK
        print(f"  {table}: Adding {config['fk']} (ON DELETE RESTRICT)")
        try:
            op.create_foreign_key(
                config['fk'],
                table,
                'user',
                ['user_id'],
                ['id'],
                ondelete='RESTRICT'
            )
        except Exception as e:
            print(f"    Warning: {e}")
        
        # Add index if doesn't exist
        index_name = config['index']
        existing_indexes = [idx['name'] for idx in inspector.get_indexes(table)]
        if index_name not in existing_indexes:
            print(f"  {table}: Adding index {index_name}")
            try:
                op.create_index(index_name, table, ['user_id'])
            except Exception as e:
                print(f"    Warning: {e}")
    
    print("\n" + "=" * 70)
    print("MIGRATION COMPLETE ✓")
    print("=" * 70)
    print("\nResults:")
    print(f"  ✓ Dummy user created: {DUMMY_USER_ID}")
    print("  ✓ All dev data linked to dummy user")
    print("  ✓ Deprecated tables renamed (preserved)")
    print("  ✓ Foreign keys added with RESTRICT")
    print("\nProduction users will create real user records in Dashboard.")


def downgrade() -> None:
    """
    Partial downgrade: removes FK constraints and indexes.
    Does NOT restore renamed tables (manual operation if needed).
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    print("Downgrading migration...")
    
    fk_configs = [
        {'table': 'jobs', 'fk': 'fk_jobs_user_id', 'index': 'idx_jobs_user_id'},
        {'table': 'credits_transactions', 'fk': 'fk_credits_transactions_user_id', 'index': 'idx_credits_transactions_user_id'},
        {'table': 'api_keys', 'fk': 'fk_api_keys_user_id', 'index': 'idx_api_keys_user_id'},
        {'table': 'usage_logs', 'fk': 'fk_usage_logs_user_id', 'index': 'idx_usage_logs_user_id'},
        {'table': 'payment_records', 'fk': 'fk_payment_records_user_id', 'index': 'idx_payment_records_user_id'},
        {'table': 'webhook_secrets', 'fk': 'fk_webhook_secrets_user_id', 'index': 'idx_webhook_secrets_user_id'},
    ]
    
    for config in fk_configs:
        table = config['table']
        if table not in inspector.get_table_names():
            continue
        
        # Drop index
        if config['index'] in [idx['name'] for idx in inspector.get_indexes(table)]:
            op.drop_index(config['index'], table_name=table)
        
        # Drop FK
        if any(fk['name'] == config['fk'] for fk in inspector.get_foreign_keys(table)):
            op.drop_constraint(config['fk'], table, type_='foreignkey')
    
    print("Downgrade complete. Renamed tables NOT restored (manual operation if needed).")
