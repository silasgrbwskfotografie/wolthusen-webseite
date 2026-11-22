# Wolthusen Hub

Webseite und Vereinsverwaltung des **SV Amisia Wolthusen e.V.** (Sportverein in Emden-Wolthusen, seit 1929: Fußball von der G-Jugend bis zu den Alten Herren,
American Football mit den Emden Tigers, Turnen und Gymnastik, Vereinssaal). Grundlage ist der Emden Tigers Hub 5.16 (eigenes Repository), ohne Livescore/Highlight Desk.
Web-App für Medien, Verein, Mitglieder und Finanzen mit Konten, Gruppen und Rechten, dazu die öffentliche Vereinswebseite.
Betreiber und Hauptnutzer: Silas (Admin). Sprache der Oberfläche und Texte: **Deutsch**.

## Aufbau

- `server.py`: der komplette Server in **Python 3 Standardbibliothek** (keine pip-Pakete). `http.server` + `sqlite3`.
  - `TABLES`: Schema der Fachtabellen. Neue Spalten hier eintragen, `init_db()` ergänzt sie beim Start automatisch (Migration per `ALTER TABLE`).
  - Konten/Rechte liegen bewusst **nicht** in `TABLES` (nicht über die generische API erreichbar): `users`, `sessions`, `groups`, `group_perms`, `user_groups`, `user_perms`.
  - Generische REST-API: `GET/POST /api/<tabelle>`, `GET/PUT/DELETE /api/<tabelle>/<id>`.
  - Spezielle Endpunkte: `/api/admin/info` (Seite Admin `#/admin`, nur Admins: `admin_info`, Versionsprüfung `latest_version` gegen `UPDATE_SOURCE`, Pfade `HOST_DIR`/`BEHIND_PROXY`/`SSH_USER`, keine Geheimnisse ausgeben), `/api/me`, `/api/profile`, `/api/admin/users|groups`, `/api/dashboard`, `/api/upload`, `/api/backup`, `/api/restore`, `/api/backups`, `/api/settings`, `/healthz`.
  - Anmeldung: `/login`, `/setup` (nur lokal ohne Benutzer), `/invite/<token>`, `POST /auth/login|logout|setup|invite`.
