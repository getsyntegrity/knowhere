"""add foreign keys to new user table

Revision ID: f1a2b3c4d5e6
Revises: e8b123456789
Create Date: 2026-02-03 18:44:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e8b123456789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def foreign_key_exists(table_name: str, constraint_name: str) -> bool:
    """Check if a foreign key constraint exists."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    try:
        foreign_keys = inspector.get_foreign_keys(table_name)
        return any(fk['name'] == constraint_name for fk in foreign_keys)
    except Exception:
        return False


def index_exists(table_name: str, index_name: str) -> bool:
    """Check if an index exists."""
    try:
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        indexes = inspector.get_indexes(table_name)
        return any(idx['name'] == index_name for idx in indexes)
    except Exception:
        return False


def upgrade() -> None:
    """
    Complete user_id migration from old UUID-based users table to new Text-based user table.
    
    Steps:
    1. Drop deprecated tables (oauth_providers, email_logs)
    2. Convert all user_id columns from UUID to Text
    3. Drop old foreign keys pointing to users.id (UUID)
    4. Add new foreign keys pointing to user.id (Text)
    5. Add indexes for performance
    
    Tables updated:
    - user_balances
    - jobs
    - credits_transactions
    - api_keys
    - usage_logs
    - payment_records
    
    Tables dropped:
    - oauth_providers (deprecated, not maintained)
    - email_logs (deprecated, not maintained)
    - subscriptions (deprecated, not maintained)
    - roles (deprecated, not maintained)
    """
    
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    # STEP 0: Drop deprecated tables
    deprecated_tables = ['oauth_providers', 'email_logs', 'subscriptions', 'roles']
    for table_name in deprecated_tables:
        if table_name in inspector.get_table_names():
            print(f"Dropping deprecated table: {table_name}")
            op.drop_table(table_name)

    
    # List of tables with user_id that need migration
    tables_to_migrate = [
        {
            'table': 'user_balances',
            'new_fk': 'fk_user_balances_user_id',
            'index': 'idx_user_balances_user_id',
            'nullable': False,
            'cascade': True
        },
        {
            'table': 'jobs',
            'new_fk': 'fk_jobs_user_id',
            'index': 'idx_jobs_user_id',
            'nullable': False,
            'cascade': True
        },
        {
            'table': 'credits_transactions',
            'new_fk': 'fk_credits_transactions_user_id',
            'index': 'idx_credits_transactions_user_id',
            'nullable': False,
            'cascade': True
        },
        {
            'table': 'api_keys',
            'new_fk': 'fk_api_keys_user_id',
            'index': 'idx_api_keys_user_id',
            'nullable': False,
            'cascade': True
        },
        {
            'table': 'usage_logs',
            'new_fk': 'fk_usage_logs_user_id',
            'index': 'idx_usage_logs_user_id',
            'nullable': False,
            'cascade': True
        },
        {
            'table': 'payment_records',
            'new_fk': 'fk_payment_records_user_id',
            'index': 'idx_payment_records_user_id',
            'nullable': False,
            'cascade': True
        }
    ]
    
    for config in tables_to_migrate:
        table_name = config['table']
        new_fk_name = config['new_fk']
        index_name = config['index']
        nullable = config['nullable']
        cascade = config['cascade']
        
        # Check if table exists
        if table_name not in inspector.get_table_names():
            print(f"Skipping {table_name} - table does not exist")
            continue
        
        print(f"Processing {table_name}...")
        
        # STEP 1: Drop all existing foreign keys on user_id column
        try:
            existing_fks = inspector.get_foreign_keys(table_name)
            for fk in existing_fks:
                if 'user_id' in fk.get('constrained_columns', []):
                    fk_name = fk['name']
                    if fk_name:
                        print(f"  Dropping old FK: {fk_name}")
                        op.drop_constraint(fk_name, table_name, type_='foreignkey')
        except Exception as e:
            print(f"  Warning: Could not drop FKs for {table_name}: {e}")
        
        # STEP 2: Convert user_id column from UUID to Text
        # Use raw SQL to handle the conversion safely
        try:
            # Check current column type
            columns = inspector.get_columns(table_name)
            user_id_col = next((c for c in columns if c['name'] == 'user_id'), None)
            
            if user_id_col:
                col_type = str(user_id_col['type'])
                print(f"  Current user_id type: {col_type}")
                
                # Only convert if it's UUID type
                if 'UUID' in col_type.upper():
                    print(f"  Converting user_id from UUID to Text...")
                    # Convert UUID to Text - cast UUID to text representation
                    op.execute(f'ALTER TABLE {table_name} ALTER COLUMN user_id TYPE TEXT USING user_id::text')
                else:
                    print(f"  user_id already Text type, skipping conversion")
        except Exception as e:
            print(f"  Warning: Could not convert user_id type for {table_name}: {e}")
        
        # STEP 3: Add new foreign key pointing to public.user table
        if not foreign_key_exists(table_name, new_fk_name):
            print(f"  Creating new FK: {new_fk_name}")
            ondelete = 'CASCADE' if cascade else 'SET NULL'
            op.create_foreign_key(
                new_fk_name,
                table_name,
                'user',
                ['user_id'],
                ['id'],
                ondelete=ondelete
            )
        else:
            print(f"  FK {new_fk_name} already exists")
        
        # STEP 4: Add index for foreign key performance
        if not index_exists(table_name, index_name):
            print(f"  Creating index: {index_name}")
            op.create_index(index_name, table_name, ['user_id'])
        else:
            print(f"  Index {index_name} already exists")
    
    print("Migration complete!")



def downgrade() -> None:
    """
    Revert changes - remove foreign keys to public.user table.
    
    WARNING: This does NOT restore foreign keys to the old users table,
    does NOT convert columns back to UUID, and does NOT restore dropped tables.
    """
    
    tables_to_revert = [
        {
            'table': 'user_balances',
            'fk': 'fk_user_balances_user_id',
            'index': 'idx_user_balances_user_id'
        },
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
        }
    ]
    
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    for config in tables_to_revert:
        table_name = config['table']
        fk_name = config['fk']
        index_name = config['index']
        
        if table_name not in inspector.get_table_names():
            continue
        
        # Drop index
        if index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        
        # Drop foreign key
        if foreign_key_exists(table_name, fk_name):
            op.drop_constraint(fk_name, table_name, type_='foreignkey')

