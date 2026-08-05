"""Validates the `plans` table's `jsonb` columns on the way out.

The database stores flexibility; this module enforces shape (CLAUDE.md
§8). It runs on **read**, not only on write, which is the point: a plan
row is edited operationally — by a migration, an admin action, or a
support engineer fixing a limit at 2am — so the guarantee that has to
hold is "whatever is in the table parses into something the enforcement
code can use", not "whatever we wrote last time was fine".

The failure mode this exists to prevent is specific. `jsonb` with a
typo'd key (`"agent"` for `"agents"`) deserializes perfectly happily
into a dict, and `plan.resource_limit(AGENTS)` then returns `None`,
which this system reads as *unlimited*. A quiet typo would hand every
workspace unlimited agents. So an unknown key is a hard error, not a
warning.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError, field_validator

from agentverse_api.billing_service.domain.plan import (
    Capability,
    MeteredDimension,
    OverageRate,
    Plan,
    PlanTier,
    ResourceLimit,
)


class MalformedPlanError(Exception):
    """A `plans` row's JSON columns do not parse. Maps to HTTP 500 —
    this is an operator error in the catalog, never a caller's fault, and
    must page rather than degrade into permissive defaults.
    """

    def __init__(self, slug: str, detail: str) -> None:
        self.slug = slug
        self.detail = detail
        super().__init__(f"Plan {slug!r} has a malformed configuration: {detail}")


class OverageRateConfig(BaseModel):
    """Stored shape of one overage rate. `model_config` forbids extras so
    a renamed field is caught here rather than silently dropped.
    """

    model_config = {"extra": "forbid"}

    billing_increment: int = Field(gt=0)
    price_cents_per_increment: int = Field(ge=0)


def _parse_limits(slug: str, raw: object) -> dict[ResourceLimit, int | None]:
    if not isinstance(raw, dict):
        raise MalformedPlanError(
            slug, f"resource_limits must be an object, got {type(raw).__name__}"
        )
    parsed: dict[ResourceLimit, int | None] = {}
    for key, value in raw.items():
        try:
            dimension = ResourceLimit(key)
        except ValueError as exc:
            raise MalformedPlanError(slug, f"unknown resource limit {key!r}") from exc
        parsed[dimension] = _parse_limit_value(slug, key, value)
    return parsed


def _parse_allowances(slug: str, raw: object) -> dict[MeteredDimension, int | None]:
    if not isinstance(raw, dict):
        raise MalformedPlanError(
            slug, f"metered_allowances must be an object, got {type(raw).__name__}"
        )
    parsed: dict[MeteredDimension, int | None] = {}
    for key, value in raw.items():
        try:
            dimension = MeteredDimension(key)
        except ValueError as exc:
            raise MalformedPlanError(slug, f"unknown metered dimension {key!r}") from exc
        parsed[dimension] = _parse_limit_value(slug, key, value)
    return parsed


def _parse_limit_value(slug: str, key: str, value: object) -> int | None:
    if value is None:
        return None
    # `bool` is an `int` subclass in Python, so an accidental `true` in
    # the JSON would otherwise pass as the limit 1 — a plan capped at one
    # agent, from a value that was never meant to be a number at all.
    if isinstance(value, bool) or not isinstance(value, int):
        raise MalformedPlanError(slug, f"limit {key!r} must be an integer or null, got {value!r}")
    if value < 0:
        raise MalformedPlanError(slug, f"limit {key!r} must not be negative, got {value}")
    return value


def _parse_capabilities(slug: str, raw: object) -> frozenset[Capability]:
    if not isinstance(raw, list):
        raise MalformedPlanError(slug, f"capabilities must be an array, got {type(raw).__name__}")
    parsed: set[Capability] = set()
    for item in raw:
        try:
            parsed.add(Capability(item))
        except ValueError as exc:
            raise MalformedPlanError(slug, f"unknown capability {item!r}") from exc
    return frozenset(parsed)


def _parse_overage_rates(slug: str, raw: object) -> dict[MeteredDimension, OverageRate]:
    if not isinstance(raw, dict):
        raise MalformedPlanError(slug, f"overage_rates must be an object, got {type(raw).__name__}")
    parsed: dict[MeteredDimension, OverageRate] = {}
    for key, value in raw.items():
        try:
            dimension = MeteredDimension(key)
        except ValueError as exc:
            raise MalformedPlanError(slug, f"unknown metered dimension {key!r}") from exc
        try:
            config = OverageRateConfig.model_validate(value)
        except ValidationError as exc:
            raise MalformedPlanError(slug, f"overage rate {key!r}: {exc.errors()}") from exc
        parsed[dimension] = OverageRate(
            dimension=dimension,
            billing_increment=config.billing_increment,
            price_cents_per_increment=config.price_cents_per_increment,
        )
    return parsed


class PlanRowFields(BaseModel):
    """The scalar columns, validated together so a bad row cannot half-load.

    Kept separate from the JSON parsing above because these constraints
    are also enforced by the table's CHECKs — this is the second line,
    covering the window where a row was inserted by something that
    bypassed them (a restore from an older dump, most plausibly).
    """

    model_config = {"extra": "forbid"}

    display_name: str = Field(min_length=1, max_length=64)
    description: str = Field(max_length=512)
    monthly_price_cents: int | None = Field(default=None, ge=0)
    annual_price_cents: int | None = Field(default=None, ge=0)
    currency: str = Field(min_length=3, max_length=3)
    trial_days: int = Field(ge=0, le=365)
    sort_order: int

    @field_validator("currency")
    @classmethod
    def _lowercase_currency(cls, value: str) -> str:
        # Stripe's API is lowercase-only for currency codes. Normalising
        # on read means a row inserted as "USD" does not produce a
        # checkout session Stripe rejects at the worst possible moment.
        return value.lower()


def to_domain(
    *,
    plan_id: str,
    slug: PlanTier,
    display_name: str,
    description: str,
    monthly_price_cents: int | None,
    annual_price_cents: int | None,
    currency: str,
    trial_days: int,
    is_public: bool,
    is_active: bool,
    sort_order: int,
    resource_limits: object,
    metered_allowances: object,
    capabilities: object,
    overage_rates: object,
) -> Plan:
    """Build the domain `Plan` from a stored row, or raise."""
    try:
        fields = PlanRowFields(
            display_name=display_name,
            description=description,
            monthly_price_cents=monthly_price_cents,
            annual_price_cents=annual_price_cents,
            currency=currency,
            trial_days=trial_days,
            sort_order=sort_order,
        )
    except ValidationError as exc:
        raise MalformedPlanError(slug.value, str(exc.errors())) from exc

    return Plan(
        id=plan_id,
        slug=slug,
        display_name=fields.display_name,
        description=fields.description,
        monthly_price_cents=fields.monthly_price_cents,
        annual_price_cents=fields.annual_price_cents,
        currency=fields.currency,
        trial_days=fields.trial_days,
        is_public=is_public,
        is_active=is_active,
        sort_order=fields.sort_order,
        resource_limits=_parse_limits(slug.value, resource_limits),
        metered_allowances=_parse_allowances(slug.value, metered_allowances),
        capabilities=_parse_capabilities(slug.value, capabilities),
        overage_rates=_parse_overage_rates(slug.value, overage_rates),
    )
