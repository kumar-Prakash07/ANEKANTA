"""Infrastructure fingerprinting for hidden services.

An operator can rename a market, rotate a PGP key and move to a new .onion
address in an afternoon. What they usually do not do is rebuild the *stack*:
the same favicon gets copied across, the same TLS key is reused, the same
template is redeployed, the same reverse proxy emits headers in the same order.
Those are the artefacts that survive a rebrand, and this module extracts them.

Seven families are collected, ordered roughly by how hard each is to change by
accident and how hard it is to change on purpose:

  favicon        mmh3 hash over the base64-encoded icon -- the Shodan
                 convention, so values are comparable with public datasets --
                 plus SHA-256 and a perceptual dHash that survives re-encoding
                 and small edits.
  TLS            issuer, subject, serial, validity window, signature algorithm,
                 SAN list, and the SHA-256 of the SubjectPublicKeyInfo. The
                 SPKI hash is the strong one: it identifies the *key*, so it
                 links services across certificate renewals and across onions.
  HTTP stack     the ordered list of response header names. Header order is a
                 property of the server implementation and its proxy chain, and
                 operators almost never think about it.
  error pages    the shape of a 404, which is template- and stack-specific and
                 is rarely customised on a rebrand.
  DOM skeleton   the tag sequence with all text and attributes stripped, so it
                 fingerprints the template rather than the content.
  CSS vocabulary the set of class names, which identifies a theme even after
                 the copy is rewritten.
  assets         SHA-256 of every linked stylesheet, script and image.

Everything here is passive: it reads what the service chose to publish. There
is no scanning, no probing for vulnerabilities, and no attempt to attack the
service or the Tor network.
"""

from __future__ import annotations

import base64
import hashlib
import re
import socket
import ssl
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

import mmh3

# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def favicon_mmh3(data: bytes) -> int:
    """Shodan's favicon hash.

    The convention is mmh3 over the *base64 re-encoding* of the bytes, with
    standard-library line wrapping. Reproducing it exactly matters: it is what
    lets a hash found here be pivoted against public internet-wide scan data.
    """
    return mmh3.hash(base64.encodebytes(data))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dhash(data: bytes, size: int = 8) -> str | None:
    """Perceptual difference hash: survives re-encoding and minor edits.

    An exact hash breaks the moment an operator re-saves the icon at a
    different quality. Comparing adjacent-pixel brightness does not.
    """
    try:
        import io
        from PIL import Image
        img = (Image.open(io.BytesIO(data)).convert("L")
               .resize((size + 1, size), Image.LANCZOS))
        # tobytes() on an "L" image is row-major one byte per pixel, and unlike
        # getdata() it is not on a deprecation path
        px = img.tobytes()
        bits = 0
        n = 0
        for row in range(size):
            for col in range(size):
                left = px[row * (size + 1) + col]
                right = px[row * (size + 1) + col + 1]
                bits = (bits << 1) | (1 if left > right else 0)
                n += 1
        return "%016x" % bits
    except Exception:
        return None


def hamming_hex(a: str, b: str) -> int:
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except Exception:
        return 64


# ---------------------------------------------------------------------------
# Structural fingerprints
# ---------------------------------------------------------------------------

TAG = re.compile(r"<\s*(/?)([a-zA-Z][a-zA-Z0-9]*)")
CLASS = re.compile(r'class\s*=\s*["\']([^"\']{1,300})["\']')
ASSET = re.compile(r'(?:href|src)\s*=\s*["\']([^"\']{1,300})["\']')


def dom_skeleton(html: str) -> list[str]:
    """Tag sequence with text and attributes removed."""
    return ["%s%s" % (slash, name.lower()) for slash, name in TAG.findall(html)]


def dom_skeleton_hash(html: str) -> str:
    return sha256(" ".join(dom_skeleton(html)).encode())[:32]


def css_vocabulary(html: str) -> list[str]:
    out: set[str] = set()
    for blob in CLASS.findall(html):
        for cls in blob.split():
            if 1 < len(cls) <= 40:
                out.add(cls)
    return sorted(out)


def header_order(headers) -> list[str]:
    return [k.lower() for k in headers.keys()]


def header_order_hash(headers) -> str:
    return sha256("|".join(header_order(headers)).encode())[:32]


# ---------------------------------------------------------------------------
# TLS
# ---------------------------------------------------------------------------

@dataclass
class TLSInfo:
    present: bool = False
    subject_cn: str = ""
    issuer_cn: str = ""
    issuer_o: str = ""
    serial: str = ""
    not_before: str = ""
    not_after: str = ""
    sig_alg: str = ""
    spki_sha256: str = ""       # hash of the public key: survives renewal
    cert_sha256: str = ""
    sans: list = field(default_factory=list)
    self_signed: bool = False
    error: str = ""

    def to_json(self) -> dict:
        return asdict(self)


