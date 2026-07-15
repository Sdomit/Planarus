---
project: golden-project
kind: agent_rules
updated_at: 2026-06-19T00:00:00+00:00
source_of_truth: Approvo
generated: true
pinned: false
---

# Agent rules

## Scope
- Operate only within [FILES_ALLOWED.md](FILES_ALLOWED.md).
- Never read, modify, or exfiltrate paths in [FILES_FORBIDDEN.md](FILES_FORBIDDEN.md).

## Approval
- Every write proposed through an external AI surface is approval-gated (proposal -> human approve -> apply).
- Local human actions may write directly; they are still validated and audited.

## Response format
1. What changed
2. Files touched
3. Validation performed
4. Risks / open questions
5. Exact next step
