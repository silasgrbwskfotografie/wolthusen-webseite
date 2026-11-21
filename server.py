"""
Wolthusen Hub
Vereinsverwaltung des SV Amisia Wolthusen: Medien, Verein, Mitglieder, Finanzen mit Konten und Rechten.

Betrieb auf dem Server: siehe INSTALLATION.md (Docker Compose mit Caddy und HTTPS).
Lokal:                  python server.py   (oder Start.bat unter Windows)

Benötigt nur Python 3.10+ (keine zusätzlichen Pakete).

Konfiguration über Umgebungsvariablen:
  TMH_HOST            Adresse, an die der Server bindet (Standard 127.0.0.1, im Container 0.0.0.0)
  TMH_PORT            Port (Standard 8765)
  TMH_DATA            Datenordner (Standard: Ordner "data" neben dieser Datei)
  TMH_SERVER          1 = Serverbetrieb (kein Browser, keine Ersteinrichtung über die Webseite)
  TMH_SECURE_COOKIES  1 = Login-Cookie nur über HTTPS (hinter Caddy immer 1)
  TMH_TRUST_PROXY     1 = Client-IP aus X-Forwarded-For übernehmen (hinter Caddy)
  TMH_ADMIN_USER      Benutzername des ersten Admins
  TMH_ADMIN_PASSWORD  Passwort des ersten Admins (wird nur genutzt, solange es keinen Benutzer gibt)
  TMH_RESET_PASSWORD  1 = Passwort von TMH_ADMIN_USER beim Start auf TMH_ADMIN_PASSWORD zurücksetzen
  TMH_BACKUP_KEEP     Anzahl täglicher Sicherungen, die aufbewahrt werden (Standard 14)
"""

import base64
import struct
import contextlib
import hashlib
import hmac
import secrets
import shutil
import time
import io
import json
import mimetypes
import os
import re
import sqlite3
import sys
import threading
import uuid
import webbrowser
import zipfile
from datetime import date, datetime, timedelta
from email.utils import parseaddr
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs, urlencode, quote
import urllib.request
import urllib.error

import website   # öffentliche Webseite (website.py, gleiche Ordnerebene)

VERSION = "1.0"
APP_NAME = "Wolthusen Hub"
ENV = os.environ.get
HOST = ENV("TMH_HOST", "127.0.0.1")
PORT = int(ENV("TMH_PORT", "8765"))
SERVER_MODE = ENV("TMH_SERVER") == "1"
SECURE_COOKIES = ENV("TMH_SECURE_COOKIES") == "1"
TRUST_PROXY = ENV("TMH_TRUST_PROXY") == "1"
BACKUP_KEEP = int(ENV("TMH_BACKUP_KEEP", "14"))
SITE_URL = (ENV("SITE_URL") or "").rstrip("/")   # öffentliche Adresse, z. B. https://amisia-stern.de (vorerst die Server-IP)
MAX_BODY = 300 * 1024 * 1024          # 300 MB (Backup einspielen)
MAX_JSON = 60 * 1024 * 1024           # 60 MB (Bild-Upload als Base64)
SESSION_DAYS = 30
COOKIE = "tmh_session"

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
DATA = Path(ENV("TMH_DATA") or (BASE / "data")).resolve()
MEDIA = DATA / "media"
DB_PATH = DATA / "wolthusen.db"
BACKUPS = DATA / "backups"
STARTED = time.time()
# Seite „Admin“ im Hub: Prüfung auf neue Versionen (öffentliches Repository, nur der Kopf von server.py) und Server-Pfade
UPDATE_SOURCE = ENV("TMH_UPDATE_URL", "https://raw.githubusercontent.com/silasgrbwskfotografie/wolthusen-webseite/main/server.py")
REPO_URL = "https://github.com/silasgrbwskfotografie/wolthusen-webseite"
BEHIND_PROXY = ENV("COMPOSE_FILE", "") == "docker-compose.proxy.yml"   # Betrieb hinter /opt/docker/proxy (siehe deploy/DEPLOY.md)
HOST_DIR = ENV("TMH_HOST_DIR") or ("/opt/docker/apps/wolthusen-hub" if BEHIND_PROXY else "/opt/WolthusenHub")
SSH_USER = ENV("TMH_SSH_USER", "wolthusenhub")

# Mannschaften (players.team, games.team). Gleiche Liste in static/pages/01-grundlagen.js (TEAMS) und website.py.
TEAMS = ("Erste Herren", "Zweite Herren", "Alte Herren", "D-Jugend", "E-Jugend", "F-Jugend", "G-Jugend")
MAIN_TEAM = TEAMS[0]   # Standard für neue Spieler und Spiele
YOUTH_TEAMS = {"D-Jugend", "E-Jugend", "F-Jugend", "G-Jugend"}   # Spieler (Minderjährige) erscheinen nie auf der Webseite
# Anliegen im Kontaktformular der Webseite (landet als Quelle in contact_requests), wie CONTACT_TOPICS in website.py
CONTACT_TOPICS = ("Allgemeine Frage", "Mitgliedschaft", "Probetraining Herren", "Probetraining Jugend", "Turnen und Gymnastik", "Saal mieten", "Sponsoring", "Dauerkarte")

# ---------------------------------------------------------------------------
# Datenbank-Schema
# Jede Tabelle: Spaltenname -> SQL-Typ. "id" wird automatisch angelegt.
# Neue Spalten können hier einfach ergänzt werden, sie werden beim Start
# automatisch zur bestehenden Datenbank hinzugefügt.
# ---------------------------------------------------------------------------
TABLES = {
    "players": {
        "kind": "TEXT DEFAULT 'Spieler'",      # Spieler / Coach / Staff
        "first_name": "TEXT",
        "last_name": "TEXT",
        "number": "TEXT",
        "position": "TEXT",
        "unit": "TEXT",                         # Offense / Defense / Special Teams / Staff
        "role": "TEXT",                         # z. B. Headcoach, OC, DC
        "rookie": "INTEGER DEFAULT 0",
        "since": "TEXT",                        # dabei seit
        "photo": "TEXT",
        "instagram": "TEXT",
        "consent": "INTEGER DEFAULT 0",         # Foto-/Veröffentlichungseinwilligung
        "active": "INTEGER DEFAULT 1",
        "nickname": "TEXT",
        "facts": "TEXT",                        # Funfacts / Fußball-Geschichte
        "notes": "TEXT",
        "source": "TEXT",                       # Herkunft, z. B. "Tabelle" (frühere Google-Tabelle)
        "team": "TEXT DEFAULT 'Erste Herren'",        # Mannschaft (TEAMS)
        "extra_role": "TEXT",                   # Zusatzrolle eines Spielers (z. B. Social Media Betreuer, Position Coach)
        "email": "TEXT",                        # intern (nie auf der Webseite, public_team gibt es nicht aus)
        "phone": "TEXT",                        # intern
    },
    "hub_plans": {                              # Planung neuer Projekte für den Hub (Seite Admin > Planung, nur Admins)
        "title": "TEXT",
        "status": "TEXT DEFAULT 'Idee'",        # Idee / Geplant / In Arbeit / Erledigt
        "priority": "TEXT DEFAULT 'Mittel'",    # Hoch / Mittel / Niedrig
        "category": "TEXT",                     # Webseite / Hub / Team / Finanzen / Server / Sonstiges
        "target_version": "TEXT",
        "due": "TEXT",
        "description": "TEXT",
        "steps": "TEXT",                        # Schritte, eine pro Zeile, erledigte mit [x]
        "notes": "TEXT",
        "sort": "INTEGER DEFAULT 0",
        "done_at": "TEXT",
    },
    "admin_notes": {                            # Notizen der Admins (Verwaltung > Notizen, nur Admins)
        "title": "TEXT",
        "body": "TEXT",                         # Klartext, oder bei encrypted=1 JSON {v, salt, iv, ct}: AES-GCM im Browser, Passwort verlässt ihn nie
        "encrypted": "INTEGER DEFAULT 0",
        "pinned": "INTEGER DEFAULT 0",
        "updated": "TEXT",
    },
    "player_signups": {                         # Eingänge aus dem Spielerbogen (/spielerbogen/<token>), erst nach Prüfung in den Kader
        "first_name": "TEXT",
        "last_name": "TEXT",
        "nickname": "TEXT",
        "kind": "TEXT",                         # Spieler / Coach / Staff
        "team": "TEXT",
        "number": "TEXT",
        "position": "TEXT",
        "role": "TEXT",                         # Rolle (Coach/Staff) bzw. Zusatzrolle (Spieler)
        "instagram": "TEXT",
        "email": "TEXT",
        "phone": "TEXT",
        "consent": "INTEGER DEFAULT 0",         # Einwilligung Foto und Veröffentlichung
        "since": "TEXT",
        "facts": "TEXT",
        "message": "TEXT",
        "status": "TEXT DEFAULT 'Neu'",         # Neu / Übernommen / Verworfen
        "player_id": "INTEGER",                 # übernommen in diese Person
        "created": "TEXT",
        "source": "TEXT",                       # Spielerbogen / Einladung
        "user_id": "INTEGER",                   # Konto aus der Einladung (beim Übernehmen mit der Person im Kader verknüpft)
    },
    "opponents": {
        "name": "TEXT",
        "short": "TEXT",
        "city": "TEXT",
        "logo": "TEXT",
        "instagram": "TEXT",
        "notes": "TEXT",
    },
    "games": {
        "season": "TEXT",
        "date": "TEXT",
        "time": "TEXT",
        "opponent_id": "INTEGER",
        "home": "INTEGER DEFAULT 1",
        "location": "TEXT",
        "kind": "TEXT DEFAULT 'Liga'",
        "league": "TEXT",
        "score_us": "TEXT",
        "score_them": "TEXT",
        "quarters": "TEXT",
        "sponsor_id": "INTEGER",
        "highlights": "TEXT",
        "notes": "TEXT",
        "team": "TEXT DEFAULT 'Erste Herren'",
        "stream_url": "TEXT",                   # Livestream-Link (öffentlich auf der Webseite)
    },
    "sponsors": {
        "name": "TEXT",
        "package": "TEXT",
        "logo": "TEXT",
        "instagram": "TEXT",
        "website": "TEXT",
        "contact": "TEXT",
        "start": "TEXT",
        "end": "TEXT",
        "amount": "TEXT",
        "posts_agreed": "INTEGER DEFAULT 0",
        "active": "INTEGER DEFAULT 1",
        "notes": "TEXT",
        "files": "TEXT",                        # JSON-Liste [{name, path, size, added}]: Verträge, Rechnungen, Bilder
        "package_id": "INTEGER",                # internes Sponsorenpaket (sponsor_packages), nie öffentlich
    },
    "sponsor_packages": {                       # Sponsorenpakete, von Hand angelegt, nur intern (Bereich Verein, Preis nur mit Finanz-Leserecht)
        "name": "TEXT",
        "price": "TEXT",
        "season": "TEXT",
        "services": "TEXT",                     # Leistungen, eine pro Zeile
        "active": "INTEGER DEFAULT 1",
        "sort": "INTEGER DEFAULT 0",
        "notes": "TEXT",
    },
    "media_team": {
        "name": "TEXT",
        "role": "TEXT",
        "phone": "TEXT",
        "instagram": "TEXT",
        "active": "INTEGER DEFAULT 1",
        "notes": "TEXT",
    },
    "assignments": {
        "game_id": "INTEGER",
        "member_id": "INTEGER",
        "task": "TEXT",
        "confirmed": "INTEGER DEFAULT 0",
        "notes": "TEXT",
    },
    "supporter_cards": {
        "season": "TEXT",
        "holder": "TEXT",
        "number": "TEXT",
        "sold_on": "TEXT",
        "price": "REAL",
        "paid": "INTEGER DEFAULT 0",
        "notes": "TEXT",
        "email": "TEXT",                        # bei Online-Bestellung über /supporter-karte
        "phone": "TEXT",
        "source": "TEXT",                       # "Online" oder leer (im Hub eingetragen)
        "order_id": "INTEGER",                  # Online-Bestellung (card_orders), zu der die Karte gehört
    },
    "card_orders": {                            # Online-Bestellungen der Dauerkarte (eine Bestellung, mehrere Karten)
        "order_no": "TEXT",                     # z. B. SK-2027-0001 (Verwendungszweck)
        "season": "TEXT",
        "buyer": "TEXT",
        "email": "TEXT",
        "phone": "TEXT",
        "holders": "TEXT",                      # JSON-Liste der Namen auf den Karten
        "count": "INTEGER",
        "delivery": "TEXT",                     # Post / Einschreiben / Einlass
        "street": "TEXT",
        "zip": "TEXT",
        "city": "TEXT",
        "price_each": "REAL",
        "shipping": "REAL",
        "total": "REAL",
        "message": "TEXT",
        "paid": "INTEGER DEFAULT 0",
        "paid_on": "TEXT",
        "invoice_no": "TEXT",                   # wird beim Markieren als bezahlt vergeben
        "invoice_sent": "TEXT",
        "delivered": "INTEGER DEFAULT 0",
        "created": "TEXT",
        "notes": "TEXT",
        "tracking_no": "TEXT",                  # Sendungsnummer beim Einschreiben
        "shipped_on": "TEXT",                   # verschickt am (Versandbestätigung an den Kunden)
        "shipped_mail": "TEXT",                 # Versandbestätigung verschickt (Zeitpunkt)
        "cancel_hash": "TEXT",                  # SHA-256 des Storno-Links aus der Bestätigungsmail (Link selbst wird nicht gespeichert)
        "cancelled": "TEXT",                    # storniert am (Zeitpunkt), nur bis Zahlungseingang möglich
        "cancelled_by": "TEXT",                 # "Kunde" (Link) oder Name im Hub
    },
    "posts": {
        "date": "TEXT",
        "time": "TEXT",
        "type": "TEXT",
        "title": "TEXT",
        "caption": "TEXT",
        "image": "TEXT",
        "status": "TEXT DEFAULT 'Idee'",       # Idee / In Arbeit / Geplant / Gepostet
        "platform": "TEXT DEFAULT 'Instagram'",
        "format": "TEXT DEFAULT 'Feed'",        # Feed / Story / Reel / Karussell
        "game_id": "INTEGER",
        "sponsor_id": "INTEGER",
        "player_id": "INTEGER",
        "posted_url": "TEXT",
        "notes": "TEXT",
        "media": "TEXT",                           # Karussell (mehrere Bilder) oder Reel (ein Video): JSON-Liste wie files
        "auto_publish": "INTEGER DEFAULT 0",       # Freigabe: zum geplanten Zeitpunkt automatisch posten
        "targets": "TEXT DEFAULT 'Facebook'",      # Facebook / Instagram / Facebook + Instagram
        "publish_state": "TEXT",                   # nur Server: läuft / gepostet / teilweise / fehler / verpasst
        "publish_log": "TEXT",                     # nur Server
        "published_at": "TEXT",                    # nur Server
    },
    "story_rules": {                            # Wiederkehrende Storys, z. B. Trainingszeiten
        "name": "TEXT",
        "weekdays": "TEXT",                        # ISO-Wochentage, z. B. 2,4 (1 = Montag)
        "time": "TEXT",                            # HH:MM
        "image": "TEXT",
        "targets": "TEXT DEFAULT 'Facebook'",
        "active": "INTEGER DEFAULT 1",
        "valid_from": "TEXT",
        "valid_until": "TEXT",
        "last_run": "TEXT",                        # nur Server: Datum der letzten Ausführung
        "last_result": "TEXT",                     # nur Server
        "notes": "TEXT",
    },
    "members": {                                # Mitgliederverwaltung
        "first_name": "TEXT",
        "last_name": "TEXT",
        "member_type": "TEXT DEFAULT 'Spieler'",   # Spieler / Trainer / Vorstand / Helfer / Fotograf / Förderer
        "status": "TEXT DEFAULT 'Aktiv'",          # Aktiv / Passiv / Probetraining / Ausgetreten
        "birthdate": "TEXT",
        "email": "TEXT",
        "phone": "TEXT",
        "street": "TEXT",
        "zip": "TEXT",
        "city": "TEXT",
        "member_since": "TEXT",
        "exit_date": "TEXT",
        "emergency_contact": "TEXT",
        "equipment": "TEXT",
        "consent_photo": "INTEGER DEFAULT 0",
        "player_id": "INTEGER",
        "user_id": "INTEGER",
        "notes": "TEXT",
    },
    "transactions": {                           # Finanzen: Einnahmen und Ausgaben
        "date": "TEXT",
        "kind": "TEXT DEFAULT 'Ausgabe'",          # Einnahme / Ausgabe
        "category": "TEXT",
        "description": "TEXT",
        "amount": "REAL",
        "sponsor_id": "INTEGER",
        "member_id": "INTEGER",
        "receipt": "TEXT",
        "paid_by": "TEXT",
        "status": "TEXT DEFAULT 'Erledigt'",       # Offen / Erledigt
        "notes": "TEXT",
    },
    "media": {
        "path": "TEXT",
        "name": "TEXT",
        "tags": "TEXT",
        "created": "TEXT",
    },
    "magazines": {                              # Stadionheft: ein Eintrag pro Ausgabe
        "season": "TEXT",
        "number": "TEXT",                          # z. B. 1 von 4
        "title": "TEXT DEFAULT 'Amisia Echo'",
        "game_id": "INTEGER",
        "status": "TEXT DEFAULT 'Planung'",        # Planung / In Arbeit / Im Druck / Fertig
        "deadline": "TEXT",                        # Redaktionsschluss
        "print_date": "TEXT",                      # Druckabgabe
        "pages_target": "INTEGER",
        "canva_url": "TEXT",
        "files": "TEXT",                           # JSON-Liste wie bei sponsors.files
        "notes": "TEXT",
        "sponsor_ids": "TEXT",                     # JSON-Liste der Sponsoren in diesem Heft
    },
    "magazine_pages": {                         # Beiträge eines Stadionhefts (Vorwort, Behind the Helmet, ...)
        "magazine_id": "INTEGER",
        "page": "INTEGER",
        "section": "TEXT",                         # Cover / Vorwort / Anzeige / Kader / Spielbericht ...
        "title": "TEXT",
        "owner": "TEXT",
        "status": "TEXT DEFAULT 'Offen'",          # Offen / Text da / Bilder da / Fertig in Canva
        "sponsor_id": "INTEGER",
        "player_id": "INTEGER",
        "game_id": "INTEGER",
        "opponent_id": "INTEGER",
        "text": "TEXT",
        "files": "TEXT",
        "notes": "TEXT",
        "author": "TEXT",                          # Vorwort: wer schreibt
        "role": "TEXT",                            # Vorwort: Funktion
        "image": "TEXT",
        "answers": "TEXT",                         # Behind the Helmet: JSON {Frage: Antwort}
    },
    "articles": {                               # News auf der Webseite (/news), im Hub unter Medien > News
        "title": "TEXT",
        "teaser": "TEXT",                          # kurzer Vorspann für Liste und Startseite
        "body": "TEXT",                            # Text, Absätze durch Leerzeilen (oder HTML, siehe format)
        "format": "TEXT DEFAULT 'Text'",           # Blöcke (JSON aus dem Editor) / Text / HTML (HTML wird beim Anzeigen gefiltert: website.clean_html)
        "image": "TEXT",                           # Foto aus der Mediathek (/media/...)
        "image_alt": "TEXT",
        "photo_by": "TEXT",                        # Fotograf, steht unter dem Artikel ("Foto: ...")
        "photo_url": "TEXT",                       # Link zum Fotografen (https oder @instagram)
        "date": "TEXT",                            # Veröffentlichungsdatum, vorher nicht sichtbar
        "status": "TEXT DEFAULT 'Entwurf'",        # Entwurf / Veröffentlicht
        "team": "TEXT",                            # optional: eine Mannschaft aus TEAMS
        "game_id": "INTEGER",                      # optional: Spiel, z. B. für Spielberichte
        "notes": "TEXT",                           # intern, nie öffentlich
    },
    "contact_requests": {                       # Anfragen über das Kontaktformular der Webseite
        "name": "TEXT",
        "email": "TEXT",
        "phone": "TEXT",
        "message": "TEXT",
        "source": "TEXT",                          # z. B. Probetraining
        "status": "TEXT DEFAULT 'Neu'",            # Neu / In Bearbeitung / Erledigt
        "created": "TEXT",
        "notes": "TEXT",
    },
    "shop_products": {                          # Fanshop-Produkte für das Laufband auf der Startseite (Bereich Medien)
        "name": "TEXT",
        "price": "TEXT",                        # Anzeige, z. B. 39,90 €
        "image": "TEXT",                        # Bild aus der Mediathek (öffentlich nur signiert über public_image)
        "url": "TEXT",                          # Link zum Produkt im Fanshop (nur https)
        "is_new": "INTEGER DEFAULT 0",          # Hinweis „Neu“ im Laufband
        "colors": "INTEGER DEFAULT 0",          # Hinweis „In verschiedenen Farben erhältlich“
        "active": "INTEGER DEFAULT 1",
        "sort": "INTEGER DEFAULT 0",
    },
    "nl_groups": {                              # Newsletter-Gruppen (Hub > Newsletter > Gruppen), public = auf der Webseite zur Auswahl
        "name": "TEXT",
        "description": "TEXT",
        "public": "INTEGER DEFAULT 1",
        "active": "INTEGER DEFAULT 1",
        "sort": "INTEGER DEFAULT 0",
    },
    "mail_lists": {                             # Verteiler für Mails (Postfach > Verteiler): Name und Adressen, eine pro Zeile
        "name": "TEXT",
        "addresses": "TEXT",
        "notes": "TEXT",
    },
    "gd_shifts": {                              # Heimspieltag: Schichten pro Spiel (Kasse, Grill, Aufbau ...), Bereich spieltag
        "game_id": "INTEGER",
        "role": "TEXT",
        "start": "TEXT",
        "end": "TEXT",
        "slots": "INTEGER DEFAULT 1",
        "notes": "TEXT",
        "sort": "INTEGER DEFAULT 0",
    },
    "gd_signups": {                             # Heimspieltag: Eintragungen in eine Schicht (über den Link ohne Konto oder im Hub)
        "shift_id": "INTEGER",
        "game_id": "INTEGER",
        "name": "TEXT",
        "phone": "TEXT",
        "user_id": "INTEGER",
        "source": "TEXT",                       # Link / Hub / von Hand
        "created": "TEXT",
        "notes": "TEXT",
    },
    "gd_checks": {                              # Heimspieltag: Checkliste pro Spiel (Schiedsrichter bestätigt, Platz gebucht ...)
        "game_id": "INTEGER",
        "text": "TEXT",
        "done": "INTEGER DEFAULT 0",
        "done_by": "TEXT",
        "done_at": "TEXT",
        "sort": "INTEGER DEFAULT 0",
    },
    "trainings": {                              # Trainingszeiten je Mannschaft (Hub > Trainingszeiten), öffentlich auf den Mannschaftsseiten
        "team": "TEXT",                            # Mannschaft (TEAMS) oder Gruppe (Fit for Fun ...)
        "weekday": "TEXT",                         # Montag ... Sonntag
        "start": "TEXT",                           # HH:MM
        "end": "TEXT",                             # HH:MM
        "place": "TEXT",                           # z. B. Sportplatz Wolthusen
        "season": "TEXT",                          # z. B. Sommer / Winter, leer = ganzjährig
        "active": "INTEGER DEFAULT 1",
        "notes": "TEXT",                           # intern, nie öffentlich
    },
    "bookings": {                               # Belegung von Saal, Sportplatz und Halle (Hub > Belegung), nur intern
        "resource": "TEXT DEFAULT 'Saal'",         # Saal / Sportplatz / Kunstrasen / Turnhalle / Sportheim
        "date": "TEXT",
        "start": "TEXT",
        "end": "TEXT",
        "title": "TEXT",                           # Anlass, z. B. Geburtstag, Training E-Jugend, Heimspiel
        "status": "TEXT DEFAULT 'Anfrage'",        # Anfrage / Bestätigt / Abgesagt
        "renter": "TEXT",                          # Mieter oder Mannschaft
        "contact": "TEXT",                         # Telefon oder E-Mail des Mieters
        "persons": "INTEGER",
        "price": "REAL",
        "deposit": "REAL",                         # Kaution
        "paid": "INTEGER DEFAULT 0",
        "notes": "TEXT",
    },
    "apparel": {                                # Teamkleidung: ein Eintrag pro Artikel, z. B. Hoodie 2027
        "name": "TEXT",
        "description": "TEXT",
        "image": "TEXT",
        "price": "REAL",
        "deadline": "TEXT",                        # Bestellschluss (an dem Tag noch offen)
        "active": "INTEGER DEFAULT 1",
        "show_list": "INTEGER DEFAULT 1",          # Bestellungen auf der öffentlichen Seite zeigen
        "fields": "TEXT",                          # JSON-Liste [{key, label, type, options, required, internal}]
        "public_token": "TEXT",                    # geheimer Teil des Bestell-Links, nur vom Server vergeben
        "notes": "TEXT",
    },
    "apparel_orders": {
        "apparel_id": "INTEGER",
        "data": "TEXT",                            # JSON {Feld-Key: Wert}
        "quantity": "INTEGER DEFAULT 1",
        "paid": "INTEGER DEFAULT 0",
        "source": "TEXT",                          # Link / Hub
        "created": "TEXT",
        "notes": "TEXT",
        "booked_tx": "INTEGER",                    # nur Server: Buchung in den Finanzen (Sammelbuchung)
    },
}

# Rechtstexte der Webseite (im Hub unter Webseite > Texte > Rechtliches änderbar).
# Format: "## " Überschrift, Leerzeile = Absatz, "- " Liste, [eckige Klammern] = noch auszufüllen (auf der Webseite gelb markiert).
# {E-Mail} und {Instagram} werden durch die Einstellungen ersetzt. Inhalt entspricht dem, was Webseite und Hub tatsächlich verarbeiten.
LEGAL_IMPRESSUM = """## Angaben gemäß § 5 Digitale-Dienste-Gesetz (DDG)

SV Amisia Wolthusen e.V.
Folkmar-Allena-Straße 13
26725 Emden

## Vertreten durch

Den vertretungsberechtigten Vorstand gemäß § 26 BGB: [Vorname Name (1. Vorsitzende/r), Vorname Name (2. Vorsitzende/r)]

## Kontakt

E-Mail: {E-Mail}
Telefon: [Telefonnummer des Vereins]
Kontaktformular: /kontakt

## Registereintrag

Eingetragen im Vereinsregister.
Registergericht: [Amtsgericht Aurich]
Registernummer: [VR ...]

## Umsatzsteuer

[Umsatzsteuer-Identifikationsnummer nach § 27a UStG, falls der Verein eine hat. Sonst diesen Abschnitt löschen.]

## Verantwortlich für den Inhalt nach § 18 Abs. 2 MStV

[Vorname Name]
Folkmar-Allena-Straße 13, 26725 Emden

## Gilt auch für unsere Social-Media-Auftritte

Dieses Impressum gilt auch für unser Profil bei Instagram ({Instagram}) und unsere Seite bei Facebook.

## Verbraucherstreitbeilegung

Wir sind nicht bereit und nicht verpflichtet, an Streitbeilegungsverfahren vor einer Verbraucherschlichtungsstelle teilzunehmen.

## Haftung für Inhalte und Links

Die Inhalte dieser Webseite erstellen wir mit Sorgfalt. Für die Richtigkeit, Vollständigkeit und Aktualität können wir jedoch keine Gewähr übernehmen. Unsere Webseite enthält Links zu Webseiten Dritter, zum Beispiel zu fussball.de, unseren Partnern oder Instagram. Auf deren Inhalte haben wir keinen Einfluss, dafür ist der jeweilige Anbieter verantwortlich. Bei Bekanntwerden von Rechtsverletzungen entfernen wir solche Links umgehend.

## Bildnachweis

Fotos der Emden Tigers (American Football): silasgrbwsk.fotografie (https://silasgrbwskfotografie.de). [Weitere Fotografen]. Logos von Partnern und Gegnern gehören den jeweiligen Inhabern."""

LEGAL_DATENSCHUTZ = """## Verantwortlicher

SV Amisia Wolthusen e.V.
Folkmar-Allena-Straße 13, 26725 Emden
Vertreten durch den Vorstand: [Vorname Name]
E-Mail: {E-Mail}

[Einen Datenschutzbeauftragten haben wir nicht benannt, weil wir nicht dazu verpflichtet sind. Bitte prüfen: Pflicht ab in der Regel 20 Personen, die ständig mit personenbezogenen Daten arbeiten.]

## Das Wichtigste in Kürze

- Wir setzen keine Analyse- oder Werbedienste ein, keine Tracker und keine Cookies auf der öffentlichen Webseite.
- Schriften, Bilder und Programmteile liefern wir vom eigenen Server aus. Beim Besuch werden keine Daten an Google, Meta oder andere Dienste übertragen.
- Daten, die du uns über ein Formular schickst, nutzen wir nur für dein Anliegen.

## Hosting und Aufruf der Webseite

Die Webseite läuft auf einem Server bei [Hosting-Anbieter, Anschrift], Standort Deutschland. Mit dem Anbieter besteht ein Vertrag zur Auftragsverarbeitung nach Art. 28 DSGVO.

Beim Aufruf überträgt dein Browser technisch notwendige Daten wie IP-Adresse, Datum und Uhrzeit, aufgerufene Adresse und Browsertyp. Wir speichern dafür keine Zugriffsprotokolle. Zum Schutz vor Missbrauch der Formulare (zu viele Anfragen in kurzer Zeit) halten wir die IP-Adresse höchstens eine Stunde lang im Arbeitsspeicher des Servers, danach wird sie verworfen. Die Verbindung ist per HTTPS verschlüsselt.

Rechtsgrundlage ist unser berechtigtes Interesse an einer sicheren und funktionsfähigen Webseite (Art. 6 Abs. 1 lit. f DSGVO).

## Cookies

Die öffentliche Webseite setzt keine Cookies. Einzige Ausnahme ist der passwortgeschützte Spielerbogen für unsere Mannschaften: Nach Eingabe des Passworts setzen wir ein technisch notwendiges Cookie („tmh_pf“), das nur für diese Seite gilt und nach zwei Stunden abläuft (§ 25 Abs. 2 TDDDG).

## Kontaktformular und E-Mail

Wenn du uns über das Kontaktformular schreibst, verarbeiten wir dein Anliegen, deinen Namen, deine Nachricht sowie E-Mail-Adresse und/oder Telefonnummer, damit wir dir antworten können. Die Anfrage speichern wir in unserer internen Vereinsverwaltung und leiten sie per E-Mail an die zuständigen Personen im Verein weiter. Wenn du eine E-Mail-Adresse angibst, schicken wir dir an diese Adresse eine automatische Eingangsbestätigung (ohne den Inhalt deiner Nachricht). Wenn du uns direkt eine E-Mail schreibst, gilt das entsprechend.

Rechtsgrundlage ist deine Einwilligung, die du im Formular erteilst (Art. 6 Abs. 1 lit. a DSGVO), bei Anfragen zu einer Mitgliedschaft, einem Probetraining oder einer Saalmiete außerdem die Anbahnung eines Vertragsverhältnisses (Art. 6 Abs. 1 lit. b DSGVO). Du kannst die Einwilligung jederzeit per E-Mail widerrufen. Wir löschen die Anfrage, wenn sie erledigt ist, [spätestens nach ... Monaten], soweit keine gesetzlichen Aufbewahrungspflichten bestehen.

## Mitgliedschaft

Für die Mitgliederverwaltung verarbeiten wir die Angaben aus der Beitrittserklärung, zum Beispiel Name, Anschrift, Geburtsdatum, Kontaktdaten, Mannschaft und Bankverbindung für den Beitragseinzug. Rechtsgrundlage ist die Mitgliedschaft nach unserer Satzung (Art. 6 Abs. 1 lit. b DSGVO). Spielberechtigungen beantragen wir beim Niedersächsischen Fußballverband (NFV) und geben dafür die nötigen Angaben weiter. Nach dem Austritt löschen wir die Daten, soweit keine gesetzlichen Aufbewahrungspflichten bestehen (Beitragsbuchungen bis zu zehn Jahre, § 147 AO).

## Saalvermietung

Für die Miete unseres Saals verarbeiten wir Name, Kontaktdaten, Termin und Anlass, um die Buchung abzuwickeln (Art. 6 Abs. 1 lit. b DSGVO). Angaben, die für unsere Buchführung erforderlich sind, bewahren wir nach den gesetzlichen Fristen auf.

## Bestellungen von Teamkleidung

Bestellungen von Teamkleidung nehmen wir über einen Link an, den wir nur an Mitglieder und Eltern weitergeben. Dabei verarbeiten wir die abgefragten Angaben, zum Beispiel Name, Größe und Anzahl. Wer den Link kennt, sieht eine Liste der bisherigen Bestellungen mit Name und Auswahl, damit Sammelbestellungen abgestimmt werden können. Ob bezahlt wurde und interne Notizen sind dort nicht sichtbar.

Rechtsgrundlage ist die Abwicklung der Bestellung (Art. 6 Abs. 1 lit. b DSGVO) und unser berechtigtes Interesse an einer einfachen Sammelbestellung im Verein (Art. 6 Abs. 1 lit. f DSGVO).

## Versand von E-Mails

Unsere E-Mail-Adressen und den Versand von Bestätigungen betreibt [E-Mail-Anbieter, Anschrift], Serverstandort Deutschland. Dabei verarbeitet der Anbieter Absender, Empfänger und Inhalt der E-Mails. Mit dem Anbieter besteht ein Vertrag zur Auftragsverarbeitung nach Art. 28 DSGVO.

## Spielerbogen für Spieler, Trainer und Betreuer

Spieler, Trainer und Betreuer unserer Herrenmannschaften können ihre Angaben über einen passwortgeschützten Bogen selbst eintragen: Name, Spitzname, Art (Spieler, Trainer, Betreuer), Mannschaft, Rückennummer, Position bzw. Rolle, Instagram-Name, E-Mail-Adresse, Telefonnummer und freiwillig „dabei seit“ und eine Nachricht. Die Angaben prüfen wir und übernehmen sie in unsere interne Vereinsverwaltung. E-Mail-Adresse und Telefonnummer nutzen wir nur intern zur Organisation der Mannschaft, sie erscheinen nie auf der Webseite. Angaben zu Spielerinnen und Spielern unserer Jugend nehmen wir nicht über diesen Bogen an.

Rechtsgrundlage ist die Organisation des Spiel- und Trainingsbetriebs im Rahmen der Mitgliedschaft (Art. 6 Abs. 1 lit. b DSGVO). Ob Foto, Name, Rückennummer und Position auf der Webseite und in unseren Social-Media-Kanälen erscheinen, entscheidet jede Person selbst mit der Einwilligung im Bogen (Art. 6 Abs. 1 lit. a DSGVO); sie ist freiwillig und kann jederzeit widerrufen werden.

## Helfer am Heimspieltag

Für unsere Heimspiele und Vereinsfeste können sich Helferinnen und Helfer über einen Link, den wir im Verein weitergeben, für Aufgaben wie Kasse, Kiosk oder Aufbau eintragen. Dabei verarbeiten wir den Namen, freiwillig die Telefonnummer für Rückfragen und die gewählten Aufgaben. Wer den Link kennt, sieht bei jeder Aufgabe nur die Vornamen der bereits Eingetragenen.

Rechtsgrundlage ist deine Einwilligung (Art. 6 Abs. 1 lit. a DSGVO), die du beim Eintragen erteilst und jederzeit widerrufen kannst, sowie unser berechtigtes Interesse an der Organisation des Spieltags (Art. 6 Abs. 1 lit. f DSGVO). Wir löschen die Einträge, sobald sie für die Organisation nicht mehr gebraucht werden, spätestens zum Ende der Saison.

## Newsletter

Auf unserer Webseite kannst du unseren Newsletter abonnieren und dabei Themen auswählen. Dafür verarbeiten wir deine E-Mail-Adresse, freiwillig deinen Namen, die gewählten Themen sowie Zeitpunkt und Wortlaut deiner Einwilligung. Die Anmeldung wird erst wirksam, wenn du den Link in unserer Bestätigungsmail anklickst (Double-Opt-In). Ohne Bestätigung löschen wir die Angaben nach spätestens 30 Tagen.

Rechtsgrundlage ist deine Einwilligung (Art. 6 Abs. 1 lit. a DSGVO). Du kannst sie jederzeit über den Link in jeder Ausgabe oder per E-Mail an uns widerrufen. Wir verschicken den Newsletter selbst über unser E-Mail-Postfach und messen nicht, ob oder wann du ihn öffnest oder auf Links klickst. Nach der Abmeldung speichern wir die Adresse mit Zeitpunkt der Anmeldung und Abmeldung bis zu drei Jahre, um nachweisen zu können, dass wir nur mit Einwilligung geschrieben haben (Art. 6 Abs. 1 lit. f DSGVO); auf Wunsch löschen wir sie früher.

## Mannschaften, Trainer und Fotos auf der Webseite

Auf den Seiten unserer Herrenmannschaften zeigen wir Name, Position und Rückennummer unserer Spieler sowie Trainer und Betreuer. Fotos von Spielern zeigen wir nur mit deren Einwilligung (Art. 6 Abs. 1 lit. a DSGVO), die jederzeit widerrufen werden kann. Spielerinnen und Spieler unserer Jugendmannschaften zeigen wir nicht namentlich, dort nennen wir nur Trainer und Betreuer. Spielberichte und Fotos von Spielen veröffentlichen wir im Rahmen unserer Vereinsarbeit (Art. 6 Abs. 1 lit. f DSGVO), Fotos von Kindern nur mit Einwilligung der Erziehungsberechtigten. Wer nicht gezeigt werden möchte, kann sich jederzeit an uns wenden.

## Instagram und Facebook

Auf der Startseite können wir Bilder unserer neuesten Instagram-Beiträge zeigen. Diese ruft unser Server selbst über die Schnittstelle von Meta ab und speichert sie bei uns. Beim Besuch unserer Webseite werden dadurch keine Daten an Instagram oder Meta übertragen. Erst wenn du auf einen Beitrag oder einen Link zu Instagram oder Facebook klickst, öffnet sich der Dienst und es gelten die Datenschutzbestimmungen von Meta: https://privacycenter.instagram.com/policy

Für unser Profil bei Instagram ({Instagram}) und unsere Facebook-Seite sind wir gemeinsam mit der Meta Platforms Ireland Limited, Merrion Road, Dublin 4, Irland, verantwortlich (Art. 26 DSGVO). Meta erstellt Statistiken über die Nutzung (Insights). Die Vereinbarung dazu findest du unter https://www.facebook.com/legal/terms/page_controller_addendum. Deine Rechte kannst du gegenüber uns und gegenüber Meta geltend machen. Rechtsgrundlage ist unser berechtigtes Interesse an der Öffentlichkeitsarbeit des Vereins (Art. 6 Abs. 1 lit. f DSGVO).

## Links zu anderen Angeboten

Unsere Webseite enthält Links, zum Beispiel zu fussball.de, zu superkicker.de, zu Kartendiensten und zu den Webseiten unserer Partner. Erst beim Anklicken wirst du zum jeweiligen Anbieter weitergeleitet, dort gelten dessen Datenschutzbestimmungen.

## Schriften

Die Schriften dieser Webseite (Anton und Karla) liegen auf unserem eigenen Server. Es wird keine Verbindung zu Google Fonts oder anderen Schriftdiensten aufgebaut.

## Empfänger und Pflichtangaben

Deine Daten erhalten nur die Personen im Verein, die für dein Anliegen zuständig sind, sowie unsere Dienstleister für Hosting und E-Mail-Versand im Rahmen ihres Auftrags. Wir verkaufen keine Daten und geben sie nicht zu Werbezwecken weiter.

In den Formularen sind nur die Angaben Pflicht, die wir zur Bearbeitung brauchen (sie sind dort gekennzeichnet). Ohne sie können wir dir nicht antworten oder die Anfrage nicht bearbeiten. Eine automatisierte Entscheidungsfindung oder ein Profiling (Art. 22 DSGVO) findet nicht statt.

## Deine Rechte

Du hast das Recht auf Auskunft (Art. 15 DSGVO), Berichtigung (Art. 16), Löschung (Art. 17), Einschränkung der Verarbeitung (Art. 18), Datenübertragbarkeit (Art. 20) und Widerspruch gegen Verarbeitungen auf Grundlage berechtigter Interessen (Art. 21). Eine Einwilligung kannst du jederzeit mit Wirkung für die Zukunft widerrufen. Schreib uns dazu einfach an {E-Mail}.

Du kannst dich außerdem bei einer Datenschutz-Aufsichtsbehörde beschweren. Für uns zuständig ist: Die Landesbeauftragte für den Datenschutz Niedersachsen, Prinzenstraße 5, 30159 Hannover, https://www.lfd.niedersachsen.de

## Stand

[Monat Jahr]"""

DEFAULT_SETTINGS = {
    "club_name": "SV Amisia Wolthusen",
    "club_short": "AMISIA",
    "instagram": "amisiasternwolthusen",
    "color_primary": "#3D2F96",
    "color_dark": "#15122B",
    "color_light": "#FFFFFF",
    "logo": "",
    "crest": "",
    "home_location": "Sportplatz Wolthusen",
    "home_city": "Emden",
    "entry_fee": "",
    "season": "2026/27",
    # Dauerkarte (im Hub technisch „Dauerkarte“): Eintritt zu allen Heimspielen der Ersten Herren in der Saison
    "card_price": "30",
    "card_share_wolthusen": "0",                # Abgabe je Karte an Dritte (Standard: keine)
    "card_shipping": "1.50",                    # Versand per Post, einmal pro Bestellung
    "card_shipping_registered": "4.00",         # Versand per Einschreiben, einmal pro Bestellung
    # Begleitbrief zum Ausdrucken (liegt den Karten bei); {Name} = Vorname des Bestellers, {Saison}
    "card_letter_text": "Hallo {Name},\n\nvielen Dank, dass du den SV Amisia Wolthusen mit der Dauerkarte {Saison} unterstützt! "
                        "Mit deiner Karte bist du bei allen Heimspielen unserer Ersten Herren dabei. Zeig sie einfach an der Kasse vor.\n\n"
                        "Deine Unterstützung hilft uns, den Fußball in Wolthusen weiter nach vorne zu bringen.\n\n"
                        "Wir freuen uns darauf, dich am Platz zu sehen!",
    # Bankverbindung und Rechnung für Online-Bestellungen (Hub: Finanzen, nicht öffentlich)
    "inv_sender": "SV Amisia Wolthusen e.V.\nFolkmar-Allena-Straße 13\n26725 Emden",
    "inv_account_holder": "",
    "inv_iban": "",
    "inv_bic": "",
    "inv_bank": "",
    "inv_tax_no": "",
    "inv_tax_note": "[Hinweis zur Umsatzsteuer, zum Beispiel Steuerbefreiung oder Steuersatz. Bitte mit dem Kassenwart oder Steuerberater klären.]",
    "inv_due_days": "14",
    "default_hashtags": "#amisiawolthusen #wolthusen #emden #ostfriesland #fussball",
    "training_text": "",
    "font_headline": "Anton, Impact, 'Arial Narrow', sans-serif",
    "font_text": "Karla, 'Segoe UI', Arial, sans-serif",
    "media_tasks": "Fotos\nStorys am Spielfeldrand\nVideo / Clips\nSpielbericht",
    # Öffentliche Webseite (Hub > Webseite). Leere Texte erscheinen dort als markierter Platzhalter.
    "site_hero_title": "",
    "site_hero_text": "Fußball, American Football, Turnen und Gymnastik mitten in Emden-Wolthusen. Für Kinder, Jugendliche und Erwachsene.",
    "site_about": "Der SV Amisia Wolthusen e.V. ist der Sportverein im Emder Stadtteil Wolthusen. Gegründet 1929, ist der Verein bis heute ein Treffpunkt für Sport und Gemeinschaft im Viertel.\n\n"
                  "Hier findest du alles rund um unseren Verein: Mannschaften, Trainingszeiten, Ansprechpartner, unseren Saal und wie du Mitglied wirst.",
    "site_training_times": "",
    "site_training_place": "Sportplatz Wolthusen",
    "site_training_address": "Folkmar-Allena-Straße 13, 26725 Emden",
    "site_trial_text": "Du willst bei uns mitspielen? Komm einfach zu einem Training vorbei. Am besten schreibst du uns vorher kurz über das Formular, "
                       "dann wissen die Trainer Bescheid und nehmen dich am Platz in Empfang. Für den Anfang reichen Sportkleidung, Fußballschuhe und etwas zu trinken.",
    "site_home_address": "Folkmar-Allena-Straße 13, 26725 Emden-Wolthusen",
    "site_home_maps_url": "",   # Link für Adresse und Anfahrt zum Sportplatz
    "site_gameday_text": "An Heimspieltagen freuen wir uns über jede Unterstützung am Spielfeldrand. Bring Familie und Freunde mit und feuer unsere Mannschaften an.",
    "site_card_short": "Mit der Dauerkarte bist du bei allen Heimspielen der Ersten Herren dabei.",
    "site_card_text": "Mit der Dauerkarte hast du freien Eintritt zu allen Heimspielen unserer Ersten Herren in der Saison und unterstützt den Verein.",
    # Pflichthinweise vor der Online-Bestellung der Dauerkarte (über dem Bestellknopf und in der Bestätigungsmail)
    "site_card_terms": "Leistung: Die Dauerkarte berechtigt zum freien Eintritt zu allen Heimspielen der Ersten Herren des SV Amisia Wolthusen in der genannten Saison. "
                       "Auswärtsspiele, Pokalspiele und Spiele anderer Mannschaften sind nicht enthalten.\n"
                       "Kein Widerrufsrecht: "
                       "Für Verträge über Freizeitveranstaltungen, die für einen bestimmten Termin oder Zeitraum vereinbart sind, besteht nach "
                       "§ 312g Abs. 2 Nr. 9 BGB kein Widerrufsrecht.\n"
                       "Spielausfall: Fällt ein Spiel aus Gründen aus, die wir nicht zu vertreten haben (zum Beispiel Wetter, Absage durch den Gegner "
                       "oder den Verband, behördliche Anordnung oder höhere Gewalt), besteht kein Anspruch auf Erstattung oder Entschädigung. "
                       "Gesetzliche Ansprüche bei Ausfällen, die wir zu vertreten haben, bleiben unberührt.",
    # Freiwillige Stornierung bis Zahlungseingang (kein gesetzliches Widerrufsrecht, sondern ein Angebot des Vereins)
    "site_card_cancel_text": "Freiwillige Stornierung: Auch wenn kein gesetzliches Widerrufsrecht besteht, kannst du deine Bestellung bis zum Eingang "
                             "deiner Zahlung bei uns kostenlos stornieren. Nutze dafür den Link in deiner Bestellbestätigung oder schreib uns eine E-Mail. "
                             "Nach Zahlungseingang ist eine Stornierung nicht mehr möglich.",
    # Kasten unter jedem News-Artikel (Knopf führt zum Kontaktformular)
    "site_news_cta_text": "Lust, selbst bei uns mitzuspielen? Komm zum Probetraining, egal ob Kind, Jugendlicher oder Erwachsener.",
    "site_news_cta_button": "Probetraining anfragen",
    "site_impressum": LEGAL_IMPRESSUM,
    "site_datenschutz": LEGAL_DATENSCHUTZ,
    "site_sponsor_text": "Ohne unsere Partner wäre der Sport in Wolthusen nicht möglich. Sie unterstützen Trainingsbetrieb, Ausrüstung, Jugendarbeit und Spieltage. "
                         "Sie möchten den Verein mit Ihrem Unternehmen unterstützen? Wir stellen gern ein Paket zusammen, von der Bandenwerbung bis zum Trikotsponsoring.",
    "site_contact_email": "",
    # Automatische Bestätigung an Anfragende über das Kontaktformular (leer = keine Bestätigung)
    "site_contact_confirm": "vielen Dank für deine Nachricht! Sie ist bei uns angekommen und wir melden uns so schnell wie möglich bei dir.\n\n"
                            "Wenn du noch etwas ergänzen möchtest, antworte einfach auf diese E-Mail.",
    "site_insta_hide": "",
    # Social-Media-Kanäle (Footer und Menü der Webseite, nur https-Adressen, leer = kein Link)
    "site_social_instagram": "https://www.instagram.com/amisiasternwolthusen",
    "site_social_facebook": "https://www.facebook.com/AmisiaStern",
    "site_social_tiktok": "",
    # Heimspieltag: Vorlagen (Hub > Spieltag > Vorlagen). Schichten: Rolle | Anzahl | Beginn-Ende, eine pro Zeile
    "gd_roles": "Aufbau | 2 | \nKasse | 2 | \nKiosk und Getränke | 3 | \nGrill | 2 | \nLinienrichter | 2 | \nAbbau | 2 | ",
    "gd_checklist": "Schiedsrichter bestätigt (DFBnet)\nPlatz abgekreidet, Netze und Eckfahnen\nKabinen für Gäste und Schiri vorbereitet\nSpielbericht im DFBnet vorbereitet\nKasse mit Wechselgeld\nKiosk, Getränke und Grill eingekauft\nSpielbälle aufgepumpt\nErste-Hilfe-Koffer und Kühlakkus",
    "site_shop_url": "",   # Fanshop (Menü und Footer der Webseite), leer = kein Fanshop
    # Online-Bestellung der Dauerkarte unter /supporter-karte (an/aus im Hub unter Finanzen)
    "site_card_order_open": "",
    # Wartungsmodus der Webseite (nur über /api/maintenance, Recht Wartung)
    "maint_on": "",
    "pf_notify_groups": '["Vorstand"]',   # Postfach: wer bei neuen Mails benachrichtigt wird (Gruppennamen, JSON)
    # Postfach: gemeinsame Signatur für alle, {Name} aus dem Konto, {Rolle} je Konto (Zeile entfällt ohne Rolle)
    "mail_signature": "Sportliche Grüße\n{Name}\n{Rolle}\n\nSV Amisia Wolthusen e.V.\nFolkmar-Allena-Straße 13, 26725 Emden\nhttps://www.amisia-stern.de",
    "maint_title": "Wir sind gleich wieder da",
    "maint_text": "Unsere Webseite wird gerade überarbeitet und ist in Kürze wieder für euch da.\n"
                  "Bis dahin findet ihr alle Neuigkeiten des SV Amisia Wolthusen auf Instagram und Facebook.",
    "maint_until": "",
    "site_card_order_text": "Nach deiner Bestellung bekommst du eine E-Mail mit allen Daten für die Überweisung. Sobald dein Geld da ist, schicken wir dir die Rechnung.",
    # Ablauf der Online-Bestellung (Pflichtangaben im elektronischen Geschäftsverkehr, § 312i BGB, Art. 246c EGBGB)
    "site_card_process": "1. Du wählst die Anzahl der Karten, trägst für jede Karte den Namen ein, wählst die Lieferart und gibst deine Kontaktdaten an. "
                         "Vor dem Absenden kannst du alle Angaben prüfen und korrigieren.\n"
                         "2. Mit Klick auf „Zahlungspflichtig bestellen“ gibst du eine verbindliche Bestellung ab. Der Vertrag kommt zustande, "
                         "sobald wir dir die Bestellung per E-Mail bestätigen.\n"
                         "3. In der Bestätigung findest du alle Angaben für die Überweisung. Wir speichern die Bestellung, die Bestätigung mit allen Angaben bekommst du per E-Mail.\n"
                         "4. Nach Zahlungseingang schicken wir dir die Rechnung per E-Mail.\n"
                         "5. Du bekommst die Karten per Post oder an der Kasse beim Heimspiel, so wie du es bei der Bestellung gewählt hast.\n"
                         "Vertragssprache ist Deutsch.",
    "site_card_delivery_text": "",
    # Suchmaschinen (Google, Bing ...): Beschreibung unter dem Link in den Suchergebnissen
    "site_seo_title": "Sportverein in Emden-Wolthusen",
    "site_seo_start": "SV Amisia Wolthusen e.V. in Emden: Fußball von der G-Jugend bis zu den Alten Herren, American Football mit den Emden Tigers, Turnen und Gymnastik, Vereinssaal.",
    "site_seo_herren": "Kader, Trainer und Training der Herrenmannschaften des SV Amisia Wolthusen.",
    "site_seo_jugend": "Kinder- und Jugendfußball beim SV Amisia Wolthusen: D-, E-, F- und G-Jugend in Emden-Wolthusen.",
    "site_seo_spielplan": "Spielplan und Ergebnisse aller Mannschaften des SV Amisia Wolthusen.",
    "site_seo_news": "Neuigkeiten, Spielberichte und Termine aus dem SV Amisia Wolthusen.",
    "site_seo_sponsoren": "Partner und Sponsoren des SV Amisia Wolthusen.",
    "site_seo_kontakt": "Kontakt zum SV Amisia Wolthusen: Probetraining, Mitgliedschaft, Saal mieten, Sponsoring und Fragen zum Verein.",
    "site_verify_google": "",
    "site_verify_bing": "",
    "site_herren_lead": "Fußball mit Ehrgeiz und Zusammenhalt: unsere Herrenmannschaften.",
    "site_herren_title": "Unsere Herren",
    "site_herren_intro": "",
    "site_youth_lead": "Fußball für Kinder und Jugendliche in Wolthusen.",
    "site_youth_title": "Unser Nachwuchs",
    "site_youth_intro": "",
    "site_youth_text": "",
    "site_youth_ages": "",
    "site_youth_training_times": "",
    "site_youth_training_place": "",
    # Hinweis-Leiste oben auf jeder Seite (z. B. „Heimspiel am Sonntag“), nur bis zum Datum sichtbar
    "site_notice_text": "",
    "site_notice_link": "",
    "site_notice_until": "",
    # Webseite im Hub (Bereich Medien): eigene Bilder und Aufbau der Startseite als JSON, nicht öffentlich
    "web_images": "{}",
    "web_layout": "",
}
SITE_TEXTS_VERSION = "1"   # erhöhen, wenn neue Standardtexte in leere Felder bestehender Server übernommen werden sollen
# SHA-256 früherer Fassungen von LEGAL_DATENSCHUTZ (aus der Git-Historie). Steht eine davon unverändert im Server,
# wird sie beim Start durch die aktuelle Vorlage ersetzt. Bei jeder Änderung der Vorlage den alten Hash hier ergänzen.
OLD_LEGAL_DATENSCHUTZ = {   # SHA-256 früherer, unveränderter Vorlagen; bei jeder Änderung von LEGAL_DATENSCHUTZ den alten Hash ergänzen
}


DB_LOCK = threading.RLock()   # exklusiv beim Einspielen eines Backups


# ---------------------------------------------------------------------------
# Bereiche und Rechte
# Stufen: 0 = kein Zugriff, 1 = Lesen, 2 = Bearbeiten. Admins dürfen alles.
# ---------------------------------------------------------------------------
AREAS = {"medien": "Medien", "verein": "Verein", "mitglieder": "Mitglieder", "finanzen": "Finanzen", "wartung": "Wartung", "postfach": "Postfach", "spieltag": "Spieltag"}
TABLE_AREA = {
    "gd_shifts": "spieltag", "gd_signups": "spieltag", "gd_checks": "spieltag",
    "posts": "medien", "media": "medien", "shop_products": "medien", "mail_lists": "postfach", "nl_groups": "medien",
    "media_team": "medien", "assignments": "medien", "magazines": "medien", "magazine_pages": "medien", "story_rules": "medien",
    "games": "verein", "opponents": "verein", "players": "verein", "sponsors": "verein", "sponsor_packages": "verein",
    "articles": "medien",
    "members": "mitglieder", "contact_requests": "mitglieder",
    "supporter_cards": "finanzen", "transactions": "finanzen", "card_orders": "finanzen",
    "apparel": "verein", "apparel_orders": "verein", "player_signups": "verein", "trainings": "verein", "bookings": "verein",
    "hub_plans": "admin",   # kein Bereich: nur Admins (siehe ADMIN_TABLES)
    "admin_notes": "admin",
}
ADMIN_TABLES = {"hub_plans", "admin_notes"}   # nur für Admins lesbar und änderbar, unabhängig von Gruppenrechten
# Tabellen, die mehrere Bereiche verwalten dürfen: es zählt das höchste Recht dieser Bereiche
TABLE_AREAS_ANY = {
    "apparel": ("verein", "finanzen", "medien"),
    "apparel_orders": ("verein", "finanzen", "medien"),
}
# Nachschlage-Tabellen: lesbar für alle, die irgendeinen Bereich sehen (z. B. Spielplan für Captions)
SHARED_READ = {"games", "opponents", "players", "sponsors", "media"}
# Felder, die nur mit Finanz-Leserecht sichtbar sind
FINANCE_FIELDS = {"sponsors": ("amount",), "sponsor_packages": ("price",)}
# Felder, die nur mit Leserecht im eigenen Bereich sichtbar sind (nicht über SHARED_READ)
AREA_FIELDS = {"sponsors": ("files", "package_id")}
# Kontaktdaten: nur mit Schreibrecht im Bereich der Tabelle sichtbar (Spieler mit Leserecht sehen keine Nummern der anderen)
WRITE_FIELDS = {"players": ("email", "phone")}
# Tabellen, die überhaupt nur mit Schreibrecht im Bereich lesbar sind (enthalten Kontaktdaten)
WRITE_ONLY_TABLES = {"player_signups"}
# Felder, die nur der Server setzt (beim Speichern über die API verworfen)
SERVER_FIELDS = {"posts": ("publish_state", "publish_log", "published_at"), "story_rules": ("last_run", "last_result"),
                 "apparel_orders": ("booked_tx",),
                 "card_orders": ("order_no", "invoice_no", "invoice_sent", "paid", "paid_on", "total", "price_each", "shipping", "count",
                                 "tracking_no", "shipped_on", "shipped_mail", "cancel_hash", "cancelled", "cancelled_by"),
                 "player_signups": ("player_id",)}
# Dateien aus data/media, die der Browser direkt anzeigen darf. Alles andere wird als Download ausgeliefert.
MEDIA_INLINE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".mp4", ".mov", ".webm"}

# Seiten, die auch im Wartungsmodus erreichbar bleiben (Pflichtangaben, Storno bis Zahlungseingang, Spielerbogen fürs Team)
MAINT_OPEN_PAGES = ("impressum", "datenschutz", "spielerbogen", "supporter-storno", "newsletter")
MAINT_GROUP_DESC ="Wartungsmodus: sieht die Webseite trotz Wartung und darf den Modus, Text und Bild ändern"
DEFAULT_GROUPS = [
    ("Vorstand", "Vorstand des Vereins", {"medien": 2, "verein": 2, "mitglieder": 2, "finanzen": 2, "wartung": 2, "postfach": 2, "spieltag": 2}),
    ("Kassenwart", "Finanzen und Beiträge", {"medien": 0, "verein": 1, "mitglieder": 2, "finanzen": 2, "wartung": 0, "postfach": 0, "spieltag": 0}),
    ("Spartenleitung", "Leitung Fußball, Jugend, Turnen und American Football", {"medien": 1, "verein": 2, "mitglieder": 1, "finanzen": 0, "wartung": 0, "postfach": 0, "spieltag": 2}),
    ("Trainer", "Trainer und Betreuer aller Mannschaften", {"medien": 1, "verein": 2, "mitglieder": 1, "finanzen": 0, "wartung": 0, "postfach": 0, "spieltag": 1}),
    ("Media Team", "Webseite, Social Media, Fotos", {"medien": 2, "verein": 1, "mitglieder": 0, "finanzen": 0, "wartung": 0, "postfach": 0, "spieltag": 0}),
    ("Helfer", "Helfer am Spieltag und bei Festen", {"medien": 0, "verein": 1, "mitglieder": 0, "finanzen": 0, "wartung": 0, "postfach": 0, "spieltag": 1}),
    ("Spieler", "Spieler der Herrenmannschaften", {"medien": 0, "verein": 1, "mitglieder": 0, "finanzen": 0, "wartung": 0, "postfach": 0, "spieltag": 0}),
    ("Wartung", MAINT_GROUP_DESC, {"medien": 0, "verein": 0, "mitglieder": 0, "finanzen": 0, "wartung": 2, "postfach": 0}),
]
# Bestehende Server: Bereich „Spieler“ beim ersten Start mit 4.13 für die Standardgruppen nach Namen vorbelegen


@contextlib.contextmanager
def db():
    """Verbindung öffnen, am Ende committen (bzw. bei Fehler zurückrollen) und schließen."""
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 15000")
        try:
            with conn:
                yield conn
        finally:
            conn.close()


def init_db():
    DATA.mkdir(parents=True, exist_ok=True)
    MEDIA.mkdir(exist_ok=True)
    BACKUPS.mkdir(exist_ok=True)
    with db() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        # Benutzer und Sitzungen: bewusst NICHT in TABLES, damit sie nie über die allgemeine API erreichbar sind
        conn.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE COLLATE NOCASE, "
                     "pw_hash TEXT, role TEXT DEFAULT 'user', created_at TEXT, last_login TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER, expires REAL, "
                     "created_at TEXT, ip TEXT, user_agent TEXT)")
        ucols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        for c, t in (("display_name", "TEXT"), ("email", "TEXT"), ("is_admin", "INTEGER DEFAULT 0"), ("active", "INTEGER DEFAULT 1"),
                     ("member_id", "INTEGER"), ("invite_hash", "TEXT"), ("invite_expires", "REAL"), ("notify", "TEXT"),
                     ("reset_hash", "TEXT"), ("reset_expires", "REAL"),
                     ("login_fails", "INTEGER DEFAULT 0"), ("login_fail_at", "REAL"), ("locked_until", "REAL"),
                     ("player_id", "INTEGER"),          # Person aus Kader & Staff (Reiter Spieler: Name, Mannschaft, Gruppe)
                     ("cal_hash", "TEXT"),              # früheres Kalender-Abo (nicht mehr genutzt)
                     ("phone", "TEXT"),                 # Telefon (bei der Einladung angegeben, nur für Admins sichtbar)
                     ("invite_profile", "TEXT"),
                     ("tabbar", "TEXT"),                # eigene Tab-Leiste unten am Handy: JSON-Liste mit bis zu 4 Seitennamen
                     ("dash_layout", "TEXT"),           # eigene Übersicht: JSON-Liste [{k: Widget, w: 1 oder 2}] in Reihenfolge
                     ("mail_role", "TEXT"),
                     ("sig_phone", "TEXT")):            # Telefon in der eigenen Mail-Signatur (Mein Profil), leer = keine           # Rolle in der Mail-Signatur (z. B. Headcoach), legt der Admin fest       # Einladung: JSON {"kind": Spieler/Coach/Staff oder "", "team": ...} = Kader-Angaben abfragen
            if c not in ucols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {c} {t}")
        if "role" in ucols:
            conn.execute("UPDATE users SET is_admin=1 WHERE role='admin' AND (is_admin IS NULL OR is_admin=0)")
        conn.execute("CREATE TABLE IF NOT EXISTS groups (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE COLLATE NOCASE, "
                     "description TEXT, sort INTEGER DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS group_perms (group_id INTEGER, area TEXT, level INTEGER, PRIMARY KEY (group_id, area))")
        conn.execute("CREATE TABLE IF NOT EXISTS user_groups (user_id INTEGER, group_id INTEGER, PRIMARY KEY (user_id, group_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS user_perms (user_id INTEGER, area TEXT, level INTEGER, PRIMARY KEY (user_id, area))")
        # Zugangsdaten für Facebook/Instagram: nie über die API lesbar, nicht im Backup-Download
        conn.execute("CREATE TABLE IF NOT EXISTS secrets (key TEXT PRIMARY KEY, value TEXT)")
        # Zwei-Faktor-Anmeldung: Geheimnis und Hashes der Wiederherstellungscodes, wie users nie über die API, nicht im Backup-Download
        conn.execute("CREATE TABLE IF NOT EXISTS user_2fa (user_id INTEGER PRIMARY KEY, secret TEXT, enabled INTEGER DEFAULT 0, "
                     "pending_secret TEXT, pending_expires REAL, last_step INTEGER DEFAULT 0, recovery TEXT, enabled_at TEXT)")
        # Änderungsprotokoll: nur für Admins lesbar, nicht über die allgemeine API
        conn.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT, user_id INTEGER, user_name TEXT, "
                     "action TEXT, table_name TEXT, record_id INTEGER, label TEXT, details TEXT)")
        conn.execute("CREATE INDEX IF NOT EXISTS audit_time ON audit_log (time)")
        # Bereits verschickte Erinnerungen (jede nur einmal)
        conn.execute("CREATE TABLE IF NOT EXISTS notify_sent (key TEXT PRIMARY KEY, time TEXT)")
        # Heimspieltag: geheimer Link pro Spiel zum Eintragen ohne Konto (/helfer/<token>), nur über /api/gameday
        conn.execute("CREATE TABLE IF NOT EXISTS gd_links (game_id INTEGER PRIMARY KEY, token TEXT UNIQUE, open INTEGER DEFAULT 1, created TEXT)")
        # Push-Abos je Gerät (Web Push): wie Konten nie über die API, nicht im Backup-Download
        conn.execute("CREATE TABLE IF NOT EXISTS push_subs (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, endpoint TEXT UNIQUE, "
                     "p256dh TEXT, auth TEXT, ua TEXT, created TEXT, last_ok TEXT)")
        # Eigenes Postfach je Konto (nur Admins setzen es, Passwort nie über die API lesbar): Antworten und neue Mails gehen darüber raus
        conn.execute("CREATE TABLE IF NOT EXISTS user_mail (user_id INTEGER PRIMARY KEY, address TEXT, smtp_host TEXT, smtp_port TEXT, "
                     "smtp_security TEXT, imap_host TEXT, username TEXT, password TEXT, updated TEXT)")
        # Seit 4.43: alle Mail-Konten zentral (Admin > E-Mails), je Person höchstens eins (user_id); user_mail bleibt ungenutzt liegen
        conn.execute("CREATE TABLE IF NOT EXISTS mail_accounts (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, address TEXT, smtp_host TEXT, "
                     "smtp_port TEXT, smtp_security TEXT, imap_host TEXT, username TEXT, password TEXT, updated TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        if not conn.execute("SELECT 1 FROM mail_accounts LIMIT 1").fetchone() and get_setting(conn, "mail_accounts_migrated") != "1":
            conn.execute("INSERT INTO mail_accounts (user_id, address, smtp_host, smtp_port, smtp_security, imap_host, username, password, updated) "
                         "SELECT user_id, address, smtp_host, smtp_port, smtp_security, imap_host, username, password, updated FROM user_mail")
            set_setting(conn, "mail_accounts_migrated", "1")
        # Mehrere Personen je Mail-Konto (je Person weiterhin höchstens ein Konto); mail_accounts.user_id bleibt ungenutzt liegen
        conn.execute("CREATE TABLE IF NOT EXISTS mail_account_users (account_id INTEGER, user_id INTEGER UNIQUE, PRIMARY KEY (account_id, user_id))")
        if get_setting(conn, "mail_account_users_migrated") != "1":
            conn.execute("INSERT OR IGNORE INTO mail_account_users (account_id, user_id) SELECT id, user_id FROM mail_accounts WHERE user_id IS NOT NULL")
            set_setting(conn, "mail_account_users_migrated", "1")
        # Seit 4.44: beliebig viele Personen je Mail-Konto und beliebig viele Mail-Konten je Person
        conn.execute("CREATE TABLE IF NOT EXISTS mail_links (account_id INTEGER, user_id INTEGER, PRIMARY KEY (account_id, user_id))")
        if get_setting(conn, "mail_links_migrated") != "1":
            conn.execute("INSERT OR IGNORE INTO mail_links (account_id, user_id) SELECT account_id, user_id FROM mail_account_users")
            set_setting(conn, "mail_links_migrated", "1")
        # Neue Mails im Posteingang (Benachrichtigung an die Gruppen aus pf_notify_groups, bis jemand sie erledigt)
        conn.execute("CREATE TABLE IF NOT EXISTS pf_inbox (id INTEGER PRIMARY KEY AUTOINCREMENT, folder TEXT, uid INTEGER, uidvalidity TEXT, message_id TEXT, "
                     "subject TEXT, sender TEXT, received TEXT, status TEXT DEFAULT 'neu', handled_by INTEGER, handled_at TEXT, action TEXT, notified TEXT)")
        # Sponsoringverträge (Sponsoren > Verträge): Eingaben als JSON, PDF in data/media, nicht über die generische API
        conn.execute("CREATE TABLE IF NOT EXISTS sponsor_contracts (id INTEGER PRIMARY KEY AUTOINCREMENT, sponsor_id INTEGER, number TEXT, data TEXT, "
                     "file TEXT, created TEXT, created_by INTEGER)")
        # Rechnungen an Sponsoren aus einem Sponsoringvertrag (Nummer aus derselben Folge wie alle Rechnungen, invoice_next)
        conn.execute("CREATE TABLE IF NOT EXISTS sponsor_invoices (id INTEGER PRIMARY KEY AUTOINCREMENT, contract_id INTEGER, sponsor_id INTEGER, number TEXT, "
                     "data TEXT, file TEXT, created TEXT, created_by INTEGER)")
        # Newsletter: Abonnenten mit Einwilligung (Double-Opt-In) und verschickte Ausgaben; nur über /api/newsletter
        conn.execute("CREATE TABLE IF NOT EXISTS nl_subscribers (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT UNIQUE COLLATE NOCASE, name TEXT, "
                     "status TEXT DEFAULT 'offen', groups TEXT DEFAULT '[]', pending_groups TEXT DEFAULT '[]', confirm_hash TEXT, confirm_expires REAL, "
                     "consent_at TEXT, consent_text TEXT, source TEXT, created TEXT, unsubscribed_at TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS nl_issues (id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT, body TEXT, groups TEXT DEFAULT '[]', "
                     "status TEXT DEFAULT 'entwurf', created TEXT, created_by INTEGER, sent_at TEXT, sent_count INTEGER DEFAULT 0, failed INTEGER DEFAULT 0)")
        # Mail-Aufgaben (Postfach): wer soll welche Mail bearbeiten
        conn.execute("CREATE TABLE IF NOT EXISTS mail_tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, folder TEXT, uid INTEGER, message_id TEXT, "
                     "subject TEXT, sender TEXT, user_id INTEGER, assigned_by INTEGER, note TEXT, status TEXT DEFAULT 'offen', created TEXT, "
                     "done_at TEXT, banner_seen INTEGER DEFAULT 0)")
        if conn.execute("SELECT COUNT(*) FROM groups").fetchone()[0] == 0:
            for i, (name, desc, perms) in enumerate(DEFAULT_GROUPS):
                gid = conn.execute("INSERT INTO groups (name, description, sort) VALUES (?, ?, ?)", (name, desc, i)).lastrowid
                for area, lvl in perms.items():
                    conn.execute("INSERT INTO group_perms (group_id, area, level) VALUES (?, ?, ?)", (gid, area, lvl))
        # Den Bereich „Spieler“ (Teamfunktionen, 4.13 bis 4.21) gibt es nicht mehr: alte Rechte dazu entfernen. Die Tabellen sq_* bleiben ungenutzt liegen.
        conn.execute("DELETE FROM group_perms WHERE area='spieler'")
        conn.execute("DELETE FROM user_perms WHERE area='spieler'")
        if not conn.execute("SELECT 1 FROM group_perms WHERE area='postfach' LIMIT 1").fetchone():
            # Bereich Postfach auf bestehendem Server: nur der Vorstand bekommt Bearbeiten, alle anderen keinen Zugriff
            for g in conn.execute("SELECT id, name FROM groups").fetchall():
                conn.execute("INSERT OR REPLACE INTO group_perms (group_id, area, level) VALUES (?, 'postfach', ?)",
                             (g["id"], 2 if (g["name"] or "").strip().lower() == "vorstand" else 0))
        if not conn.execute("SELECT 1 FROM group_perms WHERE area='wartung' LIMIT 1").fetchone():
            # Bereich Wartung auf bestehendem Server: Vorstand darf alles, dazu eine eigene Gruppe „Wartung“
            for g in conn.execute("SELECT id, name FROM groups").fetchall():
                conn.execute("INSERT OR REPLACE INTO group_perms (group_id, area, level) VALUES (?, 'wartung', ?)",
                             (g["id"], 2 if (g["name"] or "").strip().lower() == "vorstand" else 0))
            if not conn.execute("SELECT 1 FROM groups WHERE lower(name)='wartung'").fetchone():
                sort = (conn.execute("SELECT MAX(sort) FROM groups").fetchone()[0] or 0) + 1
                gid = conn.execute("INSERT INTO groups (name, description, sort) VALUES ('Wartung', ?, ?)", (MAINT_GROUP_DESC, sort)).lastrowid
                for area in AREAS:
                    conn.execute("INSERT OR REPLACE INTO group_perms (group_id, area, level) VALUES (?, ?, ?)", (gid, area, 2 if area == "wartung" else 0))
        for table, cols in TABLES.items():
            col_sql = ", ".join(f'"{c}" {t}' for c, t in cols.items())
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS "{table}" '
                f"(id INTEGER PRIMARY KEY AUTOINCREMENT, {col_sql}, "
                f"created_at TEXT, updated_at TEXT)"
            )
            existing = {r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")')}
            for c, t in cols.items():
                if c not in existing:
                    conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{c}" {t}')
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        if get_setting(conn, "trainings_seeded") != "1":
            # Bekannte Zeiten der Turn- und Gymnastikgruppen einmalig vorbelegen (von der bisherigen Vereinsseite), danach nur im Hub
            if not conn.execute("SELECT 1 FROM trainings LIMIT 1").fetchone():
                now = datetime.now().isoformat(timespec="seconds")
                for row in (("Fit for Fun", "Donnerstag", "", "", "Turnhalle Grundschule Wolthusen"),
                            ("Gymnastikgruppe", "Mittwoch", "", "", "Cirksena-Schule"),
                            ("Herren-Gymnastik", "Dienstag", "20:00", "21:30", "Sporthalle Grundschule Wolthusen")):
                    conn.execute("INSERT INTO trainings (team, weekday, start, end, place, active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?)", (*row, now, now))
            set_setting(conn, "trainings_seeded", "1")
        if not conn.execute("SELECT 1 FROM settings WHERE key='pf_media_granted'").fetchone():
            # 4.27: Das Media Team bekommt neue Mails gemeldet und darf sie bearbeiten (einmalig, danach unter Gruppen & Rechte änderbar)
            g = conn.execute("SELECT id FROM groups WHERE lower(name)='media team'").fetchone()
            if g:
                conn.execute("INSERT OR REPLACE INTO group_perms (group_id, area, level) VALUES (?, 'postfach', 2)", (g["id"],))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('pf_media_granted', '1')")
        # Webseiten-Texte: neue Standardtexte einmalig in noch leere Felder übernehmen (eigene Texte bleiben unberührt)
        if get_setting(conn, "site_texts_version") != SITE_TEXTS_VERSION:
            for k, v in DEFAULT_SETTINGS.items():
                if k.startswith("site_") and v:
                    conn.execute("UPDATE settings SET value=? WHERE key=? AND TRIM(IFNULL(value,''))=''", (v, k))
            set_setting(conn, "site_texts_version", SITE_TEXTS_VERSION)
        # Unveränderte alte Vorlage der Datenschutzerklärung durch die aktuelle ersetzen (eigene Änderungen bleiben unberührt)
        r = conn.execute("SELECT value FROM settings WHERE key='site_datenschutz'").fetchone()
        if r and r["value"] and hashlib.sha256(r["value"].encode()).hexdigest() in OLD_LEGAL_DATENSCHUTZ:
            conn.execute("UPDATE settings SET value=? WHERE key='site_datenschutz'", (LEGAL_DATENSCHUTZ,))
        # Google-Tabelle gibt es nicht mehr (ersetzt durch den Spielerbogen): alte Einstellungen samt Link entfernen.
        # Die Tabellen sheet_players und sheet_log bleiben auf älteren Servern unberührt liegen (nur additive Änderungen).
        conn.execute("DELETE FROM settings WHERE key LIKE 'sheet\\_%' ESCAPE '\\'")


def row_dict(r):
    return {k: r[k] for k in r.keys()}


# Links mit gefährlichem Schema (javascript:, data: ...) werden nie gespeichert, auch nicht versteckt in Dateilisten (JSON).
# Steuerzeichen und Leerzeichen dazwischen zählen mit, so wie Browser sie beim Öffnen eines Links ignorieren.
BAD_LINK = re.compile(r"^[\x00-\x20]*(?:j[\s\x00-\x1f]*a[\s\x00-\x1f]*v[\s\x00-\x1f]*a[\s\x00-\x1f]*s[\s\x00-\x1f]*c[\s\x00-\x1f]*r[\s\x00-\x1f]*i"
                      r"[\s\x00-\x1f]*p[\s\x00-\x1f]*t|vbscript|data|file|blob)[\s\x00-\x1f]*:", re.I)


def has_bad_link(v):
    if isinstance(v, str):
        if BAD_LINK.match(v):
            return True
        if v[:1] in "[{":   # Dateilisten werden als JSON-Text gespeichert
            try:
                return has_bad_link(json.loads(v))
            except ValueError:
                return False
        return False
    if isinstance(v, dict):
        return any(has_bad_link(x) for x in v.values())
    if isinstance(v, list):
        return any(has_bad_link(x) for x in v)
    return False


def clean_values(table, data):
    cols = TABLES[table]
    out = {}
    for k, v in data.items():
        if k not in cols:
            continue
        if isinstance(v, bool):
            v = int(v)
        if v == "" and ("INTEGER" in cols[k] or "REAL" in cols[k]):
            v = None
        out[k] = v
    return out


# ---------------------------------------------------------------------------
# Benutzer, Passwörter, Sitzungen
# ---------------------------------------------------------------------------
def hash_pw(pw):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_pw(pw, stored):
    try:
        algo, salt, h = (stored or "").split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(pw.encode("utf-8"), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc.hex(), h)
    except Exception:  # noqa
        return False


def pw_problem(pw):
    if len(pw or "") < 10:
        return "Das Passwort muss mindestens 10 Zeichen lang sein."
    return ""


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def user_count():
    with db() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def check_username(username):
    username = (username or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._@-]{2,40}", username):
        raise ValueError("Benutzername: 2 bis 40 Zeichen, nur Buchstaben, Zahlen und . _ - @")
    return username


def create_user(username, password=None, is_admin=False, display_name="", email="", member_id=None):
    """Legt ein Konto an. Ohne Passwort entsteht ein Einladungslink (Rückgabe: Token)."""
    username = check_username(username)
    if password is not None:
        prob = pw_problem(password)
        if prob:
            raise ValueError(prob)
    now = datetime.now().isoformat(timespec="seconds")
    invite = None if password is not None else secrets.token_urlsafe(24)
    with db() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise ValueError("Diesen Benutzernamen gibt es schon.")
        uid = conn.execute(
            "INSERT INTO users (username, pw_hash, is_admin, active, display_name, email, member_id, invite_hash, invite_expires, created_at) "
            "VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)",
            (username, hash_pw(password) if password is not None else "", 1 if is_admin else 0, display_name or username,
             email or "", member_id, token_hash(invite) if invite else None,
             time.time() + INVITE_DAYS * 86400 if invite else None, now)).lastrowid
        if member_id:
            conn.execute("UPDATE members SET user_id=? WHERE id=?", (uid, member_id))
    return uid, invite


INVITE_DAYS = 14


def new_invite(conn, uid):
    tok = secrets.token_urlsafe(24)
    conn.execute("UPDATE users SET invite_hash=?, invite_expires=? WHERE id=?", (token_hash(tok), time.time() + INVITE_DAYS * 86400, uid))
    return tok


def effective_perms(conn, user):
    """Rechte je Bereich: Ausnahme der Person, sonst das Maximum ihrer Gruppen."""
    if user.get("is_admin"):
        return {a: 2 for a in AREAS}
    perms = {a: 0 for a in AREAS}
    for r in conn.execute("SELECT gp.area, MAX(gp.level) AS lvl FROM user_groups ug JOIN group_perms gp ON gp.group_id = ug.group_id "
                          "WHERE ug.user_id=? GROUP BY gp.area", (user["id"],)):
        if r["area"] in perms:
            perms[r["area"]] = int(r["lvl"] or 0)
    for r in conn.execute("SELECT area, level FROM user_perms WHERE user_id=?", (user["id"],)):
        if r["area"] in perms and r["level"] is not None:
            perms[r["area"]] = int(r["level"])
    return perms


def admin_count(conn):
    return conn.execute("SELECT COUNT(*) FROM users WHERE is_admin=1 AND active=1").fetchone()[0]


def bootstrap_admin():
    user = (ENV("TMH_ADMIN_USER") or "").strip()
    pw = ENV("TMH_ADMIN_PASSWORD") or ""
    if not user or not pw:
        return
    with db() as conn:
        row = conn.execute("SELECT id FROM users WHERE username=?", (user,)).fetchone()
        if row and ENV("TMH_RESET_PASSWORD") == "1":
            conn.execute("UPDATE users SET pw_hash=?, is_admin=1, active=1 WHERE id=?", (hash_pw(pw), row["id"]))
            conn.execute("DELETE FROM sessions WHERE user_id=?", (row["id"],))
            print(f"Passwort für {user} wurde zurückgesetzt.")
            return
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            return
    try:
        create_user(user, pw, is_admin=True)
        print(f"Admin-Benutzer {user} wurde angelegt.")
    except ValueError as e:
        print("Admin-Benutzer konnte nicht angelegt werden:", e)


FAILED_LOGINS = {}
FAILED_LOCK = threading.Lock()


def login_blocked(ip):
    with FAILED_LOCK:
        now = time.time()
        hits = [t for t in FAILED_LOGINS.get(ip, []) if now - t < 600]
        FAILED_LOGINS[ip] = hits
        return len(hits) >= 8


def login_failed(ip):
    with FAILED_LOCK:
        FAILED_LOGINS.setdefault(ip, []).append(time.time())


# ---------------------------------------------------------------------------
# Sperre pro Konto: nach ACCOUNT_FAIL_MAX Fehlversuchen (Passwort oder Code) ACCOUNT_LOCK_MINUTES gesperrt, mit Info-Mail.
# Unbekannte Benutzernamen werden im Speicher genauso gezählt und gesperrt, damit die Antwort nichts über Konten verrät.
# ---------------------------------------------------------------------------
ACCOUNT_FAIL_MAX = 5
ACCOUNT_LOCK_MINUTES = 15
GHOST_FAILS = {}          # Benutzername (klein) -> [Anzahl, erster Fehlversuch, gesperrt bis]
DUMMY_PW_HASH = None      # gleiche Rechenzeit für unbekannte Benutzernamen


def dummy_check_pw(pw):
    global DUMMY_PW_HASH
    if DUMMY_PW_HASH is None:
        DUMMY_PW_HASH = hash_pw(secrets.token_hex(8))
    check_pw(pw, DUMMY_PW_HASH)


def account_locked(conn, u, username):
    """True, wenn das Konto (oder der unbekannte Benutzername) gerade gesperrt ist."""
    now = time.time()
    if u is None:
        with FAILED_LOCK:
            g = GHOST_FAILS.get((username or "").lower())
            return bool(g and g[2] > now)
    return bool(u["locked_until"] and u["locked_until"] > now)


def account_failed(conn, u, username, ip):
    """Fehlversuch zählen. Beim Erreichen der Grenze sperren und (nur bei echten Konten) die Person per Mail informieren."""
    now = time.time()
    window = ACCOUNT_LOCK_MINUTES * 60
    if u is None:
        with FAILED_LOCK:
            if len(GHOST_FAILS) > 5000:
                for k in [k for k, g in GHOST_FAILS.items() if now - g[1] > window and g[2] < now]:
                    GHOST_FAILS.pop(k, None)
            g = GHOST_FAILS.get((username or "").lower())
            if not g or now - g[1] > window:
                g = [0, now, 0]
            g[0] += 1
            if g[0] >= ACCOUNT_FAIL_MAX:
                g = [0, now, now + window]
            GHOST_FAILS[(username or "").lower()] = g
        return
    count = int(u["login_fails"] or 0)
    if not u["login_fail_at"] or now - u["login_fail_at"] > window:
        count = 0
    count += 1
    if count >= ACCOUNT_FAIL_MAX:
        conn.execute("UPDATE users SET login_fails=0, login_fail_at=NULL, locked_until=? WHERE id=?", (now + window, u["id"]))
        audit(conn, "Anmeldung", "Konto vorübergehend gesperrt (Fehlversuche)", "users", u["id"], u["display_name"] or u["username"], {"IP": ["", ip]})
        email = account_email(conn, u)
        cfg = smtp_config()
        if email and cfg["smtp_host"]:
            body = (f"Hallo {u['display_name'] or u['username']},\n\nbei deinem Konto im Wolthusen Hub (Benutzername: {u['username']}) gab es gerade "
                    f"{ACCOUNT_FAIL_MAX} fehlgeschlagene Anmeldeversuche ({datetime.now():%d.%m.%Y %H:%M}, IP-Adresse {ip}).\n"
                    f"Zum Schutz ist die Anmeldung für {ACCOUNT_LOCK_MINUTES} Minuten gesperrt. Danach geht es automatisch wieder.\n\n"
                    "Warst du das nicht? Dann ändere bitte dein Passwort, richte unter „Mein Profil“ die Zwei-Faktor-Anmeldung ein "
                    "und melde dich beim Vorstand bzw. Admin.")
            threading.Thread(target=lambda: send_mail(cfg, email, "Wolthusen Hub: Anmeldung vorübergehend gesperrt", body, footer=False), daemon=True).start()
    else:
        conn.execute("UPDATE users SET login_fails=?, login_fail_at=? WHERE id=?",
                     (count, u["login_fail_at"] if count > 1 else now, u["id"]))


def account_ok(conn, uid):
    conn.execute("UPDATE users SET login_fails=0, login_fail_at=NULL, locked_until=NULL WHERE id=?", (uid,))


# ---------------------------------------------------------------------------
# Zwei-Faktor-Anmeldung (TOTP nach RFC 6238: 30 Sekunden, 6 Ziffern, SHA-1, wie alle gängigen Authenticator-Apps)
# Geheimnis in user_2fa (nicht in TABLES, nie über die API lesbar, nicht im Backup-Download, beim Serverumzug dabei).
# Wiederherstellungscodes nur als SHA-256-Hash, jeder nur einmal gültig.
# ---------------------------------------------------------------------------
TOTP_ISSUER = "Wolthusen Hub"
RECOVERY_COUNT = 10
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
TWOFA_TICKET_MINUTES = 5
TWOFA_POLICY_KEYS = ("twofa_admins", "twofa_finance")   # Einstellungen: Pflicht für Admins bzw. Finanz-Schreibrecht ("1")
TWOFA_TICKETS = {}        # Hash des Zwischen-Tickets -> {"uid", "expires", "tries"} (nach richtigem Passwort, vor dem Code)


def totp_code(secret_b32, step):
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8), casefold=True)
    mac = hmac.new(key, step.to_bytes(8, "big"), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    return f"{(int.from_bytes(mac[off:off + 4], 'big') & 0x7FFFFFFF) % 1000000:06d}"


def totp_match(secret_b32, code, last_step=0, now=None):
    """Passenden Zeitschritt zurückgeben (eine Abweichung von 30 Sekunden erlaubt), sonst 0. Schon benutzte Codes zählen nicht."""
    code = re.sub(r"\s", "", code or "")
    if not re.fullmatch(r"\d{6}", code) or not secret_b32:
        return 0
    t = int((now or time.time()) // 30)
    for step in (t - 1, t, t + 1):
        if step > (last_step or 0) and hmac.compare_digest(totp_code(secret_b32, step), code):
            return step
    return 0


def totp_uri(secret_b32, username):
    from urllib.parse import quote
    label = quote(f"{TOTP_ISSUER}:{username}")
    return f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(TOTP_ISSUER)}&algorithm=SHA1&digits=6&period=30"


def recovery_norm(code):
    return re.sub(r"[^a-z0-9]", "", (code or "").lower())


def recovery_new():
    """Neue Codes (Klartext für die einmalige Anzeige) und ihre Hashes (zum Speichern)."""
    codes = []
    for _ in range(RECOVERY_COUNT):
        c = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(10))
        codes.append(f"{c[:5]}-{c[5:]}")
    return codes, [token_hash(recovery_norm(c)) for c in codes]


def twofa_row(conn, uid):
    return conn.execute("SELECT * FROM user_2fa WHERE user_id=?", (uid,)).fetchone()


def twofa_enabled(conn, uid):
    r = twofa_row(conn, uid)
    return bool(r and r["enabled"] and r["secret"])


def twofa_required(conn, user, perms=None):
    """Pflicht für Admins bzw. Konten mit Finanz-Schreibrecht, je nach Einstellung."""
    perms = perms if perms is not None else effective_perms(conn, user)
    if user.get("is_admin") and get_setting(conn, "twofa_admins") == "1":
        return True
    return perms.get("finanzen", 0) >= 2 and get_setting(conn, "twofa_finance") == "1"


def twofa_check(conn, uid, code):
    """Code aus der App oder Wiederherstellungscode prüfen. Rückgabe: "totp", "recovery" oder ""."""
    r = twofa_row(conn, uid)
    if not r or not r["enabled"]:
        return ""
    step = totp_match(r["secret"], code, r["last_step"] or 0)
    if step:
        conn.execute("UPDATE user_2fa SET last_step=? WHERE user_id=?", (step, uid))
        return "totp"
    norm = recovery_norm(code)
    if len(norm) == 10:
        hashes = json.loads(r["recovery"] or "[]")
        h = token_hash(norm)
        for x in hashes:
            if hmac.compare_digest(x, h):
                hashes.remove(x)
                conn.execute("UPDATE user_2fa SET recovery=? WHERE user_id=?", (json.dumps(hashes), uid))
                return "recovery"
    return ""


def twofa_ticket_new(uid):
    tok = secrets.token_urlsafe(32)
    with FAILED_LOCK:
        now = time.time()
        for k in [k for k, v in TWOFA_TICKETS.items() if v["expires"] < now]:
            TWOFA_TICKETS.pop(k, None)
        TWOFA_TICKETS[token_hash(tok)] = {"uid": uid, "expires": now + TWOFA_TICKET_MINUTES * 60, "tries": 0}
    return tok


# ---------------------------------------------------------------------------
# Passwort vergessen: Link per E-Mail (60 Minuten gültig, nur einmal, nur der Hash wird gespeichert)
# ---------------------------------------------------------------------------
RESET_MINUTES = 60
RESET_HITS = {}          # "ip:..." bzw. "user:..." -> Zeitpunkte der Anfragen
RESET_LIMITS = {"ip": 10, "user": 3, "form": 60, "chat": 400, "cal": 300}   # pro Stunde ("form": Spielerbogen, oft viele Spieler im selben WLAN)


def reset_rate_ok(kind, key):
    with FAILED_LOCK:
        now = time.time()
        k = f"{kind}:{key}"
        hits = [t for t in RESET_HITS.get(k, []) if now - t < 3600]
        ok = len(hits) < RESET_LIMITS[kind]
        if ok:
            hits.append(now)
        RESET_HITS[k] = hits
        return ok


def account_email(conn, u):
    """E-Mail des Kontos, sonst die des verknüpften Mitglieds."""
    if u["email"]:
        return u["email"]
    if u["member_id"]:
        m = conn.execute("SELECT email FROM members WHERE id=?", (u["member_id"],)).fetchone()
        return (m["email"] or "").strip() if m else ""
    return ""


def request_password_reset(login, base_url):
    """Sucht das Konto zu Benutzername oder E-Mail und schickt den Link. Gibt nach außen nie preis, ob es das Konto gibt."""
    login = (login or "").strip()
    if not login:
        return
    with db() as conn:
        u = conn.execute("SELECT * FROM users WHERE active=1 AND username=? COLLATE NOCASE", (login,)).fetchone()
        if not u and "@" in login:
            u = conn.execute("SELECT * FROM users WHERE active=1 AND lower(email)=lower(?)", (login,)).fetchone() or conn.execute(
                "SELECT u.* FROM users u JOIN members m ON m.id = u.member_id WHERE u.active=1 AND lower(m.email)=lower(?)", (login,)).fetchone()
        if not u:
            return
        email = account_email(conn, u)
        if not email or not reset_rate_ok("user", u["id"]):
            return
        tok = secrets.token_urlsafe(32)
        conn.execute("UPDATE users SET reset_hash=?, reset_expires=? WHERE id=?", (token_hash(tok), time.time() + RESET_MINUTES * 60, u["id"]))
        audit(conn, "Passwort vergessen", "Link angefordert", "users", u["id"], u["display_name"] or u["username"])
    cfg = smtp_config()
    if not cfg["smtp_host"]:
        return
    link = f"{cfg['hub_url'] or base_url}/passwort-neu/{tok}"
    body = (f"Hallo {u['display_name'] or u['username']},\n\nfür dein Konto im Wolthusen Hub (Benutzername: {u['username']}) wurde ein neues Passwort angefordert.\n"
            f"Über diesen Link legst du es fest. Er gilt {RESET_MINUTES} Minuten und funktioniert nur einmal:\n\n{link}\n\n"
            "Wenn du das nicht warst, ignoriere diese Mail einfach. Dein bisheriges Passwort bleibt dann gültig.")
    threading.Thread(target=lambda: send_mail(cfg, email, "Wolthusen Hub: Passwort zurücksetzen", body, footer=False), daemon=True).start()


# ---------------------------------------------------------------------------
# Teamkleidung: öffentlicher Bestell-Link (ohne Anmeldung)
# ---------------------------------------------------------------------------
ORDER_HITS = {}          # IP -> Zeitpunkte der letzten öffentlichen Bestellungen
ORDER_LIMIT = 60         # Versuche pro Stunde und IP (großzügig, weil ein Team oft über dasselbe WLAN bestellt)
AP_FIELD_TYPES = {"text", "number", "select", "check"}


def order_rate_ok(ip):
    with FAILED_LOCK:
        now = time.time()
        hits = [t for t in ORDER_HITS.get(ip, []) if now - t < 3600]
        ok = len(hits) < ORDER_LIMIT
        if ok:
            hits.append(now)
        ORDER_HITS[ip] = hits
        return ok


def apparel_fields(a):
    try:
        fields = json.loads(a["fields"] or "[]")
    except ValueError:
        return []
    return [f for f in fields if isinstance(f, dict) and f.get("key") and f.get("type") in AP_FIELD_TYPES]


def apparel_open(a):
    return bool(a["active"]) and (not a["deadline"] or datetime.now().strftime("%Y-%m-%d") <= a["deadline"])


def clean_order(fields, data, qty):
    """Prüft eine Bestellung vom öffentlichen Link. Liefert (werte, menge, fehler)."""
    if not isinstance(data, dict):
        return None, None, "Ungültige Bestellung."
    out = {}
    for f in fields:
        label, t, v = f.get("label") or "Feld", f["type"], data.get(f["key"])
        if t == "check":
            v = 1 if v in (True, 1, "1", "true", "on") else 0
        else:
            v = str(v if v is not None else "").strip()[:200]
            if t == "select" and v and v not in (f.get("options") or []):
                return None, None, f"Ungültige Auswahl bei {label}."
            if t == "number" and v and not re.fullmatch(r"\d{1,6}", v):
                return None, None, f"{label}: bitte nur Ziffern eintragen."
        if f.get("required") and not v:
            return None, None, f"Bitte {label} ausfüllen."
        out[f["key"]] = v
    try:
        qty = int(qty)
    except (TypeError, ValueError):
        qty = 0
    if not 1 <= qty <= 20:
        return None, None, "Die Menge muss zwischen 1 und 20 liegen."
    return out, qty, None


# ---------------------------------------------------------------------------
# Automatisch posten: Facebook-Seite und Instagram über die Meta Graph API
# Das Seiten-Token liegt in der Tabelle secrets (nie über die API lesbar, nicht im Backup-Download).
# Instagram holt Bilder selbst ab, dafür gibt es signierte Links /teilen/<sig>/<datei> (nur Bilder).
# ---------------------------------------------------------------------------
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/webp", ".webp")   # fehlt in manchen Systemen (Webseite, Instagram-Bilder)
mimetypes.add_type("font/woff2", ".woff2")   # Schriften der Webseite
GRAPH = ENV("TMH_GRAPH_URL") or "https://graph.facebook.com/v26.0"   # Variable nur für lokale Tests mit einem Test-Server
SOCIAL_LOCK = threading.Lock()
POST_LATE_HOURS = 24        # freigegebene Posts, die länger überfällig sind, werden nicht mehr nachgeholt
STORY_LATE_MINUTES = 180    # Story-Regeln: so lange nach der geplanten Uhrzeit wird noch gepostet (z. B. nach Neustart)
SHARE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXT = {".mp4", ".mov"}


class GraphError(Exception):
    pass


def secret_get(conn, key):
    r = conn.execute("SELECT value FROM secrets WHERE key=?", (key,)).fetchone()
    return r["value"] if r and r["value"] is not None else ""


def secret_set(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO secrets (key, value) VALUES (?, ?)", (key, value))


def social_config():
    with db() as conn:
        cfg = {k: secret_get(conn, k) for k in ("fb_token", "fb_page_id", "fb_page_name", "ig_user_id", "ig_username", "public_url", "share_key")}
        if not cfg["share_key"]:
            cfg["share_key"] = secrets.token_hex(32)
            secret_set(conn, "share_key", cfg["share_key"])
    cfg["public_url"] = (cfg["public_url"] or SITE_URL).rstrip("/")
    return cfg


# ---------------------------------------------------------------------------
# Öffentliche Daten für die Webseite (/api/public und die Seiten unter /).
# Nur hier definierte Felder gehen raus, jede Antwort wird Feld für Feld neu gebaut.
# Nie: Finanzen, Mitglieder, Kontakte, Konten, Notizen, interne Dateien.
# ---------------------------------------------------------------------------
PUBLIC_SETTINGS = ("club_name", "club_short", "season", "instagram", "home_location", "home_city", "entry_fee", "card_price", "card_shipping", "card_shipping_registered", "training_text",
                   *(k for k in DEFAULT_SETTINGS if k.startswith("site_")))


def public_image(path, key):
    """Signierter Link auf ein einzelnes Bild aus data/media (sonst leer)."""
    name = (path or "").rsplit("/", 1)[-1]
    if not (path or "").startswith("/media/") or Path(name).suffix.lower() not in IMAGE_EXT or not (MEDIA / name).is_file():
        return ""
    return f"/teilen/{share_sig(key, name)}/{name}"


# ---------------------------------------------------------------- Dauerkarte: Online-Bestellung, Überweisung, Rechnung
CARD_ORDER_MAX = 10          # Karten pro Bestellung
CARD_SHIPS = {"Post": "per Post", "Einschreiben": "per Einschreiben"}   # Lieferarten mit Versand (Anschrift nötig)
CARD_SETTING_KEYS = ("card_shipping", "card_shipping_registered", "inv_sender", "inv_account_holder", "inv_iban", "inv_bic", "inv_bank", "inv_tax_no", "inv_tax_note",
                     "inv_due_days", "site_card_process", "site_card_delivery_text", "card_letter_text", "site_card_cancel_text")   # im Hub unter Dauerkarte (Finanzen 2)
INVOICE_DIR = DATA / "rechnungen"


def money(v):
    try:
        return round(float(str(v).replace("€", "").replace(",", ".").strip()), 2)
    except (TypeError, ValueError):
        return None


def eur_text(v):
    return f"{(v or 0):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def card_holders(o):
    try:
        v = json.loads(o["holders"] or "[]")
        return [str(x) for x in v] if isinstance(v, list) else []
    except ValueError:
        return []


def card_order_summary(o):
    lines = [f"Bestellnummer: {o['order_no']}", f"Besteller: {o['buyer']}", f"E-Mail: {o['email']}", f"Telefon: {o['phone'] or '-'}", "",
             f"{o['count']} x Dauerkarte {o['season'] or ''} zu je {eur_text(o['price_each'])}"]
    lines += [f"  Karte {i + 1}: {h}" for i, h in enumerate(card_holders(o))]
    if o["delivery"] in CARD_SHIPS:
        lines += ["", f"Lieferung: {CARD_SHIPS[o['delivery']]} ({eur_text(o['shipping'])})", f"  {o['buyer']}", f"  {o['street']}", f"  {o['zip']} {o['city']}"]
    else:
        lines += ["", "Lieferung: Abholung am Einlass beim Heimspiel"]
    lines += ["", f"Gesamtbetrag: {eur_text(o['total'])}"]
    return "\n".join(lines)


def card_bank(conn):
    return {k: (get_setting(conn, "inv_" + k) or "").strip() for k in ("account_holder", "iban", "bic", "bank", "due_days")}


def card_order_mail(conn, o, cancel_url=""):
    """Bestätigung an den Besteller: Übersicht, Überweisungsdaten, Ablauf, Lieferung, Storno-Link, Hinweise."""
    b = card_bank(conn)
    due = int(b["due_days"]) if b["due_days"].isdigit() else 14
    if b["iban"]:
        pay = (f"Bitte überweise den Gesamtbetrag innerhalb von {due} Tagen:\n\n"
               f"  Empfänger: {b['account_holder'] or 'SV Amisia Wolthusen e.V.'}\n  IBAN: {b['iban']}\n"
               + (f"  BIC: {b['bic']}\n" if b["bic"] else "") + (f"  Bank: {b['bank']}\n" if b["bank"] else "")
               + f"  Betrag: {eur_text(o['total'])}\n  Verwendungszweck: {o['order_no']} {o['buyer']}")
    else:
        pay = "Die Bankverbindung für die Überweisung schicken wir dir in einer gesonderten E-Mail."
    delivery = (get_setting(conn, "site_card_delivery_text") or "").strip() or "Infos zur Lieferung der Karten folgen."
    terms = (get_setting(conn, "site_card_terms") or "").strip()
    cancel = (get_setting(conn, "site_card_cancel_text") or "").strip()
    storno = ("STORNIEREN\nBis zum Eingang deiner Zahlung kannst du die Bestellung kostenlos stornieren"
              + (f", ganz einfach über diesen Link:\n{cancel_url}\n" if cancel_url else ".\n")
              + "Oder schreib uns einfach eine E-Mail" + (f" an {club}" if (club := (get_setting(conn, "site_contact_email") or "").strip()) else "")
              + ". Nach Zahlungseingang ist keine Stornierung mehr möglich.\n\n")
    return (f"Hallo {o['buyer']},\n\ndanke für deine Bestellung der Dauerkarte {o['season'] or ''} des SV Amisia Wolthusen! "
            f"Hiermit bestätigen wir deine Bestellung.\n\n{card_order_summary(o)}\n\n"
            f"ÜBERWEISUNG\n{pay}\n\nRECHNUNG\nSobald dein Betrag bei uns eingegangen ist, schicken wir dir die Rechnung per E-Mail.\n\n"
            f"LIEFERUNG\n{delivery}\n\n{storno}"
            + (f"WICHTIGE HINWEISE\n{terms}" + (f"\n{cancel}" if cancel else "") + "\n\n" if terms or cancel else "")
            + "Sportliche Grüße\nSV Amisia Wolthusen")


def card_cancel_lookup(token):
    """Bestellung zum Storno-Link (nur der Hash ist gespeichert)."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", token or ""):
        return None
    with db() as conn:
        return conn.execute("SELECT * FROM card_orders WHERE cancel_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()


def card_order_cancel(oid, by, user):
    """Bestellung stornieren (nur bis Zahlungseingang): unbezahlte Karten löschen, Kunde und Verein informieren.
    Liefert (Bestellung, Fehler) mit Fehler "bezahlt", "storniert" oder "nicht gefunden"; Mail-Hinweis als dritter Wert."""
    stamp = datetime.now().isoformat(timespec="seconds")
    with db() as conn:
        o = conn.execute("SELECT * FROM card_orders WHERE id=?", (oid,)).fetchone()
        if not o:
            return None, "nicht gefunden", None
        if o["cancelled"]:
            return o, "storniert", None
        if o["paid"]:
            return o, "bezahlt", None
        conn.execute("UPDATE card_orders SET cancelled=?, cancelled_by=?, updated_at=? WHERE id=?", (stamp, by, stamp, oid))
        conn.execute("DELETE FROM supporter_cards WHERE order_id=? AND IFNULL(paid, 0)=0", (oid,))
        audit(conn, user, "storniert", "card_orders", oid, f"{o['order_no']} {o['buyer']}", {"Storniert durch": by, "Summe": eur_text(o["total"])})
        o = conn.execute("SELECT * FROM card_orders WHERE id=?", (oid,)).fetchone()
        club = get_setting(conn, "site_contact_email")
    body = (f"Hallo {o['buyer']},\n\ndeine Bestellung {o['order_no']} ({o['count']} x Dauerkarte {o['season'] or ''}, {eur_text(o['total'])}) "
            f"ist storniert. Du musst nichts mehr überweisen.\n\n"
            f"Falls du den Betrag schon überwiesen hast, melde dich bitte kurz bei uns, dann erstatten wir ihn dir.\n\n"
            f"Schade, dass es diesmal nicht klappt. Vielleicht sehen wir uns trotzdem beim nächsten Heimspiel!\n\nSportliche Grüße\nSV Amisia Wolthusen")
    cfg = smtp_config()
    mail_err = None
    if cfg["smtp_host"]:
        mail_err = send_mail(cfg, o["email"], f"Stornierung deiner Bestellung {o['order_no']}: Dauerkarte SV Amisia Wolthusen", body, footer=False)
        if club and by == "Kunde":
            threading.Thread(target=lambda: send_mail(cfg, club, f"Dauerkarte: Bestellung {o['order_no']} storniert",
                                                      f"{o['buyer']} hat die Bestellung {o['order_no']} über den Link storniert.\n\n" + card_order_summary(o),
                                                      footer=False), daemon=True).start()
    else:
        mail_err = "Kein E-Mail-Versand eingerichtet, der Kunde hat keine Stornobestätigung bekommen."
    if by == "Kunde":
        notify_async("card_order", f"Dauerkarte: {o['order_no']} storniert", f"{o['buyer']} hat die Bestellung storniert.\n\n" + card_order_summary(o))
    with db() as conn:
        audit(conn, user, "Stornobestätigung verschickt" if not mail_err else "Stornobestätigung nicht verschickt", "card_orders", oid, o["order_no"],
              {"An": o["email"], "Fehler": mail_err or ""})
    return o, None, (f"Storniert, aber die Bestätigung an den Kunden ging nicht raus ({mail_err})." if mail_err and cfg["smtp_host"] else mail_err)


def invoice_next(conn):
    """Fortlaufende Rechnungsnummer je Jahr (RE-2027-0001), eine gemeinsame Folge für alle Rechnungen (Dauerkarte und Sponsoren).
    Erst hochzählen, dann lesen: das UPDATE sperrt die Datenbank, zwei gleichzeitige Rechnungen bekommen nie dieselbe Nummer.
    Schon vergebene Nummern (z. B. nach einem Zurücksetzen des Zählers) werden übersprungen."""
    year, key = datetime.now().year, f"inv_counter_{datetime.now().year}"
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, '0')", (key,))
    while True:
        conn.execute("UPDATE settings SET value = CAST(IFNULL(value, '0') AS INTEGER) + 1 WHERE key=?", (key,))
        num = f"RE-{year}-{int(conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()[0]):04d}"
        if not (conn.execute("SELECT 1 FROM card_orders WHERE invoice_no=?", (num,)).fetchone()
                or conn.execute("SELECT 1 FROM sponsor_invoices WHERE number=?", (num,)).fetchone()):
            return num


def pdf_text(s):
    s = str(s).encode("cp1252", "replace").decode("cp1252")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_width(s, size, bold=False):
    """Genäherte Textbreite in Helvetica (Tausendstel der Schriftgröße je Zeichen)."""
    narrow, wide = set("iljtfI.,:;'!|()[] "), set("mwMW")
    w = 0
    for ch in s:
        w += (278 if ch in narrow else 833 if ch in wide else 556 if ch.isdigit() or ch in "€-+" else
              667 if ch.isupper() else 500 if ch.islower() or ch in "äöüß" else 556)
    return w * size / 1000 * (1.06 if bold else 1)


class PdfPage:
    """Eine A4-Seite als PDF ohne Zusatzprogramme (Helvetica, cp1252 für Umlaute und €)."""
    W, H = 595, 842

    def __init__(self):
        self.ops = []

    def txt(self, x, y, s, size=10, bold=False, right=False, color=None, center=False):
        s = str(s)
        if right:   # Breite für rechtsbündigen Text (Helvetica, genäherte Zeichenbreiten)
            x -= pdf_width(s, size, bold)
        if center:
            x -= pdf_width(s, size, bold) / 2
        rgb = color or (0.08, 0.08, 0.08)
        self.ops.append(f"BT {rgb[0]} {rgb[1]} {rgb[2]} rg /{'F2' if bold else 'F1'} {size} Tf {x:.1f} {y:.1f} Td ({pdf_text(s)}) Tj ET")

    def line(self, x1, y1, x2, y2, w=0.6, rgb=(0.75, 0.75, 0.75)):
        self.ops.append(f"{w} w {rgb[0]} {rgb[1]} {rgb[2]} RG {x1} {y1} m {x2} {y2} l S")

    def rect(self, x, y, w, h, rgb):
        self.ops.append(f"{rgb[0]} {rgb[1]} {rgb[2]} rg {x} {y} {w} {h} re f")

    def logo(self, x, y, w, h):
        """Vereinslogo des Briefpapiers (web/assets/brief/logo.png), unten links bei x, y."""
        if letter_logo():
            self.ops.append(f"q {w:.1f} 0 0 {h:.1f} {x:.1f} {y:.1f} cm /Logo Do Q")
            self.uses_logo = True

    def wrap(self, x, y, text, size=10, width=None, lead=None, bold=False, color=None):
        """Absatz mit Zeilenumbruch nach Breite; Leerzeilen trennen Absätze. Liefert das neue y."""
        width, lead = width or (self.W - x - 57), lead or size * 1.45
        for para in str(text or "").replace("\r", "").split("\n"):
            if not para.strip():
                y -= lead * 0.6
                continue
            cur = ""
            for wd in para.split():
                if cur and pdf_width(cur + " " + wd, size, bold) > width:
                    self.txt(x, y, cur, size, bold, color=color); y -= lead; cur = wd
                else:
                    cur = (cur + " " + wd).strip()
            if cur:
                self.txt(x, y, cur, size, bold, color=color); y -= lead
        return y

    def render(self):
        return pdf_render([self])


def pdf_render(pages):
    """Mehrere PdfPage-Seiten als ein PDF (gemeinsame Schriften Helvetica und Helvetica-Bold)."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    kids, xobj = [], ""
    if any(getattr(pg, "uses_logo", False) for pg in pages) and letter_logo():
        objs.append(letter_logo())
        xobj = f" /XObject << /Logo {len(objs)} 0 R >>"
    for pg in pages:
        stream = "\n".join(pg.ops).encode("cp1252", "replace")
        pid = len(objs) + 1
        kids.append(f"{pid} 0 R")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pg.W} {pg.H}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >>{xobj} >> /Contents {pid + 1} 0 R >>".encode())
        objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode()
    out, offs = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for i, ob in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + ob + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


MM = 2.835   # Punkte je Millimeter
LETTER_ML, LETTER_MR = 25 * MM, 20 * MM   # Ränder wie die Briefvorlage (links 25 mm, rechts 20 mm)
LETTER = {   # Standard-Briefpapier, überschreibbar über Einstellungen letter_title, letter_sub, letter_return, letter_footer
    "title": "SV AMISIA WOLTHUSEN", "sub": "Sportverein in Emden-Wolthusen seit 1929",
    "return": "SV Amisia Wolthusen e.V. · Folkmar-Allena-Straße 13 · 26725 Emden",
    "footer": "SV Amisia Wolthusen e.V. · Folkmar-Allena-Straße 13 · 26725 Emden · amisia-stern.de · info@amisia-stern.de"}
_LOGO = {}


def letter_text(conn, key):
    return (get_setting(conn, "letter_" + key) or "").strip() or LETTER[key]


def letter_logo():
    """Logo als PDF-Bild (PNG ohne Transparenz, die Daten gehen unverändert mit Flate und PNG-Vorhersage ins PDF). None, wenn es fehlt."""
    if "obj" not in _LOGO:
        _LOGO["obj"] = None
        try:
            b = (BASE / "web" / "assets" / "brief" / "logo.png").read_bytes()
            w, h, bd, ct, _, _, il = struct.unpack(">IIBBBBB", b[16:29])
            if b[:8] == b"\x89PNG\r\n\x1a\n" and bd == 8 and ct in (0, 2) and not il:
                idat, i = b"", 8
                while i + 8 <= len(b):
                    n, typ = struct.unpack(">I4s", b[i:i + 8])
                    if typ == b"IDAT":
                        idat += b[i + 8:i + 8 + n]
                    i += 12 + n
                col = 3 if ct == 2 else 1
                _LOGO["obj"] = (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /{'DeviceRGB' if col == 3 else 'DeviceGray'} "
                                f"/BitsPerComponent 8 /Filter /FlateDecode /DecodeParms << /Predictor 15 /Colors {col} /BitsPerComponent 8 /Columns {w} >> "
                                f"/Length {len(idat)} >>\nstream\n").encode() + idat + b"\nendstream"
        except (OSError, struct.error):
            pass
    return _LOGO["obj"]


def letterhead(pg, conn, sub=None, page=None):
    """Briefkopf und Fuß auf eine Seite: Logo links, Name rechts, schwarze Linie; unten graue Linie mit Anschrift.
    sub: zweite Fußzeile (z. B. Bank und Steuernummer), page: (links, rechts) für Seitenangaben."""
    W, H, L, R, grey = pg.W, pg.H, LETTER_ML, pg.W - LETTER_MR, (0.33, 0.33, 0.33)
    pg.logo(L, H - 28 * MM, 16 * MM, 18 * MM)   # Wappen 400 x 450 px
    pg.txt(R, H - 17 * MM, letter_text(conn, "title"), 16, True, right=True)
    pg.txt(R, H - 22.5 * MM, letter_text(conn, "sub"), 9, right=True, color=grey)
    pg.line(L, H - 31 * MM, R, H - 31 * MM, 1.5, (0, 0, 0))
    pg.line(L, 20 * MM, R, 20 * MM, 0.75, (0.6, 0.6, 0.6))
    pg.txt((L + R) / 2, 15.5 * MM, letter_text(conn, "footer"), 8, center=True, color=grey)
    if sub:
        pg.txt((L + R) / 2, 11.5 * MM, sub, 7.5, center=True, color=grey)
    if page:
        pg.txt(L, 11.5 * MM, page[0], 7.5, color=grey)
        pg.txt(R, 11.5 * MM, page[1], 7.5, right=True, color=grey)


def letter_address(pg, conn, lines):
    """Rücksendezeile (klein, grau, unterstrichen) und Anschrift im Fenster (DIN 5008 Form B, ab 45 mm von oben)."""
    ret, H, L = letter_text(conn, "return"), pg.H, LETTER_ML
    pg.txt(L, H - 50 * MM, ret, 8, color=(0.47, 0.47, 0.47))
    pg.line(L, H - 50 * MM - 1.6, L + pdf_width(ret, 8), H - 50 * MM - 1.6, 0.4, (0.47, 0.47, 0.47))
    y = H - 58 * MM
    for s in lines:
        if str(s or "").strip():
            pg.txt(L, y, s, 11); y -= 14


CONTRACT_TAX = {"zzgl": "zuzüglich der gesetzlichen Umsatzsteuer", "inkl": "einschließlich der gesetzlichen Umsatzsteuer",
                "ku": "Der Verein ist Kleinunternehmer im Sinne von § 19 UStG, Umsatzsteuer wird daher nicht berechnet"}
CONTRACT_PAY = {"einmal": "in einer Summe", "zwei": "in zwei gleichen Raten, die erste zu Beginn und die zweite zur Mitte der Laufzeit",
                "jahr": "jährlich im Voraus, jeweils zu Beginn eines Vertragsjahres"}


def contract_clean(d, conn):
    """Eingaben für einen Sponsoringvertrag prüfen. Liefert (daten, fehler)."""
    from decimal import Decimal, InvalidOperation
    t = lambda k, n: str(d.get(k) or "").replace("\r", "").strip()[:n]
    sid = int(d["sponsor_id"]) if str(d.get("sponsor_id") or "").isdigit() else 0
    if not sid or not conn.execute("SELECT 1 FROM sponsors WHERE id=?", (sid,)).fetchone():
        return None, "Bitte einen Sponsor auswählen."
    out = {"sponsor_id": sid, "partner_name": t("partner_name", 200), "partner_address": t("partner_address", 500), "partner_rep": t("partner_rep", 200),
           "club_rep": t("club_rep", 200), "special": t("special", 4000), "place": t("place", 80) or "Emden", "court": t("court", 80) or "Emden",
           "tax": t("tax", 10), "pay": t("pay", 10), "renew": bool(d.get("renew")), "kind": t("kind", 10) or "geld",
           "services": [x.strip()[:300] for x in str(d.get("services") or "").split("\n") if x.strip()][:40],
           "inkind": [x.strip()[:300] for x in str(d.get("inkind") or "").split("\n") if x.strip()][:20]}
    ids = [int(x) for x in (d.get("package_ids") or []) if str(x).isdigit()][:10] if isinstance(d.get("package_ids"), list) else []
    rows = {r["id"]: r["name"] for r in conn.execute(f"SELECT id, name FROM sponsor_packages WHERE id IN ({','.join('?' * len(ids)) or 'NULL'})", ids)}
    out["package_ids"] = [i for i in ids if i in rows]
    out["packages"] = [rows[i] for i in out["package_ids"]]
    if not out["partner_name"] or not out["partner_address"]:
        return None, "Bitte Name und Anschrift des Sponsors eintragen."
    if not out["club_rep"]:
        return None, "Bitte eintragen, wer den Verein vertritt (zum Beispiel Name und Vorstandsamt)."
    if not out["services"]:
        return None, "Bitte mindestens eine Leistung des Vereins eintragen (eine pro Zeile)."
    if out["pay"] not in CONTRACT_PAY:
        return None, "Bitte die Zahlungsweise auswählen."
    try:
        start, end = date.fromisoformat(t("start", 10)), date.fromisoformat(t("end", 10))
    except ValueError:
        return None, "Bitte Beginn und Ende der Laufzeit als Datum eintragen."
    if end <= start:
        return None, "Das Ende der Laufzeit muss nach dem Beginn liegen."
    out["start"], out["end"] = start.isoformat(), end.isoformat()
    raw = re.sub(r"[^\d,.]", "", t("amount", 20))
    raw = raw.replace(".", "").replace(",", ".") if "," in raw else (raw.replace(".", "") if re.fullmatch(r"\d{1,3}(\.\d{3})+", raw) else raw)
    try:
        amount = Decimal(raw).quantize(Decimal("0.01"))
    except InvalidOperation:
        amount = Decimal(0)
    if out["kind"] not in ("geld", "sach", "beides"):
        return None, "Bitte die Art des Sponsorings wählen."
    if out["kind"] == "sach":   # reines Sachsponsoring: kein Geld, keine Steuerregel
        amount, out["tax"] = Decimal("0.00"), ""
    elif out["kind"] == "geld":
        out["inkind"] = []
    if out["kind"] != "geld" and not out["inkind"]:
        return None, "Bitte mindestens eine Sachleistung des Sponsors eintragen (eine pro Zeile)."
    if not 0 <= amount < 10000000 or (out["kind"] != "sach" and amount == 0):
        return None, "Bitte den Geldbetrag in Euro eintragen (zum Beispiel 1.500,00)."
    if amount > 0 and out["tax"] not in CONTRACT_TAX:
        return None, "Bitte auswählen, wie die Umsatzsteuer behandelt wird."
    out["amount"] = str(amount)
    try:
        out["notice"] = min(12, max(1, int(d.get("notice") or 3)))
    except (TypeError, ValueError):
        out["notice"] = 3
    sender = [x.strip() for x in (get_setting(conn, "inv_sender") or "").split("\n") if x.strip()]
    if not sender or any("[" in x for x in sender):
        return None, "Bitte zuerst die Anschrift des Vereins eintragen: Dauerkarte > Einstellungen > Absender auf Rechnungen."
    return out, ""


def money_de(v):
    whole, cents = f"{float(v):.2f}".split(".")
    return f"{int(whole):,}".replace(",", ".") + "," + cents + " EUR"


def sponsor_contract_pdf(d, number, conn):
    """Sponsoringvertrag als PDF (mehrere Seiten). Vorlage nach deutschem Recht, keine Rechtsberatung."""
    club = get_setting(conn, "club_name") or "SV Amisia Wolthusen"
    sender = [x.strip() for x in (get_setting(conn, "inv_sender") or "").split("\n") if x.strip()]
    bank = {k: (get_setting(conn, "inv_" + k) or "").strip() for k in ("account_holder", "iban", "bic", "bank", "due_days")}
    due = bank["due_days"] if bank["due_days"].isdigit() else "14"
    M, W, red, grey = LETTER_ML, PdfPage.W - LETTER_ML - LETTER_MR, (0.70, 0.07, 0.11), (0.42, 0.42, 0.42)
    pages, st = [], {}

    def new_page():
        pg = PdfPage(); pages.append(pg); st["pg"], st["y"] = pg, PdfPage.H - 42 * MM   # unter dem Briefkopf

    def lines(text, size, width, bold=False):
        out = []
        for para in str(text).split("\n"):
            cur = ""
            for wd in para.split():
                if cur and pdf_width(cur + " " + wd, size, bold) > width:
                    out.append(cur); cur = wd
                else:
                    cur = (cur + " " + wd).strip()
            out.append(cur)
        return out

    def need(h):
        if st["y"] - h < 27 * MM:   # über dem Fuß des Briefpapiers
            new_page()

    def text(t, size=10, bold=False, x=0, gap=3, color=None):
        for ln in lines(t, size, W - x, bold):
            need(size * 1.5); st["pg"].txt(M + x, st["y"], ln, size, bold, color=color); st["y"] -= size * 1.5
        st["y"] -= gap

    def head(t):
        st["y"] -= 8; need(70)
        st["pg"].txt(M, st["y"], t, 11.5, True); st["y"] -= 18

    def item(no, t):
        ls = lines(t, 10, W - 22)
        for i, ln in enumerate(ls):
            need(15)
            if i == 0 and no:
                st["pg"].txt(M, st["y"], no, 10)
            st["pg"].txt(M + 22, st["y"], ln, 10); st["y"] -= 15
        st["y"] -= 4

    def bullet(t):
        for i, ln in enumerate(lines(t, 10, W - 36)):
            need(15)
            if i == 0:
                st["pg"].txt(M + 24, st["y"], "\u2022", 10, color=red)
            st["pg"].txt(M + 36, st["y"], ln, 10); st["y"] -= 15

    fd = lambda iso: date.fromisoformat(iso).strftime("%d.%m.%Y")
    new_page()
    pg = st["pg"]
    pg.rect(M, st["y"] + 14, 46, 3, red)
    pg.txt(M, st["y"] - 14, "Sponsoringvertrag", 22, True); st["y"] -= 34
    pg.txt(M, st["y"], f"Vertragsnummer {number}", 10, color=grey); st["y"] -= 30
    text("zwischen", 10, color=grey, gap=4)
    for ln in sender:
        text(ln, 10, bold=ln == sender[0], gap=0)
    text(f"vertreten durch {d['club_rep']}", 10, gap=2)
    text("nachfolgend „Verein“", 10, color=grey, gap=12)
    text("und", 10, color=grey, gap=4)
    text(d["partner_name"], 10, bold=True, gap=0)
    for ln in d["partner_address"].split("\n"):
        if ln.strip():
            text(ln.strip(), 10, gap=0)
    if d["partner_rep"]:
        text(f"vertreten durch {d['partner_rep']}", 10, gap=2)
    text("nachfolgend „Sponsor“", 10, color=grey, gap=8)

    n = 0
    def sec(title):
        nonlocal n
        n += 1
        head(f"§ {n} {title}")
    sec("Vertragsgegenstand")
    item("(1)", f"Der Sponsor unterstützt den Verein „{club}“ finanziell. Der Verein erbringt dafür die in § 2 genannten Werbe- und Kommunikationsleistungen.")
    item("(2)", "Der Sponsor erhält durch diesen Vertrag keinen Einfluss auf die sportliche und organisatorische Arbeit des Vereins.")
    sec("Leistungen des Vereins")
    pk = d.get("packages") or []
    item("(1)", "Der Verein erbringt während der Vertragslaufzeit folgende Leistungen"
         + (f" ({'Sponsorenpaket' if len(pk) == 1 else 'Sponsorenpakete'} {', '.join(pk)})" if pk else "") + ":")
    for x in d["services"]:
        bullet(x)
    st["y"] -= 4
    item("(2)", "Art, Größe und Platzierung der Werbung stimmen die Parteien vorab ab. Der Verein darf Werbemittel ablehnen, die gegen gesetzliche Vorschriften, die guten Sitten, die Satzung des Vereins oder die Bestimmungen der zuständigen Sportverbände verstoßen.")
    item("(3)", "Fallen einzelne Leistungen aus Gründen aus, die der Verein nicht zu vertreten hat, insbesondere bei Absage oder Verlegung von Spielen, behördlichen Anordnungen oder höherer Gewalt, bemühen sich die Parteien um eine gleichwertige Ersatzleistung. Eine Minderung der Zahlung ist nur möglich, wenn der Zweck des Vertrags dadurch wesentlich beeinträchtigt wird.")
    item("(4)", "Der Verein schuldet keinen bestimmten sportlichen Erfolg, keine bestimmte Zuschauerzahl und keine bestimmte Reichweite in den Medien.")
    sec("Leistungen des Sponsors")
    k = iter(range(1, 20))
    if float(d["amount"]) > 0:
        tax = f"{money_de(d['amount'])}. {CONTRACT_TAX['ku']}." if d["tax"] == "ku" else f"{money_de(d['amount'])} {CONTRACT_TAX[d['tax']]}."
        item(f"({next(k)})", f"Der Sponsor zahlt dem Verein für die gesamte Vertragslaufzeit einen Betrag von {tax}")
        acc = (f" auf das Konto des Vereins: Kontoinhaber {bank['account_holder'] or sender[0]}, IBAN {bank['iban']}"
               + (f", BIC {bank['bic']}" if bank["bic"] else "") + (f", {bank['bank']}" if bank["bank"] else "")) if bank["iban"] else " auf das in der Rechnung genannte Konto des Vereins"
        item(f"({next(k)})", f"Die Zahlung erfolgt {CONTRACT_PAY[d['pay']]}, {'' if d['pay'] == 'einmal' else 'jeweils '}innerhalb von {due} Tagen nach Erhalt einer ordnungsgemäßen Rechnung,{acc}.")
    if d.get("inkind"):
        item(f"({next(k)})", ("Zusätzlich" if float(d["amount"]) > 0 else "Als Gegenleistung") + " erbringt der Sponsor folgende Sachleistungen:")
        for x in d["inkind"]:
            bullet(x)
        st["y"] -= 4
        item(f"({next(k)})", "Die Sachleistungen sind Teil der Gegenleistung für die Leistungen des Vereins nach § 2. Sie werden rechtzeitig und in gebrauchsfähigem Zustand übergeben. "
                             "Soweit nichts anderes vereinbart ist, gehen sie mit der Übergabe in das Eigentum des Vereins über. Eine Zuwendungsbestätigung (Spendenquittung) wird dafür nicht ausgestellt.")
    item(f"({next(k)})", "Der Sponsor stellt dem Verein Logos und Werbemittel rechtzeitig, kostenfrei und in druck- und digital geeigneter Form zur Verfügung.")
    sec("Laufzeit und Kündigung")
    item("(1)", f"Der Vertrag beginnt am {fd(d['start'])} und endet am {fd(d['end'])}.")
    item("(2)", f"Er verlängert sich jeweils um ein Jahr, wenn er nicht von einer Partei mit einer Frist von {d['notice']} {'Monat' if d['notice'] == 1 else 'Monaten'} zum Ende der Laufzeit gekündigt wird."
         if d["renew"] else "Er endet mit Ablauf der Laufzeit, ohne dass es einer Kündigung bedarf.")
    item("(3)", "Das Recht beider Parteien zur außerordentlichen Kündigung aus wichtigem Grund bleibt unberührt. Ein wichtiger Grund liegt insbesondere vor, wenn eine Partei durch ihr Verhalten das Ansehen der anderen Partei erheblich schädigt, oder für den Verein, wenn der Sponsor mit einer fälligen Zahlung trotz Mahnung länger als 30 Tage in Verzug ist.")
    item("(4)", "Kündigungen bedürfen der Textform (zum Beispiel E-Mail).")
    sec("Nutzungsrechte")
    item("(1)", "Der Sponsor räumt dem Verein für die Dauer des Vertrags das einfache, nicht übertragbare und unentgeltliche Recht ein, Namen, Logos und Marken des Sponsors für die Leistungen nach § 2 zu nutzen. Der Sponsor versichert, dass er über diese Rechte verfügt, und stellt den Verein von Ansprüchen Dritter frei, die auf einer Verletzung dieser Rechte beruhen.")
    item("(2)", f"Der Sponsor darf während der Laufzeit mit dem Hinweis „Sponsor der {club}“ werben. Die Nutzung von Logos und Marken des Vereins bedarf der vorherigen Zustimmung des Vereins in Textform.")
    item("(3)", "Nach Vertragsende werden keine neuen Werbemittel mit den Zeichen der anderen Partei veröffentlicht. Bereits veröffentlichte Beiträge, Berichte und gedruckte Werbemittel müssen nicht entfernt werden.")
    sec("Haftung")
    item("(1)", "Die Parteien haften unbeschränkt für Vorsatz und grobe Fahrlässigkeit sowie für Schäden aus der Verletzung des Lebens, des Körpers oder der Gesundheit.")
    item("(2)", "Bei leichter Fahrlässigkeit haften die Parteien nur bei Verletzung einer wesentlichen Vertragspflicht, deren Erfüllung die ordnungsgemäße Durchführung des Vertrags erst ermöglicht, und begrenzt auf den vertragstypischen, vorhersehbaren Schaden.")
    sec("Datenschutz")
    item("", "Die Parteien verarbeiten personenbezogene Daten ihrer Ansprechpartner nur, soweit dies zur Durchführung dieses Vertrags erforderlich ist (Art. 6 Abs. 1 lit. b und f DSGVO), und beachten die geltenden Vorschriften zum Datenschutz.")
    if d["special"]:
        sec("Sondervereinbarungen")
        item("", d["special"])
    sec("Schlussbestimmungen")
    item("(1)", "Mündliche Nebenabreden bestehen nicht. Änderungen und Ergänzungen dieses Vertrags bedürfen der Textform.")
    item("(2)", "Es gilt das Recht der Bundesrepublik Deutschland.")
    item("(3)", f"Ist der Sponsor Kaufmann, eine juristische Person des öffentlichen Rechts oder ein öffentlich-rechtliches Sondervermögen, ist Gerichtsstand {d['court']}.")
    item("(4)", "Sollte eine Bestimmung dieses Vertrags unwirksam sein oder werden, bleibt die Wirksamkeit der übrigen Bestimmungen unberührt. An die Stelle der unwirksamen Bestimmung tritt die gesetzliche Regelung.")
    item("(5)", "Der Vertrag wird zweifach ausgefertigt. Jede Partei erhält ein unterschriebenes Exemplar.")

    st["y"] -= 26; need(140)
    pg, y, half = st["pg"], st["y"], W / 2 + 10
    for x, who, name in ((M, "Für den Verein", d["club_rep"]), (M + half, "Für den Sponsor", d["partner_rep"] or d["partner_name"])):
        pg.txt(x, y, f"{d['place'] if x == M else ''}{', den' if x == M else 'Ort, Datum'}", 9, color=grey)
        pg.line(x, y - 46, x + W / 2 - 20, y - 46, 0.8, (0.2, 0.2, 0.2))
        pg.txt(x, y - 60, who, 9, True)
        for i, ln in enumerate(lines(name, 9, W / 2 - 24)[:2]):
            pg.txt(x, y - 73 - i * 12, ln, 9, color=grey)
    for i, p in enumerate(pages, 1):
        letterhead(p, conn, page=(f"Sponsoringvertrag {number}", f"Seite {i} von {len(pages)}"))
    return pdf_render(pages)


VAT_RATE = 19   # Regelsteuersatz für Werbeleistungen (Sponsoring)


def sponsor_invoice_sums(amount, tax):
    """Netto, Umsatzsteuer und Brutto (Decimal) nach der Steuerregel des Vertrags (zzgl, inkl, ku)."""
    from decimal import Decimal, ROUND_HALF_UP
    a, c = Decimal(str(amount)), Decimal("0.01")
    if tax == "zzgl":
        net = a.quantize(c, ROUND_HALF_UP); vat = (net * VAT_RATE / 100).quantize(c, ROUND_HALF_UP); return net, vat, net + vat
    if tax == "inkl":
        gross = a.quantize(c, ROUND_HALF_UP); net = (gross * 100 / (100 + VAT_RATE)).quantize(c, ROUND_HALF_UP); return net, gross - net, gross
    return a.quantize(c, ROUND_HALF_UP), Decimal("0.00"), a.quantize(c, ROUND_HALF_UP)


def sponsor_invoice_pdf(inv, conn):
    """Rechnung an einen Sponsor auf dem Briefpapier (Pflichtangaben nach § 14 UStG, Kleinunternehmer mit Hinweis nach § 19 UStG)."""
    pg = PdfPage()
    txt, line, mm, L, R, grey = pg.txt, pg.line, MM, LETTER_ML, pg.W - LETTER_MR, (0.4, 0.4, 0.4)
    tax_no = (get_setting(conn, "inv_tax_no") or "").strip()
    b = card_bank(conn)
    holder = b.get("account_holder") or ""
    letterhead(pg, conn, sub=" · ".join(x for x in (f"Steuernummer {tax_no}" if tax_no else "", f"IBAN {b['iban']}" if b["iban"] else "",
                                                     f"BIC {b['bic']}" if b["bic"] else "", b["bank"]) if x))
    letter_address(pg, conn, [inv["partner_name"]] + [x.strip() for x in inv["partner_address"].split("\n") if x.strip()])
    meta = [("Rechnungsnummer", inv["number"]), ("Rechnungsdatum", fmt_de(inv["date"])), ("Vertrag", inv["contract"]),
            ("Leistungszeitraum", f"{fmt_de(inv['start'])} bis {fmt_de(inv['end'])}"), ("Fällig am", fmt_de(inv["due"]))]
    y = 842 - 58 * mm
    for k, v in meta:
        txt(122 * mm, y, k, 9, color=grey); txt(R, y, v, 9, right=True); y -= 13
    txt(L, 842 - 98 * mm, "Rechnung", 18, True)
    y = pg.wrap(L, 842 - 106 * mm, "Sehr geehrte Damen und Herren,\nvielen Dank für Ihre Unterstützung. Für das Sponsoring berechnen wir Ihnen vereinbarungsgemäß:", 10, width=R - L, lead=14) - 8
    txt(L, y, "Pos.", 9, True); txt(L + 30, y, "Beschreibung", 9, True); txt(R, y, "Betrag", 9, True, right=True)
    y -= 6; line(L, y, R, y); y -= 16
    net, vat, gross = sponsor_invoice_sums(inv["amount"], inv["tax"])
    first = True
    for ln in [x for x in inv["text"].split("\n") if x.strip()] or ["Sponsoring"]:
        yy = pg.wrap(L + 30, y, ln, 10 if first else 9, width=R - L - 120, lead=13, color=None if first else grey)
        if first:
            txt(L, y, "1", 10); txt(R, y, eur_text(float(net if inv["tax"] != "ku" else gross)), 10, right=True)
        y, first = yy, False
    y -= 4; line(L, y, R, y); y -= 16
    if inv["tax"] == "ku":
        txt(300, y, "Gesamtbetrag", 11, True); txt(R, y, eur_text(float(gross)), 11, True, right=True); y -= 22
        y = pg.wrap(L, y, "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet (Kleinunternehmer).", 9, width=R - L, lead=12) - 6
    else:
        txt(300, y, "Nettobetrag", 10); txt(R, y, eur_text(float(net)), 10, right=True); y -= 14
        txt(300, y, f"Umsatzsteuer {VAT_RATE} %", 10); txt(R, y, eur_text(float(vat)), 10, right=True); y -= 6
        line(300, y, R, y); y -= 15
        txt(300, y, "Gesamtbetrag", 11, True); txt(R, y, eur_text(float(gross)), 11, True, right=True); y -= 24
    acc = (f" auf das Konto {('von ' + holder + ', ') if holder else ''}IBAN {b['iban']}" + (f", BIC {b['bic']}" if b["bic"] else "")) if b["iban"] else ""
    y = pg.wrap(L, y, f"Bitte überweisen Sie den Gesamtbetrag bis zum {fmt_de(inv['due'])} unter Angabe der Rechnungsnummer {inv['number']}{acc}.", 10, width=R - L, lead=14) - 10
    y = pg.wrap(L, y, "Mit sportlichen Grüßen", 10, width=R - L, lead=14) - 2
    txt(L, y, get_setting(conn, "club_name") or "SV Amisia Wolthusen", 10, True); y -= 13
    txt(L, y, letter_text(conn, "sub"), 9, color=grey)
    return pg.render()


def assign_card_numbers(conn):
    """Bezahlte Karten ohne Nummer bekommen automatisch die nächste Kartennummer (00001, 00002, ...). Liefert die vergebenen Nummern."""
    todo = conn.execute("SELECT id FROM supporter_cards WHERE IFNULL(paid, 0)=1 AND TRIM(IFNULL(number, ''))='' ORDER BY id").fetchall()
    if not todo:
        return []
    used = [int(r["number"]) for r in conn.execute("SELECT number FROM supporter_cards") if str(r["number"] or "").strip().isdigit()]
    n = max(used + [int(get_setting(conn, "card_counter") or 0)])
    out = []
    for r in todo:
        n += 1
        conn.execute("UPDATE supporter_cards SET number=? WHERE id=?", (f"{n:05d}", r["id"]))
        out.append(f"{n:05d}")
    set_setting(conn, "card_counter", n)
    return out


def card_letter_pdf(o, conn):
    """Fanbrief zum Ausdrucken für den Umschlag mit den Karten (Briefpapier wie die Vorlage, Anschrift im Fenster DIN lang, DIN 5008 Form B)."""
    pg = PdfPage()
    mm, red, L, R = MM, (0.70, 0.07, 0.11), LETTER_ML, pg.W - LETTER_MR
    letterhead(pg, conn)
    letter_address(pg, conn, [o["buyer"]] + ([o["street"], f"{o['zip']} {o['city']}"] if o["delivery"] in CARD_SHIPS else []))
    pg.txt(R, 842 - 92 * mm, f"Emden, {datetime.now().strftime('%d.%m.%Y')}", 10, right=True)   # direkt unter dem Fenster (Anschriftfeld 45 bis 90 mm)
    text = (get_setting(conn, "card_letter_text") or DEFAULT_SETTINGS["card_letter_text"]).strip()
    first = (o["buyer"] or "").split()[0] if (o["buyer"] or "").strip() else ""
    text = text.replace("{Name}", first or "liebe Supporterin, lieber Supporter").replace("{Saison}", str(o["season"] or ""))
    pg.txt(L, 842 - 98 * mm, f"Deine Dauerkarte {o['season'] or ''}".strip(), 11, True)
    y = pg.wrap(L, 842 - 106 * mm, text, 11, width=R - L, lead=16)
    y -= 8
    pg.txt(L, y, "Sportliche Grüße", 11); y -= 16
    pg.txt(L, y, get_setting(conn, "club_name") or "SV Amisia Wolthusen", 11, True); y -= 14
    pg.txt(L, y, letter_text(conn, "sub"), 10, color=(0.33, 0.33, 0.33)); y -= 30   # Absender: der Verein
    # Karten mit Nummer und Name
    cards = conn.execute("SELECT number, holder FROM supporter_cards WHERE order_id=? ORDER BY id", (o["id"],)).fetchall()
    if cards:
        pg.rect(L, y - 6, R - L, 20, (0.08, 0.08, 0.08))
        pg.txt(L + 10, y, f"Deine Dauerkarte{'n' if len(cards) > 1 else ''} {o['season'] or ''}", 10, True, color=(1, 1, 1)); y -= 22
        for c in cards:
            pg.txt(L + 10, y, f"Nr. {c['number']}" if c["number"] else "Nr. folgt", 10, True, color=red)
            pg.txt(L + 90, y, c["holder"] or "", 10); y -= 15
        y -= 14
    today = datetime.now().date().isoformat()
    games = conn.execute("SELECT g.date, g.time, g.location, op.name FROM games g LEFT JOIN opponents op ON op.id=g.opponent_id "
                         "WHERE IFNULL(g.team, 'Erste Herren')='Erste Herren' AND IFNULL(g.home, 1)=1 AND g.date>=? AND (?='' OR IFNULL(g.season, '')=?) "
                         "ORDER BY g.date, g.time LIMIT 8", (today, str(o["season"] or ""), str(o["season"] or ""))).fetchall()
    if games and y > 150:
        pg.txt(L, y, f"Heimspiele der Herren{' in der Saison ' + str(o['season']) if o['season'] else ''}", 11, True, color=red); y -= 17
        for g in games:
            if y < 100:
                break
            pg.txt(L, y, fmt_de(g["date"]) + (f", {g['time']} Uhr" if g["time"] else ""), 10)
            pg.txt(L + 120, y, f"SV Amisia Wolthusen gegen {g['name']}" if g["name"] else "SV Amisia Wolthusen", 10); y -= 14
        pg.txt(L, y - 4, "Alle Termine und Änderungen findest du auf unserer Webseite unter Spielplan.", 8, color=(0.45, 0.45, 0.45))
    return pg.render()


def invoice_pdf(o, conn):
    """Rechnung als PDF auf dem Briefpapier (A4, Helvetica, ohne Zusatzprogramme)."""
    pg = PdfPage()
    txt, line, mm, L, R, grey = pg.txt, pg.line, MM, LETTER_ML, pg.W - LETTER_MR, (0.4, 0.4, 0.4)
    tax_no, tax_note = (get_setting(conn, "inv_tax_no") or "").strip(), (get_setting(conn, "inv_tax_note") or "").strip()
    b = card_bank(conn)
    bank = " · ".join(x for x in (f"Steuernummer {tax_no}" if tax_no else "", f"IBAN {b['iban']}" if b["iban"] else "",
                                   f"BIC {b['bic']}" if b["bic"] else "", b["bank"]) if x)
    letterhead(pg, conn, sub=bank)
    letter_address(pg, conn, [o["buyer"]] + ([o["street"], f"{o['zip']} {o['city']}"] if o["delivery"] in CARD_SHIPS else []))
    # Informationsblock rechts neben der Anschrift (unter der langen Rücksendezeile)
    meta = [("Rechnungsnummer", o["invoice_no"]), ("Rechnungsdatum", fmt_de(o["paid_on"])), ("Bestellnummer", o["order_no"]),
            ("Leistungszeitraum", f"Saison {o['season'] or ''}"), ("Bezahlt am", fmt_de(o["paid_on"]))]
    y = 842 - 58 * mm
    for k, v in meta:
        txt(125 * mm, y, k, 9, color=grey); txt(R, y, v, 9, right=True); y -= 13
    txt(L, 842 - 98 * mm, "Rechnung", 18, True)
    y = 842 - 109 * mm
    txt(L, y, "Pos.", 9, True); txt(L + 30, y, "Beschreibung", 9, True); txt(370, y, "Menge", 9, True); txt(420, y, "Einzel", 9, True); txt(R, y, "Gesamt", 9, True, right=True)
    y -= 6; line(L, y, R, y); y -= 16
    holders = card_holders(o)
    txt(L, y, "1", 10); txt(L + 30, y, f"Dauerkarte Saison {o['season'] or ''}", 10); txt(370, y, str(o["count"]), 10)
    txt(420, y, eur_text(o["price_each"]), 10); txt(R, y, eur_text(o["price_each"] * o["count"]), 10, right=True); y -= 13
    txt(L + 30, y, "Freier Eintritt zu allen Heimspielen der Herren in der Saison", 8, color=grey); y -= 12
    for i in range(0, len(holders), 3):
        txt(L + 30, y, "Karteninhaber: " + ", ".join(holders[i:i + 3]), 8, color=grey); y -= 11
    y -= 6
    if o["delivery"] in CARD_SHIPS:
        txt(L, y, "2", 10); txt(L + 30, y, f"Versand {CARD_SHIPS[o['delivery']]}", 10); txt(370, y, "1", 10); txt(420, y, eur_text(o["shipping"]), 10)
        txt(R, y, eur_text(o["shipping"]), 10, right=True); y -= 18
    line(L, y, R, y); y -= 18
    txt(330, y, "Gesamtbetrag", 11, True); txt(R, y, eur_text(o["total"]), 11, True, right=True); y -= 26
    for part in (tax_note, f"Der Betrag ist am {fmt_de(o['paid_on'])} bei uns eingegangen. Vielen Dank für deine Unterstützung!"):
        if part:
            y = pg.wrap(L, y, part, 9, width=R - L, lead=12) - 4
    return pg.render()


def fmt_de(d):
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)", str(d or ""))
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else ""


def card_order_paid(oid, user):
    """Bestellung als bezahlt markieren: Karten bezahlt, Rechnungsnummer vergeben, PDF ablegen, Rechnung per Mail. Liefert (Bestellung, Fehler)."""
    today = datetime.now().date().isoformat()
    with db() as conn:
        o = conn.execute("SELECT * FROM card_orders WHERE id=?", (oid,)).fetchone()
        if not o:
            return None, "Bestellung nicht gefunden."
        if o["cancelled"]:
            return None, "Diese Bestellung ist storniert."
        if not o["invoice_no"]:
            conn.execute("UPDATE card_orders SET paid=1, paid_on=?, invoice_no=?, updated_at=? WHERE id=?",
                         (o["paid_on"] or today, invoice_next(conn), datetime.now().isoformat(timespec="seconds"), oid))
        else:
            conn.execute("UPDATE card_orders SET paid=1, paid_on=IFNULL(paid_on, ?) WHERE id=?", (today, oid))
        conn.execute("UPDATE supporter_cards SET paid=1 WHERE order_id=?", (oid,))
        nums = assign_card_numbers(conn)
        o = conn.execute("SELECT * FROM card_orders WHERE id=?", (oid,)).fetchone()
        pdf = invoice_pdf(o, conn)
        audit(conn, user, "bezahlt, Rechnung erstellt", "card_orders", oid, f"{o['order_no']} {o['buyer']}",
              {"Rechnung": o["invoice_no"], "Summe": eur_text(o["total"]), "Kartennummern": ", ".join(nums)})
    INVOICE_DIR.mkdir(parents=True, exist_ok=True)
    (INVOICE_DIR / f"{o['invoice_no']}.pdf").write_bytes(pdf)
    return o, card_invoice_send(o, pdf, user)


def card_order_shipped(oid, tracking, user):
    """Bestellung als verschickt markieren und dem Kunden eine Versandbestätigung schicken (beim Einschreiben mit Sendungsnummer).
    Liefert (Bestellung, Fehler für den Hub, Hinweis zur Mail)."""
    tracking = re.sub(r"\s+", "", str(tracking or "")).upper()[:40]
    with db() as conn:
        o = conn.execute("SELECT * FROM card_orders WHERE id=?", (oid,)).fetchone()
        if not o:
            return None, "Bestellung nicht gefunden.", None
        if o["cancelled"]:
            return None, "Diese Bestellung ist storniert.", None
        if o["delivery"] not in CARD_SHIPS:
            return None, "Diese Bestellung wird am Einlass übergeben, nicht verschickt.", None
        if o["delivery"] == "Einschreiben" and not re.fullmatch(r"[A-Z0-9]{8,40}", tracking):
            return None, "Bitte die Sendungsnummer des Einschreibens eintragen (nur Buchstaben und Ziffern).", None
        today = datetime.now().date().isoformat()
        conn.execute("UPDATE card_orders SET delivered=1, shipped_on=?, tracking_no=?, updated_at=? WHERE id=?",
                     (today, tracking if o["delivery"] == "Einschreiben" else "", datetime.now().isoformat(timespec="seconds"), oid))
        o = conn.execute("SELECT * FROM card_orders WHERE id=?", (oid,)).fetchone()
        audit(conn, user, "verschickt", "card_orders", oid, f"{o['order_no']} {o['buyer']}",
              {"Versand": o["delivery"], "Sendungsnummer": o["tracking_no"] or ""})
    cfg = smtp_config()
    if not cfg["smtp_host"]:
        return o, None, "Kein E-Mail-Versand eingerichtet, der Kunde hat keine Versandbestätigung bekommen."
    names = ", ".join(card_holders(o))
    track = (f"\n\nDu hast dich für ein Einschreiben entschieden. Die Sendungsnummer lautet:\n  {o['tracking_no']}\n"
             f"Damit kannst du die Sendung verfolgen: https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?piececode={o['tracking_no']}"
             if o["delivery"] == "Einschreiben" else "")
    body = (f"Hallo {o['buyer']},\n\ndeine Dauerkarte{'n' if o['count'] > 1 else ''} ({o['count']} x, {names}) aus der Bestellung {o['order_no']} "
            f"{'sind' if o['count'] > 1 else 'ist'} heute {CARD_SHIPS[o['delivery']]} an dich rausgegangen:\n\n  {o['buyer']}\n  {o['street']}\n  {o['zip']} {o['city']}"
            f"{track}\n\nFalls die Post in ein paar Tagen noch nicht da ist, melde dich bitte bei uns.\n\nWir sehen uns beim Heimspiel!\nSportliche Grüße\nSV Amisia Wolthusen")
    err = send_mail(cfg, o["email"], f"Deine Dauerkarte ist unterwegs ({o['order_no']})", body, footer=False)
    with db() as conn:
        if not err:
            conn.execute("UPDATE card_orders SET shipped_mail=? WHERE id=?", (datetime.now().isoformat(timespec="seconds"), oid))
        audit(conn, user, "Versandbestätigung verschickt" if not err else "Versandbestätigung nicht verschickt", "card_orders", oid, o["order_no"],
              {"An": o["email"], "Fehler": err or ""})
    return o, None, (f"Als verschickt markiert, die Versandbestätigung konnte aber nicht gesendet werden ({err})." if err else None)


def card_invoice_file(oid):
    """(Bestellung, PDF-Bytes) einer bezahlten Bestellung; fehlt die Datei (z. B. nach Umzug), wird sie gleich wieder erzeugt."""
    with db() as conn:
        o = conn.execute("SELECT * FROM card_orders WHERE id=?", (oid,)).fetchone()
        if not o or not o["invoice_no"]:
            return o, None
        f = INVOICE_DIR / f"{o['invoice_no']}.pdf"
        if f.exists():
            return o, f.read_bytes()
        pdf = invoice_pdf(o, conn)
    INVOICE_DIR.mkdir(parents=True, exist_ok=True)
    f.write_bytes(pdf)
    return o, pdf


def card_invoice_send(o, pdf, user):
    cfg = smtp_config()
    if not cfg["smtp_host"]:
        return "Kein E-Mail-Versand eingerichtet (Einstellungen > E-Mail-Versand). Die Rechnung liegt im Hub zum Herunterladen bereit."
    body = (f"Hallo {o['buyer']},\n\nvielen Dank, dein Betrag für die Bestellung {o['order_no']} ist bei uns eingegangen. "
            f"Im Anhang findest du deine Rechnung {o['invoice_no']}.\n\nSportliche Grüße\nSV Amisia Wolthusen")
    err = send_mail(cfg, o["email"], f"Deine Rechnung {o['invoice_no']}: Dauerkarte SV Amisia Wolthusen", body, footer=False,
                    attachments=[(f"Rechnung {o['invoice_no']}.pdf", pdf, "application", "pdf")])
    if err:
        err = f"Die Rechnung liegt im Hub, die E-Mail konnte aber nicht verschickt werden ({err}). Bitte E-Mail-Versand prüfen und „Rechnung erneut senden“."
    with db() as conn:
        if not err:
            conn.execute("UPDATE card_orders SET invoice_sent=? WHERE id=?", (datetime.now().isoformat(timespec="seconds"), o["id"]))
        audit(conn, user, "Rechnung verschickt" if not err else "Rechnung nicht verschickt", "card_orders", o["id"], o["order_no"], {"An": o["email"], "Fehler": err or ""})
    return err


def public_info():
    with db() as conn:
        return {k: get_setting(conn, k) for k in PUBLIC_SETTINGS}


def public_games():
    key = social_config()["share_key"]
    with db() as conn:
        home_loc = get_setting(conn, "home_location")
        opp = {r["id"]: r for r in conn.execute("SELECT * FROM opponents")}
        spon = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM sponsors WHERE active=1")}
        rows = conn.execute("SELECT * FROM games WHERE IFNULL(date,'') != '' ORDER BY date, time").fetchall()
    out = []
    for g in rows:
        o = opp.get(g["opponent_id"])
        played = g["score_us"] not in (None, "") and g["score_them"] not in (None, "")
        out.append({
            "id": g["id"], "team": g["team"] if g["team"] in TEAMS else MAIN_TEAM, "season": g["season"] or "", "date": g["date"], "time": g["time"] or "", "home": bool(g["home"]), "kind": g["kind"] or "",
            "league": g["league"] or "", "location": g["location"] or (home_loc if g["home"] else ""),
            "opponent": {"name": o["name"] or "", "short": o["short"] or "", "city": o["city"] or "", "logo": public_image(o["logo"], key)} if o else None,
            "score_us": g["score_us"] if played else None, "score_them": g["score_them"] if played else None,
            "sponsor": spon.get(g["sponsor_id"], ""),
            "stream": stream if re.fullmatch(r"https://[^\s\"'<>]+", stream := (g["stream_url"] or "").strip()) else "",
        })
    return out


# ---------------------------------------------------------------- Spielerbogen (/spielerbogen): ersetzt die Google-Tabelle
# Feste Adresse mit Passwort (nur als Hash in secrets.player_form_pw), an/aus im Hub unter Kader & Staff (Verein 2).
# Nach dem richtigen Passwort ein signiertes Cookie (2 Stunden, nur für /spielerbogen); ein neues Passwort macht alte Cookies ungültig.
# Eingänge landen in player_signups und kommen erst mit „Übernehmen“ in den Kader. E-Mail und Telefon bleiben intern.
PLAYER_FORM_COOKIE = "tmh_pf"
PLAYER_FORM_HOURS = 2
PLAYER_FORM_KINDS = ("Spieler", "Coach", "Staff")
PLAYER_FORM_POSITIONS = ("Tor", "Abwehr", "Mittelfeld", "Sturm")   # wie POSITIONS in static/pages/01-grundlagen.js


def player_form_state(conn):
    return {"open": get_setting(conn, "player_form_open") == "1", "has_pw": bool(secret_get(conn, "player_form_pw"))}


def player_form_sig(conn, exp):
    key = secret_get(conn, "player_form_key")
    if not key:
        key = secrets.token_hex(32)
        secret_set(conn, "player_form_key", key)
    return hmac.new(key.encode(), f"{exp}|{secret_get(conn, 'player_form_pw')}".encode(), hashlib.sha256).hexdigest()


def player_form_cookie_ok(conn, value):
    exp, _, sig = (value or "").partition(".")
    if not exp.isdigit() or int(exp) < time.time():
        return False
    return hmac.compare_digest(sig, player_form_sig(conn, exp))


def player_signup_apply(conn, s, target_id, user):
    """Eingang in den Kader übernehmen: bestehende Person ergänzen (nur ausgefüllte Felder) oder neu anlegen."""
    now = datetime.now().isoformat(timespec="seconds")
    kind = s["kind"] if s["kind"] in PLAYER_FORM_KINDS else "Spieler"
    want = {"kind": kind, "first_name": s["first_name"], "last_name": s["last_name"], "nickname": s["nickname"],
            "team": s["team"] if s["team"] in TEAMS else MAIN_TEAM, "instagram": s["instagram"], "email": s["email"], "phone": s["phone"],
            "consent": 1 if s["consent"] else 0, "since": s["since"], "facts": s["facts"]}
    if kind == "Spieler":
        want.update({"number": s["number"], "position": s["position"], "extra_role": s["role"]})
    else:
        want.update({"role": s["role"]})
    p = conn.execute("SELECT * FROM players WHERE id=?", (target_id,)).fetchone() if target_id else None
    if p:
        upd = {k: v for k, v in want.items() if (k == "consent" or v not in (None, "")) and (p[k] if p[k] is not None else "") != v}
        if upd:
            upd["updated_at"] = now
            conn.execute(f"UPDATE players SET {', '.join(f'{k}=?' for k in upd)} WHERE id=?", [*upd.values(), p["id"]])
        pid = p["id"]
        audit(conn, user, "Spielerbogen übernommen", "players", pid, f"{s['first_name']} {s['last_name']}",
              {k: audit_short(v) for k, v in upd.items() if k not in ("updated_at", "email", "phone")})
    else:
        want.update({"active": 1, "source": "Formular", "created_at": now, "updated_at": now})
        pid = conn.execute(f"INSERT INTO players ({', '.join(want)}) VALUES ({', '.join('?' for _ in want)})", list(want.values())).lastrowid
        audit(conn, user, "Spielerbogen als neue Person angelegt", "players", pid, f"{s['first_name']} {s['last_name']}")
    conn.execute("UPDATE player_signups SET status='Übernommen', player_id=?, updated_at=? WHERE id=?", (pid, now, s["id"]))
    if s["user_id"]:   # aus einer Einladung: Konto mit der Person im Kader verknüpfen, falls noch keine gesetzt
        conn.execute("UPDATE users SET player_id=? WHERE id=? AND player_id IS NULL", (pid, s["user_id"]))
    return pid


def public_team():
    """Alle aktiven Spieler und Coaches; Foto nur mit Einwilligung (players.consent).
    Jugendmannschaften (YOUTH_TEAMS, Minderjährige): nur Trainer und Betreuer, keine Spieler."""
    key = social_config()["share_key"]
    with db() as conn:
        rows = conn.execute("SELECT * FROM players WHERE active=1").fetchall()
    out = []
    for p in rows:
        team = p["team"] if p["team"] in TEAMS else MAIN_TEAM
        if team in YOUTH_TEAMS and (p["kind"] or "Spieler") == "Spieler":
            continue
        out.append({
            "team": team, "kind": p["kind"] or "Spieler", "first_name": p["first_name"] or "", "last_name": p["last_name"] or "",
            "number": p["number"] or "", "position": p["position"] or "", "unit": p["unit"] or "", "role": p["role"] or "",
            "extra_role": (p["extra_role"] or "") if (p["kind"] or "Spieler") == "Spieler" else "",
            "photo": public_image(p["photo"], key) if p["consent"] else "",
        })
    return out


def public_trainings():
    """Aktive Trainingszeiten für die Webseite: nur Mannschaft, Tag, Uhrzeit, Ort und Zeitraum (keine Notizen)."""
    order = {d: i for i, d in enumerate(("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"))}
    with db() as conn:
        rows = conn.execute("SELECT * FROM trainings WHERE active=1").fetchall()
    out = [{"team": (r["team"] or "").strip(), "weekday": r["weekday"] if r["weekday"] in order else "", "start": (r["start"] or "")[:5],
            "end": (r["end"] or "")[:5], "place": (r["place"] or "").strip()[:80], "season": (r["season"] or "").strip()[:60]} for r in rows]
    return sorted([t for t in out if t["team"] and t["weekday"]], key=lambda t: (order[t["weekday"]], t["start"]))


def article_slug(a):
    """Adresse eines Artikels: /news/<id>-<titel-ohne-sonderzeichen>. Die Zahl vorne zählt, der Rest ist nur für Leser und Google."""
    t = (a["title"] or "").lower()
    for k, v in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(k, v)
    return f"{a['id']}-" + (re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60].strip("-") or "artikel")


ARTICLE_BLOCKS = {   # Blocktyp -> erlaubte Felder (alles andere wird verworfen)
    "p": ("text",), "h": ("text",), "quote": ("text", "by"), "list": ("items",), "highlight": ("text",),
    "cta": ("text", "label", "link"), "image": ("src", "alt", "caption"), "note": ("text",),
}


def article_blocks(raw, key):
    """Blöcke aus dem Editor prüfen: nur bekannte Typen und Felder, Längen begrenzt, Bilder nur aus der Mediathek (signiert), Links geprüft."""
    try:
        data = json.loads(raw or "[]")
    except ValueError:
        return []
    out = []
    for b in data if isinstance(data, list) else []:
        if not isinstance(b, dict) or b.get("t") not in ARTICLE_BLOCKS:
            continue
        row = {"t": b["t"]}
        for f in ARTICLE_BLOCKS[b["t"]]:
            v = b.get(f)
            if f == "items":
                row[f] = [str(x)[:500] for x in (v if isinstance(v, list) else str(v or "").splitlines()) if str(x).strip()][:30]
            else:
                row[f] = str(v or "").strip()[:4000]
        if row["t"] == "image":
            row["src"] = public_image(row["src"], key)
            if not row["src"]:
                continue
        if row["t"] == "cta":
            link = row["link"]
            row["link"] = link if re.fullmatch(r"(https?://[^\s\"'<>]+|/(?!/)[^\s\"'<>]*|mailto:[^\s\"'<>]+)", link) else ""
        if any(row[f] for f in ARTICLE_BLOCKS[row["t"]]):
            out.append(row)
        if len(out) >= 80:
            break
    return out


def public_articles():
    """Veröffentlichte Artikel ab ihrem Datum, neueste zuerst. Nur feste Felder, keine Notizen."""
    key = social_config()["share_key"]
    today = datetime.now().strftime("%Y-%m-%d")
    with db() as conn:
        rows = conn.execute("SELECT * FROM articles WHERE status='Veröffentlicht' AND IFNULL(date,'') != '' AND date <= ? "
                            "AND IFNULL(title,'') != '' ORDER BY date DESC, id DESC", (today,)).fetchall()
    out = []
    for a in rows:
        fmt = a["format"] if a["format"] in ("Blöcke", "HTML") else "Text"
        blocks = article_blocks(a["body"], key) if fmt == "Blöcke" else []
        body = "\n\n".join(b.get("text", "") for b in blocks if b["t"] in ("p", "h")) if fmt == "Blöcke" else (a["body"] or "")
        out.append(article_public(a, key, fmt, body, blocks))
    return out


def photo_link(v):
    """Link zum Fotografen: https-Adresse oder @instagram-Name, sonst leer."""
    v = (v or "").strip()
    m = re.fullmatch(r"@([A-Za-z0-9._]{1,30})", v)
    if m:
        return f"https://www.instagram.com/{m.group(1)}/"
    if re.fullmatch(r"[A-Za-z0-9.-]+\.[a-z]{2,}(/\S*)?", v):   # z. B. silasgrbwskfotografie.de ohne https://
        v = "https://" + v
    return v if re.fullmatch(r"https://[^\s\"'<>]+", v) else ""


def article_public(a, key, fmt, body, blocks):
    return {"id": a["id"], "slug": article_slug(a), "title": a["title"], "teaser": a["teaser"] or "", "body": body,
            "format": fmt, "blocks": blocks,
            "date": a["date"], "image": public_image(a["image"], key), "image_alt": a["image_alt"] or "",
            "photo_by": (a["photo_by"] or "").strip()[:80], "photo_url": photo_link(a["photo_url"]),
            "team": a["team"] if a["team"] in TEAMS else "", "game_id": a["game_id"] or None}


def public_sponsors():
    key = social_config()["share_key"]
    with db() as conn:
        rows = conn.execute("SELECT * FROM sponsors WHERE active=1 ORDER BY name COLLATE NOCASE").fetchall()
    out = []
    for s in rows:
        web = (s["website"] or "").strip()
        if web and not web.startswith(("http://", "https://")):
            web = "https://" + web
        out.append({"name": s["name"] or "", "package": s["package"] or "", "website": web if re.fullmatch(r"https?://[^\s\"'<>]+", web) else "",
                    "instagram": (s["instagram"] or "").strip().lstrip("@"), "logo": public_image(s["logo"], key)})
    return out


def public_shop():
    """Aktive Fanshop-Produkte für die Startseite: nur Name, Preis, signiertes Bild und geprüfter https-Link."""
    key = social_config()["share_key"]
    with db() as conn:
        rows = conn.execute("SELECT * FROM shop_products WHERE active=1 ORDER BY IFNULL(sort, 0), name COLLATE NOCASE").fetchall()
    out = []
    for r in rows:
        url = (r["url"] or "").strip()
        img = public_image(r["image"], key)
        if not (r["name"] or "").strip() or not img:
            continue
        out.append({"name": r["name"].strip()[:80], "price": (r["price"] or "").strip()[:30], "image": img, "new": bool(r["is_new"]), "colors": bool(r["colors"]),
                    "url": url if re.fullmatch(r"https://[^\s\"'<>]+", url) else ""})
    return out[:24]


def share_sig(key, name):
    return hmac.new(key.encode(), name.encode(), hashlib.sha256).hexdigest()[:40]


def graph(method, path, params=None, token=None, files=None):
    """Aufruf der Graph API. files: {feld: (dateiname, bytes, mime)} wird als multipart gesendet."""
    url = f"{GRAPH}/{path.lstrip('/')}"
    params = {k: v for k, v in (params or {}).items() if v is not None}
    if token:
        params["access_token"] = token
    if method == "GET":
        req = urllib.request.Request(url + "?" + urlencode(params))
    elif files:
        b = uuid.uuid4().hex
        body = io.BytesIO()
        for k, v in params.items():
            body.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'.encode() + str(v).encode() + b"\r\n")
        for k, (fname, data, mime) in files.items():
            body.write(f'--{b}\r\nContent-Disposition: form-data; name="{k}"; filename="{fname}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
            body.write(data + b"\r\n")
        body.write(f"--{b}--\r\n".encode())
        req = urllib.request.Request(url, data=body.getvalue(), method="POST", headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    else:
        req = urllib.request.Request(url, data=urlencode(params).encode(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error", {}).get("message")
        except ValueError:
            msg = None
        raise GraphError(msg or f"Meta antwortet mit Fehler {e.code}")
    except urllib.error.URLError as e:
        raise GraphError(f"Keine Verbindung zu Meta ({e.reason})")


def social_connect(token, public_url):
    """Prüft das Seiten-Token und liest Seite und verknüpftes Instagram-Konto aus."""
    me = graph("GET", "me", {"fields": "id,name"}, token)
    page = graph("GET", me["id"], {"fields": "id,name,instagram_business_account{id,username}"}, token)
    ig = page.get("instagram_business_account") or {}
    with db() as conn:
        secret_set(conn, "fb_token", token)
        secret_set(conn, "fb_page_id", page["id"])
        secret_set(conn, "fb_page_name", page.get("name", ""))
        secret_set(conn, "ig_user_id", ig.get("id", ""))
        secret_set(conn, "ig_username", ig.get("username", ""))
        secret_set(conn, "public_url", (public_url or "").strip().rstrip("/"))
    return {"page": page.get("name", ""), "instagram": ig.get("username", "")}


def media_bytes(path):
    """/media/datei.png -> (name, bytes, mime) oder Fehler."""
    name = (path or "").rsplit("/", 1)[-1]
    f = MEDIA / name
    if not path or not path.startswith("/media/") or not f.is_file():
        raise GraphError("Das Bild wurde nicht gefunden.")
    return name, f.read_bytes(), mimetypes.guess_type(name)[0] or "application/octet-stream"


def check_media(kind, image, media):
    """Prüft, ob die Dateien zum Format passen. kind: feed / story / carousel / reel."""
    ext = lambda p: Path(p or "").suffix.lower()
    if kind == "story" and not image:
        raise GraphError("Für eine Story wird ein Bild gebraucht.")
    if kind == "carousel":
        imgs = [m for m in media if ext(m) in IMAGE_EXT]
        if not 2 <= len(imgs) <= 10 or len(imgs) != len(media):
            raise GraphError("Ein Karussell braucht 2 bis 10 Bilder (JPG oder PNG), keine anderen Dateien.")
    if kind == "reel":
        if len(media) != 1 or ext(media[0]) not in VIDEO_EXT:
            raise GraphError("Ein Reel braucht genau ein Video (MP4 oder MOV).")


def publish_facebook(cfg, kind, image, media, text):
    page, tok = cfg["fb_page_id"], cfg["fb_token"]
    if kind == "story":
        up = graph("POST", f"{page}/photos", {"published": "false"}, tok, {"source": media_bytes(image)})
        res = graph("POST", f"{page}/photo_stories", {"photo_id": up["id"]}, tok)
        return res.get("post_id") or res.get("id") or ""
    if kind == "carousel":   # Beitrag mit mehreren Bildern: erst unveröffentlicht hochladen, dann gemeinsam posten
        ids = [graph("POST", f"{page}/photos", {"published": "false"}, tok, {"source": media_bytes(m)})["id"] for m in media]
        params = {"message": text or "", **{f"attached_media[{i}]": json.dumps({"media_fbid": pid}) for i, pid in enumerate(ids)}}
        return graph("POST", f"{page}/feed", params, tok).get("id", "")
    if kind == "reel":       # Reels-API: Start, Video hochladen, Veröffentlichen
        name, data, _ = media_bytes(media[0])
        start = graph("POST", f"{page}/video_reels", {"upload_phase": "start"}, tok)
        req = urllib.request.Request(start["upload_url"], data=data, method="POST",
                                     headers={"Authorization": f"OAuth {tok}", "offset": "0", "file_size": str(len(data))})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raise GraphError(f"Video-Upload fehlgeschlagen ({e.code})")
        except urllib.error.URLError as e:
            raise GraphError(f"Video-Upload fehlgeschlagen ({e.reason})")
        graph("POST", f"{page}/video_reels", {"upload_phase": "finish", "video_id": start["video_id"],
                                               "video_state": "PUBLISHED", "description": text or ""}, tok)
        return start["video_id"]
    if image:
        res = graph("POST", f"{page}/photos", {"caption": text or "", "published": "true"}, tok, {"source": media_bytes(image)})
        return res.get("post_id") or res.get("id") or ""
    return graph("POST", f"{page}/feed", {"message": text or ""}, tok).get("id", "")


def ig_wait(cfg, box_id, tries=20, delay=3):
    """Instagram verarbeitet Bilder/Videos erst, danach kann veröffentlicht werden."""
    for _ in range(tries):
        st = graph("GET", box_id, {"fields": "status_code"}, cfg["fb_token"]).get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise GraphError("Instagram konnte die Datei nicht verarbeiten (JPG im Format 4:5, Storys 9:16, Reels MP4 hochkant klappen am sichersten).")
        time.sleep(delay)
    raise GraphError("Instagram hat die Datei nicht rechtzeitig verarbeitet. Bitte später „Jetzt posten“ versuchen.")


def publish_instagram(cfg, kind, image, media, text):
    if not cfg["ig_user_id"]:
        raise GraphError("Mit der Facebook-Seite ist kein Instagram-Business-Konto verknüpft.")
    if kind in ("feed", "story") and not image:
        raise GraphError("Instagram braucht ein Bild.")
    if not cfg["public_url"].startswith("https://"):
        raise GraphError("Für Instagram fehlt die öffentliche https-Adresse des Hubs (Auto-Posting > Verbindung).")
    ig, tok = cfg["ig_user_id"], cfg["fb_token"]

    def url(path):
        name = media_bytes(path)[0]
        if Path(name).suffix.lower() not in SHARE_EXT:
            raise GraphError("Instagram kann dieses Dateiformat nicht verarbeiten (Bilder JPG oder PNG, Videos MP4).")
        return f"{cfg['public_url']}/teilen/{share_sig(cfg['share_key'], name)}/{name}"

    if kind == "carousel":
        children = []
        for m in media:
            child = graph("POST", f"{ig}/media", {"image_url": url(m), "is_carousel_item": "true"}, tok)
            ig_wait(cfg, child["id"])
            children.append(child["id"])
        box = graph("POST", f"{ig}/media", {"media_type": "CAROUSEL", "children": ",".join(children), "caption": text or ""}, tok)
        ig_wait(cfg, box["id"])
    elif kind == "reel":
        box = graph("POST", f"{ig}/media", {"media_type": "REELS", "video_url": url(media[0]), "caption": text or ""}, tok)
        ig_wait(cfg, box["id"], tries=40, delay=10)   # Videos brauchen länger
    else:
        params = {"image_url": url(image), "media_type": "STORIES"} if kind == "story" else {"image_url": url(image), "caption": text or ""}
        box = graph("POST", f"{ig}/media", params, tok)
        ig_wait(cfg, box["id"])
    return graph("POST", f"{ig}/media_publish", {"creation_id": box["id"]}, tok).get("id", "")


def social_publish(cfg, kind, image, media, text, targets):
    """Postet auf alle Ziele. Liefert (zustand, protokoll, facebook_id)."""
    t = (targets or "Facebook").lower()
    jobs = [("Facebook", publish_facebook)] if "facebook" in t else []
    jobs += [("Instagram", publish_instagram)] if "instagram" in t else []
    if not jobs:
        return "fehler", "Kein Ziel ausgewählt.", ""
    try:
        check_media(kind, image, media)
    except GraphError as e:
        return "fehler", f"{datetime.now():%d.%m.%Y %H:%M} {e}", ""
    ok, log, fb_id = 0, [], ""
    for label, fn in jobs:
        try:
            rid = fn(cfg, kind, image, media, text)
            ok += 1
            log.append(f"{label}: gepostet")
            if label == "Facebook":
                fb_id = rid
        except GraphError as e:
            log.append(f"{label}: {e}")
        except Exception as e:  # noqa
            log.append(f"{label}: unerwarteter Fehler ({e})")
    state = "gepostet" if ok == len(jobs) else "teilweise" if ok else "fehler"
    return state, f"{datetime.now():%d.%m.%Y %H:%M} " + " | ".join(log), fb_id


POST_KIND = {"Feed": "feed", "Story": "story", "Karussell": "carousel", "Reel": "reel"}


def post_media(post):
    try:
        items = json.loads(post["media"] or "[]")
    except ValueError:
        items = []
    return [i["path"] for i in items if isinstance(i, dict) and i.get("path")]


def publish_post(cfg, post):
    fmt = post["format"] or "Feed"
    state, log, fb_id = social_publish(cfg, POST_KIND.get(fmt, "feed"), post["image"], post_media(post), post["caption"], post["targets"])
    now = datetime.now().isoformat(timespec="seconds")
    with db() as conn:
        conn.execute("UPDATE posts SET publish_state=?, publish_log=?, published_at=?, updated_at=? WHERE id=?",
                     (state, log, now if state != "fehler" else None, now, post["id"]))
        if state != "fehler":
            conn.execute("UPDATE posts SET status='Gepostet' WHERE id=?", (post["id"],))
            if fb_id and fmt != "Story":
                link = f"https://www.facebook.com/reel/{fb_id}" if fmt == "Reel" else f"https://www.facebook.com/{fb_id}"
                conn.execute("UPDATE posts SET posted_url=? WHERE id=? AND IFNULL(posted_url,'')=''", (link, post["id"]))
    return state, log


def publish_rule(cfg, rule):
    state, log, _ = social_publish(cfg, "story", rule["image"], [], "", rule["targets"])
    with db() as conn:
        conn.execute("UPDATE story_rules SET last_result=? WHERE id=?", (log, rule["id"]))
    return state, log


def social_tick():
    """Einmal pro Minute: fällige freigegebene Posts und Story-Regeln veröffentlichen (höchstens einmal)."""
    cfg = social_config()
    if not cfg["fb_token"]:
        return
    now = datetime.now()
    today, hm = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
    claimed_posts, claimed_rules, missed_posts, missed_rules = [], [], [], []
    with db() as conn:
        due = conn.execute("SELECT * FROM posts WHERE auto_publish=1 AND IFNULL(publish_state,'')='' AND IFNULL(date,'')!='' "
                           "AND (date < ? OR (date = ? AND IFNULL(NULLIF(time,''),'00:00') <= ?))", (today, today, hm)).fetchall()
        for p in due:
            planned = datetime.strptime(f"{p['date']} {(p['time'] or '00:00')[:5]}", "%Y-%m-%d %H:%M")
            if (now - planned).total_seconds() > POST_LATE_HOURS * 3600:
                log = f"{now:%d.%m.%Y %H:%M} Nicht gepostet: Zeitpunkt lag mehr als {POST_LATE_HOURS} Stunden zurück."
                conn.execute("UPDATE posts SET publish_state='verpasst', publish_log=? WHERE id=?", (log, p["id"]))
                missed_posts.append((p, log))
                continue
            # zuerst als „läuft“ markieren, damit ein Post auch bei Fehlern nie doppelt rausgeht
            if conn.execute("UPDATE posts SET publish_state='läuft' WHERE id=? AND IFNULL(publish_state,'')=''", (p["id"],)).rowcount:
                claimed_posts.append(p)
        wd = str(now.isoweekday())
        for r in conn.execute("SELECT * FROM story_rules WHERE active=1 AND IFNULL(last_run,'') != ?", (today,)).fetchall():
            if wd not in (r["weekdays"] or "").split(",") or not r["time"] or r["time"][:5] > hm:
                continue
            if (r["valid_from"] and today < r["valid_from"]) or (r["valid_until"] and today > r["valid_until"]):
                continue
            late = (now - datetime.strptime(f"{today} {r['time'][:5]}", "%Y-%m-%d %H:%M")).total_seconds() / 60
            if not conn.execute("UPDATE story_rules SET last_run=? WHERE id=? AND IFNULL(last_run,'') != ?", (today, r["id"], today)).rowcount:
                continue
            if late > STORY_LATE_MINUTES:
                log = f"{now:%d.%m.%Y %H:%M} Ausgelassen: der Hub lief zur geplanten Zeit nicht."
                conn.execute("UPDATE story_rules SET last_result=? WHERE id=?", (log, r["id"]))
                missed_rules.append((r, log))
                continue
            claimed_rules.append(r)
    for p, log in missed_posts:
        notify_publish("Post", p["title"] or p["type"] or "Post", "verpasst", log)
    for r, log in missed_rules:
        notify_publish("Story", r["name"] or "Story", "verpasst", log)
    for p in claimed_posts:
        state, log = publish_post(cfg, p)
        with db() as conn:
            audit(conn, "Auto-Posting", f"automatisch: {state}", "posts", p["id"], p["title"] or "", {"Ergebnis": log})
        notify_publish("Post", p["title"] or p["type"] or "Post", state, log)
    for r in claimed_rules:
        state, log = publish_rule(cfg, r)
        with db() as conn:
            audit(conn, "Auto-Posting", f"automatisch: {state}", "story_rules", r["id"], r["name"] or "", {"Ergebnis": log})
        notify_publish("Story", r["name"] or "Story", state, log)


# ---- Statistik und Beiträge, die online sind (nur lesen, 15 Minuten zwischengespeichert) ----
SOCIAL_CACHE = {}           # schlüssel -> (zeitpunkt, daten)
SOCIAL_CACHE_SECONDS = 900
# Meta ändert Kennzahlen regelmäßig: jede wird einzeln abgefragt, fehlende werden übersprungen und gemeldet
FB_PAGE_METRICS = [("page_media_view", "Aufrufe"), ("page_total_media_view_unique", "Erreichte Personen"),
                   ("page_post_engagements", "Interaktionen mit Beiträgen")]
IG_ACCOUNT_METRICS = [("views", "Aufrufe"), ("reach", "Erreichte Konten"), ("accounts_engaged", "Konten mit Interaktion"),
                      ("total_interactions", "Interaktionen"), ("profile_links_taps", "Klicks auf Profil-Links")]


def social_cached(key, refresh, fn):
    hit = SOCIAL_CACHE.get(key)
    if hit and not refresh and time.time() - hit[0] < SOCIAL_CACHE_SECONDS:
        return hit[1]
    if hit and refresh and time.time() - hit[0] < 60:   # höchstens einmal pro Minute neu laden
        return hit[1]
    data = fn()
    data["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    SOCIAL_CACHE[key] = (time.time(), data)
    return data


def graph_try(errors, label, *args, **kw):
    try:
        return graph(*args, **kw)
    except GraphError as e:
        errors.append(f"{label}: {e}")
        return None


def social_insights(cfg, days):
    until = int(time.time())
    since = until - days * 86400
    tok, errors = cfg["fb_token"], []
    fb = {"metrics": [], "followers": None}
    page = graph_try(errors, "Facebook-Seite", "GET", cfg["fb_page_id"], {"fields": "followers_count,fan_count"}, tok) or {}
    fb["followers"] = page.get("followers_count", page.get("fan_count"))
    for key, label in FB_PAGE_METRICS:
        r = graph_try(errors, f"Facebook {label}", "GET", f"{cfg['fb_page_id']}/insights", {"metric": key, "period": "day", "since": since, "until": until}, tok)
        vals = ((r or {}).get("data") or [{}])[0].get("values") or []
        if r is not None:
            series = [{"date": (v.get("end_time") or "")[:10], "value": v.get("value") if isinstance(v.get("value"), (int, float)) else 0} for v in vals]
            fb["metrics"].append({"key": key, "label": label, "value": sum(s["value"] for s in series), "series": series})
    ig = None
    if cfg["ig_user_id"]:
        ig = {"metrics": [], "followers": None}
        acc = graph_try(errors, "Instagram-Konto", "GET", cfg["ig_user_id"], {"fields": "followers_count,media_count"}, tok) or {}
        ig["followers"], ig["media_count"] = acc.get("followers_count"), acc.get("media_count")
        ig_since = until - min(days, 30) * 86400   # Instagram erlaubt höchstens 30 Tage
        for key, label in IG_ACCOUNT_METRICS:
            r = graph_try(errors, f"Instagram {label}", "GET", f"{cfg['ig_user_id']}/insights",
                          {"metric": key, "period": "day", "metric_type": "total_value", "since": ig_since, "until": until}, tok)
            if r is not None:
                tv = ((r.get("data") or [{}])[0].get("total_value") or {}).get("value")
                ig["metrics"].append({"key": key, "label": label, "value": tv or 0, "series": []})
        r = graph_try(errors, "Instagram Verlauf", "GET", f"{cfg['ig_user_id']}/insights",
                      {"metric": "reach", "period": "day", "metric_type": "time_series", "since": ig_since, "until": until}, tok)
        series = [{"date": (v.get("end_time") or "")[:10], "value": v.get("value") or 0} for v in (((r or {}).get("data") or [{}])[0].get("values") or [])]
        for m in ig["metrics"]:
            if m["key"] == "reach":
                m["series"] = series
    return {"days": days, "facebook": fb, "instagram": ig, "errors": errors}


def social_online(cfg):
    tok, errors = cfg["fb_token"], []
    out = {"facebook": [], "facebook_stories": [], "instagram": [], "instagram_stories": [], "errors": errors}
    r = graph_try(errors, "Facebook-Beiträge", "GET", f"{cfg['fb_page_id']}/published_posts", {
        "fields": "id,message,created_time,full_picture,permalink_url,status_type,shares,"
                  "reactions.summary(total_count).limit(0),comments.summary(total_count).limit(0)", "limit": 20}, tok)
    for p in (r or {}).get("data", []):
        item = {"id": p["id"], "text": p.get("message", ""), "created": p.get("created_time", ""), "image": p.get("full_picture", ""),
                "url": p.get("permalink_url", ""), "reactions": ((p.get("reactions") or {}).get("summary") or {}).get("total_count", 0),
                "comments": ((p.get("comments") or {}).get("summary") or {}).get("total_count", 0),
                "shares": (p.get("shares") or {}).get("count", 0), "views": None}
        ins = graph_try([], "", "GET", f"{p['id']}/insights", {"metric": "post_media_view"}, tok)
        vals = ((ins or {}).get("data") or [{}])[0].get("values") or []
        if vals:
            item["views"] = vals[-1].get("value")
        out["facebook"].append(item)
    st = graph_try(errors, "Facebook-Storys", "GET", f"{cfg['fb_page_id']}/stories", {}, tok)
    for s in (st or {}).get("data", []):
        if (s.get("status") or "").upper() in ("", "PUBLISHED"):
            out["facebook_stories"].append({"id": s.get("post_id") or s.get("id"), "created": s.get("creation_time", ""),
                                            "url": s.get("url", ""), "type": s.get("media_type", "")})
    if cfg["ig_user_id"]:
        fields = "id,caption,media_type,media_product_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count"
        r = graph_try(errors, "Instagram-Beiträge", "GET", f"{cfg['ig_user_id']}/media", {"fields": fields, "limit": 20}, tok)
        for m in (r or {}).get("data", []):
            item = {"id": m["id"], "text": m.get("caption", ""), "created": m.get("timestamp", ""), "image": m.get("thumbnail_url") or m.get("media_url", ""),
                    "url": m.get("permalink", ""), "type": m.get("media_product_type") or m.get("media_type", ""),
                    "likes": m.get("like_count", 0), "comments": m.get("comments_count", 0), "views": None, "reach": None}
            ins = graph_try([], "", "GET", f"{m['id']}/insights", {"metric": "views,reach"}, tok)
            for d in (ins or {}).get("data", []):
                item[d.get("name")] = ((d.get("values") or [{}])[0]).get("value", (d.get("total_value") or {}).get("value"))
            out["instagram"].append(item)
        r = graph_try(errors, "Instagram-Storys", "GET", f"{cfg['ig_user_id']}/stories", {"fields": fields}, tok)
        for m in (r or {}).get("data", []):
            item = {"id": m["id"], "created": m.get("timestamp", ""), "image": m.get("thumbnail_url") or m.get("media_url", ""),
                    "url": m.get("permalink", ""), "views": None, "reach": None}
            ins = graph_try([], "", "GET", f"{m['id']}/insights", {"metric": "views,reach"}, tok)
            for d in (ins or {}).get("data", []):
                item[d.get("name")] = ((d.get("values") or [{}])[0]).get("value", (d.get("total_value") or {}).get("value"))
            out["instagram_stories"].append(item)
    return out


# Neueste Instagram-Beiträge für die Webseite: der Server holt sie über die Meta-Verbindung
# und speichert die Bilder lokal (data/instagram), Besucher laden nichts von Meta.
INSTA_DIR = DATA / "instagram"
INSTA_FEED = DATA / "instagram.json"
INSTA_REFRESH_SECONDS = 1800
INSTA_LOCK = threading.Lock()
INSTA_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


def insta_codes(text):
    """Kurzcodes aus Instagram-Links (…/p/<code>/, …/reel/<code>/), Groß- und Kleinschreibung zählt."""
    return set(re.findall(r"instagram\.com/(?:[A-Za-z0-9_.]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]{5,40})", text or ""))


def insta_refresh():
    if not INSTA_LOCK.acquire(blocking=False):
        return
    try:
        cfg = social_config()
        if not (cfg["fb_token"] and cfg["ig_user_id"]):
            return
        with db() as conn:
            hide = insta_codes(get_setting(conn, "site_insta_hide"))
        r = graph("GET", f"{cfg['ig_user_id']}/media", {"fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp", "limit": 12 + len(hide)}, cfg["fb_token"])
        INSTA_DIR.mkdir(parents=True, exist_ok=True)
        items = []
        for m in r.get("data", []):
            mid, src, link = str(m.get("id", "")), m.get("thumbnail_url") or m.get("media_url") or "", m.get("permalink") or ""
            if not mid.isalnum() or not src or not link.startswith(("https://www.instagram.com/", "https://instagram.com/")):
                continue
            if insta_codes(link) & hide:   # im Hub ausgeblendet (z. B. angepinnt)
                continue
            old = next(INSTA_DIR.glob(mid + ".*"), None)
            if old is None:
                try:
                    with urllib.request.urlopen(src, timeout=30) as resp:
                        ext = INSTA_TYPES.get((resp.headers.get("Content-Type") or "").split(";")[0].strip())
                        data = resp.read(8_000_001)
                except (urllib.error.URLError, OSError, ValueError):
                    continue
                if not ext or len(data) > 8_000_000:
                    continue
                old = INSTA_DIR / (mid + ext)
                old.write_bytes(data)
            caption = " ".join((m.get("caption") or "").split("\n")[0].split())
            items.append({"image": f"/web/insta/{old.name}", "url": link, "alt": caption[:120] or "Instagram-Beitrag des SV Amisia Wolthusen"})
            if len(items) == 6:
                break
        keep = {i["image"].rsplit("/", 1)[-1] for i in items}
        for f in INSTA_DIR.iterdir():
            if f.name not in keep:
                f.unlink(missing_ok=True)
        INSTA_FEED.write_text(json.dumps({"fetched": time.time(), "items": items}), encoding="utf-8")
    except (GraphError, OSError, ValueError) as e:
        print("Instagram für die Webseite nicht geladen:", e)
        try:   # nicht bei jedem Seitenaufruf neu versuchen
            INSTA_FEED.write_text(json.dumps({**public_instagram_raw(), "fetched": time.time()}), encoding="utf-8")
        except OSError:
            pass
    finally:
        INSTA_LOCK.release()


# ---------------------------------------------------------------------------
# Webseite im Hub verwalten: Bilder (vom Browser als WebP in 640/1280/1920 erzeugt), Aufbau der Startseite
# ---------------------------------------------------------------------------
SITE_DIR = DATA / "site"
SITE_WIDTHS = (640, 960, 1280, 1920)
SITE_IMAGE_MAX = 4 * 1024 * 1024


def web_images(conn):
    try:
        v = json.loads(get_setting(conn, "web_images") or "{}")
        return v if isinstance(v, dict) else {}
    except ValueError:
        return {}


def web_sitemap(conn, raw=None):
    """Sitemap-Einstellung {schlüssel: [an, priorität]} für alle website.SITEMAP_PAGES, Unbekanntes und Ungültiges verworfen.
    raw: neue Werte aus dem Hub (sonst die gespeicherten)."""
    if raw is None:
        try:
            raw = json.loads(get_setting(conn, "web_sitemap") or "{}")
        except ValueError:
            raw = {}
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for k, _, prio in website.SITEMAP_PAGES:
        v = raw.get(k)
        ok = isinstance(v, list) and len(v) == 2 and str(v[1]) in website.SITEMAP_PRIOS
        out[k] = [bool(v[0]), str(v[1])] if ok else [True, prio]
    return out


def web_layout(conn):
    """Reihenfolge und Sichtbarkeit der Startseiten-Abschnitte: [[schlüssel, sichtbar], ...], unbekannte verworfen, neue ergänzt."""
    try:
        raw = json.loads(get_setting(conn, "web_layout") or "[]")
    except ValueError:
        raw = []
    out, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, list) and len(item) == 2 and item[0] in website.START_SECTIONS and item[0] not in seen:
            out.append([item[0], bool(item[1])])
            seen.add(item[0])
    keys = list(website.START_SECTIONS)
    for i, k in enumerate(keys):   # neue Abschnitte an ihren Standardplatz, hinter den Abschnitt davor
        if k not in seen:
            prev = next((j for j, (x, _) in enumerate(out) if i and x == keys[i - 1]), None)
            out.insert(prev + 1 if prev is not None else len(out), [k, True])
            seen.add(k)
    return out


# ---------------------------------------------------------------- Menü der Webseite (Hub > Webseite > Menü)
# Das Hauptmenü mit Sportarten und Verein steht fest in website.NAV. Hier nur die Zusatzpunkte, die der Hub ein- und ausblendet.
NAV_BUILTIN = [("supporter-karte", "Dauerkarte"), ("fanshop", "Fanshop")]
NAV_HIDDEN_DEFAULT = set()   # Dauerkarte erscheint ohnehin nur bei offener Bestellung, Fanshop nur mit Adresse
SOCIAL_HOSTS = {"site_social_instagram": ("instagram.com",), "site_social_facebook": ("facebook.com", "fb.com"), "site_social_tiktok": ("tiktok.com",)}


def web_nav(conn):
    """Alle Seiten des Menüs in gespeicherter Reihenfolge, neue hinten: [{key, title, label, show, button}]."""
    try:
        raw = json.loads(get_setting(conn, "web_nav") or "[]")
    except ValueError:
        raw = []
    titles = dict(NAV_BUILTIN)
    out, seen = [], set()
    for it in raw if isinstance(raw, list) else []:
        if isinstance(it, dict) and it.get("key") in titles and it["key"] not in seen:
            out.append({"key": it["key"], "title": titles[it["key"]], "show": bool(it.get("show")), "label": str(it.get("label") or "")[:40], "button": bool(it.get("button"))})
            seen.add(it["key"])
    for k, t in NAV_BUILTIN:
        if k not in seen:
            out.append({"key": k, "title": t, "show": k not in NAV_HIDDEN_DEFAULT, "label": "", "button": k == "fanshop"})
    return out


LINKS_MAX = 20   # Link-Seite /links (für die Instagram-Bio): höchstens so viele Knöpfe
LINKS_DEFAULT = [{"label": "Zur Webseite", "url": "/", "hot": True}, {"label": "Spielplan", "url": "/spielplan", "hot": False},
                 {"label": "Mitglied werden", "url": "/mitglied-werden", "hot": False}, {"label": "News", "url": "/news", "hot": False}]


def link_url_ok(url):
    """Ziel eines Knopfs auf der Link-Seite: https-Adresse oder eigene Seite (/...), ohne Leer- und Steuerzeichen."""
    url = (url or "").strip()
    if len(url) > 500 or any(c in url for c in ' "\'<>`\\') or any(ord(c) < 32 for c in url):
        return ""
    return url if re.match(r"https://[a-z0-9-]+(\.[a-z0-9-]+)+(/|\?|#|$)", url, re.I) or re.match(r"/(?!/)", url) else ""


def web_links(conn):
    """Knöpfe der Link-Seite: [{label, url, hot}]. Ohne Einstellung die Standardliste."""
    raw = get_setting(conn, "web_links")
    if not raw:
        return [dict(x) for x in LINKS_DEFAULT]
    try:
        items = json.loads(raw)
    except ValueError:
        items = []
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and str(it.get("label") or "").strip() and link_url_ok(it.get("url")):
            out.append({"label": str(it["label"]).strip()[:60], "url": link_url_ok(it["url"]), "hot": bool(it.get("hot"))})
    return out[:LINKS_MAX]


def social_url(key, url):
    """Nur https-Adressen der passenden Plattform, ohne Leer- und Steuerzeichen."""
    url = (url or "").strip()
    host = re.match(r"https://(?:[a-z0-9-]+\.)*([a-z0-9-]+\.[a-z]+)(?:/|$)", url, re.I)
    if not host or any(c in url for c in ' "\'<>`') or host.group(1).lower() not in SOCIAL_HOSTS.get(key, ()):
        return ""
    return url[:300]


def public_nav():
    """Menü für website.layout: sichtbare Einträge (Dauerkarte nur bei offener Bestellung, Fanshop nur mit Adresse) und die Social-Media-Symbole."""
    with db() as conn:
        items = web_nav(conn)
        card_open = get_setting(conn, "site_card_order_open") == "1"
        shop = (get_setting(conn, "site_shop_url") or "").strip()
        social = [(k[12:], social_url(k, get_setting(conn, k))) for k in SOCIAL_HOSTS]
    shop = shop if shop.startswith("https://") and not any(c in shop for c in ' "<>') else ""
    out = []
    for it in items:
        if not it["show"]:
            continue
        label = it["label"] or it["title"]
        if it["key"] == "fanshop":
            if shop:
                out.append({"href": shop, "label": label, "button": it["button"], "external": True, "slug": None})
        elif it["key"] != "supporter-karte" or card_open:
            out.append({"href": "/" + it["key"], "label": label, "button": it["button"], "slug": it["key"]})
    return {"items": out, "social": [{"kind": k, "url": u} for k, u in social if u]}


def public_site():
    """Eigene Bilder (nur Dateiname, Maße, Alt-Text) und Aufbau der Startseite für website.py."""
    with db() as conn:
        imgs, layout = web_images(conn), web_layout(conn)
    out = {}
    for slot, m in imgs.items():
        if slot not in website.IMAGE_SLOTS or not isinstance(m, dict):
            continue
        files = {int(w): f for w, f in (m.get("files") or {}).items() if str(w).isdigit() and (SITE_DIR / str(f)).is_file()}
        out[slot] = {"alt": str(m.get("alt") or ""), "w": int(m.get("w") or 0), "h": int(m.get("h") or 0),
                     "src": {w: f"/web/site/{f}" for w, f in sorted(files.items())}}
    return {"images": out, "layout": layout}


def website_overview(text_keys):
    """Alles für die Seite „Webseite“ im Hub: Texte, Bilder, Aufbau und eine Checkliste offener Punkte."""
    std = website.image_meta(standard=True)
    site = public_site()
    with db() as conn:
        texts = {k: get_setting(conn, k) for k in text_keys}
        imgs = web_images(conn)
        players = conn.execute("SELECT * FROM players WHERE active=1").fetchall()
        sponsors = conn.execute("SELECT name, logo FROM sponsors WHERE active=1").fetchall()
        today = datetime.now().date().isoformat()
        games = conn.execute("SELECT g.*, o.name AS opp, o.logo AS opp_logo FROM games g LEFT JOIN opponents o ON o.id = g.opponent_id "
                             "WHERE IFNULL(g.date,'') >= ? ORDER BY g.date", (today,)).fetchall()
        secret = secret_get(conn, "ig_user_id")
    images = []
    for slot, (label, where) in website.IMAGE_SLOTS.items():
        if slot == website.MAINT_SLOT:   # eigenes Bild der Wartungsseite, gepflegt unter Verwaltung > Wartungsmodus
            continue
        own = site["images"].get(slot)
        s = std.get(slot) or {}
        src = (own or {}).get("src") or {}
        preview = src.get(640) or src.get(min(src)) if src else (f"/web/assets/img/{slot}-640.webp" if s else "")
        images.append({"slot": slot, "label": label, "where": where, "own": bool(own), "preview": preview,
                       "alt": (imgs.get(slot) or {}).get("alt") or s.get("alt", ""), "standard_alt": s.get("alt", ""),
                       "w": (own or s).get("w", 0), "h": (own or s).get("h", 0)})
    checks = []
    def add(level, text, link=""):
        checks.append({"level": level, "text": text, "link": link})
    for k, label in website.REQUIRED_TEXTS.items():
        if not (texts.get(k) or "").strip():
            add("fehlt", f"Text fehlt: {label} (erscheint als gelber Platzhalter)", "#/website/texte")
    for k, label in (("site_impressum", "Impressum"), ("site_datenschutz", "Datenschutzerklärung")):
        open_marks = re.findall(r"\[[^\]\n]{1,200}\]", texts.get(k) or "")
        if open_marks:
            add("fehlt", f"{label}: {len(open_marks)} Angaben in [eckigen Klammern] noch ausfüllen (z. B. {open_marks[0]})", "#/website/texte")
    herren = [p for p in players if (p["team"] or MAIN_TEAM) == MAIN_TEAM and (p["kind"] or "Spieler") == "Spieler"]
    no_consent = [p for p in herren if not p["consent"]]
    if not herren:
        add("hinweis", "Noch keine aktiven Spieler der Ersten Herren: Auf ihrer Seite fehlt der Kader.", "#/players")
    if no_consent:
        add("hinweis", f"{len(no_consent)} Spieler ohne Foto-Einwilligung: Sie erscheinen mit dem Vereinswappen statt Foto.", "#/players")
    no_photo = [p for p in herren if p["consent"] and not p["photo"]]
    if no_photo:
        add("hinweis", f"{len(no_photo)} Spieler mit Einwilligung, aber ohne Foto.", "#/players")
    no_pos = [p for p in herren if not p["position"]]
    if no_pos:
        add("hinweis", f"{len(no_pos)} Spieler ohne Position: Sie stehen im Kader unter „Weitere Spieler“.", "#/players")
    if not [p for p in players if (p["kind"] or "Spieler") != "Spieler"]:
        add("hinweis", "Noch keine Trainer eingetragen.", "#/players")
    with db() as conn:
        no_training = [t for t in TEAMS if not conn.execute("SELECT 1 FROM trainings WHERE team=? AND active=1", (t,)).fetchone()]
    if no_training:
        add("hinweis", "Ohne Trainingszeiten: " + ", ".join(no_training), "#/trainings")
    if not games:
        add("hinweis", "Keine kommenden Spiele: Startseite und Spielplan zeigen „Termine folgen“.", "#/games")
    for g in games:
        day = website.fmt_date(g["date"]) or g["date"]
        if not g["opp"]:
            add("hinweis", f"Spiel am {day} ohne Gegner.", "#/games")
        elif not g["opp_logo"]:
            add("hinweis", f"Gegner {g['opp']} ohne Logo (Spiel am {day}).", "#/opponents")
        if not g["time"]:
            add("hinweis", f"Spiel am {day} ohne Anstoßzeit.", "#/games")
    missing_logo = [s["name"] for s in sponsors if not s["logo"]]
    if missing_logo:
        add("hinweis", "Sponsoren ohne Logo (erscheinen nur als Name): " + ", ".join(missing_logo[:5]), "#/sponsors")
    if not secret:
        add("hinweis", "Instagram ist nicht verbunden: Das Raster auf der Startseite zeigt die Ersatzbilder der Galerie (ohne Bilder bleibt es aus).", "#/autopost")
    notice_until = texts.get("site_notice_until") or ""
    if texts.get("site_notice_text") and notice_until and notice_until < today:
        add("hinweis", "Die Hinweis-Leiste ist abgelaufen und wird nicht mehr angezeigt.", "#/website/hinweis")
    with db() as conn:
        sm = web_sitemap(conn)
        nav = web_nav(conn)
        links, links_default = web_links(conn), not get_setting(conn, "web_links")
    return {"texts": texts, "images": images, "checks": checks, "site_url": SITE_URL, "nav": nav, "links": links, "links_default": links_default, "links_max": LINKS_MAX,
            "layout": [{"key": k, "label": website.START_SECTIONS[k], "visible": v} for k, v in site["layout"]],
            "sitemap": [{"key": k, "label": label, "on": sm[k][0], "prio": sm[k][1], "default": d} for k, label, d in website.SITEMAP_PAGES]}


def public_instagram_raw():
    try:
        return json.loads(INSTA_FEED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"fetched": 0, "items": []}


def public_instagram():
    """Bis zu 6 neueste Instagram-Bilder (lokal gespeichert), veraltet: im Hintergrund neu laden."""
    feed = public_instagram_raw()
    if time.time() - feed.get("fetched", 0) > INSTA_REFRESH_SECONDS:
        threading.Thread(target=insta_refresh, daemon=True).start()
    return [{"image": i["image"], "url": i["url"], "alt": i["alt"]} for i in feed.get("items", []) if (INSTA_DIR / i["image"].rsplit("/", 1)[-1]).is_file()]


# ---------------------------------------------------------------------------
# E-Mail-Benachrichtigungen. Jeder wählt unter „Mein Profil“, was er bekommt (users.notify),
# angeboten wird nur, wofür er Leserechte hat. SMTP-Zugang in secrets (Passwort nie über die API lesbar).
# ---------------------------------------------------------------------------
APPAREL_ANY = ("verein", "finanzen", "medien")
NOTIFY_KINDS = {
    "post_failed": ("Auto-Posting hat nicht geklappt", ("medien",)),
    "post_done": ("Ein Post wurde automatisch veröffentlicht", ("medien",)),
    "magazine_deadline": ("Stadionheft: Redaktionsschluss naht (7, 3, 1 Tag vorher und am Tag)", ("medien",)),
    "apparel_orders": ("Teamkleidung: neue Bestellungen (höchstens einmal pro Stunde gesammelt)", APPAREL_ANY),
    "apparel_deadline": ("Teamkleidung: Bestellschluss naht und Zusammenfassung danach", APPAREL_ANY),
    "contact_request": ("Neue Anfrage über das Kontaktformular der Webseite", ("mitglieder",)),
    "card_order": ("Neue Online-Bestellung einer Dauerkarte", ("finanzen",)),
    "player_signup": ("Neuer Spielerbogen (Formular für Kader & Staff)", ("verein",)),
}
# Gelten automatisch, solange jemand unter „Mein Profil“ noch nie Benachrichtigungen gespeichert hat
NOTIFY_DEFAULT = ()


def notify_kinds_of(u):
    """Abonnierte Arten eines Kontos; nie gespeichert = Standard."""
    if u["notify"] is None:
        return list(NOTIFY_DEFAULT)
    try:
        return json.loads(u["notify"] or "[]")
    except ValueError:
        return []


def notify_users(user_ids, kind, subject, body, once_prefix=None):
    """Mail an bestimmte Konten (z. B. Eingeladene eines Termins), nur wer die Art abonniert hat und die Rechte dafür hat.
    once_prefix: je Konto nur einmal (Schlüssel once_prefix:konto)."""
    cfg = smtp_config()
    if not cfg["smtp_host"] or not user_ids:
        return
    to = []
    with db() as conn:
        for uid in set(user_ids):
            u = conn.execute("SELECT id, is_admin, email, notify, member_id, active FROM users WHERE id=?", (uid,)).fetchone()
            if not u or not u["active"] or kind not in notify_kinds_of(u) or not notify_allowed(effective_perms(conn, row_dict(u)), kind):
                continue
            addr = account_email(conn, u)
            if not addr:
                continue
            if once_prefix:
                key = f"{once_prefix}:{uid}"
                if conn.execute("SELECT 1 FROM notify_sent WHERE key=?", (key,)).fetchone():
                    continue
                conn.execute("INSERT INTO notify_sent (key, time) VALUES (?, ?)", (key, datetime.now().isoformat(timespec="seconds")))
            to.append(addr)
    for addr in to:
        send_mail(cfg, addr, f"Wolthusen Hub: {subject}", body)


def notify_users_async(*args, **kw):
    threading.Thread(target=lambda: notify_users(*args, **kw), daemon=True).start()
SMTP_KEYS = ("smtp_host", "smtp_port", "smtp_security", "smtp_user", "smtp_from", "hub_url", "imap_host")
NOTIFY_HOUR = 8   # Erinnerungen frühestens ab 8 Uhr
NOTIFY_INTERVAL = int(ENV("TMH_NOTIFY_INTERVAL") or 300)   # Sekunden zwischen zwei Durchläufen (Variable nur für Tests)
DIGEST_SECONDS = int(ENV("TMH_DIGEST_SECONDS") or 3600)    # neue Bestellungen höchstens so oft gesammelt melden


def notify_allowed(perms, kind):
    need = NOTIFY_KINDS[kind][2] if len(NOTIFY_KINDS[kind]) > 2 else 1
    return any(perms.get(a, 0) >= need for a in NOTIFY_KINDS[kind][1])


# ---------------------------------------------------------------------------
# Postfach (IMAP): Mails des Vereinspostfachs im Hub lesen und beantworten (Bereich „postfach“).
# Zugang wie beim Versand (smtp_user/smtp_password), Server aus imap_host oder smtp.* -> imap.*.
# Nichts wird im Hub gespeichert, jede Anfrage holt live vom Mailserver. Inhalte nur als Text (HTML wird zu Text), Anhänge nur als Download.
# ---------------------------------------------------------------------------
PF_PAGE = 40
PF_DONE_FOLDER = "Erledigt"   # „Erledigt“ verschiebt Mails hierher (wird bei Bedarf angelegt)
PF_FOLDER_LABELS = {"inbox": "Posteingang", "done": "Erledigt", "sent": "Gesendet", "drafts": "Entwürfe", "trash": "Papierkorb", "junk": "Spam", "archive": "Archiv"}
PF_ROLE_NAMES = {"sent": ("sent", "gesendet", "gesendete objekte", "sent items", "sent messages"), "trash": ("trash", "papierkorb", "deleted items", "gelöschte objekte"),
                 "drafts": ("drafts", "entwürfe"), "junk": ("junk", "spam", "unerwünscht"), "archive": ("archive", "archiv"), "done": ("erledigt",)}


class PostfachError(Exception):
    pass


def imap_utf7_decode(name):
    out = []
    for part in re.split(r"(&[^-]*-)", name):
        if part.startswith("&") and part.endswith("-"):
            if part == "&-":
                out.append("&")
            else:
                b = part[1:-1].replace(",", "/")
                try:
                    out.append(base64.b64decode(b + "=" * (-len(b) % 4)).decode("utf-16-be"))
                except (ValueError, UnicodeDecodeError):
                    out.append(part)
        else:
            out.append(part)
    return "".join(out)


def imap_quote(name):
    return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def postfach_config():
    cfg = smtp_config()
    host = (cfg.get("imap_host") or "").strip() or re.sub(r"^smtp\.", "imap.", (cfg.get("smtp_host") or "").strip())
    cfg["imap"] = host if re.fullmatch(r"[A-Za-z0-9.-]{3,200}", host or "") else ""
    return cfg


def postfach_open(cfg=None):
    import imaplib
    import ssl
    cfg = cfg or postfach_config()
    if not (cfg["imap"] and cfg["smtp_user"] and cfg["smtp_password"]):
        raise PostfachError("Das Postfach ist noch nicht eingerichtet (Verwaltung > Einstellungen > E-Mail-Versand: Benutzer, Passwort und Server).")
    try:
        m = imaplib.IMAP4_SSL(cfg["imap"], 993, ssl_context=ssl.create_default_context(), timeout=20)
    except OSError as e:
        raise PostfachError(f"Der Mailserver {cfg['imap']} ist nicht erreichbar ({type(e).__name__}).")
    try:
        m.login(cfg["smtp_user"], cfg["smtp_password"])
    except imaplib.IMAP4.error:
        raise PostfachError("Anmeldung am Postfach fehlgeschlagen. Benutzername oder Passwort stimmen nicht.")
    return m, cfg


def postfach_folders(m):
    typ, data = m.list()
    out = []
    for line in data or []:
        if not isinstance(line, bytes):
            continue
        mm = re.match(rb'\((?P<flags>[^)]*)\) (?:"[^"]*"|NIL) (?P<name>.+)$', line)
        if not mm:
            continue
        raw = mm.group("name").decode("utf-8", "replace").strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1].replace('\\"', '"').replace("\\\\", "\\")
        flags = mm.group("flags").decode().lower()
        if "\\noselect" in flags:
            continue
        label = imap_utf7_decode(raw)
        short = label.split("/")[-1].split(".")[-1].strip().lower()
        role = "inbox" if raw.upper() == "INBOX" else next((r for r in ("sent", "trash", "drafts", "junk", "archive") if f"\\{r}" in flags), "")
        if not role:
            role = next((r for r, names in PF_ROLE_NAMES.items() if short in names), "")
        out.append({"name": raw, "label": PF_FOLDER_LABELS.get(role, label), "role": role})
    order = ["inbox", "done", "sent", "drafts", "archive", "junk", "trash", ""]
    out.sort(key=lambda f: (order.index(f["role"]), f["label"].lower()))
    return out


def pf_done_folder(m, create=True):
    """Name des Ordners „Erledigt“ im Postfach; legt ihn an, wenn er fehlt (create=True)."""
    names = [f["name"] for f in postfach_folders(m)]
    target = next((n for n in names if n.split(".")[-1].split("/")[-1].strip().lower() == PF_DONE_FOLDER.lower()), "")
    if not target and create:
        names = [PF_DONE_FOLDER]
        with contextlib.suppress(Exception):   # manche Anbieter erlauben Ordner nur unterhalb von „INBOX.“ (persönlicher Namensraum)
            typ, ns = m.namespace()
            mm = re.match(rb'\(\("([^"]*)" "([^"]*)"\)', (ns or [b""])[0] or b"")
            if mm and mm.group(1):
                names.append(mm.group(1).decode() + PF_DONE_FOLDER)
        for name in names:
            with contextlib.suppress(Exception):
                typ, _d = m.create(imap_quote(name))
                if typ == "OK":
                    target = name
                    with contextlib.suppress(Exception):
                        m.subscribe(imap_quote(name))
                    break
    return target


def pf_move_to_done(folder, uid, cfg=None):
    """Mail in den Ordner „Erledigt“ verschieben (anlegen, falls nötig). Zuweisungen und Erledigt-Vermerk ziehen mit.
    cfg = eigenes Postfach eines Kontos (dann ohne Zuweisungen). Gibt (Ordner, neue UID) zurück oder None."""
    m, _ = postfach_open(cfg)
    try:
        target = pf_done_folder(m)
        if not target:
            raise PostfachError("Ordner „Erledigt“ konnte nicht angelegt werden.")
        if folder == target:
            return None
        pf_select(m, folder, readonly=False)
        typ, data = m.uid("FETCH", str(uid), "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])")
        hdr = next((x[1] for x in data or [] if isinstance(x, tuple)), b"")
        if not hdr:
            return None
        mid = re.search(rb"Message-ID:\s*(<[^>]+>)", hdr, re.I)
        m.untagged_responses.pop("COPYUID", None)
        if "MOVE" in m.capabilities:
            typ, data = m.uid("MOVE", str(uid), imap_quote(target))
        else:
            typ, data = m.uid("COPY", str(uid), imap_quote(target))
            if typ == "OK":
                m.uid("STORE", str(uid), "+FLAGS", "(\\Deleted)")
                m.expunge()
        if typ != "OK":
            raise PostfachError("Verschieben nach „Erledigt“ fehlgeschlagen.")
        new_uid = None
        texts = [x for x in (m.untagged_responses.pop("COPYUID", None) or []) + list(data or []) if isinstance(x, (bytes, str))]
        for t in texts:
            mm = re.search(r"(?:COPYUID )?\d+ (\d+) (\d+)", t.decode() if isinstance(t, bytes) else t)
            if mm and mm.group(1) == str(uid):
                new_uid = int(mm.group(2))
        if new_uid is None and mid:   # ohne Rückmeldung: über die Message-ID im Zielordner suchen
            pf_select(m, target)
            typ, d2 = m.uid("SEARCH", None, "HEADER", "Message-ID", mid.group(1).decode())
            found = (d2[0] or b"").split()
            new_uid = int(found[-1]) if found else None
    finally:
        with contextlib.suppress(Exception):
            m.logout()
    if new_uid and cfg is None:
        with db() as conn:
            conn.execute("UPDATE pf_inbox SET folder=?, uid=? WHERE folder=? AND uid=?", (target, new_uid, folder, int(uid)))
            conn.execute("UPDATE mail_tasks SET folder=?, uid=? WHERE folder=? AND uid=?", (target, new_uid, folder, int(uid)))
    return target, new_uid


def pf_forward_to_person(cfg, msg, to, name, by, note=""):
    """Mail aus dem Vereinspostfach an eine Person ohne Zugriff weiterleiten (Text, Anhänge, Antworten gehen an den Absender)."""
    frm, subj = pf_head(msg.get("From")), pf_head(msg.get("Subject")) or "(ohne Betreff)"
    atts, total = [], 0
    for i, part in enumerate(msg.iter_attachments()):
        data = part.get_payload(decode=True) or b""
        total += len(data)
        if total > 20 * 1024 * 1024:
            break
        ctype = part.get_content_type() if "/" in part.get_content_type() else "application/octet-stream"
        atts.append((pf_head(part.get_filename() or "") or f"anhang-{i + 1}", data, *ctype.split("/", 1)))
    text = (f"Hallo {name},\n\n{by.get('display_name') or by.get('username')} hat dir diese Mail aus dem Vereinspostfach {cfg.get('smtp_user', '')} "
            f"zum Bearbeiten weitergeleitet.\n" + (f"Hinweis: {note}\n" if note else "") +
            "Mit „Antworten“ geht deine Antwort direkt an den Absender.\n\n"
            f"---------- Weitergeleitete Nachricht ----------\nVon: {frm}\nDatum: {msg.get('Date') or ''}\nBetreff: {subj}\nAn: {pf_head(msg.get('To'))}\n"
            + (f"Cc: {pf_head(msg.get('Cc'))}\n" if msg.get("Cc") else "") + "\n" + pf_text(msg))
    reply_to = pf_head(msg.get("Reply-To")) or frm
    return send_mail(cfg, to, subj if re.match(r"(wg|fwd)\s*:", subj, re.I) else f"WG: {subj}", text, footer=False,
                     attachments=atts, headers={"Reply-To": reply_to.replace("\n", " ")[:300]})


def pf_role_folder(m, role):
    return next((f["name"] for f in postfach_folders(m) if f["role"] == role), "")


def pf_select(m, folder, readonly=True):
    typ, data = m.select(imap_quote(folder or "INBOX"), readonly=readonly)
    if typ != "OK":
        raise PostfachError("Diesen Ordner gibt es nicht.")


def pf_name(f):
    from email.utils import parseaddr
    n, a = parseaddr(f or "")
    return n or a or (f or "")


def pf_head(text):
    from email.header import decode_header, make_header
    try:
        return str(make_header(decode_header(text or "")))
    except Exception:  # noqa
        return text or ""


class _HtmlText(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "blockquote", "hr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.href = [], 0, ""

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head", "title"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")
        if tag == "li":
            self.out.append("- ")
        if tag == "a":
            self.href = dict(attrs).get("href") or ""

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head", "title"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")
        if tag == "a" and self.href.startswith(("http://", "https://")):
            self.out.append(f" [{self.href}]")
            self.href = ""

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(html):
    p = _HtmlText()
    try:
        p.feed(html or "")
        p.close()
    except Exception:  # noqa
        return re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.out))
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()


def pf_message(m, folder, uid, mark_seen=True):
    from email import policy
    from email.parser import BytesParser
    pf_select(m, folder, readonly=not mark_seen)
    typ, data = m.uid("FETCH", uid, "(FLAGS BODY.PEEK[])")
    raw = next((x[1] for x in data or [] if isinstance(x, tuple)), None)
    if not raw:
        raise PostfachError("Diese Mail gibt es nicht mehr.")
    flags = next((x[0] for x in data if isinstance(x, tuple)), b"")
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    if mark_seen and b"\\Seen" not in flags:
        m.uid("STORE", uid, "+FLAGS", "(\\Seen)")
    return msg, flags


def pf_text(msg):
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    try:
        content = part.get_content()
    except (LookupError, ValueError):
        content = part.get_payload(decode=True).decode("utf-8", "replace")
    if part.get_content_subtype() == "html":
        content = html_to_text(content)
    return str(content)[:200000]


def pf_attachments(msg):
    out = []
    for i, part in enumerate(msg.iter_attachments()):
        name = pf_head(part.get_filename() or "") or f"anhang-{i + 1}"
        payload = part.get_payload(decode=True) or b""
        out.append({"i": i, "name": name[:150], "type": part.get_content_type(), "size": len(payload)})
    return out


def pf_unseen(cfg=None):
    m, _ = postfach_open(cfg)
    try:
        typ, data = m.status("INBOX", "(UNSEEN)")
        mm = re.search(rb"UNSEEN (\d+)", data[0] if data else b"")
        return int(mm.group(1)) if mm else 0
    finally:
        with contextlib.suppress(Exception):
            m.logout()


def pf_append_sent(raw):
    """Kopie einer aus dem Hub verschickten Mail im Ordner „Gesendet“ ablegen (wie bei einem Mailprogramm)."""
    import imaplib
    m, _ = postfach_open()
    try:
        sent = pf_role_folder(m, "sent")
        if sent:
            m.append(imap_quote(sent), "(\\Seen)", imaplib.Time2Internaldate(time.time()), raw)
    finally:
        with contextlib.suppress(Exception):
            m.logout()


# ---------------------------------------------------------------------------
# Web Push (RFC 8030/8291/8292) nur mit der Standardbibliothek: P-256 (ECDH, ECDSA für VAPID), HKDF, AES-128-GCM.
# Geprüft gegen die Testwerte aus RFC 8291 Anhang A und NIST-GCM. Nachrichten sind Ende-zu-Ende verschlüsselt,
# der Push-Dienst (Google, Apple, Mozilla) sieht nur Absender-Schlüssel, Größe und Zeitpunkt.
# ---------------------------------------------------------------------------
_EC_P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
_EC_A = _EC_P - 3
_EC_B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_EC_N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_EC_G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
         0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _ec_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    (x1, y1), (x2, y2) = p1, p2
    if x1 == x2 and (y1 + y2) % _EC_P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1 + _EC_A) * pow(2 * y1, -1, _EC_P) % _EC_P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, _EC_P) % _EC_P
    x3 = (lam * lam - x1 - x2) % _EC_P
    return x3, (lam * (x1 - x3) - y1) % _EC_P


def _ec_mul(k, pt):
    r0, r1 = None, pt   # Montgomery-Leiter: gleiche Schrittfolge für jedes Bit
    for bit in bin(k)[2:]:
        if bit == "1":
            r0, r1 = _ec_add(r0, r1), _ec_add(r1, r1)
        else:
            r0, r1 = _ec_add(r0, r0), _ec_add(r0, r1)
    return r0


def _ec_on_curve(pt):
    x, y = pt
    return 0 <= x < _EC_P and 0 <= y < _EC_P and (y * y - (x * x * x + _EC_A * x + _EC_B)) % _EC_P == 0


def ec_pub_bytes(pt):
    return b"\x04" + pt[0].to_bytes(32, "big") + pt[1].to_bytes(32, "big")


def ec_pub_point(raw):
    if len(raw) != 65 or raw[0] != 4:
        raise ValueError("Ungültiger öffentlicher Schlüssel")
    pt = (int.from_bytes(raw[1:33], "big"), int.from_bytes(raw[33:], "big"))
    if not _ec_on_curve(pt):
        raise ValueError("Schlüssel liegt nicht auf der Kurve")
    return pt


def ec_keypair(priv=None):
    d = priv if priv is not None else secrets.randbelow(_EC_N - 1) + 1
    return d, _ec_mul(d, _EC_G)


def ec_sign(d, data):
    """ECDSA P-256 mit SHA-256, Ergebnis r||s (64 Bytes) wie für JWT ES256 nötig."""
    z = int.from_bytes(hashlib.sha256(data).digest(), "big")
    while True:
        k = secrets.randbelow(_EC_N - 1) + 1
        r = _ec_mul(k, _EC_G)[0] % _EC_N
        if not r:
            continue
        s = pow(k, -1, _EC_N) * (z + r * d) % _EC_N
        if s:
            return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def ec_verify(pub, data, sig):
    r, s = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")
    if not (0 < r < _EC_N and 0 < s < _EC_N):
        return False
    z = int.from_bytes(hashlib.sha256(data).digest(), "big")
    w = pow(s, -1, _EC_N)
    pt = _ec_add(_ec_mul(z * w % _EC_N, _EC_G), _ec_mul(r * w % _EC_N, pub))
    return pt is not None and pt[0] % _EC_N == r


# AES-128 (nur Verschlüsseln) und GCM
_AES_SBOX = bytes.fromhex(
    "637c777bf26b6fc53001672bfed7ab76ca82c97dfa5947f0add4a2af9ca472c0b7fd9326363ff7cc34a5e5f171d8311504c723c31896059a071280e2eb27b275"
    "09832c1a1b6e5aa0523bd6b329e32f8453d100ed20fcb15b6acbbe394a4c58cfd0efaafb434d338545f9027f503c9fa851a3408f929d38f5bcb6da2110fff3d2"
    "cd0c13ec5f974417c4a77e3d645d197360814fdc222a908846eeb814de5e0bdbe0323a0a4906245cc2d3ac629195e479e7c8376d8dd54ea96c56f4ea657aae08"
    "ba78252e1ca6b4c6e8dd741f4bbd8b8a703eb5664803f60e613557b986c11d9ee1f8981169d98e949b1e87e9ce5528df8ca1890dbfe6426841992d0fb054bb16")
_AES_RCON = (1, 2, 4, 8, 16, 32, 64, 128, 27, 54)


def _aes_expand(key):
    w = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    for i in range(4, 44):
        t = list(w[i - 1])
        if i % 4 == 0:
            t = [_AES_SBOX[b] for b in t[1:] + t[:1]]
            t[0] ^= _AES_RCON[i // 4 - 1]
        w.append([a ^ b for a, b in zip(w[i - 4], t)])
    return [sum(w[r * 4:r * 4 + 4], []) for r in range(11)]


def _xt(a):
    return ((a << 1) ^ 0x1B) & 0xFF if a & 0x80 else a << 1


def _aes_block(rk, block):
    s = [b ^ k for b, k in zip(block, rk[0])]
    for rnd in range(1, 11):
        s = [_AES_SBOX[b] for b in s]
        s = [s[(i + 4 * (i % 4)) % 16] for i in range(16)]   # ShiftRows (spaltenweise Ablage)
        if rnd != 10:
            t = []
            for c in range(4):
                a = s[4 * c:4 * c + 4]
                x = a[0] ^ a[1] ^ a[2] ^ a[3]
                t += [a[i] ^ x ^ _xt(a[i] ^ a[(i + 1) % 4]) for i in range(4)]
            s = t
        s = [b ^ k for b, k in zip(s, rk[rnd])]
    return bytes(s)


def _gf_mul(x, y):
    r, R = 0, 0xE1 << 120
    for i in range(127, -1, -1):
        if (y >> i) & 1:
            r ^= x
        x = (x >> 1) ^ R if x & 1 else x >> 1
    return r


def aes128_gcm_encrypt(key, iv, plaintext, aad=b""):
    rk = _aes_expand(key)
    h = int.from_bytes(_aes_block(rk, bytes(16)), "big")
    j0 = iv + b"\x00\x00\x00\x01"
    out = bytearray()
    ctr = int.from_bytes(j0, "big")
    for i in range(0, len(plaintext), 16):
        ctr = (ctr & ~0xFFFFFFFF) | ((ctr + 1) & 0xFFFFFFFF)
        ks = _aes_block(rk, ctr.to_bytes(16, "big"))
        out += bytes(a ^ b for a, b in zip(plaintext[i:i + 16], ks))
    def blocks(b):
        b = b + bytes(-len(b) % 16)
        return [int.from_bytes(b[i:i + 16], "big") for i in range(0, len(b), 16)]
    g = 0
    for blk in blocks(aad) + blocks(bytes(out)) + [((len(aad) * 8) << 64) | (len(out) * 8)]:
        g = _gf_mul(g ^ blk, h)
    tag = bytes(a ^ b for a, b in zip(g.to_bytes(16, "big"), _aes_block(rk, j0)))
    return bytes(out) + tag


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64u_dec(s):
    s = str(s or "")
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def webpush_encrypt(ua_public, auth_secret, plaintext, as_priv=None, salt=None):
    """RFC 8291 (aes128gcm): ein Datensatz, Ergebnis ist der fertige Nachrichtenkörper."""
    ua_pt = ec_pub_point(ua_public)
    d, as_pt = ec_keypair(as_priv)
    as_public = ec_pub_bytes(as_pt)
    shared = _ec_mul(d, ua_pt)[0].to_bytes(32, "big")
    salt = salt or secrets.token_bytes(16)
    hm = lambda k, m: hmac.new(k, m, hashlib.sha256).digest()
    ikm = hm(hm(auth_secret, shared), b"WebPush: info\x00" + ua_public + as_public + b"\x01")
    prk = hm(salt, ikm)
    cek = hm(prk, b"Content-Encoding: aes128gcm\x00\x01")[:16]
    nonce = hm(prk, b"Content-Encoding: nonce\x00\x01")[:12]
    header = salt + (4096).to_bytes(4, "big") + bytes([len(as_public)]) + as_public
    return header + aes128_gcm_encrypt(cek, nonce, plaintext + b"\x02")


PUSH_HOSTS = (".googleapis.com", ".push.apple.com", ".push.services.mozilla.com", ".notify.windows.com", ".windows.com")


def push_endpoint_ok(url):
    """Nur https-Adressen der bekannten Push-Dienste (sonst könnte jemand den Server an beliebige Adressen schicken lassen)."""
    u = urlparse(str(url or ""))
    host = (u.hostname or "").lower()
    return u.scheme == "https" and len(url) < 1000 and any(host.endswith(h) or host == h.lstrip(".") for h in PUSH_HOSTS)


def vapid_keys(conn):
    raw = secret_get(conn, "vapid_d")
    if not raw:
        d, _ = ec_keypair()
        raw = format(d, "064x")
        secret_set(conn, "vapid_d", raw)
    d = int(raw, 16)
    return d, ec_pub_bytes(_ec_mul(d, _EC_G))


def push_send_one(sub_row, payload, d, pub, contact):
    u = urlparse(sub_row["endpoint"])
    claims = {"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 12 * 3600, "sub": contact}
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode()) + "." + b64u(json.dumps(claims, separators=(",", ":")).encode())
    jwt = head + "." + b64u(ec_sign(d, head.encode()))
    body = webpush_encrypt(b64u_dec(sub_row["p256dh"]), b64u_dec(sub_row["auth"]), json.dumps(payload, ensure_ascii=False).encode())
    req = urllib.request.Request(sub_row["endpoint"], data=body, method="POST", headers={
        "Authorization": f"vapid t={jwt}, k={b64u(pub)}", "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
        "TTL": "86400", "Urgency": "high"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa
        return 0


def send_push(user_ids, title, body, url="/hub", tag="hub", kind="show"):
    """Push an alle Geräte der Personen. Abgelaufene Abos (404/410) werden entfernt. Gibt die Zahl erfolgreicher Zustellungen zurück."""
    ids = [int(i) for i in user_ids if i]
    if not ids:
        return 0
    with db() as conn:
        subs = conn.execute(f"SELECT * FROM push_subs WHERE user_id IN ({','.join('?' for _ in ids)})", ids).fetchall()
        if not subs:
            return 0
        d, pub = vapid_keys(conn)
        user = secret_get(conn, "smtp_user") or ""
    contact = f"mailto:{user}" if "@" in user else (SITE_URL if SITE_URL.startswith("https://") else "mailto:hub@example.org")
    payload = {"title": title[:120], "body": body[:300], "url": url if url.startswith("/") else "/hub", "tag": tag[:60], "type": kind}
    with db() as conn:
        badges = {i: badge_for(conn, i) for i in ids}
    ok = 0
    for row in subs:
        st = push_send_one(row, {**payload, "badge": badges.get(row["user_id"], 0)}, d, pub, contact)
        with db() as conn:
            if st in (404, 410):
                conn.execute("DELETE FROM push_subs WHERE id=?", (row["id"],))
            elif 200 <= st < 300:
                ok += 1
                conn.execute("UPDATE push_subs SET last_ok=? WHERE id=?", (datetime.now().isoformat(timespec="seconds"), row["id"]))
    return ok


def send_push_async(*a, **kw):
    threading.Thread(target=lambda: send_push(*a, **kw), daemon=True).start()


# ---------------------------------------------------------------------------
# Mail-Aufgaben: Mails aus dem Postfach Personen zuweisen (Push, Mail, Hinweis im Hub). Die Person darf genau diese Mail lesen und beantworten.
# Signatur: eine Vorlage für alle (Einstellung mail_signature), Name aus dem Konto, Rolle aus users.mail_role.
# ---------------------------------------------------------------------------
# Signatur nach dem Signatur-Paket des Vereins (web/assets/signatur: signatur.html, signatur.txt, Bilder, README.md).
# Platzhalter {{NAME}} (aus dem Konto) und {{ROLLE}} (Gruppen ohne „Wartung“ oder „Rolle in der Signatur“ unter Konten).
# Bilder liegen öffentlich unter https://www.amisia-stern.de/signatur/... (Route /signatur/<datei>.png), keine eingebetteten Bilder.
SIG_DIR = website.WEB / "assets" / "signatur"
SIG_URL = "https://www.amisia-stern.de/signatur/"   # so steht es in signatur.html
SIG_SKIP_GROUPS = {"wartung"}   # technische Gruppen nicht als Rolle zeigen


def signature_role(conn, uid):
    u = conn.execute("SELECT mail_role FROM users WHERE id=?", (uid,)).fetchone()
    if u and (u["mail_role"] or "").strip():
        return u["mail_role"].strip()
    groups = [r["name"] for r in conn.execute("SELECT g.name FROM user_groups ug JOIN groups g ON g.id = ug.group_id WHERE ug.user_id=? ORDER BY g.sort, g.name", (uid,))
              if (r["name"] or "").strip().lower() not in SIG_SKIP_GROUPS]
    return " | ".join(groups)


def signature_parts(conn, uid, email="", preview=False):
    """(Text, HTML) der Signatur. preview=True: Bilder relativ (/signatur/...), damit die Vorschau auch ohne Domain lädt."""
    try:
        tpl_html = (SIG_DIR / "signatur.html").read_text(encoding="utf-8")
        tpl_text = (SIG_DIR / "signatur.txt").read_text(encoding="utf-8")
    except OSError:
        return "", ""
    u = conn.execute("SELECT display_name, username, sig_phone FROM users WHERE id=?", (uid,)).fetchone()
    name = ((u["display_name"] or u["username"]) if u else "").strip()
    role = signature_role(conn, uid)
    phone = ((u["sig_phone"] or "") if u else "").strip()
    tel = re.sub(r"[^\d+]", "", phone)
    tel = "+49" + tel[1:] if tel.startswith("0") and not tel.startswith("00") else tel   # Link zum Anrufen im internationalen Format
    row = (f'<tr><td valign="middle" style="padding:0 8px 6px 0;"><a href="tel:{html_esc(tel)}" style="text-decoration:none;"><img src="{SIG_URL}icon-phone.png" width="18" height="18" alt="" style="display:block;border:0;"></a></td>'
           f'<td valign="middle" style="padding:0 0 6px 0;font-size:13px;line-height:18px;"><a href="tel:{html_esc(tel)}" style="color:#333333;text-decoration:none;">{html_esc(phone)}</a></td></tr>') if phone else ""
    html = (re.sub(r"<!--.*?-->\s*", "", tpl_html, flags=re.S).replace("{{NAME}}", html_esc(name)).replace("{{ROLLE}}", html_esc(role))
            .replace("{{TELEFON_ZEILE}}", row).strip())
    if preview:
        html = html.replace(SIG_URL, "/signatur/")
    lines = []
    for line in tpl_text.replace("\r\n", "\n").split("\n"):
        if "{{ROLLE}}" in line and not role and not line.replace("{{ROLLE}}", "").strip():
            continue   # Zeile nur für die Rolle: weglassen, wenn keine Rolle da ist
        if "{{TELEFON}}" in line and not phone:
            continue   # ohne Nummer keine Telefonzeile
        lines.append(line.replace("{{NAME}}", name).replace("{{ROLLE}}", role).replace("{{TELEFON}}", phone))
    return "\n".join(lines).strip(), html


def mail_signature_for(conn, uid, email=""):
    """Textfassung der Signatur (Vorschau und Mailprogramme ohne HTML)."""
    return signature_parts(conn, uid, email or "info@amisia-stern.de")[0]


def user_mail_cfg(conn, uid, base=None, row=None):
    """Mail-Konto einer Person (oder Zeile `row` aus mail_accounts) im Format von smtp_config(), sonst None (dann gilt das Vereinspostfach)."""
    r = row or conn.execute("SELECT m.* FROM mail_accounts m JOIN mail_links a ON a.account_id=m.id WHERE a.user_id=? ORDER BY lower(m.address), m.id", (uid,)).fetchone()
    if not r or not (r["smtp_host"] and r["username"] and r["password"]):
        return None
    u = conn.execute("SELECT display_name, username FROM users WHERE id=?", (uid,)).fetchone() if uid else None
    base = base or smtp_config()
    name = (u["display_name"] or u["username"]) if u else ""
    club = get_setting(conn, "club_name") or "SV Amisia Wolthusen"
    if name and club.lower() not in name.lower():   # Absender: „Silas Grabowski | SV Amisia Wolthusen“
        name = f"{name} | {club}"
    cfg = {"smtp_host": r["smtp_host"], "smtp_port": r["smtp_port"] or "", "smtp_security": r["smtp_security"] or "starttls",
           "smtp_user": r["username"], "smtp_password": r["password"], "hub_url": base.get("hub_url", ""), "public_url": base.get("public_url", ""),
           "smtp_from": f"{name} <{r['address'] or r['username']}>" if name else (r["address"] or r["username"]), "imap_host": r["imap_host"] or ""}
    host = (cfg["imap_host"] or "").strip() or re.sub(r"^smtp\.", "imap.", cfg["smtp_host"])
    cfg["imap"] = host if re.fullmatch(r"[A-Za-z0-9.-]{3,200}", host or "") else ""
    return cfg


def user_mail_boxes(conn, uid, base=None):
    """Alle vollständig hinterlegten Mail-Konten einer Person als [(Schlüssel 'acc<id>', Zugang)]."""
    rows = conn.execute("SELECT m.* FROM mail_accounts m JOIN mail_links a ON a.account_id=m.id WHERE a.user_id=? ORDER BY lower(m.address), m.id", (uid,)).fetchall()
    return [(f"acc{r['id']}", c) for r in rows if (c := user_mail_cfg(conn, uid, base, row=r))]


def mail_addr(c):
    return parseaddr(mail_sender(c)[0])[1] or c["smtp_user"]


def pf_senders(conn, user, can_info, box="info"):
    """Mögliche Absender im Hub: Vereinspostfach (mit Recht) und die eigenen Mail-Konten. Liefert (Liste, Vorgabe, Zugänge)."""
    info = postfach_config()
    mine = user_mail_boxes(conn, user["id"], info)
    out, cfgs = [], {"info": info}
    if can_info:
        out.append({"key": "info", "address": mail_addr(info)})
    for k, c in mine:
        out.append({"key": k, "address": mail_addr(c)})
        cfgs[k] = c
    if not out:
        out.append({"key": "info", "address": mail_addr(info)})
    keys = [x["key"] for x in out]
    default = box if box in keys else ("info" if can_info or not mine else mine[0][0])
    return out, default, cfgs


def own_mail_address(conn, uid):
    """Adresse des eigenen Postfachs eines Kontos (leer, wenn keins vollständig hinterlegt ist)."""
    c = user_mail_cfg(conn, uid)
    return (parseaddr(mail_sender(c)[0])[1] or c["smtp_user"]) if c else ""


def mail_account_check(cfg):
    """Prüft Anmeldung an SMTP und IMAP eines Zugangs, ohne etwas zu verschicken."""
    import smtplib
    import ssl
    res = {}
    try:
        port = int(cfg["smtp_port"] or (465 if cfg["smtp_security"] == "ssl" else 587))
        sec = {465: "ssl", 587: "starttls"}.get(port, cfg["smtp_security"])
        ctx = ssl.create_default_context()
        s_ = smtplib.SMTP_SSL(cfg["smtp_host"], port, timeout=20, context=ctx) if sec == "ssl" else smtplib.SMTP(cfg["smtp_host"], port, timeout=20)
        with s_:
            if sec == "starttls":
                s_.starttls(context=ctx)
            s_.login(cfg["smtp_user"], cfg["smtp_password"])
        res["smtp"] = "ok"
    except Exception as e:  # noqa
        res["smtp"] = f"{type(e).__name__}: {e}"[:200]
    try:
        m, _ = postfach_open(cfg)
        with contextlib.suppress(Exception):
            m.logout()
        res["imap"] = "ok"
    except Exception as e:  # noqa
        res["imap"] = str(e)[:200]
    res["ok"] = res["smtp"] == "ok"
    return res


# ---------------------------------------------------------------------------
# Neue Mails im Posteingang: Abruf im Hintergrund (pf_poll_loop), Push an die Gruppen aus pf_notify_groups.
# Eine Mail gilt als erledigt, sobald jemand im Hub antwortet, weiterleitet, zuweist, löscht oder „Erledigt“ klickt
# (auch Antworten aus einem anderen Mailprogramm: Kennzeichen \Answered). Dann geht an alle anderen eine Erledigt-Meldung,
# die die alte Meldung ersetzt und sich selbst schließt. Die Zahl am App-Symbol = offene eigene Aufgaben + neue Mails.
# ---------------------------------------------------------------------------
PF_POLL_SECONDS = max(30, int(ENV("TMH_PF_POLL", "120")))


def pf_notify_groups(conn):
    try:
        v = json.loads(get_setting(conn, "pf_notify_groups") or "[]")
        return [str(x) for x in v] if isinstance(v, list) else []
    except ValueError:
        return []


def pf_recipients(conn):
    names = [n.lower() for n in pf_notify_groups(conn)]
    if not names:
        return []
    rows = conn.execute(f"SELECT DISTINCT u.id FROM users u JOIN user_groups ug ON ug.user_id = u.id JOIN groups g ON g.id = ug.group_id "
                        f"WHERE u.active=1 AND lower(g.name) IN ({','.join('?' for _ in names)})", names).fetchall()
    return [r["id"] for r in rows]


def badge_for(conn, uid):
    n = conn.execute("SELECT COUNT(*) FROM mail_tasks WHERE user_id=? AND status='offen'", (uid,)).fetchone()[0]
    if uid in pf_recipients(conn):
        n += conn.execute("SELECT COUNT(*) FROM pf_inbox WHERE status='neu'").fetchone()[0]
    return n


def pf_mark_handled(folder, uid, user, action):
    """Mail als erledigt markieren und den anderen Empfängern die Erledigt-Meldung schicken."""
    with db() as conn:
        row = conn.execute("SELECT * FROM pf_inbox WHERE folder=? AND uid=? AND status='neu'", (folder, int(uid))).fetchone()
        if not row:
            return False
        conn.execute("UPDATE pf_inbox SET status='erledigt', handled_by=?, handled_at=?, action=? WHERE id=?",
                     (user["id"] if user else None, datetime.now().isoformat(timespec="seconds"), action, row["id"]))
        others = [i for i in pf_recipients(conn) if not user or i != user["id"]]
    who = (user.get("display_name") or user.get("username")) if user else "jemand"
    send_push_async(others, f"Erledigt: {row['subject'][:80]}", f"{who} hat die Mail {action}.", "/hub#/postfach", f"mail-{row['id']}", "done")
    return True


MAIL_QUOTA_BYTES = 5 * 1024 ** 3          # gebuchte Größe je Postfach (5 GB), falls der Mailserver keine Grenze meldet
MAIL_QUOTA_WARN_FREE = 0.2 * 1024 ** 3     # Warnung, wenn weniger frei ist (bei 5 GB also ab 4,8 GB belegt)


def pf_quota(m):
    """Belegter Speicher des Postfachs über IMAP QUOTA (RFC 2087). None, wenn der Server das nicht meldet."""
    try:
        typ, data = m.getquotaroot("INBOX")
    except Exception:  # noqa
        return None
    hit = re.search(r"STORAGE (\d+) (\d+)", repr(data)) if typ == "OK" else None
    if not hit:
        return None
    used, limit = int(hit.group(1)) * 1024, int(hit.group(2)) * 1024   # Angaben in KB
    limit = limit or MAIL_QUOTA_BYTES
    return {"used": used, "limit": limit, "warn": limit - used <= MAIL_QUOTA_WARN_FREE}


NL_CONFIRM_HOURS = 48   # so lange gilt der Bestätigungslink der Newsletter-Anmeldung


def nl_key(conn):
    """Geheimer Schlüssel für die Abmeldelinks (wird beim ersten Mal erzeugt)."""
    k = secret_get(conn, "nl_key")
    if not k:
        k = secrets.token_hex(32)
        secret_set(conn, "nl_key", k)
    return k


def nl_token(key, sid):
    """Abmeldelink-Token: Abonnent-Nummer plus Signatur, nichts davon muss gespeichert werden."""
    return f"{sid}-" + hmac.new(key.encode(), f"nl-abmelden:{sid}".encode(), hashlib.sha256).hexdigest()[:32]


def nl_token_id(token):
    m = re.fullmatch(r"(\d{1,9})-([0-9a-f]{32})", token or "")
    if not m:
        return None
    with db() as conn:
        key = nl_key(conn)
    return int(m.group(1)) if hmac.compare_digest(nl_token(key, int(m.group(1))), token) else None


def nl_ids(v):
    try:
        x = json.loads(v or "[]")
    except ValueError:
        return []
    return [int(i) for i in x if str(i).isdigit()] if isinstance(x, list) else []


def nl_public_groups(conn):
    return [{"id": r["id"], "name": r["name"] or "", "description": r["description"] or ""} for r in conn.execute(
        "SELECT id, name, description FROM nl_groups WHERE IFNULL(public, 1)=1 AND IFNULL(active, 1)=1 ORDER BY IFNULL(sort, 0), name")]


def nl_pending(token):
    """Gültige, noch offene Bestätigung zu diesem Link?"""
    h = hashlib.sha256((token or "").encode()).hexdigest()
    with db() as conn:
        return bool(conn.execute("SELECT 1 FROM nl_subscribers WHERE confirm_hash=? AND confirm_expires > ?", (h, time.time())).fetchone())


def nl_mail(club, foot, subject, body, link):
    """Newsletter als Text und HTML (Logo, Absätze, Fuß mit Anschrift und Abmeldelink)."""
    text = body.rstrip() + f"\n\n--\n{club}\n{foot}\nDu bekommst diesen Newsletter, weil du ihn auf unserer Webseite abonniert hast.\nAbmelden: {link}\n"
    paras = "".join('<p style="margin:0 0 14px">' + html_esc(p.strip()).replace("\n", "<br>") + "</p>" for p in re.split(r"\n\s*\n", body.strip()) if p.strip())
    html = ('<div style="background:#f2f0eb;padding:20px 0"><div style="max-width:600px;margin:0 auto;background:#ffffff;font-family:Arial,Helvetica,sans-serif;color:#1a1a1a">'
            f'<div style="padding:18px 24px;border-bottom:4px solid #3D2F96"><img src="{SIG_URL}wappen.png" width="72" height="80" alt="{html_esc(club)}" style="display:block;border:0"></div>'
            f'<div style="padding:24px;font-size:15px;line-height:23px"><h1 style="font-size:22px;line-height:28px;margin:0 0 16px">{html_esc(subject)}</h1>{paras}</div>'
            f'<div style="padding:16px 24px;font-size:12px;line-height:18px;color:#777777;border-top:1px solid #eeeeee">{html_esc(foot)}<br>'
            f'Du bekommst diesen Newsletter, weil du ihn auf unserer Webseite abonniert hast. <a href="{html_esc(link)}" style="color:#3D2F96">Newsletter abbestellen</a></div></div></div>')
    return text, html


def nl_recipients(conn, gids):
    """Aktive Abonnenten der Gruppen (leere Liste = alle aktiven)."""
    rows = conn.execute("SELECT id, email, groups FROM nl_subscribers WHERE status='aktiv' ORDER BY id").fetchall()
    return [r for r in rows if not gids or set(nl_ids(r["groups"])) & set(gids)]


def nl_send_issue(iid, user, base):
    """Ausgabe im Hintergrund an jeden Empfänger einzeln, mit persönlichem Abmeldelink (auch als List-Unsubscribe für Mailprogramme)."""
    with db() as conn:
        it = conn.execute("SELECT * FROM nl_issues WHERE id=?", (iid,)).fetchone()
        subs = nl_recipients(conn, nl_ids(it["groups"]))
        key, club, foot = nl_key(conn), get_setting(conn, "club_name") or "SV Amisia Wolthusen", letter_text(conn, "footer")
    cfg, ok, failed = smtp_config(), 0, 0
    for r in subs:
        link = f"{base}/newsletter/abmelden/{nl_token(key, r['id'])}"
        text, html = nl_mail(club, foot, it["subject"], it["body"], link)
        err = send_mail(cfg, r["email"], it["subject"], text, footer=False, html=html,
                        headers={"List-Unsubscribe": f"<{link}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
        ok, failed = (ok, failed + 1) if err else (ok + 1, failed)
        time.sleep(1)   # Mailserver schonen (Versandgrenzen der Anbieter)
    with db() as conn:
        conn.execute("UPDATE nl_issues SET status='gesendet', sent_at=?, sent_count=?, failed=? WHERE id=?", (datetime.now().isoformat(timespec="seconds"), ok, failed, iid))
        audit(conn, user, "Newsletter verschickt", "nl_issues", iid, it["subject"][:100], {"Empfänger": ["", f"{ok} von {len(subs)}"]})
    send_push_async([user["id"]], "Newsletter verschickt", f"{it['subject'][:60]}: {ok} von {len(subs)} raus" + (f", {failed} fehlgeschlagen" if failed else ""), "/hub#/newsletter", "nl-done")


PF_BULK_MAX = 200   # höchstens so viele Empfänger beim Einzelversand (Verteiler)


def pf_send_bulk(sender, rcpts, subject, text, html, headers, user):
    """Einzelmails an einen Verteiler im Hintergrund: nacheinander mit kurzer Pause (Versandgrenzen der Anbieter),
    Kopien unter „Gesendet“, am Ende Protokoll und Push an die absendende Person."""
    import imaplib
    ok, failed, raws = 0, [], []
    for a in rcpts:
        o = {}
        if send_mail(sender, a, subject, text, footer=False, headers=headers, out=o, html=html):
            failed.append(a)
        else:
            ok += 1
            raws.append(o.get("raw"))
        time.sleep(1)
    try:
        box = postfach_open(sender)[0]
        try:
            sent = pf_role_folder(box, "sent")
            for raw in raws if sent else []:
                if raw:
                    box.append(imap_quote(sent), "(\\Seen)", imaplib.Time2Internaldate(time.time()), raw)
        finally:
            with contextlib.suppress(Exception):
                box.logout()
    except Exception:  # noqa
        pass
    with db() as conn:
        audit(conn, user, "Mail gesendet", "postfach", None, subject[:100],
              {"An": f"{ok} von {len(rcpts)} einzeln" + (f", nicht verschickt: {', '.join(failed[:10])}" if failed else "")})
    send_push_async([user["id"]], "Verteiler verschickt", f"{subject[:60]}: {ok} von {len(rcpts)} Mails raus" + (f", {len(failed)} fehlgeschlagen" if failed else ""),
                    "/hub#/postfach", "bulk-done")


def pf_drop_draft(m, folder, uid):
    """Alten Entwurf entfernen, aber nur im Ordner „Entwürfe“ (sonst nichts löschen)."""
    if not folder or folder != pf_role_folder(m, "drafts") or not str(uid).isdigit():
        return False
    pf_select(m, folder, readonly=False)
    m.uid("STORE", str(uid), "+FLAGS", "(\\Deleted)")
    try:
        m.uid("EXPUNGE", str(uid))   # nur diese Mail (UIDPLUS)
    except Exception:  # noqa
        m.expunge()
    return True


def pf_mark_all_handled(folder, user):
    """Alle offenen Mails eines Ordners im Vereinspostfach als erledigt markieren (ohne Verschieben). Liefert die Anzahl."""
    now = datetime.now().isoformat(timespec="seconds")
    with db() as conn:
        rows = conn.execute("SELECT id, subject FROM pf_inbox WHERE folder=? AND status='neu'", (folder,)).fetchall()
        conn.execute("UPDATE pf_inbox SET status='erledigt', handled_by=?, handled_at=?, action='als erledigt markiert (alle)' WHERE folder=? AND status='neu'",
                     (user["id"], now, folder))
        others = [i for i in pf_recipients(conn) if i != user["id"]]
    for r in rows[:50]:   # offene Mitteilungen auf den Handys der anderen schließen (Push-Art done)
        send_push_async(others, f"Erledigt: {r['subject'][:80]}", "als erledigt markiert", "/hub#/postfach", f"mail-{r['id']}", "done")
    return len(rows)


def pf_poll():
    """Neue ungelesene Mails im Posteingang melden, Antworten von außerhalb erkennen. Beim ersten Lauf nur den Stand merken."""
    from email import policy
    from email.parser import BytesHeaderParser
    cfg = postfach_config()
    if not (cfg["imap"] and cfg["smtp_user"] and cfg["smtp_password"]):
        return 0
    m, _ = postfach_open(cfg)
    new_rows = []
    try:
        typ, data = m.select("INBOX", readonly=True)
        uv = (m.untagged_responses.get("UIDVALIDITY") or [b""])[0]
        uv = uv.decode() if isinstance(uv, bytes) else str(uv)
        with db() as conn:
            last = int(secret_get(conn, "pf_last_uid") or 0)
            known_uv = secret_get(conn, "pf_uidvalidity") or ""
        typ, data = m.uid("SEARCH", None, "ALL")
        uids = [int(x) for x in (data[0] or b"").split()]
        if not known_uv or known_uv != uv:   # erster Lauf oder Postfach neu aufgebaut: nichts Altes melden
            with db() as conn:
                secret_set(conn, "pf_uidvalidity", uv)
                secret_set(conn, "pf_last_uid", str(max(uids or [0])))
            return 0
        fresh = [u for u in uids if u > last]
        if fresh:
            typ, data = m.uid("FETCH", ",".join(map(str, fresh[-50:])), "(UID FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID)])")
            for x in data or []:
                if not isinstance(x, tuple):
                    continue
                um = re.search(rb"UID (\d+)", x[0])
                if not um or b"\\Seen" in x[0]:
                    continue
                h = BytesHeaderParser(policy=policy.compat32).parsebytes(x[1])
                new_rows.append((int(um.group(1)), pf_head(h.get("Subject")) or "(ohne Betreff)", pf_head(h.get("From")), (h.get("Message-ID") or "")[:300]))
            with db() as conn:
                secret_set(conn, "pf_last_uid", str(max(fresh)))
        # offene Mails: von außen beantwortet oder verschwunden?
        with db() as conn:
            open_rows = conn.execute("SELECT * FROM pf_inbox WHERE folder='INBOX' AND status='neu' AND uidvalidity=?", (uv,)).fetchall()
        done = []
        if open_rows:
            typ, data = m.uid("FETCH", ",".join(str(r["uid"]) for r in open_rows), "(UID FLAGS)")
            flags = {}
            for x in data or []:
                line = x[0] if isinstance(x, tuple) else x
                if isinstance(line, bytes):
                    um = re.search(rb"UID (\d+)", line)
                    if um:
                        flags[int(um.group(1))] = line
            for r in open_rows:
                f = flags.get(r["uid"])
                if f is None:
                    done.append((r, "gelöscht oder verschoben"))
                elif b"\\Answered" in f:
                    done.append((r, "beantwortet"))
    finally:
        with contextlib.suppress(Exception):
            m.logout()
    now = datetime.now().isoformat(timespec="seconds")
    with db() as conn:
        for uid, subj, frm, mid in new_rows:
            conn.execute("INSERT INTO pf_inbox (folder, uid, uidvalidity, message_id, subject, sender, received, status, notified) VALUES ('INBOX',?,?,?,?,?,?, 'neu', ?)",
                         (uid, uv, mid, subj[:250], frm[:250], now, now))
        ids = {uid: conn.execute("SELECT id FROM pf_inbox WHERE folder='INBOX' AND uid=? ORDER BY id DESC", (uid,)).fetchone()["id"] for uid, *_ in new_rows}
        rcpt = pf_recipients(conn)
    if new_rows:
        if len(new_rows) <= 3:
            for uid, subj, frm, _ in new_rows:
                send_push(rcpt, f"Neue Mail: {subj[:80]}", f"von {pf_name(frm)}", f"/hub#/postfach/m/INBOX/{uid}", f"mail-{ids[uid]}")
        else:
            send_push(rcpt, f"{len(new_rows)} neue Mails im Postfach", ", ".join(s_[:40] for _, s_, *_ in new_rows[:3]) + " ...", "/hub#/postfach", "mail-sammel")
    for r, action in done:
        pf_mark_handled("INBOX", r["uid"], None, action)
    return len(new_rows)


def pf_poll_loop():
    while True:
        threading.Event().wait(PF_POLL_SECONDS)
        try:
            pf_poll()
        except Exception as e:  # noqa
            print("Postfach-Abruf:", repr(e)[:200])


def mail_task_row(conn, t):
    names = {r["id"]: r["display_name"] or r["username"] for r in conn.execute("SELECT id, display_name, username FROM users")}
    d = dict(t)
    d["user_name"], d["by_name"] = names.get(t["user_id"], "?"), names.get(t["assigned_by"], "?")
    return d


def mail_task_access(conn, user_id, folder, uid):
    return bool(conn.execute("SELECT 1 FROM mail_tasks WHERE user_id=? AND folder=? AND uid=?", (user_id, folder, int(uid))).fetchone())


def smtp_config():
    with db() as conn:
        cfg = {k: secret_get(conn, k) for k in (*SMTP_KEYS, "smtp_password", "public_url")}
    cfg["hub_url"] = (cfg["hub_url"] or SITE_URL or cfg["public_url"] or "").rstrip("/")
    return cfg


def mail_sender(cfg):
    """Absender-Kopfzeile und Absender-Adresse für den Mailserver. Steht unter „Absender“ nur ein Name (z. B. „SV Amisia Wolthusen“),
    wird die Adresse des Postfachs (Benutzername) dazugenommen: „SV Amisia Wolthusen <info@amisia-stern.de>“.
    Viele Anbieter (z. B. Strato) verlangen, dass die Absenderadresse zum angemeldeten Postfach passt."""
    from email.utils import formataddr, parseaddr
    user = (cfg.get("smtp_user") or "").strip()
    raw = (cfg.get("smtp_from") or "").strip()
    name, addr = parseaddr(raw)
    if "@" not in addr:   # nur ein Name eingetragen
        name, addr = raw, user
    if "@" not in addr:
        addr = user
    envelope = user if "@" in user else addr
    return (formataddr((name, addr)) if name and name != addr else addr), envelope


def send_mail(cfg, to, subject, body, footer=True, attachments=(), headers=None, cc=(), out=None, html=None, related=()):
    """Schickt eine Klartext-Mail (optional mit Anhängen: (Dateiname, Bytes, Haupttyp, Untertyp)). Liefert None oder eine Fehlermeldung."""
    import smtplib
    import ssl
    from email.message import EmailMessage
    from email.utils import formatdate, make_msgid
    msg = EmailMessage()
    msg["From"], envelope = mail_sender(cfg)
    msg["To"] = to
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    for k, v in (headers or {}).items():
        if v:
            msg[k] = v
    msg["Date"] = formatdate(localtime=True)   # ohne Datum und Message-ID sortieren Yahoo, Gmail und Co. Mails gern aus
    msg["Message-ID"] = make_msgid(domain=envelope.rsplit("@", 1)[-1] if "@" in envelope else None)
    msg.set_content(body + ((f"\n\nZum Hub: {cfg['hub_url']}/hub" if cfg["hub_url"] else "") +
                            "\n\nWelche Nachrichten du bekommst, stellst du im Hub unter „Mein Profil“ ein." if footer else ""))
    if html:   # HTML-Fassung (z. B. mit Signatur), Bilder eingebettet über cid
        msg.add_alternative(html, subtype="html")
        hpart = msg.get_payload()[-1]
        for cid, data in related:
            hpart.add_related(data, maintype="image", subtype="png", cid=f"<{cid}>", disposition="inline")
    for fname, data, maintype, subtype in attachments:
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=fname)
    try:
        port = int(cfg["smtp_port"] or (465 if cfg["smtp_security"] == "ssl" else 587))
        security = cfg["smtp_security"]
        if security != "none":   # Standardports haben feste Verschlüsselung: 465 = SSL, 587 = STARTTLS (häufige Verwechslung)
            security = {465: "ssl", 587: "starttls"}.get(port, security)
        ctx = ssl.create_default_context()
        if security == "ssl":
            s = smtplib.SMTP_SSL(cfg["smtp_host"], port, timeout=30, context=ctx)
        else:
            s = smtplib.SMTP(cfg["smtp_host"], port, timeout=30)
            if security != "none":
                s.starttls(context=ctx)
        with s:
            if cfg["smtp_user"]:
                # Nur der erste Anmeldeweg, sonst verdeckt Gmail die Ablehnung mit "Connection unexpectedly closed"
                s.ehlo_or_helo_if_needed()
                s.user, s.password = cfg["smtp_user"], cfg["smtp_password"] or ""
                if cfg["smtp_host"].lower().endswith(("gmail.com", "googlemail.com")):
                    s.password = "".join(s.password.split())   # App-Passwort wird mit Leerzeichen angezeigt: "abcd efgh ijkl mnop"
                mech = next((m for m in ("PLAIN", "LOGIN") if m in s.esmtp_features.get("auth", "").upper().split()), None)
                if mech:
                    s.auth(mech, s.auth_plain if mech == "PLAIN" else s.auth_login)
                else:
                    s.login(cfg["smtp_user"], cfg["smtp_password"])
            refused = s.send_message(msg, from_addr=envelope)
        if out is not None:
            out["raw"] = msg.as_bytes()
        if refused:
            return "Empfänger abgelehnt: " + ", ".join(f"{k} ({v[0]})" for k, v in refused.items())
        return None
    except smtplib.SMTPAuthenticationError as e:
        return (f"Anmeldung abgelehnt ({e.smtp_code}). Benutzername oder Passwort stimmen nicht. "
                "Bei Gmail die komplette Adresse und ein App-Passwort verwenden (Bestätigung in zwei Schritten muss an sein).")
    except Exception as e:  # noqa
        return f"{type(e).__name__}: {e}"


def notify(kind, subject, body, once_key=None):
    """Mail an alle, die diese Nachricht abonniert haben und die Rechte dafür haben. once_key: nur einmal verschicken."""
    cfg = smtp_config()
    if not cfg["smtp_host"]:
        return
    with db() as conn:
        if once_key:
            if conn.execute("SELECT 1 FROM notify_sent WHERE key=?", (once_key,)).fetchone():
                return
            conn.execute("INSERT INTO notify_sent (key, time) VALUES (?, ?)", (once_key, datetime.now().isoformat(timespec="seconds")))
        users = conn.execute("SELECT id, is_admin, email, notify FROM users WHERE active=1 AND IFNULL(email,'') != ''").fetchall()
        to = []
        for u in users:
            kinds = notify_kinds_of(u)
            if kind in kinds and notify_allowed(effective_perms(conn, row_dict(u)), kind):
                to.append(u["email"])
    errors = [e for e in (send_mail(cfg, addr, f"Wolthusen Hub: {subject}", body) for addr in to) if e]   # einzeln, keine fremden Adressen sichtbar
    with db() as conn:
        secret_set(conn, "smtp_last_error", f"{datetime.now():%d.%m.%Y %H:%M} {errors[0]}" if errors else "")


def notify_async(*args, **kw):
    threading.Thread(target=lambda: notify(*args, **kw), daemon=True).start()


def notify_publish(kind_label, title, state, log):
    if state in ("fehler", "teilweise", "verpasst"):
        notify_async("post_failed", f"{kind_label} „{title}“ hat nicht geklappt", f"{kind_label}: {title}\n{log}\n\nIm Hub unter Medien > Auto-Posting kannst du es erneut versuchen.")
    elif state == "gepostet":
        notify_async("post_done", f"{kind_label} „{title}“ ist online", f"{kind_label}: {title}\n{log}")


MAG_SECTIONS_NEEDED = ("Vorwort", "Behind the Helmet", "Spielbericht", "Schiedsrichter", "Fan-Info", "Jugend", "Rückseite")


def notify_tick():
    """Erinnerungen (einmal pro Stichtag) und gesammelte neue Bestellungen."""
    now = datetime.now()
    today = now.date()
    if now.hour >= NOTIFY_HOUR:
        with db() as conn:
            mags =conn.execute("SELECT * FROM magazines WHERE IFNULL(status,'') != 'Fertig' AND IFNULL(deadline,'') != ''").fetchall()
            mag_open = {}
            for m in mags:
                have = {r["section"] for r in conn.execute("SELECT DISTINCT section FROM magazine_pages WHERE magazine_id=?", (m["id"],))}
                miss = [s for s in MAG_SECTIONS_NEEDED if s not in have]
                if not (m["sponsor_ids"] or "").strip("[] "):
                    miss.insert(0, "Sponsoren")
                if not m["game_id"]:
                    miss.append("Heimspiel")
                mag_open[m["id"]] = miss
            apparel = conn.execute("SELECT * FROM apparel WHERE IFNULL(deadline,'') != ''").fetchall()
            counts = {r["apparel_id"]: (r["n"], r["pcs"]) for r in conn.execute(
                "SELECT apparel_id, COUNT(*) AS n, SUM(IFNULL(quantity,1)) AS pcs FROM apparel_orders GROUP BY apparel_id")}
        for m in mags:
            d = (datetime.strptime(m["deadline"], "%Y-%m-%d").date() - today).days
            label = " ".join(x for x in (m["title"], m["number"], m["season"]) if x)
            if d in (7, 3, 1, 0) and mag_open[m["id"]]:
                when = "heute" if d == 0 else "morgen" if d == 1 else f"in {d} Tagen"
                notify("magazine_deadline", f"Stadionheft {label}: Redaktionsschluss {when}",
                       f"Redaktionsschluss für „{label}“ ist {when} ({m['deadline'][8:]}.{m['deadline'][5:7]}.).\nNoch offen: {', '.join(mag_open[m['id']])}",
                       once_key=f"mag:{m['id']}:{m['deadline']}:{d}")
        for a in apparel:
            d = (datetime.strptime(a["deadline"], "%Y-%m-%d").date() - today).days
            n, pcs = counts.get(a["id"], (0, 0))
            if d in (3, 1) and a["active"]:
                notify("apparel_deadline", f"{a['name']}: Bestellschluss in {d} Tag{'en' if d > 1 else ''}",
                       f"Bestellschluss für „{a['name']}“ ist am {a['deadline'][8:]}.{a['deadline'][5:7]}.\nBisher: {n} Bestellungen, {pcs or 0} Stück.",
                       once_key=f"app:{a['id']}:{a['deadline']}:{d}")
            if d == -1:
                notify("apparel_deadline", f"{a['name']}: Bestellschluss vorbei",
                       f"Für „{a['name']}“ ist der Bestellschluss vorbei.\nErgebnis: {n} Bestellungen, {pcs or 0} Stück.\n"
                       "Die Zusammenfassung für den Lieferanten steht im Hub unter Teamkleidung.",
                       once_key=f"app:{a['id']}:{a['deadline']}:done")
    # Neue Bestellungen über den Link: höchstens einmal pro Stunde gesammelt
    with db() as conn:
        if not secret_get(conn, "notify_last_order"):   # erster Lauf: nur ab jetzt melden, nicht alle alten Bestellungen
            secret_set(conn, "notify_last_order", str(conn.execute("SELECT IFNULL(MAX(id), 0) FROM apparel_orders").fetchone()[0]))
            return
        last_id = int(secret_get(conn, "notify_last_order") or 0)
        last_time = float(secret_get(conn, "notify_last_digest") or 0)
        if time.time() - last_time < DIGEST_SECONDS:
            return
        rows = conn.execute("SELECT o.id, o.quantity, a.name FROM apparel_orders o JOIN apparel a ON a.id = o.apparel_id "
                            "WHERE o.id > ? AND o.source='Link' ORDER BY o.id", (last_id,)).fetchall()
        if not rows:
            return
        secret_set(conn, "notify_last_order", str(rows[-1]["id"]))
        secret_set(conn, "notify_last_digest", str(time.time()))
    per = {}
    for r in rows:
        n, pcs = per.get(r["name"], (0, 0))
        per[r["name"]] = (n + 1, pcs + (r["quantity"] or 1))
    notify("apparel_orders", f"{len(rows)} neue Bestellung{'en' if len(rows) > 1 else ''}",
           "Neu über den Bestell-Link:\n" + "\n".join(f"{k}: {n} Bestellung{'en' if n > 1 else ''}, {p} Stück" for k, (n, p) in per.items()))


# ---------------------------------------------------------------- Heimspieltag (Bereich spieltag)
GD_TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,64}")


def gd_lines(text):
    """Vorlage Schichten: „Rolle | Anzahl | Beginn-Ende“ pro Zeile -> [(rolle, anzahl, beginn, ende)]."""
    out = []
    for line in str(text or "").splitlines():
        parts = [x.strip() for x in line.split("|")]
        if not parts or not parts[0]:
            continue
        n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
        start, end = "", ""
        if len(parts) > 2 and parts[2]:
            m = re.fullmatch(r"(\d{1,2}[:.]\d{2})\s*(?:-|bis)\s*(\d{1,2}[:.]\d{2})", parts[2])
            start, end = (m.group(1).replace(".", ":"), m.group(2).replace(".", ":")) if m else (parts[2][:5], "")
        out.append((parts[0][:60], max(1, min(30, n)), start, end))
    return out[:40]


def gd_public(token):
    """Daten für /helfer/<token>: Spiel, Schichten mit freien Plätzen und nur den Vornamen der Eingetragenen. None = Link ungültig, zu oder Spiel vorbei."""
    if not GD_TOKEN_RE.fullmatch(token or ""):
        return None
    with db() as conn:
        link = conn.execute("SELECT * FROM gd_links WHERE token=?", (token,)).fetchone()
        if not link or not link["open"]:
            return None
        g = conn.execute("SELECT * FROM games WHERE id=?", (link["game_id"],)).fetchone()
        if not g or (g["date"] or "") < date.today().isoformat():
            return None
        opp = conn.execute("SELECT name FROM opponents WHERE id=?", (g["opponent_id"],)).fetchone()
        shifts = []
        for sh in conn.execute("SELECT * FROM gd_shifts WHERE game_id=? ORDER BY sort, start, id", (g["id"],)):
            names = [(r["name"] or "").split()[0][:30] for r in conn.execute("SELECT name FROM gd_signups WHERE shift_id=? ORDER BY id", (sh["id"],)) if (r["name"] or "").strip()]
            shifts.append({"id": sh["id"], "role": sh["role"] or "", "start": sh["start"] or "", "end": sh["end"] or "", "slots": max(1, int(sh["slots"] or 1)),
                           "notes": (sh["notes"] or "")[:200], "names": names})
        home = get_setting(conn, "home_location")
    return {"game_id": g["id"], "date": g["date"], "time": g["time"] or "", "opponent": opp["name"] if opp else "", "location": g["location"] or home or "",
            "team": g["team"] or MAIN_TEAM, "shifts": shifts}


def gd_reminders():
    """Am Vortag ab 17 Uhr: Push an alle, die sich im Hub für eine Schicht eingetragen haben (jede Eintragung nur einmal)."""
    now = datetime.now()
    if now.hour < 17:
        return
    tomorrow = (now.date() + timedelta(days=1)).isoformat()
    with db() as conn:
        rows = conn.execute("SELECT s.id, s.user_id, sh.role, sh.start, g.id AS gid, g.time FROM gd_signups s JOIN gd_shifts sh ON sh.id=s.shift_id "
                            "JOIN games g ON g.id=sh.game_id WHERE g.date=? AND s.user_id IS NOT NULL", (tomorrow,)).fetchall()
        todo = []
        for r in rows:
            key = f"gd-{r['id']}"
            if conn.execute("SELECT 1 FROM notify_sent WHERE key=?", (key,)).fetchone():
                continue
            conn.execute("INSERT INTO notify_sent (key, time) VALUES (?, ?)", (key, now.isoformat(timespec="seconds")))
            todo.append(r)
    for r in todo:
        when = f"ab {r['start']} Uhr" if r["start"] else (f"Anstoß {r['time']} Uhr" if r["time"] else "morgen")
        send_push_async([r["user_id"]], f"Morgen Heimspiel: {r['role']}", f"Deine Schicht {when}. Danke, dass du hilfst!", f"/hub#/spieltag/{r['gid']}", f"gd-{r['id']}")


def notify_loop():
    while True:
        try:
            notify_tick()
        except Exception as e:  # noqa
            print("Benachrichtigungen fehlgeschlagen:", e)
        try:
            gd_reminders()
        except Exception as e:  # noqa
            print("Spieltag-Erinnerungen fehlgeschlagen:", e)
        threading.Event().wait(NOTIFY_INTERVAL)


def social_loop():
    while True:
        try:
            with SOCIAL_LOCK:
                social_tick()
        except Exception as e:  # noqa
            print("Auto-Posting fehlgeschlagen:", e)
        threading.Event().wait(60)


# ---------------------------------------------------------------------------
# Sicherungen
# ---------------------------------------------------------------------------
def db_snapshot(target: Path):
    """Konsistente Kopie der Datenbank (auch während des Betriebs)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    with db() as src:
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
    os.replace(tmp, target)
    return target


def daily_backup():
    name = BACKUPS / f"wolthusen-{datetime.now():%Y-%m-%d}.db"
    if not name.exists():
        db_snapshot(name)
        print("Tägliche Sicherung erstellt:", name.name)
    olds = sorted(BACKUPS.glob("wolthusen-????-??-??.db"))
    for f in olds[:-BACKUP_KEEP] if BACKUP_KEEP > 0 else []:
        f.unlink(missing_ok=True)


def backup_loop():
    while True:
        try:
            daily_backup()
        except Exception as e:  # noqa
            print("Sicherung fehlgeschlagen:", e)
        try:   # Newsletter: wie in der Datenschutzerklärung zugesagt
            with db() as conn:
                conn.execute("DELETE FROM nl_subscribers WHERE status='offen' AND created < ?", ((datetime.now() - timedelta(days=30)).isoformat(timespec="seconds"),))
                conn.execute("DELETE FROM nl_subscribers WHERE status='abgemeldet' AND unsubscribed_at < ?", ((datetime.now() - timedelta(days=3 * 365)).isoformat(timespec="seconds"),))
        except Exception as e:  # noqa
            print("Newsletter aufräumen fehlgeschlagen:", e)
        threading.Event().wait(3600)


AUTH_TABLES = ("users", "sessions", "groups", "group_perms", "user_groups", "user_perms", "secrets", "audit_log", "user_2fa", "push_subs", "mail_tasks", "user_mail", "pf_inbox", "mail_accounts", "mail_account_users", "mail_links")


# ---------------------------------------------------------------------------
# Seite „Admin“ (/api/admin/info, nur Admins): Zustand des Servers und Hinweise für Updates
# ---------------------------------------------------------------------------
UPDATE_CACHE = {"at": 0.0, "version": "", "error": ""}


def latest_version(force=False):
    """Neueste Version auf GitHub (main), höchstens einmal pro Stunde abgefragt, nur die ersten 4 KB von server.py."""
    if not force and time.time() - UPDATE_CACHE["at"] < 3600:
        return UPDATE_CACHE
    UPDATE_CACHE["at"] = time.time()
    try:
        req = urllib.request.Request(UPDATE_SOURCE, headers={"Range": "bytes=0-4095", "User-Agent": "WolthusenHub"})
        with urllib.request.urlopen(req, timeout=6) as r:
            head = r.read(8192).decode("utf-8", "replace")
        m = re.search(r'^VERSION = "([0-9.]+)"', head, re.M)
        UPDATE_CACHE.update(version=m.group(1) if m else "", error="" if m else "Version nicht gefunden")
    except Exception as e:  # noqa
        UPDATE_CACHE.update(version="", error=f"GitHub nicht erreichbar ({type(e).__name__})")
    return UPDATE_CACHE


UPD_DIR = DATA / "updater"   # Austausch mit dem Update-Helfer auf dem VPS (deploy/updater): Anfrage rein, Status und Protokoll raus
UPD_ACTIONS = {"check": "Jetzt prüfen", "hub": "Hub aktualisieren", "caddy": "Caddy aktualisieren", "system": "Ubuntu-Updates einspielen", "reboot": "Server neu starten"}


def updater_state():
    """Was der Update-Helfer zuletzt gemeldet hat, dazu die Versionen, die der Hub selbst kennt."""
    import ssl
    try:
        helper = json.loads((UPD_DIR / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        helper = None
    try:
        log = (UPD_DIR / "last.log").read_text(encoding="utf-8", errors="replace")[-30000:]
    except OSError:
        log = ""
    run = (helper or {}).get("running") or None
    if run:   # hängengebliebene Meldung (Helfer abgebrochen) nach 2 Stunden nicht mehr als „läuft“ werten
        try:
            if time.time() - datetime.fromisoformat(run["since"]).timestamp() > 7200:
                run = None
        except (KeyError, TypeError, ValueError):
            run = None
    latest = latest_version()
    return {"helper": helper, "running": run, "log": log, "pending": (UPD_DIR / "request").exists(), "installed": UPD_DIR.is_dir(),
            "hub": {"version": VERSION, "latest": latest["version"], "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
                    "openssl": ssl.OPENSSL_VERSION}, "actions": UPD_ACTIONS, "host_dir": HOST_DIR}


def dir_size(d):
    n = size = 0
    if d.is_dir():
        for f in d.iterdir():
            if f.is_file():
                n += 1
                size += f.stat().st_size
    return n, size


def admin_info(force_update=False):
    disk = shutil.disk_usage(DATA)
    backups = sorted(BACKUPS.glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True) if BACKUPS.is_dir() else []
    media_n, media_size = dir_size(MEDIA)
    site_n, _ = dir_size(DATA / "site")
    now = time.time()
    with db() as conn:
        users = conn.execute("SELECT id, username, display_name, is_admin, active, locked_until, pw_hash FROM users").fetchall()
        tfa = {r["user_id"] for r in conn.execute("SELECT user_id FROM user_2fa WHERE enabled=1")}
        st = {k: get_setting(conn, k) for k in ("maint_on", "twofa_admins", "twofa_finance", "site_impressum", "site_datenschutz")}
        smtp_ok = bool(secret_get(conn, "smtp_host") and secret_get(conn, "smtp_user"))
        meta_ok = bool(secret_get(conn, "fb_token"))
    active = [u for u in users if u["active"]]
    admins = [u for u in active if u["is_admin"]]
    latest = latest_version(force_update)
    newer = bool(latest["version"]) and version_tuple(latest["version"]) > version_tuple(VERSION)
    open_legal = sum(len(re.findall(r"\[[^\]\n]{1,200}\]", st[k] or "")) for k in ("site_impressum", "site_datenschutz"))
    checks = []
    def add(level, text, link=""):
        checks.append({"level": level, "text": text, "link": link})
    if newer:
        add("info", f"Neue Version {latest['version']} auf GitHub (main). Unten unter „Update einspielen“ steht, wie es geht.")
    no2fa = [u["display_name"] or u["username"] for u in admins if u["id"] not in tfa]
    if no2fa:
        add("warn", "Admins ohne Zwei-Faktor-Anmeldung: " + ", ".join(no2fa), "#/profile")
    if st["twofa_admins"] != "1":
        add("warn", "Zwei-Faktor-Pflicht für Admins ist aus.", "#/accounts")
    if not smtp_ok:
        add("warn", "E-Mail-Versand ist nicht eingerichtet (Passwort vergessen, Bestellungen und Benachrichtigungen gehen dann nicht).", "#/settings")
    if not backups:
        add("warn", "Noch keine automatische Sicherung vorhanden.")
    elif now - backups[0].stat().st_mtime > 2 * 86400:
        add("warn", "Die letzte automatische Sicherung ist älter als 2 Tage.")
    if disk.free / disk.total < 0.1:
        add("warn", f"Nur noch {disk.free // 2**30} GB Speicher frei.")
    if open_legal:
        add("warn", f"Impressum und Datenschutz: {open_legal} Angaben in [eckigen Klammern] offen.", "#/website/texte")
    if st["maint_on"] == "1":
        add("info", "Wartungsmodus ist an, Besucher sehen nur die Wartungsseite.", "#/wartung")
    locked = [u["display_name"] or u["username"] for u in active if (u["locked_until"] or 0) > now]
    if locked:
        add("info", "Gesperrte Konten (zu viele Fehlversuche): " + ", ".join(locked), "#/accounts")
    return {
        "version": VERSION, "latest": latest["version"], "latest_error": latest["error"], "newer": newer,
        "python": sys.version.split()[0], "server": SERVER_MODE, "started": datetime.fromtimestamp(STARTED).isoformat(timespec="seconds"),
        "uptime_h": round((now - STARTED) / 3600, 1), "site_url": SITE_URL, "behind_proxy": BEHIND_PROXY,
        "host_dir": HOST_DIR, "proxy_dir": "/opt/docker/proxy" if BEHIND_PROXY else "", "ssh_user": SSH_USER, "repo": REPO_URL,
        "disk": {"total": disk.total, "free": disk.free}, "db_size": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "media": {"count": media_n, "size": media_size}, "site_images": site_n,
        "backups": [{"name": f.name, "size": f.stat().st_size, "time": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds")} for f in backups[:8]],
        "backup_count": len(backups), "backup_keep": BACKUP_KEEP,
        "users": {"active": len(active), "admins": len(admins), "admins_2fa": len([u for u in admins if u["id"] in tfa]),
                  "with_2fa": len([u for u in active if u["id"] in tfa]), "pending": len([u for u in active if not u["pw_hash"]])},
        "status": {"maintenance": st["maint_on"] == "1", "smtp": smtp_ok, "meta": meta_ok,
                   "twofa_admins": st["twofa_admins"] == "1", "twofa_finance": st["twofa_finance"] == "1"},
        "checks": checks,
    }


# ---------------------------------------------------------------------------
# Änderungsprotokoll
# ---------------------------------------------------------------------------
AUDIT_SKIP = {"updated_at", "created_at", "public_token"}
AUDIT_KEEP_DAYS = 400
LABEL_KEYS = ("title", "name", "description", "holder", "section", "author", "date")


def audit_short(v):
    s = "" if v is None else str(v)
    return s if len(s) <= 120 else s[:117] + "..."


def audit_label(row):
    d = row_dict(row) if row is not None and not isinstance(row, dict) else (row or {})
    if d.get("first_name") or d.get("last_name"):
        return f"{d.get('first_name') or ''} {d.get('last_name') or ''}".strip()
    return next((audit_short(d[k]) for k in LABEL_KEYS if d.get(k)), "")


def audit(conn, user, action, table="", rid=None, label="", details=None):
    """user: angemeldeter Benutzer (dict) oder ein Name wie „Bestell-Link“ für Aktionen ohne Login."""
    if isinstance(user, dict):
        uid, name = user.get("id"), user.get("display_name") or user.get("username") or "?"
    else:
        uid, name = None, user or "System"
    conn.execute("INSERT INTO audit_log (time, user_id, user_name, action, table_name, record_id, label, details) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (datetime.now().isoformat(timespec="seconds"), uid, name, action, table, rid, (label or "")[:120],
                  json.dumps(details, ensure_ascii=False)[:6000] if details else ""))


def db_check_import(path, broken_msg):
    """Eingespielte Datenbank prüfen und entschärfen: muss intakt sein; Trigger und Views legt der Hub nie an,
    eine präparierte Datei könnte darüber aber bei jedem Speichern eigene SQL-Befehle ausführen. Darum werden alle entfernt."""
    test = sqlite3.connect(path)
    try:
        if test.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError(broken_msg)
        extras = test.execute("SELECT type, name FROM sqlite_master WHERE type IN ('trigger', 'view')").fetchall()
        for typ, name in extras:
            test.execute(f'DROP {typ.upper()} IF EXISTS "{name.replace(chr(34), chr(34) * 2)}"')
        test.commit()
        return len(extras)
    finally:
        test.close()


def restore_backup(raw: bytes):
    """Spielt ein Backup-ZIP (aus "Backup herunterladen") oder eine wolthusen.db ein.
    Benutzer und Sitzungen des Servers bleiben erhalten."""
    db_bytes, media = None, {}
    if raw[:16] == b"SQLite format 3\x00":
        db_bytes = raw
    else:
        try:
            z = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile:
            raise ValueError("Das ist weder ein Backup-ZIP noch eine Datenbankdatei.")
        for info in z.infolist():
            n = info.filename.replace("\\", "/")
            if n.endswith("wolthusen.db") and db_bytes is None:
                db_bytes = z.read(info)
            elif "/media/" in "/" + n and not n.endswith("/"):
                base = n.rsplit("/", 1)[-1]
                if re.fullmatch(r"[A-Za-z0-9._-]{1,120}", base):
                    media[base] = info
        if db_bytes is None:
            raise ValueError("Im ZIP wurde keine wolthusen.db gefunden.")
        if db_bytes[:16] != b"SQLite format 3\x00":
            raise ValueError("Die wolthusen.db im ZIP ist keine gültige Datenbank.")

    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    db_snapshot(BACKUPS / f"vor-wiederherstellung-{stamp}.db")
    new_path = DATA / "_restore.db"
    new_path.write_bytes(db_bytes)
    db_check_import(new_path, "Die Datenbank im Backup ist beschädigt.")   # Gültigkeit prüfen, Trigger und Views entfernen

    with SYNC_LOCK, DB_LOCK:
        keep = {}
        with db() as conn:
            for t in AUTH_TABLES:
                keep[t] = [dict(r) for r in conn.execute(f"SELECT * FROM {t}")]
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        for suffix in ("-wal", "-shm"):
            Path(str(DB_PATH) + suffix).unlink(missing_ok=True)
        os.replace(new_path, DB_PATH)
        init_db()
        with db() as conn:
            for t in AUTH_TABLES:
                conn.execute(f"DELETE FROM {t}")
                cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({t})")}
                for row in keep[t]:
                    row = {k: v for k, v in row.items() if k in cols}
                    conn.execute(f"INSERT INTO {t} ({', '.join(row)}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))
    count = 0
    if media:
        z = zipfile.ZipFile(io.BytesIO(raw))
        for base, info in media.items():
            target = MEDIA / base
            if not target.exists():
                target.write_bytes(z.read(info))
                count += 1
    return {"ok": True, "media": count}


# ---------------------------------------------------------------------------
# Serverumzug: Komplett-Export und -Import. Enthält ALLES (Konten, Gruppen, Rechte, Zugangsdaten,
# Protokoll, Vereinsdaten, Bilder), nur Sitzungen nicht. Die Datei ist mit einem Passwort verschlüsselt,
# nur mit der Standardbibliothek: Schlüssel per scrypt, Schlüsselstrom per SHAKE-256, Echtheit per
# HMAC-SHA256 über die ganze Datei (erst prüfen, dann entschlüsseln).
# Aufbau: MAGIC | Salz 16 | Nonce 16 | verschlüsseltes ZIP | HMAC 32
# ---------------------------------------------------------------------------
MIGRATE_MAGIC = b"WOLTHUSENHUB-UMZUG-1\n"
MIGRATE_MAX = 2 * 1024 ** 3        # 2 GB
MIGRATE_CHUNK = 1024 * 1024


def migrate_keys(password, salt):
    k = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 15, r=8, p=1, maxmem=128 * 1024 * 1024, dklen=64)
    return k[:32], k[32:]


def migrate_xor(data, key, nonce, index):
    stream = hashlib.shake_256(key + nonce + index.to_bytes(8, "big")).digest(len(data))
    return (int.from_bytes(data, "big") ^ int.from_bytes(stream, "big")).to_bytes(len(data), "big")


def migrate_encrypt(src: Path, dst: Path, password):
    salt, nonce = os.urandom(16), os.urandom(16)
    enc_key, mac_key = migrate_keys(password, salt)
    mac = hmac.new(mac_key, digestmod=hashlib.sha256)
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        head = MIGRATE_MAGIC + salt + nonce
        fo.write(head)
        mac.update(head)
        i = 0
        while block := fi.read(MIGRATE_CHUNK):
            c = migrate_xor(block, enc_key, nonce, i)
            fo.write(c)
            mac.update(c)
            i += 1
        fo.write(mac.digest())


def migrate_decrypt(src: Path, dst: Path, password):
    size = src.stat().st_size
    hl = len(MIGRATE_MAGIC) + 32
    with open(src, "rb") as fi:
        head = fi.read(hl)
        if size < hl + 32 or not head.startswith(MIGRATE_MAGIC):
            raise ValueError("Das ist keine Umzugsdatei des Hubs.")
        salt, nonce = head[len(MIGRATE_MAGIC):len(MIGRATE_MAGIC) + 16], head[len(MIGRATE_MAGIC) + 16:]
        enc_key, mac_key = migrate_keys(password, salt)
        mac = hmac.new(mac_key, head, hashlib.sha256)
        left = size - hl - 32
        while left > 0:
            block = fi.read(min(MIGRATE_CHUNK, left))
            mac.update(block)
            left -= len(block)
        if not hmac.compare_digest(mac.digest(), fi.read(32)):
            raise ValueError("Das Passwort ist falsch oder die Datei ist beschädigt.")
        fi.seek(hl)
        left, i = size - hl - 32, 0
        with open(dst, "wb") as fo:
            while left > 0:
                block = fi.read(min(MIGRATE_CHUNK, left))
                fo.write(migrate_xor(block, enc_key, nonce, i))
                left -= len(block)
                i += 1


MIGRATE_DIRS = {"site": SITE_DIR, "rechnungen": INVOICE_DIR}   # außer data/media beim Serverumzug mitnehmen (Instagram-Bilder lädt der Hub neu)


def migrate_export(password) -> Path:
    """Baut die verschlüsselte Umzugsdatei und liefert ihren Pfad (wird nach dem Herunterladen gelöscht)."""
    stamp = secrets.token_hex(16)
    tmpdb, tmpzip, out = DATA / f"_umzug_{stamp}.db", DATA / f"_umzug_{stamp}.zip", DATA / f"_umzug_{stamp}.wolthusen"
    try:
        db_snapshot(tmpdb)
        c = sqlite3.connect(tmpdb)
        try:
            c.execute("DELETE FROM sessions")   # Anmeldungen ziehen nicht mit um
            c.commit()
            users = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            c.close()
        files = [f for f in MEDIA.iterdir() if f.is_file()]
        # Dazu eigene Webseitenbilder (data/site) und ausgestellte Rechnungen (data/rechnungen)
        extra = [(folder, f) for folder, d in MIGRATE_DIRS.items() if d.is_dir() for f in d.iterdir() if f.is_file()]
        with zipfile.ZipFile(tmpzip, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("umzug.json", json.dumps({"app": APP_NAME, "version": VERSION, "created": datetime.now().isoformat(timespec="seconds"),
                                                 "users": users, "media": len(files), "files": len(extra)}, ensure_ascii=False))
            z.write(tmpdb, "data/wolthusen.db")
            for f in files:   # Bilder und Videos sind schon komprimiert
                z.write(f, f"data/media/{f.name}", compress_type=zipfile.ZIP_STORED)
            for folder, f in extra:
                z.write(f, f"data/{folder}/{f.name}", compress_type=zipfile.ZIP_STORED)
        migrate_encrypt(tmpzip, out, password)
        return out
    finally:
        tmpdb.unlink(missing_ok=True)
        tmpzip.unlink(missing_ok=True)


def version_tuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0"))


def migrate_import(src: Path, password):
    """Ersetzt den kompletten Stand durch die Umzugsdatei. Vorher wird der eigene Stand gesichert."""
    tmpzip, newdb = DATA / "_umzug_import.zip", DATA / "_umzug_import.db"
    try:
        migrate_decrypt(src, tmpzip, password)
        try:
            z = zipfile.ZipFile(tmpzip)
        except zipfile.BadZipFile:
            raise ValueError("Die Umzugsdatei ist beschädigt.")
        with z:
            meta = json.loads(z.read("umzug.json").decode("utf-8"))
            if version_tuple(meta.get("version")) > version_tuple(VERSION):
                raise ValueError(f"Die Datei stammt von Version {meta.get('version')}. Bitte diesen Hub zuerst auf mindestens diese Version bringen.")
            newdb.write_bytes(z.read("data/wolthusen.db"))
            db_check_import(newdb, "Die Datenbank in der Umzugsdatei ist beschädigt.")
            db_snapshot(BACKUPS / f"vor-umzug-import-{datetime.now():%Y-%m-%d_%H%M%S}.db")
            with SYNC_LOCK, DB_LOCK, SOCIAL_LOCK:
                with db() as conn:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                for suffix in ("-wal", "-shm"):
                    Path(str(DB_PATH) + suffix).unlink(missing_ok=True)
                os.replace(newdb, DB_PATH)
                init_db()
            count = 0
            targets = {"media": MEDIA, **MIGRATE_DIRS}
            for info in z.infolist():
                parts = info.filename.split("/")
                if len(parts) != 3 or parts[0] != "data" or parts[1] not in targets or not re.fullmatch(r"[A-Za-z0-9._-]{1,120}", parts[2]) \
                        or parts[2].startswith("."):
                    continue
                d = targets[parts[1]]
                d.mkdir(parents=True, exist_ok=True)
                with z.open(info) as fi, open(d / parts[2], "wb") as fo:
                    shutil.copyfileobj(fi, fo, MIGRATE_CHUNK)
                count += parts[1] == "media"
        SOCIAL_CACHE.clear()
        return {"ok": True, "version": meta.get("version"), "created": meta.get("created"), "users": meta.get("users"), "media": count}
    finally:
        tmpzip.unlink(missing_ok=True)
        newdb.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Einstellungen und kleine Helfer
# ---------------------------------------------------------------------------
SYNC_LOCK = threading.RLock()   # sperrt Restore und Serverumzug gegen gleichzeitige Schreibvorgänge


def get_setting(conn, key):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else DEFAULT_SETTINGS.get(key, "")


def set_setting(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))


def clean_handle(h):
    h = (h or "").strip()
    h = re.sub(r"^https?://(www\.)?instagram\.com/", "", h)
    return h.strip("/").lstrip("@").split("?")[0].strip()


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class PayloadTooLarge(Exception):
    pass



class _NoBody:
    """Ziel für den Inhalt bei HEAD-Anfragen: nimmt alles an und verwirft es."""
    def write(self, b):
        return len(b)

    def flush(self):
        pass

class Handler(BaseHTTPRequestHandler):
    server_version = "WolthusenHub/" + VERSION
    timeout = 60   # Sekunden ohne Daten, dann wird die Verbindung getrennt (halb geschickte Anfragen blockieren sonst einen Thread)

    def log_message(self, fmt, *args):  # ruhige Konsole
        if "--verbose" in sys.argv:
            super().log_message(fmt, *args)

    # -- Antworten --------------------------------------------------------
    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, download_name=None, cache=False):
        if not path.is_file():
            return self.send_error(404)
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype.endswith("javascript") else ""))
        self.send_header("Content-Length", str(len(data)))
        # Dateien der Webseite im Browser behalten: mit Versionsstempel (?v=), Schriften und Dateien mit eindeutigem Namen ein Jahr,
        # übrige Bilder eine Woche; alles andere immer frisch prüfen
        forever = cache and (cache == "long" or path.suffix == ".woff2" or "v=" in urlparse(self.path).query)
        self.send_header("Cache-Control", "public, max-age=31536000, immutable" if forever else "public, max-age=604800" if cache else "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(data)

    def send_stream(self, path: Path, download_name):
        """Große Datei in Stücken senden (nicht komplett in den Speicher laden)."""
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        with open(path, "rb") as f:
            shutil.copyfileobj(f, self.wfile, MIGRATE_CHUNK)

    def save_body(self, target: Path, limit):
        """Großen Upload direkt in eine Datei schreiben."""
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise PayloadTooLarge()
        left = length
        with open(target, "wb") as f:
            while left > 0:
                block = self.rfile.read(min(MIGRATE_CHUNK, left))
                if not block:
                    break
                f.write(block)
                left -= len(block)

    def read_body(self, limit=MAX_BODY):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise PayloadTooLarge()
        if length > limit or length < 0:   # negative Länge würde bis zum Verbindungsende lesen und den Thread blockieren
            raise PayloadTooLarge()
        return self.rfile.read(length) if length else b""

    def read_json(self):
        raw = self.read_body(MAX_JSON)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def parts(self):
        return [unquote(p) for p in urlparse(self.path).path.strip("/").split("/") if p]

    def redirect(self, to, status=302, cookie=None):
        self.send_response(status)
        self.send_header("Location", to)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_html(self, html, status=200, headers=None):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        # Grundlegende Sicherheits-Header (Caddy ergänzt HSTS)
        self.send_header("X-Content-Type-Options", "nosniff")
        # Öffentliche Seiten darf nur der Hub selbst einbetten (Vorschau unter Webseite), alles andere nie
        self.send_header("X-Frame-Options", "SAMEORIGIN" if getattr(self, "frame_ok", False) else "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        # Content-Security-Policy: Die Webseite lädt nur eigene Skripte, Schriften und Bilder. Der Hub nutzt noch Inline-Handler,
        # dort sperrt die Regel Plugins, fremde <base>-Adressen, Formulare an fremde Ziele und das Einbetten.
        if getattr(self, "frame_ok", False):
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                                        "font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'")
        else:
            self.send_header("Content-Security-Policy", "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        super().end_headers()
        if self.command == "HEAD":   # Kopfzeilen sind raus, den Inhalt verwerfen
            self.wfile = _NoBody()

    # -- Anfragende Person ------------------------------------------------
    def client_ip(self):
        if TRUST_PROXY:
            fwd = self.headers.get("X-Forwarded-For", "")
            if fwd:
                return fwd.split(",")[0].strip()
        return self.client_address[0]

    def is_local_direct(self):
        return (self.client_address[0] in ("127.0.0.1", "::1")
                and not self.headers.get("X-Forwarded-For") and not SERVER_MODE)

    def session_token(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE:
                return v
        return ""

    def current_user(self):
        if hasattr(self, "_user"):
            return self._user
        self._user = None
        tok = self.session_token()
        if tok:
            with db() as conn:
                r = conn.execute("SELECT u.id, u.username, u.display_name, u.is_admin, u.active, u.member_id, s.expires "
                                 "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token_hash=?", (token_hash(tok),)).fetchone()
                if r and r["expires"] > time.time() and r["active"]:
                    u = {"id": r["id"], "username": r["username"], "display_name": r["display_name"] or r["username"],
                         "is_admin": bool(r["is_admin"]), "member_id": r["member_id"]}
                    u["perms"] = effective_perms(conn, u)
                    u["twofa"] = twofa_enabled(conn, u["id"])
                    # Pflicht, aber noch nicht eingerichtet: nur das eigene Profil zum Einrichten ist erreichbar
                    u["must_2fa"] = not u["twofa"] and twofa_required(conn, u, u["perms"])
                    self._user = u
                elif r:
                    conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(tok),))
        return self._user

    def cookie_header(self, value, max_age):
        parts = [f"{COOKIE}={value}", "Path=/", "HttpOnly", "SameSite=Lax", f"Max-Age={max_age}"]
        if SECURE_COOKIES:
            parts.append("Secure")
        return "; ".join(parts)

    def start_session(self, user_id):
        tok = secrets.token_urlsafe(32)
        now = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            conn.execute("INSERT INTO sessions (token_hash, user_id, expires, created_at, ip, user_agent) VALUES (?, ?, ?, ?, ?, ?)",
                         (token_hash(tok), user_id, time.time() + SESSION_DAYS * 86400, now, self.client_ip(),
                          (self.headers.get("User-Agent") or "")[:200]))
            conn.execute("UPDATE users SET last_login=? WHERE id=?", (now, user_id))
        return tok

    def send_session(self, user_id, extra=None):
        """Neue Sitzung anlegen und das Cookie mit der Antwort setzen."""
        tok = self.start_session(user_id)
        body = json.dumps({"ok": True, **(extra or {})}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Set-Cookie", self.cookie_header(tok, SESSION_DAYS * 86400))
        self.end_headers()
        self.wfile.write(body)

    # -- Routing ----------------------------------------------------------
    def do_GET(self):
        self.handle_request("GET")

    def do_HEAD(self):
        """Wie GET, aber ohne Inhalt (Suchmaschinen, Linkprüfer und Monitoring fragen oft nur den Kopf ab; vorher kam 501)."""
        real = self.wfile
        try:
            self.handle_request("GET")
        finally:
            self.wfile = real   # die Verbindung bleibt für weitere Anfragen offen

    def do_POST(self):
        self.handle_request("POST")

    def do_PUT(self):
        self.handle_request("PUT")

    def do_DELETE(self):
        self.handle_request("DELETE")

    def handle_request(self, method):
        try:
            self.route(method)
        except PayloadTooLarge:
            self.send_json({"error": "Datei zu groß"}, 413)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def route(self, method):
        p = self.parts()
        head = p[0] if p else ""

        # Öffentlich erreichbar
        if method == "GET" and head == "healthz":
            return self.send_json({"ok": True, "version": VERSION})
        if method == "GET" and p in (["static", "style.css"], ["static", "logo.png"], ["static", "icon.png"],
                                     ["static", "icon-192.png"], ["static", "icon-512.png"],
                                     ["static", "apple-touch-icon.png"], ["static", "icon-maskable-512.png"]):
            return self.serve_under(STATIC, p[1:])
        if method == "GET" and p == ["favicon.ico"]:   # Suchmaschinen und Browser fragen das ohne Link-Angabe (PNG wird überall angenommen)
            return self.serve_under(STATIC, ["icon-192.png"])
        if method == "GET" and p in (["apple-touch-icon.png"], ["apple-touch-icon-precomposed.png"]):   # iPhone fragt das ohne Link-Angabe
            return self.serve_under(STATIC, ["apple-touch-icon.png"])
        if method == "GET" and p in (["manifest.webmanifest"], ["sw.js"]):   # App auf dem Startbildschirm
            return self.send_file(STATIC / p[0])
        if head == "login" and method == "GET":
            if self.current_user():
                return self.redirect("/hub")
            if user_count() == 0:
                return self.redirect("/setup")
            return self.send_html(LOGIN_PAGE)
        if head == "setup" and method == "GET":
            if user_count() > 0:
                return self.redirect("/login")
            return self.send_html(SETUP_PAGE if self.is_local_direct() else NO_USER_PAGE)
        if head == "invite" and method == "GET" and len(p) == 2:
            with db() as conn:
                u = conn.execute("SELECT username, display_name, email, invite_profile FROM users WHERE invite_hash=? AND invite_expires > ? AND active=1",
                                 (token_hash(p[1]), time.time())).fetchone()
            if not u:
                return self.send_html(INVALID_INVITE_PAGE, 404)
            return self.send_html(invite_page(u, p[1]))
        if head == "auth":
            return self.api_auth(method, p[1:])
        if head == "passwort-vergessen" and method == "GET":
            return self.send_html(FORGOT_SENT_PAGE if p[1:] == ["gesendet"] else FORGOT_PAGE)
        if head == "passwort-neu" and method == "GET" and len(p) == 2:
            with db() as conn:
                u = conn.execute("SELECT username, display_name FROM users WHERE reset_hash=? AND reset_expires > ? AND active=1",
                                 (token_hash(p[1]), time.time())).fetchone()
            if not u:
                return self.send_html(INVALID_RESET_PAGE, 404)
            return self.send_html(RESET_PAGE.replace("%%NAME%%", html_esc(u["display_name"] or u["username"]))
                                  .replace("%%USER%%", html_esc(u["username"])).replace("%%TOKEN%%", html_esc(p[1])))
        if head == "bestellen":
            return self.public_order(method, p[1:])
        if head == "teilen" and method == "GET" and len(p) == 3:
            # Bild für Instagram: nur mit gültiger Signatur, nur Bilddateien
            name = p[2]
            if re.fullmatch(r"[A-Za-z0-9._-]{1,120}", name) and Path(name).suffix.lower() in SHARE_EXT \
                    and hmac.compare_digest(p[1], share_sig(social_config()["share_key"], name)):
                return self.serve_under(MEDIA, [name], inline=MEDIA_INLINE)
            return self.send_error(404)
        if head == "api" and p[1:2] == ["public"]:
            return self.api_public(method, p[2:])
        if head == "helfer" and len(p) == 2:   # Heimspieltag: eintragen ohne Konto, nur mit dem geheimen Link
            if method == "POST":
                if self.maint_blocks():
                    try:
                        self.read_body(20000)
                    except PayloadTooLarge:
                        pass
                    return self.redirect("/")
                return self.public_helpers(p[1])
            if method == "GET":
                gd = gd_public(p[1])
                q = parse_qs(urlparse(self.path).query)
                return self.send_site("helfer", 200 if gd else 404, helfer={"gd": gd, "token": p[1], "sent": (q.get("gesendet") or [""])[0]})
        if head == "newsletter":   # Newsletter ohne Konto: anmelden (Double-Opt-In), bestätigen, abmelden
            q = parse_qs(urlparse(self.path).query)
            arg = lambda k, n: (q.get(k) or [""])[0][:n]
            if len(p) == 1 and method == "GET":
                with db() as conn:
                    groups = nl_public_groups(conn)
                return self.send_site("newsletter", nl={"mode": "form", "sent": arg("gesendet", 20), "email": arg("email", 150), "groups": groups})
            if len(p) == 1 and method == "POST":
                if self.maint_blocks():
                    with contextlib.suppress(PayloadTooLarge):
                        self.read_body(20000)
                    return self.redirect("/newsletter")
                return self.public_newsletter()
            if len(p) == 3 and p[1] == "bestaetigen":
                if method == "POST":
                    return self.public_newsletter_confirm(p[2])
                return self.send_site("newsletter", nl={"mode": "confirm", "token": p[2][:80], "valid": nl_pending(p[2])})
            if len(p) == 3 and p[1] == "abmelden":
                sid = nl_token_id(p[2])
                if method == "POST":   # Knopf auf der Seite oder Ein-Klick-Abmeldung aus dem Mailprogramm (RFC 8058)
                    with contextlib.suppress(PayloadTooLarge):
                        self.read_body(2000)
                    if sid:
                        with db() as conn:
                            n = conn.execute("UPDATE nl_subscribers SET status='abgemeldet', unsubscribed_at=?, confirm_hash=NULL WHERE id=? AND status!='abgemeldet'",
                                             (datetime.now().isoformat(timespec="seconds"), sid)).rowcount
                            if n:
                                audit(conn, "Webseite", "Newsletter abgemeldet", "nl_subscribers", sid, "")
                    return self.redirect("/newsletter?gesendet=abgemeldet")
                return self.send_site("newsletter", nl={"mode": "unsub", "token": p[2][:80], "valid": bool(sid)})
            return self.send_site("404", 404)
        if head in ("kontakt", "supporter-karte") and method == "POST" and len(p) == 1 and self.maint_blocks():
            try:   # Wartungsmodus: Formulare der Webseite nehmen nichts an
                self.read_body(20000)
            except PayloadTooLarge:
                pass
            return self.redirect("/")
        if head == "kontakt" and method == "POST":
            return self.public_contact()
        if method == "GET" and p in (["sitemap.xml"], ["robots.txt"]):
            if head == "sitemap.xml":
                with db() as conn:
                    card_open = get_setting(conn, "site_card_order_open") == "1"
                    sm = web_sitemap(conn)
                body = website.sitemap(self.base_url(), public_articles(), card_open, sm).encode("utf-8")
            else:
                body = website.robots(self.base_url()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/xml; charset=utf-8" if head == "sitemap.xml" else "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            return self.wfile.write(body)
        if head == "supporter-karte" and method == "POST" and len(p) == 1:
            return self.public_card_order()
        if head == "supporter-karte" and len(p) == 3 and p[1] == "storno" and method in ("GET", "POST"):
            return self.public_card_cancel(method, p[2])
        if head == "spielerbogen" and len(p) == 1 and method in ("GET", "POST"):
            return self.public_player_form(method)
        # Öffentliche Webseite: Seiten, Dateien unter /web/assets, sonst 404-Seite (Hub-Pfade brauchen weiter Login)
        if method == "GET" and len(p) == 1 and head in website.REDIRECTS:   # alte Adressen der ersten Fassung
            q = urlparse(self.path).query
            return self.redirect(website.REDIRECTS[head] + ("?" + q if q else ""), 301)
        if method == "GET" and p == ["links"]:   # Link-Seite für die Instagram-Bio, nirgends verlinkt
            return self.send_site("links")
        if method == "GET" and (not p or (len(p) == 1 and head in website.PAGES)):
            return self.send_site(head)
        if method == "GET" and head == "mannschaft" and len(p) == 2:   # Seite einer Mannschaft (website.TEAM_SLUG)
            if p[1] not in website.SLUG_TEAM:
                return self.send_site("404", 404)
            return self.send_site("mannschaft/" + p[1])
        if method == "GET" and head == "news" and len(p) == 2:   # einzelner Artikel, nur veröffentlichte
            m = re.match(r"(\d{1,9})(?:-|$)", p[1])
            a = next((x for x in public_articles() if m and x["id"] == int(m.group(1))), None)
            if not a:
                return self.send_site("404", 404)
            if p[1] != a["slug"]:   # alte oder gekürzte Adresse: auf die aktuelle weiterleiten
                return self.redirect(f"/news/{a['slug']}", 301)
            return self.send_site("news-artikel", article=a)
        if method == "GET" and head == "signatur" and len(p) == 2 and re.fullmatch(r"[a-z0-9-]{1,40}\.png", p[1]):   # Bilder der Mail-Signatur
            return self.serve_under(SIG_DIR, p[1:], cache=True)
        if method == "GET" and p[:2] == ["web", "assets"]:
            return self.serve_under(website.WEB / "assets", p[2:], cache=True)
        if method == "GET" and p[:2] == ["web", "insta"] and len(p) == 3:
            return self.serve_under(INSTA_DIR, p[2:], cache="long")   # Name = Beitrags-ID, ändert sich nie
        if method == "GET" and p[:2] == ["web", "site"] and len(p) == 3 and p[2].endswith(".webp"):
            return self.serve_under(SITE_DIR, p[2:], cache="long")    # Name mit Zufallsstempel, neues Bild = neuer Name
        if method == "GET" and head not in ("hub", "static", "media", "api"):
            return self.send_site("404", 404)

        # Ab hier nur mit Anmeldung
        user = self.current_user()
        if not user:
            if head == "api":
                return self.send_json({"error": "Nicht angemeldet"}, 401)
            return self.redirect("/login")

        if method != "GET" and self.headers.get("X-TMH") != "1":
            return self.send_json({"error": "Ungültige Anfrage"}, 403)

        if p == ["hub"] and method == "GET":   # der Hub (Mitgliederbereich)
            return self.send_file(STATIC / "index.html")
        if head == "static" and method == "GET":
            return self.serve_under(STATIC, p[1:])
        if head == "media" and method == "GET":
            if user["must_2fa"]:
                return self.send_error(403)
            return self.serve_under(MEDIA, p[1:], inline=MEDIA_INLINE)
        if head == "api":
            return self.api(method, p[1:], user)
        return self.send_error(404)

    def serve_under(self, root: Path, rest, inline=None, cache=False):
        target = (root / "/".join(rest)).resolve()
        if root.resolve() not in target.parents and target != root.resolve():
            return self.send_error(403)
        # Hochgeladene Dokumente (HTML, SVG, Office ...) nie im Hub-Kontext öffnen, sondern herunterladen
        download = target.name if inline is not None and target.suffix.lower() not in inline else None
        return self.send_file(target, download, cache)

    def base_url(self):
        """Eigene Adresse für Links (Sitemap, Mails, Teilen): SITE_URL aus der .env, sonst der Host-Header (nur gültige Zeichen).
        X-Forwarded-Host wird bewusst nie übernommen, sonst könnte eine Anfrage fremde Adressen in Links und Mails schreiben."""
        if SITE_URL:
            return SITE_URL
        host = self.headers.get("Host") or ""
        if not re.fullmatch(r"[A-Za-z0-9.\-]+(:\d{1,5})?", host):
            host = f"127.0.0.1:{PORT}"
        proto = self.headers.get("X-Forwarded-Proto") if TRUST_PROXY else None
        if proto not in ("http", "https"):
            proto = "https" if SECURE_COOKIES else "http"
        return f"{proto}://{host}"

    # -- Dauerkarte stornieren (/supporter-karte/storno/<token>, Link aus der Bestätigungsmail) --
    # GET zeigt nur die Bestellung und den Knopf (Mail-Programme rufen Links teils automatisch auf), erst POST storniert.
    # Nur bis Zahlungseingang; die Seite zeigt nur Bestellnummer, Anzahl, Lieferart und Betrag, keine Namen oder Anschrift.
    def public_card_cancel(self, method, token):
        if method == "POST":
            try:
                self.read_body(2000)
            except PayloadTooLarge:
                return self.send_site("404", 404)
            if not reset_rate_ok("ip", "storno:" + self.client_ip()):
                return self.send_site("supporter-storno", 429, cancel={"state": "limit"})
        o = card_cancel_lookup(token)
        if not o:
            time.sleep(0.3)
            return self.send_site("supporter-storno", 404, cancel={"state": "ungueltig"})
        view = {"order_no": o["order_no"], "count": o["count"], "season": o["season"], "total": eur_text(o["total"]),
                "delivery": {"Einlass": "Abholung am Einlass", **CARD_SHIPS}.get(o["delivery"], o["delivery"] or ""), "token": token}
        if o["cancelled"]:
            return self.send_site("supporter-storno", cancel={**view, "state": "storniert"})
        if o["paid"]:
            return self.send_site("supporter-storno", cancel={**view, "state": "bezahlt"})
        if method == "GET":
            return self.send_site("supporter-storno", cancel={**view, "state": "offen"})
        o2, err, _ = card_order_cancel(o["id"], "Kunde", "Storno-Link")
        state = {"bezahlt": "bezahlt", "storniert": "storniert"}.get(err or "", "erledigt")
        return self.send_site("supporter-storno", cancel={**view, "state": state})

    # -- Spielerbogen (/spielerbogen, Passwort aus dem Hub, ersetzt die Google-Tabelle) --
    def public_player_form(self, method):
        cookie_val = ""
        for part in (self.headers.get("Cookie") or "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == PLAYER_FORM_COOKIE:
                cookie_val = v
        with db() as conn:
            st = player_form_state(conn)
            authed = st["open"] and st["has_pw"] and player_form_cookie_ok(conn, cookie_val)
        if not (st["open"] and st["has_pw"]):
            if method == "POST":
                try:
                    self.read_body(20000)
                except PayloadTooLarge:
                    pass
            return self.send_site("spielerbogen", form={"state": "geschlossen"})
        if method == "GET":
            sent = (parse_qs(urlparse(self.path).query).get("gesendet") or [""])[0]
            if sent == "ok":
                return self.send_site("spielerbogen", form={"state": "danke"})
            return self.send_site("spielerbogen", form={"state": "formular" if authed else "passwort", "error": sent == "falsch",
                                                         "invalid": sent == "fehler"})
        try:
            raw = self.read_body(20000).decode("utf-8")
        except (PayloadTooLarge, UnicodeDecodeError):
            return self.redirect("/spielerbogen?gesendet=fehler")
        f = {k: (v[0] or "").strip() for k, v in parse_qs(raw).items()}
        ip = self.client_ip()
        if "pw" in f:   # Schritt 1: Passwort
            if not reset_rate_ok("form", "spielerbogen:" + ip):
                time.sleep(0.6)
                return self.redirect("/spielerbogen?gesendet=falsch")
            with db() as conn:
                ok = check_pw(f["pw"][:200], secret_get(conn, "player_form_pw"))
                exp = str(int(time.time()) + PLAYER_FORM_HOURS * 3600)
                val = f"{exp}.{player_form_sig(conn, exp)}" if ok else ""
            if not ok:
                time.sleep(0.6)
                return self.redirect("/spielerbogen?gesendet=falsch")
            parts = [f"{PLAYER_FORM_COOKIE}={val}", "Path=/spielerbogen", "HttpOnly", "SameSite=Strict", f"Max-Age={PLAYER_FORM_HOURS * 3600}"]
            if SECURE_COOKIES:
                parts.append("Secure")
            return self.redirect("/spielerbogen", cookie="; ".join(parts))
        if not authed:
            return self.redirect("/spielerbogen")
        if f.get("website"):   # verstecktes Feld gegen Bots
            return self.redirect("/spielerbogen?gesendet=ok")
        if not reset_rate_ok("form", "spielerbogen-senden:" + ip):
            return self.redirect("/spielerbogen?gesendet=fehler")
        kind = f.get("kind", "") if f.get("kind") in PLAYER_FORM_KINDS else ""
        team = f.get("team", "") if f.get("team") in TEAMS else MAIN_TEAM
        first, last = f.get("first_name", "")[:60], f.get("last_name", "")[:60]
        email, phone = f.get("email", "")[:150], f.get("phone", "")[:40]
        number = f.get("number", "")[:3] if kind == "Spieler" else ""
        position = f.get("position", "") if kind == "Spieler" and f.get("position") in PLAYER_FORM_POSITIONS else ""
        ig = clean_handle(f.get("instagram", ""))[:30]
        ok = (kind and first and last and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email) and re.fullmatch(r"[0-9 +()/.-]{6,40}", phone)
              and (not number or number.isdigit()) and (not ig or re.fullmatch(r"[A-Za-z0-9._]{1,30}", ig))
              and not (kind == "Spieler" and team in YOUTH_TEAMS))   # Jugendspieler (Minderjährige) nicht über dieses Formular
        if not ok:
            return self.redirect("/spielerbogen?gesendet=fehler")
        now = datetime.now().isoformat(timespec="seconds")
        vals = {"first_name": first, "last_name": last, "nickname": f.get("nickname", "")[:40], "kind": kind, "team": team,
                "number": number, "position": position, "role": f.get("role", "")[:60], "instagram": ig, "email": email, "phone": phone,
                "consent": 1 if f.get("consent") == "1" else 0, "since": f.get("since", "")[:20], "facts": "",
                "message": f.get("message", "")[:1000], "status": "Neu", "created": now, "created_at": now, "updated_at": now}
        with db() as conn:
            sid = conn.execute(f"INSERT INTO player_signups ({', '.join(vals)}) VALUES ({', '.join('?' for _ in vals)})", list(vals.values())).lastrowid
            audit(conn, "Spielerbogen", "neu", "player_signups", sid, f"{first} {last}", {"Art": kind, "Mannschaft": team})
        notify_async("player_signup", f"Spielerbogen: {first} {last} ({kind})",
                     f"{first} {last} hat den Spielerbogen ausgefüllt ({kind}, {team}).\n\nPrüfen und übernehmen im Hub unter Verein > Kader & Staff.")
        return self.redirect("/spielerbogen?gesendet=ok")

    def maint_view(self):
        """Wartungsmodus: (Einstellungen, darf die Webseite trotzdem sehen). Vorbei nur angemeldet mit Recht Wartung (Admins immer)."""
        with db() as conn:
            st = {k: get_setting(conn, k) for k in ("maint_on", "maint_title", "maint_text", "maint_until")}
        if st["maint_on"] != "1" and "wartung-vorschau" not in (self.path or ""):
            return st, False   # aus: keine Sitzung nachschlagen
        u = self.current_user()
        return st, bool(u and not u["must_2fa"] and u["perms"].get("wartung", 0) >= 1)

    def maint_blocks(self):
        """True, wenn Besucher gerade nichts über die Webseite einreichen dürfen (Kontakt, Kartenbestellung)."""
        st, staff = self.maint_view()
        return st["maint_on"] == "1" and not staff

    def send_site(self, slug, status=200, article=None, cancel=None, form=None, helfer=None, nl=None):
        """Seite der öffentlichen Webseite aus den öffentlichen Daten bauen."""
        st, staff = self.maint_view()
        on = st["maint_on"] == "1"
        preview = staff and (parse_qs(urlparse(self.path).query).get("wartung-vorschau") or [""])[0] == "1"
        if (on and not staff and slug not in MAINT_OPEN_PAGES) or preview:
            html = website.render("wartung", {"info": public_info(), "site": public_site(), "base": self.base_url(), "nav": public_nav(),
                                              "maint": {"title": st["maint_title"], "text": st["maint_text"], "until": st["maint_until"], "preview": preview}})
            self.frame_ok = True
            try:
                return self.send_html(html, 200 if preview else 503, None if preview else {"Retry-After": "3600"})
            finally:
                self.frame_ok = False
        data = {"info": public_info(), "games": public_games(), "team": public_team(), "sponsors": public_sponsors(), "trainings": public_trainings(),
                "instagram": public_instagram() if slug == "" else [], "shop": public_shop() if slug == "" else [], "site": public_site(), "base": self.base_url(),
                "articles": public_articles() if slug in ("", "news", "sitemap") else [], "article": article, "cancel": cancel, "form": form, "helfer": helfer, "nl": nl,
                "nav": public_nav()}
        if slug == "links":
            with db() as conn:
                data["links"] = web_links(conn)
        q = parse_qs(urlparse(self.path).query)
        sent = (q.get("gesendet") or [None])[0]
        data["preselect"] = (q.get("anliegen") or [""])[0]   # Vorauswahl im Kontaktformular (website.py prüft den Wert)
        data["maint_bar"] = on and staff
        html = website.render(slug, data, sent)
        self.frame_ok = True
        try:
            return self.send_html(html, status)
        finally:
            self.frame_ok = False

    # -- Anmeldung --------------------------------------------------------
    def api_auth(self, method, p):
        name = p[0] if p else ""
        if method != "POST" or self.headers.get("X-TMH") != "1":
            return self.send_json({"error": "Ungültige Anfrage"}, 403)
        if name == "login":
            ip = self.client_ip()
            if login_blocked(ip):
                return self.send_json({"error": "Zu viele Fehlversuche. Bitte in 10 Minuten erneut versuchen."}, 429)
            data = self.read_json()
            username = (data.get("username") or "").strip()[:80]
            locked_msg = f"Zu viele Fehlversuche mit diesem Benutzernamen. Bitte in {ACCOUNT_LOCK_MINUTES} Minuten erneut versuchen."
            with db() as conn:
                u = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
                if u and not u["active"]:
                    u = None
                if account_locked(conn, u, username):
                    login_failed(ip)
                    time.sleep(0.6)
                    return self.send_json({"error": locked_msg}, 429)
                if u:
                    ok = check_pw(data.get("password") or "", u["pw_hash"])
                else:
                    dummy_check_pw(data.get("password") or "")
                    ok = False
                if not ok:
                    login_failed(ip)
                    account_failed(conn, u, username, ip)
                    locked = account_locked(conn, conn.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone() if u else None, username)
                if ok:
                    need = twofa_enabled(conn, u["id"])
                    if not need:
                        account_ok(conn, u["id"])
            if not ok:
                time.sleep(0.6)
                return self.send_json({"error": locked_msg if locked else "Benutzername oder Passwort falsch."}, 429 if locked else 401)
            if need:   # Passwort stimmt, jetzt noch der Code aus der App (Sitzung erst danach)
                return self.send_json({"need_2fa": True, "ticket": twofa_ticket_new(u["id"])})
            return self.send_session(u["id"])
        if name == "login2":
            ip = self.client_ip()
            if login_blocked(ip):
                return self.send_json({"error": "Zu viele Fehlversuche. Bitte in 10 Minuten erneut versuchen."}, 429)
            data = self.read_json()
            th = token_hash(data.get("ticket") or "")
            with FAILED_LOCK:
                t = TWOFA_TICKETS.get(th)
                if t and (t["expires"] < time.time() or t["tries"] >= ACCOUNT_FAIL_MAX):
                    TWOFA_TICKETS.pop(th, None)
                    t = None
            if not t:
                return self.send_json({"error": "Die Anmeldung ist abgelaufen. Bitte noch einmal mit Benutzername und Passwort anmelden.", "restart": True}, 400)
            with db() as conn:
                u = conn.execute("SELECT * FROM users WHERE id=? AND active=1", (t["uid"],)).fetchone()
                if not u or account_locked(conn, u, ""):
                    with FAILED_LOCK:
                        TWOFA_TICKETS.pop(th, None)
                    return self.send_json({"error": f"Zu viele Fehlversuche mit diesem Benutzernamen. Bitte in {ACCOUNT_LOCK_MINUTES} Minuten erneut versuchen.",
                                           "restart": True}, 429)
                kind = twofa_check(conn, u["id"], data.get("code") or "")
                if not kind:
                    login_failed(ip)
                    account_failed(conn, u, u["username"], ip)
                    with FAILED_LOCK:
                        t["tries"] += 1
                else:
                    account_ok(conn, u["id"])
                    with FAILED_LOCK:
                        TWOFA_TICKETS.pop(th, None)
                    left = len(json.loads(twofa_row(conn, u["id"])["recovery"] or "[]"))
                    if kind == "recovery":
                        audit(conn, "Anmeldung", "Wiederherstellungscode benutzt", "users", u["id"], u["display_name"] or u["username"], {"übrig": ["", left]})
                        email = account_email(conn, u)
            if not kind:
                time.sleep(0.6)
                return self.send_json({"error": "Der Code stimmt nicht. Bitte den aktuellen Code aus der App eingeben."}, 401)
            if kind == "recovery":
                cfg = smtp_config()
                if email and cfg["smtp_host"]:
                    body = (f"Hallo {u['display_name'] or u['username']},\n\nbei deinem Konto im Wolthusen Hub (Benutzername: {u['username']}) wurde gerade "
                            f"ein Wiederherstellungscode für die Anmeldung benutzt ({datetime.now():%d.%m.%Y %H:%M}). Übrig sind noch {left}.\n\n"
                            "Warst du das nicht? Dann ändere bitte sofort dein Passwort und melde dich beim Vorstand bzw. Admin.")
                    threading.Thread(target=lambda: send_mail(cfg, email, "Wolthusen Hub: Wiederherstellungscode benutzt", body, footer=False), daemon=True).start()
            return self.send_session(u["id"], {"recovery_left": left, "next": "/hub#/profile"} if kind == "recovery" else None)
        if name == "logout":
            tok = self.session_token()
            if tok:
                with db() as conn:
                    conn.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(tok),))
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Set-Cookie", self.cookie_header("", 0))
            self.end_headers()
            self.wfile.write(body)
            return
        if name == "invite":
            data = self.read_json()
            tok = data.get("token") or ""
            with db() as conn:
                u = conn.execute("SELECT * FROM users WHERE invite_hash=? AND invite_expires > ? AND active=1",
                                 (token_hash(tok), time.time())).fetchone()
            if not u:
                return self.send_json({"error": "Der Einladungslink ist ungültig oder abgelaufen."}, 400)
            prob = pw_problem(data.get("password") or "")
            if prob:
                return self.send_json({"error": prob}, 400)
            f = {k: str(v or "").strip() for k, v in data.items() if isinstance(v, (str, int))}
            prof = invite_profile(u)
            kind = prof.get("kind") if prof.get("kind") in PLAYER_FORM_KINDS else ""
            # Benutzername: frei wählbar, solange er gültig und frei ist
            try:
                uname = check_username(f.get("username") or u["username"])
            except ValueError as e:
                return self.send_json({"error": str(e)}, 400)
            first, last = f.get("first_name", "")[:60], f.get("last_name", "")[:60]
            email, phone = f.get("email", "")[:150], f.get("phone", "")[:40]
            if not (first and last):
                return self.send_json({"error": "Bitte Vor- und Nachnamen angeben."}, 400)
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                return self.send_json({"error": "Bitte eine gültige E-Mail-Adresse angeben."}, 400)
            if (phone or kind) and not re.fullmatch(r"[0-9 +()/.-]{6,40}", phone):
                return self.send_json({"error": "Bitte eine gültige Telefonnummer angeben."}, 400)
            signup = None
            if kind:
                team = f.get("team") if f.get("team") in TEAMS else (prof.get("team") if prof.get("team") in TEAMS else MAIN_TEAM)
                if kind == "Spieler" and team in YOUTH_TEAMS:   # Jugendspieler (Minderjährige) nicht über Einladung in den Kader
                    team = MAIN_TEAM
                number = f.get("number", "")[:3] if kind == "Spieler" else ""
                position = f.get("position", "") if kind == "Spieler" and f.get("position") in PLAYER_FORM_POSITIONS else ""
                role = f.get("role", "")[:60] if kind != "Spieler" else ""
                ig = clean_handle(f.get("instagram", ""))[:30]
                if (number and not number.isdigit()) or (ig and not re.fullmatch(r"[A-Za-z0-9._]{1,30}", ig)) or (kind != "Spieler" and not role):
                    return self.send_json({"error": "Bitte die Angaben für Kader und Staff prüfen (Nummer nur Ziffern, Instagram ohne Leerzeichen, Rolle angeben)."}, 400)
                signup = {"first_name": first, "last_name": last, "nickname": f.get("nickname", "")[:40], "kind": kind, "team": team,
                          "number": number, "position": position, "role": role, "instagram": ig, "email": email, "phone": phone,
                          "consent": 1 if f.get("consent") == "1" else 0, "since": f.get("since", "")[:20], "facts": "",
                          "message": "", "status": "Neu", "source": "Einladung", "user_id": u["id"]}
            now = datetime.now().isoformat(timespec="seconds")
            with db() as conn:
                if uname.lower() != (u["username"] or "").lower() and conn.execute("SELECT 1 FROM users WHERE username=? AND id != ?", (uname, u["id"])).fetchone():
                    return self.send_json({"error": "Diesen Benutzernamen gibt es schon. Bitte einen anderen wählen."}, 400)
                conn.execute("UPDATE users SET username=?, pw_hash=?, display_name=?, email=?, phone=?, invite_hash=NULL, invite_expires=NULL, invite_profile=NULL WHERE id=?",
                             (uname, hash_pw(data["password"]), f"{first} {last}", email, phone, u["id"]))
                conn.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))
                audit(conn, {"id": u["id"], "username": uname, "display_name": f"{first} {last}"}, "Einladung angenommen", "users", u["id"], f"{first} {last}",
                      {"Benutzername": ["", uname], **({"Kader-Angaben": ["", kind]} if kind else {})})
                if signup:
                    vals = {**signup, "created": now, "created_at": now, "updated_at": now}
                    sid = conn.execute(f"INSERT INTO player_signups ({', '.join(vals)}) VALUES ({', '.join('?' for _ in vals)})", list(vals.values())).lastrowid
                need = twofa_enabled(conn, u["id"])
            if signup:
                notify_async("player_signup", f"Einladung angenommen: {first} {last} ({kind})",
                             f"{first} {last} hat die Einladung angenommen und die Angaben für Kader & Staff eingetragen ({kind}, {signup['team']}).\n\n"
                             "Prüfen und übernehmen im Hub unter Verein > Kader & Staff (Eingänge).")
            if need:   # mit Zwei-Faktor-Anmeldung nie direkt anmelden, der Code gehört dazu
                return self.send_json({"ok": True, "next": "/login"})
            return self.send_session(u["id"])
        if name == "forgot":
            # Immer dieselbe Antwort, egal ob es das Konto gibt (keine Auskunft über Konten)
            if reset_rate_ok("ip", self.client_ip()):
                request_password_reset(self.read_json().get("login"), self.base_url())
            time.sleep(0.4)
            return self.send_json({"ok": True})
        if name == "reset":
            data = self.read_json()
            tok = data.get("token") or ""
            with db() as conn:
                u = conn.execute("SELECT * FROM users WHERE reset_hash=? AND reset_expires > ? AND active=1", (token_hash(tok), time.time())).fetchone()
            if not u:
                return self.send_json({"error": "Der Link ist ungültig oder abgelaufen. Bitte unter „Passwort vergessen“ einen neuen anfordern."}, 400)
            prob = pw_problem(data.get("password") or "")
            if prob:
                return self.send_json({"error": prob}, 400)
            with db() as conn:
                conn.execute("UPDATE users SET pw_hash=?, reset_hash=NULL, reset_expires=NULL, invite_hash=NULL, invite_expires=NULL WHERE id=?",
                             (hash_pw(data["password"]), u["id"]))
                conn.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))   # überall abmelden
                account_ok(conn, u["id"])   # Sperre aufheben: der Link aus der Mail zeigt, dass es die Person selbst ist
                audit(conn, "Passwort vergessen", "Passwort per Link neu gesetzt", "users", u["id"], u["display_name"] or u["username"])
                email = account_email(conn, u)
                need = twofa_enabled(conn, u["id"])
            cfg = smtp_config()
            if email and cfg["smtp_host"]:
                body = (f"Hallo {u['display_name'] or u['username']},\n\ndas Passwort für dein Konto im Wolthusen Hub (Benutzername: {u['username']}) "
                        f"wurde gerade über „Passwort vergessen“ geändert ({datetime.now():%d.%m.%Y %H:%M}).\n\n"
                        "Warst du das nicht? Dann melde dich bitte sofort beim Vorstand bzw. Admin.")
                threading.Thread(target=lambda: send_mail(cfg, email, "Wolthusen Hub: Dein Passwort wurde geändert", body, footer=False), daemon=True).start()
            if need:   # mit Zwei-Faktor-Anmeldung nie direkt anmelden, der Code gehört dazu
                return self.send_json({"ok": True, "next": "/login"})
            return self.send_session(u["id"])
        if name == "setup":
            if user_count() > 0 or not self.is_local_direct():
                return self.send_json({"error": "Ersteinrichtung nicht möglich."}, 403)
            data = self.read_json()
            try:
                create_user(data.get("username"), data.get("password") or "", is_admin=True)
            except ValueError as e:
                return self.send_json({"error": str(e)}, 400)
            return self.send_json({"ok": True})
        return self.send_json({"error": "Unbekannter Pfad"}, 404)

    # -- Öffentliche Schnittstelle für die Webseite (ohne Login, nur lesen) --
    def api_public(self, method, p):
        what = p[0] if p else ""
        if method != "GET" or len(p) != 1:
            return self.send_json({"error": "Nicht gefunden"}, 404)
        fn = {"info": public_info, "spielplan": public_games, "team": public_team, "sponsoren": public_sponsors}.get(what)
        if not fn:
            return self.send_json({"error": "Nicht gefunden"}, 404)
        body = json.dumps(fn(), ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=300")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    # -- Kontaktformular der Webseite (ohne Login, funktioniert ohne JavaScript) --
    def public_contact(self):
        back = lambda res: self.redirect(f"/kontakt?gesendet={res}#formular")
        try:
            raw = self.read_body(20000).decode("utf-8")
        except (PayloadTooLarge, UnicodeDecodeError):
            return back("fehler")
        f = {k: (v[0] or "").strip() for k, v in parse_qs(raw).items()}
        if f.get("website"):                       # verstecktes Feld: nur Bots füllen es aus, still verwerfen
            return back("ok")
        if not reset_rate_ok("ip", "kontakt:" + self.client_ip()):
            return back("fehler")
        name, email, phone, msg = f.get("name", "")[:100], f.get("email", "")[:150], f.get("phone", "")[:40], f.get("message", "")[:3000]
        source = f.get("anliegen") if f.get("anliegen") in CONTACT_TOPICS else "Webseite"
        if not name or not msg or f.get("consent") != "1" or not (email or phone):
            return back("fehler")
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return back("fehler")
        now = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            cur = conn.execute("INSERT INTO contact_requests (name, email, phone, message, source, status, created, created_at, updated_at) "
                               "VALUES (?, ?, ?, ?, ?, 'Neu', ?, ?, ?)", (name, email, phone, msg, source, now, now, now))
            audit(conn, "Webseite", "neu", "contact_requests", cur.lastrowid, name)
            to = get_setting(conn, "site_contact_email")
            confirm = (get_setting(conn, "site_contact_confirm") or "").strip()
        text = f"Neue Anfrage über die Webseite ({source})\n\nName: {name}\nE-Mail: {email or '-'}\nTelefon: {phone or '-'}\n\n{msg}"
        cfg = smtp_config()
        if cfg["smtp_host"]:
            # Antworten im Hub oder im Mailprogramm gehen direkt an die anfragende Person (Reply-To)
            from email.utils import formataddr
            reply = formataddr((re.sub(r"[\r\n\"<>]", " ", name).strip(), email)) if email else ""
            def deliver():
                if to:
                    send_mail(cfg, to, f"Webseite: Anfrage von {name}", text, footer=False, headers={"Reply-To": reply})
                # Bestätigung ohne Inhalte aus dem Formular (sonst ließe sich das Formular für Spam an fremde Adressen nutzen)
                if email and confirm:
                    send_mail(cfg, email, "Deine Anfrage beim SV Amisia Wolthusen", f"Hallo,\n\n{confirm}\n\nSportliche Grüße\nSV Amisia Wolthusen",
                              footer=False, headers={"Reply-To": to or ""})
            threading.Thread(target=deliver, daemon=True).start()
        notify_async("contact_request", f"Neue Anfrage von {name}", text + "\n\nIm Hub unter Mitglieder > Anfragen.")
        return back("ok")

    # -- Newsletter: Anmeldung mit Double-Opt-In. Gleiche Antwort, ob die Adresse schon bekannt ist oder nicht (keine Auskunft).
    # Gruppen ändern sich erst nach der Bestätigung, so kann niemand fremde Abos verstellen. Begrenzung pro IP und pro Adresse.
    def public_newsletter(self):
        back = lambda res: self.redirect(f"/newsletter?gesendet={res}#anmelden")
        try:
            raw = self.read_body(20000).decode("utf-8")
        except (PayloadTooLarge, UnicodeDecodeError):
            return back("fehler")
        q = parse_qs(raw)
        f = {k: (v[0] or "").strip() for k, v in q.items()}
        if f.get("website"):
            return back("ok")
        email, name = f.get("email", "")[:150], re.sub(r"[\x00-\x1f<>]", "", f.get("name", ""))[:80]
        if f.get("consent") != "1" or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return back("fehler")
        if not reset_rate_ok("ip", "newsletter:" + self.client_ip()) or not reset_rate_ok("user", "newsletter:" + email.lower()):
            return back("ok")   # zu viele Versuche: still, damit niemand fremde Postfächer zumüllt
        with db() as conn:
            pub = {g["id"] for g in nl_public_groups(conn)}
            chosen = sorted({int(x) for x in q.get("gruppe", []) if str(x).isdigit() and int(x) in pub})
            if pub and not chosen:
                return back("gruppe")
            token = secrets.token_urlsafe(24)
            h, exp, now = hashlib.sha256(token.encode()).hexdigest(), time.time() + NL_CONFIRM_HOURS * 3600, datetime.now().isoformat(timespec="seconds")
            row = conn.execute("SELECT id FROM nl_subscribers WHERE email=?", (email,)).fetchone()
            if row:
                conn.execute("UPDATE nl_subscribers SET pending_groups=?, confirm_hash=?, confirm_expires=?, name=COALESCE(NULLIF(?, ''), name) WHERE id=?",
                             (json.dumps(chosen), h, exp, name, row["id"]))
            else:
                conn.execute("INSERT INTO nl_subscribers (email, name, status, groups, pending_groups, confirm_hash, confirm_expires, source, created) "
                             "VALUES (?, ?, 'offen', '[]', ?, ?, ?, 'Webseite', ?)", (email, name, json.dumps(chosen), h, exp, now))
            club = get_setting(conn, "club_name") or "SV Amisia Wolthusen"
        link = f"{self.base_url()}/newsletter/bestaetigen/{token}"
        cfg = smtp_config()
        if cfg["smtp_host"]:
            text = (f"Hallo{(' ' + name) if name else ''},\n\nbitte bestätige deine Anmeldung zum Newsletter der {club}:\n{link}\n\n"
                    f"Der Link gilt {NL_CONFIRM_HOURS} Stunden. Wenn du dich nicht angemeldet hast, ignoriere diese E-Mail einfach, dann passiert nichts.\n\nSportliche Grüße\n{club}")
            threading.Thread(target=send_mail, args=(cfg, email, f"Bitte bestätige deine Anmeldung zum Newsletter der {club}", text), kwargs={"footer": False}, daemon=True).start()
        return back("ok")

    def public_newsletter_confirm(self, token):
        with contextlib.suppress(PayloadTooLarge):
            self.read_body(2000)
        h = hashlib.sha256((token or "").encode()).hexdigest()
        with db() as conn:
            r = conn.execute("SELECT * FROM nl_subscribers WHERE confirm_hash=? AND confirm_expires > ?", (h, time.time())).fetchone()
            if not r:
                return self.redirect("/newsletter?gesendet=abgelaufen")
            groups = sorted(set(nl_ids(r["pending_groups"])) | (set(nl_ids(r["groups"])) if r["status"] == "aktiv" else set()))
            now = datetime.now().isoformat(timespec="seconds")
            conn.execute("UPDATE nl_subscribers SET status='aktiv', groups=?, pending_groups='[]', confirm_hash=NULL, confirm_expires=NULL, consent_at=?, consent_text=?, "
                         "unsubscribed_at=NULL WHERE id=?", (json.dumps(groups), now, website.NL_CONSENT, r["id"]))
            audit(conn, "Webseite", "Newsletter bestätigt", "nl_subscribers", r["id"], "")
        return self.redirect("/newsletter?gesendet=bestaetigt")

    # -- Heimspieltag: Helfer tragen sich über den geheimen Link ein (/helfer/<token>, ohne Anmeldung) --
    # Nur Name (Pflicht), Telefon (freiwillig) und geprüfte Schichten dieses Spiels, nur freie Plätze, verstecktes Feld und Begrenzung pro IP.
    def public_helpers(self, token):
        back = lambda res: self.redirect(f"/helfer/{token}?gesendet={res}#eintragen")
        try:
            raw = self.read_body(20000).decode("utf-8")
        except (PayloadTooLarge, UnicodeDecodeError):
            return back("fehler")
        q = parse_qs(raw)
        f = {k: (v[0] or "").strip() for k, v in q.items()}
        if f.get("website"):
            return back("ok")
        gd = gd_public(token)
        if not gd:
            return self.send_site("helfer", 404, helfer={"gd": None, "token": token, "sent": ""})
        if not reset_rate_ok("ip", "helfer:" + self.client_ip()):
            return back("fehler")
        name, phone = re.sub(r"\s+", " ", f.get("name", ""))[:80], f.get("phone", "")[:40]
        wanted = [int(x) for x in q.get("schicht", []) if x.isdigit()][:10]
        if not name or f.get("consent") != "1" or not wanted:
            return back("fehler")
        shifts = {sh["id"]: sh for sh in gd["shifts"]}
        now = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            done = []
            for sid in wanted:
                sh = shifts.get(sid)
                if not sh:
                    continue
                taken = conn.execute("SELECT COUNT(*) FROM gd_signups WHERE shift_id=?", (sid,)).fetchone()[0]
                if taken >= sh["slots"]:
                    continue
                cur = conn.execute("INSERT INTO gd_signups (shift_id, game_id, name, phone, source, created) VALUES (?, ?, ?, ?, 'Link', ?)",
                                   (sid, gd["game_id"], name, phone, now))
                audit(conn, "Helfer-Link", "neu", "gd_signups", cur.lastrowid, f"{name}: {sh['role']}")
                done.append(sh["role"])
        return back("ok" if done else "voll")

    # -- Dauerkarte online bestellen (/supporter-karte, ohne Anmeldung) --
    # Nimmt nur feste Felder an (Name, E-Mail, Telefon, Anzahl 1 bis 5, Nachricht), nur wenn im Hub geöffnet,
    # mit verstecktem Feld gegen Bots und Begrenzung pro Verbindung. Legt pro Karte einen Eintrag „Online“, unbezahlt an.
    def public_card_order(self):
        back = lambda res: self.redirect(f"/supporter-karte?gesendet={res}#bestellen")
        try:
            raw = self.read_body(20000).decode("utf-8")
        except (PayloadTooLarge, UnicodeDecodeError):
            return back("fehler")
        f = {k: (v[0] or "").strip() for k, v in parse_qs(raw).items()}
        if f.get("website"):
            return back("ok")
        with db() as conn:
            is_open, season, price = get_setting(conn, "site_card_order_open") == "1", get_setting(conn, "season"), get_setting(conn, "card_price")
            ship_cost = {"Post": get_setting(conn, "card_shipping"), "Einschreiben": get_setting(conn, "card_shipping_registered")}
        if not is_open:
            return back("geschlossen")
        if not reset_rate_ok("ip", "karte:" + self.client_ip()):
            return back("fehler")
        name, email, phone, msg = f.get("name", "")[:100], f.get("email", "")[:150], f.get("phone", "")[:40], f.get("message", "")[:1000]
        count = int(f["count"]) if f.get("count", "").isdigit() and 1 <= int(f["count"]) <= CARD_ORDER_MAX else 0
        delivery = {"post": "Post", "einschreiben": "Einschreiben", "einlass": "Einlass"}.get(f.get("delivery", ""), "")
        ships = delivery in CARD_SHIPS
        street, zip_, city = f.get("street", "")[:120], f.get("zip", "")[:10], f.get("city", "")[:80]
        if not name or not count or not delivery or f.get("consent") != "1" or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            return back("fehler")
        if ships and not (street and re.fullmatch(r"\d{4,5}", zip_) and city):
            return back("fehler")
        holders = [(f.get(f"holder{i}", "")[:100] or name) for i in range(1, count + 1)]   # leere Namensfelder: Besteller
        price_val, ship_val = money(price), (money(ship_cost[delivery]) or 0.0) if ships else 0.0
        if price_val is None:
            return back("fehler")
        total = round(price_val * count + ship_val, 2)
        now = datetime.now()
        stamp = now.isoformat(timespec="seconds")
        with db() as conn:
            cur = conn.execute("INSERT INTO card_orders (season, buyer, email, phone, holders, count, delivery, street, zip, city, price_each, shipping, total, "
                               "message, paid, delivered, created, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,?,?,?)",
                               (season, name, email, phone, json.dumps(holders, ensure_ascii=False), count, delivery,
                                street if ships else "", zip_ if ships else "", city if ships else "",
                                price_val, ship_val, total, msg, stamp, stamp, stamp))
            oid = cur.lastrowid
            order_no = f"SK-{now.year}-{oid:04d}"
            cancel_token = secrets.token_urlsafe(24)   # Storno-Link für den Kunden, gespeichert nur als Hash
            conn.execute("UPDATE card_orders SET order_no=?, cancel_hash=? WHERE id=?", (order_no, hashlib.sha256(cancel_token.encode()).hexdigest(), oid))
            for i, holder in enumerate(holders):
                c = conn.execute("INSERT INTO supporter_cards (season, holder, sold_on, price, paid, notes, email, phone, source, order_id, created_at, updated_at) "
                                 "VALUES (?, ?, ?, ?, 0, ?, ?, ?, 'Online', ?, ?, ?)",
                                 (season, holder, now.date().isoformat(), price_val, f"{order_no}, Karte {i + 1} von {count}", email, phone, oid, stamp, stamp))
            audit(conn, "Webseite", "neu", "card_orders", oid, f"{order_no} {name}", {"Karten": count, "Lieferung": delivery, "Summe": eur_text(total)})
            o = conn.execute("SELECT * FROM card_orders WHERE id=?", (oid,)).fetchone()
            confirm = card_order_mail(conn, o, f"{SITE_URL or self.base_url()}/supporter-karte/storno/{cancel_token}")
            to = get_setting(conn, "site_contact_email")
        text = (f"Neue Online-Bestellung Dauerkarte {season} ({order_no})\n\n" + card_order_summary(o) + (f"\n\nNachricht: {msg}" if msg else ""))
        cfg = smtp_config()
        if cfg["smtp_host"]:
            if to:
                threading.Thread(target=lambda: send_mail(cfg, to, f"Dauerkarte: Bestellung {order_no} von {name}", text, footer=False), daemon=True).start()
            threading.Thread(target=lambda: send_mail(cfg, email, f"Deine Bestellung {order_no}: Dauerkarte SV Amisia Wolthusen", confirm, footer=False), daemon=True).start()
        notify_async("card_order", f"Dauerkarte: {count} x von {name}", text + "\n\nIm Hub unter Finanzen > Dauerkarte.")
        return back("ok")

    # -- Öffentlicher Bestell-Link (Teamkleidung) -------------------------
    # Nur über den geheimen Link erreichbar. Liefert ausschließlich: Infos zum Artikel, die Bestellfelder,
    # die öffentliche Liste (ohne interne Felder, ohne „bezahlt“) und nimmt neue Bestellungen an.
    def public_order(self, method, p):
        tok = p[0] if p else ""
        a = None
        if re.fullmatch(r"[A-Za-z0-9_-]{16,64}", tok):
            with db() as conn:
                a = conn.execute("SELECT * FROM apparel WHERE public_token=?", (tok,)).fetchone()
        sub = p[1] if len(p) > 1 else ""
        if not a or len(p) > 2:
            if method == "GET" and sub == "":
                return self.send_html(ORDER_INVALID_PAGE, 404)
            return self.send_json({"error": "Dieser Bestell-Link ist ungültig."}, 404)
        fields = apparel_fields(a)
        if method == "GET" and sub == "":
            return self.send_file(STATIC / "order.html")
        if method == "GET" and sub == "bild":
            img = a["image"] or ""
            if not img.startswith("/media/"):
                return self.send_error(404)
            return self.serve_under(MEDIA, [img.rsplit("/", 1)[-1]], inline=MEDIA_INLINE)
        if sub != "daten":
            return self.send_error(404)
        if method == "GET":
            orders, rows = [], []
            with db() as conn:
                club = get_setting(conn, "club_name") or APP_NAME
                if a["show_list"]:
                    rows = conn.execute("SELECT data, quantity FROM apparel_orders WHERE apparel_id=? ORDER BY id", (a["id"],)).fetchall()
            if rows:
                public = [f["key"] for f in fields if not f.get("internal")]
                for r in rows:
                    try:
                        d = json.loads(r["data"] or "{}")
                    except ValueError:
                        d = {}
                    orders.append({"data": {k: d.get(k, "") for k in public}, "quantity": r["quantity"] or 1})
            return self.send_json({
                "name": a["name"], "description": a["description"] or "", "image": bool(a["image"]),
                "price": a["price"], "deadline": a["deadline"] or "", "open": apparel_open(a), "show_list": bool(a["show_list"]),
                "fields": [{k: f.get(k) for k in ("key", "label", "type", "options", "required", "internal")} for f in fields],
                "orders": orders, "club": club,
            })
        if method == "POST":
            if self.headers.get("X-TMH") != "1":
                return self.send_json({"error": "Ungültige Anfrage"}, 403)
            if not apparel_open(a):
                return self.send_json({"error": "Für diesen Artikel ist der Bestellschluss vorbei."}, 400)
            if not order_rate_ok(self.client_ip()):
                return self.send_json({"error": "Zu viele Bestellungen in kurzer Zeit. Bitte später erneut versuchen."}, 429)
            try:
                data = json.loads(self.read_body(20000).decode("utf-8") or "{}")
            except ValueError:
                return self.send_json({"error": "Ungültige Bestellung."}, 400)
            vals, qty, err = clean_order(fields, data.get("data"), data.get("quantity", 1))
            if err:
                return self.send_json({"error": err}, 400)
            now = datetime.now().isoformat(timespec="seconds")
            with db() as conn:
                cur = conn.execute("INSERT INTO apparel_orders (apparel_id, data, quantity, paid, source, created, created_at, updated_at) "
                                   "VALUES (?, ?, ?, 0, 'Link', ?, ?, ?)", (a["id"], json.dumps(vals, ensure_ascii=False), qty, now, now, now))
                audit(conn, "Bestell-Link", "neu", "apparel_orders", cur.lastrowid, a["name"], {**vals, "Menge": qty})
            return self.send_json({"ok": True, "number": cur.lastrowid})
        return self.send_json({"error": "Methode nicht erlaubt"}, 405)

    # -- API --------------------------------------------------------------
    def deny(self, msg="Dafür fehlen dir die Rechte."):
        return self.send_json({"error": msg}, 403)

    def api_gameday(self, method, p, user, perms):
        lvl = 2 if user.get("is_admin") else perms.get("spieltag", 0)
        if lvl < 1:
            return self.deny()
        what = p[0] if p else ""
        now = datetime.now().isoformat(timespec="seconds")
        who = user.get("display_name") or user.get("username") or ""
        if what == "templates":
            with db() as conn:
                if method == "PUT":
                    if lvl < 2:
                        return self.deny()
                    d = self.read_json()
                    for k in ("gd_roles", "gd_checklist"):
                        if k in d:
                            set_setting(conn, k, str(d[k] or "")[:4000])
                    audit(conn, user, "Vorlagen Spieltag geändert", "gd_shifts")
                return self.send_json({k: get_setting(conn, k) for k in ("gd_roles", "gd_checklist")})
        if not what and method == "GET":   # kommende Heimspiele mit Stand
            today = date.today().isoformat()
            with db() as conn:
                out = []
                for g in conn.execute("SELECT * FROM games WHERE IFNULL(home, 0)=1 AND IFNULL(date, '')>=? ORDER BY date, time", (today,)):
                    opp = conn.execute("SELECT name FROM opponents WHERE id=?", (g["opponent_id"],)).fetchone()
                    slots = conn.execute("SELECT IFNULL(SUM(slots), 0) FROM gd_shifts WHERE game_id=?", (g["id"],)).fetchone()[0]
                    filled = conn.execute("SELECT COUNT(*) FROM gd_signups WHERE game_id=?", (g["id"],)).fetchone()[0]
                    checks = conn.execute("SELECT COUNT(*), IFNULL(SUM(done), 0) FROM gd_checks WHERE game_id=?", (g["id"],)).fetchone()
                    mine = conn.execute("SELECT COUNT(*) FROM gd_signups WHERE game_id=? AND user_id=?", (g["id"], user["id"])).fetchone()[0]
                    out.append({"id": g["id"], "date": g["date"], "time": g["time"] or "", "team": g["team"] or MAIN_TEAM, "opponent": opp["name"] if opp else "",
                                "slots": slots, "filled": filled, "checks": checks[0], "checks_done": checks[1], "mine": mine})
            return self.send_json(out)
        if not what.isdigit():
            return self.send_json({"error": "Unbekannter Pfad"}, 404)
        gid, sub = int(what), (p[1] if len(p) > 1 else "")
        with db() as conn:
            g = conn.execute("SELECT * FROM games WHERE id=?", (gid,)).fetchone()
            if not g:
                return self.send_json({"error": "Spiel nicht gefunden"}, 404)
            if sub == "template" and method == "POST":   # Vorlage einfügen (nur was noch fehlt)
                if lvl < 2:
                    return self.deny()
                have = {(r["role"] or "").lower() for r in conn.execute("SELECT role FROM gd_shifts WHERE game_id=?", (gid,))}
                for i, (role, n, st, en) in enumerate(gd_lines(get_setting(conn, "gd_roles"))):
                    if role.lower() not in have:
                        conn.execute("INSERT INTO gd_shifts (game_id, role, start, end, slots, sort, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                                     (gid, role, st, en, n, i, now, now))
                have_c = {(r["text"] or "").lower() for r in conn.execute("SELECT text FROM gd_checks WHERE game_id=?", (gid,))}
                for i, line in enumerate(x.strip() for x in (get_setting(conn, "gd_checklist") or "").splitlines()):
                    if line and line.lower() not in have_c:
                        conn.execute("INSERT INTO gd_checks (game_id, text, done, sort, created_at, updated_at) VALUES (?,?,0,?,?,?)", (gid, line[:200], i, now, now))
                audit(conn, user, "Vorlage Spieltag eingefügt", "games", gid)
            elif sub == "link" and method in ("POST", "PUT"):   # Link erzeugen bzw. neu erzeugen (alter wird ungültig) oder öffnen/schließen
                if lvl < 2:
                    return self.deny()
                d = self.read_json() if method == "PUT" else {}
                if method == "POST":
                    conn.execute("INSERT OR REPLACE INTO gd_links (game_id, token, open, created) VALUES (?, ?, 1, ?)", (gid, secrets.token_urlsafe(18), now))
                    audit(conn, user, "neuer Helfer-Link", "games", gid)
                else:
                    conn.execute("UPDATE gd_links SET open=? WHERE game_id=?", (1 if d.get("open") else 0, gid))
                    audit(conn, user, "Helfer-Link " + ("geöffnet" if d.get("open") else "geschlossen"), "games", gid)
            elif sub == "me" and method in ("POST", "DELETE"):   # selbst eintragen oder austragen (Push-Erinnerung am Vortag)
                d = self.read_json() if method == "POST" else {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
                sid = int(d.get("shift_id") or 0) if str(d.get("shift_id") or "").isdigit() else 0
                sh = conn.execute("SELECT * FROM gd_shifts WHERE id=? AND game_id=?", (sid, gid)).fetchone()
                if not sh:
                    return self.send_json({"error": "Schicht nicht gefunden"}, 404)
                if method == "DELETE":
                    conn.execute("DELETE FROM gd_signups WHERE shift_id=? AND user_id=?", (sid, user["id"]))
                    audit(conn, user, "aus Schicht ausgetragen", "gd_signups", sid, sh["role"])
                else:
                    if conn.execute("SELECT 1 FROM gd_signups WHERE shift_id=? AND user_id=?", (sid, user["id"])).fetchone():
                        return self.send_json({"error": "Du bist hier schon eingetragen."}, 400)
                    if conn.execute("SELECT COUNT(*) FROM gd_signups WHERE shift_id=?", (sid,)).fetchone()[0] >= max(1, int(sh["slots"] or 1)):
                        return self.send_json({"error": "Diese Schicht ist schon voll."}, 400)
                    u = conn.execute("SELECT phone FROM users WHERE id=?", (user["id"],)).fetchone()
                    conn.execute("INSERT INTO gd_signups (shift_id, game_id, name, phone, user_id, source, created, created_at, updated_at) VALUES (?,?,?,?,?,'Hub',?,?,?)",
                                 (sid, gid, who, (u["phone"] if u else "") or "", user["id"], now, now, now))
                    audit(conn, user, "in Schicht eingetragen", "gd_signups", sid, sh["role"])
            elif sub or method != "GET":
                return self.send_json({"error": "Methode nicht erlaubt"}, 405)
            opp = conn.execute("SELECT name FROM opponents WHERE id=?", (g["opponent_id"],)).fetchone()
            shifts = []
            for sh in conn.execute("SELECT * FROM gd_shifts WHERE game_id=? ORDER BY sort, start, id", (gid,)):
                sign = [{k: r[k] for k in ("id", "name", "phone", "user_id", "source", "created")} for r in conn.execute("SELECT * FROM gd_signups WHERE shift_id=? ORDER BY id", (sh["id"],))]
                shifts.append({**{k: sh[k] for k in ("id", "role", "start", "end", "slots", "notes", "sort")}, "signups": sign})
            checks = [{k: r[k] for k in ("id", "text", "done", "done_by", "done_at", "sort")} for r in conn.execute("SELECT * FROM gd_checks WHERE game_id=? ORDER BY sort, id", (gid,))]
            link = conn.execute("SELECT token, open FROM gd_links WHERE game_id=?", (gid,)).fetchone() if lvl >= 2 else None
        return self.send_json({"game": {"id": g["id"], "date": g["date"], "time": g["time"] or "", "team": g["team"] or MAIN_TEAM, "opponent": opp["name"] if opp else "",
                                        "location": g["location"] or ""}, "shifts": shifts, "checks": checks, "can_edit": lvl >= 2, "me": user["id"],
                               "link": {"token": link["token"], "open": bool(link["open"]), "url": self.base_url().rstrip("/") + "/helfer/" + link["token"]} if link else None})

    def api(self, method, p, user):
        try:
            if not p:
                return self.send_json({"app": APP_NAME, "version": VERSION})
            name = p[0]
            self.user = user   # für das Änderungsprotokoll
            perms = user["perms"]
            admin = user["is_admin"]
            can = lambda area, lvl=1: perms.get(area, 0) >= lvl
            # Wartung gibt nur Zugang zur Webseite im Wartungsmodus, kein Leserecht auf Nachschlage-Tabellen
            any_read = any(v >= 1 for a, v in perms.items() if a not in ("wartung", "postfach"))
            any_write = any(v >= 2 for a, v in perms.items() if a not in ("wartung", "postfach"))

            # Zwei-Faktor-Pflicht, aber noch nicht eingerichtet: nur Profil, eigenes Konto und Einstellungen lesen
            if user.get("must_2fa") and not (name in ("me", "profile") or (name == "settings" and method == "GET")):
                return self.send_json({"error": "Bitte richte zuerst unter „Mein Profil“ die Zwei-Faktor-Anmeldung ein.", "need_2fa": True}, 403)

            # --- eigenes Konto und Profil (alle)
            if name == "me" and len(p) > 1 and p[1] == "2fa":
                return self.api_twofa(method, p[2:], user)
            if name == "me":
                if method == "GET":
                    with db() as conn:
                        groups = [r["name"] for r in conn.execute(
                            "SELECT g.name FROM user_groups ug JOIN groups g ON g.id = ug.group_id WHERE ug.user_id=? ORDER BY g.sort, g.name", (user["id"],))]
                        own_addr = own_mail_address(conn, user["id"])
                        boxes = [{"key": k, "address": mail_addr(c)} for k, c in user_mail_boxes(conn, user["id"])]
                        urow = conn.execute("SELECT tabbar, dash_layout FROM users WHERE id=?", (user["id"],)).fetchone()
                        try:
                            tabbar = json.loads(urow["tabbar"] or "[]")
                        except (ValueError, TypeError):
                            tabbar = []
                        try:
                            dash_layout = json.loads(urow["dash_layout"] or "null")
                        except (ValueError, TypeError):
                            dash_layout = None
                    return self.send_json({**user, "perms": {**user["perms"], "ownmail": 2 if own_addr else 0}, "own_mail": own_addr, "mail_boxes": boxes, "tabbar": tabbar, "dash_layout": dash_layout,
                                           "groups": groups, "areas": AREAS, "server": SERVER_MODE, "data": str(DATA) if admin else ""})
                if method == "PUT" and len(p) > 1 and p[1] == "password":
                    data = self.read_json()
                    with db() as conn:
                        u = conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone()
                    if not check_pw(data.get("old") or "", u["pw_hash"]):
                        return self.send_json({"error": "Das bisherige Passwort stimmt nicht."}, 400)
                    prob = pw_problem(data.get("new") or "")
                    if prob:
                        return self.send_json({"error": prob}, 400)
                    with db() as conn:
                        conn.execute("UPDATE users SET pw_hash=?, reset_hash=NULL, reset_expires=NULL WHERE id=?", (hash_pw(data["new"]), user["id"]))
                        conn.execute("DELETE FROM sessions WHERE user_id=? AND token_hash != ?", (user["id"], token_hash(self.session_token())))
                    return self.send_json({"ok": True})
            if name == "profile":
                return self.api_profile(method, user)

            # --- Verwaltung (nur Admins)
            if name == "admin":
                if not admin:
                    return self.deny("Nur für Admins.")
                return self.api_admin(method, p[1:], user)
            if name == "restore" and method == "POST":
                if not admin:
                    return self.deny("Nur für Admins.")
                try:
                    res = restore_backup(self.read_body())
                    with db() as conn:
                        audit(conn, user, "Backup eingespielt", "backup", None, f"{res.get('media', 0)} neue Bilder")
                    return self.send_json(res)
                except ValueError as e:
                    return self.send_json({"error": str(e)}, 400)
            if name in ("backup", "export", "backups"):
                if not admin:
                    return self.deny("Nur für Admins.")
                if name == "backups" and method == "GET":
                    files = sorted(BACKUPS.glob("*.db"), reverse=True)
                    return self.send_json([{"name": f.name, "size": f.stat().st_size} for f in files])
                if name == "backup" and method == "GET":
                    with db() as conn:
                        audit(conn, user, "Backup heruntergeladen", "backup")
                    return self.api_backup()
                if name == "export" and method == "GET":
                    return self.api_export()

            if name == "settings":
                if method != "GET" and not admin:
                    return self.deny("Nur Admins können Einstellungen ändern.")
                return self.api_settings(method, can("finanzen", 1))
            if name == "dashboard" and method == "GET":
                return self.api_dashboard(perms)
            if name == "tabbar" and method == "PUT":   # eigene Tab-Leiste (nur für das eigene Konto, nur Seitennamen, Rechte prüft das Menü)
                pages = self.read_json().get("pages")
                pages = [x for x in pages if isinstance(x, str) and re.fullmatch(r"[a-z]{2,20}", x)][:4] if isinstance(pages, list) else []
                with db() as conn:
                    conn.execute("UPDATE users SET tabbar=? WHERE id=?", (json.dumps(pages) if pages else None, user["id"]))
                return self.send_json({"ok": True, "tabbar": pages})
            if name == "dashlayout" and method == "PUT":   # eigene Übersicht (nur das eigene Konto; welche Widgets erlaubt sind, prüfen die Daten dahinter)
                items = self.read_json().get("widgets")
                clean = [{"k": x["k"], "w": 2 if x.get("w") == 2 else 1} for x in items
                         if isinstance(x, dict) and isinstance(x.get("k"), str) and re.fullmatch(r"[a-z]{2,20}", x["k"])][:40] if isinstance(items, list) else None
                with db() as conn:
                    conn.execute("UPDATE users SET dash_layout=? WHERE id=?", (json.dumps(clean) if clean is not None else None, user["id"]))
                return self.send_json({"ok": True, "dash_layout": clean})
            if name == "gameday":   # Heimspieltag (Bereich spieltag): Übersicht, Spiel, Vorlagen, Link, selbst eintragen
                return self.api_gameday(method, p[1:], user, perms)
            if name == "navcounts" and method == "GET":   # Zahlen an den Menüpunkten (nur was die Person sehen darf)
                out = {}
                with db() as conn:
                    if perms.get("mitglieder", 0) >= 1:
                        out["contacts"] = conn.execute("SELECT COUNT(*) FROM contact_requests WHERE IFNULL(status, 'Neu')='Neu'").fetchone()[0]
                    if perms.get("verein", 0) >= 2:
                        out["players"] = conn.execute("SELECT COUNT(*) FROM player_signups WHERE IFNULL(status, 'Neu')='Neu'").fetchone()[0]
                    if perms.get("finanzen", 0) >= 1:
                        out["cards"] = conn.execute("SELECT COUNT(*) FROM card_orders WHERE IFNULL(paid, 0)=0 AND IFNULL(cancelled, '')=''").fetchone()[0]
                return self.send_json(out)
            if name == "upload" and method == "POST":
                if not any_write:
                    return self.deny()
                return self.api_upload(library=can("medien", 2))
            if name == "player-form":   # Spielerbogen: an/aus, Passwort, Eingänge übernehmen (Bereich Verein)
                if not can("verein", 1):
                    return self.deny()
                if method == "PUT" and len(p) == 1:
                    if not can("verein", 2):
                        return self.deny()
                    data = self.read_json()
                    with db() as conn:
                        changes = {}
                        if data.get("password") is not None and str(data["password"]) != "":
                            pw = str(data["password"])
                            if len(pw) < 8:
                                return self.send_json({"error": "Das Passwort braucht mindestens 8 Zeichen."}, 400)
                            secret_set(conn, "player_form_pw", hash_pw(pw))   # alte Freischaltungen (Cookies) werden damit ungültig
                            changes["Passwort"] = "neu gesetzt"
                        if "open" in data:
                            if data["open"] and not secret_get(conn, "player_form_pw"):
                                return self.send_json({"error": "Bitte zuerst ein Passwort für den Spielerbogen festlegen."}, 400)
                            set_setting(conn, "player_form_open", "1" if data["open"] else "")
                            changes["Spielerbogen"] = "offen" if data["open"] else "geschlossen"
                        if changes:
                            audit(conn, user, "geändert", "settings", None, "Spielerbogen", changes)
                if method in ("GET", "PUT") and len(p) == 1:
                    with db() as conn:
                        return self.send_json({**player_form_state(conn), "url": (SITE_URL or self.base_url()) + "/spielerbogen"})
                if method == "POST" and len(p) == 4 and p[1] == "signups" and p[2].isdigit() and p[3] == "apply":
                    if not can("verein", 2):
                        return self.deny()
                    target = self.read_json().get("player_id")
                    with db() as conn:
                        s = conn.execute("SELECT * FROM player_signups WHERE id=?", (int(p[2]),)).fetchone()
                        if not s:
                            return self.send_json({"error": "Eingang nicht gefunden."}, 404)
                        if s["status"] == "Übernommen":
                            return self.send_json({"error": "Dieser Eingang ist schon übernommen."}, 400)
                        if target and not conn.execute("SELECT 1 FROM players WHERE id=?", (int(target),)).fetchone():
                            return self.send_json({"error": "Person nicht gefunden."}, 404)
                        pid = player_signup_apply(conn, s, int(target) if target else None, user)
                    return self.send_json({"ok": True, "player_id": pid})
                return self.send_error(404)
            if name == "cards" and p[1:] == ["online"]:   # Online-Bestellung der Dauerkarte an/aus
                if not can("finanzen", 1):
                    return self.deny()
                if method == "PUT":
                    if not can("finanzen", 2):
                        return self.deny()
                    data = self.read_json()
                    if any(k in data and money(data[k]) is None for k in ("card_shipping", "card_shipping_registered")):
                        return self.send_json({"error": "Versandkosten bitte als Betrag angeben, z. B. 1,50."}, 400)
                    if "inv_iban" in data and data["inv_iban"] and not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", re.sub(r"\s", "", str(data["inv_iban"]).upper())):
                        return self.send_json({"error": "Die IBAN sieht nicht gültig aus."}, 400)
                    changed = {}
                    with db() as conn:
                        if "open" in data:
                            set_setting(conn, "site_card_order_open", "1" if data["open"] else "")
                            changed["Online-Bestellung"] = "offen" if data["open"] else "geschlossen"
                        if "text" in data:
                            set_setting(conn, "site_card_order_text", str(data["text"])[:2000])
                        for k in CARD_SETTING_KEYS:
                            if k in data:
                                v = str(data[k] or "").strip()[:3000]
                                if k in ("card_shipping", "card_shipping_registered"):
                                    v = f"{money(v):.2f}"
                                if k == "inv_due_days":
                                    v = v if v.isdigit() and 0 < int(v) < 100 else "14"
                                if k == "inv_iban":
                                    v = " ".join(re.findall(".{1,4}", re.sub(r"\s", "", v.upper())))
                                if get_setting(conn, k) != v:
                                    set_setting(conn, k, v)
                                    changed[k] = "geändert"
                        audit(conn, user, "geändert", "settings", None, "Dauerkarte online", changed)
                with db() as conn:
                    return self.send_json({"open": get_setting(conn, "site_card_order_open") == "1",
                                           "text": get_setting(conn, "site_card_order_text"), "url": (SITE_URL or "") + "/supporter-karte",
                                           "price": get_setting(conn, "card_price"), "smtp": bool(smtp_config()["smtp_host"]),
                                           **{k: get_setting(conn, k) for k in CARD_SETTING_KEYS}})
            if name == "cards" and len(p) >= 4 and p[1] == "orders" and p[2].isdigit():   # Bestellung: bezahlt, Rechnung
                oid, act = int(p[2]), "/".join(p[3:])
                if method == "GET" and act in ("invoice.pdf", "letter.pdf"):
                    if not can("finanzen", 1):
                        return self.deny()
                    if act == "letter.pdf":   # Fanbrief zum Ausdrucken, wird jedes Mal frisch erzeugt
                        with db() as conn:
                            o = conn.execute("SELECT * FROM card_orders WHERE id=?", (oid,)).fetchone()
                            body = card_letter_pdf(o, conn) if o else None
                        fname = f"Fanbrief {o['order_no']}.pdf" if o else ""
                    else:
                        o, body = card_invoice_file(oid)
                        fname = f"Rechnung {o['invoice_no']}.pdf" if body else ""
                    if not body:
                        return self.send_json({"error": "Für diese Bestellung gibt es noch keine Rechnung." if act == "invoice.pdf" else "Bestellung nicht gefunden."}, 404)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("Content-Disposition", f'inline; filename="{fname}"')
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if method == "POST" and act == "cancel":   # Stornieren im Hub (nur bis Zahlungseingang), Kunde bekommt eine Bestätigung
                    if not can("finanzen", 2):
                        return self.deny()
                    o, err, mail_err = card_order_cancel(oid, user.get("display_name") or user.get("username") or "Hub", user)
                    if err:
                        return self.send_json({"error": {"nicht gefunden": "Bestellung nicht gefunden.", "storniert": "Die Bestellung ist schon storniert.",
                                                         "bezahlt": "Die Bestellung ist schon bezahlt und kann nicht mehr storniert werden."}[err]},
                                              404 if err == "nicht gefunden" else 400)
                    return self.send_json({"ok": True, "mail_error": mail_err})
                if method == "POST" and act == "shipped":   # verschickt: Versandbestätigung an den Kunden (Einschreiben mit Sendungsnummer)
                    if not can("finanzen", 2):
                        return self.deny()
                    o, err, mail_err = card_order_shipped(oid, self.read_json().get("tracking_no"), user)
                    if err:
                        return self.send_json({"error": err}, 404 if "nicht gefunden" in err else 400)
                    return self.send_json({"ok": True, "tracking_no": o["tracking_no"], "mail_error": mail_err})
                if method == "POST" and act in ("paid", "invoice"):
                    if not can("finanzen", 2):
                        return self.deny()
                    if act == "paid":
                        o, err = card_order_paid(oid, user)
                        if not o:
                            return self.send_json({"error": err}, 404 if "nicht gefunden" in err else 400)
                        return self.send_json({"ok": True, "invoice_no": o["invoice_no"], "mail_error": err})
                    o, pdf = card_invoice_file(oid)
                    if not pdf:
                        return self.send_json({"error": "Für diese Bestellung gibt es noch keine Rechnung."}, 404)
                    err = card_invoice_send(o, pdf, user)
                    return self.send_json({"ok": not err, "mail_error": err})
                return self.send_error(404)
            if name == "postfach":
                return self.api_postfach(method, p[1:], user, can)
            if name == "mailtasks":
                return self.api_mailtasks(method, p[1:], user, can)
            if name == "push":
                return self.api_push(method, p[1:], user)
            if name == "maintenance":
                return self.api_maintenance(method, p[1:], user, can)
            if name == "website":
                return self.api_website(method, p[1:], user, can)
            if name == "newsletter":
                return self.api_newsletter(method, p[1:], user, can)
            if name == "sponsor-contracts":
                return self.api_sponsor_contracts(method, p[1:], user, can)
            if name == "social":
                return self.api_social(method, p[1:], user, can)
            if name == "notify":
                return self.api_notify(method, p[1:], user)
            if name == "migrate":
                if not admin:
                    return self.deny("Nur für Admins.")
                return self.api_migrate(method, p[1:], user)

            if name == "apparel" and method == "POST" and len(p) == 3 and p[2] == "book":
                # Sammelbuchung: alle bezahlten, noch nicht gebuchten Bestellungen als eine Einnahme
                if not can("finanzen", 2):
                    return self.deny("Für Buchungen braucht es Bearbeiten-Rechte bei Finanzen.")
                with db() as conn:
                    a = conn.execute("SELECT * FROM apparel WHERE id=?", (int(p[1]),)).fetchone()
                    if not a:
                        return self.send_json({"error": "Artikel nicht gefunden."}, 404)
                    if not a["price"]:
                        return self.send_json({"error": "Für den Artikel ist kein Preis eingetragen."}, 400)
                    rows = conn.execute("SELECT id, quantity FROM apparel_orders WHERE apparel_id=? AND paid=1 AND booked_tx IS NULL", (a["id"],)).fetchall()
                    if not rows:
                        return self.send_json({"error": "Es gibt keine neuen bezahlten Bestellungen."}, 400)
                    pcs = sum(r["quantity"] or 1 for r in rows)
                    now = datetime.now().isoformat(timespec="seconds")
                    vals = {"date": now[:10], "kind": "Einnahme", "category": "Teamkleidung",
                            "description": f"{a['name']}: {len(rows)} Bestellung{'en' if len(rows) > 1 else ''}, {pcs} Stück",
                            "amount": round(a["price"] * pcs, 2), "status": "Erledigt", "paid_by": "Besteller",
                            "notes": "Bestellnummern: " + ", ".join(f"#{r['id']}" for r in rows), "created_at": now, "updated_at": now}
                    cur = conn.execute(f"INSERT INTO transactions ({', '.join(vals)}) VALUES ({', '.join('?' for _ in vals)})", list(vals.values()))
                    conn.execute(f"UPDATE apparel_orders SET booked_tx=? WHERE id IN ({', '.join('?' for _ in rows)})", [cur.lastrowid, *[r["id"] for r in rows]])
                    audit(conn, user, "neu", "transactions", cur.lastrowid, vals["description"], {"Betrag": vals["amount"], "Bestellungen": vals["notes"]})
                return self.send_json({"ok": True, "transaction_id": cur.lastrowid, "amount": vals["amount"], "orders": len(rows)})

            if name == "apparel" and method == "POST" and len(p) == 3 and p[2] == "new-link":
                if max(perms.get(a, 0) for a in TABLE_AREAS_ANY["apparel"]) < 2:
                    return self.deny()
                with db() as conn:
                    conn.execute("UPDATE apparel SET public_token=? WHERE id=?", (secrets.token_urlsafe(18), int(p[1])))
                    a = conn.execute("SELECT name FROM apparel WHERE id=?", (int(p[1]),)).fetchone()
                    audit(conn, user, "neuer Bestell-Link", "apparel", int(p[1]), a["name"] if a else "")
                return self.send_json({"ok": True})

            if name in TABLES:
                area = TABLE_AREA.get(name)
                lvl = max(perms.get(a, 0) for a in TABLE_AREAS_ANY.get(name, (area,)))
                if name in ADMIN_TABLES:
                    if not admin:
                        return self.deny("Nur für Admins.")
                    lvl = 2
                if method == "GET":
                    if not (lvl >= 1 or (name in SHARED_READ and any_read)):
                        return self.deny()
                elif name == "media" and method == "POST":
                    return self.deny()
                elif lvl < 2:
                    return self.deny(f"Für den Bereich {AREAS.get(area, area)} hast du nur Leserechte.")
                rid = int(p[1]) if len(p) > 1 else None
                return self.api_table(method, name, rid, perms)

            return self.send_json({"error": "Unbekannter Pfad"}, 404)
        except PayloadTooLarge:
            raise
        except Exception as e:  # noqa
            print("Fehler:", repr(e))
            return self.send_json({"error": str(e)}, 500)

    # -- Serverumzug (nur Admins) ------------------------------------------
    def api_migrate(self, method, p, user):
        sub = p[0] if p else ""
        if method == "POST" and sub == "export":
            pw = self.read_json().get("password") or ""
            if len(pw) < 10:
                return self.send_json({"error": "Das Passwort für die Umzugsdatei braucht mindestens 10 Zeichen."}, 400)
            with db() as conn:   # vorher protokollieren, damit der Eintrag mit umzieht
                audit(conn, user, "Komplett-Export erstellt", "backup", None, "Serverumzug")
            path = migrate_export(pw)
            return self.send_json({"download": f"/api/migrate/download/{path.stem[len('_umzug_'):]}", "size": path.stat().st_size})
        if method == "GET" and sub == "download" and len(p) == 2 and re.fullmatch(r"[0-9a-f]{32}", p[1]):
            path = DATA / f"_umzug_{p[1]}.wolthusen"
            if not path.is_file():
                return self.send_json({"error": "Die Umzugsdatei ist nicht mehr da. Bitte neu erstellen."}, 404)
            try:
                return self.send_stream(path, f"WolthusenHub-Umzug-{datetime.now():%Y-%m-%d}.wolthusen")
            finally:
                path.unlink(missing_ok=True)   # nur einmal herunterladbar
        if method == "POST" and sub == "import":
            try:
                pw = base64.b64decode(self.headers.get("X-Umzug-Passwort") or "").decode("utf-8")
            except ValueError:
                pw = ""
            if not pw:
                return self.send_json({"error": "Bitte das Passwort der Umzugsdatei angeben."}, 400)
            upload = DATA / f"_umzug_upload_{secrets.token_hex(8)}.wolthusen"
            try:
                self.save_body(upload, MIGRATE_MAX)
                res = migrate_import(upload, pw)
            except ValueError as e:
                return self.send_json({"error": str(e)}, 400)
            finally:
                upload.unlink(missing_ok=True)
            with db() as conn:
                audit(conn, user, "Komplett-Import eingespielt", "backup", None, "Serverumzug", res)
            return self.send_json(res)
        return self.send_json({"error": "Unbekannter Pfad"}, 404)

    # -- E-Mail-Versand (nur Admins) ---------------------------------------
    def api_notify(self, method, p, user):
        if not user["is_admin"]:
            return self.deny("Nur Admins können den E-Mail-Versand einrichten.")
        sub = p[0] if p else ""
        if method == "GET" and not sub:
            with db() as conn:
                cfg = {k: secret_get(conn, k) for k in SMTP_KEYS}
                cfg["password_set"] = bool(secret_get(conn, "smtp_password"))
                cfg["last_error"] = secret_get(conn, "smtp_last_error")
            return self.send_json(cfg)
        if method == "PUT" and not sub:
            data = self.read_json()
            with db() as conn:
                for k in SMTP_KEYS:
                    if k in data:
                        secret_set(conn, k, str(data[k] or "").strip())
                if (data.get("smtp_password") or "").strip():
                    secret_set(conn, "smtp_password", data["smtp_password"].strip())
                audit(conn, user, "geändert", "settings", None, "E-Mail-Versand", {k: audit_short(data.get(k)) for k in SMTP_KEYS if k in data})
            return self.send_json({"ok": True})
        if method == "POST" and sub == "test":
            to = (self.read_json().get("to") or "").strip()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to):
                return self.send_json({"error": "Bitte eine gültige E-Mail-Adresse angeben."}, 400)
            cfg = smtp_config()
            if not cfg["smtp_host"]:
                return self.send_json({"error": "Es ist noch kein Mailserver eingetragen."}, 400)
            err = send_mail(cfg, to, "Wolthusen Hub: Test-Nachricht", "Der E-Mail-Versand des Wolthusen Hub funktioniert.")
            if err:
                return self.send_json({"error": f"Versand fehlgeschlagen: {err}"}, 400)
            return self.send_json({"ok": True})
        return self.send_json({"error": "Unbekannter Pfad"}, 404)

    # -- Auto-Posting (Facebook/Instagram) ---------------------------------
    def api_social(self, method, p, user, can):
        sub = p[0] if p else ""
        if method == "GET" and not sub:
            if not can("medien", 1):
                return self.deny()
            cfg = social_config()
            return self.send_json({"connected": bool(cfg["fb_token"]), "page": cfg["fb_page_name"], "instagram": cfg["ig_username"],
                                   "public_url": cfg["public_url"], "is_admin": bool(user["is_admin"])})
        if method == "GET" and sub in ("insights", "online"):
            if not can("medien", 1):
                return self.deny()
            cfg = social_config()
            if not cfg["fb_token"]:
                return self.send_json({"error": "Es ist noch keine Facebook-Seite verbunden."}, 400)
            q = parse_qs(urlparse(self.path).query)
            refresh = (q.get("refresh") or [""])[0] == "1"
            if sub == "insights":
                days = 7 if (q.get("days") or ["28"])[0] == "7" else 28
                return self.send_json(social_cached(f"insights{days}", refresh, lambda: social_insights(cfg, days)))
            return self.send_json(social_cached("online", refresh, lambda: social_online(cfg)))
        if sub == "connection":
            if not user["is_admin"]:
                return self.deny("Nur Admins können die Verbindung einrichten.")
            SOCIAL_CACHE.clear()
            if method == "DELETE":
                with db() as conn:
                    for k in ("fb_token", "fb_page_id", "fb_page_name", "ig_user_id", "ig_username"):
                        secret_set(conn, k, "")
                    audit(conn, user, "Verbindung getrennt", "social", None, "Facebook/Instagram")
                return self.send_json({"ok": True})
            if method == "PUT":
                data = self.read_json()
                token = (data.get("token") or "").strip() or social_config()["fb_token"]
                if not token:
                    return self.send_json({"error": "Bitte das Seiten-Token eintragen."}, 400)
                try:
                    res = social_connect(token, data.get("public_url"))
                    with db() as conn:
                        audit(conn, user, "verbunden", "social", None, "Facebook/Instagram", res)
                    return self.send_json(res)
                except GraphError as e:
                    return self.send_json({"error": f"Verbindung fehlgeschlagen: {e}"}, 400)
                except (KeyError, TypeError):
                    return self.send_json({"error": "Das Token gehört zu keiner Facebook-Seite. Bitte ein Seiten-Token verwenden."}, 400)
        if sub == "publish" and method == "POST":
            if not can("medien", 2):
                return self.deny()
            data = self.read_json()
            cfg = social_config()
            if not cfg["fb_token"]:
                return self.send_json({"error": "Es ist noch keine Facebook-Seite verbunden."}, 400)
            with SOCIAL_LOCK, db() as conn:
                if data.get("post_id"):
                    row = conn.execute("SELECT * FROM posts WHERE id=?", (int(data["post_id"]),)).fetchone()
                    if not row:
                        return self.send_json({"error": "Post nicht gefunden."}, 404)
                    if row["publish_state"] in ("gepostet", "läuft") and not data.get("again"):
                        return self.send_json({"error": "Dieser Post ist schon gepostet."}, 400)
                    conn.execute("UPDATE posts SET publish_state='läuft' WHERE id=?", (row["id"],))
                elif data.get("rule_id"):
                    row = conn.execute("SELECT * FROM story_rules WHERE id=?", (int(data["rule_id"]),)).fetchone()
                    if not row:
                        return self.send_json({"error": "Regel nicht gefunden."}, 404)
                else:
                    return self.send_json({"error": "Nichts ausgewählt."}, 400)
            with SOCIAL_LOCK:
                state, log = publish_post(cfg, row) if data.get("post_id") else publish_rule(cfg, row)
            with db() as conn:
                audit(conn, user, "jetzt gepostet", "posts" if data.get("post_id") else "story_rules", row["id"],
                      row["title"] if data.get("post_id") else row["name"], {"Ergebnis": log})
            return self.send_json({"state": state, "log": log})
        if sub == "reset" and method == "POST":
            # Post nach Fehler oder verpasstem Termin wieder einplanen
            if not can("medien", 2):
                return self.deny()
            with db() as conn:
                conn.execute("UPDATE posts SET publish_state=NULL WHERE id=? AND publish_state IN ('fehler', 'verpasst', 'teilweise', 'läuft')",
                             (int(self.read_json().get("post_id") or 0),))
            return self.send_json({"ok": True})
        return self.send_json({"error": "Unbekannter Pfad"}, 404)

    # -- Zwei-Faktor-Anmeldung des eigenen Kontos (/api/me/2fa) ------------
    def api_twofa(self, method, p, user):
        what = p[0] if p else ""
        uid = user["id"]
        if method == "GET" and not what:
            with db() as conn:
                r = twofa_row(conn, uid)
                on = bool(r and r["enabled"])
                return self.send_json({"enabled": on, "required": twofa_required(conn, user, user["perms"]),
                                       "recovery_left": len(json.loads(r["recovery"] or "[]")) if on else 0,
                                       "enabled_at": r["enabled_at"] if on else None})
        if method != "POST":
            return self.send_json({"error": "Unbekannter Pfad"}, 404)
        data = self.read_json()
        if what in ("setup", "recovery", "disable"):   # nur mit dem Passwort (schützt vor fremder Nutzung einer offenen Sitzung)
            with db() as conn:
                pw_hash = conn.execute("SELECT pw_hash FROM users WHERE id=?", (uid,)).fetchone()["pw_hash"]
            if not check_pw(data.get("password") or "", pw_hash):
                login_failed(self.client_ip())
                time.sleep(0.6)
                return self.send_json({"error": "Das Passwort stimmt nicht."}, 400)
        with db() as conn:
            r = twofa_row(conn, uid)
            on = bool(r and r["enabled"])
            if what == "setup":
                if on:
                    return self.send_json({"error": "Die Zwei-Faktor-Anmeldung ist schon eingerichtet."}, 400)
                secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
                conn.execute("INSERT INTO user_2fa (user_id, enabled, pending_secret, pending_expires) VALUES (?, 0, ?, ?) "
                             "ON CONFLICT(user_id) DO UPDATE SET pending_secret=excluded.pending_secret, pending_expires=excluded.pending_expires",
                             (uid, secret, time.time() + 900))
                return self.send_json({"secret": secret, "uri": totp_uri(secret, user["username"]), "issuer": TOTP_ISSUER, "account": user["username"]})
            if what == "enable":
                if on:
                    return self.send_json({"error": "Die Zwei-Faktor-Anmeldung ist schon eingerichtet."}, 400)
                if not r or not r["pending_secret"] or (r["pending_expires"] or 0) < time.time():
                    return self.send_json({"error": "Die Einrichtung ist abgelaufen. Bitte noch einmal starten."}, 400)
                step = totp_match(r["pending_secret"], data.get("code") or "")
                if not step:
                    time.sleep(0.4)
                    return self.send_json({"error": "Der Code stimmt nicht. Prüfe, ob die Uhrzeit am Handy stimmt, und gib den aktuellen Code ein."}, 400)
                codes, hashes = recovery_new()
                conn.execute("UPDATE user_2fa SET secret=pending_secret, pending_secret=NULL, pending_expires=NULL, enabled=1, last_step=?, "
                             "recovery=?, enabled_at=? WHERE user_id=?", (step, json.dumps(hashes), datetime.now().isoformat(timespec="seconds"), uid))
                conn.execute("DELETE FROM sessions WHERE user_id=? AND token_hash != ?", (uid, token_hash(self.session_token())))   # andere Geräte neu anmelden
                audit(conn, user, "Zwei-Faktor-Anmeldung eingerichtet", "users", uid, user["display_name"])
                return self.send_json({"ok": True, "codes": codes})
            if what == "recovery":
                if not on:
                    return self.send_json({"error": "Die Zwei-Faktor-Anmeldung ist nicht eingerichtet."}, 400)
                codes, hashes = recovery_new()
                conn.execute("UPDATE user_2fa SET recovery=? WHERE user_id=?", (json.dumps(hashes), uid))
                audit(conn, user, "Neue Wiederherstellungscodes", "users", uid, user["display_name"])
                return self.send_json({"ok": True, "codes": codes})
            if what == "disable":
                if not on:
                    return self.send_json({"error": "Die Zwei-Faktor-Anmeldung ist nicht eingerichtet."}, 400)
                if twofa_required(conn, user, user["perms"]):
                    return self.send_json({"error": "Für dein Konto ist die Zwei-Faktor-Anmeldung Pflicht. Ausschalten kann sie nur ein Admin (zurücksetzen)."}, 400)
                conn.execute("DELETE FROM user_2fa WHERE user_id=?", (uid,))
                audit(conn, user, "Zwei-Faktor-Anmeldung ausgeschaltet", "users", uid, user["display_name"])
                return self.send_json({"ok": True})
        return self.send_json({"error": "Unbekannter Pfad"}, 404)

    # -- Postfach (/api/postfach, Bereich postfach: Lesen 1, Antworten und Löschen 2) --
    def api_postfach(self, method, p, user, can):
        sub = p[0] if p else ""
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        folder = (q.get("folder") or "INBOX")[:200]
        uid = q.get("uid") or ""
        if uid and not uid.isdigit():
            return self.send_json({"error": "Ungültige Mail."}, 400)
        body = self.read_json() if method == "POST" else {}
        bsel = str(q.get("box") or (body.get("box") if isinstance(body, dict) else "") or "")[:20]   # info, acc<id> oder own (= erstes eigenes)
        own_box = bsel not in ("", "info")
        own_cfg_box, bkey = None, "info"
        if own_box:
            with db() as conn:
                mine = user_mail_boxes(conn, user["id"])
            hit = (mine[0] if mine else None) if bsel == "own" else next((x for x in mine if x[0] == bsel), None)
            if not hit:
                return self.send_json({"error": "Dieses Postfach ist deinem Konto nicht zugewiesen."}, 404)
            bkey, own_cfg_box = hit
            if sub in ("assign", "people"):
                return self.deny()
        task = False   # Person ohne Postfach-Recht, der genau diese Mail zugewiesen ist: lesen und antworten
        if own_box:
            pass
        elif not can("postfach", 1):
            if sub in ("message", "attachment") and uid:
                tf, tu = folder, uid
            elif sub == "send" and isinstance(body.get("reply"), dict):
                tf, tu = str(body["reply"].get("folder") or "INBOX")[:200], str(body["reply"].get("uid") or "")
            else:
                return self.deny()
            with db() as conn:
                task = tu.isdigit() and mail_task_access(conn, user["id"], tf, tu)
            if not task:
                return self.deny()
        write = method != "GET" and sub not in ("flag", "handled", "allread", "allhandled")   # gelesen markieren darf, wer lesen darf
        if write and not task and not own_box and not can("postfach", 2):
            return self.deny("Zum Antworten, Zuweisen und Löschen braucht es Bearbeiten im Bereich Postfach.")
        self._pf_body = body
        m = None
        try:
            if sub == "status" and method == "GET" and own_box:
                return self.send_json({"configured": True, "unseen": pf_unseen(own_cfg_box), "address": own_cfg_box["smtp_user"], "server": own_cfg_box["imap"]})
            if sub == "status" and method == "GET":
                cfg = postfach_config()
                if not (cfg["imap"] and cfg["smtp_user"] and cfg["smtp_password"]):
                    return self.send_json({"configured": False})
                return self.send_json({"configured": True, "unseen": pf_unseen(), "address": cfg["smtp_user"], "server": cfg["imap"]})
            if sub == "allhandled" and method == "POST":   # alle „neu“-Hinweise des Ordners weg, Mails bleiben liegen
                if own_box:
                    return self.send_json({"ok": True, "count": 0})
                n = pf_mark_all_handled(str(self._pf_body.get("folder") or "INBOX")[:200], user)
                with db() as conn:
                    audit(conn, user, "Mails erledigt", "postfach", None, f"{n} Mails als erledigt markiert", {})
                return self.send_json({"ok": True, "count": n})
            if sub == "handled" and method == "POST":   # „Erledigt“ ohne Antwort
                d_ = self._pf_body
                if not str(d_.get("uid") or "").isdigit():
                    return self.send_json({"error": "Ungültige Mail."}, 400)
                fold = str(d_.get("folder") or "INBOX")[:200]
                ok = True if own_box else pf_mark_handled(fold, int(d_["uid"]), user, "als erledigt markiert")
                try:
                    moved = pf_move_to_done(fold, int(d_["uid"]), own_cfg_box)
                except Exception as e:  # noqa
                    return self.send_json({"ok": ok, "moved": False, "note": f"Erledigt, aber nicht verschoben: {e}"})
                return self.send_json({"ok": ok, "moved": bool(moved), "folder": moved[0] if moved else fold, "uid": moved[1] if moved else int(d_["uid"])})
            if sub == "people":
                if not can("postfach", 2):
                    return self.deny()
                with db() as conn:
                    rows = conn.execute("SELECT id, display_name, username, mail_role, email, member_id, is_admin FROM users WHERE active=1 AND pw_hash != '' "
                                        "ORDER BY COALESCE(display_name, username) COLLATE NOCASE").fetchall()
                    out = []
                    for r in rows:
                        no_access = effective_perms(conn, {"id": r["id"], "is_admin": r["is_admin"]}).get("postfach", 0) < 1
                        out.append({"id": r["id"], "name": r["display_name"] or r["username"], "role": r["mail_role"] or "",
                                    "forward": (own_mail_address(conn, r["id"]) or account_email(conn, r)) or ("-" if no_access else "")})
                return self.send_json(out)
            m, cfg = postfach_open(own_cfg_box)
            boxw = own_box or can("postfach", 2)   # im eigenen Postfach darf das Konto alles
            if sub == "folders" and method == "GET":
                if boxw and not pf_done_folder(m, create=False):   # Ordner „Erledigt“ immer anzeigen
                    with contextlib.suppress(Exception):
                        pf_done_folder(m)
                folders = postfach_folders(m)
                for f in folders:
                    if f["role"] == "inbox":
                        typ, data = m.status(imap_quote(f["name"]), "(UNSEEN)")
                        mm = re.search(rb"UNSEEN (\d+)", data[0] if data else b"")
                        f["unseen"] = int(mm.group(1)) if mm else 0
                with db() as conn:
                    senders, dflt, _c = pf_senders(conn, user, can("postfach", 2), bkey)
                    send_as = next(x["address"] for x in senders if x["key"] == dflt)
                    sig, sig_html = signature_parts(conn, user["id"], send_as, preview=True)
                boxes = ([{"key": "info", "address": postfach_config()["smtp_user"]}] if can("postfach", 1) else []) + \
                        [x for x in senders if x["key"] != "info"]
                return self.send_json({"folders": folders, "address": cfg["smtp_user"], "box": bkey, "boxes": boxes, "quota": pf_quota(m),
                                       "can_write": boxw, "signature": sig, "signature_html": sig_html, "send_as": send_as, "senders": senders, "sender": dflt})
            if sub == "messages" and method == "GET":
                from email import policy
                from email.parser import BytesHeaderParser
                pf_select(m, folder)
                term = (q.get("q") or "").strip()[:100]
                if term:
                    m.literal = term.encode("utf-8")   # als Literal, damit auch Umlaute gesucht werden können
                    typ, data = m.uid("SEARCH", "CHARSET", "UTF-8", "TEXT")
                else:
                    typ, data = m.uid("SEARCH", None, "ALL")
                uids = (data[0] or b"").split()[::-1]
                page = max(0, int(q.get("page") or 0)) if (q.get("page") or "0").isdigit() else 0
                sel = uids[page * PF_PAGE:(page + 1) * PF_PAGE]
                items = []
                if sel:
                    typ, data = m.uid("FETCH", b",".join(sel), "(UID FLAGS RFC822.SIZE BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])")
                    for x in data or []:
                        if not isinstance(x, tuple):
                            continue
                        meta = x[0]
                        um = re.search(rb"UID (\d+)", meta)
                        if not um:
                            continue
                        h = BytesHeaderParser(policy=policy.compat32).parsebytes(x[1])
                        fl = re.search(rb"FLAGS \(([^)]*)\)", meta)
                        flags = (fl.group(1) if fl else b"").decode()
                        low = meta.lower()
                        items.append({"uid": int(um.group(1)), "from": pf_head(h.get("From")), "to": pf_head(h.get("To")), "subject": pf_head(h.get("Subject")) or "(ohne Betreff)",
                                      "date": h.get("Date") or "", "seen": "\\Seen" in flags, "answered": "\\Answered" in flags, "flagged": "\\Flagged" in flags,
                                      "attachment": b'"attachment"' in low or b'("name"' in low or b'"filename"' in low})
                    items.sort(key=lambda i: -i["uid"])
                    tasks, fresh = {}, {}
                    if not own_box:   # Zuweisungen und Erledigt-Vermerke gibt es nur im Vereinspostfach
                        with db() as conn:
                            for t in conn.execute("SELECT * FROM mail_tasks WHERE folder=? ORDER BY id", (folder,)):
                                tasks[t["uid"]] = mail_task_row(conn, t)
                            fresh = {r["uid"]: r["status"] for r in conn.execute("SELECT uid, status FROM pf_inbox WHERE folder=?", (folder,))}
                    for it in items:
                        it["inbox"] = fresh.get(it["uid"], "")
                        t = tasks.get(it["uid"])
                        it["task"] = {"id": t["id"], "user": t["user_name"], "status": t["status"]} if t else None
                return self.send_json({"folder": folder, "total": len(uids), "page": page, "pages": max(1, -(-len(uids) // PF_PAGE)), "items": items})
            if sub == "message" and method == "GET" and uid:
                msg, flags = pf_message(m, folder, uid, mark_seen=q.get("peek") != "1" and not task)
                with db() as conn:
                    tasks = [] if own_box else [mail_task_row(conn, t) for t in conn.execute("SELECT * FROM mail_tasks WHERE folder=? AND uid=? ORDER BY id DESC", (folder, int(uid)))]
                    senders, dflt, _c = pf_senders(conn, user, can("postfach", 2) or bool(task), bkey)
                    send_as = next(x["address"] for x in senders if x["key"] == dflt)
                    sig, sig_html = signature_parts(conn, user["id"], send_as, preview=True)
                    ib = None if own_box else conn.execute("SELECT status, action, handled_at, handled_by FROM pf_inbox WHERE folder=? AND uid=? ORDER BY id DESC", (folder, int(uid))).fetchone()
                    hb = conn.execute("SELECT display_name, username FROM users WHERE id=?", (ib["handled_by"],)).fetchone() if ib and ib["handled_by"] else None
                inbox = {"status": ib["status"], "action": ib["action"] or "", "at": ib["handled_at"] or "", "by": (hb["display_name"] or hb["username"]) if hb else ""} if ib else None
                return self.send_json({"inbox": inbox, "tasks": tasks, "signature": sig, "signature_html": sig_html, "send_as": send_as, "senders": senders, "sender": dflt,
                                       "box": bkey, "can_write": boxw or bool(task), "can_assign": can("postfach", 2) and not own_box,
                                       "uid": int(uid), "folder": folder, "from": pf_head(msg.get("From")), "to": pf_head(msg.get("To")), "cc": pf_head(msg.get("Cc")),
                                       "reply_to": pf_head(msg.get("Reply-To")), "subject": pf_head(msg.get("Subject")) or "(ohne Betreff)", "date": msg.get("Date") or "",
                                       "text": pf_text(msg), "attachments": pf_attachments(msg), "answered": b"\\Answered" in flags,
                                       "draft": b"\\Draft" in flags or folder == pf_role_folder(m, "drafts")})
            if sub == "attachment" and method == "GET" and uid and (q.get("i") or "").isdigit():
                msg, _ = pf_message(m, folder, uid, mark_seen=False)
                parts = list(msg.iter_attachments())
                i = int(q["i"])
                if i >= len(parts):
                    return self.send_json({"error": "Anhang nicht gefunden."}, 404)
                part = parts[i]
                body = part.get_payload(decode=True) or b""
                name = re.sub(r'[^\w.\- ()äöüÄÖÜß]', "_", pf_head(part.get_filename() or "") or f"anhang-{i + 1}")[:150]
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")   # nie im Hub anzeigen (kein HTML/SVG im Hub-Kontext)
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name)}")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if sub == "flag" and method == "POST":
                data = self._pf_body
                tuid = str(data.get("uid") or "")
                if not tuid.isdigit():
                    return self.send_json({"error": "Ungültige Mail."}, 400)
                pf_select(m, str(data.get("folder") or "INBOX")[:200], readonly=False)
                flag = {"seen": "\\Seen", "flagged": "\\Flagged"}.get(data.get("flag") or "seen", "\\Seen")
                m.uid("STORE", tuid, "+FLAGS" if data.get("value") else "-FLAGS", f"({flag})")
                return self.send_json({"ok": True})
            if sub == "draft" and method == "POST":   # Entwurf im Ordner „Entwürfe“ des geöffneten Postfachs speichern, alter Entwurf wird ersetzt
                import imaplib
                from email.message import EmailMessage
                from email.utils import formatdate, make_msgid
                data = self._pf_body
                drafts = pf_role_folder(m, "drafts")
                if not drafts:
                    return self.send_json({"error": "Dieses Postfach hat keinen Ordner für Entwürfe."}, 400)
                one = lambda k, n: re.sub(r"[\r\n]+", " ", str(data.get(k) or "")).strip()[:n]   # keine Zeilenumbrüche in Kopfzeilen
                msg = EmailMessage()
                msg["From"] = mail_sender(own_cfg_box or postfach_config())[0]
                for head, key in (("To", "to"), ("Cc", "cc")):
                    if one(key, 2000):
                        msg[head] = one(key, 2000)
                msg["Subject"] = one("subject", 250)
                msg["Date"], msg["Message-ID"] = formatdate(localtime=True), make_msgid()
                msg.set_content(str(data.get("body") or "")[:100000])
                typ, _ = m.append(imap_quote(drafts), "(\\Draft \\Seen)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
                if typ != "OK":
                    return self.send_json({"error": "Entwurf konnte nicht gespeichert werden."}, 400)
                old = data.get("replace") if isinstance(data.get("replace"), dict) else {}
                if old:
                    with contextlib.suppress(Exception):
                        pf_drop_draft(m, str(old.get("folder") or "")[:200], old.get("uid"))
                return self.send_json({"ok": True, "folder": drafts})
            if sub == "allread" and method == "POST":   # alle ungelesenen Mails des Ordners als gelesen markieren
                pf_select(m, str(self._pf_body.get("folder") or "INBOX")[:200], readonly=False)
                typ, res = m.uid("SEARCH", None, "UNSEEN")
                uids = (res[0] or b"").split() if typ == "OK" and res else []
                for i in range(0, len(uids), 500):   # in Blöcken, damit der Befehl nicht zu lang wird
                    m.uid("STORE", b",".join(uids[i:i + 500]).decode(), "+FLAGS", "(\\Seen)")
                return self.send_json({"ok": True, "count": len(uids)})
            if sub == "delete" and method == "POST":
                data = self._pf_body
                tuid, fold = str(data.get("uid") or ""), str(data.get("folder") or "INBOX")[:200]
                if not tuid.isdigit():
                    return self.send_json({"error": "Ungültige Mail."}, 400)
                msg, _ = pf_message(m, fold, tuid, mark_seen=False)
                trash = pf_role_folder(m, "trash")
                pf_select(m, fold, readonly=False)
                if trash and trash != fold:
                    typ, _ = m.uid("COPY", tuid, imap_quote(trash))
                    if typ != "OK":
                        return self.send_json({"error": "Verschieben in den Papierkorb fehlgeschlagen."}, 400)
                    action = "in den Papierkorb"
                else:
                    action = "endgültig gelöscht"
                m.uid("STORE", tuid, "+FLAGS", "(\\Deleted)")
                m.expunge()
                if not own_box:
                    pf_mark_handled(fold, int(tuid), user, "gelöscht")
                with db() as conn:
                    audit(conn, user, "Mail gelöscht", "postfach", None, pf_head(msg.get("Subject"))[:100], {"Von": pf_head(msg.get("From")), "Wohin": action})
                return self.send_json({"ok": True, "action": action})
            if sub == "send" and method == "POST":
                data = self._pf_body
                addr_re = r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+"
                def addrs(v):
                    from email.utils import getaddresses
                    out = [a for _, a in getaddresses([str(v or "")]) if a]
                    return out if all(re.fullmatch(addr_re, a) for a in out) else None
                to, cc = addrs(data.get("to")), addrs(data.get("cc"))
                subject = str(data.get("subject") or "").strip()[:250]
                body = str(data.get("body") or "")[:100000]
                q = data.get("quote") if isinstance(data.get("quote"), dict) else {}
                q_head, q_text, q_fwd = str(q.get("head") or "")[:2000], str(q.get("text") or "")[:200000], bool(q.get("forward"))
                with_sig = data.get("signature", True) is not False
                most = PF_BULK_MAX if data.get("separate") else 20
                if not to or cc is None or len(to) + len(cc) > most:
                    return self.send_json({"error": f"Bitte gültige Empfänger angeben (mehrere mit Komma, höchstens {most}{'' if data.get('separate') else ', einzeln senden bis ' + str(PF_BULK_MAX)})."}, 400)
                if not subject or not body.strip():
                    return self.send_json({"error": "Bitte Betreff und Text ausfüllen."}, 400)
                headers = {}
                reply = data.get("reply") if isinstance(data.get("reply"), dict) else None
                if reply and str(reply.get("uid") or "").isdigit():
                    orig, _ = pf_message(m, str(reply.get("folder") or "INBOX")[:200], str(reply["uid"]), mark_seen=False)
                    mid = (orig.get("Message-ID") or "").strip()
                    if mid:
                        headers = {"In-Reply-To": mid, "References": ((orig.get("References") or "") + " " + mid).strip()}
                out = {}
                with db() as conn:
                    senders, dflt, cfgs = pf_senders(conn, user, can("postfach", 2) or bool(task), bkey)
                    frm = str(data.get("from") or "")
                    if frm == "own":   # alter Schlüssel: erstes eigenes Mail-Konto
                        frm = next((x["key"] for x in senders if x["key"] != "info"), frm)
                    frm = frm if frm in [x["key"] for x in senders] else dflt
                    sender = cfgs[frm]
                    sig_mail = parseaddr(mail_sender(sender)[0])[1] or sender["smtp_user"]
                    sig_text, sig_html = signature_parts(conn, user["id"], sig_mail) if with_sig else ("", "")
                quoted = ("\n".join(q_text.split("\n")) if q_fwd else "\n".join("> " + l for l in q_text.split("\n"))) if q_text else ""
                text = body.rstrip() + (("\n\n" + sig_text) if sig_text else "") + (("\n\n\n" + q_head + "\n" + quoted) if (q_head or quoted) else "")
                para = lambda t: html_esc(t).replace("\n", "<br>\n")
                html = ('<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:20px;color:#1a1a1a;">' + para(body.rstrip()) + "</div><br>\n"
                        + sig_html
                        + ((f'<div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#555555;margin-top:20px;">{para(q_head)}</div>'
                            f'<blockquote style="margin:6px 0 0;padding-left:12px;border-left:3px solid #dddddd;color:#555555;font-family:Arial,Helvetica,sans-serif;font-size:13px;">{para(q_text)}</blockquote>')
                           if (q_head or q_text) else ""))
                separate = bool(data.get("separate")) and len(to) > 1   # an jeden einzeln: jede Mail nennt nur den eigenen Empfänger
                if separate and cc:
                    return self.send_json({"error": "Einzeln senden geht ohne Cc. Bitte alle Adressen unter „An“ eintragen."}, 400)
                if separate and len(to) > 5:   # größere Verteiler im Hintergrund, sonst läuft die Anfrage in die Zeitgrenze
                    dr = data.get("draft") if isinstance(data.get("draft"), dict) else None
                    if dr:
                        with contextlib.suppress(Exception):
                            pf_drop_draft(m, str(dr.get("folder") or "")[:200], dr.get("uid"))
                    threading.Thread(target=pf_send_bulk, args=(sender, list(to), subject, text, html, headers, dict(user)), daemon=True).start()
                    return self.send_json({"ok": True, "background": True,
                                           "note": f"{len(to)} Mails werden jetzt einzeln verschickt (etwa {max(1, len(to) // 30)} Minute{'n' if len(to) >= 60 else ''}). Du bekommst eine Nachricht, wenn alle raus sind."})
                outs, errs = [], []
                for rcpt in ([[a] for a in to] if separate else [to]):
                    o = {}
                    e_ = send_mail(sender, ", ".join(rcpt), subject, text, footer=False, headers=headers, cc=[] if separate else cc, out=o, html=html)
                    if e_:
                        errs.append(f"{', '.join(rcpt)}: {e_}")
                    else:
                        outs.append(o)
                if not outs:
                    return self.send_json({"error": f"Versand fehlgeschlagen: {errs[0] if errs else 'unbekannt'}"}, 400)
                note = ("Nicht verschickt an " + "; ".join(errs)) if errs else ""
                try:
                    if reply and str(reply.get("uid") or "").isdigit():
                        pf_select(m, str(reply.get("folder") or "INBOX")[:200], readonly=False)
                        m.uid("STORE", str(reply["uid"]), "+FLAGS", "(\\Answered)")
                    if any(o.get("raw") for o in outs):
                        import imaplib
                        box = m if frm == bkey else postfach_open(sender)[0]   # Kopie in „Gesendet“ des Postfachs, über das verschickt wurde
                        try:
                            sent = pf_role_folder(box, "sent")
                            for o in outs if sent else []:
                                if o.get("raw"):
                                    box.append(imap_quote(sent), "(\\Seen)", imaplib.Time2Internaldate(time.time()), o["raw"])
                        finally:
                            if box is not m:
                                with contextlib.suppress(Exception):
                                    box.logout()
                except Exception as e:  # noqa
                    note = (note + " " if note else "") + f"Verschickt, aber nicht unter „Gesendet“ abgelegt ({type(e).__name__})."
                dr = data.get("draft") if isinstance(data.get("draft"), dict) else None   # aus einem Entwurf gesendet: Entwurf entfernen
                if dr:
                    with contextlib.suppress(Exception):
                        pf_drop_draft(m, str(dr.get("folder") or "")[:200], dr.get("uid"))
                src = data.get("source") if isinstance(data.get("source"), dict) else None   # Weiterleitung: Ursprungsmail
                if own_box:
                    pass
                elif reply and str(reply.get("uid") or "").isdigit():
                    pf_mark_handled(str(reply.get("folder") or "INBOX")[:200], int(reply["uid"]), user, "beantwortet")
                elif src and str(src.get("uid") or "").isdigit():
                    pf_mark_handled(str(src.get("folder") or "INBOX")[:200], int(src["uid"]), user, "weitergeleitet")
                done = 0
                with db() as conn:
                    audit(conn, user, "Mail gesendet", "postfach", None, subject[:100], {"An": ", ".join(to + cc) + (" (einzeln)" if separate else "")})
                    if reply and str(reply.get("uid") or "").isdigit() and not own_box:
                        done = conn.execute("UPDATE mail_tasks SET status='erledigt', done_at=? WHERE user_id=? AND folder=? AND uid=? AND status='offen'",
                                            (datetime.now().isoformat(timespec="seconds"), user["id"], str(reply.get("folder") or "INBOX")[:200], int(reply["uid"]))).rowcount
                return self.send_json({"ok": True, "note": note, "task_done": bool(done), "from": sender.get("smtp_user", "")})
            if sub == "assign" and method == "POST":
                data = self._pf_body
                tuid, fold = str(data.get("uid") or ""), str(data.get("folder") or "INBOX")[:200]
                target = int(data["user_id"]) if str(data.get("user_id") or "").isdigit() else 0
                if not tuid.isdigit() or not target:
                    return self.send_json({"error": "Bitte eine Person auswählen."}, 400)
                msg, _ = pf_message(m, fold, tuid, mark_seen=False)
                now = datetime.now().isoformat(timespec="seconds")
                note = str(data.get("note") or "").strip()[:1000]
                subj, sender = pf_head(msg.get("Subject"))[:250] or "(ohne Betreff)", pf_head(msg.get("From"))[:250]
                with db() as conn:
                    tu = conn.execute("SELECT id, display_name, username, email, member_id, is_admin, active FROM users WHERE id=?", (target,)).fetchone()
                    if not tu or not tu["active"]:
                        return self.send_json({"error": "Konto nicht gefunden."}, 404)
                    tid = conn.execute("INSERT INTO mail_tasks (folder, uid, message_id, subject, sender, user_id, assigned_by, note, status, created, banner_seen) "
                                       "VALUES (?,?,?,?,?,?,?,?, 'offen', ?, 0)", (fold, int(tuid), (msg.get("Message-ID") or "")[:300], subj, sender, target, user["id"], note, now)).lastrowid
                    audit(conn, user, "Mail zugewiesen", "postfach", tid, subj[:100], {"An": tu["display_name"] or tu["username"]})
                    email = account_email(conn, tu)
                    no_access = effective_perms(conn, {"id": target, "is_admin": tu["is_admin"]}).get("postfach", 0) < 1
                    fwd_to = own_mail_address(conn, target) or email   # die Mail landet immer im Postfach der Person (eigenes Hub-Postfach, sonst Konto-Adresse)
                if no_access and not fwd_to:
                    with db() as conn:
                        conn.execute("DELETE FROM mail_tasks WHERE id=?", (tid,))
                    return self.send_json({"error": "Diese Person hat keinen Zugriff auf das Vereinspostfach und keine E-Mail-Adresse im Konto. "
                                                    "Bitte unter Konten eine Adresse oder ein eigenes Postfach hinterlegen."}, 400)
                if fwd_to:   # die Mail selbst (mit Anhängen) an die Person weiterleiten, Antworten gehen an den Absender
                    err = pf_forward_to_person(cfg, msg, fwd_to, tu["display_name"] or tu["username"], user, note)
                    if err:
                        with db() as conn:
                            conn.execute("DELETE FROM mail_tasks WHERE id=?", (tid,))
                        return self.send_json({"error": f"Weiterleiten an {fwd_to} fehlgeschlagen: {err}"}, 400)
                    with db() as conn:
                        audit(conn, user, "Mail weitergeleitet", "postfach", tid, subj[:100], {"An": fwd_to})
                pf_mark_handled(fold, int(tuid), user, f"an {tu['display_name'] or tu['username']} {'weitergeleitet' if fwd_to else 'zugewiesen'}")
                name = tu["display_name"] or tu["username"]
                link = f"/hub#/mailaufgabe/{tid}"
                send_push_async([target], "Neue Mail-Aufgabe", f"{subj} (von {pf_name(sender)})", link, f"task-{tid}")
                if email and target != user["id"] and not fwd_to:
                    cfg2 = smtp_config()
                    if cfg2["smtp_host"]:
                        text = (f"Hallo {name},\n\n{user['display_name']} hat dir im Wolthusen Hub eine Mail aus dem Vereinspostfach zum Bearbeiten zugewiesen.\n\n"
                                f"Von: {sender}\nBetreff: {subj}\n" + (f"Hinweis: {note}\n" if note else "") +
                                (f"\nÖffnen: {cfg2['hub_url']}{link}\n" if cfg2["hub_url"] else "\nDu findest sie im Hub auf der Startseite.\n"))
                        threading.Thread(target=lambda: send_mail(cfg2, email, subj if re.match(r"(re|aw)\s*:", subj, re.I) else f"Re: {subj}", text, footer=False), daemon=True).start()
                return self.send_json({"ok": True, "id": tid, "forwarded": fwd_to})
            if sub == "people" and method == "GET":
                if not can("postfach", 2):
                    return self.deny()
                with db() as conn:
                    rows = conn.execute("SELECT id, display_name, username, mail_role, email, member_id, is_admin FROM users WHERE active=1 AND pw_hash != '' "
                                        "ORDER BY COALESCE(display_name, username) COLLATE NOCASE").fetchall()
                    out = []
                    for r in rows:
                        no_access = effective_perms(conn, {"id": r["id"], "is_admin": r["is_admin"]}).get("postfach", 0) < 1
                        out.append({"id": r["id"], "name": r["display_name"] or r["username"], "role": r["mail_role"] or "",
                                    "forward": (own_mail_address(conn, r["id"]) or account_email(conn, r)) or ("-" if no_access else "")})
                return self.send_json(out)
            return self.send_json({"error": "Unbekannter Pfad"}, 404)
        except PostfachError as e:
            return self.send_json({"error": str(e)}, 400)
        except Exception as e:  # noqa
            return self.send_json({"error": f"Fehler beim Postfach: {type(e).__name__}: {e}"}, 502)
        finally:
            if m is not None:
                with contextlib.suppress(Exception):
                    m.logout()

    # -- Mail-Aufgaben (/api/mailtasks): eigene Aufgaben für alle, alle offenen für Postfach-Leser --
    def api_mailtasks(self, method, p, user, can):
        tid = int(p[0]) if p and p[0].isdigit() else None
        action = p[1] if len(p) > 1 else ""
        now = datetime.now().isoformat(timespec="seconds")
        with db() as conn:
            if method == "GET" and tid is None:
                mine = [mail_task_row(conn, t) for t in conn.execute(
                    "SELECT * FROM mail_tasks WHERE user_id=? AND (status='offen' OR done_at >= ?) ORDER BY status='erledigt', id DESC LIMIT 50",
                    (user["id"], (datetime.now() - timedelta(days=14)).isoformat()))]
                others = [mail_task_row(conn, t) for t in conn.execute("SELECT * FROM mail_tasks WHERE status='offen' AND user_id != ? ORDER BY id DESC LIMIT 100", (user["id"],))] \
                    if can("postfach", 1) else []
                inbox = [dict(r) for r in conn.execute("SELECT * FROM pf_inbox WHERE status='neu' ORDER BY id DESC LIMIT 50")] \
                    if (can("postfach", 1) and user["id"] in pf_recipients(conn)) or can("postfach", 2) else []
                return self.send_json({"mine": mine, "others": others, "inbox": inbox, "badge": badge_for(conn, user["id"])})
            t = conn.execute("SELECT * FROM mail_tasks WHERE id=?", (tid,)).fetchone() if tid else None
            if not t:
                return self.send_json({"error": "Aufgabe nicht gefunden."}, 404)
            own = t["user_id"] == user["id"]
            if method == "GET":
                if not (own or can("postfach", 1)):
                    return self.deny()
                return self.send_json(mail_task_row(conn, t))
            if method == "POST" and action == "seen" and own:
                conn.execute("UPDATE mail_tasks SET banner_seen=1 WHERE id=?", (tid,))
                return self.send_json({"ok": True})
            if method == "POST" and action in ("done", "reopen") and (own or can("postfach", 2)):
                conn.execute("UPDATE mail_tasks SET status=?, done_at=?, banner_seen=1 WHERE id=?",
                             ("erledigt" if action == "done" else "offen", now if action == "done" else None, tid))
                audit(conn, user, "Mail-Aufgabe erledigt" if action == "done" else "Mail-Aufgabe wieder offen", "postfach", tid, t["subject"][:100])
                conn.commit()
                if action == "done":
                    pf_mark_handled(t["folder"], t["uid"], user, "erledigt")
                    try:
                        pf_move_to_done(t["folder"], t["uid"])
                    except Exception as e:  # noqa
                        return self.send_json({"ok": True, "note": f"Erledigt, aber nicht verschoben: {e}"})
                return self.send_json({"ok": True})
            if method == "DELETE" and can("postfach", 2):
                conn.execute("DELETE FROM mail_tasks WHERE id=?", (tid,))
                audit(conn, user, "Mail-Zuweisung entfernt", "postfach", tid, t["subject"][:100])
                return self.send_json({"ok": True})
        return self.deny()

    # -- Push-Benachrichtigungen (/api/push): Schlüssel, Abo je Gerät, Test --
    def api_push(self, method, p, user):
        sub = p[0] if p else ""
        with db() as conn:
            if method == "GET" and sub == "key":
                _, pub = vapid_keys(conn)
                n = conn.execute("SELECT COUNT(*) FROM push_subs WHERE user_id=?", (user["id"],)).fetchone()[0]
                return self.send_json({"key": b64u(pub), "devices": n})
            if method == "POST" and sub == "subscribe":
                data = self.read_json()
                ep, keys = str(data.get("endpoint") or ""), data.get("keys") or {}
                if not push_endpoint_ok(ep):
                    return self.send_json({"error": "Dieser Push-Dienst wird nicht unterstützt."}, 400)
                try:
                    ec_pub_point(b64u_dec(keys.get("p256dh")))
                    if len(b64u_dec(keys.get("auth"))) != 16:
                        raise ValueError
                except (ValueError, TypeError):
                    return self.send_json({"error": "Ungültiges Push-Abo."}, 400)
                conn.execute("DELETE FROM push_subs WHERE endpoint=?", (ep,))
                conn.execute("INSERT INTO push_subs (user_id, endpoint, p256dh, auth, ua, created) VALUES (?,?,?,?,?,?)",
                             (user["id"], ep, keys["p256dh"], keys["auth"], (self.headers.get("User-Agent") or "")[:200], datetime.now().isoformat(timespec="seconds")))
                return self.send_json({"ok": True})
            if method == "POST" and sub == "unsubscribe":
                ep = str(self.read_json().get("endpoint") or "")
                conn.execute("DELETE FROM push_subs WHERE endpoint=? AND user_id=?", (ep, user["id"]))
                return self.send_json({"ok": True})
        if method == "POST" and sub == "test":
            n = send_push([user["id"]], "Wolthusen Hub", "Push-Benachrichtigungen funktionieren.", "/hub#/profile", "test")
            return self.send_json({"ok": n > 0, "delivered": n})
        return self.send_json({"error": "Unbekannter Pfad"}, 404)

    def api_profile(self, method, user):
        with db() as conn:
            if method == "PUT":
                data = self.read_json()
                if "display_name" in data:
                    conn.execute("UPDATE users SET display_name=? WHERE id=?", ((data["display_name"] or "").strip()[:80] or user["username"], user["id"]))
                if "account_email" in data or "notify_email" in data:
                    # E-Mail des Kontos: für Benachrichtigungen und „Passwort vergessen“
                    email = (data.get("account_email", data.get("notify_email")) or "").strip()
                    if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                        return self.send_json({"error": "Bitte eine gültige E-Mail-Adresse angeben."}, 400)
                    conn.execute("UPDATE users SET email=? WHERE id=?", (email, user["id"]))
                if "sig_phone" in data:   # Telefon in der eigenen Mail-Signatur: nur Ziffern, Leerzeichen, + / ( ) -
                    ph = re.sub(r"\s+", " ", str(data["sig_phone"] or "")).strip()[:40]
                    if ph and not re.fullmatch(r"\+?[\d ()/-]{5,40}", ph):
                        return self.send_json({"error": "Bitte nur eine Telefonnummer eintragen (Ziffern, Leerzeichen, +, /)."}, 400)
                    conn.execute("UPDATE users SET sig_phone=? WHERE id=?", (ph, user["id"]))
                if "notify" in data:
                    kinds = [k for k in (data["notify"] or []) if k in NOTIFY_KINDS and notify_allowed(user["perms"], k)]
                    conn.execute("UPDATE users SET notify=? WHERE id=?", (json.dumps(kinds), user["id"]))
                if user["member_id"]:
                    vals = clean_values("members", {k: v for k, v in data.items() if k in self.PROFILE_FIELDS})
                    if vals:
                        vals["updated_at"] = datetime.now().isoformat(timespec="seconds")
                        conn.execute(f"UPDATE members SET {', '.join(f'{k}=?' for k in vals)} WHERE id=?", [*vals.values(), user["member_id"]])
            u = row_dict(conn.execute("SELECT username, display_name, email, notify, sig_phone FROM users WHERE id=?", (user["id"],)).fetchone())
            if u["notify"] is None:   # nie gespeichert: Standard anzeigen (gilt auch beim Versand)
                u["notify"] = json.dumps([k for k in NOTIFY_DEFAULT if notify_allowed(user["perms"], k)])
            m = conn.execute("SELECT * FROM members WHERE id=?", (user["member_id"],)).fetchone() if user["member_id"] else None
            pl = None
            if m and m["player_id"]:
                pl = conn.execute("SELECT number, position, unit, role, kind FROM players WHERE id=?", (m["player_id"],)).fetchone()
            kinds = [{"key": k, "label": v[0]} for k, v in NOTIFY_KINDS.items() if notify_allowed(user["perms"], k)]
            mail_ready = bool(secret_get(conn, "smtp_host"))
            return self.send_json({"account": u, "member": row_dict(m) if m else None, "player": row_dict(pl) if pl else None,
                                   "notify_kinds": kinds, "mail_ready": mail_ready})

    # -- Konten, Gruppen, Rechte ------------------------------------------
    def user_payload(self, conn, uid):
        u = conn.execute("SELECT id, username, display_name, email, is_admin, active, member_id, created_at, last_login, "
                         "invite_expires, pw_hash != '' AS has_pw, locked_until, player_id, phone, invite_profile, mail_role FROM users WHERE id=?", (uid,)).fetchone()
        d = row_dict(u)
        d["is_admin"] = bool(d["is_admin"])
        d["locked"] = (d.pop("locked_until") or 0) > time.time()
        d["twofa"] = twofa_enabled(conn, uid)
        d["groups"] = [r["group_id"] for r in conn.execute("SELECT group_id FROM user_groups WHERE user_id=?", (uid,))]
        d["overrides"] = {r["area"]: r["level"] for r in conn.execute("SELECT area, level FROM user_perms WHERE user_id=?", (uid,))}
        d["effective"] = effective_perms(conn, {"id": uid, "is_admin": d["is_admin"]})
        d["twofa_required"] = twofa_required(conn, {"id": uid, "is_admin": d["is_admin"]}, d["effective"])
        d["invite_open"] = bool(d.pop("invite_expires") or 0) and not d["has_pw"]
        prof = invite_profile(u)
        d.pop("invite_profile", None)
        d["invite_kader"] = (prof.get("kind") or "") if d["invite_open"] else ""
        d["own_mail"] = ", ".join((a["address"] or a["username"]) for a in conn.execute(
            "SELECT m.address, m.username FROM mail_accounts m JOIN mail_links a ON a.account_id=m.id WHERE a.user_id=? ORDER BY lower(m.address)", (uid,)))
        return d

    def send_invite_mail(self, data, link):
        """Einladungslink per Mail schicken. Liefert None oder eine Fehlermeldung."""
        to = (data.get("email") or "").strip()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to):
            return "Keine gültige E-Mail-Adresse angegeben, bitte den Link selbst weitergeben."
        cfg = smtp_config()
        if not (cfg["smtp_host"] and cfg["smtp_user"]):
            return "Der E-Mail-Versand ist nicht eingerichtet, bitte den Link selbst weitergeben."
        name = (data.get("display_name") or "").strip()
        name = "" if name in ("Einladung offen",) else name
        try:
            return send_mail(cfg, to, "Einladung zum Wolthusen Hub", invite_mail_text(name, link, INVITE_DAYS), footer=False)
        except Exception as e:  # noqa
            return f"Versand fehlgeschlagen: {e}"

    def save_user_links(self, conn, uid, data):
        if "player_id" in data:   # Person in Kader & Staff (Name, Mannschaft und Gruppe im Reiter Spieler)
            pid = int(data["player_id"]) if str(data["player_id"] or "").isdigit() else None
            if pid and not conn.execute("SELECT 1 FROM players WHERE id=?", (pid,)).fetchone():
                pid = None
            conn.execute("UPDATE users SET player_id=? WHERE id=?", (pid, uid))
        if "mail_role" in data:
            conn.execute("UPDATE users SET mail_role=? WHERE id=?", (str(data["mail_role"] or "").strip()[:80], uid))
        if "groups" in data:
            conn.execute("DELETE FROM user_groups WHERE user_id=?", (uid,))
            for gid in data["groups"] or []:
                conn.execute("INSERT OR IGNORE INTO user_groups (user_id, group_id) VALUES (?, ?)", (uid, int(gid)))
        if "overrides" in data:
            conn.execute("DELETE FROM user_perms WHERE user_id=?", (uid,))
            for area, lvl in (data["overrides"] or {}).items():
                if area in AREAS and lvl not in (None, "") and int(lvl) in (0, 1, 2):
                    conn.execute("INSERT INTO user_perms (user_id, area, level) VALUES (?, ?, ?)", (uid, area, int(lvl)))
        if "member_id" in data:
            mid = data["member_id"] or None
            conn.execute("UPDATE members SET user_id=NULL WHERE user_id=?", (uid,))
            conn.execute("UPDATE users SET member_id=? WHERE id=?", (mid, uid))
            if mid:
                conn.execute("UPDATE users SET member_id=NULL WHERE member_id=? AND id != ?", (mid, uid))
                conn.execute("UPDATE members SET user_id=? WHERE id=?", (uid, mid))

    def api_mail_accounts(self, method, rid, sub, me):
        with db() as conn:
            r = conn.execute("SELECT * FROM mail_accounts WHERE id=?", (rid,)).fetchone() if rid else None
            if rid and not r:
                return self.send_json({"error": "Mail-Konto nicht gefunden"}, 404)
            if method == "GET" and not rid:
                out = []
                for a in conn.execute("SELECT * FROM mail_accounts ORDER BY lower(address)"):
                    d = {k: a[k] or "" for k in ("address", "smtp_host", "smtp_port", "smtp_security", "imap_host", "username", "updated")}
                    d.update(id=a["id"], password_set=bool(a["password"]), users=[
                        {"id": u["id"], "name": u["display_name"] or u["username"], "no_shared": u["level"] == 0}
                        for u in conn.execute("SELECT u.id, u.display_name, u.username, p.level FROM mail_links x JOIN users u ON u.id=x.user_id "
                                              "LEFT JOIN user_perms p ON p.user_id=u.id AND p.area='postfach' WHERE x.account_id=? "
                                              "ORDER BY lower(coalesce(u.display_name, u.username))", (a["id"],))])
                    out.append(d)
                users = [{"id": u["id"], "name": u["display_name"] or u["username"]}
                         for u in conn.execute("SELECT id, display_name, username FROM users ORDER BY lower(coalesce(display_name, username))")]
                return self.send_json({"accounts": out, "users": users})
            if method == "DELETE" and rid and not sub:
                conn.execute("DELETE FROM mail_links WHERE account_id=?", (rid,))
                conn.execute("DELETE FROM mail_accounts WHERE id=?", (rid,))
                audit(conn, me, "Mail-Konto gelöscht", "mail_accounts", rid, r["address"] or r["username"])
                return self.send_json({"ok": True})
            if method == "POST" and rid and sub == "check":   # Anmeldung an SMTP und IMAP prüfen, es wird keine Mail verschickt
                cfg = user_mail_cfg(conn, None, row=r)
                if not cfg:
                    return self.send_json({"error": "Mailserver, Benutzername und Passwort fehlen noch."}, 400)
            elif not sub and ((method == "POST" and not rid) or (method == "PUT" and rid)):
                data = self.read_json()
                if rid and data and set(data) <= {"add_user", "remove_user", "user_id", "no_shared"}:   # Personen zuweisen/lösen, Schalter je Person
                    uid = data.get("add_user") or data.get("remove_user") or data.get("user_id")
                    uid = int(uid) if str(uid or "").isdigit() else None
                    if not uid or not conn.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
                        return self.send_json({"error": "Konto nicht gefunden"}, 404)
                    linked = conn.execute("SELECT 1 FROM mail_links WHERE account_id=? AND user_id=?", (rid, uid)).fetchone()
                    if "add_user" in data:
                        conn.execute("INSERT OR IGNORE INTO mail_links (account_id, user_id) VALUES (?, ?)", (rid, uid))
                        audit(conn, me, "Mail-Konto zugewiesen", "mail_accounts", rid, f"{r['address']} -> {uid}")
                    elif "remove_user" in data:
                        conn.execute("DELETE FROM mail_links WHERE account_id=? AND user_id=?", (rid, uid))
                        audit(conn, me, "Mail-Konto Zuweisung gelöst", "mail_accounts", rid, f"{r['address']} -> {uid}")
                    elif "no_shared" in data:
                        if not linked:
                            return self.send_json({"error": "Die Person ist diesem Mail-Konto nicht zugewiesen."}, 400)
                        if data["no_shared"]:
                            conn.execute("INSERT OR REPLACE INTO user_perms (user_id, area, level) VALUES (?, 'postfach', 0)", (uid,))
                        else:
                            conn.execute("DELETE FROM user_perms WHERE user_id=? AND area='postfach' AND level=0", (uid,))
                        audit(conn, me, "Zugriff Vereinspostfach " + ("gesperrt" if data["no_shared"] else "freigegeben"), "users", uid, "")
                    return self.send_json({"ok": True})
                vals = {k: str(data.get(k) or "").strip()[:200] for k in ("address", "smtp_host", "smtp_port", "smtp_security", "imap_host", "username")}
                if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", vals["address"]):
                    return self.send_json({"error": "Bitte eine gültige Adresse angeben."}, 400)
                vals["username"] = vals["username"] or vals["address"]
                if not re.fullmatch(r"[A-Za-z0-9.-]{3,200}", vals["smtp_host"]):
                    return self.send_json({"error": "Bitte den Mailserver (SMTP) angeben."}, 400)
                if vals["imap_host"] and not re.fullmatch(r"[A-Za-z0-9.-]{3,200}", vals["imap_host"]):
                    return self.send_json({"error": "Der IMAP-Server sieht nicht gültig aus."}, 400)
                if vals["smtp_port"] and not vals["smtp_port"].isdigit():
                    return self.send_json({"error": "Der Port muss eine Zahl sein."}, 400)
                if vals["smtp_security"] not in ("starttls", "ssl", "none"):
                    vals["smtp_security"] = "starttls"
                pw = str(data.get("password") or "")
                if not pw and not (r and r["password"]):
                    return self.send_json({"error": "Bitte das Passwort des Postfachs eintragen."}, 400)
                vals["password"] = pw or r["password"]
                vals["updated"] = datetime.now().isoformat(timespec="seconds")
                if rid:
                    conn.execute(f"UPDATE mail_accounts SET {', '.join(k + '=?' for k in vals)} WHERE id=?", [*vals.values(), rid])
                else:
                    rid = conn.execute(f"INSERT INTO mail_accounts ({', '.join(vals)}) VALUES ({', '.join('?' for _ in vals)})", list(vals.values())).lastrowid
                audit(conn, me, "Mail-Konto gespeichert", "mail_accounts", rid, vals["address"])
                return self.send_json({"ok": True, "id": rid})
            else:
                return self.send_json({"error": "Methode nicht erlaubt"}, 405)
        return self.send_json(mail_account_check(cfg))

    def api_admin(self, method, p, me):
        what = p[0] if p else ""
        rid = int(p[1]) if len(p) > 1 and p[1].isdigit() else None
        sub = p[2] if len(p) > 2 else ""

        if what == "info" and method == "GET":   # Seite „Admin“
            fresh = (parse_qs(urlparse(self.path).query).get("neu") or [""])[0] == "1"
            return self.send_json(admin_info(fresh))
        if what == "updates":   # Admin > Updates: Status lesen, feste Aktionen beim Helfer anstoßen
            if method == "GET":
                return self.send_json(updater_state())
            if method != "POST":
                return self.send_json({"error": "Nicht erlaubt"}, 405)
            data = self.read_json()
            action = str(data.get("action") or "")
            if action not in UPD_ACTIONS:
                return self.send_json({"error": "Unbekannte Aktion."}, 400)
            with db() as conn:
                if not twofa_enabled(conn, me["id"]):
                    return self.send_json({"error": "Updates nur mit eingeschalteter Zwei-Faktor-Anmeldung (Mein Profil)."}, 403)
                if action != "check":
                    row = conn.execute("SELECT pw_hash FROM users WHERE id=?", (me["id"],)).fetchone()
                    if not row or not check_pw(str(data.get("password") or ""), row["pw_hash"]):
                        return self.send_json({"error": "Das Passwort stimmt nicht."}, 403)
                if not UPD_DIR.is_dir():
                    return self.send_json({"error": "Der Update-Helfer ist auf dem Server noch nicht eingerichtet (Anleitung auf dieser Seite)."}, 400)
                st = updater_state()
                if st["pending"] or st["running"]:
                    return self.send_json({"error": "Es läuft schon eine Aktion. Bitte warten, bis sie fertig ist."}, 409)
                tmp = UPD_DIR / f".request-{uuid.uuid4().hex}"
                tmp.write_text(action + "\n", encoding="ascii")
                os.replace(tmp, UPD_DIR / "request")
                audit(conn, me, "Update angestoßen", "admin", None, UPD_ACTIONS[action], {})
            return self.send_json(updater_state())
        if what == "log" and method == "GET":
            q = parse_qs(urlparse(self.path).query)
            limit = min(1000, max(50, int((q.get("limit") or ["300"])[0] or 300)))
            with db() as conn:
                rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return self.send_json([row_dict(r) for r in rows])
        if what == "2fa-policy":   # Pflicht zur Zwei-Faktor-Anmeldung
            with db() as conn:
                if method == "PUT":
                    data = self.read_json()
                    new = {k: "1" if data.get(k) else "" for k in TWOFA_POLICY_KEYS if k in data}
                    if "1" in new.values() and not twofa_enabled(conn, me["id"]):   # Admins haben auch Finanz-Schreibrecht
                        return self.send_json({"error": "Richte zuerst für dein eigenes Konto die Zwei-Faktor-Anmeldung ein (Mein Profil)."}, 400)
                    old = {k: get_setting(conn, k) or "" for k in new}
                    for k, v in new.items():
                        set_setting(conn, k, v)
                    changes = {k: [old[k], v] for k, v in new.items() if old[k] != v}
                    if changes:
                        audit(conn, me, "geändert", "settings", None, "Pflicht Zwei-Faktor-Anmeldung", changes)
                elif method != "GET":
                    return self.send_json({"error": "Unbekannter Pfad"}, 404)
                return self.send_json({k: get_setting(conn, k) == "1" for k in TWOFA_POLICY_KEYS})
        if what == "mail":   # Admin > E-Mails: alle Mail-Konten, Zuweisung an Personen (Passwort nur schreiben)
            return self.api_mail_accounts(method, rid, sub, me)
        if what == "users" and rid and sub in ("2fa-reset", "unlock") and method == "POST":
            with db() as conn:
                u = conn.execute("SELECT * FROM users WHERE id=?", (rid,)).fetchone()
                if not u:
                    return self.send_json({"error": "Konto nicht gefunden"}, 404)
                label = u["display_name"] or u["username"]
                if sub == "unlock":
                    account_ok(conn, rid)
                    audit(conn, me, "Anmeldesperre aufgehoben", "users", rid, label)
                    return self.send_json(self.user_payload(conn, rid))
                if not twofa_row(conn, rid):
                    return self.send_json({"error": "Für dieses Konto ist keine Zwei-Faktor-Anmeldung eingerichtet."}, 400)
                conn.execute("DELETE FROM user_2fa WHERE user_id=?", (rid,))
                audit(conn, me, "Zwei-Faktor-Anmeldung zurückgesetzt", "users", rid, label)
                email = account_email(conn, u)
                payload = self.user_payload(conn, rid)
            cfg = smtp_config()
            if email and cfg["smtp_host"] and rid != me["id"]:
                body = (f"Hallo {label},\n\nein Admin ({me['display_name']}) hat die Zwei-Faktor-Anmeldung deines Kontos im Wolthusen Hub "
                        f"(Benutzername: {u['username']}) zurückgesetzt ({datetime.now():%d.%m.%Y %H:%M}). Du meldest dich jetzt nur mit dem Passwort an "
                        "und kannst sie unter „Mein Profil“ neu einrichten.\n\nWusstest du nichts davon? Dann melde dich bitte beim Vorstand bzw. Admin.")
                threading.Thread(target=lambda: send_mail(cfg, email, "Wolthusen Hub: Zwei-Faktor-Anmeldung zurückgesetzt", body, footer=False), daemon=True).start()
            return self.send_json(payload)
        if method != "GET" and what in ("users", "groups"):
            name = None
            with db() as conn:
                if rid and what == "users":
                    u = conn.execute("SELECT username, display_name FROM users WHERE id=?", (rid,)).fetchone()
                    name = u and (u["display_name"] or u["username"])
                elif rid:
                    g = conn.execute("SELECT name FROM groups WHERE id=?", (rid,)).fetchone()
                    name = g and g["name"]
                act = {"POST": "neu", "PUT": "geändert", "DELETE": "gelöscht"}.get(method, method)
                audit(conn, me, f"{act}{' (' + sub + ')' if sub else ''}", what, rid, name or "")

        if what == "users":
            if method == "GET":
                with db() as conn:
                    ids = [r["id"] for r in conn.execute("SELECT id FROM users ORDER BY COALESCE(display_name, username) COLLATE NOCASE")]
                    return self.send_json([self.user_payload(conn, i) for i in ids])
            if method == "POST" and rid is None:
                data = self.read_json()
                kader = data.get("kader") if isinstance(data.get("kader"), dict) else {}
                kind = kader.get("kind") if kader.get("kind") in PLAYER_FORM_KINDS else ""
                team = kader.get("team") if kader.get("team") in TEAMS else MAIN_TEAM
                if kind == "Spieler" and team in YOUTH_TEAMS:
                    return self.send_json({"error": "Jugendspieler (Minderjährige) bitte nicht per Einladung in den Kader aufnehmen."}, 400)
                pick = not (data.get("username") or "").strip()   # ohne Namen wählt die Person ihn selbst
                username = data.get("username") or f"einladung-{secrets.token_hex(3)}"
                try:
                    uid, tok = create_user(username, None, bool(data.get("is_admin")), data.get("display_name") or "",
                                           data.get("email") or "", data.get("member_id") or None)
                except ValueError as e:
                    return self.send_json({"error": str(e)}, 400)
                link = f"{self.base_url()}/invite/{tok}"
                with db() as conn:
                    self.save_user_links(conn, uid, {k: v for k, v in data.items() if k in ("groups", "overrides", "player_id", "mail_role")})
                    if pick or kind:
                        conn.execute("UPDATE users SET invite_profile=? WHERE id=?", (json.dumps({"kind": kind, "team": team, "pick_name": pick}), uid))
                    if pick and not (data.get("display_name") or "").strip():
                        conn.execute("UPDATE users SET display_name='Einladung offen' WHERE id=?", (uid,))
                    payload = self.user_payload(conn, uid)
                mail_error = self.send_invite_mail(data, link) if data.get("send_mail") else None
                return self.send_json({"user": payload, "invite": link, "days": INVITE_DAYS, "mailed": bool(data.get("send_mail")) and not mail_error,
                                       "mail_error": mail_error}, 201)
            if method == "POST" and rid and sub == "invite":
                data = self.read_json() if int(self.headers.get("Content-Length") or 0) else {}
                with db() as conn:
                    u = conn.execute("SELECT display_name, email FROM users WHERE id=?", (rid,)).fetchone()
                    if not u:
                        return self.send_json({"error": "Konto nicht gefunden"}, 404)
                    tok = new_invite(conn, rid)
                link = f"{self.base_url()}/invite/{tok}"
                mail_error = self.send_invite_mail({"email": u["email"], "display_name": u["display_name"]}, link) if data.get("send_mail") else None
                return self.send_json({"invite": link, "days": INVITE_DAYS, "mailed": bool(data.get("send_mail")) and not mail_error, "mail_error": mail_error})
            if method == "PUT" and rid:
                data = self.read_json()
                with db() as conn:
                    u = conn.execute("SELECT * FROM users WHERE id=?", (rid,)).fetchone()
                    if not u:
                        return self.send_json({"error": "Konto nicht gefunden"}, 404)
                    is_admin = bool(data.get("is_admin", u["is_admin"]))
                    active = bool(data.get("active", u["active"]))
                    if rid == me["id"] and (not is_admin or not active):
                        return self.send_json({"error": "Du kannst dir die Admin-Rechte nicht selbst entziehen oder dich deaktivieren."}, 400)
                    if "username" in data and data["username"] != u["username"]:
                        try:
                            name = check_username(data["username"])
                        except ValueError as e:
                            return self.send_json({"error": str(e)}, 400)
                        if conn.execute("SELECT 1 FROM users WHERE username=? AND id != ?", (name, rid)).fetchone():
                            return self.send_json({"error": "Diesen Benutzernamen gibt es schon."}, 400)
                        conn.execute("UPDATE users SET username=? WHERE id=?", (name, rid))
                    conn.execute("UPDATE users SET display_name=?, email=?, is_admin=?, active=? WHERE id=?",
                                 ((data.get("display_name") or u["display_name"] or u["username"]).strip()[:80],
                                  (data.get("email") if "email" in data else u["email"]) or "", 1 if is_admin else 0, 1 if active else 0, rid))
                    if not active:
                        conn.execute("DELETE FROM sessions WHERE user_id=?", (rid,))
                    self.save_user_links(conn, rid, data)
                    return self.send_json(self.user_payload(conn, rid))
            if method == "DELETE" and rid:
                if rid == me["id"]:
                    return self.send_json({"error": "Du kannst dich nicht selbst löschen."}, 400)
                with db() as conn:
                    for t in ("sessions", "user_groups", "user_perms", "user_2fa", "push_subs", "user_mail"):
                        conn.execute(f"DELETE FROM {t} WHERE user_id=?", (rid,))
                    conn.execute("DELETE FROM mail_links WHERE user_id=?", (rid,))   # Mail-Konten bleiben, nur ohne diese Person
                    conn.execute("UPDATE members SET user_id=NULL WHERE user_id=?", (rid,))
                    conn.execute("DELETE FROM users WHERE id=?", (rid,))
                return self.send_json({"ok": True})

        if what == "groups":
            with db() as conn:
                if method == "GET":
                    out = []
                    for g in conn.execute("SELECT * FROM groups ORDER BY sort, name"):
                        d = row_dict(g)
                        d["perms"] = {a: 0 for a in AREAS}
                        for r in conn.execute("SELECT area, level FROM group_perms WHERE group_id=?", (g["id"],)):
                            d["perms"][r["area"]] = r["level"]
                        d["members"] = conn.execute("SELECT COUNT(*) FROM user_groups WHERE group_id=?", (g["id"],)).fetchone()[0]
                        out.append(d)
                    return self.send_json(out)
                if method in ("POST", "PUT"):
                    data = self.read_json()
                    name = (data.get("name") or "").strip()[:40]
                    if not name:
                        return self.send_json({"error": "Bitte einen Namen angeben."}, 400)
                    if conn.execute("SELECT 1 FROM groups WHERE name=? AND id != ?", (name, rid or 0)).fetchone():
                        return self.send_json({"error": "Diese Gruppe gibt es schon."}, 400)
                    if method == "POST":
                        sort = conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 FROM groups").fetchone()[0]
                        rid = conn.execute("INSERT INTO groups (name, description, sort) VALUES (?, ?, ?)",
                                           (name, data.get("description") or "", sort)).lastrowid
                    else:
                        conn.execute("UPDATE groups SET name=?, description=? WHERE id=?", (name, data.get("description") or "", rid))
                    for area in AREAS:
                        lvl = int((data.get("perms") or {}).get(area, 0) or 0)
                        conn.execute("INSERT OR REPLACE INTO group_perms (group_id, area, level) VALUES (?, ?, ?)", (rid, area, max(0, min(2, lvl))))
                    return self.send_json({"ok": True, "id": rid})
                if method == "DELETE" and rid:
                    conn.execute("DELETE FROM user_groups WHERE group_id=?", (rid,))
                    conn.execute("DELETE FROM group_perms WHERE group_id=?", (rid,))
                    conn.execute("DELETE FROM groups WHERE id=?", (rid,))
                    return self.send_json({"ok": True})
        return self.send_json({"error": "Unbekannter Pfad"}, 404)

    def api_table(self, method, table, rid, perms=None):
        now = datetime.now().isoformat(timespec="seconds")
        hide = ()
        if perms is not None:
            if perms.get("finanzen", 0) < 1:
                hide += FINANCE_FIELDS.get(table, ())
            if perms.get(TABLE_AREA.get(table), 0) < 1:
                hide += AREA_FIELDS.get(table, ())
            if perms.get(TABLE_AREA.get(table), 0) < 2:
                hide += WRITE_FIELDS.get(table, ())
                if table in WRITE_ONLY_TABLES:
                    return self.send_json({"error": "Dafür fehlen dir die Rechte."}, 403)

        def out(r):
            d = row_dict(r)
            for f in hide:
                d.pop(f, None)
            return d

        with db() as conn:
            if method == "GET":
                if rid is None:
                    rows = conn.execute(f'SELECT * FROM "{table}" ORDER BY id').fetchall()
                    return self.send_json([out(r) for r in rows])
                r = conn.execute(f'SELECT * FROM "{table}" WHERE id=?', (rid,)).fetchone()
                return self.send_json(out(r) if r else None, 200 if r else 404)

            if method == "POST":
                vals = clean_values(table, self.read_json())
                if any(has_bad_link(v) for v in vals.values()):
                    return self.send_json({"error": "Links müssen mit https:// beginnen oder auf eine Datei im Hub zeigen."}, 400)
                for f in hide + SERVER_FIELDS.get(table, ()):
                    vals.pop(f, None)
                if table == "apparel":
                    vals["public_token"] = secrets.token_urlsafe(18)
                vals["created_at"] = now
                vals["updated_at"] = now
                cols = ", ".join(f'"{k}"' for k in vals)
                qs = ", ".join("?" for _ in vals)
                cur = conn.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({qs})', list(vals.values()))
                if table == "supporter_cards":   # bezahlt ohne Nummer: nächste Kartennummer
                    assign_card_numbers(conn)
                r = conn.execute(f'SELECT * FROM "{table}" WHERE id=?', (cur.lastrowid,)).fetchone()
                audit(conn, getattr(self, "user", None), "neu", table, cur.lastrowid, audit_label(r),
                      {k: audit_short(v) for k, v in vals.items() if k not in AUDIT_SKIP and v not in (None, "")})
                return self.send_json(out(r), 201)

            if method == "PUT" and rid is not None:
                vals = clean_values(table, self.read_json())
                if any(has_bad_link(v) for v in vals.values()):
                    return self.send_json({"error": "Links müssen mit https:// beginnen oder auf eine Datei im Hub zeigen."}, 400)
                for f in hide + SERVER_FIELDS.get(table, ()):
                    vals.pop(f, None)
                vals.pop("public_token", None)   # neuer Link nur über /api/apparel/<id>/new-link
                vals["updated_at"] = now
                old = conn.execute(f'SELECT * FROM "{table}" WHERE id=?', (rid,)).fetchone()
                if table == "apparel_orders" and old and old["booked_tx"] and "paid" in vals and int(vals["paid"] or 0) != int(old["paid"] or 0):
                    return self.send_json({"error": "Diese Bestellung ist schon in den Finanzen gebucht, „bezahlt“ lässt sich nicht mehr ändern."}, 400)
                sets = ", ".join(f'"{k}"=?' for k in vals)
                conn.execute(f'UPDATE "{table}" SET {sets} WHERE id=?', list(vals.values()) + [rid])
                if table == "supporter_cards":   # bezahlt ohne Nummer: nächste Kartennummer
                    assign_card_numbers(conn)
                    if "number" in vals:
                        vals["number"] = conn.execute("SELECT number FROM supporter_cards WHERE id=?", (rid,)).fetchone()["number"]
                r = conn.execute(f'SELECT * FROM "{table}" WHERE id=?', (rid,)).fetchone()
                if old:
                    changes = {k: [audit_short(old[k]), audit_short(v)] for k, v in vals.items()
                               if k not in AUDIT_SKIP and str(old[k] if old[k] is not None else "") != str(v if v is not None else "")}
                    if changes:
                        audit(conn, getattr(self, "user", None), "geändert", table, rid, audit_label(r), changes)
                return self.send_json(out(r) if r else None)

            if method == "DELETE" and rid is not None:
                old = conn.execute(f'SELECT * FROM "{table}" WHERE id=?', (rid,)).fetchone()
                if old:
                    audit(conn, getattr(self, "user", None), "gelöscht", table, rid, audit_label(old),
                          {k: audit_short(v) for k, v in row_dict(old).items() if k not in AUDIT_SKIP and v not in (None, "")})
                conn.execute(f'DELETE FROM "{table}" WHERE id=?', (rid,))
                if table == "card_orders":   # unbezahlte Karten der Bestellung gehen mit, bezahlte bleiben
                    conn.execute("DELETE FROM supporter_cards WHERE order_id=? AND IFNULL(paid, 0)=0", (rid,))
                    conn.execute("UPDATE supporter_cards SET order_id=NULL WHERE order_id=?", (rid,))
                if table == "games":
                    conn.execute("DELETE FROM assignments WHERE game_id=?", (rid,))
                if table == "media_team":
                    conn.execute("DELETE FROM assignments WHERE member_id=?", (rid,))
                if table == "members":
                    conn.execute("UPDATE users SET member_id=NULL WHERE member_id=?", (rid,))
                if table == "magazines":
                    conn.execute("DELETE FROM magazine_pages WHERE magazine_id=?", (rid,))
                if table == "apparel":
                    conn.execute("DELETE FROM apparel_orders WHERE apparel_id=?", (rid,))
                return self.send_json({"ok": True})

        return self.send_json({"error": "Methode nicht erlaubt"}, 405)

    # -- Webseite im Hub (Bereich Medien) ---------------------------------
    # -- Wartungsmodus der Webseite (/api/maintenance): Lesen mit Wartung 1, Schalten und Texte mit Wartung 2 --
    def api_maintenance(self, method, p, user, can):
        if not can("wartung", 1):
            return self.deny()
        if p == ["image"]:   # Hintergrundbild der Wartungsseite, gleiche Prüfung wie die Bilder der Webseite
            if not can("wartung", 2):
                return self.deny("Zum Ändern des Wartungsmodus braucht es Schreibrecht im Bereich Wartung.")
            return self.site_image(method, website.MAINT_SLOT, user, lambda: self.api_maintenance("GET", [], user, can))
        if p:
            return self.send_json({"error": "Nicht gefunden"}, 404)
        if method == "PUT":
            if not can("wartung", 2):
                return self.deny("Zum Ändern des Wartungsmodus braucht es Schreibrecht im Bereich Wartung.")
            data = self.read_json()
            new = {}
            if "on" in data:
                new["maint_on"] = "1" if data["on"] else ""
            if "title" in data:
                new["maint_title"] = str(data["title"] or "").strip()[:120]
            if "text" in data:
                new["maint_text"] = str(data["text"] or "").strip()[:2000]
            if "until" in data:
                u = str(data["until"] or "").strip()[:16]
                new["maint_until"] = u if re.fullmatch(r"\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?", u) else ""
            with db() as conn:
                old = {k: get_setting(conn, k) for k in new}
                changes = {k: [audit_short(old[k]), audit_short(v)] for k, v in new.items() if (old[k] or "") != v}
                for k, v in new.items():
                    set_setting(conn, k, v)
                if "maint_on" in changes:
                    audit(conn, user, "eingeschaltet" if new["maint_on"] else "ausgeschaltet", "settings", None, "Wartungsmodus", changes)
                elif changes:
                    audit(conn, user, "geändert", "settings", None, "Wartungsmodus", changes)
            return self.api_maintenance("GET", [], user, can)
        if method != "GET":
            return self.send_json({"error": "Methode nicht erlaubt"}, 405)
        site = public_site()
        own = site["images"].get(website.MAINT_SLOT)
        with db() as conn:
            st = {k: get_setting(conn, k) for k in ("maint_on", "maint_title", "maint_text", "maint_until")}
            alt = (web_images(conn).get(website.MAINT_SLOT) or {}).get("alt", "")
            last = conn.execute("SELECT time, user_name, action FROM audit_log WHERE label='Wartungsmodus' AND action IN ('eingeschaltet','ausgeschaltet') "
                                "ORDER BY id DESC LIMIT 1").fetchone()
        src = (own or {}).get("src") or {}
        return self.send_json({"on": st["maint_on"] == "1", "title": st["maint_title"], "text": st["maint_text"], "until": st["maint_until"],
                               "image": {"own": bool(own), "alt": alt, "preview": src.get(640) or (src[min(src)] if src else "/web/assets/img/hero-640.webp")},
                               "last": dict(last) if last else None, "can_edit": can("wartung", 2)})

    def site_image(self, method, slot, user, done):
        """Eigenes Bild der Webseite hochladen (WebP vom Browser), Alt-Text ändern oder zum Standardbild zurück."""
        with db() as conn:
            imgs = web_images(conn)
            cur = imgs.get(slot) or {}
            if method == "DELETE":   # zurück zum Standardbild
                for f in (cur.get("files") or {}).values():
                    (SITE_DIR / str(f)).unlink(missing_ok=True)
                imgs.pop(slot, None)
                action = "Standardbild"
            elif method == "PUT":    # nur Alt-Text
                imgs[slot] = {**cur, "alt": str(self.read_json().get("alt") or "")[:300]}
                action = "Alt-Text"
            elif method == "POST":
                data = self.read_json()
                files, stamp = {}, uuid.uuid4().hex[:10]
                SITE_DIR.mkdir(parents=True, exist_ok=True)
                for w, url in (data.get("files") or {}).items():
                    m = re.match(r"^data:image/webp;base64,(.+)$", str(url), re.S)
                    if not (str(w).isdigit() and int(w) in SITE_WIDTHS and m):
                        continue
                    raw = base64.b64decode(m.group(1))
                    if len(raw) > SITE_IMAGE_MAX or raw[:4] != b"RIFF" or raw[8:12] != b"WEBP":
                        for f in files.values():
                            (SITE_DIR / f).unlink(missing_ok=True)
                        return self.send_json({"error": "Das Bild ist ungültig oder zu groß."}, 400)
                    name = f"{slot}-{w}-{stamp}.webp"
                    (SITE_DIR / name).write_bytes(raw)
                    files[str(w)] = name
                if not files:
                    return self.send_json({"error": "Kein Bild empfangen."}, 400)
                for f in (cur.get("files") or {}).values():
                    (SITE_DIR / str(f)).unlink(missing_ok=True)
                imgs[slot] = {"alt": str(data.get("alt") or "")[:300], "w": int(data.get("w") or 0), "h": int(data.get("h") or 0), "files": files}
                action = "neues Bild"
            else:
                return self.send_json({"error": "Methode nicht erlaubt"}, 405)
            set_setting(conn, "web_images", json.dumps(imgs))
            audit(conn, user, "geändert", "settings", None, f"Webseite Bild {website.IMAGE_SLOTS[slot][0]}", {"Änderung": ["", action]})
        return done()

    def api_newsletter(self, method, p, user, can):
        """Hub > Newsletter (Bereich Medien: Lesen 1, Ändern und Senden 2): Abonnenten, Ausgaben; Gruppen über die generische Tabelle nl_groups."""
        if not can("medien", 1):
            return self.deny()
        if method != "GET" and not can("medien", 2):
            return self.deny("Für den Newsletter braucht es Bearbeiten im Bereich Medien.")
        what = p[0] if p else ""
        rid = int(p[1]) if len(p) > 1 and p[1].isdigit() else None
        act = p[2] if len(p) > 2 else ""
        now = datetime.now().isoformat(timespec="seconds")
        email_ok = lambda v: re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v or "")
        if method == "GET" and not p:
            with db() as conn:
                subs = conn.execute("SELECT * FROM nl_subscribers ORDER BY created DESC, id DESC").fetchall()
                issues = conn.execute("SELECT * FROM nl_issues ORDER BY id DESC").fetchall()
                groups = [row_dict(r) for r in conn.execute("SELECT * FROM nl_groups ORDER BY IFNULL(sort, 0), name")]
            return self.send_json({
                "subscribers": [{"id": r["id"], "email": r["email"], "name": r["name"] or "", "status": r["status"], "groups": nl_ids(r["groups"]),
                                 "consent_at": r["consent_at"] or "", "source": r["source"] or "", "created": r["created"] or "", "unsubscribed_at": r["unsubscribed_at"] or ""} for r in subs],
                "issues": [{"id": r["id"], "subject": r["subject"] or "", "body": r["body"] or "", "groups": nl_ids(r["groups"]), "status": r["status"],
                            "created": r["created"] or "", "sent_at": r["sent_at"] or "", "sent_count": r["sent_count"] or 0, "failed": r["failed"] or 0} for r in issues],
                "groups": groups, "link_ok": bool(SITE_URL)})
        data = self.read_json() if method in ("POST", "PUT") else {}
        with db() as conn:
            all_groups = {r["id"] for r in conn.execute("SELECT id FROM nl_groups")}
            gl = lambda v: sorted({int(x) for x in (v if isinstance(v, list) else []) if str(x).isdigit() and int(x) in all_groups})
            if what == "subscribers":
                if method == "POST" and rid is None:   # von Hand eintragen, nur mit bestätigter Einwilligung
                    email = str(data.get("email") or "").strip()[:150]
                    if not email_ok(email):
                        return self.send_json({"error": "Bitte eine gültige E-Mail-Adresse eintragen."}, 400)
                    if not data.get("consent"):
                        return self.send_json({"error": "Bitte bestätigen, dass die Person in den Newsletter eingewilligt hat."}, 400)
                    note = re.sub(r"\s+", " ", str(data.get("note") or "")).strip()[:300]
                    who = user.get("display_name") or user.get("username")
                    ctext = f"Im Hub eingetragen von {who}" + (f": {note}" if note else "")
                    row = conn.execute("SELECT id, groups, status FROM nl_subscribers WHERE email=?", (email,)).fetchone()
                    g = gl(data.get("groups"))
                    if row:
                        g = sorted(set(g) | (set(nl_ids(row["groups"])) if row["status"] == "aktiv" else set()))
                        conn.execute("UPDATE nl_subscribers SET status='aktiv', groups=?, name=COALESCE(NULLIF(?, ''), name), consent_at=?, consent_text=?, unsubscribed_at=NULL WHERE id=?",
                                     (json.dumps(g), str(data.get("name") or "")[:80], now, ctext, row["id"]))
                        sid = row["id"]
                    else:
                        sid = conn.execute("INSERT INTO nl_subscribers (email, name, status, groups, consent_at, consent_text, source, created) VALUES (?, ?, 'aktiv', ?, ?, ?, 'Hub', ?)",
                                           (email, str(data.get("name") or "")[:80], json.dumps(g), now, ctext, now)).lastrowid
                    audit(conn, user, "Newsletter eingetragen", "nl_subscribers", sid, email)
                    return self.send_json({"ok": True, "id": sid})
                r = conn.execute("SELECT * FROM nl_subscribers WHERE id=?", (rid,)).fetchone() if rid else None
                if not r:
                    return self.send_json({"error": "Abonnent nicht gefunden."}, 404)
                if method == "PUT":
                    conn.execute("UPDATE nl_subscribers SET groups=?, name=? WHERE id=?", (json.dumps(gl(data.get("groups"))), str(data.get("name") or "")[:80], rid))
                    audit(conn, user, "geändert", "nl_subscribers", rid, r["email"])
                    return self.send_json({"ok": True})
                if method == "POST" and act == "unsubscribe":
                    conn.execute("UPDATE nl_subscribers SET status='abgemeldet', unsubscribed_at=?, confirm_hash=NULL WHERE id=?", (now, rid))
                    audit(conn, user, "Newsletter abgemeldet", "nl_subscribers", rid, r["email"])
                    return self.send_json({"ok": True})
                if method == "DELETE":   # Daten auf Wunsch ganz löschen
                    conn.execute("DELETE FROM nl_subscribers WHERE id=?", (rid,))
                    audit(conn, user, "gelöscht", "nl_subscribers", rid, r["email"])
                    return self.send_json({"ok": True})
            if what == "issues":
                subject, body = str(data.get("subject") or "").strip()[:200], str(data.get("body") or "").replace("\r", "")[:50000]
                if method == "POST" and rid is None:
                    if not subject:
                        return self.send_json({"error": "Bitte einen Betreff eintragen."}, 400)
                    iid = conn.execute("INSERT INTO nl_issues (subject, body, groups, status, created, created_by) VALUES (?, ?, ?, 'entwurf', ?, ?)",
                                       (subject, body, json.dumps(gl(data.get("groups"))), now, user["id"])).lastrowid
                    return self.send_json({"ok": True, "id": iid})
                it = conn.execute("SELECT * FROM nl_issues WHERE id=?", (rid,)).fetchone() if rid else None
                if not it:
                    return self.send_json({"error": "Newsletter nicht gefunden."}, 404)
                draft = it["status"] == "entwurf"
                if method == "PUT":
                    if not draft:
                        return self.send_json({"error": "Verschickte Newsletter lassen sich nicht mehr ändern."}, 400)
                    if not subject:
                        return self.send_json({"error": "Bitte einen Betreff eintragen."}, 400)
                    conn.execute("UPDATE nl_issues SET subject=?, body=?, groups=? WHERE id=?", (subject, body, json.dumps(gl(data.get("groups"))), rid))
                    return self.send_json({"ok": True, "id": rid})
                if method == "DELETE":
                    if not draft:
                        return self.send_json({"error": "Verschickte Newsletter bleiben als Nachweis gespeichert."}, 400)
                    conn.execute("DELETE FROM nl_issues WHERE id=?", (rid,))
                    return self.send_json({"ok": True})
                if method == "POST" and act in ("test", "send"):
                    if not (it["subject"] or "").strip() or not (it["body"] or "").strip():
                        return self.send_json({"error": "Bitte Betreff und Text eintragen und speichern."}, 400)
                    cfg = smtp_config()
                    if not cfg["smtp_host"]:
                        return self.send_json({"error": "E-Mail-Versand ist nicht eingerichtet (Einstellungen)."}, 400)
                    base = self.base_url()
                    if act == "test":
                        to = account_email(conn, conn.execute("SELECT * FROM users WHERE id=?", (user["id"],)).fetchone())
                        if not to:
                            return self.send_json({"error": "In deinem Profil fehlt eine E-Mail-Adresse für den Test."}, 400)
                        text, html = nl_mail(get_setting(conn, "club_name") or "SV Amisia Wolthusen", letter_text(conn, "footer"), it["subject"], it["body"], base + "/newsletter")
                        err = send_mail(cfg, to, "[Test] " + it["subject"], text, footer=False, html=html)
                        return self.send_json({"error": f"Test fehlgeschlagen: {err}"}, 400) if err else self.send_json({"ok": True, "to": to})
                    if not draft:
                        return self.send_json({"error": "Dieser Newsletter wurde schon verschickt."}, 400)
                    n = len(nl_recipients(conn, nl_ids(it["groups"])))
                    if not n:
                        return self.send_json({"error": "In den gewählten Gruppen gibt es keine aktiven Abonnenten."}, 400)
                    conn.execute("UPDATE nl_issues SET status='läuft' WHERE id=?", (rid,))
                    audit(conn, user, "Newsletter gestartet", "nl_issues", rid, it["subject"][:100], {"Empfänger": ["", str(n)]})
                    threading.Thread(target=nl_send_issue, args=(rid, dict(user), base), daemon=True).start()
                    return self.send_json({"ok": True, "count": n})
        return self.send_json({"error": "Nicht gefunden"}, 404)

    def api_sponsor_contracts(self, method, p, user, can):
        """Sponsoringverträge: Liste lesen (Verein 1 + Finanzen 1), erstellen und löschen (Verein 2 + Finanzen 1).
        Das PDF liegt in data/media und hängt zusätzlich als Datei am Sponsor."""
        if not (can("verein", 1) and can("finanzen", 1)):
            return self.deny("Verträge brauchen Leserecht in den Bereichen Verein und Finanzen.")
        if method != "GET" and not can("verein", 2):
            return self.deny("Zum Erstellen und Löschen von Verträgen braucht es Schreibrecht im Bereich Verein.")
        if method == "GET" and not p:
            with db() as conn:
                rows = conn.execute("SELECT c.*, s.name AS sponsor FROM sponsor_contracts c LEFT JOIN sponsors s ON s.id=c.sponsor_id ORDER BY c.id DESC").fetchall()
                invs = conn.execute("SELECT i.*, s.name AS sponsor, c.number AS contract FROM sponsor_invoices i LEFT JOIN sponsors s ON s.id=i.sponsor_id "
                                    "LEFT JOIN sponsor_contracts c ON c.id=i.contract_id ORDER BY i.id DESC").fetchall()
                return self.send_json({"contracts": [{"id": r["id"], "sponsor_id": r["sponsor_id"], "sponsor": r["sponsor"] or "(gelöscht)", "number": r["number"],
                                                      "file": r["file"], "created": r["created"], "data": json.loads(r["data"] or "{}")} for r in rows],
                                       "invoices": [{"id": r["id"], "contract_id": r["contract_id"], "contract": r["contract"] or "", "sponsor": r["sponsor"] or "(gelöscht)",
                                                     "number": r["number"], "file": r["file"], "data": json.loads(r["data"] or "{}")} for r in invs],
                                       "club_rep": get_setting(conn, "contract_club_rep") or "", "sender": get_setting(conn, "inv_sender") or ""})
        if method == "POST" and not p:
            with db() as conn:
                d, err = contract_clean(self.read_json(), conn)
                if err:
                    return self.send_json({"error": err}, 400)
                year = d["start"][:4]
                used = [int(m.group(1)) for (num,) in conn.execute("SELECT number FROM sponsor_contracts WHERE number LIKE ?", (f"V-{year}-%",))
                        if (m := re.fullmatch(rf"V-{year}-(\d+)", num or ""))]
                number = f"V-{year}-{max(used + [0]) + 1:03d}"
                pdf = sponsor_contract_pdf(d, number, conn)
                safe = re.sub(r"[^A-Za-z0-9_-]+", "-", d["partner_name"])[:30].strip("-") or "sponsor"
                fname = f"{datetime.now():%Y%m%d-%H%M%S}-sponsoringvertrag-{number}-{safe}-{uuid.uuid4().hex[:20]}.pdf"
                (MEDIA / fname).write_bytes(pdf)
                path, now = f"/media/{fname}", datetime.now().isoformat(timespec="seconds")
                cid = conn.execute("INSERT INTO sponsor_contracts (sponsor_id, number, data, file, created, created_by) VALUES (?,?,?,?,?,?)",
                                   (d["sponsor_id"], number, json.dumps(d, ensure_ascii=False), path, now, user["id"])).lastrowid
                row = conn.execute("SELECT files FROM sponsors WHERE id=?", (d["sponsor_id"],)).fetchone()
                try:
                    files = json.loads(row["files"] or "[]") if row else []
                except ValueError:
                    files = []
                files = (files if isinstance(files, list) else []) + [{"name": f"Sponsoringvertrag {number}.pdf", "path": path, "size": len(pdf), "added": now}]
                conn.execute("UPDATE sponsors SET files=?, updated_at=? WHERE id=?", (json.dumps(files, ensure_ascii=False), now, d["sponsor_id"]))
                set_setting(conn, "contract_club_rep", d["club_rep"])
                audit(conn, user, "erstellt", "sponsor_contracts", cid, f"Sponsoringvertrag {number}", {"Sponsor": ["", d["partner_name"]], "Laufzeit": ["", f"{d['start']} bis {d['end']}"]})
            return self.send_json({"ok": True, "id": cid, "number": number, "file": path})
        if method == "PUT" and len(p) == 1 and p[0].isdigit():   # Vertrag ändern: gleiche Nummer, neues PDF ersetzt das alte
            with db() as conn:
                old = conn.execute("SELECT * FROM sponsor_contracts WHERE id=?", (int(p[0]),)).fetchone()
                if not old:
                    return self.send_json({"error": "Vertrag nicht gefunden."}, 404)
                d, err = contract_clean(self.read_json(), conn)
                if err:
                    return self.send_json({"error": err}, 400)
                number = old["number"]
                pdf = sponsor_contract_pdf(d, number, conn)
                safe = re.sub(r"[^A-Za-z0-9_-]+", "-", d["partner_name"])[:30].strip("-") or "sponsor"
                fname = f"{datetime.now():%Y%m%d-%H%M%S}-sponsoringvertrag-{number}-{safe}-{uuid.uuid4().hex[:20]}.pdf"
                (MEDIA / fname).write_bytes(pdf)
                path, now = f"/media/{fname}", datetime.now().isoformat(timespec="seconds")
                conn.execute("UPDATE sponsor_contracts SET sponsor_id=?, data=?, file=? WHERE id=?", (d["sponsor_id"], json.dumps(d, ensure_ascii=False), path, old["id"]))
                for sid in {old["sponsor_id"], d["sponsor_id"]}:   # Datei am Sponsor austauschen (auch wenn der Sponsor gewechselt wurde)
                    row = conn.execute("SELECT files FROM sponsors WHERE id=?", (sid,)).fetchone()
                    if not row:
                        continue
                    try:
                        files = json.loads(row["files"] or "[]")
                    except ValueError:
                        files = []
                    files = [f for f in (files if isinstance(files, list) else []) if not (isinstance(f, dict) and f.get("path") == old["file"])]
                    if sid == d["sponsor_id"]:
                        files.append({"name": f"Sponsoringvertrag {number}.pdf", "path": path, "size": len(pdf), "added": now})
                    conn.execute("UPDATE sponsors SET files=?, updated_at=? WHERE id=?", (json.dumps(files, ensure_ascii=False), now, sid))
                before = json.loads(old["data"] or "{}")
                changes = {k: [audit_short(str(before.get(k, ""))), audit_short(str(v))] for k, v in d.items() if str(before.get(k, "")) != str(v)}
                audit(conn, user, "geändert", "sponsor_contracts", old["id"], f"Sponsoringvertrag {number}", changes)
            f = MEDIA / Path(old["file"] or "").name
            if (old["file"] or "").startswith("/media/") and f.is_file():
                f.unlink()
            return self.send_json({"ok": True, "id": old["id"], "number": number, "file": path})
        if method == "POST" and len(p) == 2 and p[0].isdigit() and p[1] == "invoice":   # Rechnung zum Vertrag (Finanzen 2)
            if not can("finanzen", 2):
                return self.deny("Rechnungen erstellen braucht Schreibrecht im Bereich Finanzen.")
            from decimal import Decimal, InvalidOperation
            body = self.read_json()
            with db() as conn:
                c = conn.execute("SELECT * FROM sponsor_contracts WHERE id=?", (int(p[0]),)).fetchone()
                if not c:
                    return self.send_json({"error": "Vertrag nicht gefunden."}, 404)
                d = json.loads(c["data"] or "{}")
                if d.get("tax") not in CONTRACT_TAX:
                    return self.send_json({"error": "Dieser Vertrag hat keinen Geldbetrag, nur Sachleistungen."}, 400)
                if not (get_setting(conn, "inv_tax_no") or "").strip():
                    return self.send_json({"error": "Für Rechnungen braucht es die Steuernummer des Vereins: Dauerkarte > Einstellungen."}, 400)
                raw = re.sub(r"[^\d,.]", "", str(body.get("amount") or ""))
                raw = raw.replace(".", "").replace(",", ".") if "," in raw else (raw.replace(".", "") if re.fullmatch(r"\d{1,3}(\.\d{3})+", raw) else raw)
                try:
                    amount = Decimal(raw).quantize(Decimal("0.01"))
                except InvalidOperation:
                    amount = Decimal(0)
                if not 0 < amount < 10000000:
                    return self.send_json({"error": "Bitte den Rechnungsbetrag eintragen."}, 400)
                try:
                    day = date.fromisoformat(str(body.get("date") or date.today().isoformat())[:10])
                except ValueError:
                    return self.send_json({"error": "Bitte ein gültiges Rechnungsdatum eintragen."}, 400)
                due_days = int(get_setting(conn, "inv_due_days") or 14) if str(get_setting(conn, "inv_due_days") or "14").isdigit() else 14
                text = "\n".join(x.strip()[:300] for x in str(body.get("text") or "").replace("\r", "").split("\n") if x.strip())[:1500] or f"Sponsoring laut Sponsoringvertrag {c['number']}"
                number = invoice_next(conn)
                inv = {"number": number, "date": day.isoformat(), "due": (day + timedelta(days=due_days)).isoformat(), "contract": c["number"],
                       "partner_name": d["partner_name"], "partner_address": d["partner_address"], "start": d["start"], "end": d["end"],
                       "amount": str(amount), "tax": d["tax"], "text": text}
                net, vat, gross = sponsor_invoice_sums(amount, d["tax"])
                inv.update(net=str(net), vat=str(vat), gross=str(gross))
                pdf = sponsor_invoice_pdf(inv, conn)
                safe = re.sub(r"[^A-Za-z0-9_-]+", "-", d["partner_name"])[:30].strip("-") or "sponsor"
                fname = f"{datetime.now():%Y%m%d-%H%M%S}-rechnung-{number}-{safe}-{uuid.uuid4().hex[:20]}.pdf"
                (MEDIA / fname).write_bytes(pdf)
                path, now = f"/media/{fname}", datetime.now().isoformat(timespec="seconds")
                iid = conn.execute("INSERT INTO sponsor_invoices (contract_id, sponsor_id, number, data, file, created, created_by) VALUES (?,?,?,?,?,?,?)",
                                   (c["id"], c["sponsor_id"], number, json.dumps(inv, ensure_ascii=False), path, now, user["id"])).lastrowid
                row = conn.execute("SELECT files FROM sponsors WHERE id=?", (c["sponsor_id"],)).fetchone()
                try:
                    files = json.loads(row["files"] or "[]") if row else []
                except ValueError:
                    files = []
                files = (files if isinstance(files, list) else []) + [{"name": f"Rechnung {number}.pdf", "path": path, "size": len(pdf), "added": now}]
                conn.execute("UPDATE sponsors SET files=?, updated_at=? WHERE id=?", (json.dumps(files, ensure_ascii=False), now, c["sponsor_id"]))
                audit(conn, user, "erstellt", "sponsor_invoices", iid, f"Rechnung {number}", {"Vertrag": ["", c["number"]], "Betrag": ["", eur_text(float(gross))]})
            return self.send_json({"ok": True, "id": iid, "number": number, "file": path})
        if method == "DELETE" and len(p) == 1 and p[0].isdigit():
            with db() as conn:
                r = conn.execute("SELECT * FROM sponsor_contracts WHERE id=?", (int(p[0]),)).fetchone()
                if not r:
                    return self.send_json({"error": "Vertrag nicht gefunden."}, 404)
                conn.execute("DELETE FROM sponsor_contracts WHERE id=?", (r["id"],))
                srow = conn.execute("SELECT files FROM sponsors WHERE id=?", (r["sponsor_id"],)).fetchone()
                if srow:
                    try:
                        files = [f for f in json.loads(srow["files"] or "[]") if not (isinstance(f, dict) and f.get("path") == r["file"])]
                        conn.execute("UPDATE sponsors SET files=? WHERE id=?", (json.dumps(files, ensure_ascii=False), r["sponsor_id"]))
                    except ValueError:
                        pass
                audit(conn, user, "gelöscht", "sponsor_contracts", r["id"], f"Sponsoringvertrag {r['number']}", {})
            f = MEDIA / Path(r["file"] or "").name
            if (r["file"] or "").startswith("/media/") and f.is_file():
                f.unlink()
            return self.send_json({"ok": True})
        return self.send_json({"error": "Nicht gefunden"}, 404)

    def api_website(self, method, p, user, can):
        if not can("medien", 1):
            return self.deny()
        if method != "GET" and not can("medien", 2):
            return self.deny("Zum Bearbeiten der Webseite braucht es Schreibrecht im Bereich Medien.")
        text_keys = [k for k in DEFAULT_SETTINGS if k.startswith("site_")]
        if not p and method == "PUT":
            data = self.read_json()
            texts = {k: str(v)[:40000 if k in ("site_impressum", "site_datenschutz") else 5000] for k, v in (data.get("texts") or {}).items() if k in text_keys}
            with db() as conn:
                old = {k: get_setting(conn, k) for k in texts}
                changes = {k: [audit_short(old[k]), audit_short(v)] for k, v in texts.items() if (old[k] or "") != v}
                for k, v in texts.items():
                    set_setting(conn, k, v)
                if isinstance(data.get("layout"), list):
                    set_setting(conn, "web_layout", json.dumps([[str(x[0]), bool(x[1])] for x in data["layout"]
                                                                if isinstance(x, list) and len(x) == 2 and x[0] in website.START_SECTIONS]))
                    changes["Aufbau Startseite"] = ["", " > ".join(k for k, v in web_layout(conn) if v)]
                if isinstance(data.get("nav"), list):   # Menü der Webseite: nur bekannte Einträge
                    known = dict(NAV_BUILTIN)
                    clean = [{"key": it["key"], "show": bool(it.get("show")), "label": str(it.get("label") or "").strip()[:40], "button": bool(it.get("button"))}
                             for it in data["nav"] if isinstance(it, dict) and it.get("key") in known]
                    set_setting(conn, "web_nav", json.dumps(clean, ensure_ascii=False))
                    changes["Menü"] = ["", " · ".join((it["label"] or known[it["key"]]) for it in clean if it["show"])]
                if data.get("links_reset"):   # Link-Seite: zurück zur Standardliste
                    set_setting(conn, "web_links", "")
                    changes["Link-Seite"] = ["", "Standard"]
                elif isinstance(data.get("links"), list):
                    bad = [str(it.get("label") or it.get("url") or "?")[:40] for it in data["links"] if isinstance(it, dict)
                           and (str(it.get("label") or "").strip() or str(it.get("url") or "").strip()) and not (str(it.get("label") or "").strip() and link_url_ok(it.get("url")))]
                    if bad:
                        return self.send_json({"error": "Bitte bei jedem Knopf einen Namen und eine Adresse mit https:// oder eine eigene Seite mit / eintragen: " + ", ".join(bad)}, 400)
                    clean = [{"label": str(it["label"]).strip()[:60], "url": link_url_ok(it["url"]), "hot": bool(it.get("hot"))}
                             for it in data["links"] if isinstance(it, dict) and str(it.get("label") or "").strip()][:LINKS_MAX]
                    set_setting(conn, "web_links", json.dumps(clean, ensure_ascii=False))
                    changes["Link-Seite"] = ["", " · ".join(it["label"] for it in clean)]
                if isinstance(data.get("sitemap"), dict):
                    sm = web_sitemap(conn, data["sitemap"])   # nur bekannte Seiten und gültige Prioritäten
                    set_setting(conn, "web_sitemap", json.dumps(sm))
                    changes["Sitemap"] = ["", ", ".join(f"{k or 'start'} {p}" for k, (on, p) in sm.items() if on)]
                if changes:
                    audit(conn, user, "geändert", "settings", None, "Webseite", changes)
            if "site_insta_hide" in changes:   # Raster gleich neu laden, nicht erst nach 30 Minuten
                threading.Thread(target=insta_refresh, daemon=True).start()
            return self.api_website("GET", [], user, can)
        if p[:1] == ["image"] and len(p) == 2 and p[1] in website.IMAGE_SLOTS and p[1] != website.MAINT_SLOT:
            return self.site_image(method, p[1], user, lambda: self.api_website("GET", [], user, can))
        if p or method != "GET":
            return self.send_json({"error": "Nicht gefunden"}, 404)
        return self.send_json(website_overview(text_keys))

    def api_settings(self, method, finance=True):
        with db() as conn:
            if method == "PUT":
                data = self.read_json()
                old = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")}
                changes = {k: [audit_short(old.get(k)), audit_short(v)] for k, v in data.items()
                           if k not in TWOFA_POLICY_KEYS
                           and str(old.get(k) or "") != str(v or "")}
                if changes:
                    audit(conn, getattr(self, "user", None), "geändert", "settings", None, "Einstellungen", changes)
                for k, v in data.items():
                    if k in TWOFA_POLICY_KEYS or k.startswith("sheet_"):   # 2FA-Pflicht nur über /api/admin/2fa-policy, Google-Tabelle gibt es nicht mehr
                        continue
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            return self.send_json({r["key"]: r["value"] for r in rows if finance or not r["key"].startswith("inv_")})   # Bank/Rechnung nur mit Finanzrecht

    def api_upload(self, library=True):
        data = self.read_json()
        raw = data.get("data", "")
        name = data.get("name") or "bild.png"
        m = re.match(r"^data:([\w/+.-]+);base64,(.*)$", raw, re.S)
        if not m:
            return self.send_json({"error": "Ungültige Datei"}, 400)
        mime, b64 = m.groups()
        suffix = Path(name).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
            suffix = ""
        # Unbekannte Typen (z. B. .pages, .indd) behalten ihre Endung statt .bin
        ext = (mimetypes.guess_extension(mime) if mime != "application/octet-stream" else None) or suffix or ".bin"
        if ext == ".jpe":
            ext = ".jpg"
        safe = re.sub(r"[^A-Za-z0-9_-]+", "-", Path(name).stem)[:40].strip("-") or "datei"
        # Zufallsteil lang genug, dass niemand fremde Dateinamen (Belege, Verträge) erraten kann; /media braucht ohnehin eine Anmeldung
        fname = f"{datetime.now():%Y%m%d-%H%M%S}-{safe}-{uuid.uuid4().hex[:20]}{ext}"
        (MEDIA / fname).write_bytes(base64.b64decode(b64))
        path = f"/media/{fname}"
        if data.get("library", True) and library:
            with db() as conn:
                conn.execute(
                    "INSERT INTO media (path, name, tags, created, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (path, name, data.get("tags", ""), datetime.now().isoformat(timespec="seconds"),
                     datetime.now().isoformat(timespec="seconds"), datetime.now().isoformat(timespec="seconds")),
                )
        return self.send_json({"path": path})

    def api_backup(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            # konsistente Kopie der Datenbank
            tmp = db_snapshot(DATA / "_backup_tmp.db")
            # Zugangsdaten gehören nicht in ein heruntergeladenes Backup
            c = sqlite3.connect(tmp)
            try:
                for t in ("sessions", "users", "user_groups", "user_perms", "secrets", "audit_log", "user_2fa", "push_subs", "mail_tasks", "user_mail", "pf_inbox", "mail_accounts", "mail_account_users", "mail_links"):
                    c.execute(f"DELETE FROM {t}")
                c.commit()
                c.execute("VACUUM")
            finally:
                c.close()
            z.write(tmp, "data/wolthusen.db")
            tmp.unlink(missing_ok=True)
            for f in MEDIA.iterdir():
                if f.is_file():
                    z.write(f, f"data/media/{f.name}")
        data = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Content-Disposition",
                         f'attachment; filename="WolthusenHub-Backup-{datetime.now():%Y-%m-%d}.zip"')
        self.end_headers()
        self.wfile.write(data)

    def api_export(self):
        out = {}
        with db() as conn:
            for t in TABLES:
                out[t] = [row_dict(r) for r in conn.execute(f'SELECT * FROM "{t}"')]
            out["settings"] = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM settings")}
        return self.send_json(out)

    def api_dashboard(self, perms):
        today = datetime.now().strftime("%Y-%m-%d")
        with db() as conn:
            q = lambda sql, a=(): [row_dict(r) for r in conn.execute(sql, a)]
            res = {
                "today": today,
                "next_games": q("SELECT * FROM games WHERE date >= ? ORDER BY date, time LIMIT 4", (today,)),
                "last_game": (q("SELECT * FROM games WHERE date < ? ORDER BY date DESC, time DESC LIMIT 1", (today,)) or [None])[0],
                "upcoming_posts": q("SELECT * FROM posts WHERE date >= ? AND status != 'Gepostet' ORDER BY date, time LIMIT 12", (today,)),
                "overdue_posts": q("SELECT * FROM posts WHERE date < ? AND status != 'Gepostet' AND status != 'Idee' ORDER BY date", (today,)),
                "counts": {
                    "players": conn.execute("SELECT COUNT(*) FROM players WHERE active=1 AND kind='Spieler'").fetchone()[0],
                    "staff": conn.execute("SELECT COUNT(*) FROM players WHERE active=1 AND kind!='Spieler'").fetchone()[0],
                    "no_consent": conn.execute("SELECT COUNT(*) FROM players WHERE active=1 AND (consent IS NULL OR consent=0)").fetchone()[0],
                    "sponsors": conn.execute("SELECT COUNT(*) FROM sponsors WHERE active=1").fetchone()[0],
                    "posts_done": conn.execute("SELECT COUNT(*) FROM posts WHERE status='Gepostet'").fetchone()[0],
                    "members": conn.execute("SELECT COUNT(*) FROM members WHERE status IN ('Aktiv', 'Probetraining')").fetchone()[0],
                },
            }
            if perms.get("finanzen", 0) >= 1:
                y = today[:4]
                inc = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE kind='Einnahme' AND substr(date, 1, 4)=?", (y,)).fetchone()[0]
                exp = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE kind='Ausgabe' AND substr(date, 1, 4)=?", (y,)).fetchone()[0]
                res["finance"] = {"year": y, "income": inc, "expense": exp,
                                  "open": conn.execute("SELECT COUNT(*) FROM transactions WHERE status='Offen'").fetchone()[0]}
        if perms.get("medien", 0) < 1:
            res["upcoming_posts"], res["overdue_posts"] = [], []
            res["counts"].pop("posts_done", None)
        if perms.get("mitglieder", 0) < 1:
            res["counts"].pop("members", None)
        return self.send_json(res)


# ---------------------------------------------------------------------------
# Seiten für Anmeldung und Ersteinrichtung
# ---------------------------------------------------------------------------
AUTH_PAGE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Wolthusen Hub</title><link rel="icon" href="/static/icon.png"><link rel="stylesheet" href="/static/style.css">
<link rel="manifest" href="/manifest.webmanifest"><link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png">
<meta name="theme-color" content="#15122B"><meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Wolthusen Hub"><meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<style>
body{display:flex;align-items:center;justify-content:center;min-height:100vh;background:#0e0e0e;padding:16px}
.auth{width:min(380px,100%);background:#fff;border-radius:14px;padding:30px 28px;box-shadow:0 20px 60px rgba(0,0,0,.4)}
.auth-logo{background:#0e0e0e;border-radius:10px;display:flex;align-items:center;gap:12px;padding:14px 16px;margin:-6px -4px 22px}
.auth-logo img{height:42px}.auth-logo b{color:#fff;font-family:var(--head);text-transform:uppercase;letter-spacing:.3px}
.auth-logo span{display:block;color:#999;font-size:11px;letter-spacing:2px;text-transform:uppercase}
.auth .field{margin-bottom:12px}.auth .btn{width:100%;justify-content:center;padding:10px;margin-top:6px}
.err{color:#b00020;font-size:13px;min-height:18px;margin-top:8px}
</style></head><body>
<form class="auth" id="f" method="post" action="/auth/none">
  <div class="auth-logo"><img src="/static/logo.png" alt=""><div><b>SV Amisia Wolthusen</b><span>Hub</span></div></div>
  %%BODY%%
  <div class="err" id="err"></div>
</form>
<script>
let action = '%%ACTION%%';
document.getElementById('f').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = Object.fromEntries(new FormData(document.getElementById('f')));
  if (fd.password2 !== undefined && fd.password !== fd.password2) { document.getElementById('err').textContent = 'Die Passwörter stimmen nicht überein.'; return false; }
  const r = await fetch(action, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-TMH': '1' }, body: JSON.stringify(fd) });
  const d = await r.json().catch(() => ({}));
  if (r.ok && d.need_2fa && document.getElementById('s2')) {   // Anmeldung: Passwort stimmt, jetzt der Code aus der App
    action = '/auth/login2';
    document.querySelectorAll('#s1 input').forEach(i => { i.disabled = true; });
    document.getElementById('s1').hidden = true;
    document.getElementById('s2').hidden = false;
    document.querySelectorAll('#s2 input').forEach(i => { i.disabled = false; });
    document.getElementById('tk').value = d.ticket;
    document.getElementById('c').focus();
    document.getElementById('err').textContent = '';
    return;
  }
  if (r.ok) location.href = d.next || '%%NEXT%%';
  else if (d.restart) { document.getElementById('err').textContent = d.error; setTimeout(() => location.reload(), 2500); }
  else document.getElementById('err').textContent = d.error || 'Fehler';
});
</script></body></html>"""

LOGIN_PAGE = (AUTH_PAGE.replace("%%ACTION%%", "/auth/login").replace("%%NEXT%%", "/hub").replace("%%BODY%%", """
  <div id="s1">
  <div class="field"><label for="u">Benutzername</label><input class="input" id="u" name="username" autocomplete="username" required autofocus></div>
  <div class="field"><label for="p">Passwort</label><input class="input" id="p" name="password" type="password" autocomplete="current-password" required></div>
  <button class="btn primary">Anmelden</button>
  <p class="small" style="text-align:center;margin:14px 0 0"><a href="/passwort-vergessen">Passwort vergessen?</a></p>
  </div>
  <div id="s2" hidden>
  <p style="margin-top:0"><b>Zwei-Faktor-Anmeldung</b></p>
  <p class="muted small">Gib den 6-stelligen Code aus deiner Authenticator-App ein. Handy nicht zur Hand? Dann einen deiner Wiederherstellungscodes.</p>
  <input type="hidden" id="tk" name="ticket" disabled>
  <div class="field"><label for="c">Code</label><input class="input" id="c" name="code" inputmode="numeric" autocomplete="one-time-code" maxlength="20" required disabled></div>
  <button class="btn primary">Bestätigen</button>
  <p class="small" style="text-align:center;margin:14px 0 0"><a href="/login">Abbrechen</a></p>
  </div>"""))

FORGOT_PAGE = (AUTH_PAGE.replace("%%ACTION%%", "/auth/forgot").replace("%%NEXT%%", "/passwort-vergessen/gesendet").replace("%%BODY%%", """
  <p style="margin-top:0"><b>Passwort vergessen?</b></p>
  <p class="muted small">Gib deinen Benutzernamen oder deine E-Mail-Adresse ein. Du bekommst dann einen Link, mit dem du ein neues Passwort festlegst.</p>
  <div class="field"><label for="l">Benutzername oder E-Mail</label><input class="input" id="l" name="login" autocomplete="username" required autofocus></div>
  <button class="btn primary">Link schicken</button>
  <p class="small" style="text-align:center;margin:14px 0 0"><a href="/login">Zurück zur Anmeldung</a></p>"""))

FORGOT_SENT_PAGE = (AUTH_PAGE.replace("%%ACTION%%", "/").replace("%%NEXT%%", "/").replace("%%BODY%%", """
  <p style="margin-top:0"><b>Schau in dein Postfach</b></p>
  <p class="muted">Wenn es ein Konto mit diesen Angaben und einer hinterlegten E-Mail-Adresse gibt, haben wir gerade einen Link geschickt.
    Er gilt 60 Minuten. Schau auch im Spam-Ordner nach.</p>
  <p class="muted small">Keine Mail bekommen? Dann ist bei deinem Konto vermutlich keine E-Mail-Adresse hinterlegt. Bitte wende dich an den Vorstand bzw. Admin.</p>
  <p class="small" style="text-align:center;margin:14px 0 0"><a href="/login">Zurück zur Anmeldung</a></p>"""))

RESET_PAGE = (AUTH_PAGE.replace("%%ACTION%%", "/auth/reset").replace("%%NEXT%%", "/hub").replace("%%BODY%%", """
  <p style="margin-top:0">Hallo <b>%%NAME%%</b>, leg jetzt dein neues Passwort fest.</p>
  <p class="muted small">Dein Benutzername: <b>%%USER%%</b></p>
  <input type="hidden" name="token" value="%%TOKEN%%">
  <input type="text" name="username" value="%%USER%%" autocomplete="username" hidden>
  <div class="field"><label for="p">Neues Passwort (mind. 10 Zeichen)</label><input class="input" id="p" name="password" type="password" autocomplete="new-password" required autofocus></div>
  <div class="field"><label for="p2">Passwort wiederholen</label><input class="input" id="p2" name="password2" type="password" autocomplete="new-password" required></div>
  <button class="btn primary">Passwort speichern und anmelden</button>"""))

INVALID_RESET_PAGE = (AUTH_PAGE.replace("%%ACTION%%", "/").replace("%%NEXT%%", "/").replace("%%BODY%%", """
  <p>Dieser Link ist ungültig oder abgelaufen.</p>
  <p class="muted">Ein Link gilt 60 Minuten und nur einmal. <a href="/passwort-vergessen">Neuen Link anfordern</a></p>"""))

SETUP_PAGE = (AUTH_PAGE.replace("%%ACTION%%", "/auth/setup").replace("%%NEXT%%", "/login").replace("%%BODY%%", """
  <p class="muted" style="margin-top:0">Ersteinrichtung: Lege deinen Admin-Zugang an.</p>
  <div class="field"><label for="u">Benutzername</label><input class="input" id="u" name="username" autocomplete="username" required autofocus></div>
  <div class="field"><label for="p">Passwort (mind. 10 Zeichen)</label><input class="input" id="p" name="password" type="password" autocomplete="new-password" required></div>
  <div class="field"><label for="p2">Passwort wiederholen</label><input class="input" id="p2" name="password2" type="password" autocomplete="new-password" required></div>
  <button class="btn primary">Zugang anlegen</button>"""))


INVITE_COACH_ROLES = ("Trainer", "Co-Trainer", "Torwarttrainer", "Betreuer", "Teammanager", "Physio", "Zeugwart", "Jugendleitung",
                      "Social Media Betreuer")   # wie website.COACH_ROLES


def invite_profile(u):
    try:
        prof = json.loads(u["invite_profile"] or "{}")
    except (ValueError, TypeError, IndexError, KeyError):
        prof = {}
    return prof if isinstance(prof, dict) else {}


def invite_page(u, tok):
    """Einladungsseite: Benutzername, Passwort, persönliche Daten und, falls vorgegeben, die Kader-Angaben wie im Spielerbogen."""
    prof = invite_profile(u)
    kind = prof.get("kind") if prof.get("kind") in PLAYER_FORM_KINDS else ""
    team = prof.get("team") if prof.get("team") in TEAMS else MAIN_TEAM
    e = html_esc
    dn = (u["display_name"] or "").strip()
    first, _, last = dn.partition(" ") if dn and dn not in (u["username"], "Einladung offen") else ("", "", "")
    def field(name, label, value="", typ="text", req=False, extra="", hint=""):
        return (f'<div class="field"><label for="i_{name}">{label}{" *" if req else ""}</label>'
                f'<input class="input" id="i_{name}" name="{name}" type="{typ}" value="{e(value)}" {"required" if req else ""} {extra}>'
                f'{f"<div class=hint>{hint}</div>" if hint else ""}</div>')
    kader = ""
    if kind:
        teams = "".join(f'<option {"selected" if t == team else ""}>{e(t)}</option>' for t in TEAMS if not (kind == "Spieler" and t in YOUTH_TEAMS))
        if kind == "Spieler":
            pos = "".join(f"<option>{e(x)}</option>" for x in PLAYER_FORM_POSITIONS)
            spec = (f'<div class="row2">{field("number", "Rückennummer", extra="inputmode=numeric maxlength=3 pattern=[0-9]{1,3}")}'
                    f'<div class="field"><label for="i_position">Position</label><select class="input" id="i_position" name="position"><option value="">bitte wählen</option>{pos}</select></div></div>')
        else:
            roles = "".join(f'<option value="{e(x)}">' for x in INVITE_COACH_ROLES)
            spec = field("role", "Rolle", req=True, extra='list="i_roles" maxlength="60"') + f'<datalist id="i_roles">{roles}</datalist>'
        kader = f"""
  <h3 class="inv-h">Für Kader &amp; Trainer ({e(kind)})</h3>
  <div class="row2"><div class="field"><label for="i_team">Mannschaft</label><select class="input" id="i_team" name="team">{teams}</select></div>
    {field("nickname", "Spitzname", extra='maxlength="40"')}</div>
  {spec}
  <div class="row2">{field("instagram", "Instagram-Name", extra='maxlength="31" placeholder="ohne @"')}{field("since", "Dabei seit", extra='maxlength="20" placeholder="z. B. 2023"')}</div>
  <label class="check inv-consent"><input type="checkbox" name="consent" value="1"> Ich bin einverstanden, dass {"Foto, Name, Rückennummer, Position" if kind == "Spieler" else "Foto, Name, Rolle"} und Instagram-Name auf der Webseite und in den Social-Media-Kanälen des SV Amisia Wolthusen erscheinen. Freiwillig, jederzeit widerrufbar.</label>"""
    body = f"""
  <style>body{{align-items:flex-start;padding-top:24px}}.auth{{width:min(560px,100%)}}.row2{{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}}
  .inv-h{{font-size:15px;margin:18px 0 8px;padding-top:12px;border-top:1px solid #eee}}.inv-consent{{display:flex;gap:8px;align-items:flex-start;font-size:13px;margin:6px 0 10px}}
  .hint{{font-size:12px;color:#777;margin-top:3px}}@media(max-width:480px){{.row2{{grid-template-columns:1fr}}}}</style>
  <p style="margin-top:0">Willkommen im <b>Wolthusen Hub</b>! Bitte trag einmal deine Angaben ein und leg dein Passwort fest.</p>
  <input type="hidden" name="token" value="{e(tok)}">
  <h3 class="inv-h" style="border:0;padding:0;margin-top:6px">Zugang</h3>
  {field("username", "Benutzername", "" if prof.get("pick_name") else u["username"], req=True, extra='autocomplete="username" maxlength="40" pattern="[A-Za-z0-9._@-]{2,40}"', hint="2 bis 40 Zeichen: Buchstaben, Zahlen und . _ - @ (ohne Leerzeichen). Damit meldest du dich an.")}
  <div class="row2">{field("password", "Passwort (mind. 10 Zeichen)", typ="password", req=True, extra='autocomplete="new-password" minlength="10"')}
    {field("password2", "Passwort wiederholen", typ="password", req=True, extra='autocomplete="new-password"')}</div>
  <h3 class="inv-h">Über dich</h3>
  <div class="row2">{field("first_name", "Vorname", first, req=True, extra='maxlength="60" autocomplete="given-name"')}{field("last_name", "Nachname", last, req=True, extra='maxlength="60" autocomplete="family-name"')}</div>
  <div class="row2">{field("email", "E-Mail", u["email"] or "", "email", req=True, extra='maxlength="150" autocomplete="email"', hint="Für „Passwort vergessen“ und Benachrichtigungen.")}
    {field("phone", "Telefon", "", "tel", req=bool(kind), extra='maxlength="40" autocomplete="tel"', hint="Nur intern für die Team-Organisation.")}</div>
  {kader}
  <p class="muted small">Deine Angaben sieht nur der Verein im geschützten Mitgliederbereich. Mehr dazu in der <a href="/datenschutz" target="_blank">Datenschutzerklärung</a>.</p>
  <button class="btn primary">Speichern und loslegen</button>"""
    return AUTH_PAGE.replace("%%ACTION%%", "/auth/invite").replace("%%NEXT%%", "/hub#/profile").replace("%%BODY%%", body)


def invite_mail_text(name, link, days):
    return (f"Hallo{(' ' + name) if name else ''},\n\ndu bist zum Wolthusen Hub eingeladen, dem Mitgliederbereich des SV Amisia Wolthusen.\n\n"
            f"Über diesen Link legst du deinen Zugang an und trägst einmal deine Angaben ein:\n{link}\n\n"
            f"Der Link gilt {days} Tage und nur für dich. Bitte nicht weiterleiten.\n\nSportliche Grüße\nSV Amisia Wolthusen")


INVALID_INVITE_PAGE = (AUTH_PAGE.replace("%%ACTION%%", "/").replace("%%NEXT%%", "/").replace("%%BODY%%", """
  <p>Dieser Einladungslink ist ungültig oder abgelaufen.</p>
  <p class="muted">Bitte frag beim Vorstand bzw. Admin nach einem neuen Link. Wenn du schon ein Passwort hast: <a href="/login">zur Anmeldung</a></p>"""))

ORDER_INVALID_PAGE = (AUTH_PAGE.replace("%%ACTION%%", "/").replace("%%NEXT%%", "/").replace("%%BODY%%", """
  <p>Dieser Bestell-Link ist ungültig.</p>
  <p class="muted">Bitte frag beim Verein nach dem aktuellen Link.</p>"""))


def html_esc(t):
    return (str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;"))


NO_USER_PAGE = (AUTH_PAGE.replace("%%ACTION%%", "/").replace("%%NEXT%%", "/").replace("%%BODY%%", """
  <p>Es ist noch kein Benutzer angelegt.</p>
  <p class="muted">Bitte in der Datei <b>.env</b> auf dem Server <b>TMH_ADMIN_USER</b> und <b>TMH_ADMIN_PASSWORD</b>
  eintragen und den Hub neu starten (<code>docker compose up -d</code>).</p>"""))


def cleanup_loop():
    while True:
        try:
            with db() as conn:
                conn.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
                conn.execute("DELETE FROM audit_log WHERE time < ?",
                             ((datetime.now() - timedelta(days=AUDIT_KEEP_DAYS)).isoformat(timespec="seconds"),))
            for f in DATA.glob("_umzug_*"):   # nicht abgeholte Umzugsdateien nach einer Stunde löschen
                if time.time() - f.stat().st_mtime > 3600:
                    f.unlink(missing_ok=True)
        except Exception:  # noqa
            pass
        threading.Event().wait(6 * 3600)


def cli():
    """Kommandozeile: python server.py adduser NAME [admin] | passwd NAME | users"""
    import getpass
    init_db()
    cmd = sys.argv[1]
    if cmd == "users":
        with db() as conn:
            for r in conn.execute("SELECT username, is_admin, active, last_login FROM users ORDER BY username"):
                print(f"{r['username']:<24} {'Admin' if r['is_admin'] else '':<6} {'' if r['active'] else 'deaktiviert':<12} "
                      f"zuletzt angemeldet: {r['last_login'] or 'nie'}")
        return
    if len(sys.argv) < 3:
        print(cli.__doc__)
        return
    name = sys.argv[2]
    pw = getpass.getpass("Neues Passwort: ")
    if pw != getpass.getpass("Wiederholen: "):
        print("Die Passwörter stimmen nicht überein.")
        sys.exit(1)
    if cmd == "adduser":
        create_user(name, pw, is_admin="admin" in sys.argv[3:])
        print("Benutzer angelegt.")
    elif cmd == "passwd":
        prob = pw_problem(pw)
        if prob:
            print(prob)
            sys.exit(1)
        with db() as conn:
            cur = conn.execute("UPDATE users SET pw_hash=?, invite_hash=NULL, active=1 WHERE username=?", (hash_pw(pw), name))
            conn.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE username=?)", (name,))
        print("Passwort geändert." if cur.rowcount else "Benutzer nicht gefunden.")


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("adduser", "passwd", "users"):
        return cli()
    init_db()
    bootstrap_admin()
    try:
        httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError:
        url = f"http://127.0.0.1:{PORT}/"
        running = ""
        try:
            with urllib.request.urlopen(url + "healthz", timeout=3) as r:
                running = json.loads(r.read().decode("utf-8")).get("version", "")
        except Exception:  # noqa
            pass
        if running == VERSION and not SERVER_MODE:
            print(f"{APP_NAME} läuft bereits. Öffne {url}")
            webbrowser.open(url)
        else:
            print("=" * 56)
            print(f"  Port {PORT} ist belegt" + (f" ({APP_NAME} {running})" if running else "") + ".")
            print("  Bitte die andere Instanz beenden und erneut starten.")
            print("=" * 56)
            sys.exit(1)
        return
    httpd.daemon_threads = True
    url = f"http://{'127.0.0.1' if HOST in ('0.0.0.0', '::') else HOST}:{PORT}/"
    print("=" * 56)
    print(f"  {APP_NAME} " + VERSION + ("  (Serverbetrieb)" if SERVER_MODE else ""))
    print(f"  Läuft unter {url}")
    print(f"  Daten: {DATA}")
    if user_count() == 0:
        print("  Noch kein Benutzer angelegt." + ("" if SERVER_MODE else " Ersteinrichtung im Browser."))
    if not SERVER_MODE:
        print("  Zum Beenden dieses Fenster schließen (oder Strg+C).")
    print("=" * 56, flush=True)
    for fn in (backup_loop, cleanup_loop, social_loop, notify_loop, pf_poll_loop):
        threading.Thread(target=fn, daemon=True).start()
    if not SERVER_MODE and "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