def _parse_cert(der: bytes) -> TLSInfo:
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    cert = x509.load_der_x509_certificate(der)

    def name_part(name, oid) -> str:
        try:
            vals = name.get_attributes_for_oid(oid)
            return vals[0].value if vals else ""
        except Exception:
            return ""

    from cryptography.x509.oid import NameOID
    spki = cert.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)

    sans: list = []
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        sans = [str(v) for v in ext.value.get_values_for_type(x509.DNSName)]
    except Exception:
        pass

    return TLSInfo(
        present=True,
        subject_cn=name_part(cert.subject, NameOID.COMMON_NAME),
        issuer_cn=name_part(cert.issuer, NameOID.COMMON_NAME),
        issuer_o=name_part(cert.issuer, NameOID.ORGANIZATION_NAME),
        serial="%x" % cert.serial_number,
        not_before=cert.not_valid_before_utc.isoformat(),
        not_after=cert.not_valid_after_utc.isoformat(),
        sig_alg=getattr(cert.signature_algorithm_oid, "_name", "") or "",
        spki_sha256=sha256(spki),
        cert_sha256=sha256(der),
        sans=sans,
        self_signed=cert.issuer == cert.subject,
    )


def probe_tls(host: str, port: int = 443, proxy: tuple | None = None,
              timeout: float = 45.0) -> TLSInfo:
    """Retrieve and parse the certificate, optionally through a SOCKS proxy.

    Certificate validation is deliberately disabled. We are not establishing
    trust in this service -- we are cataloguing what it presents, and a
    self-signed certificate is itself an informative artefact. Refusing to look
    at untrusted certificates would discard most of the signal on this network.
    """
    sock = None
    try:
        if proxy:
            import socks
            sock = socks.socksocket()
            sock.set_proxy(socks.SOCKS5, proxy[0], proxy[1], rdns=True)
        else:
            sock = socket.socket()
        sock.settimeout(timeout)
        sock.connect((host, port))

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
            info = _parse_cert(der) if der else TLSInfo(error="no certificate")
            try:
                info.sig_alg = info.sig_alg or (tls.cipher() or ("", "", 0))[0]
            except Exception:
                pass
            return info
    except Exception as exc:
        return TLSInfo(error="%s: %s" % (type(exc).__name__, str(exc)[:80]))
    finally:
        try:
            if sock is not None:
                sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

@dataclass
class ServiceFingerprint:
    """Everything passively observable about one hidden service."""

    onion: str
    fetched_at: str = ""
    server_banner: str = ""
    favicon_mmh3: str = ""
    favicon_sha256: str = ""
    favicon_dhash: str = ""
    header_order: list = field(default_factory=list)
    header_order_hash: str = ""
    cookie_names: list = field(default_factory=list)
    dom_skeleton_hash: str = ""
    css_vocab: list = field(default_factory=list)
    css_vocab_hash: str = ""
    error_page_hash: str = ""
    asset_hashes: list = field(default_factory=list)
    tls: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)

    def as_infra_dict(self) -> dict:
        """Flatten to the exact-match fingerprint map the engines consume."""
        out = {
            "favicon_mmh3": self.favicon_mmh3,
            "favicon_sha256": self.favicon_sha256,
            "header_order": self.header_order_hash,
            "error_page": self.error_page_hash,
            "dom_skeleton": self.dom_skeleton_hash,
            "css_vocab": self.css_vocab_hash,
            "server_banner": self.server_banner,
        }
        if self.tls.get("present"):
            out["tls_spki"] = self.tls.get("spki_sha256", "")
            out["tls_cert"] = self.tls.get("cert_sha256", "")
        return {k: v for k, v in out.items() if v}


def fingerprint_service(session, onion: str, base_html: str, base_headers,
                        favicon: bytes | None, error_html: str | None,
                        assets: dict | None = None,
                        tls: TLSInfo | None = None) -> ServiceFingerprint:
    fp = ServiceFingerprint(
        onion=onion,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        server_banner=(base_headers.get("Server", "") or "").strip(),
        header_order=header_order(base_headers),
        header_order_hash=header_order_hash(base_headers),
        cookie_names=sorted({c.split("=")[0].strip()
                             for c in base_headers.get("Set-Cookie", "").split(",")
                             if "=" in c}),
        dom_skeleton_hash=dom_skeleton_hash(base_html),
    )
    vocab = css_vocabulary(base_html)
    fp.css_vocab = vocab[:200]
    fp.css_vocab_hash = sha256("|".join(vocab).encode())[:32] if vocab else ""

    if favicon:
        fp.favicon_mmh3 = str(favicon_mmh3(favicon))
        fp.favicon_sha256 = sha256(favicon)
        fp.favicon_dhash = dhash(favicon) or ""
    if error_html is not None:
        # hash the *shape* of the error page, not its text, so a page that
        # echoes the requested path still fingerprints consistently
        fp.error_page_hash = dom_skeleton_hash(error_html)
    if assets:
        fp.asset_hashes = sorted(sha256(b)[:32] for b in assets.values())
    if tls is not None:
        fp.tls = tls.to_json()
    return fp
