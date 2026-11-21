#!/usr/bin/python3
"""Wolthusen Hub Update-Helfer (läuft als root auf dem VPS, eingerichtet mit deploy/updater/install.sh).

Der Hub im Container darf nur eine Anfrage-Datei mit einem Wort schreiben (data/updater/request).
Dieser Helfer führt dann genau eine fest vorgegebene Aktion aus. Aus der Anfrage wird nie ein Befehl gebaut.
Ergebnis und Versionen landen in data/updater/status.json und data/updater/last.log (nur lesbar für den Hub).

Aufruf: wolthusen-updater.py          (Anfrage aus der Datei, über wolthusen-updater.path)
        wolthusen-updater.py check    (Versionen prüfen, über wolthusen-updater-check.timer)
"""
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

APP = Path(os.environ.get("HUB_APP", "/opt/docker/apps/wolthusen-hub"))
PROXY = Path(os.environ.get("HUB_PROXY", "/opt/docker/proxy"))
DIR = APP / "data" / "updater"
LOCK = Path("/run/wolthusen-updater.lock")   # root-eigen, nicht im Ordner, auf den der Container schreiben darf
ACTIONS = ("check", "hub", "caddy", "system", "reboot")
CADDY = "proxy-caddy"
PY_BASE = "python:3.12-slim"   # wie im Dockerfile
LOG = []


def now():
    return datetime.now().isoformat(timespec="seconds")


def safe_dir():
    """Der Ordner gehört dem Container: weder er noch ein Teil des Pfads darf ein Link sein (sonst schriebe root woandershin)."""
    if not os.path.isdir(DIR) or os.path.islink(DIR) or os.path.realpath(DIR) != str(DIR):
        raise SystemExit("Update-Ordner ist ungültig")


def write(name, text):
    """Atomar schreiben: neue Datei im Ordner, dann umbenennen (ersetzt auch einen Link, folgt ihm aber nie)."""
    safe_dir()
    fd, tmp = tempfile.mkstemp(dir=DIR, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, DIR / name)


def take_request():
    """Anfrage lesen und löschen. Nur das erste Wort zählt, und nur wenn es eine bekannte Aktion ist."""
    safe_dir()
    p = DIR / "request"
    try:
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as f:
            raw = f.read(40)
    except OSError:
        raw = b""
    try:
        os.unlink(p)
    except OSError:
        pass
    word = re.sub(r"[^a-z]", "", raw.decode("ascii", "ignore").split("\n")[0].strip().lower())
    return word if word in ACTIONS else ""


def run(cmd, cwd=None, timeout=1800, env=None, log=True):
    """Befehl als feste Liste (keine Shell). Liefert (Code, Ausgabe)."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})})
        out = (r.stdout or "") + (r.stderr or "")
        code = r.returncode
    except Exception as e:  # noqa
        out, code = f"{type(e).__name__}: {e}", 1
    if log:
        LOG.append(f"$ {' '.join(cmd)}\n{out.strip()}\n(Ende mit Code {code})\n")
    return code, out


def first_line(cmd, cwd=None):
    code, out = run(cmd, cwd=cwd, timeout=120, log=False)
    return out.strip().splitlines()[0].strip() if code == 0 and out.strip() else ""


def check():
    """Versionen und verfügbare Updates sammeln."""
    comps = []
    # Hub: Version aus server.py hier und auf GitHub (main)
    run(["git", "fetch", "--quiet"], cwd=APP, timeout=120, log=False)
    ver = lambda src: (re.search(r'^VERSION = "([0-9.]+)"', src, re.M) or [None, ""])[1]
    local = ver((APP / "server.py").read_text(encoding="utf-8", errors="replace")) if (APP / "server.py").is_file() else ""
    remote = ver(run(["git", "show", "origin/main:server.py"], cwd=APP, timeout=60, log=False)[1])
    head, origin = first_line(["git", "rev-parse", "--short", "HEAD"], APP), first_line(["git", "rev-parse", "--short", "origin/main"], APP)
    comps.append({"key": "hub", "name": "Wolthusen Hub", "installed": f"{local} ({head})" if head else local,
                  "available": f"{remote} ({origin})" if origin and origin != head else "", "update": "hub",
                  "note": "Mit dem Hub wird auch Python (Basis-Image) neu geladen."})
    py = first_line(["docker", "compose", "exec", "-T", "hub", "python", "-V"], APP)
    comps.append({"key": "python", "name": "Python im Hub", "installed": py.replace("Python ", ""), "available": "", "update": "hub", "note": "kommt mit dem Hub-Update"})
    # Caddy: neues Image laden (startet nichts neu) und mit dem laufenden vergleichen
    run(["docker", "pull", "--quiet", "caddy:2"], timeout=600, log=False)
    running = first_line(["docker", "inspect", "-f", "{{.Image}}", CADDY])
    latest = first_line(["docker", "image", "inspect", "-f", "{{.Id}}", "caddy:2"])
    cv = first_line(["docker", "exec", CADDY, "caddy", "version"]).split(" ")[0]
    comps.append({"key": "caddy", "name": "Caddy (Webserver, HTTPS)", "installed": cv, "available": "neues Image" if running and latest and running != latest else "",
                  "update": "caddy", "note": ""})
    comps.append({"key": "docker", "name": "Docker", "installed": first_line(["docker", "version", "--format", "{{.Server.Version}}"]),
                  "available": "", "update": "system", "note": "kommt mit den Ubuntu-Updates"})
    # Ubuntu: Paketlisten holen, aktualisierbare Pakete zählen
    run(["apt-get", "update", "-qq"], timeout=600, log=False, env={"DEBIAN_FRONTEND": "noninteractive"})
    pk = [l.split("/")[0] for l in run(["apt", "list", "--upgradable"], timeout=120, log=False)[1].splitlines() if "/" in l and "upgradable" in l]
    sec = len([l for l in run(["apt", "list", "--upgradable"], timeout=120, log=False)[1].splitlines() if "-security" in l])
    osr = {}
    try:
        for l in Path("/etc/os-release").read_text().splitlines():
            if "=" in l:
                k, v = l.split("=", 1)
                osr[k] = v.strip('"')
    except OSError:
        pass
    comps.append({"key": "ubuntu", "name": "Ubuntu (System)", "installed": f"{osr.get('PRETTY_NAME', '')}, Kernel {os.uname().release}",
                  "available": f"{len(pk)} Pakete" + (f", davon {sec} Sicherheit" if sec else "") if pk else "", "update": "system", "note": ""})
    return {"components": comps, "packages": pk[:60], "reboot_required": Path("/var/run/reboot-required").exists(), "checked_at": now()}


def load_status():
    try:
        return json.loads((DIR / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main():
    safe_dir()
    action = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ACTIONS else take_request()
    if not action:
        return
    with open(LOCK, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        st = load_status()
        st["running"] = {"action": action, "since": now()}
        write("status.json", json.dumps(st, ensure_ascii=False))
        ok = True
        LOG.append(f"== {action} gestartet {now()} ==\n")
        if action == "hub":
            run(["docker", "pull", PY_BASE], timeout=900)
            ok = run(["bash", "update.sh"], cwd=APP, timeout=1800)[0] == 0
            if ok and (APP / "deploy/updater/wolthusen-updater.py").is_file():   # Helfer selbst mit aktualisieren (gilt ab dem nächsten Lauf)
                run(["install", "-m", "755", str(APP / "deploy/updater/wolthusen-updater.py"), "/usr/local/sbin/wolthusen-updater.py"], timeout=60)
        elif action == "caddy":
            ok = run(["docker", "compose", "pull"], cwd=PROXY, timeout=900)[0] == 0
            # „up -d“ allein startet einen laufenden Container nicht immer mit dem neuen Image neu: dann gezielt neu erstellen
            newer = first_line(["docker", "inspect", "-f", "{{.Image}}", CADDY]) != first_line(["docker", "image", "inspect", "-f", "{{.Id}}", "caddy:2"])
            ok = ok and run(["docker", "compose", "up", "-d"] + (["--force-recreate"] if newer else []), cwd=PROXY, timeout=600)[0] == 0
            run(["docker", "image", "prune", "-f"], timeout=300)
        elif action == "system":
            env = {"DEBIAN_FRONTEND": "noninteractive"}
            ok = run(["apt-get", "update"], timeout=900, env=env)[0] == 0 and run(
                ["apt-get", "-y", "-o", "Dpkg::Options::=--force-confdef", "-o", "Dpkg::Options::=--force-confold", "upgrade"], timeout=3600, env=env)[0] == 0
        elif action == "reboot":
            st.update(running=None, last={"action": action, "ok": True, "at": now()})
            write("status.json", json.dumps(st, ensure_ascii=False))
            write("last.log", "".join(LOG) + "Server startet neu.\n")
            run(["systemctl", "reboot"], timeout=60)
            return
        LOG.append(f"== {action} {'fertig' if ok else 'mit Fehler beendet'} {now()} ==\n")
        st.update(check())
        st.update(running=None, last={"action": action, "ok": ok, "at": now()})
        write("status.json", json.dumps(st, ensure_ascii=False))
        if action != "check" or not (DIR / "last.log").exists():
            write("last.log", "".join(LOG)[-60000:])


if __name__ == "__main__":
    main()
