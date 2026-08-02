"""SCIM wire-format parsing — pure functions, no I/O.

These carry real risk despite looking trivial: every real identity
provider sends a slightly different shape, and the difference between
"userName is the email" and "the primary emails entry is" decides which
account a person is provisioned into.
"""

from __future__ import annotations

import pytest

from agentverse_api.auth_service.interface.schemas.scim import (
    ScimCreateUserRequest,
    ScimFilterUnsupportedError,
    ScimPatchRequest,
    parse_username_filter,
)


class TestUsernameFilter:
    def test_extracts_the_value_an_idp_is_deduping_on(self) -> None:
        assert parse_username_filter('userName eq "ada@example.com"') == "ada@example.com"

    def test_is_case_insensitive_on_the_operator_and_attribute(self) -> None:
        assert parse_username_filter('USERNAME EQ "ada@example.com"') == "ada@example.com"

    @pytest.mark.parametrize("empty", [None, "", "   "])
    def test_no_filter_means_no_filter(self, empty: str | None) -> None:
        assert parse_username_filter(empty) is None

    @pytest.mark.parametrize(
        "unsupported",
        [
            'emails.value eq "ada@example.com"',
            'userName sw "ada"',
            'userName eq "a" and active eq true',
            "active eq true",
        ],
    )
    def test_an_unsupported_filter_is_refused_not_silently_widened(
        self, unsupported: str
    ) -> None:
        # Treating an unparsed filter as "match everything" would tell an
        # IdP a user already exists when they do not — the failure mode
        # this test exists to prevent.
        with pytest.raises(ScimFilterUnsupportedError):
            parse_username_filter(unsupported)


class TestCreateUserResolution:
    def test_okta_shape_email_in_both_fields(self) -> None:
        body = ScimCreateUserRequest.model_validate(
            {
                "userName": "ada@example.com",
                "emails": [{"value": "ada@example.com", "primary": True}],
                "displayName": "Ada Lovelace",
            }
        )
        assert body.resolved_email() == "ada@example.com"
        assert body.resolved_display_name() == "Ada Lovelace"

    def test_entra_shape_upn_in_username_mailbox_in_emails(self) -> None:
        body = ScimCreateUserRequest.model_validate(
            {
                "userName": "ada@corp.onmicrosoft.com",
                "emails": [{"value": "ada@example.com", "primary": True}],
            }
        )
        # The asserted mailbox wins — that is the address SSO will
        # present at sign-in.
        assert body.resolved_email() == "ada@example.com"

    def test_falls_back_to_username_when_no_emails_are_sent(self) -> None:
        body = ScimCreateUserRequest.model_validate({"userName": "ada@example.com"})
        assert body.resolved_email() == "ada@example.com"
        assert body.resolved_display_name() == "ada@example.com"

    def test_builds_a_display_name_from_given_and_family_name(self) -> None:
        body = ScimCreateUserRequest.model_validate(
            {
                "userName": "ada@example.com",
                "name": {"givenName": "Ada", "familyName": "Lovelace"},
            }
        )
        assert body.resolved_display_name() == "Ada Lovelace"

    def test_unknown_attributes_are_ignored_not_rejected(self) -> None:
        """RFC 7644 §3.3 — an attribute this service does not model must
        not fail the whole provisioning request.
        """
        body = ScimCreateUserRequest.model_validate(
            {
                "userName": "ada@example.com",
                "entitlements": [{"value": "whatever"}],
                "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User": {
                    "department": "Analytical Engines"
                },
            }
        )
        assert body.resolved_email() == "ada@example.com"


class TestPatchResolution:
    def test_pathed_deactivate(self) -> None:
        patch = ScimPatchRequest.model_validate(
            {"Operations": [{"op": "replace", "path": "active", "value": False}]}
        )
        assert patch.resolved_active() is False

    def test_pathless_deactivate(self) -> None:
        patch = ScimPatchRequest.model_validate(
            {"Operations": [{"op": "replace", "value": {"active": False}}]}
        )
        assert patch.resolved_active() is False

    def test_string_booleans_are_coerced(self) -> None:
        """Entra ID sends `"False"` as a string, not a JSON bool."""
        patch = ScimPatchRequest.model_validate(
            {"Operations": [{"op": "replace", "path": "active", "value": "False"}]}
        )
        assert patch.resolved_active() is False

    def test_a_patch_touching_nothing_relevant_resolves_to_none(self) -> None:
        patch = ScimPatchRequest.model_validate(
            {"Operations": [{"op": "replace", "path": "title", "value": "Countess"}]}
        )
        assert patch.resolved_active() is None
        assert patch.resolved_display_name() is None

    def test_display_name_is_extracted_from_either_shape(self) -> None:
        pathed = ScimPatchRequest.model_validate(
            {"Operations": [{"op": "replace", "path": "displayName", "value": "Ada L."}]}
        )
        pathless = ScimPatchRequest.model_validate(
            {"Operations": [{"op": "replace", "value": {"displayName": "Ada L."}}]}
        )
        assert pathed.resolved_display_name() == "Ada L."
        assert pathless.resolved_display_name() == "Ada L."
