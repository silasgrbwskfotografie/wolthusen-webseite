# Offene Platzhalter

Auf der Webseite gelb markiert (`<span class="ph">`) oder als gestreifte Bildfläche. Die meisten Inhalte pflegt man im Hub (`/hub`),
die festen Seiten in `seiten/*.html`. Im Hub unter **Medien > Webseite > Übersicht** steht eine Checkliste mit allem, was noch fehlt.

## Rechtliches (vor dem Livegang Pflicht, im Hub unter Webseite > Texte)
- [ ] Impressum: Vorstand nach § 26 BGB mit Namen, Registergericht und VR-Nummer, Telefon, Verantwortlicher nach § 18 MStV
- [ ] Datenschutz: Hosting-Anbieter, E-Mail-Anbieter, Löschfrist der Anfragen, Stand-Datum, ggf. Datenschutzbeauftragte/r
- [ ] Bildnachweise der übrigen Fotos
- [ ] Kontakt-E-Mail des Vereins (Einstellung `site_contact_email`, erscheint in Footer, Kontakt, Impressum und Datenschutz)

## Name ohne „Stern“
- [ ] Vereinsgeschichte auf der Startseite: Fusion 2012 mit dem VfB Stern Emden und Umbenennung erwähnen? (`seiten/01-start.html`)
- [ ] Domain und E-Mails heißen noch amisia-stern.de, Instagram/Facebook noch amisiasternwolthusen bzw. AmisiaStern.
      Neue Adressen im Hub (Webseite > Menü, Einstellungen) und in `web/assets/signatur/` tauschen.
- [ ] Teamnamen bei fussball.de prüfen (dort evtl. noch „Amisia Stern“)

## Fotos (Hub > Webseite > Bilder)
- [ ] Titelbild Startseite, Vereinsfoto, Fußball, Herren, Jugend (nur mit Einwilligung der Eltern), Spielplan, Turnen, Saal, Saal innen, Defibrillator, Partner, Vereinsleben
- [ ] Galerie 1 bis 6 für das Instagram-Raster, solange Instagram nicht verbunden ist (ohne Bilder bleibt der Abschnitt aus)

## Inhalte im Hub
- [ ] Trainingszeiten aller Mannschaften (Verein > Trainingszeiten); Uhrzeiten von Fit for Fun (Donnerstag) und Gymnastikgruppe (Mittwoch)
- [ ] Trainer und Betreuer je Mannschaft (Verein > Kader & Trainer, Art „Coach“ oder „Staff“), Jugendleitung
- [ ] Spielplan (Verein > Spielplan), Gegner mit Logos
- [ ] Sponsoren mit Logos (Verein > Sponsoren), dann erscheinen sie auf Partner und Startseite
- [ ] Newsletter-Themen (Medien > Newsletter > Gruppen), z. B. Herren, Jugend, Verein
- [ ] Bankverbindung und Steuernummer für Rechnungen (Finanzen > Dauerkarte > Einstellungen), falls die Dauerkarte online verkauft wird

## Inhalte in `seiten/`
- [ ] Termin Superkicker Fußballcamp 2027 (Start und Fußball)
- [ ] Standort des Defibrillators (Start)
- [ ] Saalmiete: Preis und Bedingungen (Saal)
- [ ] Adresse der Tigers Webseite bestätigen (American Football, jetzt emden-tigers.de)
- [ ] Logo Audi BKK auf der Partner-Seite (am besten als Sponsor im Hub mit Logo anlegen)

## Downloads
- [ ] PDFs nach `web/assets/downloads/` legen: `beitrittserklaerung.pdf`, `einverstaendniserklaerung.pdf`, `satzung.pdf`
      (liegen auf der bisherigen Seite unter /assets/files/)

## Betrieb
- [ ] VPS und Domain festlegen, `.env` anlegen (`DOMAIN`, Admin-Zugang), siehe INSTALLATION.md bzw. deploy/DEPLOY.md
- [ ] E-Mail-Versand einrichten (Hub > Verwaltung > Einstellungen), sonst gehen keine Bestätigungen und Benachrichtigungen raus
