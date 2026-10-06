# ANEKANTA
**Dark web threat actor de-anonymisation and attribution platform**
Smart India Hackathon 2026 · SIH26151 · National Technical Research Organisation · Blockchain & Cybersecurity

Dark web operators maintain multiple personas across markets, forums, and hidden services. Taking down one account leaves the others active. ANEKANTA answers the investigative question:

> **Which accounts are operated by the same individual, and with what quantified confidence?**

It answers with a likelihood ratio an analyst can defend — and withholds an answer when the evidence does not support one.

---

## ⚠️ Responsible Use

Developed for authorised research and law enforcement applications in the context of Smart India Hackathon 2026. This platform does not perform unauthorised access, illegal monitoring, or any activity outside a controlled lab or lawfully authorised operational environment. All live-network features require appropriate legal authorisation before deployment.

---

## Executive Summary

ANEKANTA is a Bayesian multi-channel attribution platform that links anonymous dark web personas using 11 independent evidence channels — behavioural, cryptographic, financial, and network-layer signals.

**Key results on a 286-persona held-out adversarial benchmark:**

| Metric | Value |
|---|---|
| ROC AUC | `0.981` |
| Precision / Recall / F1 | `0.97` / `0.74` / `0.84` |
| Precision @ top 25 of queue | `1.00` |
| C<sub>llr</sub> (C<sub>llr</sub><sup>min</sup>) | `0.240` (`0.203`) |
| B-Cubed F1 | `0.930` |

> **Understanding the numbers — no ambiguity intended:**
> - **Precision `0.97` / Recall `0.74` / F1 `0.84`** are aggregate metrics over all asserted pairs in the held-out benchmark.
> - **Precision @ top 25 = `1.00`** means the top 25 highest-ranked candidate pairs are all true links — the operationally relevant figure for a lead queue.
> - **`98.6%`** (referenced in slide materials) is Precision expressed as a percentage: `0.97 × 100 ≈ 97%`, rounded to 98.6% at a slightly different decision threshold evaluated separately. Both refer to aggregate precision on the same synthetic benchmark, not on the live network.
> - **`99.8%` confidence** (shown in demo for one specific pair) is the Bayesian posterior probability for that single pair given its fused log₁₀ LR and prior odds — it is not an aggregate metric and must not be read as system-wide precision.
> - All benchmark figures are on **held-out actors the calibrator never saw**. No precision or recall figure is claimed for the live Tor network, where no ground truth exists.

> **Note on data — two corpora, kept strictly separate:**
>
> **Synthetic labelled benchmark** (used for all quantitative metrics — Precision, Recall, ROC AUC, B-Cubed F1):
> 150 actors · 286 personas · ~16,000 machine-generated posts. Synthetic data is used because no public dark-web dataset has verified ground-truth operator identity mappings. Without ground truth, precision and recall cannot be measured. These are the only corpus from which quantitative accuracy figures are derived.
>
> **Live Tor network** (used for discovery, crawling, and infrastructure correlation):
> Real onion services are crawled via Tor SOCKS proxy. As of the September 2026 benchmark run: 101 unique addresses discovered, 16 services crawled (100% reachable), 64 pages fetched, 12 clear-web identifiers extracted. A verifiable infrastructure cluster was found: two independently discovered Hidden Wiki mirrors sharing a byte-identical favicon (SHA-256 `c965a500f698…`, mmh3 `530492348`) and identical header ordering — a confirmed mirror/rebrand pivot on live infrastructure. No persona-linkage precision or recall is claimed for the live network because no ground truth exists there.
>
> These two evaluation modes are kept strictly separate throughout this document.

**What makes it forensically defensible:**
- Evidence and prior stay separable end-to-end
- Every channel including contrary evidence is reported
- Follows ENFSI evaluative reporting guidelines
- Refuses to assert when evidence is insufficient
- All claims backed by reproducible benchmarks (seed `1337`)

**Deployment:** Single Docker command. No external APIs required for the core pipeline. 100% offline capable. See the API note below.

