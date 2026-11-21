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
