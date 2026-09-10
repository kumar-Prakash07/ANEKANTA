
from __future__ import annotations

import hashlib
import math
import random
import string
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone

from ..schema import Persona, Post

SITES = [
    "agora-reloaded", "dread-forum", "cryptbb-mirror", "exploit-market",
    "nulled-bazaar", "kilos-index", "thehub-successor",
]



OPSEC_TIERS = {
    "sloppy": {
        "pgp_reuse": 0.95, "handle_related": 0.95, "wallet_overlap": 0.90,
        "host_reuse": 0.90, "device_reuse": 0.85, "contact_reuse": 0.70,
        "style_adapt": 0.05, "time_jitter": 0.00, "stack_reuse": 0.90,
    },
    "mixed": {
        "pgp_reuse": 0.55, "handle_related": 0.60, "wallet_overlap": 0.50,
        "host_reuse": 0.45, "device_reuse": 0.40, "contact_reuse": 0.25,
        "style_adapt": 0.30, "time_jitter": 0.12, "stack_reuse": 0.50,
    },
    "disciplined": {
        "pgp_reuse": 0.08, "handle_related": 0.12, "wallet_overlap": 0.12,
        "host_reuse": 0.12, "device_reuse": 0.08, "contact_reuse": 0.03,
        "style_adapt": 0.60, "time_jitter": 0.30, "stack_reuse": 0.15,
    },
}
TIER_WEIGHTS = [0.30, 0.45, 0.25]

# ---------------------------------------------------------------------------
# Idiolect: the knobs that make one author measurably not another
# ---------------------------------------------------------------------------

FUNCTION_WORDS = [
    "the", "a", "of", "and", "to", "in", "that", "it", "is", "was", "for",
    "with", "as", "but", "so", "just", "really", "actually", "however",
    "though", "anyway", "basically", "honestly", "obviously", "still", "yet",
]

GREETINGS = [
    "hey", "hi all", "yo", "greetings", "good day", "listen up", "quick one",
    "ok so", "right then", "friends",
]
SIGNOFFS = [
    "thanks", "cheers", "regards", "peace", "later", "stay safe", "ty in advance",
    "appreciate it", "-- sent from my burner", "over and out",
]

TEMPLATES = [
    "{g}, my order {n} has been sitting in {state} for {d} days now",
    "{g}, has anyone else noticed the {site} mirror going down around {hr}",
    "vendor still has not responded to my message about order {n}",
    "escrow released {d} days late and support just closes the ticket",
    "the captcha on the login page is {adj} broken again",
    "i asked for a reship and got told to open a dispute instead",
    "feedback on my profile was wiped after the migration, {adj} annoying",
    "anyone got a working mirror, the main one throws a {n} error",
    "reminder to everyone to verify the signature before you trust a mirror link",
    "{g}, staff need to explain why withdrawals are queued for {d} days",
    "my two factor stopped working after the update and support is silent",
    "the new fee structure was announced with {d} days notice, that is {adj}",
    "i have been on this forum for {d} months and never seen moderation this {adj}",
    "please stop posting mirror links without a signed message",
    "the dispute system is {adj}, it took {d} rounds to get a refund",
    "profile migration lost my pgp key and now i cannot sign anything",
    "does the market still support the old key or do i need to rotate",
    "{g}, is the withdrawal queue moving for anyone else today",
    "support ticket {n} open for {d} days with no reply whatsoever",
    "the uptime on this place has been {adj} since the admin change",
]

STATES = ["escrow", "pending", "shipped", "in dispute", "finalised", "on hold"]
ADJECTIVES = ["absurd", "ridiculous", "unacceptable", "poor", "shocking",
              "typical", "frustrating", "pathetic", "acceptable", "fine"]

# How many idiolect archetypes the population is built from. Fewer archetypes
# than actors is the point: it guarantees confusable writers.
N_ARCHETYPES = 14