- **Öffentliche Webseite unter `/`**, Hub unter **`/hub`** (nur mit Login). `website.py` baut die Seiten serverseitig aus den öffentlichen Daten
  (`public_info`, `public_games`, `public_team`, `public_trainings`, `public_sponsors`, `public_articles` in server.py), ohne Datenbankzugriff.
  Feste Inhalte in `seiten/*.html` (erste Zeile JSON mit `title`, `path`, `nav`, `description`; `website.seiten()` liest sie bei Änderung neu, Adresse = `path`, muss in `website.PAGES` stehen).
  Platzhalter darin ersetzt `website.fill`: `{{SHIELD}}` (Wappen-Umriss), `{{BILD:slot[:hero-img]}}` (`picture`, Slots aus `IMAGE_SLOTS`), `{{HERO_TEXT}}`, `{{UEBER_UNS}}`, `{{DYNAMISCH}}` (Startseiten-Abschnitte `START_SECTIONS`),
  `{{MANNSCHAFTEN}}`/`{{JUGEND}}` (`team_cards` mit Trainingszeiten und Trainern), `{{SQUADS}}` (`FUSSBALL_DE`), `{{TRAINING:Gruppe}}`, `{{PARTNER}}`, `{{PARTNER_TEXT}}`.
  Design: Vereinsviolett #3D2F96, Nachtviolett #15122B, Weiß; Wappen `web/assets/logo.webp` (Original), `web/assets/wappen.png` (256 px, Kopf, Spielkarten); Menü mit Untermenüs Sportarten und Verein fest in `website.NAV`.
  `web/assets/`: `site.css` (steht über `site_css()` verkleinert als `<style>` im Kopf, keine Datei-Anfrage), `site.js` (Untermenüs, Einblenden, Dauerkarten-Formular),
  Schriften (Anton, Karla, OFL, lokal, als WOFF2, vorgeladen über `FONT_PRELOAD`), Fotos als WebP in 640/960/1280/1920 mit `bilder.json` (Alt-Texte), PDFs unter `downloads/`. Seitentexte: Einstellungen `site_*`.
  Öffentliche Schnittstelle `/api/public/<info|spielplan|team|sponsoren>`: nur lesen, jede Antwort Feld für Feld gebaut (Whitelist).
  Neue öffentliche Felder nur dort ergänzen, nie Datenbankzeilen durchreichen. Kontaktformular `POST /kontakt` -> Tabelle `contact_requests`.
  Zusatzpunkte im Menü (Dauerkarte, Fanshop): Hub > Webseite > Menü, Einstellung `web_nav` (`web_nav()`, nur `NAV_BUILTIN`), `public_nav()` -> `website.nav_html` über `_ctx.nav`; Social-Media-Links im Footer aus `site_social_*`
  (`social_url`: nur https und die passende Plattform, `SOCIAL_HOSTS`), Symbole als eigenes SVG (`website.SOCIAL_ICONS`), nichts wird von den Plattformen geladen.
  Instagram-Raster: `insta_refresh` holt die neuesten Beiträge über die Meta-Verbindung (alle 30 Minuten, im Hintergrund), speichert die Bilder in `data/instagram`,
  ausgeliefert unter `/web/insta/<datei>`. Ausblenden per Link in `site_insta_hide` (`insta_codes`). Nur Bild, Permalink (nur instagram.com) und erste Caption-Zeile als Alt-Text, Besucher laden nichts von Meta.
  Dauerkarte online (im Code noch `supporter_*`/`card_*`): `/supporter-karte` (Seite) und `POST /supporter-karte` (`public_card_order`): nur wenn `site_card_order_open` = "1",
  nur feste Felder, Anzahl 1 bis `CARD_ORDER_MAX` (10, in server.py und website.py gleich), Name pro Karte, Lieferung Post oder Einschreiben (`CARD_SHIPS`, mit Anschrift, `card_shipping`/`card_shipping_registered` einmal pro Bestellung) oder Einlass,
  Stornieren bis Zahlungseingang: Link in der Bestätigungsmail (`public_card_cancel`, `card_order_cancel`) oder im Hub `POST /api/cards/orders/<id>/cancel` (Finanzen 2);
  löscht unbezahlte Karten, Bestätigung an den Kunden. Freiwilliges Angebot (`site_card_cancel_text`), nie „Widerrufsrecht“ nennen (§ 312g Abs. 2 Nr. 9 BGB).
  Kartennummern: `assign_card_numbers` (bezahlt und ohne Nummer, fortlaufend 00001, Zähler `card_counter`), aufgerufen in `card_order_paid` und `api_table` für `supporter_cards`.
  Sponsoringverträge: Sponsoren > Verträge (`sponsorContracts` in `static/pages/08-gegner-sponsoren-fanshop.js`), `/api/sponsor-contracts` (Verein 1 + Finanzen 1 lesen, Verein 2 erstellen/löschen),
  Tabelle `sponsor_contracts` (nicht in `TABLES`), Prüfung `contract_clean`, PDF `sponsor_contract_pdf` (mehrseitig über `pdf_render`), Datei in `data/media` und in `sponsors.files`. Vorlage, keine Rechtsberatung.
  Rechnung zum Vertrag: `POST /api/sponsor-contracts/<id>/invoice` (Finanzen 2), Tabelle `sponsor_invoices` (nicht in `TABLES`, nicht löschbar), Nummer `invoice_next`, Beträge `sponsor_invoice_sums` (`VAT_RATE`), PDF `sponsor_invoice_pdf`, Steuernummer `inv_tax_no` Pflicht.
  Fanbrief `GET /api/cards/orders/<id>/letter.pdf` (Finanzen 1, `card_letter_pdf`, Text `card_letter_text`, Anschrift DIN 5008 Form B). PDFs über `PdfPage` (mehrere Seiten `pdf_render`), immer auf dem Briefpapier `letterhead` (Logo `web/assets/brief/logo.png` über `letter_logo`, Texte `LETTER`, überschreibbar mit `letter_*`) und bei Briefen mit Anschrift `letter_address` (Rücksendezeile, DIN 5008 Form B).
  `POST /api/cards/orders/<id>/shipped` (Finanzen 2, `card_order_shipped`): Versandbestätigung an den Kunden, beim Einschreiben Pflicht-Sendungsnummer `tracking_no`,
  verstecktes Feld, Begrenzung pro IP; legt eine Bestellung `card_orders` (Bestellnummer, Summe nur vom Server) und je Karte `supporter_cards` mit `source='Online'`, `paid=0`, `order_id` an.
  Bestätigungsmail `card_order_mail` mit Überweisungsdaten (`inv_*`, nie öffentlich, `/api/settings` nur mit Finanz-Leserecht). Schalter und Einstellungen `/api/cards/online` (Finanzen 2, `CARD_SETTING_KEYS`).
  `POST /api/cards/orders/<id>/paid` (Finanzen 2): Karten bezahlt, Rechnungsnummer `invoice_next` (fortlaufend je Jahr), PDF `invoice_pdf` (eigener PDF-Bau, Helvetica, cp1252) in `data/rechnungen`,
  Mail mit Anhang (`send_mail(..., attachments=)`); `.../invoice` erneut senden, `GET .../invoice.pdf` (Finanzen 1, erzeugt fehlende Datei neu, Rechnungsdatum = `paid_on`).
  Google: `layout` setzt canonical, `org_ld` (SportsOrganization) auf Start und Spielplan, `/sitemap.xml` (mit allen Mannschaftsseiten) und `/robots.txt`
  ohne Sitzung; absolute Adressen aus `SITE_URL` (sonst Host-Header über `base_url`). Neue öffentliche Seiten auch in `website.SITEMAP_PAGES` eintragen
  (Hub > Webseite > Sitemap: an/aus und Priorität je Eintrag, Einstellung `web_sitemap` über `web_sitemap()`, nicht öffentlich, PUT `sitemap` an `/api/website`).
  Suchmaschinen: `layout` setzt robots, Open Graph (absolute Bildadresse), Favicon `/favicon.ico`; Beschreibungen `site_seo_*` über `seo_desc` (`SEO_DESC`),
  Bestätigung `site_verify_google`/`site_verify_bing` nur auf der Startseite (`verify_tags`, nur Code-Zeichen), eigene canonical über `layout(..., canonical=)`, `noindex=True` für Fehlerseiten.
  Link-Seite `/links` (Instagram-Bio, `page_links`): Knöpfe aus Einstellung `web_links` (`web_links()`, Standard `LINKS_DEFAULT`, Ziele nur über `link_url_ok`: https oder eigene Seite),
  Hub > Webseite > Link-Seite (PUT `links`/`links_reset` an `/api/website`), nicht in `PAGES` (noindex), Menü und Sitemap, nirgends verlinkt.
  Newsletter: Seite `/newsletter` (`page_newsletter`, Feld im Fuß von `layout` und Kasten auf Kontakt, beide nur GET mit E-Mail), `POST /newsletter` (`public_newsletter`: Themen aus `nl_public_groups`,
  Einwilligung `website.NL_CONSENT`, Double-Opt-In, Token nur als Hash `confirm_hash`, `NL_CONFIRM_HOURS`, gleiche Antwort für bekannte Adressen, Begrenzung pro IP und Adresse),
  Bestätigen und Abmelden nur per POST (`/newsletter/bestaetigen/<token>`, `/newsletter/abmelden/<id>-<sig>` über `nl_token`/`nl_key`, auch Ein-Klick nach RFC 8058), in `MAINT_OPEN_PAGES`.
  Tabellen `nl_subscribers`, `nl_issues` (nicht in `TABLES`, `/api/newsletter`, Bereich Medien), Gruppen `nl_groups` (generische Tabelle). Versand `nl_send_issue` im Hintergrund, kein Tracking.
  Aufräumen in `backup_loop`: unbestätigt nach 30 Tagen, abgemeldet nach drei Jahren (so in der Datenschutzerklärung).
  Livestream: `games.stream_url`, öffentlich nur als geprüfter https-Link (`public_games` -> `stream`).
  Livescore und Highlight Desk gibt es im Wolthusen Hub nicht (bewusst entfernt). Ergebnisse trägt man im Spielplan ein.
  News: Tabelle `articles` (Bereich Medien, Hub-Seite `#/news`), öffentlich nur über `public_articles` (Status „Veröffentlicht“, Datum erreicht, ohne `notes`).
  Seiten `/news` (`page_news`) und `/news/<id>-<titel>` (`page_article`, falsche Schreibweise per 301 auf `article_slug`), die 3 neuesten im Startseiten-Abschnitt `news`.
  Standard ist `articles.format` = „Blöcke“: JSON aus dem Block-Editor (`editArticle` in `static/pages/06-news.js`, Import fertiger HTML-Artikel per `htmlToArticle`),
  der Server lässt nur `ARTICLE_BLOCKS` mit ihren Feldern durch (`article_blocks`: Bilder nur aus der Mediathek, signiert; Knopf-Links geprüft), die Webseite baut sie mit `render_blocks`.
  Unter jedem Artikel `article_footer`: Probetraining-Kasten (`site_news_cta_text`) und Fotograf (`photo_by`, Link nur über `photo_link`: https oder @instagram).
  Text als Absätze über `paragraphs()`; mit `articles.format` = „HTML“ nur über `clean_html()` (Whitelist: p, h2 bis h4, strong, em, u, Listen, a mit geprüftem href, blockquote, br, hr; keine Attribute, Skripte, Bilder, Einbettungen). Neue Startseiten-Abschnitte setzt `web_layout` an ihren Standardplatz.
  Mannschaften: Tabelle `teams` (Hub > Verein > Mannschaften, `static/pages/22-mannschaften.js`, Kategorie = Sportart `SPORTS`, `youth`, `page`, Texte, Links),
  `load_teams` setzt `TEAMS` (aktive), `YOUTH_TEAMS` (auch inaktive), `MAIN_TEAM` und über `website.set_teams` Seiten, Menü (`nav_items`), Bild-Slots `team-<id>` und Sitemap; im Hub `setTeams` aus `/api/me`.
  Zuordnung über den Namen in `TEAM_REF_TABLES` (Umbenennen zieht mit, Löschen nur ohne Einträge), Titelbild über `/api/team-image/<id>` (Verein 2). Vorbelegung einmalig (`teams_seeded`). Test `tests/mannschaften.py`.
  Spieler der Jugendmannschaften (Minderjährige) gibt `public_team` nie aus, nur deren Trainer und Betreuer; nie über Spielerbogen oder Einladung in den Kader.
  Positionen Tor/Abwehr/Mittelfeld/Sturm (`POSITIONS`, `PLAYER_FORM_POSITIONS`), Rollen `COACH_ROLES` wie `STAFF_ROLES` in `01-grundlagen.js` und `INVITE_COACH_ROLES`.
  Trainingszeiten: Tabelle `trainings` (Bereich Verein, Hub `#/trainings`), öffentlich nur über `public_trainings` (ohne Notizen); `init_db` belegt die Turngruppen einmalig vor (`trainings_seeded`).
  Belegung Saal und Platz: Tabelle `bookings` (Bereich Verein, Hub `#/bookings`), nur intern.
  Seiten: Start, Fußball, `/mannschaft/<slug>` (`page_team`: Training, Trainer, Kader nach Position nur Herren, Spiele, Ergebnisse, fussball.de), Spielplan (alle Mannschaften),
  American Football, Turnen & Gymnastik, Saal, Partner (Sponsoren aus dem Hub), Mitglied werden, News, Kontakt, Newsletter, Dauerkarte, Impressum, Datenschutz.
  Kontaktformular mit Anliegen `CONTACT_TOPICS` (server.py und website.py gleich halten), Vorauswahl per `/kontakt?anliegen=frage|mitglied|herren|jugend|turnen|saal|sponsoring|karte` (`karte` = Anliegen „Dauerkarte“, `CARD_TOPIC`, nur bei `site_card_order_open` = "1" im Formular).
  Standardtexte `site_*` in `DEFAULT_SETTINGS`; neue Texte für bestehende Server: `SITE_TEXTS_VERSION` erhöhen (füllt nur leere Felder).
  Webseite im Hub (`#/website`, Bereich Medien: Lesen 1, Ändern 2): `/api/website` (GET Übersicht mit Checkliste, PUT `texts` nur `site_*` und `layout`),
  `/api/website/image/<slot>` (POST WebP-Dateien vom Browser, nur `website.IMAGE_SLOTS`, Prüfung auf RIFF/WEBP, PUT Alt-Text, DELETE = Standardbild).
  Eigene Bilder in `data/site`, ausgeliefert unter `/web/site/<datei>.webp`; Beschreibung und Aufbau in den Einstellungen `web_images`, `web_layout` (nicht öffentlich).
  Abschnitte der Startseite: `website.START_SECTIONS`. Öffentliche Seiten senden `X-Frame-Options: SAMEORIGIN` (Vorschau im Hub), alles andere `DENY`.
  Fehlende Inhalte als `placeholder()` (gelb markiert) und in `PLATZHALTER.md` eintragen, nie erfinden.
