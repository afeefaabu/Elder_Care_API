"""Create the initial administrator from private server configuration."""

import logging

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.models.user import User


logger = logging.getLogger("eldercare-api.admin-seed")


async def seed_default_admin() -> None:
    """Create one configured administrator if the database has none.

    A blank or placeholder password deliberately disables the seed. This
    prevents an application from starting with a known public credential.
    """
    name = settings.DEFAULT_ADMIN_NAME.strip()
    email = settings.DEFAULT_ADMIN_EMAIL.strip().lower()
    password = settings.DEFAULT_ADMIN_PASSWORD

    async with AsyncSessionLocal() as db:
        admin_exists = await db.scalar(
            select(User.id).where(User.role == "ADMIN").limit(1)
        )
        if admin_exists:
            return

        if not name or not email or not password:
            logger.warning(
                "No administrator exists. Set DEFAULT_ADMIN_NAME, "
                "DEFAULT_ADMIN_EMAIL and DEFAULT_ADMIN_PASSWORD in .env to seed one."
            )
            return
        if "@" not in email or len(password) < 8 or password.upper().startswith("CHANGE_"):
            logger.error(
                "Default administrator was not created: use a valid email and a "
                "private password of at least 8 characters in .env."
            )
            return

        conflicting_user = await db.scalar(select(User.id).where(User.email == email))
        if conflicting_user:
            logger.error(
                "Default administrator was not created because the configured email is already in use."
            )
            return

        db.add(
            User(
                full_name=name,
                email=email,
                hashed_password=get_password_hash(password),
                role="ADMIN",
                relationship_to_elder="System Administrator",
                is_email_verified=True,
                is_active=True,
            )
        )
        await db.commit()
        logger.info("Configured administrator account created for %s.", email)
