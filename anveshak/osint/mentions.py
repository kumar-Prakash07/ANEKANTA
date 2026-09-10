"""Clear-web mention extraction, with provenance.

This implements the harvesting half of the Dark2Clear framework in Wangchuk &
Rathod (2023), "Opensource intelligence and dark web user de-anonymisation".

The premise, which their Silk Road example makes concrete: dark web operators
leak clear-web identifiers through carelessness. Ross Ulbricht promoted his
market as "altoid" and, in a separate post, asked for help using
rossulbricht@gmail.com. One clear-web mention, on a page where it did not
belong, ended the case. So the harvest looks for identifiers that only make
sense on the clear web -- addresses, domains, messaging handles, payment
identifiers -- and records exactly where each one was found.

Provenance is not an extra
--------------------------
The paper is emphatic that logging *where* each identifier came from is what
makes the harvest usable, and it is right for a reason worth stating: an e-mail
address with no context is not a lead. `abuse@` in a footer and a vendor's
private mailbox in a "message me directly for bulk orders" paragraph are the
same regex match and completely different objects. Every Mention therefore
carries its URL, its page, the account whose profile it sat on, and the text
surrounding it, so `context.py` can tell those two apart and so an analyst can
go back and read the page for themselves.

Forum thread extension
----------------------
Markets are not the only source. BreachForums / LeakForum / DarkForum-style
boards carry at least as many operational identifiers -- often more, because
posters are writing to an audience rather than filling a profile form, and their
guard is lower. The extra provenance a forum post carries (thread_id, post_id,
author persona, and structural position in the thread) flows through the same
four-signal scoring as before, but with forum-specific structural positions:
original post, quoted reply, signature block, and moderator/admin boilerplate.
A quoted reply scores lower than an original post because the identifier may
belong to whoever is being quoted, not the poster -- that distinction is
preserved end-to-end.

Beyond the paper
----------------
The paper harvests e-mail addresses and clear-web domains. Those were the
high-value identifiers in 2023 and they still are, but operators now leak
through messaging handles (Telegram, Session, Jabber, Wickr, Threema, Tox) and
payment identifiers at least as often, so those are extracted too. The
extraction is otherwise the same idea: find the thing that has to be resolvable
outside Tor to be useful, because that is the thing that can be followed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Forum structural positions.  These are not a new scoring axis; they map onto
# the existing block/in_footer fields consumed by context.py, extended with a
# forum_position field that the forum-specific signal branch reads.
FORUM_POSITIONS = frozenset({
    "original_post",   # the OP in a thread -- highest attribution weight
    "reply_post",      # a reply by the same author (not quoting) -- normal weight
    "quoted_reply",    # inside a quote block -- lower, identifier may belong to quotee
    "signature",       # sig block below the post body -- structural boilerplate position
    "mod_boilerplate", # moderator/admin/staff notice -- belongs to the platform
    "unknown",         # cannot determine position
})

EMAIL_RE = re.compile(
    r"\b([A-Za-z0-9](?:[A-Za-z0-9._%+\-]{0,62}[A-Za-z0-9])?"
    r"@(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24})\b")

# A bare domain. Deliberately anchored on a known-ish TLD shape and filtered
# afterwards, because an unanchored pattern matches filenames, version strings
# and half the JavaScript on a page.
DOMAIN_RE = re.compile(
    r"\b((?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+"
    r"(?:com|net|org|io|co|ru|de|uk|info|biz|xyz|shop|site|top|cc|ch|nl|se|is"
    r"|me|to|su|onion|example|test|invalid|localhost))\b", re.I)

# The bare "@handle" branch needs a negative lookbehind. Without one it matches
# the "@" inside every e-mail address on the page and reports the mail provider
# as a Telegram username -- "telegram: gmail", "telegram: protonmail". A
# false positive of that shape is worse than a miss, because it looks like a
# finding and an analyst will spend time on it.
TELEGRAM_RE = re.compile(
    r"(?:t\.me/|telegram\s*[:=]?\s*@?|(?<![A-Za-z0-9._%+\-])@)"
    r"([A-Za-z][A-Za-z0-9_]{4,31})\b")

# Second guard: a "username" that is actually a mail provider is not one.
NOT_USERNAMES = {
    "gmail", "googlemail", "yahoo", "outlook", "hotmail", "protonmail",
    "proton", "tutanota", "yandex", "icloud", "example", "mailbox",
    "onionmail", "riseup", "danwin1210", "elude", "secmail", "dnmx",
}
SESSION_RE = re.compile(r"\b(0[0-9a-f]{65})\b")

# Tox ID: 76 hex characters (64-char public key + 4-char nospam + 4-char
# checksum = 72 hex, sometimes shown as 76 or 64 depending on client).
# The most commonly shared form is 76 hex characters.
TOX_RE = re.compile(
    r"(?:tox\s*(?:id)?\s*[:=]?\s*)"
    r"([0-9A-Fa-f]{76})"
    r"|(?<![0-9A-Fa-f])([0-9A-Fa-f]{76})(?![0-9A-Fa-f])",
    re.I,
)
WICKR_RE = re.compile(r"wickr(?:\s*(?:me|id))?\s*[:=]?\s*@?([A-Za-z0-9_\-]{3,32})\b", re.I)
THREEMA_RE = re.compile(r"threema\s*[:=]?\s*([A-Z0-9]{8})\b", re.I)
ICQ_RE = re.compile(r"\bicq\s*[:=#]?\s*(\d{6,12})\b", re.I)
JABBER_RE = re.compile(
    r"\b([A-Za-z0-9._\-]{2,32}@(?:xmpp\.[A-Za-z0-9.\-]+|jabber\.[A-Za-z0-9.\-]+"
    r"|exploit\.im|conversations\.im|riseup\.net|cock\.li))\b", re.I)

BTC_RE = re.compile(r"\b([13][a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-z0-9]{25,62})\b")
XMR_RE = re.compile(r"\b([48][0-9AB][1-9A-HJ-NP-Za-km-z]{93})\b")
ETH_RE = re.compile(r"\b(0x[a-fA-F0-9]{40})\b")

PGP_FPR_RE = re.compile(r"\b([0-9A-Fa-f]{40})\b")
PAYPAL_RE = re.compile(r"paypal\.me/([A-Za-z0-9_\-]{3,32})\b", re.I)

SOCIAL_RE = [
    ("twitter", re.compile(r"(?:twitter\.com|x\.com)/([A-Za-z0-9_]{2,15})\b", re.I)),
    ("instagram", re.compile(r"instagram\.com/([A-Za-z0-9_.]{2,30})\b", re.I)),
    ("github", re.compile(r"github\.com/([A-Za-z0-9\-]{1,39})\b", re.I)),
    ("keybase", re.compile(r"keybase\.io/([A-Za-z0-9_]{2,32})\b", re.I)),
    ("bitcointalk", re.compile(r"bitcointalk\.org/index\.php\?action=profile;u=(\d+)", re.I)),
    ("reddit", re.compile(r"reddit\.com/u(?:ser)?/([A-Za-z0-9_\-]{3,20})\b", re.I)),
]

TAGS = re.compile(r"<(script|style)[^>]*>.*?</\1>|<[^>]+>", re.S | re.I)

# Domains that appear on every page and identify nothing. Kept explicit rather
# than learned, because the cost of a wrong entry here is a missed lead.
NOISE_DOMAINS = {
    "example.com", "example.net", "example.org", "www.w3.org", "schema.org",
    "torproject.org", "torproject.example", "gnupg.org", "localhost",
    "127.0.0.1", "github.io", "gstatic.com", "googleapis.com", "jquery.com",
}

# Free/anonymous providers. Not filtered -- an address at one is still a lead --
# but weighted lower, because the account behind it was created to be
# disposable and rarely connects to anything else.
PRIVACY_PROVIDERS = {
    "protonmail.com", "protonmail.example", "proton.me", "tutanota.com",
    "tutanota.example", "tuta.io", "cock.li", "danwin1210.de", "elude.in",
    "onionmail.org", "mail2tor.com", "riseup.net", "secmail.pro", "dnmx.org",
}

# Mainstream providers. The paper's Silk Road example turns on exactly this:
# a gmail address ties into a real-name ecosystem -- recovery details, linked
# services, breach corpora -- in a way a throwaway anonymous mailbox does not.
MAINSTREAM_PROVIDERS = {
    "gmail.com", "gmail.example", "googlemail.com", "yahoo.com", "outlook.com",
    "hotmail.com", "live.com", "aol.com", "icloud.com", "yandex.com",
    "yandex.ru", "yandex.example", "mail.ru", "gmx.com", "zoho.com",
}

CONTEXT_WINDOW = 160

# Block-level elements. Context is taken from the enclosing block rather than
# from a fixed character window, because a window does not respect the page's
# structure: on a compact page the footer falls inside the window of a vendor's
# "message me directly" paragraph and inherits its solicitation score, which
# promoted `abuse@` addresses into the high band. A human reading the page
# would never make that mistake, because they can see the two are different
# sections.
BLOCK_SPLIT = re.compile(
    r"</?(?:div|p|li|tr|td|th|section|article|header|footer|nav|aside|"
    r"h[1-6]|pre|blockquote|table|ul|ol|form|main)\b[^>]*>", re.I)

# Sections that are boilerplate by position, whatever they contain.
FOOTER_HINT = re.compile(r"<\s*(footer|nav|aside)\b", re.I)


@dataclass
class Mention:
    """One clear-web identifier, and everything needed to judge it."""

    kind: str                 # email | domain | telegram | jabber | tox | ...
    value: str
    onion: str = ""
    url: str = ""
    persona_id: str = ""      # profile page it sat on, if any
    handle: str = ""          # that account's handle
    context: str = ""         # the enclosing block, for context setting
    block: str = ""           # which kind of block it sat in
    in_footer: bool = False   # structurally boilerplate

    # Forum thread provenance (empty string / "unknown" when not from a forum)
    thread_id: str = ""       # the thread this post belongs to
    post_id: str = ""         # the individual post within the thread
    author_persona: str = ""  # persona handle of the post author (may differ
                              # from handle when the identifier is in a quote)
    forum_position: str = "unknown"  # one of FORUM_POSITIONS

    offset: int = 0
    provider: str = ""        # for e-mail: the domain
    provider_class: str = ""  # mainstream | privacy | other

    # populated by context.py
    category: str = ""
    priority: float = 0.0
    reasons: list = field(default_factory=list)

    @property
    def key(self) -> tuple:
        return (self.kind, self.value.lower())

    def to_json(self) -> dict:
        d = asdict(self)
        d["priority"] = round(self.priority, 3)
        return d


def strip_markup(html: str) -> str:
    """Remove tags, and drop script/style bodies entirely.

    Script bodies are removed rather than flattened because they are full of
    strings that look exactly like domains and are never operator leaks.
    """
    return re.sub(r"[ \t]+", " ", TAGS.sub(" ", html))


def _classify_provider(domain: str) -> str:
    d = domain.lower()
    if d in MAINSTREAM_PROVIDERS:
        return "mainstream"
    if d in PRIVACY_PROVIDERS:
        return "privacy"
    return "other"


def _window(text: str, start: int, end: int) -> str:
    lo = max(0, start - CONTEXT_WINDOW)
    hi = min(len(text), end + CONTEXT_WINDOW)
    return re.sub(r"\s+", " ", text[lo:hi]).strip()


def _segment(html: str) -> list:
    """Split a page into blocks, flagging the ones that are structurally
    boilerplate. Returns [(text, in_footer)]."""
    # remove script/style bodies before splitting, so their contents cannot
    # leak into a neighbouring block's context
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                     flags=re.S | re.I)
    marks = [(m.start(), bool(FOOTER_HINT.match(m.group(0))))
             for m in BLOCK_SPLIT.finditer(cleaned)]
    if not marks:
        return [(re.sub(r"[ \t]+", " ", TAGS.sub(" ", cleaned)), False)]

    blocks, footer_depth = [], 0
    bounds = [m[0] for m in marks] + [len(cleaned)]
    for i, start in enumerate(bounds[:-1]):
        chunk = cleaned[start:bounds[i + 1]]
        opening = BLOCK_SPLIT.match(chunk)
        tag = opening.group(0) if opening else ""
        if FOOTER_HINT.match(tag):
            footer_depth += 1
        elif re.match(r"</\s*(footer|nav|aside)", tag, re.I):
            footer_depth = max(0, footer_depth - 1)
        text = re.sub(r"\s+", " ", TAGS.sub(" ", chunk)).strip()
        if text:
            blocks.append((text, footer_depth > 0))
    return blocks


def extract(html: str, onion: str = "", url: str = "", persona_id: str = "",
            handle: str = "",
            thread_id: str = "", post_id: str = "",
            author_persona: str = "", forum_position: str = "unknown") -> list:
    """Harvest every clear-web mention from one page/post, block by block.

    For forum posts, supply thread_id, post_id, author_persona and
    forum_position.  The position must be one of FORUM_POSITIONS; unknown is
    the safe default for non-forum callers.
    """
    out: list = []
    for text, in_footer in _segment(html):
        out.extend(_extract_block(text, in_footer, onion, url, persona_id,
                                  handle, thread_id, post_id,
                                  author_persona, forum_position))
    return sanitise(out)


def _extract_block(text: str, in_footer: bool, onion: str, url: str,
                   persona_id: str, handle: str,
                   thread_id: str = "", post_id: str = "",
                   author_persona: str = "",
                   forum_position: str = "unknown") -> list:
    out: list = []

    def add(kind: str, value: str, m) -> None:
        out.append(Mention(kind=kind, value=value, onion=onion, url=url,
                           persona_id=persona_id, handle=handle,
                           context=_window(text, m.start(), m.end()),
                           block="footer" if in_footer else "body",
                           in_footer=in_footer, offset=m.start(),
                           thread_id=thread_id, post_id=post_id,
                           author_persona=author_persona or handle,
                           forum_position=forum_position))

    seen_emails = set()
    for m in EMAIL_RE.finditer(text):
        value = m.group(1)
        domain = value.rsplit("@", 1)[-1].lower()
        if domain.endswith(".onion"):
            continue                       # an onion address is not a pivot
        if value.lower() in seen_emails:
            continue
        seen_emails.add(value.lower())
        out.append(Mention(kind="email", value=value, onion=onion, url=url,
                           persona_id=persona_id, handle=handle,
                           context=_window(text, m.start(), m.end()),
                           block="footer" if in_footer else "body",
                           in_footer=in_footer, offset=m.start(),
                           thread_id=thread_id, post_id=post_id,
                           author_persona=author_persona or handle,
                           forum_position=forum_position,
                           provider=domain,
                           provider_class=_classify_provider(domain)))

    # Jabber addresses also match EMAIL_RE; re-tag them, because the pivot for
    # an XMPP account is completely different from the pivot for a mailbox.
    jabber = {m.group(1).lower() for m in JABBER_RE.finditer(text)}
    for mention in out:
        if mention.kind == "email" and mention.value.lower() in jabber:
            mention.kind = "jabber"

    emails_seen = {m.value.lower() for m in out if m.kind in ("email", "jabber")}
    for m in DOMAIN_RE.finditer(text):
        value = m.group(1).lower().strip(".")
        if value.endswith(".onion") or value in NOISE_DOMAINS:
            continue
        # a domain that is only here as the tail of an address is not a
        # separate finding
        if any(value == e.rsplit("@", 1)[-1] for e in emails_seen):
            continue
        add("domain", value, m)

    for kind, pattern in (("telegram", TELEGRAM_RE), ("session", SESSION_RE),
                          ("wickr", WICKR_RE), ("threema", THREEMA_RE),
                          ("icq", ICQ_RE), ("paypal", PAYPAL_RE)):
        for m in pattern.finditer(text):
            add(kind, m.group(1), m)

    # Tox IDs: two regex branches (prefixed and bare), groups 1 and 2
    for m in TOX_RE.finditer(text):
        value = m.group(1) or m.group(2)
        if value:
            add("tox", value.upper(), m)

    for kind, pattern in SOCIAL_RE:
        for m in pattern.finditer(text):
            add(kind, m.group(1), m)

    for kind, pattern in (("btc", BTC_RE), ("xmr", XMR_RE), ("eth", ETH_RE)):
        for m in pattern.finditer(text):
            add(kind, m.group(1), m)

    for m in PGP_FPR_RE.finditer(text):
        add("pgp_fingerprint", m.group(1).upper(), m)

    return out


def sanitise(mentions: list) -> list:
    """The paper's sanitiser module: drop invalid and duplicate findings.

    Duplicates are collapsed on (kind, value) *per page*, keeping the first
    occurrence. Collapsing across pages instead would destroy the provenance
    that makes the harvest worth anything -- the same address found in a footer
    and in a vendor's contact block are two very different observations, and
    only one of them is a lead.
    """
    out, seen = [], set()
    for m in mentions:
        if not m.value or len(m.value) > 320:
            continue
        if m.kind in ("telegram", "wickr") and (
                m.value.lower() in NOT_USERNAMES
                or m.value.lower() in {"channel", "telegram", "support",
                                       "admin", "contact", "username"}):
            continue                       # a provider or a generic word
        if m.kind == "domain" and m.value.count(".") > 4:
            continue                       # almost always a hostname in a log
        key = (m.kind, m.value.lower(), m.url, m.in_footer)
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def collapse(mentions: list) -> dict:
    """Group findings by identifier, retaining every sighting.

    The grouped view is what an analyst works from: one row per identifier,
    with the list of pages it appeared on. An identifier seen on several
    accounts is far more interesting than one seen once, and that only becomes
    visible after grouping.
    """
    groups: dict = {}
    for m in mentions:
        g = groups.setdefault(m.key, {
            "kind": m.kind, "value": m.value, "sightings": [],
            "personas": set(), "onions": set(),
            "provider": m.provider, "provider_class": m.provider_class,
        })
        g["sightings"].append(m)
        if m.persona_id:
            g["personas"].add(m.persona_id)
        if m.onion:
            g["onions"].add(m.onion)
    for g in groups.values():
        g["personas"] = sorted(g["personas"])
        g["onions"] = sorted(g["onions"])
        g["count"] = len(g["sightings"])
        # the strongest sighting decides the group's priority; an address that
        # appears once in a contact block and ten times in footers is a lead
        g["priority"] = max((s.priority for s in g["sightings"]), default=0.0)
        g["category"] = max(g["sightings"],
                            key=lambda s: s.priority).category if g["sightings"] else ""
    return groups


# ---------------------------------------------------------------------------
# Forum thread extraction
# ---------------------------------------------------------------------------

# HTML patterns used to detect forum structural positions in raw thread HTML.
# These are heuristics over common BreachForums/LeakForum/phpBB/XenForo
# conventions, not a full HTML parser.
_QUOTE_BLOCK = re.compile(
    r"<\s*(?:blockquote|div)[^>]*class=['\"][^'\"]*(?:quote|quoted|reply-quote)"
    r"[^'\"]*['\"][^>]*>", re.I)
_SIG_BLOCK = re.compile(
    r"<\s*(?:div|section)[^>]*class=['\"][^'\"]*(?:signature|sig\b|user-sig)"
    r"[^'\"]*['\"][^>]*>", re.I)
_MOD_BLOCK = re.compile(
    r"<\s*(?:div|section)[^>]*class=['\"][^'\"]*"
    r"(?:mod-note|staff-note|admin-note|moderator)[^'\"]*['\"][^>]*>", re.I)


def _forum_position_of(block_html: str, is_first_post: bool,
                        is_footer: bool) -> str:
    """Heuristically classify one HTML block by its forum structural role."""
    if is_footer:
        return "mod_boilerplate"
    if _MOD_BLOCK.search(block_html):
        return "mod_boilerplate"
    if _SIG_BLOCK.search(block_html):
        return "signature"
    if _QUOTE_BLOCK.search(block_html):
        return "quoted_reply"
    if is_first_post:
        return "original_post"
    return "reply_post"


def extract_forum_thread(
    posts: list[dict],
    onion: str = "",
    thread_id: str = "",
    forum_url: str = "",
) -> list:
    """Extract clear-web mentions from a sequence of forum post dicts.

    Each dict in *posts* must contain:
        post_id       str   unique within the thread
        author        str   persona handle of the poster
        persona_id    str   full persona_id (onion:handle) of the poster
        html          str   raw HTML body of the post (may contain quote blocks,
                            sig blocks, etc.)
        url           str   (optional) canonical URL of this post

    Returns a flat list of Mention objects with full provenance including
    thread_id, post_id, author_persona and forum_position.  The list is
    sanitised (per-post duplicates removed) but NOT scored; call
    context.score_all() on the result as you would for a normal crawl.

    Quote-block handling: the HTML is segmented by _segment() as usual
    (block-scoped, no character-window bleed), but the forum_position on
    identifiers inside a <blockquote> or .quote div is forced to
    "quoted_reply" regardless of which post they appear in, so context.py
    can apply the lower attribution weight.
    """
    out: list = []
    for i, post in enumerate(posts):
        post_html = post.get("html", "")
        post_id = str(post.get("post_id", ""))
        author = post.get("author", "")
        persona_id = post.get("persona_id", "")
        post_url = post.get("url", forum_url)
        is_first = (i == 0)

        # Walk each block and classify its position.
        # We split the raw HTML on block elements first (reusing _segment),
        # then re-classify based on the block's opening tag context.
        cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ",
                         post_html, flags=re.S | re.I)
        # Find block boundaries, preserving the raw HTML chunk for position detection
        raw_chunks = re.split(BLOCK_SPLIT.pattern, cleaned, flags=re.I)
        text_blocks = _segment(post_html)   # (text, in_footer) pairs

        for j, (text, in_footer) in enumerate(text_blocks):
            # Re-derive the raw HTML context for this block so we can check
            # for quote/sig/mod class attributes.
            raw_chunk = raw_chunks[j] if j < len(raw_chunks) else ""
            fp = _forum_position_of(raw_chunk, is_first, in_footer)

            mentions = _extract_block(
                text, in_footer, onion, post_url, persona_id, author,
                thread_id=thread_id, post_id=post_id,
                author_persona=author, forum_position=fp,
            )
            out.extend(mentions)

    return sanitise(out)