@dataclass
class Idiolect:
    """Writing habits. Sampled as an archetype, then perturbed per actor and
    again per persona, so that style similarity decays gradually rather than
    partitioning the corpus cleanly."""

    fw_weights: list
    sent_len_mu: float
    sent_len_sd: float
    comma_rate: float
    ellipsis_rate: float
    exclaim_rate: float
    contraction_rate: float
    british: bool
    lowercase_all: bool
    typo_rate: float
    leet_rate: float
    greeting: str
    signoff: str
    digit_style: bool
    double_space: bool

    @staticmethod
    def sample(rng: random.Random) -> "Idiolect":
        raw = [rng.expovariate(1.0) ** 1.4 for _ in FUNCTION_WORDS]
        tot = sum(raw)
        return Idiolect(
            fw_weights=[r / tot for r in raw],
            sent_len_mu=rng.uniform(10, 18),
            sent_len_sd=rng.uniform(3, 5),
            comma_rate=rng.uniform(0.04, 0.22),
            ellipsis_rate=rng.uniform(0.0, 0.18),
            exclaim_rate=rng.uniform(0.0, 0.15),
            contraction_rate=rng.uniform(0.05, 0.95),
            british=rng.random() < 0.45,
            lowercase_all=rng.random() < 0.35,
            typo_rate=rng.uniform(0.0, 0.035),
            leet_rate=rng.uniform(0.0, 0.05),
            greeting=rng.choice(GREETINGS),
            signoff=rng.choice(SIGNOFFS),
            digit_style=rng.random() < 0.6,
            double_space=rng.random() < 0.25,
        )

    def perturb(self, rng: random.Random, amount: float) -> "Idiolect":
        """Return a variant. `amount` 0 is identical, 1 is nearly unrelated."""
        if amount <= 0:
            return self

        def jit(v, lo, hi):
            span = (hi - lo) * amount * 0.6
            return min(hi, max(lo, v + rng.gauss(0, span)))

        fresh = [rng.expovariate(1.0) ** 1.4 for _ in FUNCTION_WORDS]
        s = sum(fresh)
        mixed = [(1 - amount) * w + amount * (f / s)
                 for w, f in zip(self.fw_weights, fresh)]
        tot = sum(mixed)

        return replace(
            self,
            fw_weights=[m / tot for m in mixed],
            sent_len_mu=jit(self.sent_len_mu, 8, 22),
            sent_len_sd=jit(self.sent_len_sd, 2, 6),
            comma_rate=jit(self.comma_rate, 0.0, 0.30),
            ellipsis_rate=jit(self.ellipsis_rate, 0.0, 0.25),
            exclaim_rate=jit(self.exclaim_rate, 0.0, 0.22),
            contraction_rate=jit(self.contraction_rate, 0.0, 1.0),
            # habits an operator can consciously switch, and does when trying
            british=(not self.british) if rng.random() < amount * 0.5 else self.british,
            lowercase_all=((not self.lowercase_all)
                           if rng.random() < amount * 0.5 else self.lowercase_all),
            typo_rate=jit(self.typo_rate, 0.0, 0.05),
            leet_rate=jit(self.leet_rate, 0.0, 0.08),
            greeting=rng.choice(GREETINGS) if rng.random() < amount else self.greeting,
            signoff=rng.choice(SIGNOFFS) if rng.random() < amount else self.signoff,
            digit_style=((not self.digit_style)
                         if rng.random() < amount * 0.5 else self.digit_style),
            double_space=((not self.double_space)
                          if rng.random() < amount * 0.4 else self.double_space),
        )


BRITISH_MAP = {"organize": "organise", "realize": "realise", "color": "colour",
               "apologize": "apologise", "analyze": "analyse", "favorite": "favourite"}
LEET_MAP = {"a": "4", "e": "3", "o": "0", "i": "1", "s": "5"}
NUMWORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
            8: "eight", 9: "nine", 10: "ten", 12: "twelve", 14: "fourteen"}
CONTRACTIONS = [("do not", "dont"), ("cannot", "cant"), ("has not", "hasnt"),
                ("have been", "ive been"), ("it is", "its"), ("that is", "thats")]


def _apply_idiolect(text: str, idio: Idiolect, rng: random.Random) -> str:
    if idio.british:
        for k, v in BRITISH_MAP.items():
            text = text.replace(k, v)
    if rng.random() < idio.contraction_rate:
        for a, b in CONTRACTIONS:
            text = text.replace(a, b)
    if idio.leet_rate > 0:
        text = "".join(
            LEET_MAP[ch] if (ch in LEET_MAP and rng.random() < idio.leet_rate) else ch
            for ch in text)
    if idio.typo_rate > 0:
        chars = list(text)
        for i in range(len(chars) - 1):
            if chars[i].isalpha() and chars[i + 1].isalpha() and rng.random() < idio.typo_rate:
                chars[i], chars[i + 1] = chars[i + 1], chars[i]
        text = "".join(chars)
    if idio.lowercase_all:
        text = text.lower()
    elif text:
        text = text[0].upper() + text[1:]
    if idio.double_space:
        text = text.replace(". ", ".  ")
    return text


