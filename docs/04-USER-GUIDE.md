# User guide

*How to actually run an investigation with this, from a cold machine to a
document you can hand to a supervisor.*

---

## 0. Install and start

Requires **Docker** and, for the CLI, **Python 3.11+**. It does **not** require
Tor installed on your host — and it should not be, because keeping Tor in a
container is what makes the network isolation work.

```bash
git clone https://github.com/anonsurf004/anekanta.git
```

```bash
cd anekanta && docker compose up -d --build
```

First start takes a few minutes: it trains the calibration before serving.
Follow it with `docker compose logs -f anekanta`.

**Before you show anyone an address, verify the isolation:**

```bash
python run.py preflight
```

Every check must pass. It inspects the *running* containers rather than the
compose file — a stale container or a port published by something else will
pass a file review and fail here. Read
[`onionlab/SECURITY.md`](../onionlab/SECURITY.md) once, properly.

Then open **<http://127.0.0.1:8000>**.

---

## 1. The eight tabs, and what each is for

| Tab | Question it answers | Read it when |
|---|---|---|
| **Overview** | Is this system working, and how well? | first, always |
| **Live Onion** | Who is behind the accounts on *this* service? | you have a target |
| **Real Network** | Does this work outside the lab? | you doubt the lab |
| **Link Graph** | What does the operator landscape look like? | triaging |
| **Linkages** | Why does it believe these two accounts are one person? | before acting on a finding |
| **Resolved Actors** | Everything known about one operator | writing it up |
| **Benchmark** | Can I defend these numbers? | someone challenges you |
| **Method** | What does it do and refuse to do? | explaining it to others |

### Overview — start here

Six KPIs, then two panels that matter more:

**Detection rate by operator discipline.** Careless operators: 100 %. Careful
operators: near zero at the assertion threshold. That second number is not a
failure — it is the system declining to assert what it cannot support, and
those pairs appear in the lead queue instead.

**Which channel survives tradecraft.** The heat map. Read it left to right: PGP
1.00 → 0.56, handle 1.00 → 0.47, favicon 0.92 → 0.55 — chance. Stylometry holds
at 0.64, circadian at **0.91**. This is the finding the tool exists to exploit.

Below that, the **adversarial traps**: five cases planted specifically to
produce wrong answers, reported pass/fail rather than summarised away.

### Live Onion — the investigation tab

1. The local lab address is prefilled. Paste your own target to replace it.
2. Set how many services the recursive crawl may follow (default 4).
3. **Crawl and analyse.** Takes minutes; progress streams live.

Then, top to bottom:

- **Services discovered** — which addresses were supplied vs *found by reading
  pages*. One seed in, more out.
- **Service fingerprints** — a column per service. **Amber = identical across
  all of them.** That is the rebrand signature: same favicon, same TLS public
  key, same DOM skeleton on two different addresses means the same deployment.
- **Clear-web mentions** — the Dark2Clear harvest, ranked, each with the
  *reason* it ranks there. High band first.
- **Operator exposure** — where the two halves meet, and the panel to read
  twice. A leak on one account, and the accounts it implicates **that leaked
  nothing themselves**.
- **Developed pivots** — each identifier turned into checkable claims. Nothing
  is fetched; the links are for you to open deliberately.
- **Accounts and linkages** — ⇗ marks a pair spanning two services, the hard
  case.
- **Graded against the lab** — only possible because the lab's operator map is
  known. Against a third-party service there is no such file, and the correct
  output is hypotheses with no accuracy figure.

### Linkages — the tab you must understand

Click any row to expand the per-channel breakdown. You will see something like:

```
crypto        +2.20   strong support for same actor
              identical receiving address published by both personas
              verify: shared_address=18wPB5sm5Npby0rDCYLj0Cgs1IVtXa8

pgp           +1.47   moderate support for same actor
              identical PGP fingerprint FCA3FC616B44DA89 (held by 2 personas)

stylometry    +1.16   moderate support for same actor
              mutual impostor rank 1.000, char n-gram cos 0.646

infra         +0.33   weak support for same actor
              ssh_hostkey matches, held by 21 of 289 personas (7.3%)
              -- uncommon but not unique

pgp           -0.50   weak support for DIFFERENT actor
              distinct fingerprints (key rotation); no secondary traces
```

Three things to take from that:

- **Every channel is shown, including negatives.** A channel arguing *against*
  the link is not hidden.
- **Every rationale is verifiable by hand.** `verify:` lines give you the exact
  value to go and check on the page yourself.
- **Rarity is stated in the text**, not just applied in the arithmetic. "held
  by 21 of 289 (7.3 %)" tells you why it only contributed +0.33.

**Open full report** renders the court-style document.

---

## 2. The command line

Eight commands. The dashboard is a view onto the same pipeline.

```bash
python run.py bench
```
Full evaluation on the labelled benchmark. Prints discrimination, operating
point, calibration, per-tier recall, the channel-survival table, and trap
results. Add `--json` for the raw report.

```bash
python run.py serve
```
Dashboard on 127.0.0.1:8000. `--port` to change.

```bash
python run.py live <address>.onion
```
Crawl a live service and analyse it. `--max-onions N` bounds recursive
discovery; `--verify-osint` enables the one safe live lookup (Gravatar).

```bash
python run.py discover --queries "market,forum" --engines tordex,tor66
```
Find onion addresses via search engines, Ahmia-filtered.

