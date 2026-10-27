from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import Admin


async def get_admin_by_username(session: AsyncSession, username: str) -> Admin | None:
    result = await session.execute(select(Admin).where(Admin.username == username))
    return result.scalar_one_or_none()


async def authenticate(
    session: AsyncSession, username: str, password: str
) -> Admin | None:
    """Return the admin if the credentials are correct, otherwise None."""
    admin = await get_admin_by_username(session, username)
    if admin is None or not verify_password(password, admin.password_hash):
        return None
    return admin


async def upsert_admin(session: AsyncSession, username: str, password: str) -> Admin:
    """Create the admin, or update the password if the username already exists."""
    admin = await get_admin_by_username(session, username)
    if admin is None:
        admin = Admin(username=username, password_hash=hash_password(password))
        session.add(admin)
    else:
        admin.password_hash = hash_password(password)
    await session.commit()
    return admin