def _make_post_text(idio: Idiolect, rng: random.Random) -> str:
    n_sent = max(1, int(rng.gauss(2.6, 1.2)))
    sentences = []
    for _ in range(n_sent):
        tpl = rng.choice(TEMPLATES)
        d = rng.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14])
        sent = tpl.format(
            g=idio.greeting,
            n=rng.randint(1000, 99999),
            state=rng.choice(STATES),
            d=str(d) if idio.digit_style else NUMWORDS.get(d, str(d)),
            hr="%02d00 utc" % rng.randint(0, 23),
            site=rng.choice(SITES),
            adj=rng.choice(ADJECTIVES),
        )
        words = sent.split()
        n_inject = max(0, int(rng.gauss(idio.sent_len_mu, idio.sent_len_sd)) - len(words))
        for _ in range(min(n_inject, 12)):
            fw = rng.choices(FUNCTION_WORDS, weights=idio.fw_weights, k=1)[0]
            words.insert(rng.randint(0, len(words)), fw)
        sent = " ".join(words)
        if rng.random() < idio.comma_rate and len(words) > 4:
            w = sent.split()
            p = rng.randint(2, len(w) - 2)
            w[p] = w[p] + ","
            sent = " ".join(w)
        if rng.random() < idio.ellipsis_rate:
            sent += "..."
        elif rng.random() < idio.exclaim_rate:
            sent += "!"
        else:
            sent += "."
        sentences.append(sent)
    return _apply_idiolect(" ".join(sentences) + " " + idio.signoff, idio, rng)


# ---------------------------------------------------------------------------
# Handles, keys, addresses, infrastructure
# ---------------------------------------------------------------------------

HANDLE_ROOTS = [
    "nightowl", "kavach", "phantomrelay", "grimoire", "sablewolf", "quietstorm",
    "hexadime", "voidcourier", "ashenkey", "redlantern", "stillwater", "brasstack",
    "coldfront", "ninelives", "paperghost", "tinman", "harborlight", "dustdevil",
    "ironbell", "mothlight", "lacquer", "saltmine", "onyxpine", "farsight", "gallows",
    "wireframe", "blackfen", "cobalt", "vellum", "tallow", "quartzite", "junco",
    "emberlane", "hollowpoint", "sixthgate", "driftwood", "palegrave", "vantablack",
    "clearcut", "sundowner", "greymarch", "littoral", "bramblewick", "hushpuppy",
]

_SYL_A = ["amber", "birch", "cinder", "dovetail", "elmshade", "flint", "gable",
          "hazel", "indigo", "jettison", "kestrel", "lumen", "marrow", "nimbus",
          "opaline", "petrel", "quillon", "rookery", "sorrel", "thistle",
          "umbral", "verdigris", "wren", "yarrow", "zephyr"]
_SYL_B = ["bank", "crest", "dell", "ford", "gate", "hollow", "keep", "marsh",
          "notch", "pike", "reach", "spire", "thorn", "vale", "wick"]


def _root_pool(rng: random.Random, n: int) -> list:
    """A pool of at least `n` distinct handle roots.

    The curated list is exhausted first, then unique two-part combinations are
    drawn. Uniqueness matters more than it looks: an earlier version recycled
    roots with a numeric suffix once it ran out, which produced unrelated
    actors called `sixthgate` and `sixthgate103` and manufactured false
    positives the handle engine had no fair way to reject. Confusable handles
    belong in the corpus, but as a controlled trap (T5), not as an accident of
    running out of names.
    """
    pool = HANDLE_ROOTS[:]
    combos = ["%s%s" % (a, b) for a in _SYL_A for b in _SYL_B]
    rng.shuffle(combos)
    pool.extend(combos)
    seen, out = set(), []
    for r in pool:
        if r not in seen:
            seen.add(r)
            out.append(r)
    if len(out) < n:
        raise ValueError("handle root pool exhausted: need %d, have %d" % (n, len(out)))
    return out


