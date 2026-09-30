# Reliable health profile updates

## Acceptance criteria
- Given a service request or refresh fails, its CLI exits nonzero and prints no fabricated health data.
- Given one service fails, the updater preserves its existing README values and marks them unavailable, updates the other service if successful, and exits nonzero.
- Given Strava returns no activities successfully, the profile shows No Activity / 0m.
- Given workout names contain punctuation, backslashes, or newlines, the updater changes only the intended profile line safely.
- The updater fetches Strava once per run. Fitbit steps and sleep use the same UTC date. HTTP requests have bounded timeouts.
- OAuth failures never print raw responses or credentials. Recovery passes secrets through stdin.
- Token artifacts are written only after successful refresh. Each service restores its newest unexpired artifact independently, including from failed profile runs.
- Shared token rotation is serialised without cancelling active runs. Pull requests run offline validation; profile publishing runs only on main.
- Tests, typing, and `pre-commit run -a` pass before commit. CI builds the production container and verifies imports without development packages or live API calls.

## Constraints
Keep the profile README content and line format (remove its dangling paragraph tag) and existing CLI commands. No scraping, live Strava application changes, unrelated refactors, deletion of credentials, or production merge. Keep OAuth consent human-driven. Do not copy local secrets into the worktree.

## Approach
Add regression tests first. Propagate CLI failures, sanitise OAuth diagnostics, and add timeouts. Replace shell interpolation with a Python updater that runs the existing CLIs and preserves individual lines on failure. Adjust Actions to retain independently refreshed token artifacts and report errors after publication. Tighten the recovery helper and document service-specific diagnosis, verification, and developer commands. Add a focused offline CI workflow. Align Python on 3.14; update uv, pre-commit, and Ruff pins, add basic file hygiene hooks, and remove the superseded one-line kaizen note. Prevent runtime uv commands from installing development tools into the production image.
