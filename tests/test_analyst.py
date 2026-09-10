from datetime import datetime
from anveshak.schema import Persona, Evidence, LinkHypothesis
from anveshak.ai import forensic_analyst

p1 = Persona(persona_id='ACT101-P0', handle='rookerynotch', site='cryptbb-mirror', first_seen=datetime.now(), last_seen=datetime.now(), btc_addresses=['1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'], pgp_fingerprint='999FF131ABCDEF0123456789')
p2 = Persona(persona_id='ACT101-P1', handle='rookerynotch_v2', site='agora-reloaded', first_seen=datetime.now(), last_seen=datetime.now(), btc_addresses=['1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa'], pgp_fingerprint='999FF131ABCDEF0123456789')

ev = [
    Evidence(persona_a='ACT101-P0', persona_b='ACT101-P1', channel='crypto', score=1.0, log10_lr=2.20, rationale='Same Bitcoin address on both accounts', supporting=['1A1z...']),
    Evidence(persona_a='ACT101-P0', persona_b='ACT101-P1', channel='device', score=0.9, log10_lr=1.79, rationale='Same image file reused (pHash match)', supporting=['phash:abc']),
    Evidence(persona_a='ACT101-P0', persona_b='ACT101-P1', channel='pgp', score=1.0, log10_lr=1.69, rationale='Identical PGP key fingerprint', supporting=['999FF131...']),
    Evidence(persona_a='ACT101-P0', persona_b='ACT101-P1', channel='favicon', score=0.8, log10_lr=1.47, rationale='Same favicon (weak — shared by 19 sites)', supporting=[]),
    Evidence(persona_a='ACT101-P0', persona_b='ACT101-P1', channel='temporal', score=0.7, log10_lr=0.68, rationale='Both UTC+0, identical sleep/activity pattern', supporting=[]),
    Evidence(persona_a='ACT101-P0', persona_b='ACT101-P1', channel='handle', score=0.6, log10_lr=0.68, rationale='"rookerynotch" is literally inside "rookerynotch_v2"', supporting=[]),
    Evidence(persona_a='ACT101-P0', persona_b='ACT101-P1', channel='template', score=0.6, log10_lr=0.64, rationale='Same site template, CSS, 404 page', supporting=[]),
    Evidence(persona_a='ACT101-P0', persona_b='ACT101-P1', channel='stylometry', score=0.5, log10_lr=0.52, rationale='Writing styles match', supporting=[]),
    Evidence(persona_a='ACT101-P0', persona_b='ACT101-P1', channel='infra', score=0.3, log10_lr=0.26, rationale='Shared hosting — too common to matter', supporting=[]),
]

link = LinkHypothesis(persona_a='ACT101-P0', persona_b='ACT101-P1', log10_lr=5.71, posterior=0.999, evidence=ev)

class MockTemporal:
    def geolocation(self, pid):
        return {'offset': 0, 'confidence': 1.0, 'band': 1.0, 'regions': ['Western Europe', 'United Kingdom']}

res = forensic_analyst.analyze_linkage(link, {'ACT101-P0': p1, 'ACT101-P1': p2}, MockTemporal(), threshold=1.38)
assert res["status"] in ("success", "fallback")
assert "Linkage Forensic Analysis: rookerynotch" in res["markdown"]
assert "Crypto" in res["markdown"]
assert "PGP" in res["markdown"]
print("All analyst test assertions passed successfully!")

