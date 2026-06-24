import os

from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication as _SimpleJWTAuthentication


def apply_active_workspace(user, tenant_id):
    """
    Resolve and attach the active workspace for this request from a (verified) JWT
    tenant_id claim. The active tenant is ALWAYS derived from an active Membership
    — never trusted from request data. Identity tokens (no tenant_id claim) leave
    the user without an active tenant so tenant-scoped endpoints deny them.
    """
    from .models import Membership

    # Identity-only token: no workspace selected yet.
    if not tenant_id:
        user.tenant_id = None
        user._identity_only = True
        user._active_membership = None
        user._active_role_names = []
        user._active_is_admin = False
        return user

    tenant_id = str(tenant_id)

    # Platform superusers may assume any workspace without a membership row.
    if getattr(user, "is_superuser", False):
        user.tenant_id = tenant_id
        user._identity_only = False
        user._active_membership = None
        user._active_role_names = list(user.roles.values_list("name", flat=True))
        user._active_is_admin = True
        return user

    membership = (
        Membership.objects.filter(user=user, tenant_id=tenant_id, status="active")
        .prefetch_related("roles")
        .first()
    )
    if not membership:
        raise AuthenticationFailed("You are not a member of this workspace.")

    user.tenant_id = tenant_id
    user._identity_only = False
    user._active_membership = membership
    user._active_role_names = list(membership.roles.values_list("name", flat=True))
    user._active_is_admin = membership.is_admin
    # Reflect workspace role onto the request-scoped user for legacy checks.
    user.is_tenant_admin = membership.is_admin
    return user


class WorkspaceJWTAuthentication(_SimpleJWTAuthentication):
    """
    SimpleJWT auth that scopes the request to the workspace named in the token's
    verified `tenant_id` claim, after confirming an active Membership exists.
    Replaces the plain JWTAuthentication so a forged/absent membership cannot
    grant cross-tenant access.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, validated_token = result
        apply_active_workspace(user, validated_token.get("tenant_id"))
        return user, validated_token


class KeycloakJWTAuthentication(BaseAuthentication):
    """
    Optional production OIDC auth for Keycloak.

    It activates only when KEYCLOAK_JWKS_URL and KEYCLOAK_AUDIENCE are set.
    Local demo JWTs continue to work through SimpleJWTAuthentication.
    """

    def authenticate(self, request):
        jwks_url = os.getenv("KEYCLOAK_JWKS_URL", "").strip()
        audience = os.getenv("KEYCLOAK_AUDIENCE", "").strip()
        issuer = os.getenv("KEYCLOAK_ISSUER", "").strip()
        if not jwks_url or not audience:
            return None

        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None

        token = auth.split(" ", 1)[1].strip()
        try:
            import jwt

            signing_key = jwt.PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=issuer or None,
                options={"verify_iss": bool(issuer)},
            )
        except Exception as exc:
            raise AuthenticationFailed(f"Invalid Keycloak token: {exc}")

        email = payload.get("email") or payload.get("preferred_username")
        subject = payload.get("sub")
        tenant_id = payload.get("tenant_id") or payload.get("tenant")
        if not email or not tenant_id:
            raise AuthenticationFailed("Keycloak token is missing email or tenant_id claim")

        User = get_user_model()
        user = User.objects.filter(email=email, tenant_id=tenant_id, is_active=True).first()
        if not user:
            user = User.objects.filter(username=email, tenant_id=tenant_id, is_active=True).first()
        if not user:
            raise AuthenticationFailed("No active tenant user matches this Keycloak identity")

        request.keycloak_claims = payload
        request.keycloak_subject = subject
        return user, token
