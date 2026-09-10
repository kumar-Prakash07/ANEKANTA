# Build notes

*How this was built, the decisions that shaped it, and the bugs that changed
the design. Written because the failures are more instructive than the
successes, and because a reviewer who knows where it broke can judge the rest.*

---

## 1. The benchmark came first, and that decided everything

Attribution research has no public ground truth. Leaked forum dumps tell you
what people wrote but not who they *were*, so you cannot measure precision
against them — you can only produce plausible-looking output and hope.

So the first component built was the corpus generator, not an engine. Every
number in this project exists because the corpus is labelled.

**The first version was useless.** AUC 1.00. Perfect scores on every channel.
The reason was that each simulated actor's traits were drawn independently, so
the population partitioned cleanly and any method looked brilliant.

Three rounds of deliberately making it harder:

**Idiolect archetypes.** Writing styles are now drawn from 14 archetypes and
perturbed, so the corpus contains genuinely confusable writers who are
different people. Independently sampled idiolects make stylometry look perfect
and teach you nothing.

**Operational-security tiers.** Every actor is sloppy, mixed or disciplined,
governing how often they reuse each artefact. This is the change that produced
the project's central finding, and it was introduced because a benchmark where
everyone is careless measures nothing useful — real investigations are decided
by the disciplined minority.

**Five adversarial traps**, planted to produce specific wrong answers:

| Trap | What it induces | Result |
|---|---|---|
| Shared bulletproof host | false positive | held, 0 false links |
| Verbatim copy-paste | false positive | held, 0 false links |
| Coin mixer | false positive | held, services quarantined |
| Handle collision | false positive | held, 0 false links |
| PGP key rotation | false **negative** | partial — 17 of 39 recovered without the key |

T3 is reported as partial rather than passed. When the artefact is gone, only
behaviour and the service stack remain, and together they recover about two
fifths. Claiming otherwise would be a lie the evaluation would catch.

Final base rate: **0.48 %** — one true link per 207 pairs. Accuracy is a
useless metric at that rate; answering "different" to everything scores 99.5 %.

---

## 2. Bugs that changed the design

These are worth reading in full. Each was found by measurement, and each
produced a design change rather than a patch.

### Two generator bugs that flattened every circadian profile

The temporal engine scored at **chance (AUC 0.54)** despite actors having
distinct sleep cycles. Two causes, both in the generator:

- `day = rng.uniform(0, span.days)` carried a fractional-day component, which
  re-randomised the hour on top of the sampled circadian hour.
- `start` also carried a fractional day, giving every persona a constant
  hour-of-day shift — so an actor's own accounts were desynchronised from each
  other.

Then a third, deeper problem: an unbroken von Mises has its minimum exactly
opposite its peak, which is not how sleep relates to waking hours. The
generator now models an explicit nightly offline window with rejection
sampling, which is what makes the sleep-gap estimator well-founded.

**After:** same-actor 0.77 vs different-actor 0.27, and UTC offset recovery to a
median 1.5 h error.

*Lesson: a channel scoring at chance is a bug report about your data, not proof
the channel is worthless.*

### The rarity floor — the same mistake in two engines

The favicon engine computed the rarity weight and then **added it to a floor of
0.35**. So a favicon present on 17 of 17 services still scored 0.35, and the
calibrator — fitted where such a match *was* informative — turned that into
log₁₀ LR +1.00.

The infra engine had a worse version: a shared `.onion` was treated as
conclusive with **no rarity weighting at all**. But every vendor on a
marketplace shares its address. They are accounts *on* it, not co-operators
*of* it.

Both were the one branch where the project's central principle had been
forgotten. Fixing them removed **all five** false positives from a live run
(precision 0.38 → 1.00) and *improved* the benchmark too (0.960 → 0.973).

*Lesson: a principle applied in nine places and forgotten in the tenth is worse
than one applied nowhere, because you will trust the output.*

### Selecting on the wrong metric

Adding the neural authorship channel made the system **worse** — AUC 0.982 →
0.971, C<sub>llr</sub> 0.223 → 0.315. It correlates with hand-crafted
stylometry, and summing correlated channels double-counts evidence.

The first fix selected channels on cross-validated **average precision** and
dropped nothing. AP scores only the *ordering*, and double-counting barely
moves a ranking — it inflates the LR *magnitude*, which is what the threshold,
the report and the analyst actually consume.

Switching selection to cross-validated **C<sub>llr</sub>** fixed it in one
change. It now drops `infra` and `template` as redundant.

*Lesson: select on the metric your product depends on, not the conventional one.*

### The context window that bled across page sections

A unit test failed because a footer `abuse@` address scored 0.52 — medium band
— on a compact page. The ±160-character context window around it reached into
the vendor's "reach me directly for bulk orders" paragraph and inherited its
solicitation score.

The fix was structural: context is now taken from the **enclosing HTML block**,
not a character window. A human reading the page would never confuse the two,
because they can see the sections are different.

*Lesson: a test failing on synthetic input can still be reporting a real defect.
Check which before adjusting the assertion.*

### `telegram: gmail`

