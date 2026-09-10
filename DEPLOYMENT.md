# Deployment

Three ways to run this, and one of them is not like the others. Read the first
section before choosing.

---

## What can and cannot be hosted

The platform is four long-running containers: a Tor daemon holding circuits
open, two hidden services, and an application that trains a model at startup,
holds state between requests, and runs crawls lasting minutes.

A serverless host cannot run any of that:

| Requirement | Serverless reality |
|---|---|
| Tor daemon | needs a persistent process; functions are invoked and torn down |
| Crawl lasting 2–8 minutes | function timeout is 10 s (Hobby) to 300 s (Fluid) |
| PyTorch + scikit-learn + SciPy | ~1.2 GB installed; the function bundle limit is 250 MB unzipped |
| State across requests | functions are stateless by design |
| Hidden services | there is nowhere to publish them from |

So **the interactive platform runs locally or on a container host, and Vercel
serves a static build of the results.** That split is not a workaround, it is
the honest shape of the thing: the analysis needs a machine with a network
stack, and the evidence it produces is just data.

Because every number is deterministic given a seed, the static build is not a
mock-up — it is the real dashboard showing the real output of a real run,
including a live crawl of two Tor hidden services and a sweep of the public Tor
network. It simply cannot start a new one, and it says so at the top of the
page rather than leaving you to discover it by clicking a dead button.

---

## 1. Full platform (local) — everything works

```bash
docker compose up -d --build
```

Open **<http://127.0.0.1:8000>**.

```bash
python run.py preflight
```

Verifies on the running containers that nothing is exposed to your machine or
your network. Read [onionlab/SECURITY.md](onionlab/SECURITY.md) first.

Four containers: the dashboard (`127.0.0.1:8000`), Tor with SOCKS
(`127.0.0.1:9050`), and two mock hidden services that publish **no host port at
all**. First start takes a few minutes — it trains the calibration before
serving. Watch with `docker compose logs -f anekanta`.

---

## 2. Static build (Vercel) — results only, public URL

```bash
python export_static.py --out public
```

Runs the benchmark, crawls the lab over Tor, and writes `public/data/*.json`
(~1.8 MB total). Re-run it whenever you want the published figures refreshed.

```bash
vercel deploy --prod
```

The CLI opens a browser for you to sign in. `vercel.json` already sets
`outputDirectory: public`, so there is no build step and no framework to
detect — Vercel just serves the directory.

To connect it to GitHub instead, import the repository at
<https://vercel.com/new>; the same `vercel.json` applies and every push
redeploys.

**What the visitor gets:** every tab, populated with real results — benchmark
metrics, the channel-survival heat map, the link graph, resolved-actor
dossiers, the live-crawl findings, and the real-network sweep. The two crawl
buttons are disabled and relabelled *(local only)*.

---

## 3. Container host — everything works, publicly

If you want the *interactive* platform reachable from outside your machine,
use somewhere that runs containers rather than functions: Fly.io, Railway,
Render, a VPS, or any Docker host.

Two things to change first, and neither is optional:

**Publish only the dashboard.** The compose file binds everything to
`127.0.0.1` on purpose. On a public host, the Tor SOCKS port must not be
published at all — an open SOCKS proxy will be found and abused within hours,
and its traffic will look like yours.

**Put authentication in front of it.** The dashboard can start crawls. There is
no login on it, because it is built to be reached over loopback. Exposing it
as-is hands anyone who finds the URL a crawler that runs from your host.

The mock hidden services will publish new `.onion` addresses on the new host,
because the addresses are derived from keys in a Docker volume that does not
travel with the image.

---

## Publishing to GitHub

The repository is committed and the remote is set, but pushing needs your
GitHub credentials, which this project deliberately does not handle.

1. Create an empty repository named `anekanta` at <https://github.com/new>
   (owner `anonsurf004`). Do **not** initialise it with a README, licence or
   `.gitignore` — the repository already has all three and an initialised
   remote will cause a conflict on first push.

2. Push:

```bash
git push -u origin main
```

Git Credential Manager opens a browser for you to sign in. Nothing is stored
in the repository and no token passes through this tool.

If you would rather the repository were named something else:

```bash
git remote set-url origin https://github.com/anonsurf004/<name>.git
```

### What is deliberately not committed

`.gitignore` excludes hidden-service private keys (`**/hidden_service/`,
`hs_ed25519_secret_key`) as a backstop — they live in a Docker volume and
should never reach a working tree, but anyone holding them can impersonate
your service at your address. It also excludes `*.zip`, `__pycache__`, logs,
and the regenerable `realworld-report.json`. The copy the static site serves
lives in `public/data/` and *is* committed.
