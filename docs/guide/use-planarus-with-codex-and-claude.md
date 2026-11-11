# Use Planarus with Codex and Claude

Planarus can give an agent a scoped view of projects through its MCP server. The agent can read records and, with **Read + propose** access, submit changes to the approval queue. The owner reviews and applies proposals by default. The optional project-scoped Auto accept switch applies valid proposals in the background until turned off.

## Connect a local agent

1. Start the Planarus app and open **Settings → Integrations → MCP (local agents)**.
2. Choose the workspace and **Read only** or **Read + propose**. The generated configuration includes the projects in that workspace. Choose a narrower scope in the client configuration if you do not want every project available to the agent.
3. For **Codex**, copy the **Codex TOML** tab into your private `~/.codex/config.toml` or a trusted project's `.codex/config.toml`. For **Claude Code**, use the **Claude Code CLI** tab from the displayed `apps/api` directory. For **Claude Desktop**, use the **JSON config** tab. The generated values include the server command, working directory, capability scope, and this instance's database path when it uses local SQLite.
4. Start a new agent session and verify the `planarus` MCP server is connected. In Codex, `codex mcp list` shows configured servers; in Claude Code, `claude mcp list` does the same. Ask the agent to list your Planarus projects as a read-only smoke check.

The root [AGENTS.md](../../AGENTS.md) guides Codex when working in this repository, and [CLAUDE.md](../../CLAUDE.md) guides Claude Code. For another repository or a one-off chat, open **Context → Agent prompts** in the Planarus menu and copy the shared prompt into Codex, Claude, or both. The same text is available in [the agent prompt](planarus-agent-prompt.md) and on the MCP card.

After you create a project, Planarus opens **Agent prompts** for that project. The prompt names its exact ID, workspace, summary, status, and linked folder. The window also provides project-scoped **Codex config.toml** and **Claude Code .mcp.json** snippets plus the automatic progress-hook link. Reopen the same window later from the project card’s **⋯ → Agent prompts** menu. In the public edition, a project in Normal mode must be switched to Agentic before using MCP.

Use **Copy everything** to paste one complete setup message into Codex or Claude Code. It includes both client configurations, the one-time hook command, the repository project link, and the shared project prompt. The agent should use only its own client configuration and merge it with existing settings. The individual copy buttons remain available when you need one piece.

For a new project, the agents can draft a plan but cannot create the project through MCP. Create the project in Planarus, refresh the MCP config so its scope includes it, and reconnect the client. The agent can then propose phases, tasks, milestones, decisions, risks, comments, URL links, and typed connections through MCP; each appears in its matching menu after approval and application, either manually or through the owner-enabled Auto accept setting. For an existing project, give the agent its name; it will read the current work before making changes. If both agents work on one project, assign separate areas and use Planarus tasks and decisions as approved handoffs. MCP does not provide direct agent-to-agent chat.

The shared prompt asks agents to write short, specific titles and put each piece of information in the right field. Longer descriptions and comments can use Markdown paragraphs and bullets; the Planning menus render those fields as formatted text, and the approval preview preserves line breaks for review.

## Automatic progress hook

The **Agent prompts** window has a one-time setup command and a project link. Run the setup command once on the machine where Codex and Claude Code run. It adds a `Stop` hook to your user-level Codex and Claude Code settings while preserving existing hooks. Choose a Planarus project in the window, copy its link, and save it as `.planarus-progress.json` at the root of the code repository. Add that file to the code repository's `.gitignore` because its ID belongs to this local Planarus instance. Repeat the link step for another code repository or worktree; the one-time setup remains installed.

At the end of a turn in a linked repository, the hook asks the agent to use Planarus MCP for a progress pass if its answer did not include a `Planarus sync:` line. The agent checks for meaningful changes to tasks, phases, milestones, decisions, risks, comments, URL links, or typed connections and proposes the matching record when warranted. A second stop is allowed so the hook cannot loop. The hook itself does not write project records, and all proposals still require your approval. A turn that only answers a question can report `Planarus sync: no update needed: <reason>`.

Codex requires you to review and trust a newly installed hook using `/hooks` in the CLI or **Settings → Hooks** in the desktop app. Claude Code reads its updated settings automatically. The hooks run in local sessions; a remote agent needs the same setup in its own execution environment. See the official [Codex hooks](https://learn.chatgpt.com/docs/hooks) and [Claude Code hooks](https://code.claude.com/docs/en/hooks) references.

Keep client configuration private: it can contain local paths and project IDs. The prompt files in this repository contain no machine-specific configuration or credentials. A Codex or Claude session must be restarted or reloaded to pick up newly added MCP configuration or repository instructions.

If you use a project-local `.mcp.json` for Claude Code, it may show the Planarus server as **Pending approval**. Open Claude Code in that project and approve the server after reviewing its command and scope.

Client references: [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp) and [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp).


## Auto accept in the Approval Queue

The **Auto accept all proposals** switch is off by default and belongs to the selected project. Turning it on processes the current pending queue and future proposals while the local API is running, even when no browser is open. The setting survives restart. Turn it off in the same queue to return to manual approval. Planarus still runs the ordinary policy, expiry, and stale-target checks; failed or invalidated proposals remain visible for review. Agents should poll get_approval_status before reporting that a record changed.
