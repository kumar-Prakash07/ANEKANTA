"""Analyst- and court-facing report generation.

The output of an attribution system is not a number, it is a document somebody
has to defend. This module renders one linkage into a form a reviewer, a
supervising officer or opposing counsel can actually interrogate.

Four things it always states, because omitting any of them is how attribution
evidence gets discredited:

  * the hypotheses being compared, in the order the likelihood ratio compares
    them, so the direction of the claim is unambiguous;
  * every channel, including the ones that argued *against* the linkage or
    abstained, so the report cannot be accused of presenting only what helped;
  * the prior, separately from the evidence, with the posterior shown as the
    consequence of combining them;
  * the known limitations, in the report itself rather than in a manual nobody
    reads.

The verbal scale follows the ENFSI guideline convention. Wording matters here:
"very strong support for the same-actor proposition" is a claim about the
evidence, whereas "the accounts are the same person" is a claim about the
world, and this system is only ever entitled to the first.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .schema import LinkHypothesis, posterior_from_log10_lr

DISCLAIMER = """\
LIMITATIONS AND PROPER USE
  1. This report expresses the WEIGHT OF EVIDENCE for one proposition over
     another. It does not establish identity, and it names no natural person.
  2. Likelihood ratios are estimated from a reference population. They are
     valid only to the extent that population resembles the case at hand;
     a different marketplace, language or era may require recalibration.
  3. The posterior probability below depends on the stated prior. An analyst
     who disagrees with the prior should substitute their own; the likelihood
     ratio is unaffected by that choice.
  4. Behavioural channels (stylometry, circadian) are probabilistic by nature
     and can be degraded deliberately. Absence of support is not support for
     absence.
  5. Machine output is an investigative aid. It is not a substitute for
     corroboration through lawful investigative process.