def _mutate_handle(root: str, rng: random.Random) -> str:
    style = rng.choice(["leet", "suffix", "separator", "abbrev", "camel", "prefix"])
    if style == "leet":
        return "".join(LEET_MAP.get(c, c) if rng.random() < 0.4 else c for c in root)
    if style == "suffix":
        return root + rng.choice(["_", ".", "-", ""]) + rng.choice(
            [str(rng.randint(1, 99)), "x", "official", "v2", "alt", "hq"])
    if style == "separator":
        mid = len(root) // 2
        return root[:mid] + rng.choice(["_", ".", "-"]) + root[mid:]
    if style == "abbrev":
        return root[: max(3, len(root) - rng.randint(2, 4))] + str(rng.randint(0, 9))
    if style == "camel":
        mid = len(root) // 2
        return root[:mid].capitalize() + root[mid:].capitalize()
    return rng.choice(["the", "mr", "x", "dr"]) + root


def _fingerprint(seed: str) -> str:
    return hashlib.sha1(seed.encode()).hexdigest()[:40].upper()


def _btc_address(seed: str) -> str:
    h = hashlib.sha256(seed.encode()).hexdigest()
    alpha = string.digits + string.ascii_letters
    body = "".join(alpha[int(h[i:i + 2], 16) % len(alpha)] for i in range(0, 60, 2))
    return "1" + body[:33]


def _onion(seed: str) -> str:
    """56 base32 characters, the shape of a v3 onion address."""
    h = (hashlib.sha256(seed.encode()).hexdigest()
         + hashlib.sha256((seed + "|1").encode()).hexdigest())
    alpha = "abcdefghijklmnopqrstuvwxyz234567"
    return "".join(alpha[int(h[i:i + 2], 16) % 32] for i in range(0, 112, 2)) + ".onion"


def _stable_hash(s: str) -> int:
    """PYTHONHASHSEED-independent, so corpora reproduce across runs."""
    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16)


CAMERAS = ["Canon EOS 1300D", "Nikon D3500", "SM-G975F", "iPhone 11",
           "Redmi Note 8 Pro", "Pixel 4a", "HUAWEI P30", "moto g(7)",
           "iPhone 13", "SM-A515F", "OnePlus 7T", "vivo 1904"]


def _host_prints(host: str) -> dict:
    return {
        "host": host,
        "jarm": _fingerprint(host + "jarm")[:32].lower(),
        "ssh_hostkey": _fingerprint(host + "ssh")[:32].lower(),
        "header_order": _fingerprint(host + "hdr")[:32].lower(),
        "server_banner": SERVER_BANNERS[_stable_hash(host) % len(SERVER_BANNERS)],
    }


# ---------------------------------------------------------------------------
# Service stack: favicon, TLS certificate, site template
# ---------------------------------------------------------------------------
#
# Modelled separately from the host because they move independently. An
# operator changes servers far more often than they rebuild their theme, and
# the whole value of these channels is that they survive the moves that were
# meant to break continuity.
#
# Template popularity is deliberately skewed. Most markets run one of a handful
# of off-the-shelf scripts, so a shared template is usually meaningless and
# only occasionally decisive -- which is exactly the discrimination the rarity
# weighting has to make, and it cannot be tested on a uniform distribution.

SERVER_BANNERS = ["nginx", "nginx/1.18.0", "Apache/2.4.52", "Caddy", "", "gunicorn"]

N_TEMPLATES = 12
TEMPLATE_POPULARITY = [0.28, 0.18, 0.12, 0.09, 0.07, 0.06, 0.05, 0.05,
                       0.04, 0.03, 0.02, 0.01]

# Icons shipped with the popular scripts. Widely shared, therefore worthless as
# evidence -- present so that the favicon engine has to prove it discounts them.
N_STOCK_FAVICONS = 5


def _css_vocab(template: int) -> list:
    """Class names belonging to a template. Overlapping stems across templates
    are intentional: real themes are forked from each other."""
    common = ["wrap", "row", "col", "btn", "card", "nav", "hdr", "ftr"]
    own = ["t%d-%s" % (template, s) for s in
           ("panel", "listing", "vendor", "escrow", "feedback", "badge",
            "rating", "mirror", "notice", "meta")]
    return sorted(common + own)


def _template_prints(template: int) -> dict:
    return {
        "dom_skeleton": _fingerprint("tpl%d-dom" % template)[:32].lower(),
        "error_page": _fingerprint("tpl%d-404" % template)[:32].lower(),
    }