- `static/`: Frontend des Hubs ohne Build-Schritt (Vanilla JS, eine Seite mit Hash-Router, ausgeliefert unter `/hub`).
  - `app.js`: API-Helfer, Router, Formular-Generator (`editRecord`, `fieldHtml`), Rechte-Hilfen (`can`, `PAGE_AREA`, `applyPermissions`).
  - `pages/*.js` (seit 4.77, früher eine Datei `pages.js`): die Seiten nach Bereichen, `01-grundlagen.js` mit Feld-Definitionen `F.<tabelle>` und Hilfen, `99-start.js` startet den Hub.
    Alle Dateien teilen sich einen gemeinsamen Bereich, Reihenfolge nur über die `<script>`-Liste in `index.html`. Neue Seite = neue Datei vor `99-start.js` und dort eintragen.
  - `captions.js`: Caption-Vorschläge aus den Vereinsdaten.
  - `style.css`, `logo.png` (Vereinswappen, **nicht verändern**, Icons aus `web/assets/logo.webp` gerendert), `icon.png`. Farben im Hub nur über die Variablen oben in `style.css` (hell in `:root`, dunkel in `[data-theme="dark"]` und `prefers-color-scheme`), nie feste Hex-Werte für Flächen oder Text; Design „schlicht“ (seit 1.3, Abschnitt am Ende von `style.css`): keine Schatten, kein Schimmer, kein Wasserzeichen, Systemschrift, Violett nur als Akzent; Umschalter `themeSet` (localStorage `tmh_theme`, gesetzt vor dem ersten Bild in `index.html`), Symbole im Menü über `PAGE_ICONS`/`TAB_ICONS` (`decorateNav`).