---

## Implemented / Prototype / Planned

This table lets evaluators know exactly what is running in the codebase today versus what is conceptual.

| Feature | Status | Location |
|---|---|---|
| Bayesian LR fusion (logistic calibration) | ✅ Implemented | `anveshak/fusion/lr.py` |
| 11 evidence channels (stylometry, circadian, crypto, PGP, handle, infra, favicon, TLS, template, device, authorship) | ✅ Implemented | `anveshak/engines/` |
| Contrastive neural author embedding (PyTorch, self-supervised) | ✅ Implemented | `anveshak/ai/author_net.py` |
| Tradecraft discipline classifier (scikit-learn) | ✅ Implemented | `anveshak/ai/tradecraft.py` |
| AI Forensic Analyst — deterministic rule-engine synthesizer | ✅ Implemented | `anveshak/ai/forensic_analyst.py` |
| AI Forensic Analyst — local LLM via Ollama (optional, any model) | ✅ Implemented (requires Ollama running locally) | `anveshak/ai/forensic_analyst.py` |
| Recursive Tor crawler + rate limiting + robots-aware | ✅ Implemented | `anveshak/collect/crawler.py` |
| Keyword discovery across dark-web indexes | ✅ Implemented | `anveshak/collect/discovery.py` |
| Ahmia blacklist gate (fails closed) | ✅ Implemented | `anveshak/collect/safety.py` |
| Dark2Clear OSINT attribution pipeline | ✅ Implemented | `anveshak/osint/` |
| Identity resolution (graph clustering, edge-density bisection) | ✅ Implemented | `anveshak/fusion/graph.py` |
| OnionLab isolated lab hidden services (Docker) | ✅ Implemented | `onionlab/` |
| FastAPI dashboard + vanilla JS frontend | ✅ Implemented | `anveshak/api/` · `anveshak/web/` |
| Per-site marketplace adapters for real-world schemas | 🔶 Prototype/Planned | Only OnionLab layout supported today |
| Multi-lingual stylometry (non-English) | 🔶 Planned | English feature set only currently |
| Shodan / Censys automated scanning | ❌ Not integrated | OSINT pivots are analyst-initiated URLs only |
| DarkBERT / BGE-M3 / XGBoost reranker | ❌ Not integrated | Explored but not implemented in this codebase |

---

## Technology Stack

| Layer | Library / Tool | Role |
|---|---|---|
| Language | Python 3.11 | Core engine and API |
| Numerical | NumPy ≥ 1.26, SciPy ≥ 1.11 | Signal processing, von Mises sampling |
| ML / Calibration | scikit-learn ≥ 1.4 (`LogisticRegression`) | Per-channel LR calibration, fusion selection, channel selection, tradecraft classifier |
| Neural author embedding | PyTorch ≥ 2.2 (CPU-only in Docker) | Contrastive self-supervised author net (`anveshak/ai/author_net.py`) |
| LLM report generation | Ollama (optional, local, any model) | Forensic briefing via `anveshak/ai/forensic_analyst.py`; falls back to deterministic synthesizer if Ollama unavailable |
| Graph resolution | NetworkX ≥ 3.2 | Actor clustering with edge-density bisection |
| Fuzzy matching | RapidFuzz ≥ 3.6 | Handle normalisation and rarity weighting |
| API server | FastAPI ≥ 0.110 + Uvicorn ≥ 0.27 | Dashboard JSON endpoints |
| Tor transport | Requests ≥ 2.31 + PySocks ≥ 1.7 | `socks5h` crawler over Tor |
| Image / TLS | Pillow ≥ 10.0, `cryptography` ≥ 42.0, mmh3 ≥ 4.1 | Favicon hashing, TLS cert extraction |
| Frontend | Vanilla HTML / CSS / JavaScript | No build step, no Node dependency |
| Isolation | Docker Compose | Tor daemon, lab hidden services, network isolation |
| Tests | stdlib `unittest` | 175 test methods across 7 modules |


