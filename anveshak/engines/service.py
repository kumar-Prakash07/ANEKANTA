"""Service-level correlation: favicon, TLS certificate, and site template.

These three channels answer a question the artefact channels cannot: when an
operator abandons a marketplace and reappears under a new name on a new .onion
with a new PGP key, what did they carry across?

Almost always, the stack. Rebuilding a service from scratch is expensive and
error-prone, so operators redeploy: the same theme, the same icon, the same
certificate, the same reverse proxy. Each of those leaves a fingerprint that
has nothing to do with the persona wearing it.

  FaviconEngine   an icon is a file that gets copied. Compared exactly (SHA-256
                  and the Shodan mmh3 convention) and perceptually (dHash), so
                  a re-encoded or lightly edited icon still matches.
  TLSEngine       certificate metadata. The strongest element is the SHA-256 of
                  the SubjectPublicKeyInfo, which identifies the key rather
                  than the certificate and therefore survives renewal. Weaker
                  but still useful: a shared issuer identity, overlapping SAN
                  entries, and certificates minted minutes apart, which is what
                  provisioning several services in one sitting looks like.
  TemplateEngine  the site itself: DOM skeleton, CSS class vocabulary, error
                  page shape, asset hashes. This is what catches a rebrand
                  where the operator changed every word but redeployed the
                  same theme.

Every comparison is rarity-weighted for the same reason as everywhere else in
this system: a default favicon shipped with a popular market script is on
hundreds of sites and means nothing, while an icon that appears on exactly two
services means a great deal. Without that weighting these channels would link
every deployment of the same off-the-shelf software.
"""

from __future__ import annotations

from datetime import datetime

from ..collect.fingerprint import hamming_hex
from .base import CorpusView, Engine, RawScore, NULL, index_values, rarity_weight

# Maximum Hamming distance between two 64-bit perceptual hashes that still
# counts as "the same image, re-encoded". Above roughly a tenth of the bits the
# comparison stops being evidence of a shared file and starts being evidence
# that both icons are simple.
DHASH_MATCH_BITS = 6

# Certificates minted within this window look like one provisioning session.
CERT_SESSION_HOURS = 72


def _parse(ts: str):
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# Favicon
# ---------------------------------------------------------------------------

class FaviconEngine(Engine):
    channel = "favicon"

    def __init__(self) -> None:
        self.by_id: dict = {}
        self.sha_index: dict = {}
        self.mmh_index: dict = {}
        self.n_personas = 0

    def fit(self, view: CorpusView) -> None:
        self.by_id = view.by_id()
        self.n_personas = len(view.personas)
        self.sha_index = index_values(
            {p.persona_id: [p.infra_fingerprints.get("favicon_sha256", "")]
             for p in view.personas})
        self.mmh_index = index_values(
            {p.persona_id: [p.infra_fingerprints.get("favicon_mmh3", "")]
             for p in view.personas})

    def score(self, a: str, b: str) -> RawScore:
        pa, pb = self.by_id.get(a), self.by_id.get(b)
        if pa is None or pb is None:
            return NULL
        fa, fb = pa.infra_fingerprints, pb.infra_fingerprints
        if not (fa.get("favicon_sha256") or fa.get("favicon_mmh3")):
            return NULL
        if not (fb.get("favicon_sha256") or fb.get("favicon_mmh3")):
            return NULL

        sha_a, sha_b = fa.get("favicon_sha256"), fb.get("favicon_sha256")
        if sha_a and sha_a == sha_b:
            holders = len(self.sha_index.get(sha_a, ()))
            w = rarity_weight(holders, self.n_personas)
            share = holders / max(1, self.n_personas)
            # The rarity weight IS the score, not a bonus on top of a floor.
            # An additive floor means a favicon shared by the whole population
            # still scores 0.35, and the calibrator -- fitted where such a
            # match was informative -- turns that into real evidence. Every
            # account on one marketplace shares its icon, so the floor linked
            # every vendor on a site to every other vendor on it.
            return RawScore(
                w,
                "byte-identical favicon (SHA-256 %s), present on %d of %d "
                "services (%.1f%%)%s"
                % (sha_a[:12], holders, self.n_personas, 100 * share,
                   "" if share <= 0.05 else
                   " -- shared this widely it identifies the platform rather "
                   "than the operator, and carries almost no weight"),
                ["favicon_sha256=%s" % sha_a,
                 "favicon_mmh3=%s" % fa.get("favicon_mmh3", "")])

        mm_a, mm_b = fa.get("favicon_mmh3"), fb.get("favicon_mmh3")
        if mm_a and mm_a == mm_b:
            holders = len(self.mmh_index.get(mm_a, ()))
            w = rarity_weight(holders, self.n_personas)
            return RawScore(0.95 * w,
                            "identical favicon mmh3 hash %s, held by %d of %d "
                            "services" % (mm_a, holders, self.n_personas),
                            ["favicon_mmh3=%s" % mm_a])

        # perceptual: survives re-encoding, cropping, palette changes
        da, db = fa.get("favicon_dhash"), fb.get("favicon_dhash")
        if da and db:
            dist = hamming_hex(da, db)
            if dist <= DHASH_MATCH_BITS:
                # Weighted by how many services carry a perceptually similar
                # icon, for the same reason as the exact branches above.
                near = sum(1 for other in self.by_id.values()
                           if hamming_hex((other.infra_fingerprints or {}).get(
                               "favicon_dhash") or "f" * 16, da) <= DHASH_MATCH_BITS)
                wp = rarity_weight(max(2, near), self.n_personas)
                return RawScore(
                    max(0.0, wp * 0.55 * (1 - dist / (DHASH_MATCH_BITS + 1))),
                    "favicons perceptually near-identical (dHash Hamming "
                    "distance %d of 64), consistent with the same icon "
                    "re-encoded; %d of %d services carry a similar icon"
                    % (dist, near, self.n_personas),
                    ["dhash_a=%s" % da, "dhash_b=%s" % db])
        return RawScore(0.0, "favicons differ", [])


