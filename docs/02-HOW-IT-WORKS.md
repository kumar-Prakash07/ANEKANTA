# How it works

*The mechanism, from a crawled page to a defensible finding. Follow it in
order; each stage exists because the one before it produces something the next
one cannot use directly.*

---

## The pipeline

```
 DISCOVERY      search engines + Ahmia blacklist ──► candidate .onion addresses
      │
 COLLECTION     Tor-only crawl, recursive ──────────► personas · posts · fingerprints
      │
 BLOCKING       inverted indexes + neighbours ──────► 40,755 pairs ► 10,787 candidates
      │
 12 ENGINES     each scores a pair on one channel ──► raw score + rationale
      │
 CALIBRATION    score ──► likelihood ratio ─────────► comparable across channels
      │
 SELECTION      drop channels that fail on Cllr ────► 10 of 11 kept, typically
      │
 FUSION         combine channel LRs ────────────────► one calibrated log10 LR
      │
 RESOLUTION     links ──► actor clusters ───────────► dossiers
      │
 DARK2CLEAR     clear-web leaks ──► context ────────► pivots, attributed to the actor
      │
 REPORTING      ──────────────────────────────────► a document you can defend
```

---

## 1. Discovery — finding services to look at

`anekanta/collect/discovery.py`, adapted from **darkdump** (Josh Schiavone, MIT).

Queries dark-web search engines (Tordex, Tor66, OnionLand and others) through
Tor, collects `.onion` addresses, and filters them.

Two safety layers, and the ordering matters:

**Ahmia's abuse blacklist, fail-closed.** Ahmia publishes SHA-1 digests of
addresses reported for child sexual abuse material. Every candidate is hashed
and checked. If the blacklist cannot be fetched, discovery **aborts** rather
than continuing unfiltered — the original tool degrades silently in that case,
and silent degradation on this particular filter is not acceptable.

**A local content gate** (`collect/safety.py`) then scores titles, snippets and
fetched pages independently, because a blacklist only knows what has already
been reported.

Anything flagged is dropped before it is fetched, never written to disk, and
counted in the report so the number of exclusions is visible.

## 2. Collection — turning a service into records

`anekanta/collect/crawler.py`

- **All traffic via `socks5h`**, so the `.onion` name is resolved *at the Tor
  proxy*. Resolving locally would leak the lookup to your DNS resolver — the
  classic way people deanonymise themselves doing this work.
- **Recursive.** One seed address in; onion links found on the pages are
  sanitised (v3 only, 56 base32 characters) and enqueued. This is the crawler
  design from Wangchuk & Rathod, who took 4,426 seeds and reached 9,135 further
  addresses.
- **Polite.** Serialised, rate-limited, `robots.txt` honoured, page and byte
  budgets enforced, GET only, never submits a form, never follows an off-onion
  link.

Output: `Persona` records (an account on one service) and `Post` records, plus
a `ServiceFingerprint` per service.

## 3. Service fingerprinting — what survives a rebrand

`anekanta/collect/fingerprint.py`

An operator can rename a market, rotate a key and move to a new address in an
afternoon. What they almost never do is rebuild the stack.

| Artefact | Why it survives | How it is compared |
|---|---|---|
| **Favicon** | an icon is a file that gets copied | SHA-256, Shodan's mmh3 convention (so a hash pivots against public scan data), and a perceptual dHash that survives re-encoding |
| **TLS certificate** | operators reuse the *key*, not just the cert | issuer/subject/serial/SAN/validity, and the **SHA-256 of the SubjectPublicKeyInfo** — which identifies the key, so it survives a certificate reissue |
| **Site template** | rewriting copy is cheap; rebuilding a theme is not | DOM skeleton with all text and attributes stripped, CSS class vocabulary (Jaccard), 404-page shape, asset hashes |
| **HTTP stack** | nobody thinks about it | ordered list of response header names, server banner |

## 4. Blocking — because O(n²) is not a plan

`anekanta/fusion/blocking.py`

At 286 personas, all-pairs is 40,755 comparisons and nobody notices. At the
scale this would actually run — millions of scraped accounts — it is 10¹² and
the system does not exist.

Candidate generation uses inverted indexes on exact artefacts (PGP fingerprint,
wallet cluster, onion address, image hash, contact identifier, rare
infrastructure prints) plus approximate neighbours on style, handle and
inferred timezone.

Two numbers are **always reported together**: reduction ratio (73.5 % of work
skipped) and pair completeness (92.9 % of true links retained). A blocker that
quietly discards true links is buying speed with cases.

## 5. The twelve engines

Each scores one pair on one channel and returns a raw score plus an
analyst-readable rationale. Engines never invent their own confidence — that is
done once, centrally, against held-out data.

**Behavioural** — what an operator cannot easily change:

- **`stylometry`** — character n-grams, Burrows' Delta on function words, twelve
  structural habits (comma rate, casing, contraction rate, British/American
  spelling), plus the **impostors method**: not "how similar are A and B" but
  "where does B rank among everyone A could have been compared with", in both
  directions. That stops bland writers matching everybody.
