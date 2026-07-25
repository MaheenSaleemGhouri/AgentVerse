from agentverse_api.auth_service.domain.slug import candidate_slugs, slugify


def test_slugify_lowercases_and_hyphenates() -> None:
    assert slugify("Acme Inc.") == "acme-inc"


def test_slugify_strips_leading_trailing_punctuation() -> None:
    assert slugify("  --Weird Name!!--  ") == "weird-name"


def test_slugify_empty_name_falls_back() -> None:
    assert slugify("...") == "workspace"


def test_candidate_slugs_starts_with_base_then_numbered() -> None:
    candidates = candidate_slugs("Acme Inc.")
    assert candidates[0] == "acme-inc"
    assert candidates[1] == "acme-inc-2"
    assert candidates[-1] == "acme-inc-10"
    assert len(candidates) == 10
