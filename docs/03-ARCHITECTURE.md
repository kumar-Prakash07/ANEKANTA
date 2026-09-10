# Architecture and infrastructure

*What runs where, what talks to what, and what happens when you point this at
something bigger than a lab.*

---

## 1. Deployment topology

Four containers. The interesting part is what is **not** connected to what.

```
┌─ HOST (your machine) ──────────────────────────────────────────────┐
│                                                                    │
│   Browser ──► 127.0.0.1:8000 ──► ┌──────────────────────────┐      │
│                                  │  anekanta                │      │
│   Analyst CLI ──────────────────►│  dashboard + API         │      │
│                                  │  engines · fusion · AI   │      │
│                                  └────────────┬─────────────┘      │
│                                               │ socks5h            │
│                                  127.0.0.1:9050                    │
└───────────────────────────────────────────────┼────────────────────┘
                                                │
┌─ DOCKER ───────────────────────────────────────┼───────────────────┐
│                                    ┌───────────▼──────────┐        │
│   edge network ────────────────────│  tor                 │        │
│   (internet: Tor network)          │  SOCKS + 2 hidden    │        │
│                                    │  services            │        │
│                                    └───┬──────────────┬───┘        │
│                                        │              │            │
│   backend network  ── internal: true ──┼──────────────┼──────      │
│   NO GATEWAY. NO INGRESS. NO EGRESS.   │              │            │
│                              ┌─────────▼───┐  ┌───────▼──────┐     │
│                              │  market     │  │  forum       │     │
│                              │  onionlab   │  │  onionlab    │     │
│                              │  NO PORTS   │  │  NO PORTS    │     │
│                              └─────────────┘  └──────────────┘     │
└────────────────────────────────────────────────────────────────────┘
```

### The three things that make this safe

**The mock services publish no host port.** There is no `ports:` key on either.
Nothing is bound on your machine — not on your LAN, not on your wifi, not on
the internet. The only process on earth that can open a socket to them is the
Tor container, over an internal Docker network.

**`backend` is `internal: true`.** Docker attaches no gateway to an internal
network. Nothing routes in and nothing routes out. If a mock service were ever
compromised it could not reach your router, your other machines, or the
internet. `run.py preflight` *proves* this at runtime by attempting an outbound
connection from inside each container and confirming it fails.

**Tor's SOCKS port is `127.0.0.1:9050:9050`.** The loopback prefix is
load-bearing. `"9050:9050"` would bind `0.0.0.0` and hand your entire local
network an anonymising proxy whose traffic looks like yours.

### Volume separation

| Volume | Contents | Mounted into |
|---|---|---|
| `hs_keys` | hidden service **private keys** | the Tor container **only** |
| `onion_pub` | the `.onion` **addresses**, nothing else | Tor (write), both sites (**read-only**) |

The two mock services link to each other, so each needs its sibling's address —
public by design. The private key sitting next to it is not. An earlier version
mounted the key directory into the sites and loosened its permissions so an
unprivileged process could traverse it. That works, and it is the wrong shape:
it puts private keys one bug away from a process that accepts input from
strangers. `preflight` checks this explicitly.

### Container hardening

Both mock services run `read_only: true`, `cap_drop: [ALL]`,
`no-new-privileges:true`, as uid 10001, with a `noexec` tmpfs, `mem_limit`
192 MB and `pids_limit` 64.

The application itself is pure standard library — no subprocess, no `eval`, no
template engine, no database, and **no file read driven by a request path**,
which is what makes path traversal structurally impossible rather than
filtered.

Full threat model: [`onionlab/SECURITY.md`](../onionlab/SECURITY.md).

---

## 2. Module map

39 Python modules, ~10,000 lines.

```
anekanta/
  schema.py          Persona · Post · Evidence · LinkHypothesis; LR caps
  pipeline.py        orchestration and the no-leakage guarantee
  live.py            live analysis with transferred calibration
  reporting.py       analyst- and court-facing documents
  preflight.py       container isolation checks

  collect/           ── acquisition ────────────────────────────────
    discovery.py     search engines + Ahmia blacklist (from darkdump)
    safety.py        local content gate, independent of the blacklist
    crawler.py       recursive Tor-only crawler
    fingerprint.py   favicon · TLS · DOM · CSS · headers

  engines/           ── evidence, one channel each ─────────────────
    base.py          engine contract + rarity_weight()
    stylometry.py    char n-grams · Burrows delta · impostors method
    neural.py        learned author embedding as a channel
    temporal.py      circadian linkage + UTC offset estimation
    crypto.py        co-spend clustering with service quarantine
    pgp.py           fingerprint · UID · key-timing
    handle.py        alias normalisation + rarity
    infra.py         SSH key · JARM · header order · host
    service.py       favicon · TLS certificate · site template

  fusion/            ── turning scores into a finding ──────────────
    blocking.py      candidate generation
    lr.py            calibration, channel selection, fusion
    graph.py         identity resolution and dossiers

  osint/             ── Dark2Clear (Wangchuk & Rathod 2023) ────────
    mentions.py      clear-web identifier harvesting with provenance
    context.py       automated context setting and ranking
    pivot.py         identity correlation and checkable leads

  ai/                ── learned components ─────────────────────────
    author_net.py    contrastive author embedding (self-supervised)
    tradecraft.py    operator-discipline classifier

  corpus/generator.py    labelled adversarial benchmark
  evaluation/metrics.py  AUC · Cllr · B-Cubed · traps · opsec breakdown
  evaluation/realworld.py public-network benchmark harness
  api/server.py          21 endpoints
  web/                   dashboard, vanilla JS, no build step
```

