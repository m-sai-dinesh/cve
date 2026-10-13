"""Seed demo users and the AcmeLIMS project (PRD §20.3 `make seed`).

    python -m app.seed

Idempotent: running it twice does not duplicate anything.
"""
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select

from .config import REPO_ROOT
from .core.audit import record
from .db.models import Project, User
from .db.session import init_db, session_scope

# PRD §18: no login screen; a header switcher picks one of these, and that name
# is recorded on approvals, overrides and audit rows.
DEMO_USERS: list[tuple[str, str]] = [
    ("Modernization Lead", "Pharma IT Advisor"),
]


def seed() -> dict[str, object]:
    init_db()
    created_users: list[str] = []

    with session_scope() as s:
        for name, role in DEMO_USERS:
            existing = s.execute(select(User).where(User.name == name)).scalar_one_or_none()
            if existing is None:
                s.add(User(name=name, role=role))
                created_users.append(f"{name} ({role})")
        s.flush()
        architect = s.execute(
            select(User).where(User.role == "Pharma IT Advisor")
        ).scalars().first()
        if not architect:
            architect = s.execute(select(User)).scalars().first()

        demo_path = REPO_ROOT / "demo-lims"
        project_id = None
        created_project = False
        if demo_path.exists():
            existing = s.execute(
                select(Project).where(Project.name == "AcmeLIMS")
            ).scalar_one_or_none()
            if existing is None:
                p = Project(
                    name="AcmeLIMS",
                    source_path=str(demo_path),
                    target_cloud="AWS",
                    use_runtime_traces=True,
                    created_by=architect.id if architect else "",
                    status="created",
                )
                s.add(p)
                s.flush()
                project_id = p.id
                created_project = True
            else:
                project_id = existing.id
                # Keep the path correct if the repo moved.
                existing.source_path = str(demo_path)

    if created_users or created_project:
        record("system.seeded", payload={"users": created_users,
                                         "project": project_id,
                                         "created_project": created_project})

    return {
        "users_created": created_users,
        "users_total": len(DEMO_USERS),
        "project_id": project_id,
        "project_created": created_project,
        "demo_path": str(REPO_ROOT / "demo-lims"),
    }


def main() -> int:
    result = seed()
    print("ModernRx seed complete.")
    if result["users_created"]:
        print(f"  users created: {', '.join(result['users_created'])}")
    else:
        print(f"  users already present ({result['users_total']})")
    if result["project_id"]:
        verb = "created" if result["project_created"] else "already present"
        print(f"  AcmeLIMS project {verb}: id={result['project_id']}")
        print(f"  source: {result['demo_path']}")
    else:
        print(f"  demo-lims not found at {result['demo_path']} - "
              f"create a project manually from a repo URL or a zip upload")
    print("\nNext: start the backend and frontend, then open http://localhost:3000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
