import os, sys, tempfile
os.environ["TMH_DATA"] = tempfile.mkdtemp(); sys.path.insert(0, ".")
import server
server.init_db()
csvdata = ("Spieldatum;Uhrzeit;Mannschaftsart;Staffel;Spielkennung;Heimmannschaft;Gastmannschaft;Spielstätte;Ergebnis\n"
           "29.11.2026;14:30;Herren;2.Kreisklasse;011507081;SV Amisia Wolthusen;TuS Borssum;Wolthusen A-Platz;\n"
           "06.12.26;11:00;E-Junioren;Kreisliga;022;JSG Leer;SV Amisia Wolthusen II;;3:1\n"
           "13.12.2026;13:00;Herren;2.Kreisklasse;033;SV Amisia Wolthusen II;FC X;;abgesetzt\n"
           "14.12.2026;13:00;Herren;2.Kreisklasse;044;FC A;FC B;;\n").encode("cp1252")
games, notes = server.dfb_parse(csvdata)
print(notes)
assert len(games) == 3, games
assert games[0]["team"] == "Erste Herren" and games[0]["home"] == 1 and games[0]["opponent"] == "TuS Borssum"
assert games[1]["team"] == "E-Jugend" and games[1]["score_us"] == "1" and games[1]["score_them"] == "3" and games[1]["date"] == "2026-12-06"
assert games[2]["team"] == "Zweite Herren" and games[2]["cancelled"]
with server.db() as conn:
    plan = server.dfb_plan(conn, games)
    assert [p["action"] for p in plan] == ["neu", "neu", "abgesetzt"], plan
    print(server.dfb_apply(conn, plan, "2026/27", None))
    games[0]["time"] = "15:00"
    plan = server.dfb_plan(conn, games)
    assert [p["action"] for p in plan] == ["ändern", "gleich", "abgesetzt"], [p["action"] for p in plan]
    server.dfb_apply(conn, plan, "2026/27", None)
    assert conn.execute("SELECT time FROM games WHERE match_no='011507081'").fetchone()[0] == "15:00"
    assert conn.execute("SELECT count(*) FROM games").fetchone()[0] == 2
print("DFB-Test OK")

# Excel (.xlsx) mit gemeinsamen Texten und Excel-Datum/-Uhrzeit als Zahl
import base64, io, zipfile  # noqa: E401,E402
ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
texts = ["Spieldatum", "Uhrzeit", "Heimmannschaft", "Gastmannschaft", "Spielkennung", "SV Amisia Wolthusen", "FC Neu"]
sst = f'<sst {ns}>' + "".join(f"<si><t>{t}</t></si>" for t in texts) + "</sst>"
def c(ref, v, s=False):
    return f'<c r="{ref}" t="s"><v>{v}</v></c>' if s else f'<c r="{ref}"><v>{v}</v></c>'
sheet = (f'<worksheet {ns}><sheetData><row r="1">' + "".join(c(f"{col}1", i, True) for i, col in enumerate("ABCDE")) + "</row>"
         '<row r="2">' + c("A2", "46365") + c("B2", "0.625") + c("C2", 5, True) + c("D2", 6, True) + c("E2", "555") + "</row></sheetData></worksheet>")
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w") as z:
    z.writestr("xl/sharedStrings.xml", sst)
    z.writestr("xl/worksheets/sheet1.xml", sheet)
xg, _ = server.dfb_parse(buf.getvalue())
assert xg and xg[0]["date"] == "2026-12-09" and xg[0]["time"] == "15:00" and xg[0]["opponent"] == "FC Neu" and xg[0]["match_no"] == "555", xg


# Endpunkt: Vorschau ändert nichts, Übernehmen legt an, ohne Schreibrecht 403, kaputte Datei 400
class Fake(server.Handler):
    def __init__(self, body):
        self.body = body

    def read_json(self):
        return self.body

    def send_json(self, data, status=200):
        return status, data

    def deny(self, msg=""):
        return 403, {"error": msg}


url = "data:application/octet-stream;base64," + base64.b64encode(buf.getvalue()).decode()
ok = lambda area, lvl=1: True  # noqa: E731
st, prev = Fake({"file": url, "filename": "x.xlsx", "team": "Erste Herren"}).api_dfbnet_import("POST", None, ok)
assert st == 200 and [i["action"] for i in prev["items"]] == ["neu"], prev
with server.db() as conn:
    assert not conn.execute("SELECT 1 FROM games WHERE match_no='555'").fetchone(), "Vorschau darf nichts speichern"
st, res = Fake({"file": url, "filename": "x.xlsx", "apply": True}).api_dfbnet_import("POST", None, ok)
assert st == 200 and res["counts"]["neu"] == 1, res
with server.db() as conn:
    assert conn.execute("SELECT season FROM games WHERE match_no='555'").fetchone()[0] == "2026/27"
assert Fake({"file": url}).api_dfbnet_import("POST", None, lambda a, lvl=1: lvl < 2)[0] == 403
assert Fake({"file": "data:x;base64," + base64.b64encode(b"PK\x03\x04kaputt").decode()}).api_dfbnet_import("POST", None, ok)[0] == 400
print("DFB-Endpunkt OK")
