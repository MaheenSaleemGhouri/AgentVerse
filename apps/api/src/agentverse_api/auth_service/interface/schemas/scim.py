"""SCIM 2.0 wire schemas (RFC 7643/7644).

These are the one place in this codebase where field names are
camelCase and a `schemas` array is echoed back verbatim — that is the
SCIM standard, not a style lapse, and identity providers validate
against it strictly.

Only the subset AgentVerse actually implements is modelled. Attributes
an IdP may send but this service does not store (`entitlements`,
`x509Certificates`, `addresses`, …) are accepted and ignored rather than
rejected, per RFC 7644 §3.3 — an unknown attribute must not fail a
provisioning request.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
LIST_RESPONSE_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
PATCH_OP_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:PatchOp"

#: The one filter form this service supports. Okta, Entra ID and
#: OneLogin all send exactly this shape for their pre-create dedup
#: lookup; anything richer is answered with a SCIM error rather than
#: silently ignored, because a filter treated as "match everything"
#: would let an IdP believe a user already exists when they do not.
_USERNAME_FILTER = re.compile(r'^\s*userName\s+eq\s+"(?P<value>[^"]*)"\s*$', re.IGNORECASE)


class ScimFilterUnsupportedError(ValueError):
    """The client sent a filter this service cannot honour."""


def parse_username_filter(filter_expression: str | None) -> str | None:
    """Returns the `userName` a filter selects, or `None` for no filter."""
    if filter_expression is None or not filter_expression.strip():
        return None
    match = _USERNAME_FILTER.match(filter_expression)
    if match is None:
        raise ScimFilterUnsupportedError(
            "Only filters of the form 'userName eq \"value\"' are supported."
        )
    return match.group("value")


class ScimName(BaseModel):
    formatted: str | None = None
    givenName: str | None = None
    familyName: str | None = None


#: Same shape `schemas/invitation.py` already validates against — reused
#: rather than pulling in `pydantic[email]` for one field.
_EMAIL_PATTERN = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"


class ScimEmail(BaseModel):
    value: str = Field(min_length=3, max_length=320, pattern=_EMAIL_PATTERN)
    primary: bool = True
    type: str | None = None


class ScimMeta(BaseModel):
    resourceType: str
    created: str
    lastModified: str


class ScimUserResource(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [USER_SCHEMA])
    id: str
    userName: str
    displayName: str
    name: ScimName
    emails: list[ScimEmail]
    active: bool
    meta: ScimMeta


class ScimGroupResource(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [GROUP_SCHEMA])
    id: str
    displayName: str
    meta: ScimMeta


class ScimListResponse(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [LIST_RESPONSE_SCHEMA])
    totalResults: int
    startIndex: int
    itemsPerPage: int
    Resources: list[Any]


class ScimError(BaseModel):
    schemas: list[str] = Field(default_factory=lambda: [ERROR_SCHEMA])
    status: str
    detail: str
    scimType: str | None = None


class ScimCreateUserRequest(BaseModel):
    # `extra="ignore"` is the RFC 7644 §3.3 behaviour: attributes this
    # service does not model must not fail the request.
    model_config = ConfigDict(extra="ignore")

    userName: str = Field(min_length=3, max_length=320)
    displayName: str | None = Field(default=None, max_length=200)
    name: ScimName | None = None
    emails: list[ScimEmail] = Field(default_factory=list)
    active: bool = True

    def resolved_email(self) -> str:
        """SCIM clients disagree about whether `userName` is the email.

        Okta sends the email in both; Entra ID sends a UPN in `userName`
        and the mailbox in `emails`. The primary email wins when present
        because that is the address SSO will actually assert.
        """
        primary = next((e for e in self.emails if e.primary), None)
        chosen = primary or (self.emails[0] if self.emails else None)
        return chosen.value if chosen is not None else self.userName

    def resolved_display_name(self) -> str:
        if self.displayName:
            return self.displayName
        if self.name is not None:
            if self.name.formatted:
                return self.name.formatted
            parts = [self.name.givenName, self.name.familyName]
            joined = " ".join(p for p in parts if p)
            if joined:
                return joined
        return self.resolved_email()


class ScimPatchOperation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    op: str
    path: str | None = None
    value: Any = None


class ScimPatchRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schemas: list[str] = Field(default_factory=lambda: [PATCH_OP_SCHEMA])
    Operations: list[ScimPatchOperation] = Field(default_factory=list)

    def resolved_active(self) -> bool | None:
        """The `active` value this patch sets, or `None` if it sets none.

        Handles both shapes IdPs send: `{"path": "active", "value":
        false}` and the pathless `{"value": {"active": false}}`.
        """
        result: bool | None = None
        for operation in self.Operations:
            if operation.op.lower() not in {"replace", "add"}:
                continue
            if operation.path and operation.path.lower() == "active":
                result = _coerce_bool(operation.value)
            elif (
                operation.path is None
                and isinstance(operation.value, dict)
                and "active" in operation.value
            ):
                result = _coerce_bool(operation.value["active"])
        return result

    def resolved_display_name(self) -> str | None:
        for operation in self.Operations:
            if operation.op.lower() not in {"replace", "add"}:
                continue
            if operation.path and operation.path.lower() == "displayname":
                return str(operation.value)
            if (
                operation.path is None
                and isinstance(operation.value, dict)
                and "displayName" in operation.value
            ):
                return str(operation.value["displayName"])
        return None


def _coerce_bool(value: Any) -> bool | None:
    """SCIM clients send `active` as a JSON bool *or* as the strings
    "True"/"false" — Entra ID does the latter.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
    return None


class IssueScimTokenRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ScimTokenResponse(BaseModel):
    id: str
    organization_id: str
    name: str
    token_prefix: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class IssuedScimTokenResponse(ScimTokenResponse):
    #: Returned exactly once, at issuance, and never retrievable again.
    token: str


ScimResourceType = Literal["User", "Group"]