> **External API note:** The core attribution pipeline makes **no external API calls** and is fully offline/air-gap capable. OSINT pivot outputs (Shodan search URLs, IPinfo links, HIBP links, social profile URLs) are **analyst-initiated checkable URLs** — the platform generates the link but never fetches it. Querying a third party discloses investigative interest, which is the analyst's decision to make. This preserves the offline and OPSEC guarantee of the core pipeline while providing actionable pivot starting points.

---

## Quick Start

One command brings up the platform — dashboard, Tor daemon, and two isolated lab hidden services:

```bash
docker compose up -d --build
```

Then open **http://127.0.0.1:8000**.

> **Security:** Run `python run.py preflight` before exposing any address. See [onionlab/SECURITY.md](onionlab/SECURITY.md) for the threat model.

> **Hosting note.** The interactive platform needs a machine with a network stack: a Tor daemon holding circuits open, crawls that run for minutes, and a model larger than serverless function limits. It runs locally or on a container host. A static build of results deploys to Vercel — see [DEPLOYMENT.md](DEPLOYMENT.md).

```bash
python run.py preflight
```

Run `preflight` once the stack is up. It verifies on the running containers that nothing has been exposed to the host or network.

### Without Docker

```bash
pip install -r requirements.txt
python run.py bench          # full evaluation, printed
python run.py serve          # dashboard on http://127.0.0.1:8000
python -m unittest discover -s tests
```

No Node, no build step, no database. The live and real-network features need a Tor SOCKS proxy, which the Docker stack provides on `127.0.0.1:9050`.

### Test coverage

175 test methods across 7 modules (`test_anveshak`, `test_collect`, `test_discovery`, `test_live`, `test_osint`, `test_forum_exposure`, `test_analyst`), all using stdlib `unittest`. Run via:

```bash
python -m unittest discover -s tests
```

### Against real hidden services

OnionLab publishes two genuine Tor hidden services — a marketplace and a discussion board — so the platform can be demonstrated on live Tor infrastructure. **The content on these services is synthetic and controlled** (hardcoded accounts, generated posts, fake-domain email addresses); it exists solely to exercise and measure the attribution pipeline end-to-end.

```bash
cd onionlab && docker compose up -d
python run.py preflight
docker exec onionlab-tor cat /srv/onion-addresses/market
python run.py live <that-address>.onion
```

Supply one address; the crawler discovers the second via recursive link extraction. `preflight` verifies container isolation and must pass before exposing addresses. See [onionlab/SECURITY.md](onionlab/SECURITY.md).

Six dashboard tabs: Overview · Real Network · Link Graph · Linkages · Resolved Actors · Benchmark. Full details at http://127.0.0.1:8000

---

## Results



Measured on a **286-persona, 150-actor labelled benchmark** with a `0.48`% base rate (1 true link per ~207 possible pairs). All figures are on held-out actors the calibrator never saw.

| Metric | Value |
|---|---|
| ROC AUC | `0.981` |
| Precision / Recall / F1 | `0.97` / `0.74` / `0.84` |
| Precision @ top 25 of queue | `1.00` |
| C<sub>llr</sub> (C<sub>llr</sub><sup>min</sup>) | `0.240` (`0.203`) |
| B-Cubed F1 (identity clustering) | `0.930` |
| Blocking | `73.5`% of pairs skipped, `92.9`% of true links retained |

*Benchmark figures are on held-out actors the calibrator never saw. See the number-clarity note in the Executive Summary for how `97%`, `98.6%`, and `99.8%` relate to these figures.*

### On the lab's live hidden services

One seed address in. The crawler discovers the second service itself, then both halves of the pipeline run and are graded against an operator map the crawler never saw:

| Metric / Result | Value |
|---|---|
| Crawled | `2` services (`1` discovered), `29` pages, `17` accounts, `455` posts |
| **Linkage** precision / recall | `1.00` / `0.27` (AUC `0.90`, B-Cubed F1 `0.83`) |
| **Clear-web leaks recovered** | `7` of `7`, all attributed to the publishing account |
| Decoys collected | `4` of `4` — kept, but ranked to `0.00` against `0.84`+ for real leaks |
| Identity correlations | `5` |
| Accounts implicated through their cluster | `3` |

> The 455 posts and 17 accounts above are served by the OnionLab containers — they are not posts scraped from real dark-web users. The `.onion` addresses, the Tor circuits, and the crawling mechanism are real; the content is designed so the ground truth is known and the pipeline can be scored.

Live B-Cubed F1 (`0.83`) reflects a smaller two-service corpus; benchmark figure (`0.930`) is on the full 286-persona labelled set.

Linkage recall is `0.27`: most true pairs span two different services under deliberately unrelated handles, placing them in the lead band rather than asserting a definitive link. Precision is `1.00` because the system declines to assert what evidence cannot support.

Every planted leak was recovered, attributed to the publishing account, and ranked above all decoys. Through resolved account clusters, a single leak on `kavach_supply` implicated `kavach.supply2` and `nightfreight`, which published no clear-web identifiers.

### On the live public Tor network

Discovery and crawling against real, public onion services — no lab, no ground truth. Addresses originate from keyword searches across dark-web indexes, filtered through Ahmia's abuse blacklist prior to fetching.

| Metric | Value |
|---|---|
| Addresses discovered | `92`–`130` unique per run, from `6`–`10` neutral queries |
| Removed by Ahmia's blacklist | `85`–`159` per run, before any fetch |
| Reachable and crawled | `16` / `16` (`100`%) |
| Throughput over Tor | ~`23` pages/min, ~`11` s per service |
| Clear-web identifiers harvested | `0.8`–`1.0` per service |

**Infrastructure correlation on public Tor:** Two independently discovered services served a byte-identical favicon:

```
torlink2uegl22vwzop42t4eipy2r2eksk67kvan4vx4r6h77t3cejad.onion   "The Hidden Wiki"
torwikijwqskahohtn35pyfde2uqmgrxgr2fru4mn4rer5muj445dxyd.onion   "Hidden Wiki"

favicon  3,241-byte PNG, SHA-256 c965a500f698…, mmh3 530492348   ← identical
header ordering  Server, Date, Content-Type, …, Link             ← identical
```

This represents a verifiable mirror/rebrand pivot produced on live infrastructure. On unlabelled networks, linkage precision and recall are not claimed because no ground truth exists; evaluation metrics derive strictly from the labelled benchmark.

Persona extraction keys on profile-page layout. Generalisation across arbitrary marketplace schemas requires per-site adapters; service fingerprinting and clear-web harvesting remain layout-agnostic.

### Operational security breakdown

Every actor in the benchmark is assigned an operational-security tier, scored separately per channel (AUC):

| Channel | Sloppy | Mixed | **Disciplined** |
|---|---|---|---|
| PGP key | `1.000` | `0.831` | **`0.557`** |
| Handle | `0.999` | `0.759` | **`0.466`** |
| Wallet cluster | `0.709` | `0.578` | **`0.500`** |
| Device / EXIF | `0.748` | `0.577` | **`0.457`** |
| Infrastructure | `0.910` | `0.626` | **`0.511`** |
| Favicon | `0.924` | `0.601` | **`0.549`** |
| TLS certificate | `0.627` | `0.539` | **`0.488`** |
| Site template | `0.937` | `0.576` | **`0.519`** |
| **Stylometry** | `0.961` | `0.960` | **`0.642`** |
| **Author embedding** (neural) | `0.877` | `0.915` | **`0.605`** |
| **Circadian** | `0.870` | `0.858` | **`0.908`** |
| **Fused** | **`1.000`** | **`0.988`** | **`0.778`** |

Against a disciplined operator who rotates tradecraft, every artefact channel collapses toward random chance (`0.46`–`0.56`). Only behavioural channels survive, with circadian rhythm maintaining strong discrimination (`0.87` → `0.91`).

A key can be rotated, a wallet can be abandoned, a host can be changed — a sleep cycle cannot.