- **`authorship`** — a learned author embedding (see below).
- **`temporal`** — circadian rhythm. Also produces a **UTC offset estimate** via
  the sleep-gap method: find the quietest contiguous window, call its centre the
  middle of the local night, solve for the offset. Reported with an uncertainty
  band derived from how pronounced the gap is, so an operator with no rhythm
  gets no location claim.

**Artefact** — things an operator chooses, and can rotate:

- **`pgp`** — fingerprint match, and when rotated, UID similarity and key
  creation timing (keys minted in one sitting look like one setup session).
- **`crypto`** — common-input-ownership clustering with **service-address
  quarantine**. Naive co-spend clustering welds a real chain into one blob
  because mixers co-spend with thousands of unrelated customers; services are
  detected by counterparty diversity, adaptively, not from a blocklist.
- **`handle`** — alias normalisation (leetspeak, separators, numeric suffixes)
  with substring-rarity weighting.
- **`infra`** — SSH host key, JARM, header order, hosting identifier.
- **`favicon`**, **`tls`**, **`template`** — as described above.
- **`device`** — EXIF camera model and perceptual image hashes.
- **`verbatim`** — exact post reuse, deliberately kept separate from stylometry.

### Rarity weighting — the single most important idea

**A match is informative only in proportion to how unusual the matched value
is.** A PGP key held by two accounts is near-conclusive; a JARM hash shared by
forty accounts on one bulletproof host says nothing about who runs them.

Formally this is the *typicality* term of the likelihood ratio. In practice it
is what stops the system linking every tenant of a hosting provider, every user
of a coin mixer, and every account on a marketplace to each other.

It is applied in **every** engine. Two production bugs during development were
both the same failure — one branch where it had been forgotten:

- The favicon engine added the rarity weight to a **floor of 0.35**, so an icon
  present on 17 of 17 services still scored 0.35 and the calibrator turned that
  into real evidence.
- The infra engine treated a shared `.onion` as conclusive with no weighting at
  all — but every vendor on a marketplace shares its address. They are accounts
  *on* it, not co-operators *of* it.

Fixing both removed **all five** false positives from a live run and raised
benchmark precision from 0.960 to 0.973.

## 6. Calibration — making channels comparable

`anekanta/fusion/lr.py`

A score of 0.83 on the handle channel and 0.83 on the crypto channel are not
the same quantity, and neither tells you how much to update your belief.

Every score is converted to a **likelihood ratio** by logistic calibration
(a score-based LR) fitted on **actor-disjoint** held-out pairs. Splitting on
*pairs* would leak — a persona in the training half would reappear in test pairs
and the model could learn that persona rather than the phenomenon.

Channels that carry no information converge to LR = 1 on their own. The
`verbatim` channel does exactly that: the calibrator learns from data that
copy-pasted text is about as common between strangers as within one operator,
and assigns it nothing.

### The artefact negative floor

The subtlest decision in the codebase, in `schema.py`.

When a disciplined operator rotates their key, the PGP channel sees "no match"
and wants to score that as evidence *against* a link. But P(no shared key |
same operator) depends almost entirely on how careful that operator is — a
latent variable never observed. Calibrated against a mixed population, that one
number is too negative for the careful operator and not negative enough for the
careless one.

Left uncapped, an operator who rotates key *and* wallet *and* host *and* handle
accumulates negative evidence from each rotation and ranks **below two random
strangers**. The system would reward tradecraft precisely where it must not.

So a null observation on a *rotatable* artefact may only weakly argue against a
link. Behavioural channels are **not** capped: a genuine mismatch in circadian
rhythm is real evidence of difference, because that is not a switch anyone can
flip.

## 7. Selection — components must earn their place

Adding a good channel can still make the system worse. When the neural
authorship channel was first added, overall AUC *fell* from 0.982 to 0.971 and
C<sub>llr</sub> degraded from 0.223 to 0.315 — it correlates with hand-crafted
stylometry, and summing two correlated channels double-counts the same evidence.

The first fix selected channels on cross-validated **average precision** and
dropped nothing, because AP scores only the *ordering* and double-counting
barely moves a ranking. It inflates the LR *magnitude* — which is what the
threshold, the report and the analyst actually consume.

Selecting on cross-validated **C<sub>llr</sub>** fixed it immediately.
C<sub>llr</sub> charges for confidence in proportion to how wrong it was, so it
sees exactly this failure. The system now drops `infra` and `template` as
redundant with `favicon` and host-level signals, and the learned fusion is
compared against a naive sum on the same folds — the loser is discarded.

**Selecting on the metric the product depends on, rather than the conventional
one, is the difference between a system that ranks well and one whose numbers
can be quoted.**

## 8. The two learned components

`anekanta/ai/`