The Telegram pattern's bare `@handle` branch matched the `@` inside every
e-mail address, reporting mail providers as usernames. A false positive shaped
like a finding is worse than a miss, because an analyst will spend time on it.

### The handle pool that ran dry

With 150 actors and 44 handle roots, the generator recycled roots with numeric
suffixes — producing unrelated actors called `sixthgate` and `sixthgate103`,
manufacturing false positives no engine could fairly reject. Now guarded by a
regression test, and confusable handles appear only as the controlled T5 trap.

---

## 3. Decisions worth defending

**Likelihood ratios, not confidence scores.** The forensic formulation, because
it separates evidence from belief and makes the prior explicit. A single
percentage invites the prosecutor's fallacy.

**Learned components must beat the simple alternative.** The neural fusion is
compared against a naive sum by cross-validation, and the loser is discarded.
The neural channel is kept only because it survives selection. Sophistication
is not evidence.

**Two stylometry channels, not one.** The hand-crafted engine is kept alongside
the learned one because an analyst can point at a comma rate in court and
cannot cross-examine a cosine. The system does not have to choose between
accuracy and defensibility.

**The author model is self-supervised.** It trains on *persona identity*, which
is printed next to every post — so no actor labels enter its input, it can be
trained on live data with no ground truth, and the held-out evaluation stays
honest. A supervised author-linking model would need labelled investigations to
train on, which is precisely what nobody has.

**Blocking reports two numbers, always.** Reduction ratio and pair
completeness. A blocker that discards true links is buying speed with cases.

**Fail closed on the abuse blacklist.** If Ahmia's list cannot be fetched,
discovery aborts. The upstream tool degrades silently, and silent degradation
on that particular filter is not acceptable.

**Keys and addresses in separate volumes.** An earlier version mounted the key
directory into the site containers and loosened its permissions. That works,
and it puts private keys one bug away from a process that accepts input from
strangers.

---

## 4. What was rejected

**Attacking Tor.** No timing correlation, no exploits, no probing. Not out of
squeamishness — it does not scale to thousands of accounts, and it produces
evidence that gets fought over rather than used.

**Scraping third-party markets for the demo.** The lab publishes services we
operate. Crawling services you do not run raises legal and ethical questions
this project does not attempt to answer.

**Fetching OSINT pivots automatically.** Querying a third party tells it you
are interested in an identifier, from your address, at a recorded time. That is
the investigator's decision. Only Gravatar is offered as an opt-in, because it
is an unauthenticated hash lookup that discloses nothing further.

**Forcing WSL sparse-disk mode** during the disk cleanup, which Microsoft has
disabled over data-corruption risk. Not on 123 GB of someone's research.

**Claiming Vercel could host the platform.** It cannot: Tor needs a persistent
process, crawls outlast any function timeout, and the dependencies are several
times the bundle limit. The static export is the honest version.

---

## 5. Testing

**142 tests**, stdlib `unittest`, no pytest — so it runs on a bare Python
install.

| Suite | Tests | Covers |
|---|---|---|
| `test_anekanta.py` | 42 | rarity, evidence, calibration, metrics, corpus, end-to-end |
| `test_osint.py` | 28 | harvest, context setting, pivots, correlation |
| `test_collect.py` | 26 | hash conventions, TLS parsing, service engines, AI |
| `test_discovery.py` | 26 | search engines, blacklist, safety gate |
| `test_live.py` | 20 | live onion, recursive discovery, container isolation |

End-to-end tests assert **floors, not exact values**. Pinning an AUC to four
decimals produces a suite that breaks whenever anyone improves the system,
which trains people to ignore it.

Two tests are worth calling out:

- `test_behaviour_outlasts_artefacts_against_disciplined_operators` — the
  project's central claim, asserted as a test. If it stops being true, the suite
  says so rather than the pitch deck.
- `test_uses_no_actor_labels` — inspects the author model's source to confirm it
  never reads `true_actor`. If it ever needs labels it stops being deployable
  and the evaluation stops being honest.

The live suite skips cleanly when the lab is not running, so an ordinary test
run needs neither Docker nor Tor.

---

## 6. What I would do next

**Persistence and incremental scoring.** The pipeline recomputes from scratch.
Production needs a persisted graph updated as the crawler delivers accounts.
The read path is already a pure function of one immutable object, so the change
is localised.

**Per-language stylometry.** The feature sets are English-only. Hindi, Russian
and Chinese boards need their own.

**Calibration on real labelled pairs.** The largest single improvement
available, and it is a data-collection problem, not a modelling one.

**Extraction adapters.** The crawler expects `/vendor/<handle>`. Real markets
need per-site patterns; the interface is one method.

**Tiered thresholds.** The disciplined tier ranks well (AUC 0.86) but cannot be
asserted at a global threshold. A tradecraft-conditioned threshold would help —
if the tradecraft classifier were better than 62.5 %.

---

## Next

- [Why this matters](01-WHY-THIS-MATTERS.md) · [How it works](02-HOW-IT-WORKS.md)
- [Architecture](03-ARCHITECTURE.md) · [User guide](04-USER-GUIDE.md)
