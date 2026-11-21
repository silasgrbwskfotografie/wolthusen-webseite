# E-Mail-Signatur SV Amisia Wolthusen

Der Hub baut die Signatur im Postfach aus `signatur.html` und `signatur.txt` (Platzhalter `{{NAME}}`, `{{ROLLE}}`, `{{TELEFON_ZEILE}}`).
Die Bilder liefert der Server öffentlich unter `/signatur/<datei>.png` aus, die HTML verweist auf `https://www.amisia-stern.de/signatur/...`.
Bei einer anderen Domain die Adressen in `signatur.html` und `SIG_URL` in `server.py` anpassen.

| Datei | Zweck |
|---|---|
| `signatur.html` | HTML-Signatur, alle Styles inline, Tabellen-Layout für Outlook |
| `signatur.txt` | Textversion |
| `wappen.png` | Vereinswappen, 216 x 240 px, Anzeige 72 x 80 px |
| `icon-*.png` | Symbole, 72 x 72 px, Anzeige 18 x 18 px |
