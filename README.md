# ANEKANTA
 # & "C:\Program Files\Orange\python.exe" run.py serve
**Dark web threat actor de-anonymisation and attribution platform**
Smart India Hackathon 2026 · **SIH26151** · National Technical Research Organisation · Blockchain & Cybersecurity

*अन्वेषक — "the investigator"*

**[Full documentation →](docs/)**  ·  [Why this matters](docs/01-WHY-THIS-MATTERS.md) ·
[How it works](docs/02-HOW-IT-WORKS.md) · [Architecture](docs/03-ARCHITECTURE.md) ·
[User guide](docs/04-USER-GUIDE.md) · [Build notes](docs/05-BUILD-NOTES.md)

---

## The problem, stated precisely

A single operator on the dark web runs many personas: a vendor account on one
market, a support handle on a forum, a reseller alias on a third board. Taking
down one account achieves nothing, because the other five keep trading. The
investigative question is not "who is this person" — that is answered by lawful
process, not by software — it is:

> **Which of these accounts are the same human being, and how strongly do we
> believe it?**

ANEKANTA answers that question with a number an analyst can defend, and refuses
to answer when the evidence does not support one.

## Quick start

One command brings up the whole platform — dashboard, Tor daemon, and two mock
hidden services:

```bash
docker compose up -d --build
```

Then open **<http://127.0.0.1:8000>**. That is the entire setup.

> **Hosting note.** The interactive platform needs a machine with a network
> stack: a Tor daemon holding circuits open, crawls that run for minutes, and
> a model larger than any serverless function limit. It therefore runs locally
> or on a container host. A **static build** of the real results — every tab,
> real numbers, including a live crawl of two hidden services and a sweep of
> the public Tor network — deploys to Vercel and is the right thing to put
> behind a public URL. See [DEPLOYMENT.md](DEPLOYMENT.md).

The first start takes a few minutes: it builds the image and then trains the
calibration on the benchmark before serving. Watch it with
`docker compose logs -f anekanta`.

```bash
python run.py preflight
```

Run that once the stack is up. It verifies on the **running containers** that
nothing has been exposed to your machine or your network, and must pass before
you show an address to anybody. See [onionlab/SECURITY.md](onionlab/SECURITY.md).

### Without Docker

```bash
pip install -r requirements.txt
```

```bash
python run.py bench          # full evaluation, printed
```

```bash
python run.py serve          # dashboard on http://127.0.0.1:8000
```

```bash
python -m unittest discover -s tests
```

No Node, no build step, no database. The live and real-network features need a
Tor SOCKS proxy, which the Docker stack provides on `127.0.0.1:9050`.

### Against real hidden services

ONIONLAB publishes **two** genuine Tor hidden services from your own machine —
a marketplace and a discussion board — so the platform can be demonstrated on
live infrastructure rather than on a file. Two rather than one, because a
single service cannot exercise recursive discovery, cross-service linkage, or
the shared-stack fingerprints that survive a rebrand.

It needs Docker. It does **not** need Tor installed on Windows, and it must
not be.

```bash
cd onionlab && docker compose up -d
```

```bash
python run.py preflight
```

```bash
docker exec onionlab-tor cat /srv/onion-addresses/market
```

```bash
python run.py live <that-address>.onion
```

You only ever supply **one** address. The crawler finds the second by reading
the pages, which is the recursive stage of the framework below.

`preflight` verifies the container isolation and must show nine passes before
you show an address to anybody. **Read [onionlab/SECURITY.md](onionlab/SECURITY.md)
first** — it explains what protects your machine and what does not.

The dashboard's **Live Onion** tab runs the same thing from the browser: it
prefills the local lab address, streams crawl progress, and renders the
fingerprint comparison, the clear-web harvest, operator exposure and the
graded result.

---

## Where to look

Everything below is reachable from <http://127.0.0.1:8000> once the stack is up.

| Tab | What it shows | Needs |
|---|---|---|
| **Overview** | Headline metrics, detection rate by operator discipline, the channel-survival heat map, adversarial trap results | nothing |
| **Live Onion** | Crawl the mock hidden services over Tor from the browser. Streams progress, then shows fingerprint comparison, the clear-web harvest, operator exposure, and a graded result | the lab (included) |
| **Real Network** | Keyword discovery and the real-world benchmark against **live public onion services** — darkdump integration, Ahmia blacklist, infrastructure correlation | Tor + internet |
| **Link Graph** | Personas packed by resolved actor; cross-cluster edges flagged | nothing |
| **Linkages** | Every scored pair, expandable to the per-channel evidence behind it | nothing |
| **Resolved Actors** | Dossiers with pooled geotemporal assessment | nothing |
| **Contact Exposure** | Per-actor contact-exposure map: actor → persona ring → identifier ring, SVG radial graph. Edge styling encodes evidence state (attributed / present / inherited). Click any node for thread ID, forum, context score, and plain-language reasoning | nothing |
| **Benchmark** | Every metric, the ablation, calibration, and the learned-component report | nothing |
| **Method** | How a linkage is produced, and what the system will not do | nothing |