def _dhash_for(seed: str) -> str:
    return "%016x" % (_stable_hash(seed) * 2654435761 % (1 << 64))


def _perturb_dhash(dh: str, bits: int) -> str:
    """Flip a few bits: what re-encoding an icon does to its perceptual hash."""
    v = int(dh, 16)
    for i in range(bits):
        v ^= 1 << ((i * 17 + 3) % 64)
    return "%016x" % v


def _favicon_prints(favicon_id: str, reencoded: bool = False) -> dict:
    dh = _dhash_for(favicon_id)
    return {
        "favicon_sha256": _fingerprint(favicon_id + ("-r" if reencoded else "")).lower(),
        "favicon_mmh3": str(_stable_hash(favicon_id + ("-r" if reencoded else ""))),
        "favicon_dhash": _perturb_dhash(dh, 3) if reencoded else dh,
    }


def _tls_cert(key_id: str, brand: str, cert_id: str, issued: datetime) -> dict:
    return {
        "present": True,
        "subject_cn": "%s.onion" % brand,
        "issuer_cn": "%s.onion" % brand,
        "issuer_o": brand.replace("-", " ").title(),
        "serial": _fingerprint(cert_id)[:32].lower(),
        "not_before": issued.isoformat(),
        "not_after": (issued + timedelta(days=825)).isoformat(),
        "sig_alg": "sha256WithRSAEncryption",
        # the key hash: identifies the private key file, so it survives reissue
        "spki_sha256": _fingerprint("spki-" + key_id).lower(),
        "cert_sha256": _fingerprint("cert-" + cert_id).lower(),
        "sans": ["%s.onion" % brand],
        "self_signed": True,
    }


# ---------------------------------------------------------------------------
# Actors
# ---------------------------------------------------------------------------

@dataclass
class Actor:
    actor_id: str
    opsec: str
    idiolect: Idiolect
    tz_offset: float
    circadian_peak: float
    circadian_conc: float
    sleep_start: float
    sleep_len: float
    handle_root: str
    pgp_fp: str
    wallets: list = field(default_factory=list)
    host_id: str = ""
    camera: str = ""
    contact: str = ""
    brand: str = ""
    template_id: int = 0
    favicon_id: str = ""
    tls_key_id: str = ""
    persona_ids: list = field(default_factory=list)


@dataclass
class Corpus:
    personas: list
    posts: list
    transactions: list
    actors: dict
    traps: dict

    def truth(self) -> dict:
        return {p.persona_id: p.true_actor for p in self.personas}

    def opsec_of(self) -> dict:
        return {p.persona_id: self.actors[p.true_actor].opsec for p in self.personas}

    def posts_by_persona(self) -> dict:
        out: dict = {}
        for p in self.posts:
            out.setdefault(p.persona_id, []).append(p)
        return out

    def stats(self) -> dict:
        multi = sum(1 for a in self.actors.values() if len(a.persona_ids) > 1)
        pairs = sum(len(a.persona_ids) * (len(a.persona_ids) - 1) // 2
                    for a in self.actors.values())
        n = len(self.personas)
        total = n * (n - 1) // 2
        tiers: dict = {}
        for a in self.actors.values():
            if len(a.persona_ids) > 1:
                k = len(a.persona_ids)
                tiers[a.opsec] = tiers.get(a.opsec, 0) + k * (k - 1) // 2
        return {
            "actors": len(self.actors),
            "multi_persona_actors": multi,
            "personas": n,
            "posts": len(self.posts),
            "transactions": len(self.transactions),
            "true_link_pairs": pairs,
            "true_pairs_by_opsec": tiers,
            "total_pairs": total,
            "base_rate": round(pairs / max(1, total), 6),
            "traps": {k: len(v) for k, v in self.traps.items()},
        }


def _in_window(hour: float, start: float, length: float) -> bool:
    return ((hour - start) % 24.0) < length


