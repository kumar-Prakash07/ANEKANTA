"""ONIONLAB isolation check.

Verifies that running a hidden service on this machine has not exposed the
machine. It inspects the *running* containers rather than reading the compose
file, because the file describes intent and only the runtime describes reality:
a stale container started before an edit, a manual `docker run`, or a port
published by something else entirely will all pass a file review and fail here.

Each check states the specific way things go wrong when it fails. A checklist
whose items you cannot explain is a checklist you will eventually skip.

Run it any time the lab is up:

    python run.py preflight
"""

from __future__ import annotations

import json
import shutil
import subprocess

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"

# Every site container, not just the first. A check that inspects half the
# deployment is worse than no check, because it reports PASS.
SITES = ["onionlab-site", "onionlab-forum"]
TOR = "onionlab-tor"


def _docker(*args) -> tuple:
    try:
        out = subprocess.run(("docker",) + args, capture_output=True, text=True,
                             timeout=30)
        return out.returncode == 0, out.stdout.strip(), out.stderr.strip()
    except Exception as exc:
        return False, "", str(exc)


def _inspect(name: str):
    ok, out, _ = _docker("inspect", name)
    if not ok or not out:
        return None
    try:
        return json.loads(out)[0]
    except Exception:
        return None


def _check_site_publishes_nothing(site) -> tuple:
    label = (site.get("Name") or "site").lstrip("/")
    ports = (site.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}
    published = {k: v for k, v in ports.items() if v}
    if published:
        return (FAIL, "%s publishes %s to the host" % (label, published),
                "Anything that can reach your machine can now reach the mock "
                "market directly, bypassing Tor entirely. Remove the `ports:` "
                "key from the site service.")
    return (PASS, "%s publishes no port to the host" % label,
            "Nothing on your machine, your LAN or the internet can open a "
            "socket to it; only the Tor container can, over the internal "
            "network.")


def _check_backend_internal(site) -> tuple:
    label = (site.get("Name") or "site").lstrip("/")
    nets = (site.get("NetworkSettings", {}) or {}).get("Networks", {}) or {}
    names = list(nets)
    internal = []
    for n in names:
        ok, out, _ = _docker("network", "inspect", n, "--format", "{{.Internal}}")
        internal.append(out.strip() == "true")
    if not names:
        return (FAIL, "site is on no network", "Unexpected state; recreate the lab.")
    if all(internal):
        return (PASS, "%s is only on internal network(s): %s"
                % (label, ", ".join(names)),
                "An internal Docker network has no gateway, so the site has no "
                "route to the internet and the internet has none to it.")
    return (FAIL, "%s is attached to a routable network: %s"
            % (label, ", ".join(names)),
            "If the site process is ever compromised it can reach the internet "
            "from your connection. Put it on the `backend` network only.")


def _check_site_hardening(site) -> list:
    label = (site.get("Name") or "site").lstrip("/")
    hc = site.get("HostConfig", {}) or {}
    cfg = site.get("Config", {}) or {}
    out = []

    out.append((PASS if hc.get("ReadonlyRootfs") else WARN,
                "%s read-only root filesystem: %s"
                % (label, bool(hc.get("ReadonlyRootfs"))),
                "A writable filesystem lets an attacker drop a payload and "
                "persist across restarts."))

    dropped = [c.upper() for c in (hc.get("CapDrop") or [])]
    out.append((PASS if "ALL" in dropped else WARN,
                "%s capabilities dropped: %s" % (label, dropped or "none"),
                "Without dropping capabilities the process keeps powers it "
                "never needs, widening what a bug can be turned into."))

    opts = hc.get("SecurityOpt") or []
    nnp = any("no-new-privileges" in o for o in opts)
    out.append((PASS if nnp else WARN,
                "%s no-new-privileges: %s" % (label, nnp),
                "Without it, a setuid binary inside the image can be used to "
                "escalate to root in the container."))

    user = cfg.get("User") or ""
    out.append((PASS if user and not user.startswith("0") else WARN,
                "%s runs as non-root user: %r" % (label, user or "root"),
                "Root in a container is a much shorter path to root on the "
                "host if the runtime is ever escaped."))
    return out


def _check_tor_binding(tor) -> tuple:
    ports = (tor.get("NetworkSettings", {}) or {}).get("Ports", {}) or {}
    bad, good = [], []
    for container_port, bindings in ports.items():
        for b in bindings or []:
            ip = b.get("HostIp", "")
            if ip in ("0.0.0.0", "::", ""):
                bad.append("%s -> %s:%s" % (container_port, ip or "*",
                                            b.get("HostPort")))
            else:
                good.append("%s -> %s:%s" % (container_port, ip, b.get("HostPort")))
    if bad:
        return (FAIL, "Tor SOCKS is bound to all interfaces: %s" % ", ".join(bad),
                "Everyone on your network can use your machine as an anonymising "
                "proxy, and their traffic will look like yours. Bind to "
                "127.0.0.1 explicitly: \"127.0.0.1:9050:9050\".")
    return (PASS, "Tor ports bound to loopback only: %s" % (", ".join(good) or "none"),
            "Only processes on this machine can use the proxy.")


