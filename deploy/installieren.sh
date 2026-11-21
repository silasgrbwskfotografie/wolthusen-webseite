#!/usr/bin/env bash
# Wolthusen Hub komplett auf dem VPS einrichten, neben dem Emden Tigers Hub (zentraler Caddy unter /opt/docker/proxy).
# Aufruf im Hub-Ordner:
#   cd /opt/docker/apps/wolthusen-hub && sudo bash deploy/installieren.sh
# Andere Domain:  sudo bash deploy/installieren.sh andere.domain.de
# Darf mehrfach laufen: was schon erledigt ist, wird übersprungen.
set -euo pipefail

DOMAIN="${1:-wolthusen.silasgrbwskfotografie.de}"
APP="$(cd "$(dirname "$0")/.." && pwd)"
PROXY=/opt/docker/proxy
STAMP=$(date +%Y%m%d-%H%M%S)

ok()   { echo "  [ok] $*"; }
info() { echo "  ->   $*"; }
stop() { echo; echo "  [FEHLER] $*"; exit 1; }
frage() { local a; read -rp "  ?    $1 [j/N] " a; [ "$a" = "j" ] || [ "$a" = "J" ]; }

echo "== Wolthusen Hub: Installation für https://${DOMAIN} =="
[ "$(id -u)" -eq 0 ] || stop "Bitte mit sudo starten: sudo bash deploy/installieren.sh"
[ -f "$APP/server.py" ] && [ -f "$APP/deploy/proxy/wolthusen.caddy" ] || stop "Skript liegt nicht im Hub-Ordner ($APP)."

# ------------------------------------------------------------------ 1. Voraussetzungen
echo; echo "1. Voraussetzungen"
command -v docker >/dev/null && docker compose version >/dev/null 2>&1 || stop "Docker mit Compose fehlt."
ok "Docker vorhanden"
[ -f "$PROXY/Caddyfile" ] && [ -f "$PROXY/.env" ] && [ -f "$PROXY/docker-compose.yml" ] || stop "Zentraler Proxy unter $PROXY fehlt (Caddyfile, .env, docker-compose.yml)."
grep -q '^(sicherheit)' "$PROXY/Caddyfile" || stop "In $PROXY/Caddyfile fehlt das Snippet (sicherheit), das der Wolthusen-Block braucht."
ok "Proxy unter $PROXY gefunden"
docker network inspect proxy >/dev/null 2>&1 || stop "Docker-Netzwerk proxy fehlt. Läuft der Proxy? (cd $PROXY && docker compose up -d)"
ok "Netzwerk proxy vorhanden"

IPS=$(getent ahosts "$DOMAIN" | awk '{print $1}' | sort -u | tr '\n' ' ')
if [ -z "$IPS" ]; then
  stop "$DOMAIN hat noch keinen DNS-Eintrag. A-Eintrag auf die IP des VPS setzen und später erneut starten."
fi
MEINE=" $(hostname -I) "
TREFFER=0
for ip in $IPS; do case "$MEINE" in *" $ip "*) TREFFER=1;; esac; done
if [ "$TREFFER" = 1 ]; then
  ok "DNS: $DOMAIN zeigt auf diesen Server ($IPS)"
else
  info "DNS: $DOMAIN zeigt auf $IPS, dieser Server hat $(hostname -I)"
  frage "Trotzdem weitermachen? (ohne passenden DNS gibt es kein Zertifikat)" || exit 1
fi

# ------------------------------------------------------------------ 2. Hub einrichten und starten
echo; echo "2. Hub"
cd "$APP"
if [ -f .env ]; then
  ok ".env vorhanden (wird nicht neu angelegt)"
  grep -q '^COMPOSE_FILE=docker-compose.proxy.yml' .env || {
    [ -z "$(tail -c1 .env)" ] || echo >> .env
    printf "# Betrieb hinter /opt/docker/proxy: nur der Hub, ohne eigenen Caddy\nCOMPOSE_FILE=docker-compose.proxy.yml\n" >> .env
    info "COMPOSE_FILE=docker-compose.proxy.yml ergänzt (sonst startet ein zweiter Caddy auf 80/443)"
  }
  ALT=$(grep '^DOMAIN=' .env | cut -d= -f2- || true)
  if [ "$ALT" != "$DOMAIN" ]; then
    sed -i "s|^DOMAIN=.*|DOMAIN=${DOMAIN}|" .env
    info "DOMAIN in .env von '${ALT}' auf '${DOMAIN}' gesetzt"
  fi
fi
# setup.sh legt eine fehlende .env an (fragt Admin und Passwort), setzt die Rechte von data/ und baut und startet den Container
WOLTHUSEN_DOMAIN="$DOMAIN" bash setup.sh --proxy
docker ps --format '{{.Names}}' | grep -qx wolthusen-hub || stop "Container wolthusen-hub läuft nicht. Logs: cd $APP && docker compose logs --tail 50"
ok "Container wolthusen-hub läuft"

