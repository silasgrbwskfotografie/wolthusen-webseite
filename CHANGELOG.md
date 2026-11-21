# Änderungen

## 1.2 (21.11.2026)
- Neuer Reiter Verein > Mannschaften: links alle Mannschaften nach Sportart (Fußball, Fußball Jugend, American Football, Turnen & Gymnastik, Sonstiges),
  rechts alles zu einer Mannschaft: Texte, Links, Titelbild der Seite, Trainingszeiten, Trainer und Betreuer, Kader, Spiele
- Mannschaften frei anlegen, umbenennen (Spiele, Kader, Training und News ziehen mit), inaktiv stellen oder löschen (nur ohne Einträge)
- Webseite: Mannschaftsseiten, Menü, Fußball-Seite und Sitemap kommen aus dem Hub; jede Mannschaft mit eigener Seite hat ihr eigenes Titelbild
- Turngruppen und die Tigers sind jetzt Mannschaften (ohne eigene Seite vorbelegt, im Hub einschaltbar)
- Wappen groß und blass im Hintergrund des Hubs
- DFBnet-Import: Lesen und Abgleichen des Spielplans im Server (Oberfläche folgt)

## 1.1 (21.11.2026)
- Installation auf dem VPS neben dem Emden Tigers Hub unter wolthusen.silasgrbwskfotografie.de: Anleitung in `deploy/DEPLOY.md`,
  Caddy-Block `deploy/proxy/wolthusen.caddy` für den zentralen Proxy (ganze Seite vorerst noindex)
- Bilder der Mail-Signatur kommen von der eigenen Adresse (`SITE_URL`), solange amisia-stern.de noch auf die alte Seite zeigt

## 1.0 (21.11.2026)
Erste Fassung des Wolthusen Hub: Vereinswebseite und Vereinsverwaltung des SV Amisia Wolthusen in einem Server.
Grundlage ist der Emden Tigers Hub 5.16 (der frühere Änderungsverlauf steht dort im Repository).

- Öffentliche Webseite im Wolthusen Design (Violett, Nachtviolett, Weiß, Wappen „SV AMISIA“), Menü mit Untermenüs Sportarten und Verein
  - Feste Seiten aus `seiten/`: Start, Fußball, American Football, Turnen & Gymnastik, Saal, Partner, Mitglied werden
  - Aus dem Hub: Mannschaftsseiten `/mannschaft/<name>` (Training, Trainer, Kader, Spiele, Ergebnisse, fussball.de), Spielplan aller Mannschaften,
    News, Kontaktformular mit Anliegen (Mitgliedschaft, Probetraining, Turnen, Saal, Sponsoring), Newsletter, Dauerkarte, Impressum, Datenschutz
  - Startseite mit nächsten Spielen, Ergebnissen, News, Partnern und Instagram (im Hub sortier- und ausblendbar)
- Fußball statt American Football: Mannschaften Erste, Zweite, Alte Herren und D- bis G-Jugend, Positionen Tor/Abwehr/Mittelfeld/Sturm,
  Rollen Trainer, Co-Trainer, Torwarttrainer, Betreuer, Zeugwart, Jugendleitung; Spieler der Jugend erscheinen nie auf der Webseite
- Neu im Hub: Trainingszeiten je Mannschaft und Gruppe (erscheinen auf der Webseite), Belegung von Saal, Sportplatz und Halle mit Miete, Kaution und Status
- Supporter Karte heißt Dauerkarte (Eintritt zu allen Heimspielen der Ersten Herren)
- Gruppen: Vorstand, Kassenwart, Spartenleitung, Trainer, Media Team, Helfer, Spieler, Wartung
- Heimspieltag-Vorlagen für Fußball (Kasse, Kiosk, Grill, Linienrichter; Checkliste mit DFBnet, Platz abkreiden, Kabinen)
- Impressum und Datenschutzerklärung für den Verein (Mitgliedschaft, Saalvermietung, NFV, Fotos von Kindern)
- Briefpapier, Rechnungen, Mail-Signatur, Newsletter und Hub-Icons mit dem Vereinswappen
- Entfernt: Livescore und die Anbindung an Highlight Desk (`/live/*`, `/public/live`, `/spielstand`, Token in den Einstellungen)
- Prüfskript `tests/seiten_rendern.py`: rendert alle Seiten ohne Server gegen eine Testdatenbank
