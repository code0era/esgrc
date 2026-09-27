"""
ESGRC/scripts/seed_platform_admin.py

Out-of-band bootstrap for the FIRST platform SUPER_ADMIN + platform organisation.

POST /auth/organisations is SUPER_ADMIN-gated (client orgs are provisioned by the
platform). A fresh install therefore has no API path to create the first
super-admin - that chicken-and-egg is broken here, by writing the platform org +
SUPER_ADMIN user directly via the ORM.

Usage (run once, against the target DATABASE_URL):

    PLATFORM_ADMIN_EMAIL=you@example.com \\
    PLATFORM_ADMIN_PASSWORD='a-strong-password' \\
    PLATFORM_ADMIN_NAME='Platform Root' \\
    DATABASE_URL=postgresql+psycopg://... \\
    python ESGRC/scripts/seed_platform_admin.py

Idempotent: if a user with that email already exists, it does nothing.
"""
import os
import sys

# Allow running as a plain script from the repo root or ESGRC/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models.models import Organisation, User, UserRole  # noqa: E402
from app.services.auth import hash_password  # noqa: E402


def main() -> int:
    email = os.getenv("PLATFORM_ADMIN_EMAIL")
    password = os.getenv("PLATFORM_ADMIN_PASSWORD")
    name = os.getenv("PLATFORM_ADMIN_NAME", "Platform Root")
    if not email or not password:
        print("ERROR: set PLATFORM_ADMIN_EMAIL and PLATFORM_ADMIN_PASSWORD.", file=sys.stderr)
        return 2

    # Login always looks up by lowercased, stripped email (see
    # app/crud/auth_crud.py:get_user_by_email). Normalise here too so a
    # mixed-case PLATFORM_ADMIN_EMAIL doesn't seed a user that can never log in.
    email = email.strip().lower()

    db = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is not None:
            print(f"User {email} already exists (role={existing.role.value}); nothing to do.")
            return 0

        org = db.execute(
            select(Organisation).where(Organisation.slug == "platform")
        ).scalar_one_or_none()
        if org is None:
            org = Organisation(name="Platform", slug="platform")
            db.add(org)
            db.flush()

        admin = User(
            organisation_id=org.id,
            email=email,
            full_name=name,
            hashed_password=hash_password(password),
            role=UserRole.SUPER_ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print(f"Created SUPER_ADMIN {email} in org '{org.slug}'.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