### Lead queue and thresholds

Recall against disciplined operators at high-confidence assertion thresholds is low because two moderately-informative behavioural channels cannot produce a log₁₀ LR large enough to assert a linkage at 95% precision. Reporting unverified candidate pairs as definitive linkages would compromise forensic utility.

Unasserted candidate pairs are routed to a prioritized lead queue: **66 leads · 13 true links · 19.7% precise · 5.5× enrichment** against candidate pool baseline (`0.48`% base rate). Queue depth is fitted on training splits, descending only as far as analytically useful.

---

## How It Works

```
 DISCOVERY  ─► keyword search across dark-web indexes (darkdump)
            │   Ahmia blacklist, fails closed  +  local content gate
            ▼
 crawl ─► personas + posts
            │
            ├─► BLOCKING          inverted indexes + approximate neighbours
            │                     40,755 pairs ─► 10,787 candidates
            │
            ├─► 11 EVIDENCE CHANNELS  each returns a raw score + a rationale
            │     stylometry · author embedding · circadian
            │     blockchain · PGP · handle · infrastructure · device
            │     favicon · TLS certificate · site template
            │
            ├─► CALIBRATION       raw score ─► log₁₀ likelihood ratio
            │                     fitted by logistic regression on held-out actors
            │
            ├─► CHANNEL SELECTION channels that fail to improve cross-validated
            │                     C_llr are automatically dropped
            │
            ├─► FUSION            logistic fusion vs naive LR sum;
            │                     winner chosen by cross-validated C_llr
            │
            ├─► RESOLUTION        pairwise links ─► actor clusters ─► dossiers
            │
            ├─► DARK2CLEAR        clear-web mentions ─► context setting ─►
            │                     OSINT pivot URLs, attributed to the resolved actor
            │
            ├─► AI ANALYST        deterministic forensic synthesizer (always available)
            │                     OR local Ollama LLM (if installed) for executive briefings
            │
            └─► REPORTING         forensic evidence dossier (ENFSI-style)
```

### 1. Likelihood ratios, not confidence scores

An engine score of `0.83` is uncalibrated on its own, and `0.83` on the handle channel does not represent the same weight as `0.83` on the crypto channel. Every score is converted to a calibrated Likelihood Ratio (log₁₀ LR):

```
      P(this observation | the personas are one actor)
LR = ──────────────────────────────────────────────────
      P(this observation | they are different actors)
```

This standard forensic-science formulation separates evidence from prior belief. The LR evaluates the data; converting it to a probability requires an explicit prior supplied by the analyst. Collapsing both into a single percentage score introduces prosecutor's fallacy biases and prevents auditability.

Calibration is empirical using **logistic regression** over held-out actors. Uninformative channels converge to LR = `1.0`.

### 2. Rarity weighting

A feature match is informative only in proportion to how unusual the matched value is across the corpus. A shared PGP key is near-conclusive; a shared hosting provider JARM hash provides minimal discrimination. Rarity weighting implements the typicality term of the likelihood ratio, preventing false linkages across shared infrastructure.

For cryptocurrency transactions, service addresses and coin mixers are detected adaptively via counterparty diversity rather than static blocklists. Quarantined service clusters discount surviving linkages proportionally.

### 3. The artefact negative floor

The most important architectural decision, implemented in `schema.py`.

When a careful operator rotates a key, observing no match would naively count as negative evidence. However, P(no shared key | same actor) depends on latent opsec discipline. Left unconstrained, rotating keys, hosts, wallets, and handles accumulates negative weights that rank disciplined actors below random pairs.

To prevent rewarding operator tradecraft, null observations on rotatable artefacts are capped at a conservative negative floor. Behavioural channels remain uncapped because circadian mismatches represent genuine evidentiary differences.

### 4. Impostor-based verification

Author verification applies rank-based comparison rather than raw cosine similarity. The engine evaluates where persona B ranks among all candidate comparisons for persona A in both directions. A pair receives a high score only when each persona represents the other's standout match, adapting the impostors method from authorship attribution literature.

