# Start auf dem VPS

> **Stand 13.11.2026: erledigt.** Der VPS läuft unter amisia-stern.de mit zentralem Proxy unter `/opt/docker`. Für den laufenden Betrieb gilt `deploy/DEPLOY.md` (Pfade dort: `/opt/docker/apps/wolthusen-hub` statt `/opt/WolthusenHub`).

Fahrplan für den echten Server im Internet. Der VPS startet **leer**: keine Testdaten, keine Testkonten, nichts von der Test-VM.
Die Test-VM bleibt nur zum Ausprobieren von Updates.

Ab Werk sind nur die Standardgruppen (Vorstand, Trainer, Media Team, Fotografen, Helfer, Spieler, Wartung) und die Vereinstexte der Webseite
(Training, Adressen, Supporter Karte, Impressum- und Datenschutz-Vorlage) vorbelegt. Alles andere trägst du auf dem VPS neu ein.

Dauer: etwa 1 bis 2 Stunden, davon das meiste Warten (DNS, Bestellung beim Anbieter).

## 0. Vorher entscheiden und besorgen

| Was | Hinweis | Erledigt |
|---|---|---|
| **VPS-Anbieter** | Rechenzentrum in Deutschland, **Debian 12** oder **Ubuntu 24.04**. Empfehlung: 2 GB RAM, 2 Kerne, ab 40 GB SSD (die Mediathek wächst). 1 GB RAM geht auch, `server-haerten.sh` legt dann eine Auslagerungsdatei an. | [ ] |
| **Vertrag zur Auftragsverarbeitung (AVV)** | Beim Anbieter abschließen (meist ein Klick im Kundenmenü). Name und Anschrift des Anbieters in der Datenschutzerklärung beim Abschnitt „Hosting“ eintragen. | [ ] |
| **Snapshots/Backups beim Anbieter** | Wenn möglich dazubuchen. Die nächtlichen Sicherungen des Hubs liegen sonst nur auf demselben Server. | [ ] |
| **Domain** | Welche Adresse soll es werden (z. B. `amisia-stern.de`, dazu `www.amisia-stern.de`)? Zugang zur DNS-Verwaltung beim Domain-Anbieter. | [ ] |
| **E-Mail-Postfach** für den Versand | Server, Port, Benutzer, App-Passwort (bei Gmail ein App-Passwort). Wird auf dem VPS neu eingetragen. | [ ] |
| **SSH-Schlüssel** für den VPS | Am PC: `ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\wolthusen_vps` (Passphrase empfohlen). Den Inhalt von `wolthusen_vps.pub` bei der Bestellung als SSH-Schlüssel hinterlegen. | [ ] |

**Achtung bei der Domain:** Läuft unter der Domain schon eine Webseite oder ein **E-Mail-Postfach**, beim Umstellen nur die **A-** und **AAAA-Einträge** für die Domain und `www` ändern.
Die **MX-Einträge** (E-Mail) und TXT-Einträge (SPF, DKIM) nie anfassen, sonst kommen keine Mails mehr an.

## 1. Code vorbereiten (am PC)

Branch `webseite` in `main` übernehmen und `main` pushen. Der VPS holt immer `main`.

## 2. VPS absichern

Am PC in PowerShell anmelden (IP aus der Mail des Anbieters):
```
ssh -i $env:USERPROFILE\.ssh\wolthusen_vps root@VPS-IP
```
Dann auf dem VPS:
```
apt update && apt install -y git
git clone https://github.com/silasgrbwskfotografie/wolthusen-hub.git /opt/WolthusenHub
cd /opt/WolthusenHub
bash server-haerten.sh
```
`server-haerten.sh` spielt Updates ein, schaltet automatische Sicherheitsupdates ein, stellt die Zeitzone ein, öffnet in der Firewall nur SSH, 80 und 443,
sperrt IPs nach falschen SSH-Anmeldungen (fail2ban) und legt auf Wunsch den Benutzer `wolthusenhub` an. Erst wenn die Anmeldung als `wolthusenhub` in einem
**zweiten Fenster** klappt, schaltet es Passwort- und root-Anmeldung ab. Ab dann:
```
ssh -i $env:USERPROFILE\.ssh\wolthusen_vps wolthusenhub@VPS-IP
```
Hat der Anbieter eine eigene Firewall im Kundenmenü, dort ebenfalls 22, 80 und 443 freigeben.

## 3. DNS umstellen

Beim Domain-Anbieter:

| Typ | Name | Wert |
|---|---|---|
| A | `@` (die Domain selbst) | IPv4 des VPS |
| A | `www` | IPv4 des VPS |
| AAAA | `@` und `www` | IPv6 des VPS (nur wenn der VPS eine hat) |

Die Änderung braucht meist Minuten, selten einige Stunden. Prüfen am PC: `Resolve-DnsName amisia-stern.de` muss die VPS-IP zeigen.
Erst danach mit Schritt 4 weitermachen, sonst kann Caddy kein Zertifikat holen (es versucht es später aber selbst erneut).

## 4. Hub installieren

Auf dem VPS:
```
cd /opt/WolthusenHub
sudo bash setup.sh
```
Abfragen:
- **Domain**: z. B. `amisia-stern.de` (ohne https, ohne Schrägstrich)
- **Weitere Adressen**: z. B. `www.amisia-stern.de` (leiten automatisch auf die Domain um)
- **E-Mail für das Zertifikat**: eine echte Adresse des Vereins
- **Admin-Benutzer und Passwort**: nur vorläufig, wird beim Import ersetzt

