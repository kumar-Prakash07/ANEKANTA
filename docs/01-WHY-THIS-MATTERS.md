# Why this matters: attribution on the dark web in 2026

*Problem context, threat landscape, and where ANEKANTA sits among existing
tools. Read this before the technical documents — it explains what problem the
machinery is for.*

---

## 1. The takedown treadmill

Hansa. AlphaBay. Wall Street Market. Hydra. Genesis. Each takedown was a real
operation with real seizures, and each was followed within months by successors
staffed substantially by the same people.

The pattern is consistent because the economics are:

- **A marketplace is infrastructure. An operator is a person.** Seizing a
  server removes a venue. It does not remove the vendor, who reappears on three
  other venues within weeks under names nobody has connected to the old one.
- **Rebranding is cheap.** A new `.onion` address costs nothing, a new PGP key
  costs a minute, a new handle costs a thought. The one thing that is expensive
  is rebuilding a customer base, which is why vendors advertise continuity to
  buyers while presenting discontinuity to investigators.
- **Investigators are outnumbered.** A mid-size market has thousands of vendor
  accounts. An analyst has a week. Any approach that requires reading every
  account by hand does not scale to the problem.

So the operationally useful question is not *"who owns this server"* but:

> **Which of these accounts are the same human being, and how strongly do we
> believe it?**

Answer that and a takedown removes an operator rather than a venue. Fail to
answer it and you are removing venues forever.

---

## 2. Why the classical de-anonymisation routes are narrowing

"De-anonymisation" historically meant attacking the anonymity network:

| Technique | Status in 2026 |
|---|---|
| Traffic correlation / timing attacks | Requires a global-passive-adversary position, or control of both ends. Rarely available, rarely lawful, never repeatable in court. |
| Network investigative techniques (browser exploits) | Effective and used, but requires a warrant, burns an expensive capability on one target, and has repeatedly produced evidence suppressed on Fourth Amendment grounds. |
| Hidden service protocol flaws | v2 onion services were genuinely weak. v3 fixed the address-harvesting problem, and v2 was removed from the network. |
| Guard discovery / relay-level attacks | Expensive, slow, and detectable. |

None of these scale to *thousands of vendor accounts*, and none produces
something a prosecutor can put in front of a jury without a fight over how it
was obtained.

**ANEKANTA does none of them.** It never touches the Tor protocol. Every signal
it uses is content an operator published to anyone who visits.

That constraint is not a limitation — it is what makes the output usable. There
is no warrant question about reading a public vendor profile, and no
suppression argument about a page anybody could load.

---

## 3. What operators actually leak

Modern tradecraft advice is widely circulated and widely followed. Serious
operators rotate keys, use fresh handles, strip EXIF, and avoid clear-web
identifiers. The benchmark models exactly that population.

But tradecraft is a set of *deliberate actions*, and deliberate actions have
two failure modes:

**They are not applied uniformly.** An operator careful on four accounts is
careless on the fifth — the one opened in a hurry, or before they took security
seriously, or when the old account got banned mid-conversation. Silk Road ended
this way: Ulbricht promoted the market as "altoid" and, in a separate forum
post months earlier, asked a programming question using `rossulbricht@gmail.com`.
One address, on one page, where it did not belong.

**Some things cannot be rotated at all.** This is the finding the whole project
is built around, and it is measured rather than asserted:

| Channel | Careless operator | **Disciplined operator** |
|---|---|---|
| PGP key | 1.000 | **0.557** |
| Handle | 0.999 | **0.466** |
| Wallet cluster | 0.709 | **0.500** |
| Device / EXIF | 0.748 | **0.457** |
| Infrastructure | 0.910 | **0.511** |
| Favicon | 0.924 | **0.549** |
| TLS certificate | 0.627 | **0.488** |
| Site template | 0.937 | **0.519** |
| **Writing style** | 0.961 | **0.642** |
| **Circadian rhythm** | 0.870 | **0.908** |

*(discrimination AUC; 0.5 is a coin flip)*

Read the right-hand column. Against an operator who rotates their tradecraft,
**every artefact channel collapses to chance**. Only behaviour survives — and
circadian rhythm does not degrade at all, because it is the one thing that is
not a choice.

A key can be rotated. A wallet can be abandoned. A host can be changed. **A
sleep cycle cannot.** You can schedule posts to hide it, and 30 % of the
disciplined operators in the benchmark do exactly that, and it still shows.

---

## 4. Why "how confident" matters more than "linked"

Most attribution tooling outputs a graph: nodes connected by edges, with a
confidence badge. That is fine for generating leads and useless for anything
downstream, because:

- **A percentage without a prior is meaningless.** "87 % confident" confident
  relative to what assumption about how likely any two accounts are to share an
  operator? Change that assumption and the number changes completely.