- Betrieb: `Dockerfile` (kopiert `server.py`, `website.py`, `static/`, `web/`, `seiten/`), `docker-compose.yml` (Hub + Caddy mit HTTPS, Log-Begrenzung), `Caddyfile`, `.env` (nicht im Repo), `setup.sh` (Ersteinrichtung), `update.sh` (Update per Git),
  `server-haerten.sh` (frischer VPS: Firewall, fail2ban, Sicherheitsupdates, SSH nur Schlüssel), Fahrplan `UMZUG-VPS.md`.
  VPS (Domain aus `DOMAIN` in der `.env`, bisher amisia-stern.de): zentraler Proxy `/opt/docker/proxy` (Vorlagen `deploy/proxy/`, Caddy einziger Container mit 80/443, Netzwerk `proxy`),
  Hub in `/opt/docker/apps/wolthusen-hub` mit `COMPOSE_FILE=docker-compose.proxy.yml` (`setup.sh --proxy`), Anleitung `deploy/DEPLOY.md`. Kann neben dem Tigers Hub auf demselben VPS laufen.
  Änderungen am Hub-Caddyfile (Robots, Größen) auch in `deploy/proxy/Caddyfile` nachziehen.
  Caddy: `X-Robots-Tag noindex` nur für Hub und interne Pfade (`@intern`), die Webseite bleibt indexierbar; `REDIRECT_DOMAINS` (Leerzeichen getrennt, nie leer setzen) leitet auf `DOMAIN` um.
  Serverumzug nimmt `data/media` und `MIGRATE_DIRS` (`data/site`, `data/rechnungen`) mit; neue Datenordner dort eintragen.
  Update-Manager (Admin > Updates, `adminUpdates`, `/api/admin/updates`, `updater_state`): Hub schreibt nur ein Wort aus `UPD_ACTIONS` nach `data/updater/request`,
  der Helfer `deploy/updater/wolthusen-updater.py` (root, systemd path und timer, `install.sh`) führt nur feste Befehle aus und schreibt `status.json`/`last.log` atomar (keine Links folgen).
  Auslösen nur Admins mit 2FA und Passwort (außer „Jetzt prüfen“), jede Aktion im `audit_log`.
