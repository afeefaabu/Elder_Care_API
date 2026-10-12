from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
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

        # SQL Server considers NULL a value in a unique index, which blocks a
        # second email-only or phone-only account.  Keep each identifier unique
        # when it exists, while allowing the other optional identifier to be NULL.
        if conn.dialect.name == "mssql":
            await _ensure_sqlserver_optional_identifier_indexes(conn)


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
