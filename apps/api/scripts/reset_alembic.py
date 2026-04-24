"""Reset the Alembic revision table so migrations can be replayed cleanly."""

import os
import sys

# Add the project root to the Python path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from shared.core.config import settings


def reset_alembic_version() -> None:
    """Delete every row from alembic_version if the table exists."""
    # Build a synchronous database URL by replacing asyncpg with psycopg2.
    sync_database_url = settings.DATABASE_URL.replace("asyncpg", "psycopg2")

    # Read SSL connect args from shared settings.
    ssl_connect_args = settings.get_ssl_connect_args()

    # Create the SQLAlchemy engine.
    engine = create_engine(
        sync_database_url,
        connect_args=ssl_connect_args,
    )

    try:
        with engine.connect() as connection:
            # Check whether the alembic_version table exists first.
            result = connection.execute(
                text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'alembic_version'
                );
            """)
            )
            table_exists = result.scalar()

            if table_exists:
                # Clear all stored revision rows.
                connection.execute(text("DELETE FROM alembic_version;"))
                connection.commit()
                print("✓ Cleared the alembic_version table")
            else:
                print("✓ alembic_version table does not exist; nothing to reset")

        print(
            "✓ Alembic revision state reset; you can regenerate the baseline migration"
        )

    except Exception as e:
        print(f"✗ Reset failed: {e}")
        sys.exit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    reset_alembic_version()
