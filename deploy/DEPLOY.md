# Betrieb auf dem VPS

Ablage auf dem Server: `/opt/docker/DEPLOY.md` (Vorlage im Repository unter `deploy/DEPLOY.md`).

## Aufbau

```
/opt/docker/
├── DEPLOY.md                  diese Anleitung
├── proxy/                     zentraler Reverse Proxy (Caddy), einziger Container mit Ports 80 und 443
│   ├── docker-compose.yml
│   ├── Caddyfile              Domains, Weiterleitungen, Sicherheits-Header
│   └── .env                   ACME_EMAIL, HUB_DOMAIN, HUB_REDIRECTS, später APP2_DOMAIN (nicht im Repository)
└── apps/
    ├── wolthusen-hub/      app1: Git-Repository des Hubs
    │   ├── .env               DOMAIN, COMPOSE_FILE=docker-compose.proxy.yml, Admin beim ersten Start
    │   └── data/              Datenbank, Bilder, Sicherungen (nie löschen)
    └── app2/                  später
```

```
Internet ──> 80/443 ──> proxy-caddy ──(Netzwerk "proxy")──> wolthusen-hub:8765
                                    └─────────────────────> app2 (später)
```

- Die Firewall (ufw) lässt nur SSH, 80 und 443 durch. Die Programme öffnen selbst keine Ports.
- Zertifikate holt Caddy automatisch bei Let's Encrypt und erneuert sie selbst (im Volume `caddy_data`).
- Zugangsdaten und Domains stehen nur in den `.env`-Dateien, nie im Repository.

## Anmelden

Putty mit dem Benutzer `wolthusenhub` und der Schlüsseldatei `wolthusen_vps.ppk` (Putty: Connection > SSH > Auth > Credentials).
Anmeldung per Passwort und als `root` ist abgeschaltet. Befehle mit `sudo` fragen nach dem Passwort von `wolthusenhub`.

## Täglicher Betrieb

| Was | Befehl |
|---|---|
| **Hub aktualisieren** (nach Push auf `main`) | `cd /opt/docker/apps/wolthusen-hub && sudo bash update.sh` |
| Status aller Container | `docker ps` |
| Logs Hub | `cd /opt/docker/apps/wolthusen-hub && docker compose logs -f --tail 100` |
| Logs Proxy (Zertifikate, Fehler) | `cd /opt/docker/proxy && docker compose logs -f --tail 100` |
| Hub neu starten | `cd /opt/docker/apps/wolthusen-hub && docker compose restart` |
| Proxy neu starten | `cd /opt/docker/proxy && docker compose restart` |
| Caddyfile geändert, ohne Unterbrechung neu laden | `cd /opt/docker/proxy && docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile` |
| Caddy-Abbild aktualisieren | `cd /opt/docker/proxy && docker compose pull && docker compose up -d` |
| Version des Hubs | `curl -s https://amisia-stern.de/healthz` |
| Firewall | `sudo ufw status verbose` |
| Gesperrte IPs (SSH) | `sudo fail2ban-client status sshd` |
| Neustart nötig nach Updates? | `ls /var/run/reboot-required` (wenn vorhanden: `sudo reboot`, alles startet von selbst) |

`update.sh` legt vor jedem Update eine Sicherung der Datenbank an (`data/backups/vor-update-...db`), holt den neuen Stand von GitHub,
baut den Container neu und prüft, ob der Hub antwortet. Auf dem Server keine Dateien im Repository von Hand ändern.

## Sicherungen

- Der Hub sichert jede Nacht die Datenbank nach `data/backups/` (14 Tage).
- Zusätzlich regelmäßig auf den PC holen (PowerShell):
  ```
  scp -i $env:USERPROFILE\.ssh\wolthusen_vps -r wolthusenhub@[IP des Servers]:/opt/docker/apps/wolthusen-hub/data/backups .\WolthusenHub-Sicherung
  ```
  oder im Hub unter Verwaltung > Einstellungen > Backup herunterladen.
- Wenn der Anbieter Snapshots anbietet: vor größeren Änderungen einen anlegen.

## app2 hinzufügen (Schritt für Schritt)

1. **DNS**: Beim Domain-Anbieter für die Domain von app2 einen A-Eintrag auf `[IP des Servers]` setzen. Prüfen: `getent hosts app2.domain.de` zeigt die IP.
2. **Programm ablegen**:
   ```
   sudo mkdir -p /opt/docker/apps/app2 && sudo chown wolthusenhub: /opt/docker/apps/app2
   cd /opt/docker/apps/app2
   git clone <Repository-Adresse> .      # oder Dateien per WinSCP hochladen
   ```
   Zugangsdaten des Programms in `/opt/docker/apps/app2/.env` (Rechte: `chmod 600 .env`).
3. **docker-compose.yml für app2** (in `/opt/docker/apps/app2`), Grundgerüst:
   ```yaml
   services:
     app2:
       build: .                     # oder image: hersteller/programm:version
       container_name: app2
       restart: unless-stopped
       env_file: .env
       expose:
         - "3000"                   # interner Port des Programms, NICHT unter ports
       networks: [proxy]
   networks:
     proxy:
       external: true
   ```
   Starten: `docker compose up -d --build`
4. **Proxy**: In `/opt/docker/proxy/.env` die Zeile `APP2_DOMAIN=app2.domain.de` eintragen und im `Caddyfile` den Block `app2` einkommentieren
   (Port hinter `reverse_proxy app2:` an das Programm anpassen). Dann:
   ```
   cd /opt/docker/proxy && docker compose up -d && docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
   ```
   Hinweis: Neue Werte aus der `.env` übernimmt Caddy erst nach `docker compose up -d` (Container neu erstellt), ein reines `reload` reicht dafür nicht.
5. **Testen**: `curl -I https://app2.domain.de` (Status 200 oder 302) und `docker compose logs caddy` im Proxy-Ordner (Zertifikat geholt).
   Die Firewall muss nicht geändert werden, alles läuft über 443.

## Notfall

- **Seite nicht erreichbar**: `docker ps` (laufen `proxy-caddy` und `wolthusen-hub`?), dann die Logs von Proxy und Hub.
- **Zertifikat fehlt**: Proxy-Logs nach `error` durchsuchen. Häufigste Ursachen: DNS zeigt nicht auf den Server, Port 80 in einer Firewall des Anbieters zu.
- **Admin-Passwort vergessen**: in `/opt/docker/apps/wolthusen-hub/.env` `TMH_RESET_PASSWORD=1` und `TMH_ADMIN_PASSWORD='neues-passwort'` setzen,
  `docker compose up -d`, danach beide Zeilen wieder entfernen bzw. auf `0` stellen.
- **Zurück auf eine ältere Version des Hubs**: siehe INSTALLATION.md, Abschnitt Updates.
- **SSH-Schlüssel verloren**: über die Web-Konsole des Anbieters (VNC/Notfallkonsole) anmelden und einen neuen Schlüssel in `~wolthusenhub/.ssh/authorized_keys` eintragen.
