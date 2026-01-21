"""Cleanup test users and related data from Supabase using service role key.

Usage: python scripts/cleanup_test_users.py
"""
from app.core.database import get_supabase_service_role

# List of explicit emails to remove
TARGET_EMAILS = {
    "nasriblog12@gmail.com",
    "regtest-sha@example.com",
    "regtest1@example.com",
    "regtest2@example.com",
    "regtest3@example.com",
}

# Remove any user with email starting with 'regtest'
PREFIXES = ("regtest",)


def main():
    sup = get_supabase_service_role()

    users_res = sup.table("users").select("*").execute()
    users = users_res.data or []

    to_delete = []
    for u in users:
        email = (u.get("email") or "").lower()
        if email in TARGET_EMAILS or any(email.startswith(p) for p in PREFIXES):
            to_delete.append(u)

    if not to_delete:
        print("No test users found to delete.")
        return

    print(f"Found {len(to_delete)} test users to delete")

    for u in to_delete:
        uid = u.get("id")
        email = u.get("email")
        print(f"-- Deleting user {email} (id={uid})")

        # Delete OTPs
        try:
            sup.table("otp_codes").delete().eq("user_id", uid).execute()
            print("   - deleted otp_codes")
        except Exception as e:
            print("   - failed to delete otp_codes:", e)

        # Delete keywords created by user
        try:
            sup.table("keywords").delete().eq("created_by", uid).execute()
            print("   - deleted keywords")
        except Exception as e:
            print("   - failed to delete keywords:", e)

        # Delete refresh tokens referencing user's sessions
        try:
            sup.table("refresh_tokens").delete().eq("user_id", uid).execute()
            print("   - deleted refresh_tokens")
        except Exception:
            pass

        # Remove user entry
        try:
            sup.table("users").delete().eq("id", uid).execute()
            print("   - deleted user row")
        except Exception as e:
            print("   - failed to delete user:", e)

        # If workspace exists, attempt to delete workspace and dependent rows
        wid = u.get("workspace_id")
        if wid:
            try:
                sup.table("keywords").delete().eq("workspace_id", wid).execute()
                sup.table("monitoring_cache").delete().eq("workspace_id", wid).execute()
                sup.table("workspace").delete().eq("id", wid).execute()
                print(f"   - deleted workspace {wid} and related rows")
            except Exception as e:
                print("   - failed to delete workspace or related rows:", e)

    print("Cleanup completed.")


if __name__ == "__main__":
    main()
