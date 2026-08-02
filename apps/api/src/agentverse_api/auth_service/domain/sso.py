"""SSO protocol/preset vocabulary — plain StrEnums, mirroring
`api_key_scope.py`'s minimal standalone pattern.

Both are stored as TEXT (see migration `f4b8d1e6c037`), so adding a value
here never needs a migration — which is exactly why 8b can add SAML and
8c can add vendor presets without touching the schema.
"""

from __future__ import annotations

from enum import StrEnum


class SsoProtocol(StrEnum):
    OIDC = "oidc"
    SAML = "saml"


class SsoPreset(StrEnum):
    """Which vendor's setup instructions the admin followed.

    UI convenience only (8c): presets pre-fill the *generic* OIDC/SAML
    fields in the form. There is deliberately no per-vendor server code —
    a preset never changes how the protocol is executed, only what the
    form starts with.
    """

    GENERIC = "generic"
    GOOGLE_WORKSPACE = "google_workspace"
    AZURE_AD = "azure_ad"
    OKTA = "okta"
    AUTH0 = "auth0"