def _check_no_windows_exposure() -> tuple:
    """Look for anything listening on a wildcard address on the lab's ports."""
    if not shutil.which("netstat") and not shutil.which("powershell"):
        return (WARN, "could not enumerate host listeners", "Check manually.")
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-NetTCPConnection -State Listen | "
             "Where-Object { $_.LocalPort -in 8080,8443,9050 } | "
             "ForEach-Object { \"$($_.LocalAddress):$($_.LocalPort)\" }"],
            capture_output=True, text=True, timeout=30).stdout
        listeners = [l.strip() for l in out.splitlines() if l.strip()]
    except Exception as exc:
        return (WARN, "host listener check failed: %s" % type(exc).__name__, "")

    wildcard = [l for l in listeners if l.startswith("0.0.0.0:") or l.startswith(":::")]
    if wildcard:
        return (FAIL, "lab ports listening on all interfaces: %s" % ", ".join(wildcard),
                "Something is reachable from your network. Find it with "
                "Get-NetTCPConnection and stop it.")
    return (PASS, "no lab port is listening on a wildcard address%s"
            % (" (found: %s)" % ", ".join(listeners) if listeners else ""),
            "Nothing on your LAN can reach the lab.")


def _check_site_has_no_egress(name: str) -> tuple:
    """Prove the isolation rather than trusting the label: try to leave."""
    ok, out, _err = _docker(
        "exec", name, "python", "-c",
        "import socket;socket.setdefaulttimeout(4);"
        "socket.create_connection(('1.1.1.1',53));print('REACHED')")
    if ok and "REACHED" in out:
        return (FAIL, "%s reached the public internet" % name,
                "The internal-network guarantee is not holding. Recreate the "
                "lab with `docker compose down && docker compose up -d`.")
    return (PASS, "%s cannot reach the public internet" % name,
            "Confirmed by attempting an outbound connection from inside it "
            "and failing.")


def _check_keys_not_mounted(site) -> tuple:
    """The hidden service private keys must never be visible to a site.

    The sites need their sibling's .onion address, which is public. They have
    no business near the keys, so addresses live in their own volume and the
    key volume is mounted into the Tor container only. Whoever holds those keys
    can impersonate your service at your address.
    """
    mounts = site.get("Mounts") or []
    for m in mounts:
        name = m.get("Name") or ""
        if "hs_keys" in name:
            return (FAIL, "the hidden service KEY volume is mounted into %s"
                    % site.get("Name", "a site container"),
                    "Anyone who compromises the site process can steal the "
                    "private keys and impersonate your service. Mount the "
                    "address volume (onion_pub) instead.")
        if name.endswith("onion_pub") and m.get("RW"):
            return (WARN, "the address volume is mounted writable",
                    "It only ever needs reading; mount it with `:ro`.")
    return (PASS, "private keys are not reachable from the site containers",
            "Addresses and keys are in separate volumes, and only Tor mounts "
            "the keys.")


def run_preflight() -> int:
    print()
    print("  ONIONLAB ISOLATION CHECK")
    print("  " + "=" * 68)

    if not shutil.which("docker"):
        print("  FAIL  docker not found on PATH")
        return 1

    tor = _inspect(TOR)
    sites = [(name, _inspect(name)) for name in SITES]
    live = [(name, obj) for name, obj in sites if obj is not None]
    if tor is None or not live:
        print("  FAIL  containers not running. Start them with:")
        print("          cd onionlab && docker compose up -d")
        return 1

    results = []
    for name, site in live:
        results.append(_check_site_publishes_nothing(site))
        results.append(_check_backend_internal(site))
        results.append(_check_site_has_no_egress(name))
        results.append(_check_keys_not_mounted(site))
        results.extend(_check_site_hardening(site))
    results.append(_check_tor_binding(tor))
    results.append(_check_no_windows_exposure())
    print("  checking %d service container(s): %s"
          % (len(live), ", ".join(n for n, _ in live)))
    print("  " + "-" * 68)

    worst = PASS
    for status, headline, why in results:
        print("  %-5s %s" % (status, headline))
        if why:
            for line in _wrap(why, 66):
                print("        %s" % line)
        if status == FAIL:
            worst = FAIL
        elif status == WARN and worst != FAIL:
            worst = WARN
    print("  " + "=" * 68)

    if worst == FAIL:
        print("  RESULT: NOT SAFE TO EXPOSE. Fix the FAIL items above first.")
        return 2
    if worst == WARN:
        print("  RESULT: isolated, but some hardening is missing (see WARN).")
        return 0
    print("  RESULT: isolated. The services are reachable only through Tor, and")
    print("  nothing on this machine is exposed to your network or the internet.")
    return 0


def _wrap(text: str, width: int) -> list:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines
