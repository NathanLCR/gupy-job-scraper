import hashlib
import hmac
import ipaddress
from ipaddress import ip_network
import pytest
from starlette.requests import Request

from services.client_identity_service import (
    ClientIdentity,
    resolve_client_identity,
    digest_client_identity,
    short_digest,
)


def make_request(peer: str = "203.0.113.10", headers: dict[str, str] | None = None) -> Request:
    """Helper to build a Starlette Request with a given peer IP and headers."""
    raw_headers = []
    if headers:
        for k, v in headers.items():
            raw_headers.append((k.lower().encode("latin-1"), v.encode("latin-1")))

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/match",
        "headers": raw_headers,
        "client": (peer, 54321) if peer else None,
    }
    return Request(scope)


def test_untrusted_peer_ignores_forwarding_headers():
    request = make_request(
        peer="203.0.113.10",
        headers={"x-forwarded-for": "198.51.100.2", "cf-connecting-ip": "198.51.100.3"},
    )
    identity = resolve_client_identity(request, trusted_networks=())
    assert identity.normalized_ip == "203.0.113.10"
    assert identity.source == "peer"


def test_untrusted_peer_digest_is_invariant_to_spoofed_headers():
    salt = "secure-random-salt-for-testing-must-be-32-chars"
    req1 = make_request(
        peer="203.0.113.10",
        headers={"x-forwarded-for": "1.1.1.1", "cf-connecting-ip": "2.2.2.2"},
    )
    req2 = make_request(
        peer="203.0.113.10",
        headers={"x-forwarded-for": "9.9.9.9", "cf-connecting-ip": "8.8.8.8"},
    )
    id1 = resolve_client_identity(req1, trusted_networks=())
    id2 = resolve_client_identity(req2, trusted_networks=())
    assert id1.normalized_ip == id2.normalized_ip == "203.0.113.10"
    assert digest_client_identity(id1.normalized_ip, salt) == digest_client_identity(id2.normalized_ip, salt)


def test_trusted_proxy_uses_valid_cloudflare_header_when_enabled():
    request = make_request(peer="10.0.0.2", headers={"cf-connecting-ip": "2001:db8::1"})
    identity = resolve_client_identity(
        request,
        trusted_networks=(ip_network("10.0.0.0/8"),),
        trust_cloudflare=True,
    )
    assert identity.normalized_ip == "2001:db8::1"
    assert identity.source == "cf-connecting-ip"


def test_trusted_proxy_ignores_cloudflare_header_when_disabled():
    request = make_request(
        peer="10.0.0.2",
        headers={"cf-connecting-ip": "198.51.100.5", "x-forwarded-for": "203.0.113.50"},
    )
    identity = resolve_client_identity(
        request,
        trusted_networks=(ip_network("10.0.0.0/8"),),
        trust_cloudflare=False,
    )
    assert identity.normalized_ip == "203.0.113.50"
    assert identity.source == "x-forwarded-for"


def test_trusted_proxy_rejects_comma_separated_cloudflare_header():
    request = make_request(
        peer="10.0.0.2",
        headers={"cf-connecting-ip": "198.51.100.5, 198.51.100.6", "x-forwarded-for": "203.0.113.50"},
    )
    identity = resolve_client_identity(
        request,
        trusted_networks=(ip_network("10.0.0.0/8"),),
        trust_cloudflare=True,
    )
    # Comma-separated CF-Connecting-IP is invalid, falls back to XFF
    assert identity.normalized_ip == "203.0.113.50"
    assert identity.source == "x-forwarded-for"


def test_trusted_proxy_rejects_malformed_cloudflare_header():
    request = make_request(
        peer="10.0.0.2",
        headers={"cf-connecting-ip": "not-an-ip", "x-forwarded-for": "203.0.113.50"},
    )
    identity = resolve_client_identity(
        request,
        trusted_networks=(ip_network("10.0.0.0/8"),),
        trust_cloudflare=True,
    )
    assert identity.normalized_ip == "203.0.113.50"
    assert identity.source == "x-forwarded-for"


def test_trusted_proxy_resolves_rightmost_non_proxy_xff():
    request = make_request(
        peer="10.0.0.2",
        headers={"x-forwarded-for": "1.2.3.4, 203.0.113.9, 10.0.0.3"},
    )
    identity = resolve_client_identity(
        request,
        trusted_networks=(ip_network("10.0.0.0/8"),),
        trust_cloudflare=False,
    )
    assert identity.normalized_ip == "203.0.113.9"
    assert identity.source == "x-forwarded-for"


def test_trusted_proxy_xff_spoofed_leftmost_does_not_alter_subject():
    salt = "secure-random-salt-for-testing-must-be-32-chars"
    req1 = make_request(
        peer="10.0.0.2",
        headers={"x-forwarded-for": "1.2.3.4, 203.0.113.9, 10.0.0.3"},
    )
    req2 = make_request(
        peer="10.0.0.2",
        headers={"x-forwarded-for": "99.88.77.66, 203.0.113.9, 10.0.0.3"},
    )
    networks = (ip_network("10.0.0.0/8"),)
    id1 = resolve_client_identity(req1, trusted_networks=networks, trust_cloudflare=False)
    id2 = resolve_client_identity(req2, trusted_networks=networks, trust_cloudflare=False)
    assert id1.normalized_ip == id2.normalized_ip == "203.0.113.9"
    assert digest_client_identity(id1.normalized_ip, salt) == digest_client_identity(id2.normalized_ip, salt)


def test_trusted_proxy_falls_back_to_peer_when_all_xff_are_trusted():
    request = make_request(
        peer="10.0.0.2",
        headers={"x-forwarded-for": "10.0.0.5, 10.0.0.6"},
    )
    identity = resolve_client_identity(
        request,
        trusted_networks=(ip_network("10.0.0.0/8"),),
        trust_cloudflare=False,
    )
    assert identity.normalized_ip == "10.0.0.2"
    assert identity.source == "peer"


def test_trusted_proxy_falls_back_to_peer_when_xff_is_malformed():
    request = make_request(
        peer="10.0.0.2",
        headers={"x-forwarded-for": "garbage, invalid-ip"},
    )
    identity = resolve_client_identity(
        request,
        trusted_networks=(ip_network("10.0.0.0/8"),),
        trust_cloudflare=False,
    )
    assert identity.normalized_ip == "10.0.0.2"
    assert identity.source == "peer"


def test_ipv4_mapped_ipv6_normalization():
    # IPv4-mapped IPv6 ::ffff:192.0.2.1 should normalize to 192.0.2.1
    request = make_request(peer="::ffff:192.0.2.1")
    identity = resolve_client_identity(request, trusted_networks=())
    assert identity.normalized_ip == "192.0.2.1"
    assert identity.source == "peer"

    # Forwarded header IPv4-mapped IPv6
    req_fwd = make_request(peer="10.0.0.2", headers={"cf-connecting-ip": "::ffff:198.51.100.77"})
    id_fwd = resolve_client_identity(
        req_fwd,
        trusted_networks=(ip_network("10.0.0.0/8"),),
        trust_cloudflare=True,
    )
    assert id_fwd.normalized_ip == "198.51.100.77"


def test_ipv6_canonical_normalization():
    request = make_request(peer="2001:0db8:0000:0000:0000:0000:0000:0001")
    identity = resolve_client_identity(request, trusted_networks=())
    assert identity.normalized_ip == "2001:db8::1"


def test_digest_client_identity_properties():
    salt = "test-salt-secret-key-32-characters-long"
    raw_ip = "203.0.113.88"
    digest = digest_client_identity(raw_ip, salt)

    assert len(digest) == 64
    assert raw_ip not in digest
    assert short_digest(digest) == digest[:12]
    assert len(short_digest(digest)) == 12

    # Determinism
    assert digest_client_identity(raw_ip, salt) == digest


def test_missing_client_peer_falls_back_to_safe_default():
    request = make_request(peer=None)
    identity = resolve_client_identity(request, trusted_networks=())
    assert identity.normalized_ip == "127.0.0.1"
    assert identity.source == "peer"