Danach im Browser `https://amisia-stern.de/healthz` öffnen. Es muss `{"ok": true, "version": "..."}` erscheinen, ohne Zertifikatswarnung.

## 5. Erste Schritte im leeren Hub

1. Unter `https://amisia-stern.de/login` mit dem Admin aus `setup.sh` anmelden.
2. **Sofort den Wartungsmodus einschalten** (Verwaltung > Wartungsmodus). Besucher sehen dann nur die Wartungsseite, bis alles eingepflegt ist.
   Impressum und Datenschutz bleiben erreichbar.
3. **Mein Profil**: Zwei-Faktor-Anmeldung einrichten (QR-Code mit der Authenticator-App scannen, Wiederherstellungscodes sicher ablegen).
   Danach unter Verwaltung > Konten die 2FA-Pflicht für Admins einschalten.
4. In der `.env` auf dem VPS die Zeile `TMH_ADMIN_PASSWORD=...` löschen (wird nach dem ersten Start nicht mehr gebraucht):
   ```
   sudo nano /opt/WolthusenHub/.env
   ```
5. **Verwaltung > Einstellungen**: E-Mail-Versand eintragen (Adresse des Hubs: `https://amisia-stern.de`), Test-Mail senden.
   Dort auch Saison, Preise und Rechnungsdaten (Absender, Bank, Steuerhinweis) prüfen.
6. **Medien > Webseite**: Texte, Impressum und Datenschutz ausfüllen (alle [eckigen Klammern], Hosting-Anbieter eintragen), eigene Bilder hochladen.
   Die Übersicht zeigt, was noch fehlt.
7. **Medien > Auto-Posting > Einrichtung**: Facebook-Seite verbinden (neues Seiten-Token), öffentliche Adresse `https://amisia-stern.de`.
8. Inhalte anlegen: Kader & Staff (oder Spielerbogen freischalten), Spielplan, Gegner, Sponsoren, Media Team.
9. **Konten**: Zugänge per Einladungslink verschicken und den Gruppen zuordnen (Spieler in die Gruppe Spieler, Trainer in Trainer usw.).
10. Wenn alles passt: Wartungsmodus ausschalten.

## 6. Vor dem Ausschalten des Wartungsmodus prüfen

| Prüfen | Wo | OK |
|---|---|---|
| Webseite, alle Seiten (angemeldet sichtbar trotz Wartung) | `https://amisia-stern.de` | [ ] |
| `www.` leitet auf die Domain um | `https://www.amisia-stern.de` | [ ] |
| Anmeldung, 2FA, Rechte eines zweiten Kontos (z. B. Spieler) | Hub | [ ] |
| **Test-Mail** kommt an | Verwaltung > Einstellungen > E-Mail-Versand | [ ] |
| Facebook/Instagram-Verbindung, Test-Post | Medien > Auto-Posting > Einrichtung | [ ] |
| Instagram-Raster auf der Startseite (lädt innerhalb von 30 Minuten) | Startseite | [ ] |
| Kontaktformular einmal ausfüllen, Anfrage kommt im Hub an | `/kontakt`, Mitglieder > Anfragen | [ ] |
| Supporter Karte: Bestellung testen und stornieren (falls geöffnet) | `/supporter-karte` | [ ] |
| Impressum und Datenschutz: alle [eckigen Klammern] ausgefüllt, Hosting-Anbieter eingetragen | Medien > Webseite > Übersicht | [ ] |
| Hub als App auf dem Handy hinzufügen (alte Verknüpfung zur VM löschen) | Handy | [ ] |

Links aus der Testzeit (Einladungen, Bestelllinks) gehören zur VM und gelten auf dem VPS nicht. Auf dem VPS neu erzeugen und verschicken.

**Google:** Unter https://search.google.com/search-console die Domain anmelden und `https://amisia-stern.de/sitemap.xml` einreichen. Die Webseite ist jetzt für Suchmaschinen freigegeben, der Hub nicht.

## 7. Laufender Betrieb

- **Updates**: am PC pushen, auf dem VPS `cd /opt/WolthusenHub && sudo bash update.sh` (legt vorher eine Sicherung an).
- **Sicherungen**: jede Nacht automatisch in `data/backups/` (14 Tage). Zusätzlich regelmäßig eine Kopie auf den PC holen:
  ```
  scp -i $env:USERPROFILE\.ssh\wolthusen_vps -r wolthusenhub@VPS-IP:/opt/WolthusenHub/data/backups .\WolthusenHub-Sicherung
  ```
  oder im Hub **Einstellungen > Backup herunterladen**. Eine Sicherung nur auf demselben Server schützt nicht, wenn der Server ausfällt.
- **Server-Updates** laufen automatisch. Ab und zu neu starten, wenn `/var/run/reboot-required` existiert: `sudo reboot` (der Hub startet von selbst wieder).
- **Protokolle** der Container sind auf 50 MB begrenzt (`docker-compose.yml`).

## 8. Test-VM

Bleibt als Testumgebung: neue Versionen zuerst dort mit `update.sh` ausprobieren, dann auf dem VPS. Ihre Daten sind Testdaten und kommen nie auf den VPS.
Wird sie nicht mehr gebraucht, die Portweiterleitung am PC (Windows `netsh interface portproxy`) entfernen und die VM löschen.
