# Wolthusen Hub

Webseite und Vereinsverwaltung des **SV Amisia Wolthusen e.V.** (Emden-Wolthusen) in einem kleinen Python-Server.

- **Webseite** unter `/`: Fußball mit allen Mannschaften, Spielplan, News, American Football (Emden Tigers), Turnen & Gymnastik, Saal, Partner, Mitglied werden, Kontakt, Newsletter.
- **Hub** unter `/hub` (mit Login): Spielplan, Kader & Trainer, Trainingszeiten, Belegung Saal & Platz, Heimspieltag mit Helferliste, Teamkleidung, Sponsoren mit Verträgen und Rechnungen,
  Mitglieder, Finanzen, Dauerkarte, News, Newsletter, Social-Media-Planung, Postfach, Webseiten-Texte und -Bilder, Konten mit Gruppen, Rechten und Zwei-Faktor-Anmeldung.

Nur Python 3 Standardbibliothek, keine externen Pakete, keine Tracker oder Cookies auf der Webseite.

## Aufbau
- `server.py`: Server, Datenbank (SQLite), API, Hub, Mails, PDFs
- `website.py`: baut die öffentlichen Seiten
- `seiten/`: feste Inhalte der Webseite (HTML mit Platzhaltern wie `{{BILD:hero}}`, `{{TRAINING:Erste Herren}}`)
- `web/assets/`: Stylesheet, Skript, Schriften, Wappen, Bilder, Downloads, Mail-Signatur
- `static/`: Oberfläche des Hubs
- `tests/seiten_rendern.py`: prüft alle Seiten ohne Server

## Prüfen
```
python3 -m pyflakes server.py website.py
python3 tests/seiten_rendern.py
```

## Auf den Server bringen
Docker mit Caddy (HTTPS automatisch): siehe [INSTALLATION.md](INSTALLATION.md), hinter einem gemeinsamen Proxy [deploy/DEPLOY.md](deploy/DEPLOY.md).
Was noch fehlt: [PLATZHALTER.md](PLATZHALTER.md).