The two-minute demo: **Overview** for the headline numbers, **Live Onion** →
*Crawl and analyse* to watch it work on a real hidden service, then **Real
Network** → *Run full benchmark* to do the same against the public Tor network.

From the terminal:

```bash
python run.py bench
```

```bash
python run.py live $(docker exec onionlab-tor cat /srv/onion-addresses/market)
```

```bash
python run.py realworld --services 16 --pages-each 4
```

---

## Results

Measured on a 286-persona, 150-actor labelled benchmark with a **0.48 % base
rate** — one true link per 207 possible pairs. All figures are on **held-out
actors** the calibrator never saw.

| | |
|---|---|
| ROC AUC | **0.981** |
| Precision / Recall / F1 | **0.97 / 0.74 / 0.84** |
| Precision @ top 25 of queue | **1.00** |
| C<sub>llr</sub> (C<sub>llr</sub><sup>min</sup>) | **0.240** (0.203) |
| B-Cubed F1 (identity clustering) | **0.930** |
| Blocking | 73.5 % of pairs skipped, 92.9 % of true links retained |

### On live hidden services

One seed address in. The crawler discovers the second service itself, then both
halves of the pipeline run and are graded against a map the crawler never saw:

| | |
|---|---|
| Crawled | 2 services (1 discovered), 29 pages, 17 accounts, 455 posts |
| **Linkage** precision / recall | **1.00 / 0.27** (AUC 0.90, B-Cubed F1 0.83) |
| **Clear-web leaks recovered** | **7 of 7**, all attributed to the publishing account |
| Decoys collected | 4 of 4 — kept, but ranked to 0.00 against 0.84+ for real leaks |
| Identity correlations | 5 |
| Accounts implicated through their cluster | 3 |

Two things are worth reading carefully.

**Linkage recall is 0.27, and that is the honest number.** Most true pairs here
span two different services under deliberately unrelated handles — an operator
running `kavach_supply` on the market and `kav_admin` on the forum. Those sit
in the lead band rather than being asserted. Precision is 1.00 because the
system declines to assert what it cannot support, which is the behaviour the
whole design is built around.

**The clear-web harvest is where this run is decisive.** Every planted leak was
found, attributed to the right account, and ranked above every decoy. And
because the linkage engines had already resolved the accounts, a single leak on
`kavach_supply` implicated `kavach.supply2` and `nightfreight`, which published
nothing at all.

### On the live Tor network

Discovery and crawling against **real, public onion services** — no lab, no
ground truth. Addresses come from keyword search across dark-web indexes
(darkdump integration, below), filtered through Ahmia's abuse blacklist before
anything is fetched.

| | |
|---|---|
| Addresses discovered | 92–130 unique per run, from 6–10 neutral queries |
| Removed by Ahmia's blacklist | 85–159 per run, **before any fetch** |
| Reachable and crawled | **16/16 (100 %)** |
| Throughput over Tor | ~23 pages/min, ~11 s per service |
| Clear-web identifiers harvested | 0.8–1.0 per service |

**The finding that needs no labels.** Two services discovered independently,
through different search terms, turned out to serve a byte-identical favicon:

```
torlink2uegl22vwzop42t4eipy2r2eksk67kvan4vx4r6h77t3cejad.onion   "The Hidden Wiki"
torwikijwqskahohtn35pyfde2uqmgrxgr2fru4mn4rer5muj445dxyd.onion   "Hidden Wiki"

favicon  3,241-byte PNG, SHA-256 c965a500f698…, mmh3 530492348   ← identical
header ordering  Server, Date, Content-Type, …, Link             ← identical
```

That is a *fact*, not a prediction. Anyone can fetch both addresses and check
the two hashes, and no operator map is needed to state it. It is exactly the
mirror/rebrand pivot the service-fingerprint channels exist to find, produced
on the live network.

It is also **sample-dependent**: a later 14-service run found no non-generic
clusters at all, because those two addresses did not both fall in the sample.
The dashboard says so rather than showing an empty panel, and that is the
honest behaviour — infrastructure correlation finds what is there to find.

**What is deliberately not claimed here.** Linkage precision and recall.
Deciding whether two accounts share an operator requires knowing the answer,
and on the live network nobody does; any figure would be invented. Those
numbers come from the labelled benchmark, which exists for exactly that reason.

**A limitation reported rather than implied.** The persona extractor keys on
profile-page structure, and real services do not share ONIONLAB's — so
account-level extraction from an arbitrary marketplace returns nothing and
needs a per-site adapter. The run reports how often that happened. Service
fingerprinting and the clear-web harvest are structure-agnostic and do
generalise, which is why they carry the real-world result.

### The finding that matters

Every actor in the benchmark is assigned an operational-security tier, and the
system is scored separately against each. Per-channel discrimination (AUC):