- Daten zur Laufzeit in `data/` (nicht im Repo): `wolthusen.db`, `media/`, `backups/`.

## Rechte-Modell

- Bereiche: `medien`, `verein`, `mitglieder`, `finanzen`, `wartung` (`AREAS` in server.py, `AREA_SHORT`/`PAGE_AREA` im Frontend).
- Wartungsmodus (`#/wartung`, `/api/maintenance`, Einstellungen `maint_*` nur dort, Bild-Slot `website.MAINT_SLOT` über `site_image`, nicht unter Webseite > Bilder):
  Bereich `wartung` Lesen = Webseite trotz Wartung sehen (angemeldet, `maint_bar`), Bearbeiten = schalten. Gruppe „Wartung“ per Migration.
  `send_site` zeigt Besuchern `page_maintenance` mit 503, außer `MAINT_OPEN_PAGES`; `POST /kontakt` und `/supporter-karte` nehmen nichts an (`maint_blocks`).
  `wartung` zählt nicht für `any_read`/`any_write` (kein Zugriff auf Nachschlage-Tabellen).
- Der Seitenbaukasten aus 4.73 ist in 4.74 wieder entfernt: die Tabelle `site_pages` und die Einstellung `web_nav` bleiben auf Servern mit 4.73 ungenutzt liegen (nur additive Änderungen).
- Heimspieltag (Bereich `spieltag`, Hub `#/spieltag`, `static/pages/20-spieltag.js`): Tabellen `gd_shifts`, `gd_signups`, `gd_checks` (generische API), Übersicht, Vorlagen (`gd_roles`, `gd_checklist`),
  Link und Selbst-Eintragen über `/api/gameday` (`api_gameday`); Link-Tabelle `gd_links` (nicht in `TABLES`). Öffentlich `/helfer/<token>` (`gd_public`, `public_helpers`, `website.page_helpers`):
  nur offene Links und kommende Spiele, nur Vornamen sichtbar, nur Name und Telefon, nur freie Plätze, verstecktes Feld und Begrenzung pro IP, noindex, nicht in Sitemap. Push am Vortag ab 17 Uhr (`gd_reminders` in `notify_loop`, einmal pro Eintragung über `notify_sent`).
- Die Teamfunktionen (Reiter Team > Spieler, Bereich `spieler`, `/api/squad`, Kalender-Abo) gibt es seit 4.22 nicht mehr: `init_db` löscht alte Rechte `spieler`, die Tabellen `sq_*` und `users.cal_hash` bleiben ungenutzt liegen (nur additive Änderungen).
- Stufen: 0 = kein Zugriff, 1 = Lesen, 2 = Bearbeiten. Admin (`users.is_admin`) darf alles.
- Effektives Recht = Ausnahme der Person (`user_perms`) falls gesetzt, sonst Maximum der Gruppen (`effective_perms`).
- `TABLE_AREA` ordnet jede Tabelle einem Bereich zu. `SHARED_READ`: Nachschlage-Tabellen, lesbar für alle mit irgendeinem Leserecht.
- `TABLE_AREAS_ANY`: Tabellen, die mehrere Bereiche verwalten dürfen (Teamkleidung: Verein, Finanzen, Medien). Im Frontend `'verein|finanzen|medien'` in `PAGE_AREA`/`data-area`, `can()` versteht `|`, CSS-Klasse `.aw`.
- `FINANCE_FIELDS`: Felder, die nur mit Finanz-Leserecht ausgeliefert werden (z. B. `sponsors.amount`).
- **Der Server prüft jede Anfrage.** Das Frontend blendet nur aus (CSS: `.pp` braucht Medien-Schreibrecht, `.vw` Verein-Schreibrecht, `body[data-ro]` = Lesemodus, `.keep` bleibt im Lesemodus sichtbar).
- Menü: Oberreiter `.nav-group` einklappbar (`initNavGroups`, localStorage `tmh_nav_fold`), Zahlen an Unterreitern `.nav-count[data-count]` aus `/api/navcounts` (nur mit passendem Recht), Summe am Oberreiter (`updateNavGroupCounts`).
- Notizen (`admin_notes`, `#/notes`, nur Admins): verschlüsselte Notizen nur im Browser (`NoteCrypto`, PBKDF2 600000 + AES-GCM, `body` = JSON), Passwort nie zum Server.
- Nur-Admin-Tabellen (`ADMIN_TABLES`, z. B. `hub_plans` für Admin > Planung, `admin_notes`): `TABLE_AREA` = `admin`, die Route lässt nur `is_admin` durch, Gruppenrechte zählen nicht.
- Neue Tabelle: in `TABLES` und `TABLE_AREA` eintragen, Seite in `static/pages/`, Menüpunkt in `index.html` mit `data-area`, Eintrag in `PAGE_AREA`.

