"""Cleanup test users and related data from PostgreSQL.

otp_codes and user_keywords go away via ON DELETE CASCADE, so only users and
their workspaces need explicit deletes.

Usage: python scripts/cleanup_test_users.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import init_pool, close_pool, fetch_all, execute

# List of explicit emails to remove
TARGET_EMAILS = [
    "nasriblog12@gmail.com",
    "regtest-sha@example.com",
    "regtest1@example.com",
    "regtest2@example.com",
    "regtest3@example.com",
]

# Remove any user with email starting with 'regtest'
PREFIXES = ["regtest"]


async def main():
    await init_pool()
    try:
        to_delete = await fetch_all(
            """
            SELECT id, email, workspace_id FROM users
             WHERE lower(email) = ANY($1) OR lower(email) LIKE ANY($2)
            """,
            [e.lower() for e in TARGET_EMAILS],
            [f"{p}%" for p in PREFIXES],
        )

        if not to_delete:
            print("No test users found to delete.")
            return

        print(f"Found {len(to_delete)} test users to delete")

        user_ids = [u["id"] for u in to_delete]
        workspace_ids = [u["workspace_id"] for u in to_delete if u["workspace_id"]]

        for u in to_delete:
            print(f"-- Deleting user {u['email']} (id={u['id']})")

        print(await execute("DELETE FROM users WHERE id = ANY($1)", user_ids))

        if workspace_ids:
            print(await execute("DELETE FROM workspace WHERE id = ANY($1)", workspace_ids))

        print("Cleanup completed.")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