| channel | sloppy | mixed | **disciplined** |
|---|---|---|---|
| PGP key | 1.000 | 0.831 | **0.557** |
| handle | 0.999 | 0.759 | **0.466** |
| wallet cluster | 0.709 | 0.578 | **0.500** |
| device / EXIF | 0.748 | 0.577 | **0.457** |
| infrastructure | 0.910 | 0.626 | **0.511** |
| favicon | 0.924 | 0.601 | **0.549** |
| TLS certificate | 0.627 | 0.539 | **0.488** |
| site template | 0.937 | 0.576 | **0.519** |
| **stylometry** | 0.961 | 0.960 | **0.642** |
| **author embedding** (neural) | 0.877 | 0.915 | **0.605** |
| **circadian** | 0.870 | 0.858 | **0.908** |
| **fused** | **1.000** | **0.988** | **0.778** |

Read the right-hand column. Against an operator who rotates their tradecraft,
**every artefact channel collapses to chance** — 0.56, 0.47, 0.50, 0.46, 0.51,
0.55, 0.49, 0.52. Those are coin flips. Only the behavioural channels survive,
and circadian rhythm barely degrades at all (0.87 → 0.91).

That is the thesis of this project, and it is asserted as a unit test
(`test_behaviour_outlasts_artefacts_against_disciplined_operators`) so that if
it ever stops being true, the suite says so rather than the pitch deck.

The reason is simple enough to say in one sentence: **a key can be rotated, a
wallet can be abandoned, a host can be changed — a sleep cycle cannot.**

### What we do *not* claim

Recall against disciplined operators at the assertion threshold is near zero
on most seeds, and the honest reason is not that we cannot rank them — the
fused AUC of 0.778 says we rank them well — but that two moderately-informative behavioural
channels cannot produce a likelihood ratio large enough to *assert* a linkage
at 95 % precision. Reporting them as linkages anyway would be the single
easiest way to make this table look better and the tool useless.

So they go to a **lead queue** instead: 66 pairs containing 13 true links —
**19.7 % precise against 3.6 % in the scored candidate pool, a 5.5× enrichment** —
explicitly labelled as leads and never as findings. The queue's depth is itself
fitted on the training split, descending only as far as it stays worth an
analyst's time.

That enrichment is deliberately quoted against the *candidate pool*, not
against the 0.48 % corpus base rate. Comparing to the corpus would let us claim
44x, but it would be taking credit for the blocking stage twice over: those
pairs were already filtered before scoring, so the pool is what an analyst
would actually be working through.

---

## How it works

```
 DISCOVERY  ─► keyword search across dark-web indexes (darkdump)
            │   Ahmia blacklist, fails closed  +  local content gate
            ▼
 crawl ─► personas + posts
            │
            ├─► BLOCKING          inverted indexes + approximate neighbours
            │                     40,755 pairs ─► 10,787 candidates
            │
            ├─► 12 EVIDENCE ENGINES  each returns a raw score + a rationale
            │     stylometry · author embedding · circadian
            │     blockchain · PGP · handle · infrastructure · device
            │     favicon · TLS certificate · site template
            │
            ├─► CALIBRATION       raw score ─► likelihood ratio, fitted on
            │                     held-out actors
            │
            ├─► SELECTION         channels and combiner that fail to improve
            │                     cross-validated Cllr are dropped
            │
            ├─► FUSION            learned combiner vs naive sum
            │
            ├─► RESOLUTION        pairwise links ─► actor clusters ─► dossiers
            │
            ├─► DARK2CLEAR        clear-web mentions ─► context setting ─►
            │                     OSINT pivots, attributed to the resolved actor
            │
            └─► REPORTING         evidence report an analyst can defend
```

### 1. Likelihood ratios, not confidence scores

An engine score of 0.83 is meaningless on its own, and 0.83 on the handle
channel is not the same quantity as 0.83 on the crypto channel. Every score is
therefore converted to a **likelihood ratio**:

```
      P(this observation | the personas are one actor)
LR = ──────────────────────────────────────────────────
      P(this observation | they are different actors)
```

This is the standard forensic-science formulation, and it has a property that
matters enormously in this domain: it separates *evidence* from *belief*. The
LR is a statement about the data. Turning it into a probability requires a
prior, which the analyst supplies and which the report prints. A system that
collapses both into one "87 % confident" badge has committed the prosecutor's
fallacy on the analyst's behalf and made it impossible to audit.

Calibration is empirical (a score-based LR via logistic regression on held-out
actors), so channels that turn out to be worthless converge to LR = 1 by
themselves. The `verbatim` channel does exactly that: the calibrator learns
from the data that copy-pasted text is roughly as common between strangers as
between one person's two accounts, and assigns it nothing.

### 2. Rarity weighting

