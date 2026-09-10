"""Onion discovery by keyword, and the safety gate that guards it.

Adapted from **darkdump** by Josh Schiavone (https://github.com/josh0xA/darkdump),
MIT licensed. Darkdump's contribution is the piece ANEKANTA was missing: until
now the crawler needed a `.onion` address handed to it, which is fine for a lab
and useless for an investigation. Darkdump queries the dark-web search engines
that index hidden services and returns addresses for a keyword, which is
precisely the "seed URL collection" stage of the Wangchuk & Rathod framework --
the stage this project previously satisfied by having the operator paste an
address in by hand.

What is taken from darkdump:
  * the set of search engines and their query endpoints;
  * the decision to check every result against Ahmia's blacklist, which is the
    single most important safety property of the tool.

What is done differently, and why:
  * **Everything goes through Tor, including the clearnet endpoints.** Darkdump
    can query ahmia.fi and tordex.cc directly. Fetching a dark-web search engine
    from your own address, over your own line, is a poor idea for the person
    running the tool: it is a plain-text record that you searched for that term
    at that time. The onion endpoints are preferred and the clearnet ones are
    routed over Tor exits, so `--clearnet` has to be asked for explicitly.
  * **The blacklist fails closed.** Darkdump filters when it can reach the
    list. Here, if the blacklist cannot be fetched, discovery aborts. A filter
    that silently stops filtering is worse than no filter, because the operator
    still believes they are protected.
  * **A second, local safety gate** (`safety.py`) runs over titles, snippets
    and fetched pages. Ahmia's blacklist covers what Ahmia knows about; the
    other engines have weaker or no filtering, and this project has no business
    fetching, storing or displaying abuse material under any circumstances.

Discovery returns addresses and search-result metadata only. Deciding whether
to then crawl a given service is a separate, deliberate step.
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from urllib.parse import quote_plus, urlparse

from .safety import SafetyGate

ONION_RE = re.compile(r"\b([a-z2-7]{56})\.onion\b", re.I)

# Endpoints as used by darkdump. Each engine has an onion address (preferred --
# the query never leaves the Tor network) and, where one exists, a clearnet
# address used only when the operator explicitly asks for it.
SEARCH_ENGINES = {
    "ahmia": {
        "onion": "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion"
                 "/search/?q={query}",
        "clearnet": "https://ahmia.fi/search/?q={query}",
        "host": "juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion",
        "searchable": False,
        "note": "search is JavaScript-only as of 2026 and returns no results to "
                "an HTTP client; its BLACKLIST is still used, and is mandatory",
    },
    "tordex": {
        "onion": "http://tordexpmg4xy32rfp4ovnz7zq5ujoejwq2u26uxxtkscgo5u3losmeid.onion"
                 "/search?query={query}",
        "clearnet": "https://tordex.cc/search?query={query}",
        "host": "tordexpmg4xy32rfp4ovnz7zq5ujoejwq2u26uxxtkscgo5u3losmeid.onion",
        "searchable": True,
        "note": "broad index, no abuse filtering of its own",
    },
    "tor66": {
        "onion": "http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion"
                 "/search?q={query}&sorttype=rel",
        "clearnet": None,
        "host": "tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion",
        "searchable": True,
        "note": "broad index, no abuse filtering of its own",
    },
    "onionland": {
        "onion": "http://3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion"
                 "/search?q={query}&page=1",
        "clearnet": None,
        "host": "3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion",
        "searchable": True,
        "note": "broad index, no abuse filtering of its own",
    },
}

# Ahmia was darkdump's default and would be the natural choice here: it is the
# one index with its own abuse filtering, run by a named researcher. It is not
# the default any more because its search front end became JavaScript-only and
# now answers an HTTP client with "we have not deployed a non-JavaScript
# version of Ahmia yet" and no results. Rather than silently returning nothing,
# `search()` detects that page and says so.
#
# Losing Ahmia's *search* does not lose Ahmia's *filtering*: its blacklist is
# applied to results from every engine, exactly as darkdump does, so switching
# the default to an unfiltered index does not weaken the safety property.
DEFAULT_ENGINE = "tordex"

SEARCHABLE_ENGINES = [name for name, spec in SEARCH_ENGINES.items()
                      if spec.get("searchable")]

# Ahmia's polite refusal, used to distinguish "this engine cannot be scraped"
# from "this query had no results".
JS_GATE_MARKERS = ("not deployd non-javascript", "not deployed non-javascript",
                   "enable javascript", "requires javascript")

BLACKLIST_URL = "https://ahmia.fi/blacklist/banned/"
BLACKLIST_MAX_AGE = 6 * 3600        # seconds


@dataclass
class Discovered:
    """One search hit. Metadata only -- nothing has been fetched from it yet."""

    onion: str
    title: str = ""
    snippet: str = ""
    engine: str = ""
    rank: int = 0
    discovered_at: str = ""
    excluded: bool = False
    exclusion_reason: str = ""

    def to_json(self) -> dict:
        return asdict(self)


class AhmiaBlacklist:
    """Ahmia's list of MD5-hashed onion hostnames known to host abuse material.

    Fails closed. If the list cannot be retrieved, `load()` raises and discovery
    refuses to run: a filter that quietly stops filtering leaves the operator
    believing they are protected while they are not, which is the worst of the
    three possible states.
    """

    def __init__(self) -> None:
        self._hashes: set = set()
        self._loaded_at = 0.0

    @property
    def size(self) -> int:
        return len(self._hashes)

    def load(self, session, force: bool = False) -> int:
        if not force and self._hashes and (time.time() - self._loaded_at) < BLACKLIST_MAX_AGE:
            return len(self._hashes)
        response = session.get(BLACKLIST_URL, timeout=60)
        response.raise_for_status()
        hashes = {line.strip().lower() for line in response.text.splitlines()
                  if re.fullmatch(r"[0-9a-fA-F]{32}", line.strip())}
        if not hashes:
            raise RuntimeError("Ahmia blacklist fetched but contained no hashes")
        self._hashes = hashes
        self._loaded_at = time.time()
        return len(hashes)

    def is_banned(self, onion: str) -> bool:
        host = onion.strip().lower()
        host = host.replace("http://", "").replace("https://", "").strip("/")
        host = host.split("/")[0].split(":")[0]
        return hashlib.md5(host.encode()).hexdigest() in self._hashes


class OnionDiscovery:
    """Keyword search across dark-web indexes, filtered before anything is
    fetched from the results."""

    def __init__(self, session, safety: SafetyGate | None = None,
                 delay: float = 2.0) -> None:
        self.session = session
        self.safety = safety or SafetyGate()
        self.blacklist = AhmiaBlacklist()
        self.delay = delay
        self._last = 0.0
        self.stats: dict = {"queried": 0, "raw_hits": 0, "blacklisted": 0,
                            "safety_excluded": 0, "kept": 0}
        self.notes: list = []

    def _throttle(self) -> None:
        gap = time.time() - self._last
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self._last = time.time()

    def prepare(self) -> dict:
        """Load the blacklist. Must succeed before any search runs."""
        n = self.blacklist.load(self.session)
        return {"blacklist_hashes": n, "source": BLACKLIST_URL}

    def search(self, query: str, engine: str = DEFAULT_ENGINE, limit: int = 20,
               clearnet: bool = False) -> list:
        if engine not in SEARCH_ENGINES:
            raise ValueError("unknown engine %r; choose from %s"
                             % (engine, ", ".join(SEARCH_ENGINES)))
        if not self.blacklist.size:
            raise RuntimeError("blacklist not loaded; call prepare() first")

        spec = SEARCH_ENGINES[engine]
        template = spec["clearnet"] if (clearnet and spec["clearnet"]) else spec["onion"]
        url = template.format(query=quote_plus(query))

        self._throttle()
        self.stats["queried"] += 1
        try:
            response = self.session.get(url, timeout=90)
            html = response.text
        except Exception as exc:
            self.notes.append("%s: request failed (%s)"
                              % (engine, type(exc).__name__))
            return []

        low = html.lower()
        if any(marker in low for marker in JS_GATE_MARKERS):
            self.notes.append(
                "%s: front end is JavaScript-only and returned no results to an "
                "HTTP client; use another engine (its blacklist is still in use)"
                % engine)
            return []

        results = self._parse(html, engine)
        # An index links to itself on every page. Its own address is not a
        # search result and would otherwise be the top hit for every query.
        own = spec.get("host")
        results = [r for r in results if r.onion != own]
        self.stats["raw_hits"] += len(results)

        kept: list = []
        for i, hit in enumerate(results):
            hit.rank = i + 1
            hit.discovered_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

            if self.blacklist.is_banned(hit.onion):
                hit.excluded = True
                hit.exclusion_reason = "on Ahmia's abuse blacklist"
                self.stats["blacklisted"] += 1
                continue

            verdict = self.safety.check_text("%s %s" % (hit.title, hit.snippet))
            if not verdict.allowed:
                hit.excluded = True
                hit.exclusion_reason = verdict.reason
                self.stats["safety_excluded"] += 1
                continue

            kept.append(hit)
            self.stats["kept"] += 1
            if len(kept) >= limit:
                break
        return kept

    # -- parsing ------------------------------------------------------------

    def _parse(self, html: str, engine: str) -> list:
        """Pull (onion, title, snippet) out of a results page.

        Deliberately structure-agnostic: it locates every v3 address in the
        document and takes the nearest preceding text as the title. Search
        engines change their markup often, and a parser written against the
        current HTML of four different engines would break constantly and
        silently. Returning slightly rougher titles is a far better failure
        mode than returning nothing.
        """
        text_only = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                           flags=re.S | re.I)
        out: list = []
        seen: set = set()

        for m in ONION_RE.finditer(text_only):
            onion = (m.group(1) + ".onion").lower()
            if onion in seen:
                continue
            seen.add(onion)

            window = text_only[max(0, m.start() - 600):m.start()]
            titles = re.findall(r"<(?:h\d|a|b|strong)[^>]*>(.*?)</(?:h\d|a|b|strong)>",
                                window, re.S | re.I)
            title = ""
            for candidate in reversed(titles):
                candidate = re.sub(r"<[^>]+>", " ", candidate)
                candidate = re.sub(r"\s+", " ", candidate).strip()
                if len(candidate) > 3 and ".onion" not in candidate:
                    title = candidate[:160]
                    break

            after = text_only[m.end():m.end() + 500]
            snippet = re.sub(r"<[^>]+>", " ", after)
            snippet = re.sub(r"\s+", " ", snippet).strip()[:300]

            out.append(Discovered(onion=onion, title=title, snippet=snippet,
                                  engine=engine))
        return out

    def multi_search(self, queries: list, engines: list | None = None,
                     per_query: int = 10, clearnet: bool = False) -> dict:
        """Run several queries across several engines and merge.

        Which query and which engine surfaced an address is retained, because
        an address returned by three independent indexes for the same term is a
        different kind of observation from one returned once.
        """
        engines = engines or [DEFAULT_ENGINE]
        found: dict = {}
        for engine in engines:
            for q in queries:
                for hit in self.search(q, engine=engine, limit=per_query,
                                       clearnet=clearnet):
                    entry = found.setdefault(hit.onion, {
                        "hit": hit, "queries": [], "engines": []})
                    if q not in entry["queries"]:
                        entry["queries"].append(q)
                    if engine not in entry["engines"]:
                        entry["engines"].append(engine)
        return found
