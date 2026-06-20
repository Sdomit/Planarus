"""Phase 7A proposal policy: action allowlist, binding/checksums, apply handlers.

The policy package is the *only* thing that grants a proposal power. It is code,
not data, and is pinned by ``allowlist.POLICY_VERSION`` so a proposal bound to an
old policy is invalidated at apply time.
"""