def _sample_hour(rng: random.Random, actor: Actor, jitter: float) -> float:
    """Local hour of a post.

    A von Mises around the actor's peak, rejected if it lands inside the
    nightly offline window. The rejection is what creates a real sleep gap, and
    a real gap is what makes the offset estimator well-founded: an unbroken von
    Mises has its minimum exactly opposite its peak, which is not how sleep
    relates to waking hours. A small leak survives rejection because everyone
    is occasionally up at 4am.

    `jitter` is deliberate tradecraft: the fraction of posts a careful operator
    schedules away from their natural rhythm to defeat exactly this analysis.
    """
    if rng.random() < jitter:
        return rng.uniform(0, 24)
    mu = actor.circadian_peak / 24.0 * 2 * math.pi
    for _ in range(12):
        h = (rng.vonmisesvariate(mu, actor.circadian_conc) / (2 * math.pi) * 24.0) % 24.0
        if not _in_window(h, actor.sleep_start, actor.sleep_len) or rng.random() < 0.05:
            return h
    return (actor.sleep_start + actor.sleep_len + rng.random()) % 24.0


def generate(seed: int = 1337,
             n_actors: int = 60,
             posts_per_persona: tuple = (25, 90),
             days: int = 400) -> Corpus:
    rng = random.Random(seed)
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)

    archetypes = [Idiolect.sample(rng) for _ in range(N_ARCHETYPES)]

    actors: dict = {}
    personas: list = []
    posts: list = []
    traps: dict = {"shared_host": [], "copypaste": [], "key_rotation": [],
                   "mixer": [], "handle_collision": []}

    # one root per actor, plus a reserve the "fresh handle" branch draws
    # from, so a disciplined operator picking a new name never collides
    # with some other actor's brand by accident
    pool = _root_pool(rng, n_actors * 2)
    rng.shuffle(pool)
    roots, reserve = pool[:n_actors], pool[n_actors:]
    # bulletproof hosts are a scarce resource, so collisions between unrelated
    # actors arise naturally; trap T1 then forces a few more
    hosts = ["host-%02d" % i for i in range(10)]

    for i in range(n_actors):
        aid = "ACT%03d" % i
        tier = rng.choices(list(OPSEC_TIERS), weights=TIER_WEIGHTS)[0]
        cfg = OPSEC_TIERS[tier]

        sleep_start = rng.uniform(22.0, 26.0) % 24.0
        sleep_len = rng.uniform(6.0, 9.0)
        wake = (sleep_start + sleep_len) % 24.0

        actor = Actor(
            actor_id=aid,
            opsec=tier,
            # an archetype plus moderate personal variation: neighbouring
            # actors in idiolect space are the hard negatives of this benchmark
            idiolect=rng.choice(archetypes).perturb(rng, 0.35),
            tz_offset=rng.choice([-8, -6, -5, -3, 0, 1, 2, 3, 3.5, 4, 5.5, 6, 7, 8, 9, 11]),
            circadian_peak=(wake + rng.uniform(0.3, 0.85) * (24 - sleep_len)) % 24.0,
            circadian_conc=rng.uniform(0.6, 3.5),
            sleep_start=sleep_start,
            sleep_len=sleep_len,
            handle_root=roots[i],
            pgp_fp=_fingerprint(aid + "-key0"),
            host_id=rng.choice(hosts),
            camera=rng.choice(CAMERAS),
            brand=roots[i],
            # template popularity is skewed, so most actors share a script with
            # somebody and only a few run something distinctive
            template_id=rng.choices(range(N_TEMPLATES),
                                    weights=TEMPLATE_POPULARITY)[0],
            # a third of actors never customise the icon their script shipped
            # with; that stock icon is then worthless as evidence
            favicon_id=("stock-%d" % rng.randrange(N_STOCK_FAVICONS)
                        if rng.random() < 0.35 else "fav-%s" % aid),
            tls_key_id="key-%s" % aid,
            contact="%s@%s" % (roots[i], rng.choice(["xmpp.jp", "jabber.ru"])),
        )
        actor.wallets = [_btc_address("%s-w%d" % (aid, j))
                         for j in range(rng.randint(2, 6))]
        actors[aid] = actor

        # most actors are singletons; a minority run several personas
        n_p = rng.choices([1, 2, 3, 4], weights=[0.45, 0.30, 0.17, 0.08])[0]
        for j, site in enumerate(rng.sample(SITES, min(n_p, len(SITES)))):
            pid = "%s-P%d" % (aid, j)
            first = (j == 0)

            # ---- handle -----------------------------------------------------
            if first or rng.random() < cfg["handle_related"]:
                handle = actor.handle_root if first else _mutate_handle(actor.handle_root, rng)
            else:
                handle = rng.choice(reserve) + str(rng.randint(1, 99))

            # whole days only: a fractional offset would become a constant
            # hour-of-day shift and desynchronise this persona from its actor
            start = base + timedelta(days=rng.randrange(0, int(days * 0.5)))
            n_posts = rng.randint(*posts_per_persona)
            span = timedelta(days=rng.randrange(30, int(days * 0.6)))

            persona = Persona(persona_id=pid, handle=handle, site=site,
                              first_seen=start, last_seen=start + span,
                              true_actor=aid)

            # ---- PGP --------------------------------------------------------
            if first or rng.random() < cfg["pgp_reuse"]:
                persona.pgp_fingerprint = actor.pgp_fp
            else:
                persona.pgp_fingerprint = _fingerprint("%s-key%d" % (aid, j))
                traps["key_rotation"].append(pid)
            dom = rng.choice(["protonmail.com", "tutanota.com", "cock.li"])
            persona.pgp_uid = "%s <%s@%s>" % (handle, handle, dom)
            persona.pgp_created = start - timedelta(days=rng.uniform(1, 300))

            # ---- wallets ----------------------------------------------------
            if rng.random() < 0.65:      # not every persona publishes an address
                if first or rng.random() < cfg["wallet_overlap"]:
                    k = rng.randint(1, max(1, len(actor.wallets) - 1))
                    persona.btc_addresses = rng.sample(actor.wallets, k)
                else:
                    persona.btc_addresses = [_btc_address("%s-iso%d-%d" % (aid, j, q))
                                             for q in range(rng.randint(1, 3))]

            # ---- infrastructure ---------------------------------------------
            persona.onion_services = [_onion(pid + "-svc")]
            host = (actor.host_id if (first or rng.random() < cfg["host_reuse"])
                    else rng.choice(hosts))
            persona.infra_fingerprints = _host_prints(host)

            # ---- service stack: favicon, template, TLS ----------------------
            # These move independently of the host: an operator changes servers
            # far more often than they rebuild a theme, which is exactly why
            # the stack outlives the moves meant to break continuity.
            keep_stack = first or rng.random() < cfg["stack_reuse"]

            template = (actor.template_id if keep_stack
                        else rng.choices(range(N_TEMPLATES),
                                         weights=TEMPLATE_POPULARITY)[0])
            persona.infra_fingerprints.update(_template_prints(template))

            fav_id = actor.favicon_id if keep_stack else "fav-%s-%d" % (aid, j)
            # sometimes the same icon is re-saved rather than copied, which
            # breaks the exact hash but not the perceptual one
            persona.infra_fingerprints.update(
                _favicon_prints(fav_id, reencoded=(keep_stack and not first
                                                   and rng.random() < 0.25)))

            persona.service = {"css_vocab": _css_vocab(template),
                               "asset_hashes": [
                                   _fingerprint("tpl%d-asset%d" % (template, q))[:32].lower()
                                   for q in range(3)]}

            # ~60% of services present TLS at all
            if rng.random() < 0.6:
                key_id = actor.tls_key_id if keep_stack else "key-%s-%d" % (aid, j)
                issued = start - timedelta(days=rng.uniform(0, 200))
                persona.service["tls"] = _tls_cert(
                    key_id, actor.brand if keep_stack else "%s-%d" % (actor.brand, j),
                    "cert-%s" % pid, issued)

            # ---- device -----------------------------------------------------
            if rng.random() < 0.75:
                if first or rng.random() < cfg["device_reuse"]:
                    persona.exif_devices = [actor.camera]
                    persona.image_hashes = [_fingerprint("%s-img%d" % (aid, q))[:16]
                                            for q in range(rng.randint(1, 3))]
                else:
                    persona.exif_devices = [rng.choice(CAMERAS)]
                    persona.image_hashes = [_fingerprint("%s-p%d-img%d" % (aid, j, q))[:16]
                                            for q in range(rng.randint(1, 2))]

            # ---- contact identifiers ----------------------------------------
            if rng.random() < 0.45:
                persona.contact_handles = (
                    [actor.contact] if (first or rng.random() < cfg["contact_reuse"])
                    else ["%s@%s" % (handle, rng.choice(["xmpp.jp", "jabber.ru"]))])

            # ---- posts ------------------------------------------------------
            # persona-level style adaptation on top of the actor idiolect: a
            # careful operator writes differently on a different board
            pidio = (actor.idiolect if first
                     else actor.idiolect.perturb(rng, cfg["style_adapt"]))
            for q in range(n_posts):
                day = rng.randrange(0, max(1, span.days))
                local_hour = _sample_hour(rng, actor, 0.0 if first else cfg["time_jitter"])
                ts_utc = (start + timedelta(days=day, hours=local_hour)
                          - timedelta(hours=actor.tz_offset))
                posts.append(Post(post_id="%s-%04d" % (pid, q), persona_id=pid,
                                  site=site, timestamp=ts_utc,
                                  text=_make_post_text(pidio, rng),
                                  thread="t%d" % rng.randint(1, 400)))
            personas.append(persona)
            actor.persona_ids.append(pid)

    pmap = {p.persona_id: p for p in personas}
    ids = list(actors)

    # ---- trap T1: unrelated actors sharing one host ------------------------
    for _ in range(10):
        a, b = rng.sample(ids, 2)
        shared = "host-shared-%d" % rng.randint(0, 2)
        prints = _host_prints(shared)
        for aid in (a, b):
            for pid in actors[aid].persona_ids:
                # update, not replace: relocating to a shared host changes the
                # host-level fingerprints and nothing else. Overwriting the
                # whole map would also erase the favicon and template, which is
                # not what moving servers does.
                pmap[pid].infra_fingerprints.update(prints)
        traps["shared_host"].append((a, b, shared))

    # ---- trap T5: unrelated actors with confusably similar handles --------
    # Brand collisions are real: impersonators, coincidence, and vendors who
    # deliberately adopt a rival's name. Introduced deliberately and in a known
    # quantity so the false positives it causes can be counted, rather than
    # arising by accident from a name pool that ran dry.
    for _ in range(8):
        a, b = rng.sample(ids, 2)
        if not actors[b].persona_ids:
            continue
        victim = pmap[actors[b].persona_ids[0]]
        victim.handle = _mutate_handle(actors[a].handle_root, rng)
        traps["handle_collision"].append((a, b))

    # ---- trap T2: verbatim reposting between unrelated actors --------------
    by_persona: dict = {}
    for p in posts:
        by_persona.setdefault(p.persona_id, []).append(p)
    for _ in range(14):
        a, b = rng.sample(ids, 2)
        pa = rng.choice(actors[a].persona_ids)
        pb = rng.choice(actors[b].persona_ids)
        src, dst = by_persona.get(pa, []), by_persona.get(pb, [])
        if len(src) < 5 or len(dst) < 5:
            continue
        for tgt in rng.sample(dst, max(1, len(dst) // 4)):
            tgt.text = rng.choice(src).text
        traps["copypaste"].append((pa, pb))

    # ---- ledger, with mixers (trap T4) ------------------------------------
    transactions: list = []
    txn = 0
    for aid, actor in actors.items():
        # an actor sweeping their own addresses into one transaction is the
        # classic common-input-ownership signal
        for _ in range(rng.randint(2, 5)):
            if len(actor.wallets) < 2:
                continue
            k = rng.randint(2, len(actor.wallets))
            transactions.append({"txid": "tx%06d" % txn,
                                 "inputs": rng.sample(actor.wallets, k),
                                 "outputs": [_btc_address("%s-out%d" % (aid, txn))]})
            txn += 1

    # isolated per-persona wallets still transact, they just do not co-spend
    # with the actor's main set
    for p in personas:
        for addr in p.btc_addresses:
            if addr not in actors[p.true_actor].wallets:
                transactions.append({"txid": "tx%06d" % txn, "inputs": [addr],
                                     "outputs": [_btc_address("iso-out%d" % txn)]})
                txn += 1

    for i in range(3):
        m = _btc_address("MIXER%d" % i)
        # a service address co-spends with everyone; naive common-input
        # ownership collapses the whole graph unless the service is detected
        for aid in rng.sample(ids, min(len(ids), 24)):
            if not actors[aid].wallets:
                continue
            transactions.append({"txid": "tx%06d" % txn,
                                 "inputs": [m, rng.choice(actors[aid].wallets)],
                                 "outputs": [_btc_address("mix-out%d" % txn)]})
            txn += 1
        traps["mixer"].append(m)

    rng.shuffle(posts)
    return Corpus(personas=personas, posts=posts, transactions=transactions,
                  actors=actors, traps=traps)