- **It invites the prosecutor's fallacy.** P(evidence | same person) is not
  P(same person | evidence). Conflating them has produced real miscarriages of
  justice in fingerprint and DNA cases, and an attribution tool that reports one
  number encourages exactly that confusion.

ANEKANTA reports a **likelihood ratio** — the standard forensic formulation,
and the one ENFSI guidelines and several jurisdictions now expect:

```
      P(this evidence | the accounts are one operator)
LR = ──────────────────────────────────────────────────
      P(this evidence | they are different operators)
```

The LR is a statement about *evidence*. Turning it into a probability requires
a prior, which the analyst supplies and which the report prints beside the
answer. An analyst who disagrees with the prior can substitute their own; the
likelihood ratio does not move.

This is what makes an output defensible rather than merely persuasive. It also
means the system can be **wrong in a measurable way**: C<sub>llr</sub> charges
for confidence in proportion to how wrong it turned out to be, so a system that
says "10,000:1" about a false link is punished far harder than one that says
"3:1". That metric is reported, and is also what the system uses to select its
own components.

---

## 5. Where this sits among existing tools

| Tool | What it does | What it does not |
|---|---|---|
| **Maltego / Lampyre** | Graph OSINT once you have a selector. Excellent pivot visualisation. | Does not tell you which dark-web accounts to pivot *from*. Commercial, per-seat. |
| **Chainalysis / Elliptic** | Blockchain clustering and exchange attribution at scale. | One channel only. Silent when an operator uses Monero or never reuses an address. |
| **Hunchly / Ahmia / dark.fail** | Discovery and capture of onion services. | Indexing, not attribution. No linkage between accounts. |
| **darkdump** | Open-source onion discovery via search engines. | Discovery only; adapted into this project for exactly that stage. |
| **Academic stylometry** | Authorship attribution, often at high accuracy. | Evaluated on clean single-channel corpora with balanced classes. Falls apart at a 0.5 % base rate. |
| **ANEKANTA** | Fuses twelve channels into a calibrated likelihood ratio, resolves accounts into operators, and chains that to clear-web leaks. | Does not identify natural persons. Does not attack Tor. Needs recalibration for a new population. |

The gap it fills is the join: **nobody else combines behavioural attribution,
service-stack fingerprinting, and clear-web OSINT into one calibrated number**
— and critically, nobody else propagates a leak found on one account to every
other account resolved to that operator.

That last point is the practical payoff. On the live demonstration, one
carelessly published address on `kavach_supply` implicated `kavach.supply2` and
`nightfreight` — accounts that leaked nothing whatsoever. The operator's single
mistake compromised their entire estate.

---

## 6. Operational impact, stated conservatively

**What it does well.** Against careless and moderately careful operators —
which, on any real market, is most of them — it resolves accounts into
operators at 97 % precision, and the top 25 of its queue are correct. An
analyst working that queue is not guessing.

**What it does honestly.** Against genuinely disciplined operators it will
usually decline to assert a linkage, because two moderately-informative
behavioural channels cannot reach the evidential threshold an accusation needs.
Those pairs go to a **lead queue** instead — 5.5× enriched over the pool an
analyst would otherwise work through — explicitly labelled as leads and never
as findings.

That refusal is the feature. A tool that asserts everything is a tool nobody
can testify with.

**What it changes about the work.** Three things:

1. **Triage.** Thousands of accounts become tens of operator clusters, ranked.
2. **Continuity across takedowns.** Service-stack fingerprints — favicon, TLS
   public key, DOM skeleton, header order — survive a rebrand, so a market that
   reappears under a new name and new address is recognisable as the same
   deployment.
3. **Explanation.** Every finding renders to a document stating the propositions
   compared, every channel *including the ones that argued against the link*,
   the prior, the posterior, and the limitations. A supervising officer can
   read it. Opposing counsel can attack it. That is the point.

---

## 7. What it will not do, and why that is stated up front

- **It does not name people.** It links pseudonymous accounts to each other and
  quantifies how strongly. Identification is a matter for lawful process.
- **It does not attack Tor.** No circuit correlation, no exploits, no probing.
- **It is not a substitute for corroboration.** Machine output is an
  investigative aid, and every report says so.
- **Its numbers are population-dependent.** Likelihood ratios are estimated
  against a reference population. Deploy it against a different marketplace,
  language or era and the calibration must be refitted on labelled pairs from
  that population. This is a data-collection problem, not a modelling one, and
  no amount of extra machinery substitutes for it.
- **Behavioural channels can be degraded deliberately.** Absence of support is
  not support for absence, and the reports say that in those words.

---

## Next

- [How it works](02-HOW-IT-WORKS.md) — the mechanism, end to end
- [Architecture](03-ARCHITECTURE.md) — components, infrastructure, scaling
- [User guide](04-USER-GUIDE.md) — how to actually run an investigation
- [Build notes](05-BUILD-NOTES.md) — how it was built and what went wrong