# ---------------------------------------------------------------------------
# TLS
# ---------------------------------------------------------------------------

class TLSEngine(Engine):
    channel = "tls"

    def __init__(self) -> None:
        self.by_id: dict = {}
        self.spki_index: dict = {}
        self.cert_index: dict = {}
        self.n_personas = 0

    def _tls(self, pid: str) -> dict:
        p = self.by_id.get(pid)
        return (p.service or {}).get("tls", {}) if p else {}

    def fit(self, view: CorpusView) -> None:
        self.by_id = view.by_id()
        self.n_personas = len(view.personas)
        self.spki_index = index_values(
            {p.persona_id: [(p.service or {}).get("tls", {}).get("spki_sha256", "")]
             for p in view.personas})
        self.cert_index = index_values(
            {p.persona_id: [(p.service or {}).get("tls", {}).get("cert_sha256", "")]
             for p in view.personas})

    def score(self, a: str, b: str) -> RawScore:
        ta, tb = self._tls(a), self._tls(b)
        if not ta.get("present") or not tb.get("present"):
            return NULL

        # Strongest: the same public key. A certificate can be reissued, but
        # reusing the key means the same private key file was copied across.
        ka, kb = ta.get("spki_sha256"), tb.get("spki_sha256")
        if ka and ka == kb:
            holders = len(self.spki_index.get(ka, ()))
            w = rarity_weight(holders, self.n_personas)
            same_cert = ta.get("cert_sha256") == tb.get("cert_sha256")
            return RawScore(
                min(1.0, 0.75 + 0.25 * w),
                "identical TLS public key (SPKI SHA-256 %s) on both services%s; "
                "the same private key file was deployed twice"
                % (ka[:16], " (and the identical certificate)" if same_cert else
                   " under different certificates, so this survived a reissue"),
                ["spki_sha256=%s" % ka, "holders=%d" % holders])

        bits, notes, support = [], [], []

        # Same self-signed issuer identity: weak alone, but operators reuse the
        # organisation string in their openssl invocation without thinking.
        for fld, weight, label in (("issuer_o", 0.30, "issuer organisation"),
                                   ("issuer_cn", 0.25, "issuer common name"),
                                   ("subject_cn", 0.20, "subject common name")):
            va, vb = (ta.get(fld) or "").strip(), (tb.get(fld) or "").strip()
            if va and va == vb:
                bits.append(weight)
                notes.append("%s matches (%s)" % (label, va[:40]))
                support.append("%s=%s" % (fld, va[:40]))

        sans = set(ta.get("sans") or []) & set(tb.get("sans") or [])
        if sans:
            bits.append(0.35)
            notes.append("shared SAN entries: %s" % ", ".join(sorted(sans)[:3]))
            support.append("sans=%s" % ",".join(sorted(sans)[:3]))

        na, nb = _parse(ta.get("not_before", "")), _parse(tb.get("not_before", ""))
        if na and nb:
            gap = abs((na - nb).total_seconds()) / 3600.0
            if gap <= CERT_SESSION_HOURS:
                bits.append(0.35 * (1 - gap / CERT_SESSION_HOURS))
                notes.append("certificates issued %.1fh apart, consistent with "
                             "one provisioning session" % gap)

        if ta.get("self_signed") and tb.get("self_signed"):
            notes.append("both self-signed")

        if not bits:
            return RawScore(0.0, "TLS certificates share no distinguishing "
                                 "metadata", [])
        return RawScore(min(0.7, sum(bits)),      # capped: never as strong as key reuse
                        "distinct keys; " + "; ".join(notes), support)


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------

