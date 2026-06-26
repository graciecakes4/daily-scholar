#!/usr/bin/env python3
"""
Bootstrap an admin user for Daily Scholar's in-app auth (Phase A).

After deploying Phase A you'll have a `users` table but no rows in it.
This script seeds the first admin so you can log in and (eventually)
approve other signups via the admin UI in Phase F.

Idempotent: if an account with the same email already exists, the
password is reset, status is forced to `active`, and role is forced
to `admin`. Useful when you've forgotten your password or accidentally
demoted yourself.

Usage:
    python scripts/create_admin.py --email you@example.com --password 's3cret!'
    python scripts/create_admin.py --email you@example.com --password 's3cret!' --user-id grace
    python scripts/create_admin.py --email you@example.com  # prompts for password

The script reads DATABASE_URL from the environment (same as the app) so
it works against local SQLite, Railway Postgres, or any other backend
the app supports.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime
from pathlib import Path

# put repo root on sys.path so `from backend...` works when invoked directly
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.database import (  # noqa: E402
    USER_ROLE_ADMIN,
    USER_STATUS_ACTIVE,
    User,
    create_tables,
    get_session,
)
from backend.services.auth_security import (  # noqa: E402
    InvalidEmailError,
    InvalidUserIdError,
    default_user_id_from_email,
    hash_password,
    validate_email,
    validate_user_id,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Login email for the admin account.")
    parser.add_argument(
        "--password",
        default=None,
        help="Plaintext password. If omitted, the script prompts (does not echo).",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="Custom handle. Defaults to the email when omitted.",
    )
    args = parser.parse_args()

    # validate / normalize inputs
    try:
        email = validate_email(args.email)
    except InvalidEmailError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    if args.user_id is None:
        user_id = default_user_id_from_email(email)
    else:
        try:
            user_id = validate_user_id(args.user_id)
        except InvalidUserIdError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2

    password = args.password
    if not password:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm:  ")
        if password != confirm:
            print("ERROR: passwords do not match", file=sys.stderr)
            return 2

    if len(password) < 8:
        print("ERROR: password must be at least 8 characters", file=sys.stderr)
        return 2

    # make sure the schema is in place before we try to insert
    create_tables()

    session = get_session()
    try:
        existing = session.query(User).filter(User.email == email).first()
        if existing is not None:
            existing.password_hash = hash_password(password)
            existing.status = USER_STATUS_ACTIVE
            existing.role = USER_ROLE_ADMIN
            if existing.user_id != user_id:
                # the user_id might also collide with someone else — check first
                collision = (
                    session.query(User)
                    .filter(User.user_id == user_id, User.id != existing.id)
                    .first()
                )
                if collision is not None:
                    print(
                        f"ERROR: user_id {user_id!r} is already taken by another account; "
                        f"omit --user-id or pick a different one",
                        file=sys.stderr,
                    )
                    return 3
                existing.user_id = user_id
            session.commit()
            print(f"✓ Updated existing admin {email} (user_id={existing.user_id})")
            return 0

        # fresh insert — also check user_id uniqueness so the error is clear
        if session.query(User).filter(User.user_id == user_id).first() is not None:
            print(
                f"ERROR: user_id {user_id!r} is already taken; pick a different --user-id",
                file=sys.stderr,
            )
            return 3

        user = User(
            email=email,
            user_id=user_id,
            password_hash=hash_password(password),
            status=USER_STATUS_ACTIVE,
            role=USER_ROLE_ADMIN,
            created_at=datetime.utcnow(),
            approved_at=datetime.utcnow(),
        )
        session.add(user)
        session.commit()
        print(f"✓ Created admin {email} (user_id={user_id})")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