The single most important mechanism in the system, and the one that defeats
three of the five traps. **A match is informative only in proportion to how
unusual the matched value is.** A PGP key held by two personas is close to
conclusive; a JARM hash shared by forty personas on the same bulletproof host
says nothing about who runs them. Formally this is the typicality term of the
likelihood ratio; in practice it is what stops the system linking every tenant
of a hosting provider to every other.

The same idea handles coin mixers. Naive common-input-ownership clustering
welds most of a real chain into one blob, so service addresses are detected by
counterparty diversity — adaptively, not from a blocklist — and quarantined
before clustering, and any surviving linkage is discounted by the size of the
cluster that produced it.

### 3. The artefact negative floor

The subtlest decision in the codebase, in `schema.py`.

When a disciplined operator rotates their key, the PGP channel observes "no
match" and the calibrator wants to score that as evidence *against* a link. But
P(no shared key | same actor) depends almost entirely on how careful that actor
is — a latent variable we never observe. Calibrated against a mixed population,
that one number is too negative for the careful operator and not negative
enough for the careless one.

Left uncapped, an operator who rotates their key *and* their wallet *and* their
host *and* their handle accumulates negative evidence from each rotation and
ends up ranked **below two random strangers**. The system would reward
tradecraft precisely where it must not.

So a null observation on a *rotatable* artefact may only weakly argue against a
link. Behavioural channels are not capped: a genuine mismatch in circadian
rhythm is real evidence of difference, because that is not a switch an operator
can flip. In the run where it was introduced, this raised precision from 0.944 to
0.961 and disciplined-tier fused AUC from 0.811 to 0.831.

### 4. Impostor-based verification

A raw stylometric cosine of 0.65 is uninterpretable, because some personas
write so blandly they sit close to everybody. The engine therefore asks not
"how similar are A and B" but "**where does B rank among everyone A could have
been compared with**", in both directions. A pair scores highly only if each is
the other's standout match. This is the impostors method from the authorship
verification literature, and adding it lifted overall AUC 0.957 → 0.965,
disciplined-tier fused AUC 0.831 → 0.854, and recovery of key-rotated links
from 20 % to 29 %.

### 5. Service fingerprinting: what survives a rebrand

An operator can rename a market, rotate a PGP key and move to a new `.onion` in
an afternoon. What they almost never do is rebuild the *stack*. Three channels
exploit that:

| artefact | why it survives | how it is compared |
|---|---|---|
| **favicon** | an icon is a file that gets copied | SHA-256, Shodan's mmh3 convention (so a hash pivots against public scan data), and a perceptual dHash that survives re-encoding |
| **TLS certificate** | operators reuse the key, not just the cert | issuer/subject/serial/SAN/validity, and the **SHA-256 of the SubjectPublicKeyInfo** — which identifies the *key*, so it links services across a certificate reissue |
| **site template** | rewriting the copy is cheap, rebuilding the theme is not | DOM skeleton with all text and attributes stripped, CSS class vocabulary (Jaccard), 404-page shape, static asset hashes |

Plus response header *order*, which is a property of the server and proxy chain
that operators never think about.

All of them are rarity-weighted, and they have to be: a stock favicon shipped
with a popular market script is on hundreds of sites and means nothing. The
benchmark plants exactly that case — a third of actors never customise the icon
their script came with, and template popularity is skewed so most operators
share a theme with somebody.

Favicon and template rank among the strongest artefact channels on careless
operators (0.92 and 0.94 solo AUC) and, like every other artefact, fall to
chance against careful ones.

### 6. The two learned components

Both are held to the same rule as everything else: beat the simpler
alternative on cross-validated C<sub>llr</sub>, or be dropped.

**Author embedding** (`anekanta/ai/author_net.py`) — a contrastive network
trained to answer *"did these two posts come from the same account?"*. The
crucial property is that the training signal is **persona identity, which is
printed next to every post**. It is self-supervised: no actor labels exist in
its input, so it can be trained on live crawled data with no ground truth
whatsoever, and the held-out evaluation stays honest. It also solves the sample
size problem — there are a few dozen same-actor persona pairs in the benchmark
but tens of thousands of same-persona *post* pairs.

Honest result: on this corpus the hand-crafted stylometry engine **beats** it
(0.961/0.960/0.642 versus 0.877/0.915/0.605). That is unsurprising and worth
saying plainly — the generator builds idiolects out of the very features the
hand-crafted engine measures, which is a structural advantage it would not have
on real prose. The neural channel is kept because it survives selection, and
because on real text there is no hand-written feature list to fall back on. The
hand-crafted channel is kept because an analyst can point at a comma rate in
court, and cannot cross-examine a cosine.

**Tradecraft classifier** (`anekanta/ai/tradecraft.py`) — predicts how
disciplined an operator is from one persona's observable features alone, before
any linking is attempted. It matters because "no linkage found" means something
completely different for a careless operator than for a careful one, and an
analyst needs to know which case they are in rather than reading silence as
exoneration.

