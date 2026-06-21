"""Phase 7C1 external HTTP API.

A loopback-default, disabled-by-default surface at ``/api/external/v1`` that
permits only bounded project reads and pending task/decision proposals. It reuses
the Phase 7B shared read/propose handlers + serializers and the Phase 7A approval
engine; it never exposes approve/apply/reject/invalidate or any canonical
mutation. All error responses are RFC 9457 ``application/problem+json``.
"""