## Sicherheit (nicht aufweichen)

- Ohne Sitzung erreichbar: die Webseite (`/` und alle `website.PAGES`, `/mannschaft/<slug>`, `/news/<artikel>`, `/supporter-karte` (auch POST), `/supporter-karte/storno/<token>` (GET zeigt, POST storniert, nur bis Zahlungseingang, Token nur als Hash `cancel_hash`), `/helfer/<token>` (Heimspieltag, GET und POST),
  `/spielerbogen` (`public_player_form`: nur wenn `player_form_open` und Passwort gesetzt; Passwort nur als Hash in `secrets.player_form_pw`, danach signiertes Cookie `tmh_pf` für 2 Stunden;
  Eingänge in `player_signups`, lesbar nur mit Verein 2 (`WRITE_ONLY_TABLES`), in den Kader nur über `/api/player-form/signups/<id>/apply`; `players.email`/`phone` nur mit Verein 2 (`WRITE_FIELDS`)), `/impressum`, `/datenschutz`, alte Adressen (`/herren`, `/jugend`, `/sponsoren`, `/index.html` ...) als 301 in `website.REDIRECTS`, `/web/assets/...`, `/web/insta/...`, `/web/site/...`, `/signatur/<bild>.png` (Bilder der Mail-Signatur), `/sitemap.xml`, `/robots.txt`, `/api/public/...`, `POST /kontakt`),
  `/login`, `/setup`, `/invite`, `/passwort-vergessen`, `/passwort-neu`, `/healthz`, `/bestellen`, `/teilen`, `/manifest.webmanifest`, `/sw.js`, `style.css`, `logo.png`, `icon.png`, `icon-192.png`, `icon-512.png`.
  Alles unter `/hub`, `/static`, `/media` und `/api` (außer `/api/public`) braucht eine Sitzung.
- Webseite: keine externen Schriften, Skripte, Tracker oder Einbettungen (ohne Ausnahme).
  Impressum und Datenschutzerklärung sind eigene Texte (`site_impressum`, `site_datenschutz`, Vorlagen `LEGAL_IMPRESSUM`/`LEGAL_DATENSCHUTZ` in server.py,
  Darstellung `legal_html` in website.py ohne HTML aus dem Hub). Neue Datenverarbeitung (Formular, Dienst, Cookie) immer auch in der Datenschutzerklärung ergänzen.
  Bei jeder Änderung von `LEGAL_DATENSCHUTZ` den SHA-256 der alten Fassung in `OLD_LEGAL_DATENSCHUTZ` eintragen: unveränderte alte Vorlagen werden beim Start ersetzt.
  Barrierefreiheit: kleine violette Schrift auf Nachtviolett nur mit `--violet-light`, Fokusrahmen `:focus-visible`, Sprunglink `.skip` auf `main#inhalt`.
  Spielerfotos nur mit `players.consent`. Domain/Basisadresse nur über `DOMAIN` in der `.env` (daraus `SITE_URL`).
- `sw.js` speichert bewusst nichts zwischen (keine Vereinsdaten offline auf dem Handy).
- Änderungsprotokoll `audit_log` (nicht in `TABLES`, nur `/api/admin/log`, nicht im Backup-Download). `api_table` schreibt bei jedem Anlegen, Ändern, Löschen mit; neue Sonderaktionen mit `audit(...)` ergänzen.
- Serverumzug (`/api/migrate`, nur Admins): Komplett-Export inkl. Konten, `secrets` und Protokoll, ohne Sitzungen, verschlüsselt mit Passwort
  (scrypt, SHAKE-256-Schlüsselstrom, HMAC-SHA256, erst prüfen, dann entschlüsseln). Import ersetzt alles. Neue Tabellen landen automatisch mit drin.
- E-Mail: SMTP-Zugang in `secrets`, Passwort nie über die API. `notify(kind, ...)` schickt nur an Abonnenten mit passendem Leserecht (`NOTIFY_KINDS`), jede Mail einzeln.
- `/teilen/<sig>/<datei>`: einzelne Bilder aus `data/media` für Instagram (Meta holt Bilder selbst ab). Nur mit HMAC-Signatur (`share_sig`, Schlüssel `share_key` in `secrets`), nur Bildendungen (`SHARE_EXT`).
- Auto-Posting: Seiten-Token und Schlüssel in der Tabelle `secrets` (nicht in `TABLES`, nicht über die API lesbar, aus dem Backup-Download entfernt, beim Restore behalten). Verbindung einrichten nur Admins (`/api/social/connection`).
  `social_loop` postet nur freigegebene Posts (`auto_publish`) und Story-Regeln, markiert vorher `publish_state='läuft'` (nie doppelt). `SERVER_FIELDS` setzt nur der Server.
- `/bestellen/<token>` (Teamkleidung, `public_order` in server.py) ist bewusst ohne Login erreichbar, aber nur mit dem geheimen Token des Artikels.
  Liefert nur Artikel-Infos, Bestellfelder und die öffentliche Liste (ohne interne Felder, ohne `paid`, ohne Notizen) und nimmt geprüfte Bestellungen an
  (nur definierte Felder, Längen- und Auswahlprüfung, Bestellschluss, Rate-Limit pro IP). Das Token vergibt nur der Server (`/api/apparel/<id>/new-link`).
