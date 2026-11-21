#!/usr/bin/env bash
# Wolthusen Hub: Einrichtung auf einem Linux-VServer (Debian/Ubuntu)
# Aufruf im Projektordner:  sudo bash setup.sh
#   mit eigenem Caddy (Ports 80/443 gehören dem Hub):          sudo bash setup.sh
#   hinter dem zentralen Proxy (/opt/docker/proxy, DEPLOY.md):  sudo bash setup.sh --proxy
set -euo pipefail
cd "$(dirname "$0")"
PROXY=0
[ "${1:-}" = "--proxy" ] && PROXY=1

echo "== Wolthusen Hub: Einrichtung =="

if [ "$(id -u)" -ne 0 ]; then
  echo "Bitte mit sudo ausführen: sudo bash setup.sh"; exit 1
fi

# 0. Git (für Updates) sicherstellen
if ! command -v git >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq git
fi

# 1. Docker installieren, falls nicht vorhanden
if ! command -v docker >/dev/null 2>&1; then
  echo "-> Docker wird installiert ..."
  curl -fsSL https://get.docker.com | sh
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose fehlt. Bitte das Paket docker-compose-plugin installieren."; exit 1
fi

# 2. .env anlegen
if [ ! -f .env ]; then
  cp .env.example .env
  DOMAIN="${WOLTHUSEN_DOMAIN:-}"   # von deploy/installieren.sh vorgegeben
  [ -n "$DOMAIN" ] || read -rp "Domain für den Hub (z. B. hub.deinedomain.de): " DOMAIN
  REDIR=""; MAIL=""
  if [ "$PROXY" = 0 ]; then   # hinter dem zentralen Proxy regelt dessen Caddyfile Zertifikat und Umleitungen
    read -rp "Weitere Adressen, die auf diese Domain umleiten (z. B. www.${DOMAIN}, mehrere mit Leerzeichen, leer = keine): " REDIR
    read -rp "E-Mail für das HTTPS-Zertifikat: " MAIL
  fi
  read -rp "Admin-Benutzername [silas]: " ADMIN; ADMIN=${ADMIN:-silas}
  while true; do
    read -rsp "Admin-Passwort (mind. 10 Zeichen): " PW; echo
    read -rsp "Passwort wiederholen: " PW2; echo
    if [ "$PW" != "$PW2" ]; then echo "Stimmt nicht überein."; continue; fi
    if [ ${#PW} -lt 10 ]; then echo "Zu kurz."; continue; fi
    case "$PW" in *\'*) echo "Bitte ohne Apostroph ('), das stört die Konfigurationsdatei."; continue;; esac
    break
  done
  sed -i "s|^DOMAIN=.*|DOMAIN=${DOMAIN}|; s|^ACME_EMAIL=.*|ACME_EMAIL=${MAIL}|; s|^TMH_ADMIN_USER=.*|TMH_ADMIN_USER=${ADMIN}|" .env
  # Passwort in einfachen Anführungszeichen speichern, damit Sonderzeichen wie $ oder # erhalten bleiben
  grep -v '^TMH_ADMIN_PASSWORD=' .env > .env.tmp
  printf "TMH_ADMIN_PASSWORD='%s'\n" "$PW" >> .env.tmp
  REDIR=$(echo "${REDIR:-}" | tr ',' ' ' | tr -s ' ' | sed 's/^ //; s/ $//')
  if [ -n "$REDIR" ]; then printf "REDIRECT_DOMAINS=%s\n" "$REDIR" >> .env.tmp; fi
  if [ "$PROXY" = 1 ]; then printf "# Betrieb hinter /opt/docker/proxy: nur der Hub, ohne eigenen Caddy\nCOMPOSE_FILE=docker-compose.proxy.yml\n" >> .env.tmp; fi
  mv .env.tmp .env
  chmod 600 .env
  echo "-> .env angelegt."
else
  echo "-> .env ist schon vorhanden, wird nicht verändert."
fi

# 3. Datenordner mit passenden Rechten (Container läuft als Benutzer 1000)
mkdir -p data
chown -R 1000:1000 data

# 4. Starten
if grep -q '^COMPOSE_FILE=docker-compose.proxy.yml' .env; then
  docker network inspect proxy >/dev/null 2>&1 || docker network create proxy >/dev/null
  echo "-> Betrieb hinter dem zentralen Proxy (Netzwerk proxy). Caddy dort muss wolthusen-hub:8765 kennen."
fi
docker compose up -d --build
echo
echo "Fertig. Der Hub startet jetzt. Das HTTPS-Zertifikat wird beim ersten Aufruf automatisch geholt."
echo "Adresse: https://$(grep '^DOMAIN=' .env | cut -d= -f2)"
echo "Status:  docker compose ps    |    Logs: docker compose logs -f hub"
echo "Updates: sudo bash update.sh"