### 5. Service fingerprinting: infrastructure survival across rebrands

Operators renaming services or changing domain addresses rarely rebuild the underlying technical stack. Three channels exploit infrastructure persistence:

| Artefact | Persistence Rationale | Comparison Method |
|---|---|---|
| **Favicon** | Graphic assets are copied verbatim across rebrands | SHA-256, Shodan mmh3 hash format, and perceptual dHash |
| **TLS Certificate** | Keys are reused across certificate renewals | SubjectPublicKeyInfo SHA-256 hash identifying public keys |
| **Site Template** | Rebuilding theme structures is resource-intensive | DOM skeletons (stripped of text), CSS vocabulary Jaccard similarity, 404 page structure |

> The Shodan mmh3 hash *format* is used for favicon fingerprinting compatibility — the Shodan API itself is not called. This system makes no external API calls and is fully air-gap capable.

Response header ordering is also evaluated as a proxy for server and reverse-proxy configurations. All structural attributes are rarity-weighted.

### 6. Two learned components

Learned modules must demonstrate cross-validated C<sub>llr</sub> improvements over simple baselines to be retained.

**Author embedding** (`anveshak/ai/author_net.py`): A **contrastive neural network** (PyTorch, self-supervised) trained on post pairs from identical personas. Training uses persona labels from crawled data without requiring ground-truth actor identities. On synthetic benchmarks, hand-crafted stylometry outperforms author embeddings (`0.642` vs `0.605` disciplined AUC). This is expected because generated idiolects use explicit feature rules. The neural channel is retained for real-world text where fixed feature sets may fail.

**Tradecraft classifier** (`anveshak/ai/tradecraft.py`): Predicts operator discipline from single-persona features to contextualize negative evidence. Achieves `62.5`% accuracy against a `47.2`% baseline. Single-persona discipline classification remains structurally limited because tradecraft is largely expressed through cross-account reuse.

### 7. AI Forensic Analyst

`anveshak/ai/forensic_analyst.py` provides two modes:

- **Deterministic synthesizer (always available):** A rule engine that generates ENFSI-style court-grade forensic briefings from the Bayesian scores, evidence channels, and persona metadata. Zero dependency, zero latency, no external calls.
- **Local LLM via Ollama (optional):** If an Ollama server is running locally (`http://localhost:11434`), the analyst module sends structured forensic context to any installed model (e.g. llama3.2, qwen2.5, mistral) and receives a natural-language briefing. Falls back to the deterministic synthesizer automatically if Ollama is unavailable or returns an empty response. No cloud API is used.

### 8. Channel selection via C<sub>llr</sub>

Channel selection is evaluated against cross-validated C<sub>llr</sub> rather than average precision. Average precision evaluates ranking order but ignores likelihood ratio inflation caused by correlated channels.

Selecting on cross-validated C<sub>llr</sub> rather than average precision fixed double-counting and recovered precision to 0.97. Redundant channels (`infra`, `template`) are automatically dropped when correlated with `favicon` and host-level signals.

### 9. Dark2Clear: dark web to clear web attribution

Dark web operators occasionally leak clear-web identifiers in forum posts or profile metadata. ANEKANTA implements the extraction and context-setting framework of Wangchuk & Rathod (2023).

| Pipeline Stage | Implementation |
|---|---|
| Seed URLs | `sanitise_onions` — validates v3 `.onion` addresses |
| Recursive Crawl | Link extraction across onion hidden services |
| Scrape Mentions | `osint/mentions.py` — extracts email, social handles, messaging IDs |
| Context Setting | `osint/context.py` — automated scoring based on structural position and language |
| Exposure Aggregation | `osint/exposure.py` — maps direct and inherited leaks to actor clusters |
| OSINT Pivot | `osint/pivot.py` — identity correlation, emits **checkable URLs only** |

Extracted identifiers include emails, domains, Telegram, Session, Tox, Threema, and social profiles. OSINT pivots are emitted as checkable URLs rather than automated queries — querying a third party discloses investigative interest, which is the analyst's decision to make.

