"""Collection from live hidden services.

Turns an onion service into the same `Persona` and `Post` records the synthetic
benchmark produces, so everything downstream -- engines, calibration, fusion,
resolution, reporting -- runs unchanged on live data. That interface parity is
the whole point of the module: the benchmark exists to measure the system, and
it only means anything if the measured system is the one that runs.

Operating rules, enforced in code rather than left to the operator:

  * All traffic goes through Tor with `socks5h`, so the .onion name is resolved
    at the proxy. Resolving it locally would leak the lookup to whatever DNS
    resolver this machine uses and is the classic way people deanonymise
    themselves while doing this work.
  * Requests are serialised and rate-limited. A hidden service has a fraction
    of a normal site's capacity, and hammering one is both rude and conspicuous.
  * `robots.txt` is fetched and honoured.
  * Fetches are capped in count and size, and the crawler never submits a form,
    follows an off-onion link, or sends a non-GET method.

Nothing here attacks anything. It reads what a service publishes to any
visitor, which is the same material an analyst would read by hand.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from ..osint import context as osint_context
from ..osint import mentions as osint_mentions
from .safety import SafetyGate
from ..schema import Persona, Post
from .fingerprint import ServiceFingerprint, fingerprint_service, probe_tls

ONION_RE = re.compile(r"\b([a-z2-7]{56})\.onion\b")


def sanitise_onions(candidates) -> list:
    """The paper's sanitiser module, for addresses.

    A v3 onion address is exactly 56 base32 characters. Anything else is a v2
    address (removed from the network years ago), a typo, or a string that
    merely looks like one, and crawling it wastes a circuit build -- which on
    Tor costs seconds, not milliseconds, so the filter pays for itself
    immediately at scale.
    """
    out, seen = [], set()
    for raw in candidates:
        if not raw:
            continue
        value = raw.strip().lower()
        value = value.replace("http://", "").replace("https://", "").strip("/")
        value = value.split("/")[0].split(":")[0]
        m = re.fullmatch(r"([a-z2-7]{56})\.onion", value)
        if not m or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


BTC_RE = re.compile(r"\b([13][a-km-zA-HJ-NP-Z1-9]{25,34})\b")
XMR_RE = re.compile(r"\b(4[0-9AB][1-9A-HJ-NP-Za-km-z]{93})\b")
PGP_RE = re.compile(
    r"-----BEGIN PGP PUBLIC KEY BLOCK-----.*?-----END PGP PUBLIC KEY BLOCK-----",
    re.S)
FPR_RE = re.compile(r"\b([0-9A-F]{40})\b")
CONTACT_RE = re.compile(
    r"\b([A-Za-z0-9._-]{2,32}@(?:xmpp\.jp|jabber\.ru|jabber\.at|exploit\.im|"
    r"protonmail\.com|tutanota\.com|cock\.li))\b", re.I)
TAGS = re.compile(r"<[^>]+>")
TIME_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})\b")


def strip_tags(html: str) -> str:
    return re.sub(r"\s+", " ", TAGS.sub(" ", html)).strip()


@dataclass
class CrawlResult:
    onion: str
    fingerprint: ServiceFingerprint
    personas: list = field(default_factory=list)
    posts: list = field(default_factory=list)
    pages_fetched: int = 0
    bytes_fetched: int = 0
    notes: list = field(default_factory=list)
    # multi-service crawls
    onions: list = field(default_factory=list)
    fingerprints: dict = field(default_factory=dict)
    discovered_from: dict = field(default_factory=dict)
    mentions: list = field(default_factory=list)
    references: list = field(default_factory=list)
    excluded_pages: list = field(default_factory=list)
    excluded_services: list = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "onion": self.onion,
            "onions": self.onions or [self.onion],
            "services_crawled": len(self.onions or [self.onion]),
            "discovered_from": self.discovered_from,
            "pages_fetched": self.pages_fetched,
            "bytes_fetched": self.bytes_fetched,
            "personas": len(self.personas),
            "posts": len(self.posts),
            "mentions": len(self.mentions),
            "pages_excluded_by_safety_gate": len(self.excluded_pages),
            "services_excluded_by_safety_gate": len(self.excluded_services),
            "tls": bool(self.fingerprint.tls.get("present")),
            "favicon_mmh3": self.fingerprint.favicon_mmh3,
            "notes": self.notes,
        }


class TorCrawler:
    def __init__(self, proxy_host: str = "127.0.0.1", proxy_port: int = 9050,
                 delay: float = 1.0, max_pages: int = 60,
                 max_bytes: int = 8_000_000, timeout: float = 60.0,
                 safety: SafetyGate | None = None) -> None:
        import requests
        # Every fetched page passes this before anything is parsed out of it.
        # See safety.py: a page that trips is discarded whole, not redacted.
        self.safety = safety or SafetyGate()
        self.excluded_pages: list = []
        self.excluded_services: list = []
        self.proxy = (proxy_host, proxy_port)
        self.delay = delay
        self.max_pages = max_pages
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.session = requests.Session()
        # socks5h, not socks5: the "h" makes the proxy resolve the hostname.
        url = "socks5h://%s:%d" % (proxy_host, proxy_port)
        self.session.proxies = {"http": url, "https": url}
        self.session.headers.update({
            # Identify honestly. Impersonating Tor Browser here would be both
            # dishonest and useless: the fingerprint we care about belongs to
            # the server, not to us.
            "User-Agent": "ANEKANTA-collector/1.0 (research; contact operator)",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en",
        })
        self._budget_bytes = 0
        self._fetched = 0
        self._last = 0.0
        # Per-service budgets, reset at the start of each service. The
        # lifetime budgets above are the right shape for crawling one target,
        # and exactly the wrong shape for sweeping many: without these, a
        # link-heavy wiki near the front of the queue consumes the entire
        # allowance and every service behind it is recorded as unreachable
        # when in fact it was never contacted.
        self.max_pages_per_service = 0        # 0 = no per-service limit
        self._service_fetched = 0
        self._service_bytes = 0

    # -- primitives ---------------------------------------------------------

    def _throttle(self) -> None:
        gap = time.time() - self._last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last = time.time()

    def get(self, url: str):
        if self._fetched >= self.max_pages or self._budget_bytes >= self.max_bytes:
            return None
        if (self.max_pages_per_service
                and self._service_fetched >= self.max_pages_per_service):
            return None
        self._throttle()
        try:
            r = self.session.get(url, timeout=self.timeout, allow_redirects=True,
                                 stream=True)
            body = r.raw.read(1_500_000, decode_content=True)
            r._content = body
            self._fetched += 1
            self._budget_bytes += len(body)
            self._service_fetched += 1
            self._service_bytes += len(body)
            return r
        except Exception:
            return None

    def check_reachable(self) -> tuple:
        """Confirm Tor is actually up before doing anything else."""
        try:
            import socks
            s = socks.socksocket()
            s.settimeout(10)
            s.connect(self.proxy)
            s.close()
            return True, "SOCKS proxy reachable at %s:%d" % self.proxy
        except Exception as exc:
            return False, ("no Tor SOCKS proxy at %s:%d (%s). Start it with "
                           "`docker compose up -d` in onionlab/."
                           % (self.proxy[0], self.proxy[1], type(exc).__name__))

    # -- crawl --------------------------------------------------------------

    def crawl_service(self, onion: str, site_label: str | None = None) -> CrawlResult:
        self._service_fetched = 0
        self._service_bytes = 0
        onion = onion.strip().replace("http://", "").replace("https://", "").strip("/")
        base = "http://%s" % onion
        site = site_label or onion[:16]
        fpr = ServiceFingerprint(onion=onion)
        result = CrawlResult(onion=onion, fingerprint=fpr)

        root = self.get(base + "/")
        if root is None:
            result.notes.append("root page unreachable")
            return result
        html = root.content.decode("utf-8", "replace")

        # If the landing page trips the gate, the whole service is abandoned:
        # nothing is parsed, nothing is stored, and no further page is fetched.
        # Only the address and the fact of the exclusion are retained.
        verdict = self.safety.check_page(html)
        if not verdict.allowed:
            self.excluded_services.append({"onion": onion,
                                           "reason": verdict.reason})
            result.excluded_services.append({"onion": onion,
                                             "reason": verdict.reason})
            result.notes.append("service excluded by the content safety gate")
            return result

        # robots.txt, honoured
        disallow: list = []
        rb = self.get(base + "/robots.txt")
        if rb is not None and rb.status_code == 200:
            for line in rb.content.decode("utf-8", "replace").splitlines():
                if line.lower().startswith("disallow:"):
                    p = line.split(":", 1)[1].strip()
                    if p:
                        disallow.append(p)

        favicon = None
        fv = self.get(base + "/favicon.ico")
        if fv is not None and fv.status_code == 200 and fv.content:
            favicon = fv.content

        err = self.get(base + "/anekanta-probe-404")
        error_html = err.content.decode("utf-8", "replace") if err is not None else None

        tls = probe_tls(onion, 443, proxy=self.proxy)

        fpr = fingerprint_service(self.session, onion, html, root.headers,
                                  favicon, error_html, None, tls)
        result.fingerprint = fpr

        # discover on-site links only
        links = []
        for href in re.findall(r'href\s*=\s*["\']([^"\']{1,300})["\']', html):
            u = urljoin(base + "/", href)
            p = urlparse(u)
            if p.scheme not in ("http", "https") or not p.netloc.endswith(".onion"):
                continue
            if p.netloc != onion:
                continue                      # never wander to another service
            if any(p.path.startswith(d) for d in disallow):
                continue
            if u not in links:
                links.append(u)

        pages = [(base + "/", html)]
        for u in links:
            r = self.get(u)
            if r is None:
                break
            if r.status_code == 200 and "html" in r.headers.get("Content-Type", ""):
                body = r.content.decode("utf-8", "replace")
                page_verdict = self.safety.check_page(body)
                if not page_verdict.allowed:
                    self.excluded_pages.append({"url": u,
                                                "reason": page_verdict.reason})
                    result.excluded_pages.append({"url": u,
                                                  "reason": page_verdict.reason})
                    continue
                pages.append((u, body))

        result.pages_fetched = self._service_fetched
        result.bytes_fetched = self._service_bytes
        result.onions = [onion]
        result.fingerprints = {onion: fpr}
        self._extract(result, pages, site, fpr)

        # Clear-web mention harvesting (Wangchuk & Rathod). Runs over every
        # page, with the profile attribution attached where the page is one.
        url_to_persona = {}
        for p in result.personas:
            url_to_persona["http://%s/vendor/%s" % (onion, p.handle)] = p
        for url, html in pages:
            persona = url_to_persona.get(url)
            result.mentions.extend(osint_mentions.extract(
                html, onion=onion, url=url,
                persona_id=persona.persona_id if persona else "",
                handle=persona.handle if persona else ""))

        # Onion addresses referenced by this service, for the frontier
        refs = sanitise_onions(
            "%s.onion" % m for _u, h in pages for m in ONION_RE.findall(h))
        result.references = [o for o in refs if o != onion]
        return result

    def crawl(self, seeds, site_label: str | None = None,
              max_onions: int = 4) -> CrawlResult:
        """Crawl a seed address and follow the onion links it exposes.

        This is the recursive stage of the paper's framework: their crawler
        took 4,426 sanitised seed addresses and fetched 9,135 further unique
        onion addresses from the pages. The frontier is bounded here because a
        demonstration should not wander, but the shape is the same -- seed,
        fetch, extract addresses, sanitise, enqueue.
        """
        if isinstance(seeds, str):
            seeds = [seeds]
        # accept raw strings or Discovered records from the discovery stage
        seeds = [getattr(x, "onion", x) for x in seeds]
        frontier = sanitise_onions(seeds)
        if not frontier:
            merged = CrawlResult(onion="", fingerprint=ServiceFingerprint(onion=""))
            merged.notes.append("no valid v3 onion address in the seed list")
            return merged

        visited, results = [], []
        discovered_from: dict = {}
        while frontier and len(visited) < max_onions:
            target = frontier.pop(0)
            if target in visited:
                continue
            visited.append(target)
            # per-service label: the dossier has to name which
            # marketplace each persona was found on
            one = self.crawl_service(target, site_label=None)
            results.append(one)
            for ref in getattr(one, "references", []):
                if ref not in visited and ref not in frontier:
                    frontier.append(ref)
                    discovered_from.setdefault(ref, target)

        if not results:
            return CrawlResult(onion="", fingerprint=ServiceFingerprint(onion=""))

        merged = CrawlResult(onion=results[0].onion,
                             fingerprint=results[0].fingerprint)
        for one in results:
            merged.personas.extend(one.personas)
            merged.posts.extend(one.posts)
            merged.mentions.extend(one.mentions)
            merged.notes.extend(one.notes)
            merged.onions.extend(one.onions)
            merged.fingerprints.update(one.fingerprints)
            merged.excluded_pages.extend(one.excluded_pages)
            merged.excluded_services.extend(one.excluded_services)
            merged.pages_fetched = self._fetched
            merged.bytes_fetched = self._budget_bytes
        merged.discovered_from = discovered_from

        # Context setting happens once, across the whole crawl, because the
        # ubiquity signal needs to see every page before it can tell an
        # individual's address from site furniture.
        osint_context.score_all(merged.mentions)
        return merged

    # -- extraction ---------------------------------------------------------

    def _extract(self, result: CrawlResult, pages: list, site: str,
                 fpr: ServiceFingerprint) -> None:
        """Build one Persona per profile page, with its posts and artefacts."""
        infra = fpr.as_infra_dict()
        now = datetime.now(timezone.utc)

        for url, html in pages:
            path = urlparse(url).path
            m = re.match(r"^/vendor/([A-Za-z0-9._-]{1,64})$", path)
            if not m:
                continue
            handle = m.group(1)
            text = strip_tags(html)

            pgp_blocks = PGP_RE.findall(html)
            fprints = FPR_RE.findall(text)
            wallets = sorted(set(BTC_RE.findall(text)) | set(XMR_RE.findall(text)))
            contacts = sorted(set(c.lower() for c in CONTACT_RE.findall(text)))

            # timestamps carry the circadian signal; they are the reason the
            # temporal engine works at all on live data
            stamps = []
            for d, t in TIME_RE.findall(html):
                try:
                    stamps.append(datetime.fromisoformat("%sT%s:00+00:00" % (d, t)))
                except ValueError:
                    pass

            persona = Persona(
                persona_id="%s:%s" % (result.onion[:12], handle),
                handle=handle,
                site=site,
                first_seen=min(stamps) if stamps else now,
                last_seen=max(stamps) if stamps else now,
                pgp_fingerprint=(fprints[0] if fprints else None),
                pgp_uid=handle,
                pgp_created=None,
                btc_addresses=wallets,
                onion_services=[result.onion],
                infra_fingerprints=dict(infra),
                contact_handles=contacts,
                true_actor=None,          # unknown on live data, by definition
            )
            if pgp_blocks:
                persona.pgp_uid = "%s <key published>" % handle

            # posts: table rows carrying a timestamp and a message
            rows = re.findall(r"<tr>(.*?)</tr>", html, re.S)
            n = 0
            for row in rows:
                cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
                if len(cells) < 2:
                    continue
                stamp = TIME_RE.search(strip_tags(cells[0]))
                if not stamp:
                    continue
                body = strip_tags(cells[-1])
                if len(body) < 12:
                    continue
                try:
                    ts = datetime.fromisoformat(
                        "%sT%s:00+00:00" % (stamp.group(1), stamp.group(2)))
                except ValueError:
                    continue
                result.posts.append(Post(
                    post_id="%s-%04d" % (persona.persona_id, n),
                    persona_id=persona.persona_id, site=site,
                    timestamp=ts, text=body))
                n += 1

            result.personas.append(persona)

        if not result.personas:
            result.notes.append("no profile pages matched the extraction pattern")
