"""MCP prompts: the six built-in pack profiles (#184).

`app.prompt.profiles` defines six reviewed, versioned profiles (plan / build /
review / debug / git_safety_review / documentation_update) — agent
instructions, expected-output shape, and verification requirements. Today
they are reachable only through the web UI's Context Pack generator
(`context_pack_service.generate_preview`), which an MCP client cannot call —
that generator is project- and workspace-scoped, does document selection,
budget trimming and secret scanning over arbitrary docs, and its output is
designed to be copy-pasted into an *external* tool that has no other way to
see the project.

An MCP client is different: it is already live in this project, with its own
tools (`get_active_work`, `list_tasks`, `get_doc_excerpt`, …) to fetch whatever
project content it actually needs. Reimplementing the whole context-pack
pipeline as an MCP prompt would duplicate that machinery for no reason a
connected client has. So this module exposes only the profile *template* —
agent instructions, expected output, verification — not a project snapshot.
This is the scoped decision the profiles-as-prompts item in #184 asked for: it
is genuinely smaller than "port the Context Pack generator into MCP", not the
same feature restated.

No project content ever appears here, so there is nothing to redact or
boundary-wrap — unlike every read tool and the doc resource, a profile prompt
carries zero untrusted data, only reviewed static template text.

This module stays SDK-agnostic; only server.py/http_transport.py talk to the
SDK directly.
"""
from __future__ import annotations

from app.prompt import profiles


def prompt_names() -> tuple[str, ...]:
    return profiles.PROFILE_ORDER


def prompt_description(key: str) -> str:
    return profiles.get_profile(key).description


def render_prompt(key: str) -> str | None:
    """Static agent-instructions/output/verification text for one profile, or
    None for an unrecognised name."""
    if not profiles.is_valid_profile(key):
        return None
    profile = profiles.get_profile(key)
    lines: list[str] = [
        f"You are a {profile.label.lower()} assistant. {profile.description}",
        "",
        *profile.agent_instructions,
        "",
        "Expected output:",
        *profile.output_format,
        "",
        "Verification requirements:",
        *profile.verification,
    ]
    if profile.include_git_checklist:
        lines += [
            "",
            "Use READ-ONLY Git only; never mutate from this prompt (no commit,"
            " push, branch, reset, or force-update).",
        ]
    return "\n".join(lines) + "\n"