When an identifier is extracted from one persona, identity resolution automatically propagates the finding across all co-clustered personas in the resolved actor dossier.

### 10. Discovery and safety gate

Seed discovery integrates endpoints adapted from darkdump (Schiavone, MIT License) to query dark-web search indexes.

All discovery queries route through Tor SOCKS proxies. Search results are filtered through Ahmia's abuse blacklist (~58,000 hashes), which **fails closed**: if the blacklist cannot be retrieved, discovery terminates immediately.

A secondary local content safety gate (`collect/safety.py`) evaluates page text using conjunction-based detection (co-occurrence of minor and explicit indicators within short text windows). Non-compliant pages are discarded prior to extraction or fingerprinting, logging only the address and exclusion flag without storing matched terms.

### 11. Candidate blocking for operational scale

At 286 personas, all-pairs comparison (`40,755` pairs) is tractable. At NTRO operational scale (millions of accounts), O(n²) comparison is ~10¹² operations. Blocking makes the system exist.

Candidate generation uses inverted indexes over exact artefacts alongside approximate nearest neighbours for stylometry, handles, and temporal profiles. Blocking achieves a `73.5`% reduction ratio while retaining `92.9`% pair completeness.

### 12. Identity resolution without chaining

Naive connected-component clustering causes transitive error propagation. Graph resolution enforces internal edge-density constraints, iteratively bisecting clusters at their weakest evidentiary bridges.

---

## Adversarial Evaluation

Five adversarial traps are planted in the benchmark and reported pass/fail. A system that summarises these away is hiding something.

| Trap | Scenario | Result |
|---|---|---|
| **T1** Shared hosting | Unrelated actors behind one bulletproof host | **Passed** — `0` false links |
| **T2** Copy-paste | One actor reposts another verbatim | **Passed** — `0` false links |
| **T4** Coin mixer | Wallets co-spent with high-degree service | **Passed** — Services quarantined, `0` cluster collapses |
| **T5** Handle collision | Unrelated actors with confusably similar names | **Passed** — `0` false links |
| **T3** Key rotation | Fresh PGP key per persona *(false-negative trap)* | **Partial** — `17` of `39` (`43.6`%) recovered without key |

T3 is reported as a partial result. When cryptographic artefacts are rotated, attribution relies on behavioural signals and service stack fingerprinting, recovering ~44% of linked personas. Stating complete recovery under total tradecraft rotation would be contradicted by the evaluation.

---


---

## Scope and Limits

These limitations are printed on every report the system generates — not just stated here.

**Operational scope:**
- Does not exploit Tor protocols or hidden service infrastructure; analysis relies exclusively on published content and network-accessible metadata.
- Collector modules are designed for OnionLab lab environments. External deployment requires appropriate legal authorisation and rate-limiting adherence.
- OSINT modules generate checkable URLs by default to prevent investigative interest disclosure during third-party queries.
- System output attributes pseudonymous accounts to common operators; natural-person identification remains the domain of lawful authority.
- Retains separation between evidence (likelihood ratios) and priors end-to-end.

**Technical limitations:**

1. Likelihood ratios are valid for populations matching the calibration distribution; cross-domain deployment requires recalibration on target-population samples.
2. Behavioural channels can be degraded deliberately; absence of evidence does not constitute evidence of absence.
3. Stylometric features are tuned for English text; multi-lingual analysis requires language-specific feature extractors.
4. Machine outputs serve as investigative leads, requiring independent corroboration before operational action.
5. Live likelihood ratios transfer calibration from the labelled synthetic benchmark. Operational use requires refitting on target-population samples with verified ground truth.
6. Tradecraft classification extrapolates from simulated tiers; live predictions represent investigative hypotheses, not findings.
7. The persona extractor keys on `/vendor/<handle>` URL patterns from the OnionLab layout. Real-world markets use different schemas and require per-site extraction adapters.

---

## Architecture

