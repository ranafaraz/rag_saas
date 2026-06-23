from rest_framework.permissions import SAFE_METHODS, BasePermission


def user_role_names(user) -> set[str]:
    if not getattr(user, "is_authenticated", False):
        return set()
    try:
        return {name.lower() for name in user.roles.values_list("name", flat=True)}
    except Exception:
        return set()


def can_manage_tenant(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "is_tenant_admin", False):
        return True
    return "admin" in user_role_names(user)


def can_manage_content(user) -> bool:
    if can_manage_tenant(user):
        return True
    return bool({"faculty", "staff"} & user_role_names(user))


def object_tenant_id(obj):
    if hasattr(obj, "tenant_id"):
        return obj.tenant_id
    tenant = getattr(obj, "tenant", None)
    return getattr(tenant, "id", None)


class TenantScopedPermission(BasePermission):
    """
    Enforces tenant isolation for model viewsets.

    Read operations are available to authenticated users in their tenant.
    Write operations require tenant admin by default. Viewsets may set
    allow_content_manager_writes=True to also allow Faculty/Staff content ops.
    """

    def has_permission(self, request, view):
        if not getattr(request.user, "is_authenticated", False):
            return False
        if request.method in SAFE_METHODS:
            return True
        if getattr(view, "allow_content_manager_writes", False):
            return can_manage_content(request.user)
        return can_manage_tenant(request.user)

    def has_object_permission(self, request, view, obj):
        if getattr(request.user, "is_superuser", False):
            return True

        tenant_id = object_tenant_id(obj)
        if tenant_id and tenant_id != getattr(request.user, "tenant_id", None):
            return False

        if request.method in SAFE_METHODS:
            return True
        if getattr(view, "allow_content_manager_writes", False):
            return can_manage_content(request.user)
        return can_manage_tenant(request.user)
