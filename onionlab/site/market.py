"""ONIONLAB target site: mock hidden services for testing an attribution tool.

One image serves two roles, selected by SITE_ROLE:

  market   a vendor marketplace with profiles, feedback and payment details
  forum    a discussion board whose members partly overlap with the market

They run as two separate hidden services with two different .onion addresses,
and that is the point. It lets the lab exercise things a single service cannot:

  * recursive discovery -- the market links to the forum, so a crawler starting
    from one seed has to find the other by itself, which is the crawler design
    in Wangchuk & Rathod (2023);
  * cross-service correlation -- both roles ship the same template and favicon,
    so the service-fingerprint channels have a genuine rebrand to detect;
  * cross-service personas -- several operators hold accounts on both, under
    different handles, which is the linkage problem the platform exists for.

Deliberately planted clear-web leaks
------------------------------------
Some accounts leak a clear-web identifier: an e-mail address, a domain, a
messaging handle. This reproduces the phenomenon the paper is built on -- that
dark web users leak clear-web identifiers through negligence, which is how Ross
Ulbricht was found. The leaks are graded in ground_truth.json so the extraction
and the pivot can be scored rather than eyeballed.

Alongside them are decoys: abuse contacts, boilerplate support addresses and
mailing-list addresses that a naive scraper will happily collect and that a
useful one must rank down. Getting that separation right is what the paper
calls context setting.

Threat model and hardening are documented in SECURITY.md and enforced in
docker-compose.yml. The code rules that matter: every response is built from an
in-memory dataset, no file read is driven by a request path, there is no
subprocess/eval/template engine/database, all user-controlled text is escaped
at one point, no external resources are referenced, and errors return a fixed
page with no traceback.

Content is inert. The PGP blocks are shaped but not real keys, the Bitcoin
addresses are not valid mainnet addresses, the e-mail domains are RFC 2606
reserved or obviously fictional, and no listing describes a real good.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import random
import re
import struct
import sys
import zlib
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SEED = int(os.environ.get("ONIONLAB_SEED", "20260904"))
ROLE = os.environ.get("SITE_ROLE", "market").strip().lower()

BRAND = {"market": "KILO EXCHANGE", "forum": "THE LANTERN BOARD"}[ROLE]

# Path to the *other* service's hostname file, mounted read-only from the Tor
# key volume.
PEER_ONION_FILE = os.environ.get("PEER_ONION_FILE", "").strip()
_peer_cache: list = [None]


def peer_onion() -> str:
    """The sibling service's address, read lazily and then cached.

    It cannot be an environment variable: Tor generates the address, and Tor
    starts *after* this container (it waits for our health check). So at our
    startup the file does not exist yet. Reading it on first use instead of at
    import time is what makes a two-service lab work without a provisioning
    step, and a failed read is simply "no peer yet" rather than an error.
    """
    if _peer_cache[0] is not None:
        return _peer_cache[0]
    if not PEER_ONION_FILE:
        return ""
    try:
        with open(PEER_ONION_FILE, "r", encoding="utf-8") as fh:
            value = fh.read().strip()
        if value.endswith(".onion"):
            _peer_cache[0] = value
            return value
    except OSError:
        pass
    return ""

# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
#
# (handle, operator, utc_offset, style, pgp_group, wallet_group, leak)
# `leak` is the clear-web identifier this account carelessly published, or None.

MARKET_ACCOUNTS = [
    ("kavach_supply",  "OP-A", 5.5,  1, "A", "A", "kavach.supply@gmail.example"),
    ("kavach.supply2", "OP-A", 5.5,  1, "A", "A", None),
    ("nightfreight",   "OP-A", 5.5,  2, "B", "A", None),
    ("harbor_light",   "OP-B", -5.0, 3, "C", "B", "harborlight.ops@protonmail.example"),
    ("HarborLight_hq", "OP-B", -5.0, 3, "C", "B", None),
    ("quartzpine",     "OP-C", 1.0,  4, "D", "C", None),
    ("stillwater_co",  "OP-D", 8.0,  5, "E", "D", "stillwater.trading@example.com"),
    ("ninelives",      "OP-E", 3.0,  6, "F", "E", None),
    ("paper_ghost",    "OP-F", -8.0, 7, "G", "F", "paperghost-shop.example.org"),
    ("brasstack",      "OP-G", 2.0,  8, "H", "G", None),
]

# The forum roster overlaps the market by operator, not by handle. Recovering
# those pairs across two different .onion services is the headline task.
FORUM_ACCOUNTS = [
    ("kav_admin",      "OP-A", 5.5,  1, "A", "A", None),
    ("hbl_support",    "OP-B", -5.0, 3, "C", "B", "hl.trading@gmail.example"),
    ("pale_quartz",    "OP-C", 1.0,  4, "D", "C", None),
    ("ninelives_alt",  "OP-E", 3.0,  6, "F", "E", "ninelives.dev@gmail.example"),
    ("driftwood",      "OP-H", 9.0,  9, "I", "H", None),
    ("sundowner",      "OP-I", -3.0, 10, "J", "I", "sundowner.mail@yandex.example"),
    ("tallow_and_co",  "OP-J", 4.0,  11, "K", "J", None),
]

ACCOUNTS = MARKET_ACCOUNTS if ROLE == "market" else FORUM_ACCOUNTS

# Boilerplate addresses that appear on every page. A naive scraper collects
# these as eagerly as it collects a vendor's private mailbox; the context
# scorer has to tell them apart, and this is what it is scored against.
DECOY_CONTACTS = [
    "abuse@torproject.example",
    "postmaster@example.net",
    "security@example.org",
    "noreply@example.com",
]

GREETINGS = ["hey all", "quick note", "ok so", "listen up", "good day", "yo"]
SIGNOFFS = ["cheers", "thanks", "stay safe", "regards", "later", "peace"]

MARKET_TOPICS = [
    "escrow on order {n} has been pending {d} days, support is silent",
    "mirror was down again around {hr}, please post a signed link",
    "reminder: verify my signature before trusting any mirror",
    "feedback wiped after the migration, {adj} frustrating",
    "withdrawal queue moving slowly this week, {d} days and counting",
    "dispute {n} resolved after {d} rounds, finally",
    "two factor broke after the update, anyone else",
    "new fee schedule announced with {d} days notice, {adj}",
    "profile migration lost my key, rotating and re-signing everything",
    "uptime has been {adj} since the admin change",
]
FORUM_TOPICS = [
    "anyone else seeing captcha loops on the main mirror around {hr}",
    "thread {n} got locked without a reason, moderation is {adj}",
    "psa: check signatures, there are {d} fake mirrors circulating",
    "the migration guide is out of date by {d} months now",
    "vendor feedback import is broken again, {adj}",
    "reminder that staff never ask for your key in a message",
    "downtime window announced {d} days late, {adj}",
    "does anyone have a working index, the old one is dead",
    "opsec thread: rotate keys, strip metadata, do not reuse handles",
    "escrow explainer for new members, order {n} used as the example",
]
TOPICS = MARKET_TOPICS if ROLE == "market" else FORUM_TOPICS
ADJ = ["absurd", "typical", "poor", "acceptable", "frustrating", "shocking"]


def _pgp_block(group: str) -> str:
    """Syntactically plausible, cryptographically inert. The demo needs the
    shape of the artefact; publishing real key material would be careless."""
    body = hashlib.sha256(("pgp-" + group).encode()).hexdigest()
    blob = "".join(hashlib.sha256((body + str(i)).encode()).hexdigest()
                   for i in range(12))
    lines = [blob[i:i + 64] for i in range(0, len(blob), 64)]
    return ("-----BEGIN PGP PUBLIC KEY BLOCK-----\n\n" + "\n".join(lines)
            + "\n=" + body[:4] + "\n-----END PGP PUBLIC KEY BLOCK-----")


def _fingerprint(group: str) -> str:
    return hashlib.sha1(("fp-" + group).encode()).hexdigest().upper()


def _btc(group: str, i: int) -> str:
    h = hashlib.sha256(("w-%s-%d" % (group, i)).encode()).hexdigest()
    alpha = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    return "1" + "".join(alpha[int(h[j:j + 2], 16) % len(alpha)]
                         for j in range(0, 64, 2))[:33]


def _post_text(rng: random.Random, style: int) -> str:
    lower = style % 2 == 0
    commas = 0.05 + 0.04 * (style % 5)
    ell = 0.3 if style % 3 == 0 else 0.0
    out = []
    for _ in range(rng.randint(1, 3)):
        s = rng.choice(TOPICS).format(n=rng.randint(1000, 99999),
                                      d=rng.randint(2, 14),
                                      hr="%02d00 utc" % rng.randint(0, 23),
                                      adj=rng.choice(ADJ))
        if rng.random() < commas:
            w = s.split()
            if len(w) > 4:
                p = rng.randint(2, len(w) - 2)
                w[p] += ","
                s = " ".join(w)
        s += "..." if rng.random() < ell else "."
        out.append(s)
    text = "%s, %s %s" % (rng.choice(GREETINGS), " ".join(out), rng.choice(SIGNOFFS))
    return text.lower() if lower else text


def build_dataset() -> dict:
    rng = random.Random(SEED + (0 if ROLE == "market" else 7919))
    base = datetime(2026, 1, 5, tzinfo=timezone.utc)
    accounts, posts = {}, []
    for handle, op, tz, style, pgpg, walg, leak in ACCOUNTS:
        accounts[handle] = {
            "handle": handle,
            "joined": (base - timedelta(days=rng.randint(30, 600))).date().isoformat(),
            "sales": rng.randint(12, 900),
            "rating": round(rng.uniform(4.1, 5.0), 2),
            "pgp": _pgp_block(pgpg),
            "pgp_fingerprint": _fingerprint(pgpg),
            "wallets": [_btc(walg, i) for i in range(rng.randint(1, 3))],
            "bio": _post_text(rng, style),
            "leak": leak,
        }
        vrng = random.Random(SEED + style * 977 + int(
            hashlib.md5(handle.encode()).hexdigest()[:6], 16))
        for q in range(vrng.randint(18, 40)):
            peak = 14 + (style % 5)
            local = (vrng.gauss(peak, 3.0)) % 24
            ts = (base + timedelta(days=vrng.randint(0, 240), hours=local)
                  - timedelta(hours=tz))
            posts.append({"id": "%s-%03d" % (handle, q), "vendor": handle,
                          "ts": ts.replace(microsecond=0).isoformat(),
                          "text": _post_text(vrng, style)})
    posts.sort(key=lambda p: p["ts"])
    return {"accounts": accounts, "posts": posts}


DATA = build_dataset()


# ---------------------------------------------------------------------------
# Favicon: generated, so the site has a real hashable icon
# ---------------------------------------------------------------------------
#
# Both roles ship the SAME icon on purpose. Favicon reuse across services is one
# of the strongest rebrand pivots in practice, and the lab has to contain the
# phenomenon for the channel to be demonstrated rather than asserted.

def _png(width: int, height: int, rgb: tuple) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = b""
    for y in range(height):
        raw += b"\x00"
        for x in range(width):
            on = ((x // 4) + (y // 4)) % 2 == 0
            raw += bytes(rgb if on else (18, 24, 33))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


FAVICON = _png(32, 32, (77, 163, 255))

CSS = """
:root{--bg:#0d1117;--pan:#161b22;--ln:#26303c;--ink:#d7e2ee;--mut:#8b9bb0;--ac:#4da3ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.6 system-ui,sans-serif}
header{background:var(--pan);border-bottom:1px solid var(--ln);padding:14px 22px;
 display:flex;justify-content:space-between;align-items:center}
h1{font-size:17px;margin:0;letter-spacing:.16em}
a{color:var(--ac);text-decoration:none}a:hover{text-decoration:underline}
main{max-width:960px;margin:0 auto;padding:22px}
.card{background:var(--pan);border:1px solid var(--ln);border-radius:9px;
 padding:15px 18px;margin-bottom:14px}
.mut{color:var(--mut)}
table{width:100%;border-collapse:collapse}
th{text-align:left;color:var(--mut);font-weight:500;font-size:11px;
 text-transform:uppercase;letter-spacing:.07em;padding:7px 8px;border-bottom:1px solid var(--ln)}
td{padding:7px 8px;border-bottom:1px solid #1c2532}
pre{background:#0a0e13;border:1px solid var(--ln);border-radius:6px;padding:11px;
 overflow:auto;font-size:11px;color:#9fb3c8}
.badge{background:#16283c;border:1px solid #24486e;color:#7cc4ff;border-radius:99px;
 padding:1px 9px;font-size:11px}
footer{color:var(--mut);font-size:12px;padding:18px 22px;border-top:1px solid var(--ln)}
"""

E = html.escape


def page(title: str, body: str) -> bytes:
    peer = ""
    addr = peer_onion()
    if addr:
        label = "discussion board" if ROLE == "market" else "marketplace"
        peer = ('<div class="card mut">Our %s is at '
                '<a href="http://%s/">%s</a>. Mirrors: '
                '<a href="/mirrors">/mirrors</a></div>'
                % (E(label), E(addr), E(addr[:24] + "...onion")))
    return ("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s &middot; %s</title><style>%s</style></head><body>
<header><h1>%s</h1><span class="badge">onion service</span></header>
<main>%s%s</main>
<footer>Escrow held 14 days. Verify every mirror against a signed link.<br>
Abuse: %s &middot; Postmaster: %s<br>
<span class="mut">ONIONLAB demonstration target &mdash; synthetic data, no real
goods, no real keys, no real addresses.</span></footer></body></html>"""
            % (E(title), E(BRAND), CSS, E(BRAND), body, peer,
               E(DECOY_CONTACTS[0]), E(DECOY_CONTACTS[1]))).encode("utf-8")


def index() -> bytes:
    noun = "Vendors" if ROLE == "market" else "Members"
    rows = "".join(
        '<tr><td><a href="/vendor/%s">%s</a></td><td class="mut">%s</td>'
        '<td>%d</td><td>%.2f</td></tr>'
        % (E(v["handle"]), E(v["handle"]), E(v["joined"]), v["sales"], v["rating"])
        for v in DATA["accounts"].values())
    recent = "".join(
        '<tr><td class="mut">%s</td><td><a href="/vendor/%s">%s</a></td>'
        '<td>%s</td></tr>'
        % (E(p["ts"][:16].replace("T", " ")), E(p["vendor"]), E(p["vendor"]),
           E(p["text"][:110]))
        for p in DATA["posts"][-25:][::-1])
    return page("Index", """
<div class="card"><h2>%s</h2>
<table><tr><th>handle</th><th>joined</th><th>posts</th><th>rating</th></tr>
%s</table></div>
<div class="card"><h2>Recent board activity</h2>
<table><tr><th>time (utc)</th><th>account</th><th>message</th></tr>%s</table></div>
<div class="card mut">Machine-readable index at
<a href="/api/vendors.json">/api/vendors.json</a>.
Support enquiries: %s</div>""" % (noun, rows, recent, E(DECOY_CONTACTS[3])))


def vendor_page(handle: str) -> bytes | None:
    v = DATA["accounts"].get(handle)
    if v is None:
        return None
    posts = [p for p in DATA["posts"] if p["vendor"] == handle]
    plist = "".join(
        '<tr><td class="mut">%s</td><td>%s</td></tr>'
        % (E(p["ts"][:16].replace("T", " ")), E(p["text"]))
        for p in posts[::-1])
    wallets = "".join("<div>%s</div>" % E(w) for w in v["wallets"])

    # The planted leak, phrased the way a careless operator actually phrases it
    contact = ""
    if v["leak"]:
        if "@" in v["leak"]:
            contact = ('<div class="card"><h2>Contact</h2>'
                       '<p>For bulk orders and escrow disputes reach me directly '
                       'at %s &mdash; faster than the on-site messages.</p></div>'
                       % E(v["leak"]))
        else:
            contact = ('<div class="card"><h2>Contact</h2>'
                       '<p>Direct shop and stock list: <a href="http://%s/">%s</a>'
                       '</p></div>' % (E(v["leak"]), E(v["leak"])))

    return page(handle, """
<div class="card"><h2>%s</h2>
<p class="mut">joined %s &middot; %d posts &middot; rating %.2f</p>
<p>%s</p></div>
%s
<div class="card"><h2>Payment</h2>%s</div>
<div class="card"><h2>Public key</h2>
<p class="mut">fingerprint %s</p><pre>%s</pre></div>
<div class="card"><h2>Board messages (%d)</h2><table>%s</table></div>
<p><a href="/">&larr; index</a></p>"""
        % (E(v["handle"]), E(v["joined"]), v["sales"], v["rating"], E(v["bio"]),
           contact, wallets, E(v["pgp_fingerprint"]), E(v["pgp"]),
           len(posts), plist))


def mirrors_page() -> bytes:
    """A mirrors page, which is how onion services actually reference each
    other and therefore how a crawler discovers the next one."""
    peer = ""
    addr = peer_onion()
    if addr:
        peer = ('<li><a href="http://%s/">%s</a> &mdash; our other service</li>'
                % (E(addr), E(addr)))
    return page("Mirrors", """
<div class="card"><h2>Official mirrors</h2>
<p class="mut">Always verify a mirror against a signed message before use.</p>
<ul>%s</ul>
<p class="mut">Report phishing mirrors to %s</p></div>
<p><a href="/">&larr; index</a></p>""" % (peer, E(DECOY_CONTACTS[2])))


ROUTE_VENDOR = re.compile(r"^/vendor/([A-Za-z0-9._-]{1,64})$")


class Handler(BaseHTTPRequestHandler):
    server_version = "nginx"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path[:80]))

    def handle_one_request(self):
        try:
            BaseHTTPRequestHandler.handle_one_request(self)
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            self.close_connection = True

    def handle_error(self, *args):
        # socketserver's default prints a full traceback for every dropped or
        # malformed connection. On a hidden service those arrive constantly and
        # a log full of tracebacks hides the events that matter.
        sys.stderr.write("dropped connection\n")

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; "
                         "img-src 'self' data:; base-uri 'none'; form-action 'none'")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            path = self.path.split("?", 1)[0]
            if len(path) > 200:
                return self._send(414, page("Error", "<div class=card>Too long.</div>"),
                                  "text/html; charset=utf-8")
            if path == "/":
                return self._send(200, index(), "text/html; charset=utf-8")
            if path == "/favicon.ico":
                return self._send(200, FAVICON, "image/png")
            if path == "/mirrors":
                return self._send(200, mirrors_page(), "text/html; charset=utf-8")
            if path == "/robots.txt":
                return self._send(200, b"User-agent: *\nDisallow: /admin\n",
                                  "text/plain")
            if path == "/api/vendors.json":
                payload = json.dumps({
                    "role": ROLE,
                    "accounts": [{"handle": v["handle"], "joined": v["joined"],
                                  "posts": v["sales"], "rating": v["rating"],
                                  "pgp_fingerprint": v["pgp_fingerprint"],
                                  "wallets": v["wallets"]}
                                 for v in DATA["accounts"].values()]},
                    indent=1).encode()
                return self._send(200, payload, "application/json")
            m = ROUTE_VENDOR.match(path)
            if m:
                body = vendor_page(m.group(1))
                if body is not None:
                    return self._send(200, body, "text/html; charset=utf-8")
            self._send(404, page("Not found",
                                 '<div class="card">No such page. '
                                 '<a href="/">Index</a></div>'),
                       "text/html; charset=utf-8")
        except Exception:
            sys.stderr.write("handler error\n")
            try:
                self._send(500, page("Error", '<div class="card">Server error.</div>'),
                           "text/html; charset=utf-8")
            except Exception:
                pass


