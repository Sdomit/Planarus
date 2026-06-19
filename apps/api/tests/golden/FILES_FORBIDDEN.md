---
project: golden-project
kind: files_forbidden
updated_at: 2026-06-19T00:00:00+00:00
source_of_truth: AgentBoard
generated: true
pinned: false
---

# Forbidden paths

Glob deny-list of paths agents must never read, modify, or exfiltrate.
These win over any allow rule and are never removed once added.

- **/*.key
- **/*.pem
- **/*credential*
- **/.env
- **/.env.*
- **/secrets/**
- .env
- .env.*
- credentials/**
- secrets/**
