## Linked ticket

<!-- e.g. AV-142, or "N/A" -->

## Summary

<!-- What changed and why. Link the ADR if this touches architecture (docs/adr/). -->

## Testing performed

<!-- Commands run and their result. No "trust me" — paste the actual output/summary. -->

- [ ] `pnpm --filter <package> lint` / `uv run ruff check .`
- [ ] `pnpm --filter <package> typecheck` / `uv run mypy src`
- [ ] `pnpm --filter <package> build` (if applicable)
- [ ] `uv run pytest -q` (if applicable)
- [ ] Manually verified in a running app (describe how, or state N/A and why)

## Screenshots

<!-- Required for any UI change. Delete this section if not applicable. -->

## Rollback plan

<!-- Required for infra/schema/config changes. Minimum: "redeploy previous image tag." Delete this section if not applicable. -->

## Checklist

- [ ] No secrets committed (checked `git diff` for anything that looks like a credential)
- [ ] No `workspace_id`-scoping gap introduced on any new query/route/cache key (N/A if this PR predates tenant data)
- [ ] Docs updated in this PR if this changes a public contract, schema, or architecture boundary
