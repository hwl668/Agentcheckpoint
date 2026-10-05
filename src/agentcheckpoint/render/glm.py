"""Resume renderer tuned for GLM."""

from __future__ import annotations


def render(manifest: dict, report: dict | None = None) -> str:
    from agentcheckpoint.render.markdown import handoff_document

    return handoff_document(manifest, report=report, target="glm")
