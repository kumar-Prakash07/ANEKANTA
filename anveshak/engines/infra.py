"""Infrastructure and device correlation.

Two channels live here because they share one failure mode and one fix.

InfraEngine compares server-side fingerprints of the hidden services a persona
operates: TLS/JARM hash, SSH host key, favicon hash, hosting identifier. When a
fingerprint is genuinely rare this is among the hardest evidence available,
because it points at a machine rather than a habit.

DeviceEngine compares traces left by physical hardware: EXIF camera model
strings and perceptual hashes of reused images.

The failure mode both share is the shared-tenant problem. Bulletproof hosts
serve hundreds of unrelated customers behind identical stacks, so an unweighted
JARM match links every tenant to every other. Likewise, "iPhone 11" in EXIF is
not a fingerprint, it is a demographic. The fix in both cases is the rarity
weight: a value held by many personas contributes essentially nothing, and the
engine says so in its rationale so the analyst is not misled by a raw match
count.
"""

from __future__ import annotations

from .base import CorpusView, Engine, RawScore, NULL, index_values, rarity_weight

# How much identity each kind of fingerprint carries when it *is* rare. An SSH
# host key is a machine secret; a favicon is a file anyone can copy.
INFRA_KIND_WEIGHT = {
    "ssh_hostkey": 1.00,   # a machine secret; reuse means the same box
    "jarm": 0.85,          # TLS stack + configuration
    "header_order": 0.45,  # response header order is a property of the stack
    "host": 0.45,
    "server_banner": 0.15,  # near-worthless alone: everyone runs nginx
}


class InfraEngine(Engine):
    channel = "infra"

    def __init__(self) -> None:
        self.by_id: dict = {}
        self.indexes: dict[str, dict[str, set[str]]] = {}
        self.onion_index: dict[str, set[str]] = {}
        self.n_personas = 0

    def fit(self, view: CorpusView) -> None:
        self.by_id = view.by_id()
        self.n_personas = len(view.personas)
        for kind in INFRA_KIND_WEIGHT:
            self.indexes[kind] = index_values(
                {p.persona_id: [p.infra_fingerprints.get(kind, "")]
                 for p in view.personas}
            )
        self.onion_index = index_values(
            {p.persona_id: p.onion_services for p in view.personas}
        )

    def score(self, a: str, b: str) -> RawScore:
        pa, pb = self.by_id.get(a), self.by_id.get(b)
        if pa is None or pb is None:
            return NULL

        shared_onion = set(pa.onion_services) & set(pb.onion_services)
        if shared_onion:
            o = sorted(shared_onion)[0]
            holders = len(self.onion_index.get(o, ()))
            w = rarity_weight(holders, self.n_personas)
            share = holders / max(1, self.n_personas)
            # Rarity-weighted like every other fingerprint. Two personas being
            # the ONLY two on an address is strong evidence they run it
            # together. Ten personas sharing an address means it is a
            # marketplace and they are its vendors, which says nothing about
            # who operates it. Without this, the engine asserted that every
            # account on a site was the same person -- the one branch in this
            # file where the rarity principle had not been applied.
            if share > 0.15:
                return RawScore(
                    w,
                    "both accounts appear on the hidden service %s, but so do "
                    "%d of %d accounts: a shared platform, not shared operation"
                    % (o[:16] + "...onion", holders, self.n_personas),
                    ["onion=%s" % o, "holders=%d" % holders])
            return RawScore(min(1.0, 0.6 + 0.4 * w),
                            "both personas are present on the hidden service "
                            "%s, which only %d of %d accounts are"
                            % (o[:16] + "...onion", holders, self.n_personas),
                            ["onion=%s" % o, "holders=%d" % holders])

        best, best_kind, best_holders = 0.0, None, 0
        matched, support = [], []
        for kind, kw in INFRA_KIND_WEIGHT.items():
            va = pa.infra_fingerprints.get(kind)
            vb = pb.infra_fingerprints.get(kind)
            if not va or va != vb:
                continue
            holders = len(self.indexes[kind].get(va, ()))
            contrib = kw * rarity_weight(holders, self.n_personas)
            matched.append(kind)
            support.append("%s=%s" % (kind, va[:20]))
            if contrib > best:
                best, best_kind, best_holders = contrib, kind, holders

        if not matched:
            return RawScore(0.0, "no infrastructure fingerprints in common", [])

        # Describe the coincidence in proportion to the population, rather than
        # calling anything "rare" outright. A host key shared by 34 of 289
        # personas is a busy tenancy, not a fingerprint, and saying otherwise
        # in the report misleads the analyst even when the arithmetic behind it
        # has already discounted the match correctly.
        share = best_holders / max(1, self.n_personas)
        if share <= 0.02:
            verdict = "near-unique in the corpus"
        elif share <= 0.10:
            verdict = "uncommon but not unique"
        else:
            verdict = ("common: this looks like multi-tenant hosting rather "
                       "than a shared machine, and is heavily discounted")
        note = ("%s matches, held by %d of %d personas (%.1f%%) -- %s"
                % (best_kind, best_holders, self.n_personas, 100 * share, verdict))
        if len(matched) > 1:
            note += ("; %s agree, which is expected since they derive from the "
                     "same host and is not independent corroboration"
                     % ", ".join(k for k in matched if k != best_kind))
        return RawScore(min(1.0, best), note, support)


class DeviceEngine(Engine):
    channel = "device"

    def __init__(self) -> None:
        self.by_id: dict = {}
        self.cam_index: dict[str, set[str]] = {}
        self.img_index: dict[str, set[str]] = {}
        self.n_personas = 0

    def fit(self, view: CorpusView) -> None:
        self.by_id = view.by_id()
        self.n_personas = len(view.personas)
        self.cam_index = index_values(
            {p.persona_id: p.exif_devices for p in view.personas})
        self.img_index = index_values(
            {p.persona_id: p.image_hashes for p in view.personas})

    def score(self, a: str, b: str) -> RawScore:
        pa, pb = self.by_id.get(a), self.by_id.get(b)
        if pa is None or pb is None:
            return NULL
        if not (pa.exif_devices or pa.image_hashes) or not (pb.exif_devices or pb.image_hashes):
            return NULL

        shared_img = set(pa.image_hashes) & set(pb.image_hashes)
        if shared_img:
            h = sorted(shared_img)[0]
            holders = len(self.img_index.get(h, ()))
            w = rarity_weight(holders, self.n_personas)
            return RawScore(min(1.0, 0.75 + 0.25 * w),
                            "identical image reused across both personas "
                            "(pHash %s, %d holders)" % (h[:12], holders),
                            ["phash=%s" % h])

        shared_cam = set(pa.exif_devices) & set(pb.exif_devices)
        if shared_cam:
            cam = sorted(shared_cam)[0]
            holders = len(self.cam_index.get(cam, ()))
            w = rarity_weight(holders, self.n_personas)
            note = ("EXIF device %s common to both (%d personas use it, so this "
                    "is population-level, not individuating)" % (cam, holders)
                    if w < 0.35 else
                    "EXIF device %s shared and uncommon (%d holders)" % (cam, holders))
            return RawScore(0.5 * w, note, ["exif_model=%s" % cam])

        return RawScore(0.0, "no device traces in common", [])