```bash
python run.py realworld --services 16 --pages-each 4 --out realworld-report.json
```
Benchmark against the **public Tor network**: discovery, reachability,
throughput, and what the engines find on services nobody staged.

```bash
python run.py report <persona_a> <persona_b>
```
The court-style evidence report for one pair, to stdout.

```bash
python run.py dossiers
```
Every resolved actor, consolidated.

```bash
python run.py preflight
```
Container isolation verification.

---

## 3. Reading a likelihood ratio

This is the part most people get wrong, so it is worth being precise.

The system reports **log₁₀ LR**. A value of 3.0 means the evidence is about
**1,000 times more probable** if the accounts share an operator than if they do
not.

**It does not mean there is a 1,000:1 chance they are the same person.** That
would require a prior. The report prints the prior separately and shows the
posterior as the consequence of combining them, precisely so the two never get
conflated.

| log₁₀ LR | Verbal scale | What to do |
|---|---|---|
| < 1.0 | insufficient | nothing; below the assertion floor |
| 1.0 – 2.0 | investigative lead | worth an analyst's time, not a finding |
| 2.0 – 3.0 | corroborated linkage | assertable with corroboration |
| > 3.0 | high-confidence linkage | assertable |

The **assertion threshold is fitted on the training split**, targeting ≥95 %
precision, with a hard floor at log₁₀ LR = 1.0. Below that floor the system
refuses to assert regardless of what the optimiser would prefer — a threshold
can be statistically optimal and still be the wrong thing to put in front of an
analyst.

### The lead queue

Pairs below the threshold but above the lead floor are emitted as **leads**.
On the benchmark: 66 pairs, 13 true, **19.7 % precise against 3.6 % in the
scored pool — a 5.5× enrichment**.

The queue's depth is itself fitted, descending only as far as it stays worth
working. Leads are never findings, and the UI labels them so.

---

## 4. A worked investigation

**Target:** a marketplace you have an address for.

**Step 1 — crawl.** Live Onion tab, paste the address, set services to 4.

**Step 2 — check what was discovered.** Did it find sibling services? If the
Service Fingerprints panel shows amber rows, those services are the same
deployment, whatever they call themselves.

**Step 3 — work the linkages, top down.** Precision@25 is 1.00 on the
benchmark: the top of the queue is reliable. Open each and read the channel
breakdown. Ask: *would I be comfortable defending this in writing?*

**Step 4 — read the clear-web harvest.** High band only, at first. For each,
the "why it ranks here" column tells you whether it is a vendor soliciting
contact or a footer address.

**Step 5 — check operator exposure.** This is the highest-value panel. If a leak
attaches to a cluster, every account in that cluster is implicated by a mistake
made on one of them.

**Step 6 — develop the pivots yourself.** The tool constructs URLs; it does not
open them. Decide deliberately, from wherever you choose to work — querying a
third party discloses your interest in an identifier.

**Step 7 — export.** "Open full report" on each finding you intend to rely on.
The document states the propositions, every channel, the prior, the posterior,
and the limitations.

**Step 8 — corroborate.** Machine output is an investigative aid. Nothing here
substitutes for lawful process.

---

## 5. Interpreting a *negative* result

The most misused output. "No linkage found" means one of three different
things:

| What you see | What it means | What to do |
|---|---|---|
| No linkage, tradecraft says **sloppy** | probably genuinely unconnected — artefact channels would have fired | move on |
| No linkage, tradecraft says **disciplined** | the artefact channels were *expected* to be silent. Their silence is evidence of care, not innocence | check the lead queue; weight behavioural channels |
| No linkage, few posts | not enough text or timestamps to profile | collect more before concluding |

The tradecraft classifier exists for exactly this distinction — and is honest
about being weak at it (62.5 % vs a 47.2 % baseline, missing 75 % of
disciplined operators). Treat it as triage, not as an answer.

---

## 6. Common problems

**"no Tor SOCKS proxy at 127.0.0.1:9050"** — the lab is not running.
`cd onionlab && docker compose up -d`, then wait ~40 s for descriptors.

**Crawl returns no accounts** — the extractor expects profile pages at
`/vendor/<handle>`. A different market's layout needs an extraction pattern in
`crawler.py::_extract`.

**Live recall looks low** — expected when true pairs span services under
unrelated handles. Check AUC (ranking quality) rather than recall, and read the
lead queue.

**Dashboard slow to start** — it trains the author embedding before serving.
`docker compose logs -f anekanta`.

**`cd F:\New\anekanta` fails in WSL** — bash eats the backslashes. Use
`/mnt/f/New/anekanta`.

---

## 7. Rules of use

- Point the collector at services **you operate** or have authorisation to
  examine. Its politeness limits are not a substitute for permission.
- Do not publish the Tor SOCKS port. An open SOCKS proxy is found and abused
  within hours, and its traffic looks like yours.
- Do not put authentication-free dashboards on the internet. This one can start
  crawls.
- Recalibrate before operational use. The shipped LRs are fitted against a
  simulated population.
- Treat `hs_keys` as secret material. Anyone holding it can impersonate your
  service at your address.

---

## Next

- [Why this matters](01-WHY-THIS-MATTERS.md) · [How it works](02-HOW-IT-WORKS.md)
- [Architecture](03-ARCHITECTURE.md) · [Build notes](05-BUILD-NOTES.md)
