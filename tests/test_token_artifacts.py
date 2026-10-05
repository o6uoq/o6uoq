"""Exercise the workflow's JavaScript against reordered artifact pages."""

import json
import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).parents[1] / ".github/workflows/main.yaml"


def artifact(identifier, created, *, run=100, branch="main", expired=False, name="fitbit-tokens"):
    return {
        "id": identifier,
        "name": name,
        "created_at": created,
        "expired": expired,
        "workflow_run": {"id": run, "head_branch": branch},
    }


def select(pages):
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["build-and-run"]["steps"]
    step = next(step for step in steps if step.get("id") == "tokens")
    harness = r"""
const fs = require('node:fs');
const {script, pages} = JSON.parse(fs.readFileSync(0, 'utf8'));
const outputs = {};
const github = {
    rest: {actions: {listArtifactsForRepo: {}}},
    paginate: {iterator: async function* () {
        for (const artifacts of pages) yield {data: artifacts};
    }}
};
const context = {repo: {owner: 'test', repo: 'test'}};
const core = {setOutput: (key, value) => { outputs[key] = value; }};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('github', 'context', 'core', script)(github, context, core)
    .then(() => process.stdout.write(JSON.stringify(outputs)))
    .catch(error => { process.stderr.write(error.message); process.exitCode = 1; });
"""
    result = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps({"script": step["with"]["script"], "pages": pages}),
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("separate_pages", [False, True])
def test_newest_rotation_wins_even_when_older_artifact_has_higher_id(separate_pages):
    # Real rerun ordering: the older artifact was listed first and had a higher ID.
    older = artifact(11355535164, "2026-10-05T15:26:03Z")
    newer = artifact(11354608822, "2026-10-05T15:28:53Z")
    pages = [[older], [newer]] if separate_pages else [[older, newer]]
    assert select(pages) == {"fitbit": 100, "fitbit_artifact": 11354608822}


def test_ineligible_artifacts_are_excluded_and_no_match_uses_secrets():
    invalid = [
        artifact(5, "2026-10-05T16:00:00Z", branch="fix/example"),
        artifact(6, "2026-10-05T16:00:00Z", expired=True),
        artifact(7, "2026-10-05T16:00:00Z", name="other"),
    ]
    assert select([invalid]) == {}
    valid = artifact(4, "2026-10-05T15:00:00Z", run=99)
    assert select([invalid, [valid]]) == {"fitbit": 99, "fitbit_artifact": 4}


def test_download_uses_selected_id_and_recovery_can_bypass_artifacts():
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["build-and-run"]["steps"]
    selection = next(step for step in steps if step.get("id") == "tokens")
    download = next(step for step in steps if step.get("id") == "download_fitbit")
    assert selection["if"] == "inputs.skip_artifact != true"
    assert download["with"]["artifact-ids"] == "${{ steps.tokens.outputs.fitbit_artifact }}"
    assert download["with"]["run-id"] == "${{ steps.tokens.outputs.fitbit }}"
    assert "name" not in download["with"]
