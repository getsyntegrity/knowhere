"""Bootstrap helpers for API-only Better Auth user-table compatibility."""

from sqlalchemy import text
from sqlalchemy.engine import Connection

_DEFAULT_FALLBACK_EMAIL_DOMAIN: str = "knowhere.local"


def ensure_better_auth_user_table(
    connection: Connection,
    *,
    fallback_email_domain: str = _DEFAULT_FALLBACK_EMAIL_DOMAIN,
) -> None:
    """Ensure the minimal Better Auth-compatible ``user`` table exists."""
    connection.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS "user" (
                id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                "emailVerified" BOOLEAN DEFAULT false NOT NULL,
                image TEXT,
                role TEXT DEFAULT 'user' NOT NULL,
                "createdAt" TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
                "updatedAt" TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
            )
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE "user"
            ALTER COLUMN id SET NOT NULL,
            ALTER COLUMN name TYPE TEXT,
            ALTER COLUMN name SET NOT NULL,
            ALTER COLUMN email TYPE TEXT
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE "user"
            SET email = id || '@' || :fallback_email_domain
            WHERE email IS NULL
            """
        ),
        {"fallback_email_domain": fallback_email_domain},
    )
    connection.execute(
        text(
            """
            ALTER TABLE "user"
            ALTER COLUMN email SET NOT NULL
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE "user"
            ADD COLUMN IF NOT EXISTS "emailVerified" BOOLEAN DEFAULT false NOT NULL,
            ADD COLUMN IF NOT EXISTS image TEXT,
            ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user' NOT NULL,
            ADD COLUMN IF NOT EXISTS "createdAt" TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            ADD COLUMN IF NOT EXISTS "updatedAt" TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE "user"
            SET
                "emailVerified" = COALESCE("emailVerified", false),
                role = COALESCE(role, 'user'),
                "createdAt" = COALESCE("createdAt", now()),
                "updatedAt" = COALESCE("updatedAt", now())
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE "user"
            ALTER COLUMN "emailVerified" SET DEFAULT false,
            ALTER COLUMN "emailVerified" SET NOT NULL,
            ALTER COLUMN role SET DEFAULT 'user',
            ALTER COLUMN role SET NOT NULL,
            ALTER COLUMN "createdAt" SET DEFAULT now(),
            ALTER COLUMN "createdAt" SET NOT NULL,
            ALTER COLUMN "updatedAt" SET DEFAULT now(),
            ALTER COLUMN "updatedAt" SET NOT NULL
            """
        )
    )
    connection.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = '"user"'::regclass
                      AND contype = 'u'
                      AND conkey = ARRAY[
                          (
                              SELECT attnum::smallint
                              FROM pg_attribute
                              WHERE attrelid = '"user"'::regclass
                                AND attname = 'email'
                          )
                      ]
                ) THEN
                    ALTER TABLE "user"
                    ADD CONSTRAINT "user_email_unique" UNIQUE ("email");
                END IF;
            END $$;
            """
        )
    )