Honest result: **62.5 % accuracy against a 47.2 % majority baseline, and it
misses 75 % of disciplined operators.** A weak signal, useful for triage and
not much more. The limitation is structural rather than fixable by a better
model: roughly half the actors run a single persona, and discipline is largely
*defined* by what you reuse across accounts, which a lone account does not
exhibit. Its two most useful features turned out to be behavioural — hour-of-day
entropy and inter-post interval regularity — because deliberate schedule jitter
is one of the few tradecraft choices visible from a single account.

### 7. Channel selection, and why the criterion is C<sub>llr</sub>

Adding a good channel can still make the system worse. When the neural
authorship channel was first added, overall AUC *fell* from 0.982 to 0.971 and
C<sub>llr</sub> degraded from 0.223 to 0.315: it is highly correlated with
hand-crafted stylometry, and summing two correlated channels double-counts the
same evidence.

The first attempt at fixing this selected channels on cross-validated average
precision and dropped nothing, because **AP scores only the ordering** — and
double-counting barely moves a ranking. It inflates the *magnitude* of the
likelihood ratio, which is what the threshold, the report and the analyst
actually consume.

Selecting on cross-validated C<sub>llr</sub> instead fixed it immediately.
C<sub>llr</sub> charges for confidence in proportion to how wrong it turns out
to be, so it sees exactly this failure. The system now drops `infra` and
`template` as redundant with `favicon` and host-level signals, and precision
recovered to 0.96. Selecting on the metric the product depends on, rather than
the one that is conventional, is the difference between a system that ranks
well and one whose numbers can be quoted.

### 8. Dark2Clear: from the dark web to the clear web

The channels above answer *which accounts are one operator*. They cannot answer
*who that operator is*, and nothing in a hidden service will tell you — unless
the operator makes a mistake.

They do. This implements the framework from **Wangchuk, T. and Rathod, D.
(2023), "Opensource intelligence and dark web user de-anonymisation",
*Int. J. Electronic Security and Digital Forensics*, 15(2), 143–157**, whose
premise is the one that actually ends cases: dark web users leak clear-web
identifiers through negligence. Ross Ulbricht advertised Silk Road as "altoid",
and separately asked a programming question using `rossulbricht@gmail.com`. One
address, on a page where it did not belong.

The paper's pipeline, and what each stage is here:

| paper stage | implementation |
|---|---|
| seed URLs, sanitised | `sanitise_onions` — v3 addresses only (56 base32 chars); a v2 address or a typo costs a Tor circuit build, which is seconds |
| recursive crawl | the crawler follows onion links it extracts, so one seed reaches the whole neighbourhood |
| scrape clear-web mentions | `osint/mentions.py` — market profile pages and forum thread posts |
| sanitise findings | dedupe per page, drop malformed values, strip script bodies |
| **log provenance** | every finding carries its service, URL, the account whose profile it sat on, the enclosing block, and — for forum posts — the thread ID, post ID, author persona, and structural position within the thread |
| **context setting** | `osint/context.py` — **automated**, where the paper does it by hand; forum-specific positions (original post, quoted reply, signature, mod boilerplate) are scored with position-specific deltas |
| **exposure aggregation** | `osint/exposure.py` — **new** — rolls up per-persona mention lists to per-actor clusters, tagging each identifier as *direct* (this persona posted it) or *inherited* (a co-clustered persona posted it); the distinction is never collapsed |
| OSINT pivot | `osint/pivot.py` |

**What is extracted.** The paper harvests e-mail addresses and clear-web
domains. Both are here, plus the identifiers operators now leak at least as
often: Telegram, Jabber/XMPP, Session, Tox, Wickr, Threema, ICQ, PayPal, and
public social profiles. The test is always the same — does this identifier have
to resolve *outside* Tor to be useful? If so, it can be followed.

**Context setting is the part that matters.** The paper's own run is the
argument: 458,470 domains and 4,068 addresses harvested, 5,365 and 777 after
sanitisation — and then the sentence that makes the work usable, *"All the
domains and e-mail addresses the scraper collected cannot be treated as the
starting point of investigation."* Most are legitimate. They read the
surrounding pages by hand to find the few that were not.

This scores it automatically, on four signals, and always prints its reasons:

1. **surrounding language** — "reach me directly for bulk orders" versus
   "report phishing to". Scored over the *enclosing block*, not a character
   window: a window bleeds across sections and lets a footer inherit a vendor's
   solicitation, which promoted `abuse@` addresses into the high band until a
   test caught it.
2. **structural position** — a footer or nav belongs to the platform whatever
   it says; an identifier on a vendor's profile is attributable to that vendor.
   For forum threads, four additional positions are scored: an original post
   gets the strongest attribution bonus; a plain reply gets a smaller one; an
   identifier found inside a *quoted reply* is penalised because it may belong
   to whoever is being quoted rather than the current poster; a signature block
   or moderator notice is treated like a footer.