# ------------------------------------------------------------------ 3. Proxy erweitern
echo; echo "3. Proxy"
cp "$PROXY/Caddyfile" "$PROXY/Caddyfile.vor-wolthusen-$STAMP"
cp "$PROXY/.env" "$PROXY/.env.vor-wolthusen-$STAMP"
zurueck() {
  cp "$PROXY/Caddyfile.vor-wolthusen-$STAMP" "$PROXY/Caddyfile"
  cp "$PROXY/.env.vor-wolthusen-$STAMP" "$PROXY/.env"
  echo "  ->   Caddyfile und .env des Proxys zurückgesetzt, laufender Caddy unverändert."
}
ok "Sicherung: Caddyfile.vor-wolthusen-$STAMP und .env.vor-wolthusen-$STAMP"

if grep -q 'WOLTHUSEN_DOMAIN' "$PROXY/Caddyfile"; then
  ok "Wolthusen-Block steht schon in der Caddyfile"
else
  [ -z "$(tail -c1 "$PROXY/Caddyfile")" ] || echo >> "$PROXY/Caddyfile"
  { echo; cat "$APP/deploy/proxy/wolthusen.caddy"; } >> "$PROXY/Caddyfile"
  info "Wolthusen-Block an die Caddyfile angehängt"
fi

if grep -q '^WOLTHUSEN_DOMAIN=' "$PROXY/.env"; then
  sed -i "s|^WOLTHUSEN_DOMAIN=.*|WOLTHUSEN_DOMAIN=${DOMAIN}|" "$PROXY/.env"
  ok "WOLTHUSEN_DOMAIN in $PROXY/.env gesetzt"
else
  [ -z "$(tail -c1 "$PROXY/.env")" ] || echo >> "$PROXY/.env"
  echo "WOLTHUSEN_DOMAIN=${DOMAIN}" >> "$PROXY/.env"
  info "WOLTHUSEN_DOMAIN in $PROXY/.env eingetragen"
fi

cd "$PROXY"
info "Caddyfile prüfen (Wegwerf-Container mit der neuen .env, der laufende Caddy bleibt unberührt) ..."
if ! docker compose run --rm --no-deps caddy caddy validate --config /etc/caddy/Caddyfile >/tmp/wolthusen-validate.log 2>&1; then
  tail -n 20 /tmp/wolthusen-validate.log
  zurueck
  stop "Caddyfile ungültig (Ausgabe oben). Nichts übernommen, beide Seiten laufen weiter."
fi
ok "Caddyfile gültig"

info "Caddy übernimmt die Änderung (die Tigers-Seite ist dabei einige Sekunden weg) ..."
docker compose up -d
docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile
ok "Caddy neu geladen"

# ------------------------------------------------------------------ 4. Testen
echo; echo "4. Test"
pruefe() {   # $1 = Domain; bis zu 2 Minuten, beim ersten Aufruf holt Caddy das Zertifikat
  local i antwort
  for i in $(seq 1 24); do
    antwort=$(curl -fsS --max-time 10 "https://$1/healthz" 2>/dev/null || true)
    case "$antwort" in *'"ok": true'*|*'"ok":true'*) ok "https://$1  $antwort"; return 0;; esac
    sleep 5
  done
  echo "  [!!] https://$1 antwortet nicht. Logs: cd $PROXY && docker compose logs --tail 50 caddy"
  return 1
}
FEHLER=0
pruefe "$DOMAIN" || FEHLER=1
TIGERS=$(grep '^HUB_DOMAIN=' "$PROXY/.env" | cut -d= -f2- | awk '{print $1}' || true)
if [ -n "$TIGERS" ]; then pruefe "$TIGERS" || FEHLER=1; fi

# ------------------------------------------------------------------ 5. Optional: Update-Knopf
echo; echo "5. Update-Knopf im Hub (Admin > Updates)"
if systemctl is-enabled wolthusen-updater.path >/dev/null 2>&1; then
  ok "schon eingerichtet"
elif frage "Jetzt einrichten?"; then
  bash "$APP/deploy/updater/install.sh"
else
  info "übersprungen (später: sudo bash deploy/updater/install.sh)"
fi

echo
if [ "$FEHLER" = 0 ]; then
  echo "Fertig. Anmelden: https://${DOMAIN}/login"
  echo "Als Nächstes im Hub: Verwaltung > Einstellungen > E-Mail-Versand."
else
  echo "Installiert, aber mindestens eine Seite antwortet nicht (siehe oben)."
  echo "Rückweg Proxy: cp $PROXY/Caddyfile.vor-wolthusen-$STAMP $PROXY/Caddyfile, ebenso .env, dann im Proxy-Ordner docker compose up -d"
  exit 1
fi