"""


def _bar(v: float, width: int = 22) -> str:
    """A signed bar, negative to the left of centre, positive to the right."""
    half = width // 2
    n = int(round(min(abs(v), 4.0) / 4.0 * half))
    if v >= 0:
        return " " * half + "|" + "#" * n + " " * (half - n)
    return " " * (half - n) + "#" * n + "|" + " " * half


def evidence_report(link: LinkHypothesis, personas: dict, temporal,
                    prior_odds: float, threshold: float) -> str:
    a = personas.get(link.persona_a)
    b = personas.get(link.persona_b)
    post = posterior_from_log10_lr(link.log10_lr, prior_odds)
    tier = "LINKAGE" if link.log10_lr >= threshold else "INVESTIGATIVE LEAD"

    out = []
    w = out.append
    w("=" * 78)
    w("ANEKANTA  --  PERSONA LINKAGE EVIDENCE REPORT")
    w("Generated %s" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    w("=" * 78)
    w("")
    w("CLASSIFICATION OF FINDING: %s" % tier)
    w("")
    w("PROPOSITIONS COMPARED")
    w("  Hp  the two personas below are operated by the same actor")
    w("  Hd  the two personas below are operated by different actors")
    w("")
    w("PERSONAS")
    for p in (a, b):
        if p is None:
            continue
        geo = temporal.geolocation(p.persona_id)
        w("  %s" % p.persona_id)
        w("      handle        %s" % p.handle)
        w("      site          %s" % p.site)
        w("      observed      %s to %s"
          % (p.first_seen.isoformat()[:10], p.last_seen.isoformat()[:10]))
        w("      pgp           %s" % (p.pgp_fingerprint or "none published"))
        w("      wallets       %d published address(es)" % len(p.btc_addresses))
        if geo["offset"] is not None:
            w("      est. locale   UTC%+g +/- %gh (confidence %.2f)%s"
              % (geo["offset"], geo["band"], geo["confidence"],
                 "  [" + ", ".join(geo["regions"][:3]) + "]" if geo["regions"] else ""))
        w("")

    w("EVIDENCE BY CHANNEL")
    w("  %-12s %9s  %-22s %s" % ("channel", "log10 LR", "against    for", "reading"))
    w("  " + "-" * 74)
    for e in link.evidence:
        w("  %-12s %9.2f  %-22s %s" % (e.channel, e.log10_lr, _bar(e.log10_lr),
                                       e.verbal))
        w("      %s" % e.rationale)
        if e.supporting:
            w("      verify: %s" % "; ".join(e.supporting[:4]))
    w("")

    w("COMBINED WEIGHT OF EVIDENCE")
    w("  log10 LR (fused)          %+.2f" % link.log10_lr)
    w("  likelihood ratio          approximately %s : 1"
      % format(int(10 ** min(link.log10_lr, 12)), ","))
    w("  verbal scale              %s" % link.verbal)
    w("")
    w("  The observed evidence is approximately %s times more probable if the"
      % format(int(10 ** min(link.log10_lr, 12)), ","))
    w("  personas share one operator than if they do not.")
    w("")
    w("POSTERIOR, GIVEN THE STATED PRIOR")
    w("  prior odds (analyst)      1 in %d" % round(1 / prior_odds))
    w("  posterior probability     %.4f" % post)
    w("")
    w("DECISION THRESHOLD")
    w("  assertion threshold       log10 LR >= %.2f" % threshold)
    w("  this finding              %s" % ("meets the threshold"
                                          if link.log10_lr >= threshold else
                                          "BELOW threshold - lead only, not a linkage"))
    w("")
    w(DISCLAIMER)
    w("=" * 78)
    return "\n".join(out)


def dossier_report(dossier: dict) -> str:
    """Consolidated profile of one resolved actor."""
    out = []
    w = out.append
    w("=" * 78)
    w("ANEKANTA  --  RESOLVED ACTOR DOSSIER  %s" % dossier["cluster_id"])
    w("Generated %s" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    w("=" * 78)
    w("")
    w("PERSONAS ATTRIBUTED TO THIS ACTOR")
    for p in dossier["personas"]:
        w("  %-14s %-22s %-18s %s to %s"
          % (p["id"], p["handle"], p["site"], p["first_seen"], p["last_seen"]))
    w("")
    w("  weakest internal link     log10 LR %.2f" % dossier["cohesion_log10_lr"])
    w("  active                    %s to %s"
      % (dossier["active_from"], dossier["active_to"]))
    w("  marketplaces              %s" % ", ".join(dossier["sites"]))
    w("")
    tz = dossier["timezone"]
    w("GEOTEMPORAL ASSESSMENT")
    if tz["pooled_utc_offset"] is not None:
        w("  pooled UTC offset         %+.2f" % tz["pooled_utc_offset"])
        w("  spread across personas    %.2f h" % tz["per_persona_spread_hours"])
        w("  consistent with           %s" % (", ".join(tz["regions"]) or "no named region"))
        w("  note                      %s" % tz["note"])
    else:
        w("  insufficient temporal signal for a locale assessment")
    w("")
    w("TECHNICAL ARTEFACTS")
    w("  PGP keys                  %d%s" % (len(dossier["pgp_keys"]),
                                            "  (rotation observed)"
                                            if dossier["key_rotation_observed"] else ""))
    for k in dossier["pgp_keys"]:
        w("      %s" % k)
    w("  BTC addresses             %d" % len(dossier["btc_addresses"]))
    for k in dossier["btc_addresses"][:8]:
        w("      %s" % k)
    if dossier["contact_identifiers"]:
        w("  contact identifiers       %s" % ", ".join(dossier["contact_identifiers"]))
    if dossier["exif_devices"]:
        w("  devices in image EXIF     %s" % ", ".join(dossier["exif_devices"]))
    w("  hidden services           %d" % len(dossier["onion_services"]))
    for k in dossier["onion_services"][:5]:
        w("      %s" % k)
    w("")
    w(DISCLAIMER)
    w("=" * 78)
    return "\n".join(out)