3. **provider class** — the Silk Road example turns on exactly this. A
   mainstream mailbox ties into recovery details, linked services and breach
   corpora; a throwaway at an anonymous provider usually does not.
4. **ubiquity** — an identifier on every page is furniture. The same rarity
   argument the linkage engines use.

On the live lab this separates cleanly: real leaks at 0.84–1.00, every decoy at
0.00, with no overlap.

**The pivot.** The paper uses Maltego and Lampyre — commercial tools querying
paid sources. Reimplementing those is neither possible nor honest, so this does
the part that needs no subscription and emits everything else as a URL to
check rather than a result. Nothing is fetched by default: querying a third
party tells it you are interested in an identifier, from your address, at a
recorded time, and that is the investigator's decision to make.

What it does compute locally is the strongest pivot anyway — **identity
correlation**, running the leaked local part and every dark-web handle through
the *same* normaliser the handle engine uses, so `kavach.supply@gmail.example`
and the account `kavach_supply` collapse to one string. Ulbricht's mistake,
found automatically.

**And the part the paper cannot do.** Because the linkage engines have already
resolved accounts into operators, a leak found on *one* account attaches to
*every* account in its cluster. On the live run, one careless address on
`kavach_supply` implicated `kavach.supply2` and `nightfreight` — which
published nothing. Dark2Clear harvests from pages; ANEKANTA attributes the
harvest to an operator. Neither half gets there alone.

**Forum thread extension (`osint/exposure.py`).** Markets are not the only
source. BreachForums / LeakForum / DarkForum-style boards carry operational
identifiers at least as often as market profiles — operators are writing to an
audience and their guard is lower. `extract_forum_thread()` processes a
sequence of forum posts, classifying each block by its structural position
(original post, reply, quoted reply, signature, mod boilerplate) and carrying
full forum provenance — thread ID, post ID, author persona — on every extracted
identifier. `persona_exposure()` then builds per-persona counts (total posts,
leak posts matching data-sale keywords, posts containing a scored identifier).
`actor_exposure_map()` pools all personas in a resolved cluster and marks each
identifier as *direct* (this persona posted it) or *inherited* (a co-clustered
persona posted it, and this persona is implicated through their shared actor).
That distinction is preserved end-to-end — extraction → aggregation → API →
dashboard — and is never collapsed. The **Contact Exposure** dashboard tab
renders it as a three-ring SVG radial graph (actor → persona ring → identifier
ring) with edge styling that encodes evidence state: solid amber for attributed
identifiers, dashed grey for low-score direct ones, dotted grey for inherited,
and muted solid for cluster-membership edges.

### 9. Discovery, and the safety gate that guards it

