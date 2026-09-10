"""Content safety gate.

A tool that searches dark-web indexes by keyword will, sooner or later, be
handed a result pointing at material that is illegal to fetch, illegal to
store, and illegal to display. That is not a hypothetical risk to manage
politely -- it is the one failure this project must not have.

Two layers sit in front of everything:

  1. **Ahmia's blacklist** (in `discovery.py`) -- an authoritative, maintained
     list of MD5-hashed onion hostnames. It is the primary filter and it fails
     closed: if it cannot be fetched, discovery does not run.

  2. **This gate**, which is the backstop. Ahmia's list covers what Ahmia knows
     about, and three of the four supported engines apply no filtering of their
     own. So titles, snippets, and then whole fetched pages are checked here
     before anything is parsed, scored, stored or rendered.

How the classifier works, and why it is built this way
------------------------------------------------------
The obvious implementation is a denylist of the coded terms used to advertise
abuse material. It would work, and it would also mean this repository contains
a ready-made list of search terms for finding that material. That is a bad
trade, and it is avoidable.

Instead the gate looks for a **conjunction**: a token indicating a minor
appearing close to a token indicating sexual content. Neither vocabulary is
harmful on its own -- "child", "teen", "school" are ordinary words, and so are
the explicit ones -- and neither list is usable as a search query. It is their
co-occurrence within a short window that carries the signal. This is a standard
moderation technique and it degrades sensibly: a paediatric health forum trips
one list, an adult site trips the other, and neither is blocked.

What happens on a trip
----------------------
The page is discarded whole. Not truncated, not redacted, not summarised --
discarded, before mention extraction or fingerprinting runs. What is retained
is the onion address and the fact of the exclusion, so the run can be audited
and the address can be reported, and nothing else. Crawl statistics count it.

What this gate is NOT for
-------------------------
It does not filter drugs, weapons, fraud, malware or extremist content. Those
are the subject matter of the investigations this tool exists to support, and
filtering them would defeat its purpose. The distinction being drawn is
narrow and deliberate: material whose mere retrieval is a criminal offence and
which no investigative purpose here requires.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Tokens indicating a minor. Ordinary words; harmless alone.
MINOR_TOKENS = {
    "child", "children", "childs", "kid", "kids", "minor", "minors",
    "preteen", "pre-teen", "prepubescent", "toddler", "infant", "baby",
    "boy", "boys", "girl", "girls", "juvenile", "underage", "under-age",
    "schoolgirl", "schoolboy", "teen", "teens", "teenage", "teenager",
    "loli", "shota", "jailbait",
}

# Tokens indicating sexual content. Also ordinary words in their own contexts.
SEXUAL_TOKENS = {
    "porn", "porno", "pornography", "xxx", "nude", "nudes", "nudity", "naked",
    "sex", "sexual", "erotic", "erotica", "hardcore", "explicit", "fetish",
    "incest", "rape", "molest", "molestation", "abuse", "pedo", "paedo",
    "pedophile", "paedophile", "cp", "csam", "hurtcore",
}

# Terms that are abuse-specific regardless of what sits near them. Kept short
# and non-productive as search queries: these are the acronyms used by the
# filtering community itself, not the coded advertising vocabulary.
STANDALONE_TOKENS = {"csam", "hurtcore", "pedo", "paedo", "pedophile",
                     "paedophile", "loli", "shota", "jailbait"}

# How close the two vocabularies must appear, in tokens, to count as a
# conjunction. Wide enough to catch a title and its own description; narrow
# enough that an unrelated mention elsewhere on a long page does not trip it.
PROXIMITY = 8

TOKEN_RE = re.compile(r"[a-z0-9\-]+")
TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)


@dataclass
class Verdict:
    allowed: bool
    reason: str = ""
    category: str = ""

    def __bool__(self) -> bool:
        return self.allowed


ALLOWED = Verdict(True)


class SafetyGate:
    def __init__(self, proximity: int = PROXIMITY) -> None:
        self.proximity = proximity
        self.stats: dict = {"checked": 0, "blocked": 0}

    def check_text(self, text: str) -> Verdict:
        """Classify a title, snippet, or page. Cheap enough to run on everything."""
        self.stats["checked"] += 1
        if not text:
            return ALLOWED
        tokens = TOKEN_RE.findall(text.lower())
        if not tokens:
            return ALLOWED

        for i, tok in enumerate(tokens):
            if tok in STANDALONE_TOKENS:
                self.stats["blocked"] += 1
                # The matched token is deliberately not echoed into the reason:
                # the audit trail should record that an exclusion happened and
                # why, without reproducing the vocabulary in logs and reports.
                return Verdict(False,
                               "excluded by the content safety gate "
                               "(unambiguous abuse indicator)",
                               "csam")

            if tok in MINOR_TOKENS:
                window = tokens[max(0, i - self.proximity):i + self.proximity + 1]
                if any(w in SEXUAL_TOKENS for w in window):
                    self.stats["blocked"] += 1
                    return Verdict(False,
                                   "excluded by the content safety gate "
                                   "(minor and sexual-content indicators "
                                   "co-occurring)",
                                   "csam")
        return ALLOWED

    def check_page(self, html: str) -> Verdict:
        """Check a fetched page before anything is extracted from it.

        Runs on the visible text with markup stripped, because the signal is in
        what a visitor reads, and because leaving the tags in lets long
        attribute values push the two vocabularies apart and defeat the
        proximity rule.
        """
        text = TAGS.sub(" ", html or "")
        return self.check_text(text)

    def summary(self) -> dict:
        return {
            "checked": self.stats["checked"],
            "blocked": self.stats["blocked"],
            "policy": ("hard exclusion of material whose retrieval is itself "
                       "an offence; no filtering of the subject matter this "
                       "tool exists to investigate"),
        }