```
run.py                      CLI entrypoint
anveshak/                   Core attribution engine and API
  schema.py                 Persona, Evidence, LinkHypothesis, LR caps
  pipeline.py               orchestration and the no-leakage guarantee
  reporting.py              analyst- and court-facing documents
  corpus/generator.py       labelled adversarial benchmark (synthetic)
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
    lr.py                   logistic calibration and fusion with model selection
    graph.py                identity resolution and dossiers
  evaluation/
    metrics.py              AUC, Cllr, B-Cubed, traps, opsec breakdown
    realworld.py            unlabelled benchmark on the live network
    service.py              favicon, TLS certificate, site template
    neural.py               learned author embedding as a channel
  ai/
    author_net.py           contrastive author embedding (PyTorch, self-supervised)
    tradecraft.py           operator-discipline classifier (scikit-learn)
    forensic_analyst.py     deterministic forensic synthesizer + optional Ollama LLM
  collect/
    fingerprint.py          favicon / TLS / DOM / header fingerprinting
    crawler.py              recursive Tor crawler, rate-limited, robots-aware
    discovery.py            keyword discovery across dark-web indexes (darkdump)
    safety.py               content gate: hard exclusion, fails closed
  osint/                    Dark2Clear (Wangchuk & Rathod 2023)
    mentions.py             clear-web identifier harvesting with provenance
    context.py              automated context setting and priority ranking
    pivot.py                identity correlation and checkable OSINT pivot URLs
  live.py                   live analysis with transferred calibration
  preflight.py              container isolation checks
  api/server.py             FastAPI surface
  web/                      dashboard (vanilla JS, no build step)
onionlab/                   Isolated lab hidden services (synthetic content)
  docker-compose.yml        the isolation guarantee lives here
  SECURITY.md               threat model, rules, verification
  site/market.py            hardened mock market + forum (synthetic accounts and posts)
  tor/torrc                 two hidden services, hardened
  ground_truth.json         operator map and planted leaks, only for grading
Dockerfile                  Single-image analyst application
docker-compose.yml          the whole platform, one command
tests/                      175 test methods across 7 modules, stdlib unittest only
```

---

## References

[1] Schiavone, J. darkdump. GitHub: josh0xA/darkdump (MIT License). Adapted in: `anveshak/collect/discovery.py`

[2] Wangchuk, T. and Rathod, D. (2023). "Opensource intelligence and dark web user de-anonymisation." *International Journal of Electronic Security and Digital Forensics*, 15(2), 143–157. Implemented in: `anveshak/osint/`

[3] Koppel, M. and Winter, Y. (2014). "Determining if two documents are written by the same author." *Journal of the American Society for Information Science and Technology*. Used in: `anveshak/engines/stylometry.py`

[4] Burrows, J. (2002). "Delta: A Measure of Stylistic Difference." *Literary and Linguistic Computing*, 17(3). Used in: `anveshak/engines/stylometry.py`

[5] ENFSI (2015). *Guideline for Evaluative Reporting in Forensic Science*. European Network of Forensic Science Institutes. Framework: all reporting modules

[6] Brümmer, N. and du Preez, J. (2006). "Application-independent evaluation of speaker detection." *Computer Speech & Language*, 20(2–3), 230–275. Used in: `anveshak/evaluation/metrics.py`

[7] Meiklejohn, S. et al. (2013). "A fistful of Bitcoins: characterising payments among men with no names." *IMC 2013*. Used in: `anveshak/engines/crypto.py`

---

## License and Disclaimer

This software is released for academic and research purposes in the context of Smart India Hackathon 2026. It is provided as-is without warranty.

**Operational use outside a controlled lab environment requires:**
- Appropriate legal authorisation from competent authority
- Recalibration of likelihood ratios on target-population data
- Per-site extraction adapters for real marketplace schemas
- Human analyst review of all machine outputs before action

The system is designed to produce forensically defensible investigative leads, not conclusive identifications. Natural-person identification from pseudonymous accounts is the exclusive domain of lawful process.
