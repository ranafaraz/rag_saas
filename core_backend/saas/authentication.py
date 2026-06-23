import os

from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


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