**Author embedding** (`author_net.py`) — a contrastive network trained to
answer *"did these two posts come from the same account?"*. The crucial
property: the training signal is **persona identity, which is printed next to
every post**. It is self-supervised — no actor labels in its input — so it can
be trained on live crawled data with no ground truth, and the held-out
evaluation stays honest. It also solves the sample-size problem: a few dozen
same-actor persona pairs, but tens of thousands of same-persona *post* pairs.

*Honest result:* on this corpus hand-crafted stylometry **beats** it
(0.961/0.960/0.642 vs 0.877/0.915/0.605). Unsurprising — the generator builds
idiolects from the very features the hand-crafted engine measures, an advantage
it would not have on real prose. It is kept because it survives selection, and
because on real text there is no hand-written feature list to fall back on.

**Tradecraft classifier** (`tradecraft.py`) — predicts how disciplined an
operator is from one account's observable features, *before* any linking. It
matters because "no linkage found" means something completely different for a
careless operator than a careful one, and an analyst needs to know which case
they are in rather than reading silence as exoneration.

*Honest result:* **62.5 % accuracy against a 47.2 % majority baseline, missing
75 % of disciplined operators.** A weak triage signal. The limitation is
structural, not fixable by a bigger model: roughly half the actors run a single
account, and discipline is largely *defined* by what you reuse across accounts.
Its two most useful features turned out to be behavioural — hour-of-day entropy
and inter-post interval regularity — because deliberate schedule jitter is one
of the few tradecraft choices visible from a single account.

## 9. Resolution — from pairs to operators

`anekanta/fusion/graph.py`

Thresholding edges and taking connected components chains badly: A links to B
on style, B links to C on a shared host, and A and C are declared the same
person on no evidence between them at all.

Components are therefore accepted only if internally dense enough, and
otherwise split at their weakest bridge, repeatedly. Each surviving cluster
becomes a **dossier**: every account, marketplace, key, wallet, hidden service
and device, plus a timezone estimate *pooled* across the cluster — more precise
than any single account's, because it averages more observations of one rhythm.

## 10. Dark2Clear — from the dark web to the clear web

`anekanta/osint/`, implementing Wangchuk & Rathod (2023).

The channels above answer *which accounts are one operator*. They cannot answer
*who*. Nothing in a hidden service will tell you — unless the operator makes a
mistake. They do.

**Harvest** (`mentions.py`) — identifiers that only mean something outside Tor:
e-mail, clear-web domains, Telegram, Jabber, Session, Wickr, Threema, ICQ,
PayPal, public social profiles. Every finding records its service, URL, the
account whose profile it sat on, and the enclosing block.

**Context setting** (`context.py`) — the step the paper performs *by hand*, and
the one that makes the harvest usable. Their run produced 4,068 addresses, of
which a handful mattered. Four signals, always with printed reasons:

1. **Surrounding language** — "reach me directly for bulk orders" vs "report
   phishing to". Scored over the *enclosing block*, not a character window: a
   window bleeds across sections and lets a footer inherit a vendor's
   solicitation score. That bug promoted `abuse@` addresses into the high band
   until a test caught it.
2. **Structural position** — a footer belongs to the platform whatever it says;
   an identifier on a vendor's profile is attributable to that vendor.
3. **Provider class** — the Silk Road example turns on this. A mainstream
   mailbox ties into recovery details, linked services and breach corpora; a
   throwaway at an anonymous provider usually does not.
4. **Ubiquity** — an identifier on every page is furniture.

*Measured on the live lab: real leaks 0.84–1.00, every decoy 0.00, no overlap.*

**Pivot** (`pivot.py`) — the paper uses Maltego and Lampyre. Reimplementing
commercial data sources is neither possible nor honest, so this computes what
needs no subscription and emits everything else as a **URL to check, not a
result**. Nothing is fetched by default: querying a third party tells it you
are interested in an identifier, from your address, at a recorded time, and
that is the investigator's decision.

What it does compute is the strongest pivot anyway — **identity correlation**,
running the leaked local part and every dark-web handle through the *same*
normaliser the handle engine uses, so `kavach.supply@gmail.example` and the
account `kavach_supply` collapse to one string.

**And the part the paper cannot do.** Because accounts have already been
resolved into operators, a leak found on *one* account attaches to *every*
account in its cluster. On the live run, one careless address on
`kavach_supply` implicated `kavach.supply2` and `nightfreight` — which
published nothing.

## 11. Reporting

`anekanta/reporting.py`

Every finding renders to a document stating four things, because omitting any
of them is how attribution evidence gets discredited:

- the **propositions** being compared, in the order the LR compares them
- **every channel**, including the ones that argued *against* the link or
  abstained
- the **prior**, separately from the evidence, with the posterior as the
  consequence of combining them
- the **limitations**, in the report itself rather than a manual nobody reads

The verbal scale follows ENFSI convention. The wording matters: *"very strong
support for the same-actor proposition"* is a claim about evidence; *"the
accounts are the same person"* is a claim about the world, and this system is
only ever entitled to the first.

---

## Next

- [Architecture](03-ARCHITECTURE.md) — how this is deployed and how it scales
- [User guide](04-USER-GUIDE.md) — running it