class TemplateEngine(Engine):
    channel = "template"

    # A vocabulary this small is generic markup, not a theme.
    MIN_VOCAB = 6

    def __init__(self) -> None:
        self.by_id: dict = {}
        self.dom_index: dict = {}
        self.err_index: dict = {}
        self.n_personas = 0

    def fit(self, view: CorpusView) -> None:
        self.by_id = view.by_id()
        self.n_personas = len(view.personas)
        self.dom_index = index_values(
            {p.persona_id: [p.infra_fingerprints.get("dom_skeleton", "")]
             for p in view.personas})
        self.err_index = index_values(
            {p.persona_id: [p.infra_fingerprints.get("error_page", "")]
             for p in view.personas})

    def score(self, a: str, b: str) -> RawScore:
        pa, pb = self.by_id.get(a), self.by_id.get(b)
        if pa is None or pb is None:
            return NULL
        fa, fb = pa.infra_fingerprints, pb.infra_fingerprints
        sa, sb = pa.service or {}, pb.service or {}
        if not (fa.get("dom_skeleton") or sa.get("css_vocab")):
            return NULL
        if not (fb.get("dom_skeleton") or sb.get("css_vocab")):
            return NULL

        bits, notes, support = [], [], []

        da, db = fa.get("dom_skeleton"), fb.get("dom_skeleton")
        if da and da == db:
            holders = len(self.dom_index.get(da, ()))
            w = rarity_weight(holders, self.n_personas)
            bits.append(0.55 * w)
            notes.append("identical DOM skeleton across %d services -- the same "
                         "template, independent of the wording" % holders)
            support.append("dom_skeleton=%s" % da[:16])

        va = set(sa.get("css_vocab") or [])
        vb = set(sb.get("css_vocab") or [])
        if len(va) >= self.MIN_VOCAB and len(vb) >= self.MIN_VOCAB:
            j = _jaccard(va, vb)
            if j > 0.5:
                bits.append(0.45 * j)
                shared = sorted(va & vb)[:5]
                notes.append("CSS class vocabulary %.0f%% shared (%s ...)"
                             % (100 * j, ", ".join(shared)))
                support.append("css_jaccard=%.3f" % j)

        ea, eb = fa.get("error_page"), fb.get("error_page")
        if ea and ea == eb:
            holders = len(self.err_index.get(ea, ()))
            bits.append(0.3 * rarity_weight(holders, self.n_personas))
            notes.append("identical 404 page structure (%d services)" % holders)
            support.append("error_page=%s" % ea[:16])

        aa = set(sa.get("asset_hashes") or [])
        ab = set(sb.get("asset_hashes") or [])
        if aa and ab:
            shared = aa & ab
            if shared:
                bits.append(min(0.4, 0.12 * len(shared)))
                notes.append("%d byte-identical static assets" % len(shared))
                support.append("shared_assets=%d" % len(shared))

        if not bits:
            return RawScore(0.0, "site templates differ", [])
        return RawScore(min(1.0, sum(bits)), "; ".join(notes), support)
