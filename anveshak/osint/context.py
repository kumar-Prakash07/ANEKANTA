"""Context setting: deciding which harvested identifiers are worth pursuing.

Wangchuk & Rathod treat this as the step that makes the harvest usable, and
they are right. Their scraper collected 458,470 domains and 4,068 e-mail
addresses; after sanitisation, 5,365 domains and 777 addresses survived. Then
comes the sentence that matters: *"All the domains and e-mail addresses the
scraper collected cannot be treated as the starting point of investigation."*
Most are legitimate. The judgement they describe -- reading where an address
sat and what it was being used for -- is what turns 777 addresses into the
handful worth an analyst's day.

They performed that judgement by hand. This module performs it automatically,
which is the main functional extension this file makes over the paper.

How it scores
-------------
Four independent signals, combined into one priority and always accompanied by
the reasons, because an unexplained ranking is not actionable:

  1. surrounding language   "message me directly for bulk orders" reads very
                            differently from "report phishing to". The window
                            captured at extraction time is matched against
                            phrase sets for solicitation, boilerplate, and
                            site infrastructure.
  2. structural position    an identifier on a vendor's own profile page is
                            attributable to that vendor. The same string in a
                            site footer belongs to the platform and is
                            attributable to nobody.  For forum threads, four
                            additional positions are recognised: original post
                            (strongest attribution), reply post (normal),
                            quoted reply (lower -- the identifier may belong to
                            whoever is being quoted, not the current poster),
                            signature block (structural boilerplate, like a
                            footer), and moderator/admin boilerplate (platform,
                            not individual).
  3. provider class         the paper's Silk Road example turns on this. A
                            mainstream mailbox ties into recovery details,
                            linked services and breach corpora; a throwaway
                            address at an anonymous provider usually does not.
  4. ubiquity               an identifier appearing on every page is furniture.
                            The same rarity argument the linkage engines use.

The output is a priority in [0, 1] and a category. Nothing is discarded --
scoring low is not the same as being deleted, and an analyst can always widen
the net -- but the queue is ordered so the first thing they read is the thing
most likely to matter.

Score range and attribution threshold
--------------------------------------
Priority is clamped to [0.0, 1.0].  Bands:
  >= 0.70  high    worth an analyst's time now
  >= 0.50  medium  worth checking after the high band
  >= 0.30  low     retain for completeness
  >= 0.00  noise   almost certainly furniture

The bands and the [0.0, 1.0] range are the same whether the source is a market
profile page or a forum thread.  No new confidence scale is introduced.
"""

from __future__ import annotations

import re

# Language that indicates an operator is soliciting direct contact. This is the
# strongest single signal, because it means the identifier is *operational*:
# the account is inviting strangers to use it, so it is in active use and
# attributable to whoever wrote the sentence.
SOLICIT = [
    "contact me", "message me", "reach me", "write me", "email me", "mail me",
    "direct order", "bulk order", "bulk orders", "wholesale", "for orders",
    "faster than", "off-site", "off site", "outside escrow", "direct deal",
    "add me", "hit me up", "dm me", "my email", "my mail", "personal email",
    "reach out", "get in touch", "for enquiries", "for inquiries",
    "stock list", "price list", "my shop", "direct shop",
]

# Platform furniture. Present on every page, belongs to the site operator at
# best, and to a template author at worst.
BOILERPLATE = [
    "abuse", "postmaster", "webmaster", "noreply", "no-reply", "do not reply",
    "report phishing", "report abuse", "copyright", "dmca", "unsubscribe",
    "privacy policy", "terms of service", "all rights reserved",
    "powered by", "security@", "legal", "compliance",
]

# Site-operational context: real, but attributable to the platform rather than
# to a vendor, so it belongs in a different queue.
SITE_OPS = [
    "support ticket", "staff", "moderator", "moderation", "admin team",
    "site support", "helpdesk", "help desk", "mirror", "uptime",
    "announcement", "maintenance", "downtime",
]

