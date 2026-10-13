from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import inspect, text
from app.core.config import settings

def utc_now() -> datetime:
    """Returns naive UTC datetime, fully compatible with both SQLite and PostgreSQL asyncpg."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=connect_args,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # ``create_all`` does not alter an existing SQLite table.  Local
        # installations created before email/password login was added therefore
        # lack these user columns and crash when the login query selects them.
        if conn.dialect.name == "sqlite":
            await _ensure_sqlite_user_columns(conn)

        # SQL Server considers NULL a value in a unique index, which blocks a
        # second email-only or phone-only account.  Keep each identifier unique
        # when it exists, while allowing the other optional identifier to be NULL.
        if conn.dialect.name == "mssql":
            await _ensure_sqlserver_optional_identifier_indexes(conn)


async def _ensure_sqlite_user_columns(conn) -> None:
    """Bring pre-authentication SQLite user tables up to the current schema."""
    existing_columns = await conn.run_sync(
        lambda sync_conn: {
            column["name"]: column
            for column in inspect(sync_conn).get_columns("users")
        }
    )

    missing_columns = {
        "email": "VARCHAR(128)",
        "hashed_password": "VARCHAR(256)",
        "is_phone_verified": "BOOLEAN NOT NULL DEFAULT 0",
        "is_email_verified": "BOOLEAN NOT NULL DEFAULT 0",
    }
    for column_name, column_definition in missing_columns.items():
        if column_name not in existing_columns:
            await conn.execute(
                text(f"ALTER TABLE users ADD COLUMN {column_name} {column_definition}")
            )

    if not existing_columns["phone_number"]["nullable"]:
        await _rebuild_legacy_sqlite_users_table(conn)

    await conn.execute(
        text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)")
    )
    await conn.execute(
        text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_phone_number ON users (phone_number)")
    )


async def _rebuild_legacy_sqlite_users_table(conn) -> None:
    """Make phone_number optional in SQLite databases created before email login."""
    await conn.execute(
        text(
            "CREATE TABLE users_replacement ("
            "id INTEGER NOT NULL PRIMARY KEY, "
            "phone_number VARCHAR(32), "
            "email VARCHAR(128), "
            "hashed_password VARCHAR(256), "
            "full_name VARCHAR(128) NOT NULL, "
            "role VARCHAR(32) NOT NULL, "
            "relationship_to_elder VARCHAR(64), "
            "preferred_language VARCHAR(16), "
            "fcm_token VARCHAR(256), "
            "is_phone_verified BOOLEAN NOT NULL DEFAULT 0, "
            "is_email_verified BOOLEAN NOT NULL DEFAULT 0, "
            "is_active BOOLEAN DEFAULT 1, "
            "created_at DATETIME, "
            "updated_at DATETIME"
            ")"
        )
    )
    await conn.execute(
        text(
            "INSERT INTO users_replacement ("
            "id, phone_number, email, hashed_password, full_name, role, "
            "relationship_to_elder, preferred_language, fcm_token, "
            "is_phone_verified, is_email_verified, is_active, created_at, updated_at"
            ") SELECT "
            "id, phone_number, email, hashed_password, full_name, role, "
            "relationship_to_elder, preferred_language, fcm_token, "
            "is_phone_verified, is_email_verified, is_active, created_at, updated_at "
            "FROM users"
        )
    )
    await conn.execute(text("DROP TABLE users"))
    await conn.execute(text("ALTER TABLE users_replacement RENAME TO users"))


async def _ensure_sqlserver_optional_identifier_indexes(conn) -> None:
    """Replace legacy SQL Server unique indexes with NULL-safe filtered indexes."""
    for index_name, column_name in (
        ("ix_users_phone_number", "phone_number"),
        ("ix_users_email", "email"),
    ):
        index_exists = await conn.scalar(
            text(
                "SELECT COUNT(*) "
                "FROM sys.indexes "
                "WHERE object_id = OBJECT_ID(N'dbo.users') "
                "AND name = :index_name"
            ),
            {"index_name": index_name},
        )
        filter_definition = await conn.scalar(
            text(
                "SELECT filter_definition "
                "FROM sys.indexes "
                "WHERE object_id = OBJECT_ID(N'dbo.users') "
                "AND name = :index_name"
            ),
            {"index_name": index_name},
        )

        if index_exists and filter_definition is None:
            await conn.execute(
                text(f"DROP INDEX [{index_name}] ON [dbo].[users]")
            )

        if not filter_definition:
            await conn.execute(
                text(
                    f"CREATE UNIQUE INDEX [{index_name}] ON [dbo].[users] "
                    f"([{column_name}]) WHERE [{column_name}] IS NOT NULL"
                )
            )