Everything above assumed somebody had already handed the crawler an address.
That is fine for a lab and useless for an investigation, so seed discovery is
adapted from **[darkdump](https://github.com/josh0xA/darkdump)** by Josh
Schiavone (MIT). It queries the indexes that catalogue hidden services and
returns addresses for a keyword — the "seed URL collection" stage the
Dark2Clear framework opens with, and the one this project previously satisfied
by having the operator paste an address in by hand.

Taken from darkdump: the set of engines and their endpoints, and the decision
to check every result against **Ahmia's blacklist**, which is the single most
important safety property of the tool.

Three things are done differently:

**Everything goes through Tor, including the clearnet endpoints.** Darkdump can
query `ahmia.fi` and `tordex.cc` directly. Fetching a dark-web search engine
over your own line is a poor idea for the person running the tool: it is a
plain-text record that you searched that term at that time. Onion endpoints are
preferred; clearnet ones are routed over Tor exits, and `--clearnet` must be
asked for.

**The blacklist fails closed.** Darkdump filters when it can reach the list.
Here, if it cannot be fetched, discovery aborts. A filter that silently stops
filtering is worse than none, because the operator still believes they are
protected. In practice it loads ~58,000 hashed addresses and removes 85–159
results per run before anything is fetched.

**A second, local content gate** (`collect/safety.py`) runs over titles,
snippets, and then whole fetched pages. Ahmia's list covers what Ahmia knows
about, and three of the four engines apply no filtering of their own.

The gate looks for a **conjunction** — a token indicating a minor near a token
indicating sexual content — rather than a denylist of the coded terms used to
advertise abuse material. A denylist would work and would also mean this
repository ships a ready-made list of search terms for finding that material.
Neither vocabulary here is harmful alone: "child", "school" and the explicit
words are all ordinary, and it is their co-occurrence in a short window that
carries the signal. A paediatric forum trips one list, an adult site trips the
other, and neither is blocked. On a trip the page is **discarded whole**,
before extraction or fingerprinting, and only the address and the fact of the
exclusion are retained. The reason string never echoes the matched terms.

It filters nothing else. Drugs, weapons, fraud and malware are the subject
matter of the investigations this tool supports; filtering them would defeat
its purpose. The line drawn is narrow and deliberate: material whose mere
retrieval is an offence.

**A finding about the upstream tool.** Ahmia was darkdump's default engine and
would be the natural choice here, being the one index with its own abuse
filtering. Its search front end is now JavaScript-only and answers an HTTP
client with *"we have not deployd non-JavaScript version of Ahmia yet"* and no
results; OnionLand has gone the same way. The default is therefore an
unfiltered index — which costs nothing in safety, because Ahmia's *blacklist*
is applied to every engine's results regardless. Rather than returning an empty
list that looks identical to "no results", `search()` detects that page and
says so.

### 10. Blocking, because O(n²) is not a plan

At 286 personas, all-pairs comparison is 40,755 operations and nobody notices.
At the scale NTRO would actually run this — millions of scraped accounts — it
is 10<sup>12</sup> and the system does not exist. Candidate generation uses
inverted indexes on exact artefacts plus approximate neighbours on style,
handle and inferred timezone.

Two numbers are always reported together: **reduction ratio** (73.5 % of work
skipped) and **pair completeness** (92.9 % of true links retained). A blocker
that quietly discards true links is buying speed with cases.

### 11. Identity resolution without chaining

Thresholding edges and taking connected components chains badly: A links to B
on style, B links to C on a shared host, and A and C are declared the same
person on the strength of no evidence between them at all. Components are
therefore accepted only if internally dense enough, and otherwise split at
their weakest bridge, repeatedly.

---

## Adversarial evaluation

A benchmark where everyone is careless measures nothing. Five traps are planted
and reported pass/fail, not summarised away:

| trap | what it does | result |
|---|---|---|
| **T1** shared hosting | unrelated actors behind one bulletproof host | **held** — 0 false links |
| **T2** copy-paste | one actor reposts another verbatim | **held** — 0 false links |
| **T4** coin mixer | wallets co-spent with a high-degree service | **held** — services quarantined, no collapse |
| **T5** handle collision | unrelated actors with confusably similar names | **held** — 0 false links |
| **T3** key rotation | fresh PGP key per persona *(a false-negative trap)* | **partial** — 17 of 39 (43.6 %) still recovered without the key |

T3 is deliberately reported as partial. When the artefact is gone, only
behaviour and the service stack are left, and together they recover about
two fifths of those links — up from a quarter before favicon, template and
TLS were added.
Claiming otherwise would be a lie the evaluation would catch.

---

## Why the corpus is synthetic

Attribution research has no public ground truth. Leaked forum dumps tell you
what people wrote but not who they *were*, so you cannot measure precision
against them — you can only produce plausible-looking output and hope. Every
number in this README exists because the corpus is labelled.

The generator is built to be hard rather than flattering:

- **Idiolects are drawn from 14 archetypes**, not independently, so the corpus
  contains genuinely confusable writers who are different people. Independently
  sampled idiolects make stylometry look perfect and teach you nothing.
- **Operators adapt their style per persona** and jitter their posting times,
  in proportion to their opsec tier.
- **The base rate is 0.51 %.** Accuracy is a useless metric here: answering
  "different actors" to everything scores 99.5 %.
- **Bugs found this way were real.** An early version recycled handle roots
  once the name pool ran dry, producing unrelated actors called `sixthgate` and
  `sixthgate103` and manufacturing false positives no engine could fairly
  reject. It is now a guarded regression test, and confusable handles appear
  only as the controlled T5 trap.

The path to live data is the `CorpusView` interface: a real collector fills the
same structure, and nothing downstream changes. What *would* change is the
calibration, which must be refitted on a labelled sample from the target
population — the reference-population caveat is printed on every report.

---

## Scope and limits

**What this system does not do:**

- It does not attack Tor, deanonymise circuits, or exploit hidden services.
  Every signal is content an operator chose to publish, read the way any
  visitor would read it. There is no scanning and no probing.
- The collector is written for ONIONLAB, services you run yourself. Pointing it
  at third-party onion services raises legal and ethical questions this project
  does not attempt to answer, and its politeness limits are not a substitute
  for permission.
- The OSINT stage fetches nothing by default. It emits checkable URLs, because
  querying a third party discloses your interest in an identifier and that is
  the investigator's decision. `--verify-osint` enables the one lookup
  (Gravatar) that is safe to automate.
- It does not name natural persons. It links pseudonymous accounts to one
  another and quantifies the strength of that link. Identification is a matter
  for lawful process.
- It does not emit a single confidence percentage. Evidence and prior stay
  separable all the way to the page.

**Known limitations**, also printed on every report:

1. Likelihood ratios are only valid for a population resembling the one they
   were calibrated on. A different marketplace, language or era needs
   recalibration.
2. Behavioural channels can be degraded deliberately. Absence of support is not
   support for absence.
3. The English-language stylometry here would need per-language feature sets
   for Hindi, Russian or Chinese boards.
4. Machine output is an investigative aid, never a substitute for corroboration.
5. Live likelihood ratios use a calibration transferred from the benchmark,
   because live data has no labels. They are valid to the extent the benchmark
   resembles the target population. Operational use would require refitting on
   labelled pairs from the real population — a data-collection problem, not a
   modelling one.
6. The tradecraft classifier is trained on simulated tradecraft tiers. Applied
   to live data it is extrapolating, and its output there is a hypothesis.

---

## Layout

```
run.py                      CLI: serve · bench · live · preflight · report · dossiers
anekanta/
  schema.py                 Persona, Evidence, LinkHypothesis, LR caps
  pipeline.py               orchestration and the no-leakage guarantee
  reporting.py              analyst- and court-facing documents
  corpus/generator.py       labelled adversarial benchmark
  engines/
    base.py                 engine contract + rarity weighting
    stylometry.py           char n-grams, Burrows delta, impostors method
    temporal.py             circadian linkage + UTC offset estimation
    crypto.py               co-spend clustering with service quarantine
    pgp.py                  fingerprint, UID and key-timing correlation
    handle.py               alias normalisation and rarity-weighted matching
    infra.py                server fingerprints and device traces
  fusion/
    blocking.py             candidate generation
    lr.py                   calibration and fusion with model selection
    graph.py                identity resolution and dossiers
  evaluation/
    metrics.py              AUC, Cllr, B-Cubed, traps, opsec breakdown
    realworld.py            unlabelled benchmark on the live network
    service.py              favicon, TLS certificate, site template
    neural.py               learned author embedding as a channel
  ai/
    author_net.py           contrastive author embedding (self-supervised)
    tradecraft.py           operator-discipline classifier
  collect/
    fingerprint.py          favicon / TLS / DOM / header fingerprinting
    crawler.py              recursive Tor crawler, rate-limited, robots-aware
    discovery.py            keyword discovery across dark-web indexes (darkdump)
    safety.py               content gate: hard exclusion, fails closed
  osint/                    Dark2Clear (Wangchuk & Rathod 2023)
    mentions.py             clear-web identifier harvesting with provenance
    context.py              automated context setting and priority ranking
    pivot.py                identity correlation and checkable OSINT leads
  live.py                   live analysis with transferred calibration
  preflight.py              container isolation checks
  api/server.py             FastAPI surface
  web/                      dashboard (vanilla JS, no build step)
onionlab/
  docker-compose.yml        the isolation guarantee lives here
  SECURITY.md               threat model, rules, verification
  site/market.py            hardened mock market + forum (one image, two roles)
  tor/torrc                 two hidden services, hardened
  ground_truth.json         operator map and planted leaks, only for grading
Dockerfile                  the analyst application image
docker-compose.yml          the whole platform, one command
tests/                      142 tests, stdlib unittest
```

## Dashboard

Eight views: **Overview** (KPIs, opsec breakdown, trap results),
**Real Network** (keyword discovery and the live-network benchmark: crawl real
onion services, see the safety filtering, and read the infrastructure clusters),
**Live Onion**
(crawl a real hidden service from the browser: streamed progress, service
fingerprint comparison, the clear-web harvest ranked with its reasons, operator
exposure, and the graded result), **Link Graph**
(personas packed by resolved actor, cross-cluster edges flagged), **Linkages**
(ranked pairs, expandable to the per-channel evidence that produced them),
**Resolved Actors** (dossiers with pooled geotemporal assessment),
**Benchmark** (every metric, ablation and the raw report), **Method**.

Any linkage exports to a court-style evidence report stating the propositions
compared, every channel *including the ones that argued against the link*, the
prior, the posterior, and the limitations.

---

## References

- Schiavone, J. *darkdump* — https://github.com/josh0xA/darkdump (MIT). The
  dark-web search-engine endpoints and the Ahmia-blacklist filtering in
  `anekanta/collect/discovery.py` are adapted from it.
- Wangchuk, T. and Rathod, D. (2023) "Opensource intelligence and dark web user
  de-anonymisation", *International Journal of Electronic Security and Digital
  Forensics*, Vol. 15, No. 2, pp.143–157. The Dark2Clear framework implemented
  in `anekanta/osint/`, with the context-setting stage automated.
- Koppel, M. and Winter, Y. (2014) "Determining if two documents are written by
  the same author" — the impostors method, used to rank-normalise both the
  hand-crafted and learned authorship channels.
- Burrows, J. (2002) "Delta: a measure of stylistic difference" — the
  function-word distance in `engines/stylometry.py`.
- ENFSI (2015) *Guideline for Evaluative Reporting in Forensic Science* — the
  likelihood-ratio framework and the verbal scale used in every report.
- Brümmer, N. and du Preez, J. (2006) "Application-independent evaluation of
  speaker detection" — C<sub>llr</sub> and C<sub>llr</sub><sup>min</sup>, which
  this project uses both as a metric and as its model-selection criterion.
- Meiklejohn, S. et al. (2013) "A fistful of Bitcoins" — common-input-ownership
  clustering and the service-address problem addressed in `engines/crypto.py`.
