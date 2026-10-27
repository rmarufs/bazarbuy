import argparse
import asyncio

from app.core.database import async_session_factory, engine
from app.services import auth_service, setting_service


async def create_admin(username: str, password: str) -> None:
    """Create the admin (or reset the password) and ensure the Setting row exists."""
    async with async_session_factory() as session:
        await auth_service.upsert_admin(session, username, password)
        await setting_service.get_setting(session)
    await engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create-admin", help="create or update the admin")
    create.add_argument("username")
    create.add_argument("password")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "create-admin":
        asyncio.run(create_admin(args.username, args.password))
        print(f"Admin '{args.username}' is ready.")


if __name__ == "__main__":
    main()