def _serve_tls(port: int) -> None:
    """Serve the same content over TLS if the baked certificate is present.

    Non-fatal by design: the plain service is what the demo depends on, and
    losing it because a certificate was missing would be a poor trade. The TLS
    listener exists so the collector has real certificate metadata to extract.
    """
    import ssl
    import threading
    cert, key = "/certs/cert.pem", "/certs/key.pem"
    if not (os.path.exists(cert) and os.path.exists(key)):
        sys.stderr.write("no certificate present, TLS listener disabled\n")
        return
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        sys.stderr.write("onionlab TLS listener on %d\n" % port)
    except Exception as exc:
        sys.stderr.write("TLS listener disabled: %s\n" % type(exc).__name__)


def main() -> None:
    # Binds inside the container only. The container publishes no port to the
    # host and sits on an internal Docker network, so the only thing that can
    # open this socket is the Tor container.
    port = int(os.environ.get("PORT", "8080"))
    _serve_tls(int(os.environ.get("TLS_PORT", "8443")))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    srv.daemon_threads = True
    sys.stderr.write("onionlab %s on %d, %d accounts, %d posts\n"
                     % (ROLE, port, len(DATA["accounts"]), len(DATA["posts"])))
    srv.serve_forever()


if __name__ == "__main__":
    main()
