#!/usr/bin/env bash
# Update-Helfer für den Admin-Bereich des Hubs einrichten (einmalig, auf dem VPS):
#   cd /opt/docker/apps/wolthusen-hub && sudo bash deploy/updater/install.sh
# Danach zeigt Admin > Updates die Versionen und kann Hub, Caddy und Ubuntu-Updates anstoßen.
# Entfernen: sudo systemctl disable --now wolthusen-updater.path wolthusen-updater-check.timer
set -euo pipefail
cd "$(dirname "$0")"
APP=/opt/docker/apps/wolthusen-hub

if [ "$(id -u)" != "0" ]; then echo "Bitte mit sudo starten."; exit 1; fi
command -v python3 >/dev/null || { echo "python3 fehlt (sudo apt install python3)."; exit 1; }

install -m 755 wolthusen-updater.py /usr/local/sbin/wolthusen-updater.py
install -m 644 wolthusen-updater.service wolthusen-updater.path wolthusen-updater-check.service wolthusen-updater-check.timer /etc/systemd/system/
# Ordner für Anfrage und Status: der Hub (Benutzer 1000 im Container) darf hier schreiben, der Helfer prüft alles selbst
install -d -o 1000 -g 1000 -m 755 "$APP/data/updater"

systemctl daemon-reload
systemctl enable --now wolthusen-updater.path wolthusen-updater-check.timer
echo "-> Erste Prüfung der Versionen läuft (dauert etwa eine Minute) ..."
systemctl start wolthusen-updater-check.service || true
echo "Fertig. Im Hub unter Admin > Updates nachsehen."
