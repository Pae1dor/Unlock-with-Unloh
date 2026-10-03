"""Who may do what. The only place that knows role names.

Routes and templates ask about an *action* ("news.manage"), never about a role:
    user: User = Depends(require("news.manage"))       # in a route
    {% if can(user, "news.manage") %} ... {% endif %}   # in a template (Jinja global)

Hiding a button is cosmetic; every admin route and API checks again here on the server.
"""
from fastapi import Depends, HTTPException, Request

from app.deps import LoginRequired, get_current_user
from app.models import User

ROLE_LABELS = {
    "admin": "ผู้ดูแลระบบ",
    # "mosque_admin": "ผู้ดูแลมัสยิด",   # future: scoped to user_roles.mosque_id
}

# Actions each role may perform; "*" = everything.
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"*"},
}

ACTIONS = {
    "admin.panel",            # open /admin
    "role.manage",            # grant / revoke admins
    "news.manage",            # create news
    "post.delete",            # delete forum posts / comments
    "donation.manage",        # donation campaigns
    "mosque_request.review",  # approve / reject mosque requests
    "mosque.manage",          # edit / hide mosques added through the app (app_mosques)
    "report.review",          # handle problem reports
}


def can(user: User | None, action: str, mosque_id: str | None = None) -> bool:
    """True if `user` may perform `action` (optionally on one mosque)."""
    if user is None:
        return False
    assert action in ACTIONS, f"unknown action {action!r}"
    for grant in user.roles:
        allowed = ROLE_PERMISSIONS.get(grant.role, set())
        if "*" not in allowed and action not in allowed:
            continue
        # a system-wide grant covers every mosque; a scoped one only its own
        if grant.mosque_id is None or (mosque_id is not None and grant.mosque_id == mosque_id):
            return True
    return False


def require(action: str):
    """FastAPI dependency: the current user, if allowed to perform `action`.

    Anonymous visitors are sent to /login; logged-in users without the permission get a
    plain 404, so admin pages stay invisible rather than announced by a 403.
    """

    def dependency(request: Request, user: User | None = Depends(get_current_user)) -> User:
        if user is None:
            raise LoginRequired(next_url=str(request.url.path))
        if not can(user, action):
            raise HTTPException(status_code=404)
        return user

    return dependency
