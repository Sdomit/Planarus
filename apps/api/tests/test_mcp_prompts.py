"""#184: the six built-in pack profiles exposed as MCP prompts.

Unit tests against app.mcp.prompts directly, plus one real STDIO subprocess
round trip proving list_prompts/get_prompt actually work through the
installed mcp SDK's own dispatch.
"""
from __future__ import annotations

import json
import os
import sys

import anyio
import pytest
from app.mcp import prompts
from app.prompt import profiles

from tests.test_mcp_server import API_DIR, _seed_file_db


def test_prompt_names_match_the_six_profiles() -> None:
    assert set(prompts.prompt_names()) == set(profiles.PROFILE_ORDER)
    assert len(prompts.prompt_names()) == 6


def test_render_prompt_returns_none_for_unknown_name() -> None:
    assert prompts.render_prompt("not-a-real-profile") is None


@pytest.mark.parametrize("key", profiles.PROFILE_ORDER)
def test_render_prompt_includes_instructions_output_and_verification(key: str) -> None:
    profile = profiles.get_profile(key)
    text = prompts.render_prompt(key)
    assert text is not None
    for line in profile.agent_instructions:
        assert line in text
    for line in profile.output_format:
        assert line in text
    for line in profile.verification:
        assert line in text
    assert ("READ-ONLY Git only" in text) == profile.include_git_checklist


def test_render_prompt_carries_no_project_content() -> None:
    """Unlike every read tool and the doc resource, a profile prompt is
    reviewed static text — no project id, no boundary wrap, nothing to redact,
    because there is no untrusted content in it at all."""
    text = prompts.render_prompt("build")
    assert text is not None
    assert "<<< BEGIN PROJECT DATA" not in text


def test_stdio_subprocess_lists_and_gets_a_prompt(tmp_path) -> None:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    db = tmp_path / "prompts_smoke.db"
    wsid, pid = _seed_file_db(db)
    cap = json.dumps(
        {"tier": "read", "workspace_id": wsid, "project_ids": [pid], "label": "smoke"}
    )
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db}",
        "PLANARUS_MCP_CAPABILITY": cap,
        "PYTHONPATH": str(API_DIR),
    }
    results: dict = {}

    async def _run():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "app.mcp.server"], env=env, cwd=str(API_DIR)
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as sess:
                await sess.initialize()
                listed = await sess.list_prompts()
                results["names"] = sorted(p.name for p in listed.prompts)
                got = await sess.get_prompt("plan")
                results["messages"] = got.messages
                with pytest.raises(Exception):
                    await sess.get_prompt("not-a-real-profile")

    anyio.run(_run)

    assert set(results["names"]) == set(profiles.PROFILE_ORDER)
    assert len(results["messages"]) == 1
    body = results["messages"][0].content.text
    assert "Produce a concrete, scoped plan" in body
