# ANEKANTA documentation

Five documents. Read them in order the first time; after that they stand alone.

| | Document | Read it for |
|---|---|---|
| **01** | [Why this matters](01-WHY-THIS-MATTERS.md) | The problem, the threat landscape, why classical de-anonymisation is narrowing, and where this sits among Maltego, Chainalysis, Hunchly and darkdump. **Start here.** |
| **02** | [How it works](02-HOW-IT-WORKS.md) | The mechanism end to end: discovery → collection → blocking → twelve engines → calibration → selection → fusion → resolution → Dark2Clear → reporting. |
| **03** | [Architecture](03-ARCHITECTURE.md) | Deployment topology, the three things that make it safe, module map, data flow, and what changes at real scale. |
| **04** | [User guide](04-USER-GUIDE.md) | Install, the eight tabs, the eight commands, how to read a likelihood ratio, a worked investigation, and how to interpret a *negative* result. |
| **05** | [Build notes](05-BUILD-NOTES.md) | How it was built, the bugs that changed the design, decisions worth defending, what was rejected, and what I would do next. |

Also in the repository:

- [`../README.md`](../README.md) — the technical reference: full results,
  per-channel ablations, adversarial evaluation, and the reasoning behind each
  mechanism.
- [`../DEPLOYMENT.md`](../DEPLOYMENT.md) — the three hosting targets and what
  each gives up.
- [`../onionlab/SECURITY.md`](../onionlab/SECURITY.md) — threat model for
  running hidden services on your own machine. **Read before starting the lab.**
- [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) — darkdump (MIT) and
  Ahmia attribution.

---

## The one-paragraph version

A single dark-web operator runs many accounts. Taking down a marketplace
removes a venue, not the operator, who reappears elsewhere within weeks under
names nobody has connected. ANEKANTA answers *which accounts are the same
human being, and how strongly do we believe it* — fusing twelve evidence
channels into a **likelihood ratio**, the forensic standard that keeps evidence
separable from belief. It never touches the Tor protocol; every signal is
content an operator published. Against careless operators it resolves accounts
at **97 % precision**. Against disciplined ones it usually **declines to
assert**, because two behavioural channels cannot reach an evidential
threshold — and routes them to a lead queue instead, 5.5× enriched. That refusal
is the feature.

## The finding

| Channel | Careless | **Disciplined** |
|---|---|---|
| PGP · handle · wallet · device · infra · favicon · TLS · template | 0.63 – 1.00 | **0.46 – 0.56** |
| **Stylometry** | 0.961 | **0.642** |
| **Circadian rhythm** | 0.870 | **0.908** |

*Discrimination AUC; 0.5 is a coin flip.*

Against an operator who rotates their tradecraft, every artefact channel
collapses to chance. Only behaviour survives — and circadian rhythm does not
degrade at all.

**A key can be rotated. A wallet can be abandoned. A host can be changed. A
sleep cycle cannot.**

## Headline numbers

| | |
|---|---|
| Benchmark (held-out actors, 0.48 % base rate) | AUC **0.981** · precision **0.97** · recall **0.74** · C<sub>llr</sub> **0.240** |
| Identity clustering | B-Cubed F1 **0.930** |
| Live crawl, 2 Tor hidden services | precision **1.00** · 7/7 clear-web leaks recovered, all correctly attributed |
| Public Tor network | 101 addresses discovered, **16/16 reachable**, 16.4 pages/min |
| Adversarial traps | 4 of 5 held with zero false links; the 5th reported as partial |
| Tests | **142**, stdlib unittest |
