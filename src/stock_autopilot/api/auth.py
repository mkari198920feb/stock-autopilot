from __future__ import annotations

from fastapi import HTTPException, Request

from stock_autopilot.universe import load_config

MUTATING_PATHS = {
    "/api/run-now",
    "/api/re-rank",
    "/api/crypto-pulse/refresh",
    "/api/commodities-desk/refresh",
    "/api/india-desk/refresh",
    "/api/global-desk/refresh",
    "/api/market-pulse/refresh",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {"desk:read", "desk:write", "admin:config", "email:preview"},
    "analyst": {"desk:read", "desk:write", "email:preview"},
    "viewer": {"desk:read"},
}


def auth_settings(cfg: dict | None = None) -> dict:
    return (cfg or load_config()).get("auth", {})


def _roles_from_request(request: Request, cfg: dict) -> set[str]:
    header_roles = request.headers.get("X-LUMIQ-Roles", "")
    if header_roles:
        return {r.strip().lower() for r in header_roles.split(",") if r.strip()}
    federated = request.headers.get("X-LUMIQ-Federated-Role", "").strip().lower()
    if federated:
        return {federated}
    default_role = (cfg.get("rbac") or {}).get("default_role", "viewer")
    return {default_role}


def permissions_for_roles(roles: set[str], cfg: dict) -> set[str]:
    rbac = cfg.get("rbac") or {}
    custom = rbac.get("roles") or {}
    perms: set[str] = set()
    for role in roles:
        if role in custom:
            perms.update(custom[role].get("permissions") or [])
        else:
            perms.update(ROLE_PERMISSIONS.get(role, set()))
    return perms


def require_permission(request: Request, permission: str) -> None:
    cfg = auth_settings()
    if not cfg.get("enabled", False):
        return

    user = request.headers.get("X-LUMIQ-User") or request.headers.get("X-Forwarded-User")
    auth_header = request.headers.get("Authorization", "")
    if not user and not auth_header:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Configure IAM federation and pass X-LUMIQ-User or Authorization.",
        )

    roles = _roles_from_request(request, cfg)
    perms = permissions_for_roles(roles, cfg)
    if permission not in perms:
        raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")


def enforce_request_auth(request: Request) -> None:
    if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
        return
    path = request.url.path.rstrip("/") or "/"
    if path == "/api/investor-profile" and request.method == "PUT":
        require_permission(request, "desk:write")
        return
    if path in MUTATING_PATHS:
        require_permission(request, "desk:write")
