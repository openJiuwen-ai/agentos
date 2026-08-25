"""Resource-level permission service. Zero IO — all data in memory."""


# ── Resource & Action constants ─────────────────────────────────────────


class Resource:
    DASHBOARD = "dashboard"
    INFERENCE_MODELS = "inference.models"
    INFERENCE_API_KEYS = "inference.api_keys"
    INFERENCE_USAGE = "inference.usage"
    INFERENCE_MONITOR = "inference.monitor"
    AGENT_GLOBAL = "agent.global"
    LOGS = "logs"
    APPS = "apps"
    ALERTS = "alerts"
    HARDWARE = "hardware"
    NODE_SERVICE = "node_service"
    SETTINGS = "settings"


class Action:
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    MANAGE = "manage"


# ── v1 hardcoded role-permission matrix ────────────────────────────────
#  Later: migrate to permissions.yaml or panel_permissions table.

_ROLE_PERMISSIONS: dict[str, dict[str, set[str]]] = {
    "admin": {
        "*": {"*"},
    },
    "user": {
        Resource.DASHBOARD: {Action.READ},
        Resource.INFERENCE_API_KEYS: {Action.READ, Action.WRITE},
        Resource.INFERENCE_USAGE: {Action.READ},
        Resource.APPS: {Action.READ},
        Resource.ALERTS: {Action.READ},
    },
}

_ALL_RESOURCES = [
    Resource.DASHBOARD,
    Resource.INFERENCE_MODELS,
    Resource.INFERENCE_API_KEYS,
    Resource.INFERENCE_USAGE,
    Resource.INFERENCE_MONITOR,
    Resource.AGENT_GLOBAL,
    Resource.LOGS,
    Resource.APPS,
    Resource.ALERTS,
    Resource.HARDWARE,
    Resource.NODE_SERVICE,
    Resource.SETTINGS,
]

_ALL_ACTIONS = [Action.READ, Action.WRITE, Action.DELETE, Action.MANAGE]


class PermissionService:
    """Resource-level permission check.  Zero IO — dict + set lookups."""

    @staticmethod
    def check(role: str, resource: str, action: str) -> bool:
        """Return ``True`` if *role* may perform *action* on *resource*.

        Match order:
        1. Exact resource match: role → resource → action in allowed set
        2. Resource wildcard: role → ``"*"`` → action in allowed set
        3. Action wildcard: role → resource → ``"*"`` in allowed set
        4. Full wildcard: role → ``"*"`` → ``"*"`` in allowed set
        """
        allowed = _ROLE_PERMISSIONS.get(role, {})
        if not allowed:
            return False
        for res_key in (resource, "*"):
            actions = allowed.get(res_key)
            if actions is None:
                continue
            if "*" in actions or action in actions:
                return True
        return False

    @staticmethod
    def get_permissions(role: str) -> dict[str, list[str]]:
        """Expand wildcards and return the full permission matrix for *role*.

        Used by ``GET /auth/permissions``.
        """
        allowed = _ROLE_PERMISSIONS.get(role, {})
        if "*" in allowed:
            return {r: list(_ALL_ACTIONS) for r in _ALL_RESOURCES}

        result: dict[str, list[str]] = {}
        for resource in _ALL_RESOURCES:
            perms: set[str] = set()
            for res_key in (resource, "*"):
                actions = allowed.get(res_key, set())
                if "*" in actions:
                    perms.update(_ALL_ACTIONS)
                else:
                    perms.update(actions)
            result[resource] = sorted(perms)
        return result