- Schreibende Anfragen brauchen den Header `X-TMH: 1` (CSRF-Schutz). `api()` in app.js setzt ihn.
- Passwörter: scrypt. Sitzungen: Token-Hash in `sessions`, Cookie HttpOnly, SameSite=Lax, Secure auf dem Server.
- Passwort vergessen (`/auth/forgot`, `/auth/reset`): immer dieselbe Antwort (keine Auskunft, ob es ein Konto gibt), Link 60 Minuten und einmal gültig,
  nur `reset_hash` gespeichert, Begrenzung pro IP und Konto, nach dem Setzen alle Sitzungen beendet und Info-Mail. Link-Adresse aus `hub_url`.
- Zwei-Faktor-Anmeldung (TOTP, RFC 6238, nur Standardbibliothek): Tabelle `user_2fa` (nicht in `TABLES`, in `AUTH_TABLES`, nie über die API, aus dem Backup-Download gelöscht, beim Umzug dabei).
  Anmeldung zweistufig: `/auth/login` liefert bei 2FA nur ein kurzes Ticket (`TWOFA_TICKETS`, im Speicher, 5 Minuten), Sitzung erst nach `/auth/login2` mit Code oder Wiederherstellungscode
  (nur SHA-256-Hashes, einmal gültig, `last_step` verhindert doppelte Codes). Eigenes Konto: `/api/me/2fa` (setup/enable/recovery/disable mit Passwort).
  QR-Code zum Einrichten nur im Browser über `static/qrcode.js` (`qrSvg`, Byte-Modus, Fehlerkorrektur M, Version 1 bis 10), nie über einen fremden Dienst.
  Pflicht über `/api/admin/2fa-policy` (`twofa_admins`, `twofa_finance`, nicht über `/api/settings`, nur mit eigener 2FA einschaltbar); `must_2fa` sperrt alles außer Profil.
  Admin: `/api/admin/users/<id>/2fa-reset` und `/unlock`, beides im `audit_log`. „Passwort vergessen“ und Einladung melden mit 2FA nie direkt an.
- Einladung (`POST /api/admin/users` mit `groups`, `overrides`, `kader` {kind, team}, `send_mail`): ohne Benutzername wählt ihn die Person (`invite_profile` JSON in `users`, `pick_name`). Seite `invite_page`, `/auth/invite` prüft alles, setzt Name/E-Mail/`users.phone` und legt bei Kader einen Eingang `player_signups` (`source='Einladung'`, `user_id`) an; `player_signup_apply` verknüpft dann `users.player_id`. Spieler der Jugendmannschaften nie per Einladung.
- Postfach (`/api/postfach`, Bereich `postfach`, wie `wartung` nicht in `any_read`): IMAP live (`postfach_open`, Zugang aus `smtp_config`, Host `imap_host` oder smtp.* -> imap.*), nur Text (`pf_text`, `html_to_text`), Anhänge nur als octet-stream-Download.
  Mail-Aufgaben in `mail_tasks` (nicht in `TABLES`, `/api/mailtasks`): Zugewiesene dürfen genau diese Mail lesen und beantworten (`mail_task_access`). Signatur `signature_parts` aus dem Signatur-Paket `web/assets/signatur` (signatur.html/.txt, Platzhalter `{{NAME}}`/`{{ROLLE}}`, Rolle aus Gruppen oder `users.mail_role`), Bilder öffentlich unter `/signatur/<name>.png`.
  Mail-Konten in `mail_accounts` (seit 4.43, Hub-Seite `#/emails`, nur Admins, `/api/admin/mail[/<id>[/check]]`, Passwort nie lesbar, Zuordnung in `mail_links` (seit 4.44 beliebig viele Personen je Konto und Konten je Person; `mail_account_users` und `mail_accounts.user_id` ungenutzt), Postfach-Schlüssel `acc<id>` (`user_mail_boxes`, `own` = erstes), `no_shared` = Ausnahme Postfach 0; alte Tabelle `user_mail` einmalig übernommen, danach ungenutzt): im Hub als zweites Postfach
  (`box=own` in Abfrage oder Body, eigene Rechte unabhängig vom Bereich, ohne Zuweisungen/`pf_inbox`), Frontend-Bereich `postfach|ownmail` (`perms.ownmail` aus `/api/me`).
  Verteiler: Tabelle `mail_lists` (Bereich `postfach`, `pfLists`), Einzelversand bis `PF_BULK_MAX`, ab 6 Empfängern im Hintergrund (`pf_send_bulk`, Push am Ende).
  Absender wählbar über `pf_senders` (`from`: info/own). Zuweisen an Personen ohne Postfach-Leserecht leitet per `pf_forward_to_person` weiter (Anhänge, Reply-To = Absender).