### Why the layering is strict

`Evidence` is the **narrow waist**. Every engine, however different its
internals, reduces its finding to `(score, log10_lr, rationale, supporting)`.
Engines never compute their own confidence — that happens once, centrally, in
`fusion/lr.py`, against held-out data. Engines that invent confidence numbers
are how attribution systems end up uncalibrated.

`CorpusView` is what an engine is allowed to see. Notably absent:
`true_actor`. The labels exist only for scoring.

---

## 3. Data flow and state

**The pipeline is a pure function of (corpus, seed).** Every number is
deterministic. That is what makes the static export legitimate: results can be
computed once and served as JSON without becoming a mock-up.

**The API holds one immutable `Result` in memory.** Every read endpoint is a
pure function of it; nothing mutates state. Live crawls run on a worker thread
with a lock — one at a time, because two concurrent crawls double the load on a
target for no benefit and interleave their progress into something unreadable.

**Live analysis splits its inputs deliberately:**

| What | Comes from | Why |
|---|---|---|
| Rarity statistics | the **live** population | "How unusual is this favicon?" is a question about the population you are actually looking at. A stock icon on half of one market is uninformative there regardless of the benchmark. |
| Likelihood ratios | the **benchmark** | Converting a score to an LR needs labelled pairs, and live data has none. |

That second row is the reference-population assumption printed on every report:
the numbers are valid to the extent the benchmark resembles the target. Stating
it plainly is better than pretending a number is unconditional.

---

## 4. Scaling

The lab is 286 personas. Here is what changes at real scale, honestly.

| Stage | Cost | At 10⁶ personas |
|---|---|---|
| Discovery | linear in queries | fine |
| Crawling | **the bottleneck** — ~15 s/service over Tor | embarrassingly parallel across circuits; measured at 16.4 pages/min single-threaded |
| Blocking | O(n) index build, O(1) probe | fine; kNN becomes LSH or a vector index — the interface does not change |
| Scoring | O(candidates) | the reason blocking exists |
| Stylometry | TF-IDF → **truncated SVD to 200 dims** | densifying a 20k-column matrix does not survive contact with a real corpus; the SVD is computed once and leaves every comparison cheap |
| Impostor ranking | O(n²) similarity matrix | at scale the cohort becomes the blocking candidate set; the method is unchanged |
| Calibration | fits on a sample | unaffected |

**What would need real work:** persistence. The current design recomputes from
scratch. A production instance would persist the scored graph and update
incrementally as the crawler delivers new accounts — which is why every read
endpoint is already a pure function of one immutable object, so that swap is
localised.

**What would not:** the engines, the calibration and the reporting are already
population-agnostic. They take a `CorpusView` and do not care where it came
from.

---

## 5. Hosting options

| Target | Works? | Notes |
|---|---|---|
| **Local (`docker compose up -d`)** | fully | the intended shape |
| **Container host** (Fly, Railway, Render, VPS) | fully | must **not** publish the Tor SOCKS port — an open SOCKS proxy is found and abused within hours. Must put authentication in front of a dashboard that can start crawls. |
| **Vercel / serverless** | **static only** | Tor needs a persistent process; crawls run 2–8 min against a 10–300 s function limit; PyTorch + scikit-learn is ~1.2 GB against a 250 MB bundle cap; functions are stateless |

The serverless split is not a workaround, it is the honest shape: the analysis
needs a machine with a network stack, and the evidence it produces is just data.
`export_static.py` produces a 1.8 MB build with the real results of a real run —
every tab populated, the two crawl buttons disabled and relabelled *(local
only)*, and a banner saying so rather than leaving a visitor to discover it by
clicking something dead.

Details: [`DEPLOYMENT.md`](../DEPLOYMENT.md).

---

## 6. Dependencies

| Package | Used for | Optional? |
|---|---|---|
| numpy, scipy, scikit-learn | features, calibration, metrics | no |
| networkx | identity resolution | no |
| rapidfuzz | handle similarity | no |
| requests + PySocks | Tor-routed HTTP | no |
| mmh3 | Shodan favicon convention | no |
| cryptography | X.509 parsing | no |
| Pillow | perceptual image hashing | no |
| fastapi + uvicorn | API and dashboard | no |
| **torch** | learned author embedding | **yes** — the pipeline degrades gracefully; the channel reports "unavailable" and selection proceeds without it |

No JavaScript build step, no bundler, no framework. The dashboard is vanilla —
which at a demonstration is the difference between showing the work and
apologising for it.

---

## Next

- [User guide](04-USER-GUIDE.md) — running an investigation
- [Build notes](05-BUILD-NOTES.md) — decisions and what went wrong