# Advice about tradecraft: often *mentions* an identifier as an example of what
# not to do. Extracting it as a lead would be a straightforward misreading.
ADVISORY = [
    "never share", "do not share", "dont share", "never use", "do not use",
    "example", "for instance", "such as", "phishing", "scam", "impersonat",
    "fake", "beware", "warning", "psa:", "opsec",
]

LOCAL_PART_GENERIC = {
    "info", "admin", "support", "contact", "sales", "help", "office", "mail",
    "team", "hello", "service", "orders", "billing", "root", "user",
}


def _hits(text: str, phrases: list) -> list:
    low = text.lower()
    return [p for p in phrases if p in low]


def score(mention, page_frequency: int = 1, total_pages: int = 1) -> None:
    """Assign category, priority and reasons to one Mention, in place."""
    ctx = mention.context or ""
    reasons: list = []
    priority = 0.30                      # a bare finding, no context either way
    category = "unclassified"

    solicit = _hits(ctx, SOLICIT)
    boiler = _hits(ctx, BOILERPLATE)
    siteops = _hits(ctx, SITE_OPS)
    advisory = _hits(ctx, ADVISORY)

    # --- 1. surrounding language ------------------------------------------
    if solicit:
        priority += 0.34
        category = "vendor_contact"
        reasons.append("solicits direct contact (%s)" % ", ".join(solicit[:2]))
    if boiler:
        priority -= 0.30
        category = "boilerplate"
        reasons.append("platform boilerplate (%s)" % ", ".join(boiler[:2]))
    if siteops and not solicit:
        priority -= 0.12
        category = "site_operations" if category == "unclassified" else category
        reasons.append("site-operational context (%s)" % ", ".join(siteops[:2]))
    if advisory and not solicit:
        priority -= 0.16
        reasons.append("appears in advisory or warning text, may be an example "
                       "rather than the author's own identifier")

    # --- 2. structural position -------------------------------------------
    # A footer, nav or aside is platform furniture regardless of its wording.
    # This is the cheapest and most reliable structural signal on the page, and
    # it is applied before the profile-attribution bonus so that a footer on a
    # vendor's profile does not inherit that vendor's attribution.
    #
    # For forum threads the same logic extends to four named positions:
    #   original_post  -- the OP wrote this; strongest attribution after profile
    #   reply_post     -- normal reply; treated like a non-profile body position
    #   quoted_reply   -- inside a quote block; lower weight because the
    #                     identifier may belong to the person being quoted, NOT
    #                     to the current poster
    #   signature      -- structural boilerplate, same penalty as a footer
    #   mod_boilerplate-- platform/staff, same penalty as a footer
    # The in_footer flag takes precedence (footer_depth counter in mentions.py
    # sets it before we see the forum_position), so a sig inside a footer is
    # caught by the existing check and we do not double-penalise.
    fp = getattr(mention, "forum_position", "unknown")

    if getattr(mention, "in_footer", False):
        priority -= 0.34
        category = "boilerplate"
        reasons.append("sits in the page footer or navigation, which belongs "
                       "to the platform rather than to any account")
    elif fp in ("signature", "mod_boilerplate"):
        priority -= 0.34
        category = "boilerplate"
        label = ("forum signature block" if fp == "signature"
                 else "moderator/admin boilerplate")
        reasons.append("sits in a %s, which is platform furniture rather than "
                       "an individual's own contact information" % label)
    elif fp == "quoted_reply":
        # The identifier may belong to whoever is being quoted, not the poster.
        # We do not discard it -- it may still be the poster's own address,
        # e.g. if they are quoting themselves -- but we give it significantly
        # less credit than an original post.
        priority -= 0.22
        reasons.append("found inside a quoted reply; the identifier may belong "
                       "to the person being quoted rather than to the current "
                       "poster (%s)" % (mention.handle or mention.persona_id or "unknown"))
        if category == "unclassified":
            category = "quoted_context"
    elif fp == "original_post":
        # The OP wrote this themselves; strong attribution bonus.
        priority += 0.22
        reasons.append("posted in the original post (OP) of the thread by "
                       "%s, which is the strongest forum attribution"
                       % (mention.handle or mention.persona_id or "unknown"))
        if category == "unclassified":
            category = "forum_op_contact"
    elif fp == "reply_post":
        # Normal reply -- same as a non-profile body position.
        if mention.persona_id:
            priority += 0.14
            reasons.append("posted in a reply by %s"
                           % (mention.handle or mention.persona_id))
            if category == "unclassified":
                category = "forum_reply_contact"
        else:
            priority -= 0.08
            reasons.append("in a forum reply not attributed to any known persona")
    elif mention.persona_id:
        # Non-forum page with a persona attached (market profile page).
        priority += 0.18
        reasons.append("published on the profile of %s, so it is attributable "
                       "to that account" % (mention.handle or mention.persona_id))
        if category == "unclassified":
            category = "profile_contact"
    else:
        priority -= 0.08
        reasons.append("not on any account's profile page")

    # --- 3. provider class -------------------------------------------------
    if mention.kind == "email":
        local = mention.value.split("@", 1)[0].lower()
        if mention.provider_class == "mainstream":
            priority += 0.20
            reasons.append("mainstream provider (%s): more likely to connect to "
                           "recovery details, linked accounts and breach data"
                           % mention.provider)
        elif mention.provider_class == "privacy":
            priority -= 0.06
            reasons.append("anonymous provider (%s): created to be disposable, "
                           "so it usually pivots to little" % mention.provider)
        if local in LOCAL_PART_GENERIC:
            priority -= 0.22
            reasons.append("generic mailbox name (%s), belongs to a role rather "
                           "than a person" % local)
    elif mention.kind in ("telegram", "jabber", "wickr", "session", "tox",
                          "threema", "icq", "paypal"):
        priority += 0.10
        reasons.append("off-platform messaging or payment identifier, which is "
                       "operational by definition")
        if category == "unclassified":
            category = "off_platform_contact"
    elif mention.kind in ("twitter", "instagram", "github", "keybase",
                          "reddit", "bitcointalk"):
        priority += 0.16
        reasons.append("clear-web social profile, directly checkable")
        if category == "unclassified":
            category = "social_profile"
    elif mention.kind == "domain":
        priority -= 0.04
    elif mention.kind in ("btc", "xmr", "eth", "pgp_fingerprint"):
        # not clear-web pivots; they belong to the linkage engines, and are
        # scored low here so they do not crowd the OSINT queue
        priority -= 0.20
        category = "on_chain_or_key" if category == "unclassified" else category

    # --- 4. ubiquity -------------------------------------------------------
    if total_pages > 2 and page_frequency >= max(3, int(0.6 * total_pages)):
        priority -= 0.28
        reasons.append("appears on %d of %d crawled pages, so it is site "
                       "furniture rather than an individual's identifier"
                       % (page_frequency, total_pages))
    elif page_frequency == 1 and total_pages > 3:
        priority += 0.08
        reasons.append("appears on exactly one page")

    mention.priority = max(0.0, min(1.0, priority))
    mention.category = category
    mention.reasons = reasons


def score_all(mentions: list) -> list:
    """Score a whole crawl, using cross-page frequency for the ubiquity term."""
    pages = {m.url for m in mentions if m.url}
    freq: dict = {}
    for m in mentions:
        freq[m.key] = freq.get(m.key, 0) + 1
    for m in mentions:
        score(m, page_frequency=freq.get(m.key, 1), total_pages=max(1, len(pages)))
    return mentions


PRIORITY_BANDS = [
    (0.70, "high", "worth an analyst's time now"),
    (0.50, "medium", "worth checking after the high band"),
    (0.30, "low", "retain for completeness"),
    (0.0, "noise", "almost certainly furniture"),
]


def band(priority: float) -> tuple:
    for floor, name, note in PRIORITY_BANDS:
        if priority >= floor:
            return name, note
    return "noise", "almost certainly furniture"
