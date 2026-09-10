# ONIONLAB — running a hidden service without exposing your machine

You are about to publish a service that anyone in the world can send bytes to,
from a computer that also holds your files. That is worth taking seriously, and
this document explains exactly what protects you, what does not, and how to
check.

Read the first two sections before you run anything.

---

## The one thing that keeps you safe

**Neither site container publishes a port to Windows.**

```yaml
market:                   # and `forum`, identically
  networks: [backend]     # backend is `internal: true`
  # there is deliberately no `ports:` key
```

An `internal` Docker network has no gateway. Nothing routes in, nothing routes
out. The two mock services are reachable by exactly one thing on earth — the
Tor container, over that internal network — and Tor only forwards what arrives
through the hidden service protocol.

So there is no open port on your laptop. Not on your wifi, not on your LAN, not
on the internet. Someone who learns one of your `.onion` addresses can talk to
a sandboxed Python process that serves a few pages of made-up marketplace text
from memory, and that is the entire extent of their reach.

Verify it rather than trusting this document:

```bash
python run.py preflight
```

It inspects the running containers — **all of them**, not just the first — and
it *proves* the egress claim by attempting an outbound connection from inside
each site container and confirming it fails. Every check must pass before you
show an address to anyone.

## Keys and addresses live in separate volumes

The two services link to each other, so each needs its sibling's `.onion`
address. An address is public by design; the private key sitting next to it is
not. They are therefore kept in **two different Docker volumes**:

| volume | contents | mounted into |
|---|---|---|
| `hs_keys` | hidden service **private keys** | the Tor container only |
| `onion_pub` | the `.onion` **addresses**, nothing else | Tor (write), both sites (read-only) |

The first version of this lab mounted the key directory into the sites and
tried to loosen its permissions so an unprivileged process could traverse it.
That works, and it is the wrong shape: it puts the private keys one bug away
from a process that accepts input from strangers. Separating the volumes means
a compromised site cannot reach the keys even in principle, and no permission
on the key directory has to be relaxed. `preflight` checks this explicitly.

---

## What could still go wrong, and what stops it

| Risk | What stops it |
|---|---|
| Someone exploits the web app and gets a shell | The app is pure standard library with no subprocess, no `eval`, no template engine, no database, no file reads driven by request paths. There is no interpreter to inject into and no file to traverse to. |
| …and persists on your machine | The container is `read_only` with a `noexec` tmpfs. There is nowhere to write a payload. |
| …and escalates to root | `cap_drop: ALL`, `no-new-privileges:true`, runs as uid 10001. |
| …and pivots to your network | The container is on an internal network with no gateway. It cannot reach your router, your other machines, or the internet. |
| Your real IP leaks through the app | No external resources are referenced — no CDN, no fonts, no analytics. Every byte is inline, so a visitor's browser never makes a request anywhere else. `Server` and `Date` defaults are suppressed. Errors return a fixed page with no traceback, path, or version. |
| Your Tor proxy is abused by others on your network | Published as `127.0.0.1:9050:9050`. **The loopback prefix is load-bearing** — `"9050:9050"` would bind `0.0.0.0` and hand your entire LAN an anonymising proxy that exits as you. |
| Denial of service against the service | `HiddenServiceEnableIntroDoSDefense`, plus `mem_limit` and `pids_limit` on the container. |
| Tor accidentally relays other people's traffic | `ORPort 0`, `DirPort 0`, `ExitPolicy reject *:*`, `PublishServerDescriptor 0`. |

---

## Rules

**Do not** install Tor on Windows for this. Keeping it in a container is what
makes the network isolation possible; a host-installed Tor pointed at a
host-bound port removes every guarantee above.

**Do not** add a `ports:` entry to either site service. If you want to look at
a site yourself, browse the `.onion` through the Tor proxy, or use
`docker compose exec market python -c "..."`. The moment you publish the port,
your machine is serving it directly.

**Do not** put anything real in the container — no personal files, no
credentials, no bind mounts from your home directory. It is a demonstration
target and should contain nothing you would mind a stranger reading.

**Do not** commit `hs_keys`. That volume holds the hidden service private keys.
Anyone with them can impersonate your services at your addresses. Treat it the
way you would treat a TLS private key.

**Do not** point the crawler at third-party onion services. It is written for
this lab. Crawling services you do not operate raises legal and ethical
questions this project does not attempt to answer, and the collector's
politeness limits are not a substitute for permission.

---

## Operating it

```bash
cd onionlab
docker compose up -d          # start; first boot takes ~40s to publish
docker compose logs tor       # your .onion address is printed here
docker compose down           # stop, keep the address
docker compose down -v        # stop and destroy the key -> new address
```

Get the addresses on their own:

```bash
docker exec onionlab-tor cat /srv/onion-addresses/market
```

```bash
docker exec onionlab-tor cat /srv/onion-addresses/forum
```

### If you think something is wrong

```bash
docker compose down -v
```

That destroys the hidden service keys, so the old addresses stop resolving
immediately and permanently. There is no cleanup beyond it — nothing was ever
written outside Docker.

---

## Before a public demo

The address is unguessable (56 base32 characters), so the practical risk while
you are developing is close to zero. Once you put it on a slide, treat it as
public:

1. Run `python run.py preflight` and confirm every check passes.
2. Assume the addresses are permanently burned afterwards.
   `docker compose down -v` when the demo is over and generate fresh ones next
   time.
3. If you want it reachable *only* by the judges, enable v3 client
   authorisation: add authorised public keys under
   `/var/lib/tor/hidden_service/authorized_clients/` and only holders of the
   matching private key can connect. Everyone else cannot even complete the
   descriptor fetch. This is the strongest control available and costs you
   nothing except distributing a key.

---

## What this lab is not

It is a target for testing an attribution tool. The vendor accounts, listings,
keys, wallet addresses and the clear-web identifiers deliberately "leaked" on
some profiles are all generated fiction: the PGP blocks are syntactically
shaped but not real keys, the Bitcoin addresses are not valid mainnet
addresses, the e-mail domains are RFC 2606 reserved or obviously fictional, and
no listing describes a real good or service.

It exists so that ANEKANTA can be demonstrated against live hidden services
rather than only against a file, and so that the claim "this works on real
infrastructure" can be shown rather than asserted. Two services rather than
one, because a single service cannot demonstrate recursive discovery,
cross-service linkage, or the shared-stack fingerprints that survive a
rebrand.
