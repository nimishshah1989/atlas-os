"""Every GitHub Actions workflow file is valid YAML with the shape Actions requires.

A workflow that does not parse does not fail loudly. GitHub records a run with **zero jobs**,
a `startup_failure` conclusion and NO LOG — there is nothing to read, because nothing started.
It looks identical to a deploy that ran and failed, and it happened on 2026-09-08 to
`deploy-global.yml`: a multi-line `python3 -c` inside the `script: |` block was indented at
column 0, and a line indented BELOW a YAML block scalar's own indent ENDS the scalar. YAML then
tried to read Python as a mapping. The merge that was supposed to put the board live therefore
deployed nothing at all, and looked from the outside exactly like a merge that had.

`ci.yml` and `deploy-frontend.yml` are the live India paths and are covered here too: the same
mistake in either would silently stop CI or stop India deploying.

This is not a lint. It asserts the one property whose absence is invisible.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"
WORKFLOWS = sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))


def test_there_are_workflows_to_check() -> None:
    """A glob that silently matches nothing would make every test below vacuously pass."""
    assert WORKFLOWS, f"no workflow files under {WORKFLOW_DIR}"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_is_valid_yaml(path: Path) -> None:
    """The failure this file exists for: unparseable YAML, which Actions reports as no run."""
    try:
        yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:  # pragma: no cover - the message IS the value here
        pytest.fail(f"{path.name} is not valid YAML — Actions would record 0 jobs:\n{exc}")


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_has_a_trigger_and_at_least_one_job(path: Path) -> None:
    """Parsing is not enough: a workflow with no `jobs` is silently inert in the same way.

    `on` is the YAML 1.1 boolean `True` once loaded — PyYAML resolves the bare word before it
    is ever a key — so both spellings are accepted rather than asserting the one that happens
    to appear in these files today.
    """
    doc = yaml.safe_load(path.read_text())
    assert isinstance(doc, dict), f"{path.name} did not load as a mapping"
    assert doc.get("on") or doc.get(True), f"{path.name} has no trigger — it can never run"
    jobs = doc.get("jobs")
    assert isinstance(jobs, dict) and jobs, f"{path.name} defines no jobs"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_job_can_actually_do_something(path: Path) -> None:
    """A job with neither steps nor a reusable-workflow `uses` is a job that runs nothing."""
    jobs = yaml.safe_load(path.read_text())["jobs"]
    for name, job in jobs.items():
        assert job.get("steps") or job.get("uses"), (
            f"{path.name}: job '{name}' has no steps and calls no reusable workflow"
        )