- Web Push ohne Zusatzpakete (`webpush_encrypt`, `ec_sign`, `aes128_gcm_encrypt`; gegen RFC 8291 und NIST geprüft): Schlüssel `secrets.vapid_d`, Abos `push_subs` (nur bekannte Push-Dienste, `push_endpoint_ok`), `send_push`, `sw.js` zeigt nur an.
  Neue Mails: `pf_poll_loop`/`pf_poll` (alle `PF_POLL_SECONDS`, erster Lauf merkt nur den Stand), Tabelle `pf_inbox`, Empfänger `pf_recipients` (Einstellung `pf_notify_groups`), erledigt über `pf_mark_handled` (Push-Art `done` schließt sich im `sw.js`); Knopf „Erledigt“ und erledigte Mail-Aufgaben verschieben per `pf_move_to_done` in den IMAP-Ordner `PF_DONE_FOLDER` (MOVE, sonst COPY+Löschen, neue UID über COPYUID oder Message-ID, `pf_inbox`/`mail_tasks` ziehen mit), Zahl am Symbol `badge_for`.
  `push_subs`, `mail_tasks`, `user_mail`, `mail_accounts`, `mail_links`, `pf_inbox` sind in `AUTH_TABLES` und nicht im Backup-Download.
- Sperre pro Konto: `ACCOUNT_FAIL_MAX` Fehlversuche, `ACCOUNT_LOCK_MINUTES` gesperrt (`users.locked_until`), Info-Mail; unbekannte Namen gleich behandelt (`GHOST_FAILS`, `dummy_check_pw`).
- Login-Sperre nach Fehlversuchen. Backup-Download enthält keine Konten. Restore behält Konten/Gruppen des Servers.
- Die Google-Tabelle (früher `sheet_*`) ist entfernt; `init_db` löscht alte `sheet_*`-Einstellungen, die Tabellen `sheet_players`/`sheet_log` bleiben auf alten Servern ungenutzt liegen. Keine Links oder Zugänge zu fremden Diensten in den Code (Repository öffentlich).
- Link- und Dateifelder: `api_table` lehnt `has_bad_link` ab (javascript:, data:, vbscript:, file:, blob:, auch in JSON-Dateilisten); app.js blockt Klicks auf javascript:-Links.
- `base_url` nur einmal: `SITE_URL`, sonst geprüfter Host-Header, nie `X-Forwarded-Host`.
- Content-Security-Policy in `end_headers`: Webseite (`frame_ok`) nur eigene Quellen, keine Inline-Skripte (JSON-LD ist erlaubt); Hub nur object-src, base-uri, form-action, frame-ancestors (wegen der Inline-Handler in pages.js).
- `Handler.timeout` 60 s, `read_body` lehnt ungültige Längen ab. Eingespielte Datenbanken (Restore, Umzug) über `db_check_import`: Integrität, Trigger und Views werden entfernt.

## Konventionen

- Texte, Captions, Hinweise: **keine Gedankenstriche (– oder —)**, wirkt nach KI. `noDashes()` im Frontend.
- Captions: max. 5 Hashtags, eigener Account wird nie markiert, keine erfundenen Ergebnisse oder Namen.
- Vereinsdesign: Vereinsviolett (#3D2F96), Nachtviolett (#15122B) und Weiß, Wappen „SV AMISIA“ nie verändern. Kein „Stern“ mehr im Vereinsnamen (Domain und Social-Media-Namen heißen noch so).
- Keine externen Abhängigkeiten ohne guten Grund (Server: nur Standardbibliothek, Frontend: kein Build).
- Versionsnummer an zwei Stellen gleich halten: `VERSION` in server.py und `APP_VERSION` in static/app.js (der Browser zeigt sonst einen Hinweis auf eine alte Version).

## Prüfen (ohne lokalen Server)

Wunsch des Betreibers: **zum Testen keine lokalen Server starten.** Stattdessen:

```
python3 -c "import ast; ast.parse(open('server.py').read()); ast.parse(open('website.py').read())"
python3 -m pyflakes server.py website.py
node --check static/app.js static/captions.js web/assets/site.js; for f in static/pages/*.js; do node --check "$f"; done
python3 tests/seiten_rendern.py      # Testdatenbank in einem Temp-Ordner, rendert jede öffentliche Seite, prüft Platzhalter, HTML und Jugendschutz
```

Nur für lokale Tests: `TMH_GRAPH_URL` (nachgebaute Meta-API), `TMH_NOTIFY_INTERVAL` und `TMH_DIGEST_SECONDS` (Benachrichtigungen schneller). Auf dem Server nie setzen.

Rechte mit mehreren Testkonten prüfen (Admin, Trainer, Spieler, Media Team, Helfer mit Ausnahme), sobald ein Testserver erlaubt ist: sichtbare Menüpunkte, Knöpfe, und dass der Server verbotene Aktionen mit 403 ablehnt.

## Ausliefern

1. Version in `server.py` und `static/app.js` hochzählen, Änderung in `CHANGELOG.md` eintragen.
2. Commit und Push auf `main`.
3. Prüfen wie oben, dann auf dem VPS: `cd /opt/docker/apps/wolthusen-hub && sudo bash update.sh` (Sicherung, `git pull` von `main`, Neustart, Healthcheck). Betrieb siehe `deploy/DEPLOY.md`.

Datenbank-Änderungen nur **additiv** (neue Tabellen/Spalten). Nie Spalten umbenennen oder löschen, sonst geht der Update-Pfad bestehender Server kaputt.
