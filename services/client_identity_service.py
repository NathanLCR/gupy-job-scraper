import hashlib
import hmac
import ipaddress
import logging
from dataclasses import dataclass
from typing import Literal, Optional, Sequence, Union
from starlette.requests import Request

logger = logging.getLogger("skillpulse.client_identity")


@dataclass(frozen=True)
class ClientIdentity:
    normalized_ip: str
    source: Literal["peer", "cf-connecting-ip", "x-forwarded-for"]


def normalize_ip(raw: Optional[str]) -> Optional[str]:
    """Parse, strip zone IDs, convert IPv4-mapped IPv6, and normalize IP string."""
    if not raw or not isinstance(raw, str):
        return None
    cleaned = raw.strip()
    if "%" in cleaned:
        cleaned = cleaned.split("%", 1)[0]
    try:
        addr = ipaddress.ip_address(cleaned)
    except ValueError:
        return None

    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        return str(addr.ipv4_mapped)
    return str(addr)


def resolve_client_identity(
    request: Request,
    trusted_networks: Sequence[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]],
    trust_cloudflare: bool = False,
) -> ClientIdentity:
    """
    Resolve client identity with spoof resistance according to trusted proxy topology.

    - Untrusted immediate TCP peer -> always peer IP (forwarding headers ignored).
    - Trusted immediate TCP peer:
      1. CF-Connecting-IP (single valid IP) if trust_cloudflare is enabled.
      2. Right-most non-trusted address in X-Forwarded-For.
      3. Peer address fallback if all hops are trusted or headers invalid.
    """
    raw_peer = request.client.host if request.client else "127.0.0.1"
    normalized_peer = normalize_ip(raw_peer) or "127.0.0.1"

    is_peer_trusted = False
    try:
        peer_addr = ipaddress.ip_address(normalized_peer)
        is_peer_trusted = any(peer_addr in net for net in trusted_networks)
    except ValueError:
        is_peer_trusted = False

    if not is_peer_trusted:
        return ClientIdentity(normalized_ip=normalized_peer, source="peer")

    # Peer is a trusted proxy
    if trust_cloudflare:
        cf_header = request.headers.get("cf-connecting-ip")
        if cf_header:
            if "," in cf_header:
                logger.warning(
                    "Rejected invalid multi-value CF-Connecting-IP header",
                    extra={"event": "proxy_header_rejected", "header": "cf-connecting-ip"},
                )
            else:
                norm_cf = normalize_ip(cf_header)
                if norm_cf:
                    return ClientIdentity(normalized_ip=norm_cf, source="cf-connecting-ip")
                logger.warning(
                    "Rejected unparseable CF-Connecting-IP header",
                    extra={"event": "proxy_header_rejected", "header": "cf-connecting-ip"},
                )

    xff_header = request.headers.get("x-forwarded-for")
    if xff_header:
        parts = [p.strip() for p in xff_header.split(",") if p.strip()]
        for part in reversed(parts):
            norm_part = normalize_ip(part)
            if not norm_part:
                logger.warning(
                    "Rejected unparseable X-Forwarded-For component",
                    extra={"event": "proxy_header_rejected", "header": "x-forwarded-for"},
                )
                continue
            try:
                part_addr = ipaddress.ip_address(norm_part)
            except ValueError:
                continue
            if any(part_addr in net for net in trusted_networks):
                continue
            return ClientIdentity(normalized_ip=norm_part, source="x-forwarded-for")

    logger.info(
        "Falling back to peer address for trusted proxy request",
        extra={"event": "client_identity_peer_fallback"},
    )
    return ClientIdentity(normalized_ip=normalized_peer, source="peer")


def digest_client_identity(normalized_ip: str, salt: str) -> str:
    """Generate HMAC-SHA256 hex digest of normalized client IP using configured salt."""
    return hmac.new(
        salt.encode("utf-8"),
        normalized_ip.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def short_digest(subject_digest: str) -> str:
    """Return at most 12-char hex digest prefix for safe operational logging."""
    return subject_digest[:12]
