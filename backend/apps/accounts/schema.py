"""OpenAPI extensions.

Teaches drf-spectacular how to describe ``ClerkJWTAuthentication`` so the generated
schema (and therefore the frontend client and Swagger UI) advertises bearer auth.
"""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ClerkJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.ClerkJWTAuthentication"
    name = "ClerkSessionToken"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Clerk session token. Obtain it on the frontend with `getToken()` and "
                "send it as `Authorization: Bearer <token>`."
            ),
        }
