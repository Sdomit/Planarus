"""Phase 7B STDIO MCP server.

A local AI client (Claude Desktop, Codex, …) launches `python -m app.mcp.server`
over stdio. The server exposes **bounded, project-scoped reads** and **proposal
creation only** — it never approves/applies/rejects/invalidates, mutates canonical
data directly, writes files, runs commands, alters Git, or opens a network port.

Design: every tool handler is pure Python with **no MCP-SDK import**; only
`server.py` imports the SDK and adapts the static registry to the stdio transport.
Proposals flow through the same `approval_service.create_proposal()` path as the
REST API, so Phase 7A policy, secret-scan, binding, and audit cannot be bypassed.
"""
