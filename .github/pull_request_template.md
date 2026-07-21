**What changed**

**Why**

**How you tested it**
<!-- CI runs both suites, but say what you actually ran locally. -->
- [ ] `python -m pytest` from `apps/api`
- [ ] `pnpm test:web` and `pnpm typecheck:web`
- [ ] Clicked through the affected surface

**The invariant**
Planarus's rule is that external AI clients may read and propose, never apply.

- [ ] This PR doesn't add a path for an agent to write project state without
      human approval — or it does, and I've explained why below.
