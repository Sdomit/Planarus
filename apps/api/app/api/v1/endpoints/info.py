import socket
from typing import Optional

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


def _lan_ip() -> Optional[str]:
    """This machine's address on the local network, or None if it has no route.

    A UDP "connect" only fixes the socket's route, so the literal below is never
    contacted and no packet leaves the box. Preferred over
    gethostbyname(gethostname()), which picks an arbitrary adapter on machines
    with VPN / Hyper-V / WSL interfaces.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("192.0.2.1", 1))  # RFC 5737 TEST-NET-1 — never routable
            ip = sock.getsockname()[0]
        except OSError:  # no default route (offline / no LAN)
            return None
    # Windows can hand back the unspecified address instead of failing.
    return None if ip.startswith("127.") or ip == "0.0.0.0" else ip


@router.get("/info")
def get_info() -> dict:
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "phase": "9-v1-expansion",
        # Safe to disclose: every caller already passed the app-wide Host
        # allowlist, so they are on this machine or an approved LAN host.
        "lan_ip": _lan_ip(),
    }
