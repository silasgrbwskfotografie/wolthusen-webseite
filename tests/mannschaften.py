"""Mannschaften aus dem Hub (Tabelle teams) ohne HTTP-Server prüfen: Vorbelegung, Anlegen, Umbenennen, Jugendschutz, Löschen.
Aufruf im Projektordner:  python tests/mannschaften.py"""
import os
import sys
import tempfile

os.environ["TMH_DATA"] = tempfile.mkdtemp(prefix="wolthusen-teams-")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server  # noqa: E402
import website  # noqa: E402

server.init_db()


class Fake(server.Handler):
    """Nur die generische API aufrufen: Anfrage-Körper rein, Antwort (Status, Daten) raus."""
    def __init__(self, body=None):
        self.body, self.user = body or {}, None

    def read_json(self):
        return self.body

    def send_json(self, data, status=200):
        return status, data


def call(method, rid=None, body=None):
    return Fake(body).api_table(method, "teams", rid)


with server.db() as conn:
    rows = {r["name"]: dict(r) for r in conn.execute("SELECT * FROM teams")}
assert len(rows) == 11 and rows["E-Jugend"]["youth"] == 1 and rows["Fit for Fun"]["sport"] == "Turnen & Gymnastik", rows.keys()
assert "erste-herren" in website.SLUG_TEAM and server.MAIN_TEAM == "Erste Herren"

# Anlegen: Kurzname aus dem Namen, doppelte Namen abgelehnt
st, t = call("POST", body={"name": "  Ü50  Herren ", "sport": "Fußball", "page": 1, "lead": "Kicken ohne Ende"})
assert st == 201 and t["slug"] == "ue50-herren" and t["name"] == "Ü50 Herren", t
assert call("POST", body={"name": "ü50 herren"})[0] == 400
assert "ue50-herren" in website.SLUG_TEAM and f"team-{t['id']}" in website.IMAGE_SLOTS

# Umbenennen zieht Spiele, Spieler und Training mit, Kurzname bleibt
with server.db() as conn:
    conn.execute("INSERT INTO players (kind, team, first_name, last_name, active) VALUES ('Spieler', 'Ü50 Herren', 'Opa', 'Kicker', 1)")
    conn.execute("INSERT INTO trainings (team, weekday, start, active) VALUES ('Ü50 Herren', 'Freitag', '18:00', 1)")
st, t2 = call("PUT", t["id"], {"name": "Ü50", "lead": "Neu"})
assert st == 200 and t2["slug"] == "ue50-herren", t2
with server.db() as conn:
    assert conn.execute("SELECT count(*) FROM players WHERE team='Ü50'").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM trainings WHERE team='Ü50'").fetchone()[0] == 1
assert any(p["first_name"] == "Opa" for p in server.public_team())

# Jugend: Spieler verschwinden von der Webseite
call("PUT", t["id"], {"youth": 1})
assert not any(p["first_name"] == "Opa" for p in server.public_team()), "Jugendspieler öffentlich"
# Inaktiv: weder Spieler noch Training noch Seite
call("PUT", t["id"], {"youth": 0, "active": 0})
assert not any(p["first_name"] == "Opa" for p in server.public_team())
assert not any(x["team"] == "Ü50" for x in server.public_trainings()) and "ue50-herren" not in website.SLUG_TEAM

# Löschen nur ohne Einträge
st, err = call("DELETE", t["id"])
assert st == 409, (st, err)
with server.db() as conn:
    conn.execute("DELETE FROM players WHERE team='Ü50'")
    conn.execute("DELETE FROM trainings WHERE team='Ü50'")
assert call("DELETE", t["id"])[0] == 200

# Eigene Seite für eine Turngruppe: Menü und Seite
fit = rows["Fit for Fun"]
call("PUT", fit["id"], {"page": 1, "intro": "Bewegung für alle."})
data = {"info": server.public_info(), "games": [], "team": [], "sponsors": [], "trainings": server.public_trainings(), "instagram": [], "shop": [],
        "site": server.public_site(), "base": "https://x.de", "articles": [], "nav": server.public_nav()}
html = website.render("mannschaft/fit-for-fun", data, None)
assert "Bewegung für alle." in html and "Turnen &amp; Gymnastik" in html and 'href="/mannschaft/fit-for-fun"' in html
# Spielplan „nur fussball.de-Link“: Jugend und Alte Herren vorbelegt, ihre Spiele nicht öffentlich, Seite zeigt den Link
with server.db() as conn:
    sched = {r["name"]: r["schedule"] for r in conn.execute("SELECT name, schedule FROM teams")}
    conn.execute("INSERT INTO games (date, team, home) VALUES ('2099-01-01', 'E-Jugend', 1)")
    conn.execute("INSERT INTO games (date, team, home) VALUES ('2099-01-02', 'Erste Herren', 1)")
assert sched["E-Jugend"] == sched["Alte Herren"] == "nur fussball.de-Link" and sched["Erste Herren"] == "aus dem Hub", sched
assert [g["team"] for g in server.public_games()] == ["Erste Herren"]
data.update(games=server.public_games())
html = website.render("mannschaft/e-jugend", data, None)
assert "stehen aktuell bei fussball.de" in html and "fussball.de/mannschaft" in html and "Die nächsten Spiele stehen hier" not in html
assert "Weitere Mannschaften" in website.render("spielplan", data, None)
st, t3 = call("PUT", rows["Erste Herren"]["id"], {"schedule": "Quatsch"})
assert t3["schedule"] == "aus dem Hub", t3
print("Mannschaften-Test OK")
