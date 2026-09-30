# Repository guidance

The root README is the public GitHub profile. Keep setup and recovery instructions in `app/README.md`, and design decisions in `docs/specs/`.

- Work in a fresh managed worktree and task branch. Do not edit the main checkout.
- Write acceptance criteria before multi-step changes. Keep changes focused; do not merge without approval.
- Use `uv` and commit `uv.lock`. Keep uv pins in Docker and CI aligned; keep Ruff in the lockfile and hook aligned. Python minimum, runtime, and Ruff target are 3.14.
- Before commit: `uv run pytest`, `uv run pyright`, and `uv run pre-commit run -a`. No bypass.
- Tests must mock HTTP, OAuth, and GitHub writes. Do not use live tokens for tests.
- Never print API bodies, tokens, client secrets, or authorisation codes. Send GitHub secrets through stdin.
- API failure must exit nonzero. Never convert unavailable data into zero steps or an empty workout.
- Preserve each unavailable service's previous profile values and label them unavailable. Fetch Strava once per update.
- Token artifacts contain credentials. Write them only after successful refresh; do not commit or share them.
- Keep profile publishing on main, offline checks on PRs, and token rotation serialised without cancelling active runs.
