"""Rendert alle öffentlichen Seiten ohne HTTP-Server (Wunsch des Betreibers: keine lokalen Testserver).

Legt eine Testdatenbank in einem Temp-Ordner an, trägt Beispieldaten ein, ruft website.render für jede Seite auf und meldet
übrige {{Platzhalter}}, kaputtes HTML und sichtbare Jugendspieler. Aufruf: python3 tests/seiten_rendern.py
"""
import os
import re
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

root = Path(__file__).resolve().parents[1]
os.environ["TMH_DATA"] = tempfile.mkdtemp(prefix="wolthusen-test-")
sys.path.insert(0, str(root))
os.chdir(root)
import server  # noqa: E402
import website  # noqa: E402

server.init_db()
with server.db() as conn:
    now = "2026-11-21T10:00:00"
    conn.execute("INSERT INTO opponents (name, short, city) VALUES ('TuS Borssum', 'Borssum', 'Emden')")
    for d, t, team, home, su, st in (("2026-11-29", "14:30", "Erste Herren", 1, None, None), ("2026-12-06", "11:00", "E-Jugend", 0, None, None),
                                     ("2026-11-15", "15:00", "Erste Herren", 1, "3", "1"), ("2026-11-08", "13:00", "Zweite Herren", 0, "0", "2")):
        conn.execute("INSERT INTO games (season, date, time, team, home, opponent_id, kind, league, score_us, score_them) VALUES ('2026/27', ?, ?, ?, ?, 1, 'Liga', 'Kreisliga', ?, ?)",
                     (d, t, team, home, su, st))
    conn.execute("INSERT INTO players (kind, team, first_name, last_name, number, position, active, consent) VALUES ('Spieler', 'Erste Herren', 'Max', 'Muster', '9', 'Sturm', 1, 1)")
    conn.execute("INSERT INTO players (kind, team, first_name, last_name, role, active) VALUES ('Coach', 'Erste Herren', 'Erik', 'Trainer', 'Trainer', 1)")
    conn.execute("INSERT INTO players (kind, team, first_name, last_name, number, position, active, consent) VALUES ('Spieler', 'E-Jugend', 'Kind', 'Geheim', '7', 'Tor', 1, 1)")
    conn.execute("INSERT INTO players (kind, team, first_name, last_name, role, active) VALUES ('Coach', 'E-Jugend', 'Jana', 'Jugend', 'Trainer', 1)")
    conn.execute("INSERT INTO trainings (team, weekday, start, end, place, active) VALUES ('Erste Herren', 'Dienstag', '19:00', '20:30', 'Sportplatz Wolthusen', 1)")
    conn.execute("INSERT INTO sponsors (name, website, active) VALUES ('Audi BKK', 'https://www.audibkk.de', 1)")
    conn.execute("INSERT INTO articles (title, teaser, body, date, status, team) VALUES ('Sieg gegen Borssum', 'Starker Auftritt', 'Text\n\nNoch ein Absatz', '2026-11-16', 'Veröffentlicht', 'Erste Herren')")

articles = server.public_articles()
base = {"info": server.public_info(), "games": server.public_games(), "team": server.public_team(), "sponsors": server.public_sponsors(),
        "trainings": server.public_trainings(), "instagram": [], "shop": [], "site": server.public_site(), "base": "https://www.amisia-stern.de",
        "articles": articles, "nav": server.public_nav()}
assert not any(p["first_name"] == "Kind" for p in base["team"]), "Jugendspieler darf nicht öffentlich sein"
assert any(t["team"] == "Herren-Gymnastik" for t in base["trainings"]), "Vorbelegte Trainingszeiten fehlen"


class Check(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(); self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass
        else:
            self.errors.append(f"</{tag}> ohne Anfang")


slugs = ["", "fussball", "american-football", "turnen-gymnastik", "saal", "partner", "mitglied-werden", "spielplan", "news", "kontakt",
         "supporter-karte", "impressum", "datenschutz", "newsletter", "spielerbogen", "helfer", "links", "404", "wartung"]
slugs += ["mannschaft/" + s for s in website.SLUG_TEAM]
bad = 0
for slug in slugs:
    data = dict(base, maint={"title": "", "text": "Test"}, preselect="saal")
    html = website.render(slug, data, None)
    c = Check(); c.feed(html)
    problems = []
    if "{{" in html:
        problems.append("Platzhalter übrig: " + ", ".join(sorted(set(re.findall(r"\{\{[^}]*\}\}", html)))))
    if c.errors:
        problems.append("; ".join(c.errors[:3]))
    left = [t for t in c.stack if t not in ("html", "body", "head")]
    if left:
        problems.append("offen: " + ",".join(left[:5]))
    if slug == "mannschaft/e-jugend" and "Geheim" in html:
        problems.append("Jugendspieler sichtbar")
    print(f"{slug or '/':<28} {len(html):>7} Zeichen  {'OK' if not problems else ' | '.join(problems)}")
    bad += bool(problems)
a = articles[0]
html = website.render("news-artikel", dict(base, article=a), None)
print("news-artikel", "OK" if "Sieg gegen Borssum" in html and "{{" not in html else "FEHLER")
print("sitemap", website.sitemap("https://x.de", articles).count("<url>"), "Einträge")
print("Fehler:", bad)
sys.exit(1 if bad else 0)
