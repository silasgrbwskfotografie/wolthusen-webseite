"""SV Amisia Wolthusen: öffentliche Webseite (wird vom Server gerendert, ohne JavaScript-Pflicht).

Feste Inhalte (Fußball, Turnen, Saal, Partner, Mitglied werden ...) liegen als HTML in seiten/<datei>.html.
Erste Zeile jeder Datei: <!-- {"title", "path", "nav", "description"} -->, danach der Inhalt. Darin werden Platzhalter
wie {{SHIELD}}, {{BILD:name}}, {{SPIELE}}, {{MANNSCHAFTEN}} oder {{PARTNER}} durch Daten aus dem Hub ersetzt.
Dynamische Seiten (Spielplan, Mannschaften, News, Kontakt, Newsletter, Dauerkarte, Rechtliches) baut diese Datei.

Bekommt ausschließlich die öffentlichen Daten aus server.py (public_info, public_games, public_team, public_trainings,
public_sponsors, public_articles). Kein Datenbankzugriff, keine internen Felder.
Fehlende Inhalte erscheinen als deutlich markierter Platzhalter (Klasse .ph), siehe PLATZHALTER.md.
"""
import json
import re
import threading
from datetime import date, datetime
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path

BASE = Path(__file__).resolve().parent
WEB = BASE / "web"
IMG = WEB / "assets" / "img"
SEITEN = BASE / "seiten"
IMG_WIDTHS = (640, 960, 1280, 1920)
LOGO = "/web/assets/wappen.png"   # Vereinswappen 256 x 288 px (Original: web/assets/logo.webp)

# Impressum und Datenschutz: eigene Texte aus dem Hub (Einstellungen site_impressum, site_datenschutz)
LEGAL = {"impressum": ("Impressum", "site_impressum"), "datenschutz": ("Datenschutzerklärung", "site_datenschutz")}

# Mannschaften wie TEAMS in server.py. Spieler der Jugend (Minderjährige) erscheinen nie auf der Webseite.
TEAMS = ("Erste Herren", "Zweite Herren", "Alte Herren", "D-Jugend", "E-Jugend", "F-Jugend", "G-Jugend")
YOUTH_TEAMS = {"D-Jugend", "E-Jugend", "F-Jugend", "G-Jugend"}
TEAM_SLUG = {"Erste Herren": "erste-herren", "Zweite Herren": "zweite-herren", "Alte Herren": "alte-herren",
             "D-Jugend": "d-jugend", "E-Jugend": "e-jugend", "F-Jugend": "f-jugend", "G-Jugend": "g-jugend"}
SLUG_TEAM = {v: k for k, v in TEAM_SLUG.items()}
# Mannschaften bei fussball.de (Spielplan, Tabelle). Neue Mannschaften hier ergänzen.
FUSSBALL_DE = {
    "Erste Herren": [("Herren I", "https://next.fussball.de/mannschaft/-/011MIF3UFK000000VTVG0001VTR8C1K7")],
    "Zweite Herren": [("Herren II", "https://next.fussball.de/mannschaft/-/01KV6SMQ68000000VV0AG80NVVRC6LS5")],
    "E-Jugend": [("E-Junioren I", "https://next.fussball.de/mannschaft/-/01DQ7DBIQ4000000VV0AG811VTPFGC7P"),
                 ("E-Junioren II", "https://next.fussball.de/mannschaft/-/02PQBAC560000000VS5489B2VUGLP840")],
    "F-Jugend": [("F-Junioren", "https://next.fussball.de/mannschaft/-/01DQ7KCOKC000000VV0AG811VTPFGC7P")],
    "G-Jugend": [("G-Junioren", "https://next.fussball.de/mannschaft/-/02MMD80AU8000000VS5489B2VU7T3OBS")],
}
TEAM_LEAD = {"Erste Herren": "Unser Aushängeschild", "Zweite Herren": "Fußball mit Ehrgeiz und Spaß", "Alte Herren": "Für alle, die weiter kicken wollen",
             "D-Jugend": "Jahrgänge laut DFB-Altersklasse", "E-Jugend": "Jahrgänge laut DFB-Altersklasse", "F-Jugend": "Die Jüngsten mit Ball am Fuß",
             "G-Jugend": "Bambini: erste Schritte im Verein"}

# Hauptmenü: Link (Schlüssel, Adresse, Text) oder Untermenü {"text", "keys", "groups": [(Überschrift, Adresse, [(Text, Adresse)])]}
NAV = [
    ("start", "/", "Start"),
    {"text": "Sportarten", "keys": {"fussball", "mannschaft", "football", "turnen", "spielplan"}, "groups": [
        ("Fußball", "/fussball", [
            ("Erste Herren", "/mannschaft/erste-herren"), ("Zweite Herren", "/mannschaft/zweite-herren"), ("Alte Herren", "/mannschaft/alte-herren"),
            ("Kinder- und Jugendfußball", "/fussball#jugend"), ("Spielplan und Ergebnisse", "/spielplan"), ("Superkicker Fußballcamp", "/fussball#camp"),
        ]),
        ("American Football", "/american-football", [("AFC Tigers Emden", "/american-football"), ("Mehr über die Tigers", "/american-football#tigers-social")]),
        ("Turnen & Gymnastik", "/turnen-gymnastik", [("Fit for Fun", "/turnen-gymnastik#fit-for-fun"), ("Gymnastikgruppe", "/turnen-gymnastik#gymnastikgruppe"),
                                                    ("Herren-Gymnastik", "/turnen-gymnastik#herren-gymnastik")]),
    ]},
    {"text": "Verein", "keys": {"saal", "partner", "mitglied", "news"}, "groups": [
        ("Über uns", "/#ueber-uns", [("Unser Verein", "/#ueber-uns"), ("News", "/news"), ("Projekt Defibrillator", "/#defibrillator"), ("Partner und Sponsoren", "/partner")]),
        ("Mitmachen", "/mitglied-werden", [("Mitglied werden", "/mitglied-werden"), ("Beiträge", "/mitglied-werden#beitraege"), ("Downloads", "/mitglied-werden#downloads"),
                                          ("Newsletter", "/newsletter")]),
        ("Unser Saal", "/saal", [("Saal mieten", "/saal"), ("Saal anfragen", "/kontakt?anliegen=saal#formular")]),
    ]},
    ("kontakt", "/kontakt", "Kontakt"),
]
CTA = ("mitglied", "/mitglied-werden", "Mitglied werden")
# Alte Adressen (bisherige Webseite und Tigers-Vorlage) leiten dauerhaft auf die neuen Seiten weiter
REDIRECTS = {"index.html": "/", "herren": "/mannschaft/erste-herren", "jugend": "/fussball#jugend", "sponsoren": "/partner", "team": "/fussball",
             "turnen": "/turnen-gymnastik", "mitglied": "/mitglied-werden", "probetraining": "/kontakt"}
# Anliegen im Kontaktformular: Wert (wie CONTACT_TOPICS in server.py), Kurzname für ?anliegen=, Beschriftung, Hinweis
CONTACT_TOPICS = [
    ("Allgemeine Frage", "frage", "Allgemeine Frage", "Alles rund um den Verein"),
    ("Mitgliedschaft", "mitglied", "Mitgliedschaft", "Beitritt, Beiträge, Kündigung"),
    ("Probetraining Herren", "herren", "Probetraining Herren", "Erste, Zweite oder Alte Herren"),
    ("Probetraining Jugend", "jugend", "Probetraining Jugend", "Kinder von der G- bis zur D-Jugend"),
    ("Turnen und Gymnastik", "turnen", "Turnen und Gymnastik", "Fit for Fun und Gymnastikgruppen"),
    ("Saal mieten", "saal", "Saal mieten", "Feiern im Sportheim, bis 80 Personen"),
    ("Sponsoring", "sponsoring", "Sponsoring", "Partner werden"),
    ("Dauerkarte", "karte", "Dauerkarte", "Fragen zur Dauerkarte und zu deiner Bestellung"),
]
CARD_TOPIC = "Dauerkarte"   # nur im Formular, solange die Online-Bestellung offen ist (site_card_order_open)
NL_CONSENT = ("Ich möchte den Newsletter des SV Amisia Wolthusen zu den gewählten Themen per E-Mail erhalten. "
              "Die Einwilligung kann ich jederzeit über den Link in jeder Ausgabe widerrufen.")
POSITIONS = ["Tor", "Abwehr", "Mittelfeld", "Sturm"]
POS_NAME = {"Tor": "Torwart", "Abwehr": "Abwehr", "Mittelfeld": "Mittelfeld", "Sturm": "Sturm"}
POS_PLURAL = {"Tor": "Tor", "Abwehr": "Abwehr", "Mittelfeld": "Mittelfeld", "Sturm": "Sturm"}
COACH_ROLES = ["Trainer", "Co-Trainer", "Torwarttrainer", "Betreuer", "Teammanager", "Physio", "Zeugwart", "Jugendleitung",
               "Social Media Betreuer"]   # wie STAFF_ROLES in static/pages/01-grundlagen.js, bestimmt die Reihenfolge
WD = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# Bilder, die im Hub (Webseite > Bilder) ersetzt werden können: Name -> (Bezeichnung, wo es erscheint)
IMAGE_SLOTS = {
    "hero": ("Titelbild Startseite", "Großes Bild ganz oben auf der Startseite, auch Vorschaubild beim Teilen von Links"),
    "verein": ("Vereinsfoto", "Startseite bei „Über uns“"),
    "fussball": ("Fußball", "Startseite (Karte Fußball) und Titelbild der Seite Fußball"),
    "herren": ("Herrenmannschaft", "Titelbild der Seiten Erste, Zweite und Alte Herren"),
    "jugend": ("Jugendfußball", "Titelbild der Jugendseiten (bitte nur mit Einwilligung der Eltern)"),
    "spielplan": ("Spielplan", "Titelbild der Seite Spielplan"),
    "turnen": ("Turnen und Gymnastik", "Titelbild der Seite Turnen & Gymnastik"),
    "saal": ("Saal", "Startseite (Karte Saal) und Titelbild der Seite Unser Saal"),
    "saal-innen": ("Saal innen", "Seite Unser Saal neben dem Text"),
    "defi": ("Defibrillator", "Startseite beim Projekt Defibrillator"),
    "partner": ("Partner", "Titelbild der Seite Partner"),
    "mitglied": ("Vereinsleben", "Titelbild der Seiten Mitglied werden, Kontakt und Newsletter"),
    **{f"galerie-{i}": (f"Galerie {i}", "Instagram-Raster auf der Startseite, solange Instagram nicht verbunden ist") for i in range(1, 7)},
    "wartung": ("Wartungsseite", "Hintergrund der Wartungsseite (im Hub unter Verwaltung > Wartungsmodus, ohne eigenes Bild das Titelbild)"),
}
MAINT_SLOT = "wartung"   # gepflegt nur auf der Hub-Seite Wartungsmodus, nicht unter Webseite > Bilder
# Abschnitte der Startseite aus dem Hub (sortier- und ausblendbar), stehen an der Stelle {{DYNAMISCH}} in seiten/01-start.html
START_SECTIONS = {
    "spiele": "Nächste Spiele (alle Mannschaften)",
    "ergebnisse": "Zuletzt gespielt",
    "news": "News (die 3 neuesten Artikel)",
    "karte": "Dauerkarte (nur solange die Online-Bestellung offen ist)",
    "sponsoren": "Unsere Partner",
    "instagram": "Instagram",
}
# Texte, die auf der Webseite als Platzhalter erscheinen, solange sie leer sind (Checkliste im Hub)
REQUIRED_TEXTS = {
    "site_contact_email": "Kontakt-E-Mail", "site_hero_text": "Startseite: Satz unter der Überschrift", "site_about": "Startseite: Über uns",
    "site_trial_text": "Hinweise zum Probetraining", "site_home_address": "Adresse Sportplatz", "site_gameday_text": "Spielplan: Infos zum Spieltag",
    "site_sponsor_text": "Partner: Partner werden", "site_impressum": "Impressum", "site_datenschutz": "Datenschutzerklärung",
}
SHIELD = ('<svg class="shield-mark" viewBox="0 0 100 112" aria-hidden="true">'
          '<path d="M16 3 C32 9 42 10 50 10 C58 10 68 9 84 3 L98 14 C92 26 89 34 89 40 C89 50 94 58 98 62'
          ' C96 84 74 100 50 109 C26 100 4 84 2 62 C6 58 11 50 11 40 C11 34 8 26 2 14 Z"/>'
          '<path d="M92 16 L14 92"/></svg>')
_ctx = threading.local()   # Daten der gerade gebauten Seite (der Server bearbeitet Anfragen parallel)


def e(t):
    return escape(str(t if t is not None else ""), quote=True)


def asset(path):
    """Link auf eine Datei unter web/assets mit Änderungsstempel, damit Browser nach Updates die neue Fassung laden."""
    f = WEB / "assets" / path
    v = int(f.stat().st_mtime) if f.is_file() else 0
    return f"/web/assets/{path}?v={v}"


FONT_PRELOAD = ('<link rel="preload" href="/web/assets/fonts/Anton-Regular.woff2" as="font" type="font/woff2" crossorigin>'
                '<link rel="preload" href="/web/assets/fonts/Karla-Variable.woff2" as="font" type="font/woff2" crossorigin>')
_CSS = {}


def site_css():
    """site.css verkleinert für einen <style>-Block im Kopf (keine blockierende CSS-Anfrage). Neu eingelesen, wenn die Datei sich ändert."""
    f = WEB / "assets" / "site.css"
    try:
        mt = f.stat().st_mtime
    except OSError:
        return ""
    if _CSS.get("mt") != mt:
        css = re.sub(r"/\*.*?\*/", "", f.read_text(encoding="utf-8"), flags=re.S)
        css = re.sub(r"\s+", " ", css)
        css = re.sub(r"\s*([{};,>])\s*", r"\1", css).replace(";}", "}")
        _CSS.update(mt=mt, css=css.replace("</", r"<\/").strip())   # kein </style> im Block möglich
    return _CSS["css"]


def lines(t):
    return "<br>".join(e(x) for x in str(t or "").splitlines())


def placeholder(what):
    """Klar markierter Platzhalter für Inhalte, die im Hub noch fehlen."""
    return f'<span class="ph" title="Platzhalter, im Hub pflegen">Platzhalter: {e(what)}</span>'


def text_or_ph(value, what):
    return lines(value) if (value or "").strip() else placeholder(what)


def fmt_date(d, weekday=False):
    try:
        x = date.fromisoformat(d)
    except (TypeError, ValueError):
        return ""
    return (f"{WD[x.weekday()]}, " if weekday else "") + f"{x.day:02d}.{x.month:02d}.{x.year}"


def euro(v):
    """'1.50' oder '25' -> '1,50 €' / '25,00 €' (leer bei ungültigem Wert)."""
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return ""
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
# Bilder: web/assets/img/<name>-<breite>.webp, Beschreibung in bilder.json, im Hub ersetzte Bilder unter /web/site/
# ---------------------------------------------------------------------------
def image_meta(standard=False):
    f = IMG / "bilder.json"
    try:
        meta = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    if not standard:
        for slot, m in (getattr(_ctx, "images", None) or {}).items():
            if m.get("src"):
                meta[slot] = m
            elif slot in meta and m.get("alt"):
                meta[slot] = {**meta[slot], "alt": m["alt"]}
    return meta


def picture(name, sizes="100vw", cls="", eager=False, meta=None):
    meta = meta if meta is not None else image_meta()
    m = meta.get(name)
    if m and m.get("src"):
        files = sorted(m["src"].items())
    else:
        files = [(w, f"/web/assets/img/{name}-{w}.webp") for w in IMG_WIDTHS if (IMG / f"{name}-{w}.webp").is_file()]
    widths = [w for w, _ in files]
    if not m or not widths:
        label = IMAGE_SLOTS.get(name, (name,))[0]
        return f'<div class="img-ph {e(cls)}" role="img" aria-label="Platzhalter {e(label)}">{placeholder("Foto " + label)}</div>'
    srcset = ", ".join(f"{e(u)} {w}w" for w, u in files)
    mid = files[min(1, len(files) - 1)][1]
    load = 'fetchpriority="high"' if eager else 'loading="lazy"'
    return (f'<img class="{e(cls)}" src="{e(mid)}" srcset="{srcset}" sizes="{e(sizes)}" '
            f'width="{m.get("w", 1600)}" height="{m.get("h", 1067)}" alt="{e(m.get("alt") or "Foto vom SV Amisia Wolthusen")}" {load} decoding="async">')


def photos(prefix):
    return sorted((k for k in image_meta() if k.startswith(prefix)), key=lambda k: (len(k), k))


# ---------------------------------------------------------------------------
# Rahmen: Kopf, Navigation, Fußzeile
# ---------------------------------------------------------------------------
SEO_DESC = {"": "site_seo_start", "spielplan": "site_seo_spielplan", "news": "site_seo_news", "partner": "site_seo_sponsoren",
            "kontakt": "site_seo_kontakt", "mannschaft": "site_seo_herren"}


def seo_desc(info, slug, fallback):
    v = " ".join((info.get(SEO_DESC.get(slug, "")) or "").split())
    return v[:300] or fallback


def verify_tags(info):
    """Bestätigung für Google Search Console und Bing Webmaster Tools (nur der Code, streng geprüft)."""
    out = []
    for key, name in (("site_verify_google", "google-site-verification"), ("site_verify_bing", "msvalidate.01")):
        v = (info.get(key) or "").strip()
        m = re.search(r'content="([^"]+)"', v)
        v = m.group(1) if m else v
        if re.fullmatch(r"[A-Za-z0-9_\-]{8,100}", v):
            out.append(f'<meta name="{name}" content="{e(v)}">')
    return "".join(out)


def notice_bar(info):
    """Hinweis-Leiste oben (im Hub unter Webseite > Hinweis), nur bis einschließlich zum eingestellten Datum."""
    text, link, until = (info.get("site_notice_text") or "").strip(), (info.get("site_notice_link") or "").strip(), info.get("site_notice_until") or ""
    if not text or (until and until < date.today().isoformat()):
        return ""
    ok = link.startswith("/") and not link.startswith("//") or link.startswith(("https://", "http://"))
    target = "" if link.startswith("/") else ' target="_blank" rel="noopener"'
    more = f' <a href="{e(link)}"{target}>Mehr erfahren</a>' if ok else ""
    return f'<div class="notice"><p>{e(text)}{more}</p></div>'


def maint_bar():
    if not getattr(_ctx, "maint_bar", False):
        return ""
    return ('<div class="maint-bar"><p><b>Wartungsmodus ist an.</b> Besucher sehen gerade die Wartungsseite, du siehst die Webseite, '
            'weil du angemeldet bist. <a href="/?wartung-vorschau=1">Wartungsseite ansehen</a> <a href="/hub#/wartung">Im Hub ändern</a></p></div>')


SOCIAL_ICONS = {   # eigene, einfache Symbole (nichts wird von Instagram, Facebook oder TikTok geladen)
    "instagram": ("Instagram", '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none"/>'),
    "facebook": ("Facebook", '<path d="M14 8h3V4h-3a4 4 0 0 0-4 4v3H7v4h3v6h4v-6h3l1-4h-4V8z"/>'),
    "tiktok": ("TikTok", '<path d="M14 3v11.5a3.5 3.5 0 1 1-3.5-3.5"/><path d="M14 3c.5 2.8 2.4 4.6 5 5"/>'),
}


def nav_html(active):
    """Menü mit den Untermenüs Sportarten und Verein, dazu Dauerkarte und Fanshop aus dem Hub (Webseite > Menü)."""
    links = []
    for i, item in enumerate(NAV):
        if isinstance(item, dict):
            cls = "dd active" if active in item["keys"] else "dd"
            cols = "".join(f'<div class="dd-col"><a class="dd-head" href="{h}">{e(head)}</a><ul>'
                           + "".join(f'<li><a href="{x}">{e(t)}</a></li>' for t, x in subs) + "</ul></div>"
                           for head, h, subs in item["groups"])
            links.append(f'<div class="{cls}"><button class="dd-btn" type="button" aria-expanded="false" aria-controls="dd{i}">{e(item["text"])}</button>'
                         f'<div class="dd-panel" id="dd{i}">{cols}</div></div>')
            continue
        key, href, text = item
        cur = ' class="active" aria-current="page"' if key == active else ""
        links.append(f'<a href="{href}"{cur}>{e(text)}</a>')
    extra = getattr(_ctx, "nav", None) or {}
    for x in extra.get("items", []):   # aus dem Hub: Dauerkarte (bei offener Bestellung) und Fanshop
        if x.get("slug") in ("supporter-karte",) or x.get("external"):
            target = ' target="_blank" rel="noopener"' if x.get("external") else ""
            links.append(f'<a href="{e(x["href"])}"{target}>{e(x["label"])}</a>')
    cls = "cta active" if active == CTA[0] else "cta"
    links.append(f'<a class="{cls}" href="{CTA[1]}">{CTA[2]}</a>')
    return "\n      ".join(links)


def social_links(info):
    """Social-Media-Kanäle aus dem Hub (Webseite > Menü), sonst Instagram aus den Einstellungen."""
    nav = getattr(_ctx, "nav", None) or {}
    out = [(SOCIAL_ICONS[s["kind"]][0], s["url"]) for s in nav.get("social", []) if s.get("kind") in SOCIAL_ICONS]
    ig = (info.get("instagram") or "").lstrip("@")
    if not out and ig:
        out = [("Instagram", f"https://www.instagram.com/{ig}/")]
    return out


def layout(slug, title, description, body, info, extra_head="", canonical=None, noindex=False, active=None):
    club = info.get("club_name") or "SV Amisia Wolthusen"
    mail = (info.get("site_contact_email") or "").strip()
    hero = image_meta().get("hero") or {}
    og_img = ((hero.get("src") or {}).get(1280) or ("/web/assets/img/hero-1280.webp" if (IMG / "hero-1280.webp").is_file() else LOGO))
    base = getattr(_ctx, "base", "")
    og_abs = og_img if og_img.startswith("http") else base + og_img
    tagline = " ".join((info.get("site_seo_title") or "").split())[:70] or "Sportverein in Emden-Wolthusen"
    full_title = title + " | " + club if title else club + " | " + tagline
    own_robots = 'name="robots"' in extra_head
    noindex = noindex or own_robots or not (slug in PAGES or slug.startswith("mannschaft/"))
    path = canonical if canonical is not None else ("/" + slug if slug else "/")
    url = base + path if base and not noindex else ""
    robots = "" if own_robots else '<meta name="robots" content="noindex">' if noindex else '<meta name="robots" content="index, follow, max-image-preview:large">'
    social = "".join(f'<p><a href="{e(u)}" rel="noopener" target="_blank">{e(n)}</a></p>' for n, u in social_links(info))
    ld = ""
    if base and not noindex:
        ld = f'<link rel="canonical" href="{e(url)}">' + (jsonld(org_ld(info, base)) if slug in ("", "spielplan") else "")
    return f"""<!doctype html>
<html lang="de"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(full_title)}</title>
<meta name="description" content="{e(description)}">
{robots}
<meta property="og:site_name" content="{e(club)}"><meta property="og:locale" content="de_DE">
<meta property="og:title" content="{e(title or club)}"><meta property="og:description" content="{e(description)}">
<meta property="og:image" content="{e(og_abs)}"><meta property="og:type" content="{'article' if canonical and canonical.startswith('/news/') else 'website'}">
{f'<meta property="og:url" content="{e(url)}">' if url else ''}
{verify_tags(info) if slug == "" else ""}
<meta name="theme-color" content="#15122B">
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="icon" type="image/png" sizes="192x192" href="/static/icon-192.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
{ld}
{FONT_PRELOAD}
<style>{site_css()}</style>
{extra_head}
</head><body class="page-{e(slug or 'start')}">
<a class="skip" href="#inhalt">Zum Inhalt springen</a>
<header class="site-head">
  <a class="brand" href="/" aria-label="Zur Startseite"><img src="{LOGO}" alt="" width="47" height="52"><span>SV Amisia<small>Wolthusen e.V.</small></span></a>
  <input type="checkbox" id="menu" class="menu-toggle" aria-label="Menü öffnen">
  <label for="menu" class="menu-btn" aria-hidden="true"><span></span><span></span><span></span></label>
  <nav class="site-nav" aria-label="Hauptmenü">
      {nav_html(active if active is not None else slug or "start")}
  </nav>
</header>
<main id="inhalt" tabindex="-1">{maint_bar()}{notice_bar(info)}{body}</main>
<aside class="site-partner" aria-label="Premium-Partner">
  <p class="eyebrow">Premium- und Gesundheitspartner</p>
  <strong>Audi BKK</strong>
  <p>Offen für alle. Perfekt für dich. <a href="/partner">Mehr über unsere Partner</a></p>
</aside>
<footer class="site-foot">
  <div class="foot-grid">
    <div>
      <img class="foot-logo" src="{LOGO}" alt="Wappen {e(club)}" width="72" height="80" loading="lazy">
      <p><b style="color:#fff">{e(club)} e.V.</b></p>
      <p>Folkmar-Allena-Straße 13<br>26725 Emden-Wolthusen</p>
      {f'<p><a href="mailto:{e(mail)}">{e(mail)}</a></p>' if mail else ''}
    </div>
    <div>
      <h4>Sport</h4>
      <p><a href="/fussball">Fußball</a></p>
      <p><a href="/spielplan">Spielplan</a></p>
      <p><a href="/american-football">American Football</a></p>
      <p><a href="/turnen-gymnastik">Turnen &amp; Gymnastik</a></p>
    </div>
    <div>
      <h4>Verein</h4>
      <p><a href="/news">News</a></p>
      <p><a href="/mitglied-werden">Mitglied werden</a></p>
      <p><a href="/saal">Saal mieten</a></p>
      <p><a href="/partner">Partner</a></p>
      <p><a href="/kontakt">Kontakt</a></p>
    </div>
    <div>
      <h4>Folgen</h4>
      {social}
      <p><a href="/newsletter">Newsletter</a></p>
      <p><a class="members" href="/hub">Mitgliederbereich</a></p>
    </div>
  </div>
  <div class="copy">
    <span>© {datetime.now().year} {e(club)} e.V.</span>
    <span><a href="/impressum">Impressum</a> · <a href="/datenschutz">Datenschutz</a></span>
  </div>
</footer>
<script src="{asset('site.js')}" defer></script>
</body></html>"""


def section_head(eyebrow, title, more=""):
    return f'<div class="sec-head"><p class="eyebrow">{e(eyebrow)}</p><h2>{e(title)}</h2>{more}</div>'


# ---------------------------------------------------------------------------
# Bausteine: Spiele, Training, Personen
# ---------------------------------------------------------------------------
def team_of(x):
    return x.get("team") if x.get("team") in TEAMS else TEAMS[0]


def game_card(g, info):
    """Spielkarte: Heimmannschaft links, beide mit Logo und Name, Ergebnis in derselben Reihenfolge."""
    club = info.get("club_name") or "SV Amisia Wolthusen"
    o = (g.get("opponent") or {}).get("name") or "Gegner offen"
    home = g["home"]
    opp_logo = (g.get("opponent") or {}).get("logo")
    initials = "".join(w[0] for w in o.split()[:2]).upper() if g.get("opponent") else "?"
    us_t = f'<div class="team"><span class="t-logo"><img src="{LOGO}" alt="Wappen {e(club)}" width="47" height="52" loading="lazy"></span><b>Wolthusen</b></div>'
    them_t = ('<div class="team"><span class="t-logo">' + (f'<img src="{e(opp_logo)}" alt="Logo {e(o)}" loading="lazy">' if opp_logo else f'<i>{e(initials)}</i>')
              + f'</span><b>{e(o)}</b></div>')
    mid = '<span class="vs">:</span>'
    if g["score_us"] is not None:
        try:
            us, them = int(float(g["score_us"])), int(float(g["score_them"]))
            left, right = (us, them) if home else (them, us)
            cls = "win" if us > them else "loss" if us < them else "draw"
            mid = f'<span class="vs res {cls}">{left}:{right}</span>'
        except (TypeError, ValueError):
            pass
    teams = f"{us_t}{mid}{them_t}" if home else f"{them_t}{mid}{us_t}"
    league = g.get("league") or g.get("kind") or ""
    return f"""<article class="game {'home' if home else 'away'}">
      <div class="g-date"><b>{e(fmt_date(g['date'], True))}</b>{f'<span>{e(g["time"])} Uhr</span>' if g['time'] else ''}</div>
      <div class="g-teams">{teams}</div>
      <div class="g-meta"><span class="tag team">{e(team_of(g))}</span><span class="tag{' away' if not home else ''}">{'Heimspiel' if home else 'Auswärts'}</span>
        {f'<span>{e(league)}</span>' if league else ''}{f'<span>{e(g["location"])}</span>' if g['location'] else ''}</div>
      {f'<a class="stream" href="{e(g["stream"])}" target="_blank" rel="noopener">Livestream</a>' if g.get("stream") and g["score_us"] is None else ''}</article>"""


def upcoming(games, team=None, n=None):
    today = date.today().isoformat()
    up = [g for g in games if g["date"] >= today and (team is None or team_of(g) == team)]
    return up[:n] if n else up


def played(games, team=None, n=None):
    today = date.today().isoformat()
    done = [g for g in games if g["date"] < today and g["score_us"] is not None and (team is None or team_of(g) == team)][::-1]
    return done[:n] if n else done


def trainings_of(team):
    return [t for t in getattr(_ctx, "trainings", []) if t["team"] == team]


def training_list(rows, ph="Trainingszeiten"):
    if not rows:
        return f"<p>{placeholder(ph)}</p>"
    return '<ul class="info-list">' + "".join(
        f'<li><b>{e(t["weekday"][:2])}</b><span>{(e(t["start"]) + (" bis " + e(t["end"]) if t["end"] else "") + " Uhr") if t["start"] else "Uhrzeit folgt"}'
        f'{"<br><small>" + e(t["place"]) + "</small>" if t["place"] else ""}{"<br><small>" + e(t["season"]) + "</small>" if t["season"] else ""}</span></li>'
        for t in rows) + "</ul>"


def coaches_of(team, which):
    return sorted([p for p in team if p["kind"] != "Spieler" and p.get("team") == which],
                  key=lambda p: COACH_ROLES.index(p["role"]) if p["role"] in COACH_ROLES else 99)


def person_card(p, sub):
    name = f"{p['first_name']} {p['last_name']}".strip()
    img = (f'<img src="{e(p["photo"])}" alt="{e(name)}" loading="lazy" decoding="async">' if p.get("photo")
           else f'<div class="no-photo"><img src="{LOGO}" alt="" loading="lazy"></div>')
    num = f'<span class="num">{e(p["number"])}</span>' if p.get("number") and p["kind"] == "Spieler" else ""
    return f'<article class="person">{img}{num}<h3>{e(name)}</h3><p>{e(sub)}</p></article>'


def kader_html(players):
    """Spieler nach Position (Tor, Abwehr, Mittelfeld, Sturm), innerhalb nach Rückennummer."""
    key = lambda p: int(p["number"]) if str(p["number"]).isdigit() else 999
    out = []
    for pos in POSITIONS + [""]:
        ps = sorted((p for p in players if (p["position"] if p["position"] in POSITIONS else "") == pos), key=key)
        if ps:
            out.append(f'<h3 class="pos">{e(POS_PLURAL.get(pos) or "Weitere Spieler")}</h3><div class="people">'
                       + "".join(person_card(p, ", ".join(x for x in (POS_NAME.get(p["position"], ""), p.get("extra_role") or "") if x)) for p in ps) + "</div>")
    return "".join(out)


def home_maps_url(info):
    url = (info.get("site_home_maps_url") or "").strip()
    if url.startswith("https://") and not any(c in url for c in ' "<>'):
        return url
    q = info.get("site_home_address") or info.get("home_location") or ""
    return f"https://www.openstreetmap.org/search?query={q}" if q else ""


# ---------------------------------------------------------------------------
# Feste Seiten aus seiten/*.html
# ---------------------------------------------------------------------------
_SEITEN = {}


def seiten():
    """Alle festen Seiten: {slug: (meta, body)}; neu eingelesen, wenn sich eine Datei ändert."""
    files = sorted(SEITEN.glob("*.html"))
    stamp = tuple((f.name, f.stat().st_mtime) for f in files)
    if _SEITEN.get("stamp") != stamp:
        pages = {}
        for f in files:
            text = f.read_text(encoding="utf-8")
            m = re.match(r"\s*<!--\s*(\{.*?\})\s*-->\s*", text, re.S)
            if m:
                meta = json.loads(m.group(1))
                pages[meta["path"].strip("/")] = (meta, text[m.end():])
        _SEITEN.update(stamp=stamp, pages=pages)
    return _SEITEN["pages"]


def fill(body, info, data):
    """Platzhalter in den festen Seiten durch Bilder und Daten aus dem Hub ersetzen."""
    body = body.replace("{{SHIELD}}", SHIELD).replace("{{LOGO}}", LOGO)
    meta = image_meta()
    body = re.sub(r"\{\{BILD:([a-z0-9-]+)(?::([a-z-]+))?\}\}", lambda m: picture(m.group(1), "100vw" if m.group(2) == "hero-img" else "(min-width: 900px) 50vw, 100vw",
                                                                                     m.group(2) or "", eager=m.group(2) == "hero-img", meta=meta), body)
    tokens = {
        "{{HERO_TEXT}}": lambda: text_or_ph(info.get("site_hero_text"), "Satz unter der Überschrift"),
        "{{UEBER_UNS}}": lambda: paragraphs(info.get("site_about")) or placeholder("Vereinsvorstellung"),
        "{{DYNAMISCH}}": lambda: start_sections(info, data),
        "{{MANNSCHAFTEN}}": lambda: team_cards(TEAMS[:3]),
        "{{JUGEND}}": lambda: team_cards(TEAMS[3:], dark=True),
        "{{SQUADS}}": squads_html,
        "{{PARTNER}}": lambda: sponsor_tiles(data.get("sponsors") or [], fallback=True),
        "{{PARTNER_TEXT}}": lambda: text_or_ph(info.get("site_sponsor_text"), "Text Partner werden"),
        "{{BEITRAEGE_STAND}}": lambda: e(info.get("season") or ""),
    }
    for k, fn in tokens.items():
        if k in body:
            body = body.replace(k, fn())
    # {{TRAINING:Gruppe}}: Trainingszeiten einer Mannschaft oder Gruppe aus dem Hub (Hub > Trainingszeiten)
    return re.sub(r"\{\{TRAINING:([^}]{1,60})\}\}", lambda m: training_list(trainings_of(m.group(1)), "Trainingszeiten " + m.group(1)), body)


def team_cards(teams, dark=False):
    """Karten der Mannschaften mit Trainingszeiten und Trainern (Fußball-Seite)."""
    team = getattr(_ctx, "team", [])
    out = []
    for t in teams:
        tr = trainings_of(t)
        coach = coaches_of(team, t)
        who = ", ".join(f"{p['first_name']} {p['last_name']}".strip() for p in coach[:2])
        out.append(f"""<div class="card{' dark' if dark else ''} reveal"><p class="eyebrow">{e(TEAM_LEAD.get(t, ""))}</p><h3>{e(t)}</h3>
      {training_list(tr, "Trainingszeiten " + t)}
      <p class="person-line">{e(who) if who else placeholder("Trainer")}</p>
      <a class="more" href="/mannschaft/{TEAM_SLUG[t]}">Zur Mannschaft</a></div>""")
    return "".join(out)


def squads_html():
    rows = []
    for t, items in FUSSBALL_DE.items():
        for label, url in items:
            rows.append(f'<a class="squad" href="{e(url)}" target="_blank" rel="noopener"><div><b>{e(label)}</b><span>{e(t)}</span></div><i>fussball.de</i></a>')
    return f'<div class="squads reveal">{"".join(rows)}</div>'


def sponsor_tiles(sponsors, fallback=False):
    """Logos der aktiven Sponsoren aus dem Hub (Verein > Sponsoren). fallback: ohne Sponsoren die bekannten Partner als Text."""
    if not sponsors:
        return ('<div class="logo-row reveal"><div class="logo-tile">Audi BKK</div><div class="logo-tile">s-p Media</div>'
                f'<div class="logo-tile">{placeholder("Sponsoren im Hub anlegen")}</div></div>') if fallback else ""
    tiles = []
    for s in sponsors:
        inner = f'<img src="{e(s["logo"])}" alt="Logo {e(s["name"])}" loading="lazy">' if s["logo"] else e(s["name"])
        tiles.append(f'<a class="logo-tile" href="{e(s["website"])}" target="_blank" rel="noopener sponsored">{inner}</a>' if s["website"]
                     else f'<div class="logo-tile">{inner}</div>')
    return f'<div class="logo-row reveal">{"".join(tiles)}</div>'


def start_sections(info, data):
    """Abschnitte der Startseite aus dem Hub (Reihenfolge und Sichtbarkeit unter Webseite > Startseite)."""
    games, articles, sponsors, insta = data.get("games") or [], data.get("articles") or [], data.get("sponsors") or [], data.get("instagram") or []
    order = [k for k, visible in (getattr(_ctx, "layout", None) or [[k, True] for k in START_SECTIONS]) if visible and k in START_SECTIONS]
    nxt = upcoming(games, n=4)
    sec = {
        "spiele": f"""<section><div class="wrap reveal">{section_head("Spielplan", "Nächste Spiele", '<a class="more" href="/spielplan">Ganzer Spielplan</a>')}
  {f'<div class="games">{"".join(game_card(g, info) for g in nxt)}</div>' if nxt else '<p class="muted">Die nächsten Spieltage stehen hier, sobald sie feststehen. Alle Spiele findest du auch bei fussball.de.</p>'}</div></section>""",
        "ergebnisse": (f'''<section class="tone white"><div class="wrap reveal">{section_head("Ergebnisse", "Zuletzt gespielt", '<a class="more" href="/spielplan">Alle Ergebnisse</a>')}
  <div class="games">{"".join(game_card(g, info) for g in played(games, n=4))}</div></div></section>''' if played(games) else ""),
        "news": (f'''<section><div class="wrap reveal">{section_head("Aktuelles", "News", '<a class="more" href="/news">Alle News</a>')}
  <div class="news-grid">{"".join(news_card(a) for a in articles[:3])}</div></div></section>''' if articles else ""),
        "karte": card_promo(info),
        "sponsoren": (f'''<section class="tone white"><div class="wrap reveal">{section_head("Partner", "Unsere Partner", '<a class="more" href="/partner">Alle Partner</a>')}
  {sponsor_tiles(sponsors)}</div></section>''' if sponsors else ""),
        "instagram": instagram_grid(info, insta),
    }
    return "\n".join(sec[k] for k in order if sec.get(k))


def instagram_grid(info, insta):
    ig = (info.get("instagram") or "").lstrip("@")
    tiles = ([f'<a href="{e(i["url"])}" target="_blank" rel="noopener"><img src="{e(i["image"])}" alt="{e(i["alt"] or "Instagram-Beitrag")}" loading="lazy" decoding="async"></a>' for i in insta]
             or [f'<a href="https://www.instagram.com/{e(ig)}/" target="_blank" rel="noopener">{picture(k, "(min-width: 700px) 33vw, 100vw")}</a>' for k in photos("galerie-")[:6]])
    if not tiles or not ig:
        return ""
    return f"""<section class="tone dark"><div class="wrap reveal">{section_head("Instagram", "@" + ig)}
  <div class="insta">{"".join(tiles[:6])}</div>
  <p><a class="btn violet" href="https://www.instagram.com/{e(ig)}/" target="_blank" rel="noopener">Folge uns auf Instagram</a></p></div></section>"""


def card_promo(info):
    """Band Dauerkarte, nur solange die Online-Bestellung offen ist."""
    if info.get("site_card_order_open") != "1":
        return ""
    price = euro(info.get("card_price"))
    return f"""<section class="band">{SHIELD}<div class="wrap band-in reveal">
  <div><p class="eyebrow">Dauerkarte {e(info.get("season") or "")}</p><h2>Eine Karte. Alle Heimspiele.</h2>
    <p>{text_or_ph(info.get("site_card_short"), "Kurztext Dauerkarte")}{f" Für {e(price)} die ganze Saison." if price else ""}</p></div>
  <div class="btns"><a class="btn violet" href="/supporter-karte#bestellen">Jetzt bestellen</a></div></div></section>"""


def page_static(slug, info, data):
    meta, body = seiten()[slug]
    nav = meta.get("nav") or slug
    return layout(slug, meta["title"] if slug else "", seo_desc(info, slug, meta.get("description", "")), fill(body, info, data), info, active=nav)


# ---------------------------------------------------------------------------
# Dynamische Seiten
# ---------------------------------------------------------------------------
def page_team(info, slug, data):
    """Seite einer Mannschaft: Training, Trainer, Kader (nur Herren), Spiele, Ergebnisse, fussball.de."""
    t = SLUG_TEAM[slug]
    youth = t in YOUTH_TEAMS
    team, games = data.get("team") or [], data.get("games") or []
    coaches = coaches_of(team, t)
    players = [] if youth else [p for p in team if p["kind"] == "Spieler" and p.get("team") == t]
    nxt, done = upcoming(games, t, 6), played(games, t, 6)
    fde = "".join(f'<a class="squad" href="{e(u)}" target="_blank" rel="noopener"><div><b>{e(label)}</b><span>Spielplan und Tabelle</span></div><i>fussball.de</i></a>'
                  for label, u in FUSSBALL_DE.get(t, []))
    topic = "jugend" if youth else "herren"
    body = f"""<section class="page-hero">{picture("jugend" if youth else "herren", "100vw", "hero-img", eager=True)}{SHIELD}
  <div class="hero-text"><p class="eyebrow">{"Kinder- und Jugendfußball" if youth else "Herrenfußball"}</p><h1>{e(t)}</h1>
    <p class="lead">{e(TEAM_LEAD.get(t, ""))}</p>
    <div class="btns"><a class="btn violet" href="/kontakt?anliegen={topic}#formular">Probetraining anfragen</a><a class="btn ghost" href="#spiele">Spiele</a></div></div></section>
<section><div class="wrap cards">
  <div class="card reveal" id="training"><p class="eyebrow">Training</p><h3>Trainingszeiten</h3>{training_list(trainings_of(t), "Trainingszeiten " + t)}
    <p class="small muted">{e(info.get("site_training_address") or "")}</p></div>
  <div class="card dark reveal"><p class="eyebrow">Probetraining</p><h3>{"Dein Kind möchte mitspielen?" if youth else "Lust mitzuspielen?"}</h3>
    <p>{text_or_ph(info.get("site_trial_text"), "Hinweise zum Probetraining")}</p>
    <a class="btn violet" href="/kontakt?anliegen={topic}#formular">Probetraining anfragen</a></div>
</div></section>
<section class="tone white" id="trainer"><div class="wrap">{section_head("Trainer und Betreuer", "Ansprechpartner")}
  {f'<div class="people">{"".join(person_card(p, p["role"] or p["kind"]) for p in coaches)}</div>' if coaches else f'<p>{placeholder("Trainer " + t)}</p>'}</div></section>
{f'''<section id="kader"><div class="wrap">{section_head("Kader", "Saison " + (info.get("season") or ""))}{kader_html(players)}
  <p class="small muted">Fotos zeigen wir nur mit Einverständnis der Spieler.</p></div></section>''' if players else ''}
<section class="tone dark" id="spiele"><div class="wrap">{section_head("Spielplan", "Nächste Spiele", f'<a class="more" href="/spielplan#{slug}">Ganzer Spielplan</a>')}
  {f'<div class="games">{"".join(game_card(g, info) for g in nxt)}</div>' if nxt else '<p class="muted">Die nächsten Spiele stehen hier, sobald sie feststehen.</p>'}
  {f'<h3 class="pos">Ergebnisse</h3><div class="games">{"".join(game_card(g, info) for g in done)}</div>' if done else ''}
  {f'<div class="squads" style="margin-top:20px">{fde}</div>' if fde else ''}</div></section>"""
    desc = f"{t} des SV Amisia Wolthusen: Training, Trainer und Spiele." if youth else seo_desc(info, "mannschaft", f"{t} des SV Amisia Wolthusen: Kader, Trainer, Training und Spiele.")
    return layout("mannschaft/" + slug, t, desc, body, info, canonical=f"/mannschaft/{slug}", active="mannschaft")


def page_schedule(info, games):
    today = date.today().isoformat()
    def team_block(t):
        gs = [g for g in games if team_of(g) == t]
        if not gs:
            return ""
        up = [g for g in gs if g["date"] >= today]
        done = [g for g in gs if g["date"] < today][::-1]
        return (f'<section class="wrap" id="{TEAM_SLUG[t]}">{section_head("Spielplan", t, f"<a class=more href=/mannschaft/{TEAM_SLUG[t]}>Zur Mannschaft</a>")}'
                + (f'<h3 class="pos">Kommende Spiele</h3><div class="games">{"".join(game_card(g, info) for g in up)}</div>' if up else "")
                + (f'<h3 class="pos">Ergebnisse</h3><div class="games">{"".join(game_card(g, info) for g in done)}</div>' if done else "") + "</section>")
    blocks = "".join(team_block(t) for t in TEAMS)
    jump = "".join(f'<a class="btn sm ghost-dark" href="#{TEAM_SLUG[t]}">{e(t)}</a>' for t in TEAMS if any(team_of(g) == t for g in games))
    maps = home_maps_url(info)
    body = f"""<section class="page-hero">{picture("spielplan", "100vw", "hero-img", eager=True)}{SHIELD}<div class="hero-text"><p class="eyebrow">Saison {e(info.get("season"))}</p><h1>Spielplan</h1>
  <p class="lead">Alle Spiele und Ergebnisse unserer Mannschaften.</p></div></section>
{f'<section class="wrap jump-bar"><div class="btns">{jump}</div></section>' if jump else ''}
{blocks or '<section class="wrap"><p>Der Spielplan folgt in Kürze. Bis dahin findest du alle Spiele bei <a href="/fussball#spiele">fussball.de</a>.</p></section>'}
<section class="tone white"><div class="wrap cards">
  <div class="card"><p class="eyebrow">Heimspiele</p><h3>{e(info.get("home_location") or "") or placeholder("Heimspielort")}</h3>
    <p>{f'<a href="{e(maps)}" target="_blank" rel="noopener">{e(info["site_home_address"])}</a>' if info.get("site_home_address") and maps else text_or_ph(info.get("site_home_address"), "Adresse Sportplatz")}</p>
    {f"<p>Eintritt: {e(info.get('entry_fee'))} €</p>" if info.get("entry_fee") else ""}</div>
  <div class="card"><p class="eyebrow">Gut zu wissen</p><h3>Am Spieltag</h3><p>{text_or_ph(info.get("site_gameday_text"), "Infos zum Spieltag")}</p></div>
</div></section>"""
    return layout("spielplan", "Spielplan", seo_desc(info, "spielplan", "Spielplan und Ergebnisse aller Mannschaften des SV Amisia Wolthusen."), body, info)


def page_contact(info, sent=None, preselect=""):
    form_msg = {"ok": '<p class="msg ok">Danke! Deine Nachricht ist angekommen, wir melden uns bei dir.</p>',
                "fehler": '<p class="msg err">Das hat nicht geklappt. Bitte prüfe deine Angaben und versuche es noch einmal.</p>'}.get(sent, "")
    shown = [t for t in CONTACT_TOPICS if t[0] != CARD_TOPIC or info.get("site_card_order_open") == "1"]
    pick = next((v for v, short, _, _ in shown if short == preselect), shown[0][0])
    mail = (info.get("site_contact_email") or "").strip()
    topics = "".join(f'<label class="topic"><input type="radio" name="anliegen" value="{e(v)}" {"checked" if v == pick else ""}>'
                     f'<span><b>{e(label)}</b><small>{e(hint)}</small></span></label>' for v, _, label, hint in shown)
    body = f"""<section class="page-hero">{picture("mitglied", "100vw", "hero-img", eager=True)}{SHIELD}<div class="hero-text"><p class="eyebrow">Kontakt</p><h1>Schreib uns</h1>
  <p class="lead">Probetraining, Mitgliedschaft, Saal oder eine Frage zum Verein: Wir melden uns so schnell wie möglich.</p></div></section>
<section class="wrap contact-wrap" id="formular">
  <div class="contact-main">{section_head("Kontaktformular", "Deine Nachricht")}
    {form_msg}
    <form class="contact" method="post" action="/kontakt">
      <fieldset class="topics"><legend>Worum geht es?</legend>{topics}</fieldset>
      <div class="row2"><label>Name<input name="name" required maxlength="100" autocomplete="name"></label>
        <label>Telefon (optional)<input name="phone" maxlength="40" autocomplete="tel"></label></div>
      <label>E-Mail<input name="email" type="email" maxlength="150" autocomplete="email"></label>
      <label>Nachricht<textarea name="message" rows="6" required maxlength="3000" placeholder="Erzähl uns kurz, worum es geht."></textarea></label>
      <label class="hp" aria-hidden="true">Bitte leer lassen<input name="website" tabindex="-1" autocomplete="off"></label>
      <label class="check"><input type="checkbox" name="consent" value="1" required> <span>Ich bin einverstanden, dass meine Angaben zur Beantwortung meiner Anfrage gespeichert werden. Mehr in der <a href="/datenschutz">Datenschutzerklärung</a>.</span></label>
      <p class="small muted">E-Mail oder Telefon reicht. Für Kinder melden sich bitte die Eltern bei uns.</p>
      <div><button class="btn violet" type="submit">Nachricht senden</button></div>
    </form></div>
  <aside class="contact-side">
    <div class="side-box dark"><p class="eyebrow">Vereinsanschrift</p>
      <p><b>{e(info.get("club_name") or "SV Amisia Wolthusen")} e.V.</b><br>Folkmar-Allena-Straße 13<br>26725 Emden-Wolthusen</p>
      <p>E-Mail: {f'<a href="mailto:{e(mail)}">{e(mail)}</a>' if mail else placeholder("Kontakt-E-Mail")}</p></div>
    <div class="side-box"><p class="eyebrow">Mitgliedschaft</p><p><b>Ewgeni Witmaer</b><br>+49 176 34295414<br>e.witmaer@amisia-stern.de</p></div>
    <div class="side-box"><p class="eyebrow">Fußball und Camp</p><p><b>Bernhard Schönfelder</b><br>+49 172 9909694<br>b.schoenfelder@amisia-stern.de</p>
      <p><b>Andreas Gerdes</b><br>+49 171 4988356<br>a.gerdes@amisia-stern.de</p></div>
    <div class="side-box"><p class="eyebrow">Saal</p><p><b>Sabine Janßen</b><br>+49 160 4492107</p></div>
    <div class="side-box"><p class="eyebrow">Newsletter</p><p>News, Spieltage und Termine direkt ins Postfach.</p>
      <form class="foot-nl" action="/newsletter#anmelden" method="get"><input name="email" type="email" maxlength="150" placeholder="Deine E-Mail" aria-label="E-Mail-Adresse für den Newsletter" autocomplete="email" required>
        <button class="btn violet" type="submit">Abonnieren</button></form></div>
  </aside>
</section>"""
    return layout("kontakt", "Kontakt", seo_desc(info, "kontakt", "Kontakt zum SV Amisia Wolthusen."), body, info)


def process_html(text):
    steps, rest = [], []
    for row in str(text or "").replace("\r", "").split("\n"):
        m = re.match(r"\s*\d+[.)]\s+(.*)", row)
        if m:
            steps.append(f"<li>{e(m.group(1))}</li>")
        elif row.strip():
            rest.append(f"<p>{e(row.strip())}</p>")
    return (f'<ol class="steps">{"".join(steps)}</ol>' if steps else "") + "".join(rest)


CARD_ORDER_MAX = 10   # wie in server.py


def page_card_order(info, sent=None):
    """Dauerkarte online bestellen; Formular nur, wenn im Hub geöffnet (site_card_order_open)."""
    msg = {"ok": '<p class="msg ok">Danke für deine Bestellung! Du bekommst gleich eine Bestätigung mit den Daten für die Überweisung per E-Mail.</p>',
           "fehler": '<p class="msg err">Das hat nicht geklappt. Bitte prüfe deine Angaben (bei Lieferung per Post auch die Anschrift) und versuche es noch einmal.</p>',
           "geschlossen": '<p class="msg err">Die Online-Bestellung ist gerade geschlossen.</p>'}.get(sent, "")
    price, season = info.get("card_price"), info.get("season")
    ship = info.get("card_shipping") or "0"
    ship_reg = info.get("card_shipping_registered") or "0"
    is_open = info.get("site_card_order_open") == "1"
    holders = "".join(f'<label class="holder" data-n="{n}">Name auf Karte {n}<input name="holder{n}" maxlength="100"></label>' for n in range(1, CARD_ORDER_MAX + 1))
    form = f"""<form class="contact card-order" method="post" action="/supporter-karte" data-price="{e(price)}" data-ship="{e(ship)}" data-ship-reg="{e(ship_reg)}">
      <fieldset><legend>1. Karten</legend>
      <div class="row2"><label>Anzahl Karten<select name="count">{"".join(f'<option value="{n}">{n}</option>' for n in range(1, CARD_ORDER_MAX + 1))}</select></label>
        <p class="small field-note">Jede Karte ist persönlich. Trag bitte für jede Karte einen Namen ein. Leere Felder füllen wir mit deinem Namen.</p></div>
      <div class="holders">{holders}</div></fieldset>
      <fieldset><legend>2. Lieferung</legend>
      <label class="check"><input type="radio" name="delivery" value="einlass" checked> Abholung an der Kasse beim Heimspiel (kostenlos)</label>
      <label class="check"><input type="radio" name="delivery" value="post"> Versand per Post als normaler Brief (+ {e(euro(ship))} pro Bestellung)</label>
      <label class="check"><input type="radio" name="delivery" value="einschreiben"> Versand per Einschreiben mit Sendungsnummer (+ {e(euro(ship_reg))} pro Bestellung)</label>
      <div class="address"><p class="small">Anschrift für den Versand (nur bei Versand per Post oder Einschreiben nötig)</p>
        <label>Straße und Hausnummer<input name="street" maxlength="120" autocomplete="street-address"></label>
        <div class="row2"><label>PLZ<input name="zip" maxlength="5" inputmode="numeric" pattern="[0-9]{{4,5}}" autocomplete="postal-code"></label>
          <label>Ort<input name="city" maxlength="80" autocomplete="address-level2"></label></div></div></fieldset>
      <fieldset><legend>3. Deine Kontaktdaten</legend>
      <label>Dein Name (Besteller, Rechnungsempfänger)<input name="name" required maxlength="100" autocomplete="name"></label>
      <div class="row2"><label>E-Mail<input name="email" type="email" required maxlength="150" autocomplete="email"></label>
        <label>Telefon (optional)<input name="phone" maxlength="40" autocomplete="tel"></label></div>
      <label>Nachricht (optional)<textarea name="message" rows="3" maxlength="1000"></textarea></label></fieldset>
      <label class="hp" aria-hidden="true">Bitte leer lassen<input name="website" tabindex="-1" autocomplete="off"></label>
      <div class="order-sum" aria-live="polite"><p class="eyebrow">Deine Bestellung</p>
        <p data-sum>{f"Pro Karte {e(euro(price))}, Versand per Post einmalig {e(euro(ship))}, per Einschreiben {e(euro(ship_reg))}." if price else placeholder("Preis")}</p></div>
      <label class="check"><input type="checkbox" name="consent" value="1" required> <span>Ich bin einverstanden, dass meine Angaben zur Bearbeitung der Bestellung gespeichert werden. Mehr in der <a href="/datenschutz">Datenschutzerklärung</a>.</span></label>
      <div class="order-terms"><p class="eyebrow">Wichtige Hinweise</p><p>{text_or_ph(info.get("site_card_terms"), "Hinweise zu Widerruf und Spielausfall")}</p>
        {f'<p>{lines(info.get("site_card_cancel_text"))}</p>' if (info.get("site_card_cancel_text") or "").strip() else ""}</div>
      <div><button class="btn violet" type="submit">Zahlungspflichtig bestellen</button></div>
    </form>""" if is_open else '<p>Die Online-Bestellung ist gerade geschlossen. Schreib uns gern über das <a href="/kontakt?anliegen=frage#formular">Kontaktformular</a>.</p>'
    body = f"""<section class="page-hero">{picture("herren", "100vw", "hero-img", eager=True)}{SHIELD}<div class="hero-text"><p class="eyebrow">Dauerkarte {e(season)}</p><h1>Sei dabei</h1>
  <p class="lead">{f"{e(euro(price))} für die ganze Saison" if price else ""}</p></div></section>
<section class="wrap contact-wrap" id="bestellen">
  <div class="contact-main">{section_head("Online bestellen", "Deine Dauerkarte")}{msg}{form}</div>
  <aside class="contact-side">
    <div class="side-box dark"><p class="eyebrow">Dauerkarte {e(season)}</p><p><b class="big-price">{e(euro(price)) if price else placeholder("Preis")}</b><br>pro Karte und Saison</p></div>
    <div class="side-box"><p class="eyebrow">Was du bekommst</p><p>{text_or_ph(info.get("site_card_text"), "Leistungen der Dauerkarte")}</p></div>
    <div class="side-box"><p class="eyebrow">So geht es weiter</p><p>{text_or_ph(info.get("site_card_order_text"), "Hinweis zu Bezahlung und Abholung")}</p></div>
  </aside>
</section>
<section class="wrap" id="ablauf">{section_head("Bestellung", "So läuft die Bestellung ab")}
  {process_html(info.get("site_card_process")) if (info.get("site_card_process") or "").strip() else placeholder("Ablauf der Bestellung")}
  <p>{lines(info.get("site_card_delivery_text"))}</p></section>"""
    return layout("supporter-karte", "Dauerkarte", f"Dauerkarte {season} des SV Amisia Wolthusen online bestellen.", body, info, noindex=not is_open, active="")


def page_player_form(info, f):
    """Spielerbogen für Spieler, Trainer und Betreuer der Herren: erst Passwort, dann Formular. Nicht in Menü und Sitemap."""
    state = f.get("state")
    if state == "geschlossen":
        main, title = '<p>Der Spielerbogen ist gerade nicht freigeschaltet. Frag bitte in der Mannschaft nach.</p>', "Spielerbogen"
    elif state == "danke":
        main, title = ('<p class="msg ok">Danke! Deine Angaben sind angekommen. Wir prüfen sie und tragen sie in den Kader ein.</p>'
                       '<p><a href="/spielerbogen">Noch einen Bogen ausfüllen</a></p>'), "Danke"
    elif state == "passwort":
        main = (('<p class="msg err">Das Passwort stimmt nicht.</p>' if f.get("error") else '')
                + """<p>Dieser Bogen ist nur für Spieler, Trainer und Betreuer des SV Amisia Wolthusen. Das Passwort bekommst du in der Mannschaft.</p>
  <form class="contact" method="post" action="/spielerbogen">
    <label>Passwort<input name="pw" type="password" required autocomplete="current-password" maxlength="200"></label>
    <div><button class="btn violet" type="submit">Weiter</button></div></form>""")
        title = "Spielerbogen"
    else:
        pos = "".join(f'<option value="{e(k)}">{e(v)}</option>' for k, v in POS_NAME.items())
        roles = "".join(f'<option value="{e(r)}">' for r in COACH_ROLES)
        teams = "".join(f'<option value="{e(t)}">{e(t)}{" (nur Trainer und Betreuer)" if t in YOUTH_TEAMS else ""}</option>' for t in TEAMS)
        main = (('<p class="msg err">Bitte prüfe deine Angaben: Vor- und Nachname, Art, E-Mail und Telefon sind Pflicht. '
                 'Spieler der Jugend tragen wir nicht über diesen Bogen ein.</p>' if f.get("invalid") else '')
                + f"""<form class="contact player-form" method="post" action="/spielerbogen">
  <fieldset class="choice"><legend>Ich bin</legend>
    <label><input type="radio" name="kind" value="Spieler" checked> Spieler</label>
    <label><input type="radio" name="kind" value="Coach"> Trainer</label>
    <label><input type="radio" name="kind" value="Staff"> Betreuer (z. B. Physio, Zeugwart)</label></fieldset>
  <label>Mannschaft<select name="team">{teams}</select></label>
  <div class="row2"><label>Vorname<input name="first_name" required maxlength="60" autocomplete="given-name"></label>
    <label>Nachname<input name="last_name" required maxlength="60" autocomplete="family-name"></label></div>
  <label>Spitzname (optional)<input name="nickname" maxlength="40"></label>
  <div class="row2"><label>Rückennummer (Spieler)<input name="number" inputmode="numeric" maxlength="3" pattern="[0-9]{{1,3}}"></label>
    <label>Position (Spieler)<select name="position"><option value="">Bitte wählen</option>{pos}</select></label></div>
  <label>Rolle (Trainer und Betreuer) oder Zusatzrolle (Spieler, optional)<input name="role" list="pf_roles" maxlength="60"></label>
  <datalist id="pf_roles">{roles}</datalist>
  <label>Instagram (optional)<input name="instagram" maxlength="60" placeholder="@deinname"></label>
  <div class="row2"><label>E-Mail<input name="email" type="email" required maxlength="150" autocomplete="email"></label>
    <label>Telefon<input name="phone" type="tel" required maxlength="40" autocomplete="tel"></label></div>
  <p class="small muted">E-Mail und Telefon bleiben intern im Verein und erscheinen nie auf der Webseite.</p>
  <label>Dabei seit (optional)<input name="since" maxlength="20" placeholder="z. B. 2023"></label>
  <label>Nachricht an uns (optional)<textarea name="message" rows="2" maxlength="1000"></textarea></label>
  <label class="hp" aria-hidden="true">Bitte leer lassen<input name="website" tabindex="-1" autocomplete="off"></label>
  <label class="check"><input type="checkbox" name="consent" value="1"> <span>Ich bin einverstanden, dass der SV Amisia Wolthusen mein Foto sowie Name, Spitzname, Rückennummer, Position bzw. Rolle
    und Instagram-Namen auf der Webseite und in den Social-Media-Kanälen des Vereins zeigt. Freiwillig und jederzeit widerrufbar.
    Bei unter 18-Jährigen nur mit Zustimmung der Erziehungsberechtigten.</span></label>
  <p class="small muted">Mehr zum Umgang mit deinen Daten in der <a href="/datenschutz">Datenschutzerklärung</a>.</p>
  <div><button class="btn violet" type="submit">Absenden</button></div>
</form>""")
        title = "Spielerbogen"
    body = f"""<section class="page-hero">{picture("herren", "100vw", "hero-img", eager=True)}<div class="hero-text"><p class="eyebrow">Kader &amp; Trainer</p><h1>{e(title)}</h1></div></section>
<section class="wrap contact-wrap"><div class="contact-main">{main}</div></section>"""
    return layout("spielerbogen", title, "Spielerbogen für Spieler, Trainer und Betreuer.", body, info, extra_head='<meta name="robots" content="noindex, nofollow">', active="")


def page_helpers(info, h):
    """Heimspieltag: Helfer tragen sich über den geheimen Link ein (nur Vornamen der anderen sichtbar, nicht in Menü, Sitemap und Google)."""
    gd, token, sent = h.get("gd"), h.get("token") or "", h.get("sent") or ""
    if not gd:
        main, title = '<p>Dieser Link gilt nicht mehr, zum Beispiel weil das Spiel vorbei ist oder die Liste geschlossen wurde. Frag bitte im Verein nach.</p>', "Helfer"
    else:
        try:
            d = date.fromisoformat(gd["date"])
            when = f'{WD[d.weekday()]}, {d.strftime("%d.%m.%Y")}'
        except ValueError:
            when = gd["date"]
        msg = {"ok": '<p class="msg ok">Danke! Du bist eingetragen. Wir freuen uns auf dich.</p>',
               "voll": '<p class="msg err">Die gewählte Aufgabe ist inzwischen voll. Bitte wähle eine andere.</p>',
               "fehler": '<p class="msg err">Das hat nicht geklappt. Bitte gib deinen Namen an, wähle mindestens eine Aufgabe und bestätige den Hinweis.</p>'}.get(sent, "")
        rows = []
        for sh in gd["shifts"]:
            free = sh["slots"] - len(sh["names"])
            t = f'{e(sh["start"])}{" bis " + e(sh["end"]) if sh["end"] else ""} Uhr' if sh["start"] else ""
            who = ", ".join(e(n) for n in sh["names"])
            box = (f'<input type="checkbox" name="schicht" value="{sh["id"]}">' if free > 0 else '<input type="checkbox" disabled>')
            state = "voll" if free <= 0 else ("1 Platz frei" if free == 1 else f"{free} Plätze frei")
            note = f'<small>{e(sh["notes"])}</small>' if sh["notes"] else ""
            dabei = f'<small class="gd-who">Dabei: {who}</small>' if who else ""
            rows.append(f'<label class="gd-shift{" full" if free <= 0 else ""}">{box}<span><b>{e(sh["role"])}</b><small>{t}{" · " if t else ""}{state}</small>{note}{dabei}</span></label>')
        shifts = "".join(rows) or '<p>Für dieses Spiel sind noch keine Aufgaben angelegt.</p>'
        main = f"""<p class="lead-dark">Heimspiel {e(gd["team"])}{" gegen " + e(gd["opponent"]) if gd["opponent"] else ""}<br><b>{e(when)}{", Anstoß " + e(gd["time"]) + " Uhr" if gd["time"] else ""}</b>{"<br>" + e(gd["location"]) if gd["location"] else ""}</p>
  <p>Ohne Helfer kein Spieltag. Such dir eine oder mehrere Aufgaben aus und trag dich ein. Danke!</p>
  {msg}
  <form class="contact" method="post" action="/helfer/{e(token)}" id="eintragen">
    <fieldset class="gd-shifts"><legend>Aufgaben</legend>{shifts}</fieldset>
    <div class="row2"><label>Vor- und Nachname<input name="name" required maxlength="80" autocomplete="name"></label>
      <label>Telefon (optional, für Rückfragen)<input name="phone" type="tel" maxlength="40" autocomplete="tel"></label></div>
    <label class="hp" aria-hidden="true">Bitte leer lassen<input name="website" tabindex="-1" autocomplete="off"></label>
    <label class="check"><input type="checkbox" name="consent" value="1" required> <span>Ich bin einverstanden, dass der Verein meinen Namen und meine Telefonnummer für die Planung des Spieltags speichert.
      Andere mit diesem Link sehen nur meinen Vornamen. Mehr in der <a href="/datenschutz">Datenschutzerklärung</a>.</span></label>
    <div><button class="btn violet" type="submit">Eintragen</button></div>
    <p class="small muted">Austragen oder Fragen: kurz im Verein Bescheid geben oder über das <a href="/kontakt?anliegen=frage#formular">Kontaktformular</a>.</p>
  </form>"""
        title = "Helfer am Heimspieltag"
    body = f"""<section class="page-hero">{picture("mitglied", "100vw", "hero-img", eager=True)}<div class="hero-text"><p class="eyebrow">Heimspieltag</p><h1>{e(title)}</h1></div></section>
<section class="wrap contact-wrap"><div class="contact-main">{main}</div></section>"""
    return layout("helfer", title, "Helfer für den Heimspieltag des SV Amisia Wolthusen.", body, info, extra_head='<meta name="robots" content="noindex, nofollow">', active="")


def page_newsletter(info, n):
    """Newsletter: anmelden (Themen und Einwilligung), bestätigen und abmelden (nur über Knopf, damit Linkprüfer in Mailprogrammen nichts auslösen)."""
    mode = n.get("mode") or "form"
    msgs = {"ok": '<p class="msg ok">Fast geschafft! Wir haben dir eine E-Mail geschickt. Bitte bestätige darin deine Anmeldung, erst dann bekommst du den Newsletter.</p>',
            "fehler": '<p class="msg err">Das hat nicht geklappt. Bitte gib eine gültige E-Mail-Adresse an und bestätige die Einwilligung.</p>',
            "gruppe": '<p class="msg err">Bitte wähle mindestens ein Thema aus.</p>',
            "bestaetigt": '<p class="msg ok">Danke! Deine Anmeldung ist bestätigt. Du bekommst ab jetzt unseren Newsletter.</p>',
            "abgemeldet": '<p class="msg ok">Du bist abgemeldet und bekommst keinen Newsletter mehr.</p>',
            "abgelaufen": '<p class="msg err">Dieser Bestätigungslink ist abgelaufen oder wurde schon benutzt. Melde dich einfach noch einmal an.</p>'}
    if mode == "confirm":
        title = "Anmeldung bestätigen"
        main = (f'<p>Bitte bestätige mit dem Knopf, dass du unseren Newsletter erhalten möchtest.</p><form method="post" action="/newsletter/bestaetigen/{e(n.get("token", ""))}">'
                '<button class="btn violet" type="submit">Anmeldung bestätigen</button></form>' if n.get("valid") else msgs["abgelaufen"] + '<p><a class="more" href="/newsletter#anmelden">Zur Anmeldung</a></p>')
    elif mode == "unsub":
        title = "Newsletter abbestellen"
        main = (f'<p>Möchtest du unseren Newsletter wirklich abbestellen? Du kannst dich jederzeit wieder anmelden.</p><form method="post" action="/newsletter/abmelden/{e(n.get("token", ""))}">'
                '<button class="btn violet" type="submit">Newsletter abbestellen</button></form>' if n.get("valid")
                else '<p class="msg err">Dieser Abmeldelink stimmt nicht. Bitte nutze den Link aus einer aktuellen Ausgabe oder schreib uns über das <a href="/kontakt?anliegen=frage#formular">Kontaktformular</a>.</p>')
    else:
        title = "Newsletter"
        groups = n.get("groups") or []
        choose = "".join(f'<label class="topic"><input type="checkbox" name="gruppe" value="{g["id"]}"><span><b>{e(g["name"])}</b>'
                         + (f'<small>{e(g["description"])}</small>' if g["description"] else "") + '</span></label>' for g in groups)
        main = f"""<p>Neuigkeiten, Spieltage, Termine und Infos aus dem Verein direkt in dein Postfach. Kein Spam, abbestellen geht jederzeit mit einem Klick.</p>
  {msgs.get(n.get("sent") or "", "")}
  <form class="contact" method="post" action="/newsletter" id="anmelden">
    {f'<fieldset class="topics"><legend>Welche Themen interessieren dich?</legend>{choose}</fieldset>' if groups else ''}
    <div class="row2"><label>E-Mail<input name="email" type="email" required maxlength="150" autocomplete="email" value="{e(n.get("email", ""))}"></label>
      <label>Vorname (optional)<input name="name" maxlength="80" autocomplete="given-name"></label></div>
    <label class="hp" aria-hidden="true">Bitte leer lassen<input name="website" tabindex="-1" autocomplete="off"></label>
    <label class="check"><input type="checkbox" name="consent" value="1" required> <span>{e(NL_CONSENT)} Mehr in der <a href="/datenschutz">Datenschutzerklärung</a>.</span></label>
    <div><button class="btn violet" type="submit">Newsletter abonnieren</button></div>
    <p class="small muted">Du bekommst gleich eine E-Mail mit einem Bestätigungslink. Erst nach dem Klick bist du angemeldet.</p>
  </form>"""
    body = f"""<section class="page-hero">{picture("mitglied", "100vw", "hero-img", eager=True)}{SHIELD}<div class="hero-text"><p class="eyebrow">Immer auf dem Laufenden</p><h1>{e(title)}</h1></div></section>
<section class="wrap contact-wrap"><div class="contact-main">{main}</div></section>"""
    return layout("newsletter", title, "Newsletter des SV Amisia Wolthusen: Spieltage, News und Termine per E-Mail.", body, info, active="mitglied")


def page_card_cancel(info, c):
    """Storno-Seite aus dem Link der Bestätigungsmail; nur Bestellnummer, Anzahl, Lieferart und Betrag, keine Namen."""
    state = c.get("state")
    contact = '<a href="/kontakt?anliegen=frage#formular">Kontaktformular</a>'
    summary = (f'<div class="side-box"><p class="eyebrow">Bestellung {e(c.get("order_no"))}</p>'
               f'<p>{e(c.get("count"))} x Dauerkarte {e(c.get("season"))}<br>{e(c.get("delivery"))}<br><b>Gesamt: {e(c.get("total"))}</b></p></div>'
               if c.get("order_no") else "")
    if state == "offen":
        main = (f"""<p>Du kannst diese Bestellung bis zum Eingang deiner Zahlung kostenlos stornieren. Danach ist die Bestellung aufgehoben,
  du musst nichts überweisen und die Karten werden nicht ausgestellt.</p>
  <p class="small">Falls du schon überwiesen hast, wir die Zahlung aber noch nicht verbucht haben, erstatten wir dir den Betrag. Melde dich dann bitte kurz bei uns.</p>
  <form class="contact" method="post" action="/supporter-karte/storno/{e(c.get('token'))}"><input type="hidden" name="confirm" value="1">
  <div><button class="btn violet" type="submit">Bestellung kostenlos stornieren</button></div></form>""")
        title = "Bestellung stornieren"
    elif state == "erledigt":
        main, title = '<p class="msg ok">Deine Bestellung ist storniert. Du bekommst gleich eine Bestätigung per E-Mail und musst nichts mehr überweisen.</p>', "Bestellung storniert"
    elif state == "storniert":
        main, title = '<p class="msg ok">Diese Bestellung ist bereits storniert. Du musst nichts mehr tun.</p>', "Bestellung storniert"
    elif state == "bezahlt":
        main = (f'<p class="msg err">Deine Zahlung ist bereits bei uns eingegangen, darum ist eine Stornierung über diesen Link nicht mehr möglich.</p>'
                f'<p>Wenn du eine Frage zu deiner Bestellung hast, schreib uns gern über das {contact}.</p>')
        title = "Stornierung nicht mehr möglich"
    elif state == "limit":
        main, title = '<p class="msg err">Zu viele Versuche. Bitte versuche es später noch einmal.</p>', "Bitte später noch einmal"
    else:
        main = f'<p class="msg err">Dieser Link ist ungültig. Bitte nutze den Link aus deiner Bestellbestätigung oder schreib uns über das {contact}.</p>'
        title = "Link ungültig"
    body = f"""<section class="page-hero">{picture("herren", "100vw", "hero-img", eager=True)}<div class="hero-text"><p class="eyebrow">Dauerkarte</p><h1>{e(title)}</h1></div></section>
<section class="wrap contact-wrap"><div class="contact-main">{main}</div><aside class="contact-side">{summary}</aside></section>"""
    head = '<meta name="robots" content="noindex, nofollow"><meta name="referrer" content="no-referrer">'
    return layout("supporter-karte", title, "Bestellung der Dauerkarte stornieren.", body, info, extra_head=head, active="")


# ---------------------------------------------------------------------------
# Link-Seite (/links für die Instagram-Bio) und Wartungsseite
# ---------------------------------------------------------------------------
def page_links(data):
    info = data.get("info") or {}
    club = info.get("club_name") or "SV Amisia Wolthusen"
    meta = image_meta()
    name = next((n for n in ("hero", "verein") if (meta.get(n) or {}).get("src") or (IMG / f"{n}-1280.webp").is_file()), "")
    bg = picture(name, "100vw", "maint-img", eager=True, meta=meta) if name else ""

    def btn(x):
        ext = x["url"].startswith("https://")
        return f'<a class="lt-link{" hot" if x.get("hot") else ""}" href="{e(x["url"])}"' + (' target="_blank" rel="noopener"' if ext else "") + f'>{e(x["label"])}</a>'
    links = "".join(btn(x) for x in data.get("links") or [])
    social = "".join(f'<a href="{e(s["url"])}" target="_blank" rel="noopener" aria-label="{SOCIAL_ICONS[s["kind"]][0]}" title="{SOCIAL_ICONS[s["kind"]][0]}">'
                     f'<svg viewBox="0 0 24 24" aria-hidden="true">{SOCIAL_ICONS[s["kind"]][1]}</svg></a>'
                     for s in (data.get("nav") or {}).get("social", []) if s.get("kind") in SOCIAL_ICONS)
    return f"""<!doctype html>
<html lang="de"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Links | {e(club)}</title>
<meta name="description" content="Alle Links des {e(club)}.">
<meta name="robots" content="noindex, nofollow">
<meta name="theme-color" content="#15122B">
<link rel="icon" href="/favicon.ico" sizes="any"><link rel="apple-touch-icon" href="/apple-touch-icon.png">
{FONT_PRELOAD}
<style>{site_css()}</style>
</head><body class="page-links">
<main id="inhalt" class="lt">
  <div class="maint-bg">{bg}</div>
  <div class="lt-box">
    <a href="/" aria-label="{e(club)} Startseite"><img class="lt-logo" src="{LOGO}" alt="Wappen {e(club)}" width="128" height="144"></a>
    <h1>{e(club)}</h1>
    <p class="lt-sub">Sportverein in Emden-Wolthusen</p>
    <nav class="lt-links" aria-label="Links">{links or '<p class="lt-sub">Hier stehen bald unsere Links.</p>'}</nav>
    {f'<p class="lt-social">{social}</p>' if social else ''}
  </div>
  <footer class="maint-foot"><span>© {datetime.now().year} {e(club)}</span>
    <a href="/">Webseite</a><a href="/impressum">Impressum</a><a href="/datenschutz">Datenschutz</a></footer>
</main>
</body></html>"""


def maint_until_text(v):
    v = (v or "").strip()
    try:
        if len(v) == 10:
            return fmt_date(v, weekday=True)
        dt = datetime.fromisoformat(v[:16])
        return f"{fmt_date(dt.date().isoformat(), weekday=True)}, {dt.hour:02d}:{dt.minute:02d} Uhr"
    except ValueError:
        return ""


def page_maintenance(data):
    """Eigene Seite im Wartungsmodus: Vollbild mit Bild, Wappen, Text aus dem Hub. Ohne Navigation, nicht für Suchmaschinen."""
    info, m = data.get("info") or {}, data.get("maint") or {}
    club = info.get("club_name") or "SV Amisia Wolthusen"
    meta = image_meta()
    name = next((n for n in (MAINT_SLOT, "hero", "verein") if (meta.get(n) or {}).get("src")
                 or (n != MAINT_SLOT and (IMG / f"{n}-1280.webp").is_file())), "")
    bg = picture(name, "100vw", "maint-img", eager=True, meta=meta) if name else ""
    ig = (info.get("instagram") or "").lstrip("@")
    mail = (info.get("site_contact_email") or "").strip()
    until = maint_until_text(m.get("until"))
    title = (m.get("title") or "").strip() or "Wir sind gleich wieder da"
    btns = ""
    if ig:
        btns += f'<a class="btn violet" href="https://www.instagram.com/{e(ig)}/" target="_blank" rel="noopener">Instagram @{e(ig)}</a>'
    if mail:
        btns += f'<a class="btn ghost" href="mailto:{e(mail)}">E-Mail schreiben</a>'
    preview = '<p class="maint-preview">Vorschau der Wartungsseite <a href="/">Zurück zur Webseite</a></p>' if m.get("preview") else ""
    return f"""<!doctype html>
<html lang="de"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)} | {e(club)}</title>
<meta name="description" content="{e(club)}: Die Webseite wird gerade gewartet.">
<meta name="robots" content="noindex">
<meta name="theme-color" content="#15122B">
<link rel="icon" href="/static/icon.png">
{FONT_PRELOAD}
<style>{site_css()}</style>
</head><body class="page-wartung">
{preview}
<main id="inhalt" class="maint">
  <div class="maint-bg">{bg}</div>
  <div class="maint-box">
    <img class="maint-logo" src="{LOGO}" alt="Wappen {e(club)}" width="128" height="144">
    <p class="eyebrow">Wartungsarbeiten</p>
    <h1>{e(title)}</h1>
    <p class="maint-text">{lines(m.get("text"))}</p>
    {f'<p class="maint-until">Voraussichtlich wieder da: <b>{e(until)}</b></p>' if until else ''}
    {f'<div class="btns">{btns}</div>' if btns else ''}
  </div>
  <footer class="maint-foot"><span>© {datetime.now().year} {e(club)}</span>
    <a href="/impressum">Impressum</a><a href="/datenschutz">Datenschutz</a><a href="/login">Mitgliederbereich</a></footer>
</main>
</body></html>"""


# ---------------------------------------------------------------------------
# Rechtliches
# ---------------------------------------------------------------------------
def legal_inline(t):
    """Eine Zeile Rechtstext: escapen, [Platzhalter] gelb markieren, Adressen und E-Mails verlinken."""
    out, pos = [], 0
    pat = re.compile(r"\[[^\]\n]{1,200}\]|https?://[^\s<>\"')]+[^\s<>\"').,;:]|[\w.+-]+@[\w-]+(?:\.[\w-]+)+|(?<![\w/])/(?:kontakt|impressum|datenschutz)\b")
    for m in pat.finditer(t):
        out.append(e(t[pos:m.start()]))
        x = m.group(0)
        if x.startswith("["):
            out.append(f'<span class="ph">{e(x[1:-1])}</span>')
        elif "@" in x and not x.startswith("http"):
            out.append(f'<a href="mailto:{e(x)}">{e(x)}</a>')
        elif x.startswith("/"):
            out.append(f'<a href="{e(x)}">{e(x)}</a>')
        else:
            out.append(f'<a href="{e(x)}" target="_blank" rel="noopener">{e(x)}</a>')
        pos = m.end()
    out.append(e(t[pos:]))
    return "".join(out)


def legal_html(text, info):
    """Rechtstext aus dem Hub: "## " Überschrift, "### " Unterüberschrift, "- " Liste, Leerzeile = Absatz. Kein HTML aus dem Hub."""
    ig = (info.get("instagram") or "").lstrip("@")
    text = str(text or "").replace("\r", "").replace("{E-Mail}", (info.get("site_contact_email") or "").strip() or "[Kontakt-E-Mail]")
    text = text.replace("{Instagram}", f"https://www.instagram.com/{ig}/" if ig else "[Instagram-Profil]")
    out = []
    for block in re.split(r"\n\s*\n", text):
        rows = [r.rstrip() for r in block.strip().split("\n") if r.strip()]
        if not rows:
            continue
        if rows[0].startswith("### "):
            out.append(f"<h3>{legal_inline(rows[0][4:])}</h3>"); rows = rows[1:]
        elif rows[0].startswith("## "):
            out.append(f"<h2>{legal_inline(rows[0][3:])}</h2>"); rows = rows[1:]
        if rows and all(r.lstrip().startswith("- ") for r in rows):
            out.append("<ul>" + "".join(f"<li>{legal_inline(r.lstrip()[2:])}</li>" for r in rows) + "</ul>")
        elif rows:
            out.append("<p>" + "<br>".join(legal_inline(r) for r in rows) + "</p>")
    return "".join(out)


def page_legal(slug, info):
    title, key = LEGAL[slug]
    text = info.get(key) or ""
    content = legal_html(text, info) if text.strip() else f"<p>{placeholder(title)}</p>"
    body = f'<section class="wrap narrow legal"><p class="eyebrow">Rechtliches</p><h1>{e(title)}</h1><div class="legal-text">{content}</div></section>'
    return layout(slug, title, f"{title} des SV Amisia Wolthusen e.V.", body, info, active="")


def page_404(info):
    body = f"""<section class="hero" style="min-height:60svh">{SHIELD}<div class="hero-text"><p class="eyebrow">Fehler 404</p>
  <h1><span>Ins Aus</span><span>geschossen.</span></h1><p class="lead">Diese Seite gibt es nicht oder nicht mehr.</p>
  <div class="btns"><a class="btn violet" href="/">Zur Startseite</a><a class="btn ghost" href="/kontakt">Kontakt</a></div></div></section>"""
    return layout("404", "Nicht gefunden", "", body, info, noindex=True, active="")


# Öffentliche Seiten mit eigener Adresse /<slug> (die festen aus seiten/ kommen dazu)
DYNAMIC_PAGES = ("spielplan", "news", "kontakt", "supporter-karte", "impressum", "datenschutz", "newsletter")
PAGES = ("", "fussball", "american-football", "turnen-gymnastik", "saal", "partner", "mitglied-werden") + DYNAMIC_PAGES


# ---------------------------------------------------------------------------
# News: Liste, Einzelartikel, Karten für die Startseite
# ---------------------------------------------------------------------------
class _HtmlFilter(HTMLParser):
    """Lässt nur einfache Textauszeichnung durch (Absätze, Überschriften, Listen, Fett, Kursiv, Links, Zitate).
    Skripte, Styles, Einbettungen, Bilder, Formulare und alle Attribute außer einem geprüften href fallen weg."""
    ALLOWED = {"p", "br", "strong", "b", "em", "i", "u", "h2", "h3", "h4", "ul", "ol", "li", "a", "blockquote", "hr"}
    VOID = {"br", "hr"}
    DROP = {"script", "style", "iframe", "object", "embed", "template", "svg", "math", "noscript", "textarea", "select", "title", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.DROP:
            self.skip += 1
            return
        if self.skip or tag not in self.ALLOWED:
            return
        if tag in self.VOID:
            self.out.append(f"<{tag}>")
            return
        extra = ""
        if tag == "a":
            href = re.sub(r"[\x00-\x20]", "", dict(attrs).get("href") or "")
            if re.match(r"(https?://|mailto:|/(?!/)|#)", href, re.I):
                ext = href.lower().startswith(("http://", "https://"))
                extra = f' href="{e(href)}"' + (' target="_blank" rel="noopener"' if ext else "")
        self.out.append(f"<{tag}{extra}>")
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag in self.VOID and not self.skip:
            self.out.append(f"<{tag}>")

    def handle_endtag(self, tag):
        if tag in self.DROP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in self.stack:
            return
        while self.stack:
            t = self.stack.pop()
            self.out.append(f"</{t}>")
            if t == tag:
                break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(e(data))

    def result(self):
        self.close()
        return "".join(self.out) + "".join(f"</{t}>" for t in reversed(self.stack))


def clean_html(t):
    """HTML aus dem Hub für die Webseite: nur erlaubte Tags, alles andere als Text oder entfernt."""
    f = _HtmlFilter()
    f.feed(str(t or ""))
    return f.result()


def render_blocks(blocks):
    """Blöcke aus dem Editor (vom Server schon geprüft). Fließtext darf einfache Auszeichnung enthalten (clean_html), sonst nur Text."""
    out = []
    for b in blocks:
        t = b["t"]
        if t == "p":
            out.append(f'<p>{clean_html(b["text"]).replace(chr(10), "<br>")}</p>')
        elif t == "h":
            out.append(f"<h2>{e(b['text'])}</h2>")
        elif t == "quote":
            out.append(f'<blockquote><p>{lines(b["text"])}</p>{f"<footer>{e(b['by'])}</footer>" if b.get("by") else ""}</blockquote>')
        elif t == "list":
            out.append("<ul>" + "".join(f"<li>{clean_html(x)}</li>" for x in b["items"]) + "</ul>")
        elif t == "highlight":
            out.append(f'<p class="art-highlight">{e(b["text"])}</p>')
        elif t == "cta":
            btn = f'<a class="btn dark" href="{e(b["link"])}">{e(b["label"] or "Mehr erfahren")}</a>' if b.get("link") else ""
            out.append(f'<aside class="art-cta"><p>{lines(b["text"])}</p>{btn}</aside>')
        elif t == "image":
            cap = f"<figcaption>{e(b['caption'])}</figcaption>" if b.get("caption") else ""
            out.append(f'<figure class="art-img"><img src="{e(b["src"])}" alt="{e(b.get("alt"))}" loading="lazy" decoding="async">{cap}</figure>')
        elif t == "note":
            out.append(f'<p class="art-note">{e(b["text"])}</p>')
    return "".join(out)


def plain_text(t, fmt="Text"):
    if fmt not in ("HTML", "Blöcke"):
        return str(t or "")
    inline = re.sub(r"</?(strong|b|em|i|u|a)\b[^>]*>", "", clean_html(t))
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", inline))).strip()


def paragraphs(t):
    """Text aus dem Hub als Absätze: Leerzeile = neuer Absatz, einfacher Umbruch bleibt erhalten. Kein HTML."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", str(t or "").replace("\r", "")) if b.strip()]
    return "".join(f"<p>{lines(b)}</p>" for b in blocks)


def news_card(a):
    img = (f'<img src="{e(a["image"])}" alt="{e(a["image_alt"] or a["title"])}" loading="lazy" decoding="async">' if a["image"]
           else f'<div class="nc-logo"><img src="{LOGO}" alt="" loading="lazy"></div>')
    teaser = a["teaser"] or (plain_text(a["body"], a.get("format")).strip().split("\n")[0][:180] if a["body"] else "")
    return (f'<a class="news-card" href="/news/{e(a["slug"])}"><div class="nc-img">{img}</div><div class="nc-text">'
            f'<p class="nc-meta">{e(fmt_date(a["date"]))}{f" · {e(a["team"])}" if a["team"] else ""}</p>'
            f'<h3>{e(a["title"])}</h3>{f"<p>{e(teaser)}</p>" if teaser else ""}<span class="more">Weiterlesen</span></div></a>')


def page_news(info, articles):
    body = f"""<section class="page-hero">{picture("fussball", "100vw", "hero-img", eager=True)}{SHIELD}<div class="hero-text"><p class="eyebrow">Aktuelles</p><h1>News</h1></div></section>
<section class="wrap">{f'<div class="news-grid">{"".join(news_card(a) for a in articles)}</div>' if articles else '<p>Hier erscheinen bald die ersten Neuigkeiten aus dem Verein.</p>'}</section>"""
    return layout("news", "News", seo_desc(info, "news", "Neuigkeiten, Spielberichte und Termine aus dem SV Amisia Wolthusen."), body, info)


def article_footer(info, a):
    """Unter jedem Artikel: Kasten zum Probetraining (Mannschaft des Artikels) und der Fotograf mit Link."""
    text = (info.get("site_news_cta_text") or "").strip()
    label = (info.get("site_news_cta_button") or "").strip() or "Probetraining anfragen"
    topic = "jugend" if a.get("team") in YOUTH_TEAMS else "herren"
    cta = f'<aside class="art-cta"><p>{lines(text)}</p><a class="btn dark" href="/kontakt?anliegen={topic}#formular">{e(label)}</a></aside>' if text else ""
    by = a.get("photo_by") or ""
    who = (f'<a href="{e(a["photo_url"])}" target="_blank" rel="noopener">{e(by)}</a>' if a.get("photo_url") else e(by)) if by else ""
    return cta + (f'<p class="art-credit">Foto: {who}</p>' if who else "")


def page_article(info, a, games):
    g = next((x for x in games if a.get("game_id") and x.get("id") == a["game_id"]), None)
    img = f'<figure class="art-img"><img src="{e(a["image"])}" alt="{e(a["image_alt"] or a["title"])}" decoding="async"></figure>' if a["image"] else ""
    body = f"""<article class="wrap narrow article">
  <p class="eyebrow"><a href="/news">News</a></p>
  <h1>{e(a["title"])}</h1>
  <p class="nc-meta">{e(fmt_date(a["date"], True))}{f" · {e(a['team'])}" if a["team"] else ""}</p>
  {f'<p class="lead">{e(a["teaser"])}</p>' if a["teaser"] else ""}
  {img}
  {f'<div class="art-game">{game_card(g, info)}</div>' if g else ""}
  <div class="art-body">{render_blocks(a.get("blocks") or []) if a.get("format") == "Blöcke" else clean_html(a["body"]) if a.get("format") == "HTML" else paragraphs(a["body"])}</div>
  {article_footer(info, a)}
  <p><a class="more" href="/news">Alle News</a></p>
</article>"""
    base = getattr(_ctx, "base", "")
    head = ""
    if base:
        club = info.get("club_name") or "SV Amisia Wolthusen"
        ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": a["title"][:110], "datePublished": a["date"], "dateModified": a["date"],
              "url": f"{base}/news/{a['slug']}", "publisher": {"@type": "SportsOrganization", "name": club, "logo": base + LOGO},
              "image": [base + (a["image"] or LOGO)], "author": {"@type": "Organization", "name": club, "url": base + "/"}}
        head = jsonld(ld)
    desc = " ".join((a["teaser"] or plain_text(a["body"], a.get("format")).strip().split("\n")[0]).split())[:160]
    return layout("news", a["title"], desc, body, info, extra_head=head, canonical=f"/news/{a['slug']}")


# ---------------------------------------------------------------------------
# Seite bauen
# ---------------------------------------------------------------------------
def render(slug, data, sent=None):
    site = data.get("site") or {}
    _ctx.images = site.get("images") or {}
    _ctx.layout = site.get("layout")
    _ctx.base = (data.get("base") or "").rstrip("/")
    _ctx.maint_bar = bool(data.get("maint_bar"))
    _ctx.nav = data.get("nav")
    _ctx.team = data.get("team") or []
    _ctx.trainings = data.get("trainings") or []
    try:
        if slug == "wartung":
            return page_maintenance(data)
        return render_page(slug, data, sent)
    finally:
        _ctx.images, _ctx.layout, _ctx.base, _ctx.maint_bar, _ctx.nav, _ctx.team, _ctx.trainings = {}, None, "", False, None, [], []


def render_page(slug, data, sent):
    info = data["info"]
    if slug in seiten():
        return page_static(slug, info, data)
    if slug.startswith("mannschaft/") and slug[11:] in SLUG_TEAM:
        return page_team(info, slug[11:], data)
    if slug == "news":
        return page_news(info, data.get("articles") or [])
    if slug == "news-artikel" and data.get("article"):
        return page_article(info, data["article"], data["games"])
    if slug == "spielplan":
        return page_schedule(info, data["games"])
    if slug == "supporter-karte":
        return page_card_order(info, sent)
    if slug == "helfer":
        return page_helpers(info, data.get("helfer") or {})
    if slug == "links":
        return page_links(data)
    if slug == "newsletter":
        return page_newsletter(info, data.get("nl") or {})
    if slug == "spielerbogen":
        return page_player_form(info, data.get("form") or {"state": "geschlossen"})
    if slug == "supporter-storno":
        return page_card_cancel(info, data.get("cancel") or {"state": "ungueltig"})
    if slug == "kontakt":
        return page_contact(info, sent, data.get("preselect") or "")
    if slug in LEGAL:
        return page_legal(slug, info)
    return page_404(info)


# ---------------------------------------------------------------------------
# Google: strukturierte Daten (schema.org als JSON-LD) und Sitemap
# ---------------------------------------------------------------------------
def jsonld(obj):
    return '<script type="application/ld+json">' + json.dumps(obj, ensure_ascii=False).replace("</", "<\\/") + "</script>"


def org_ld(info, base):
    obj = {"@context": "https://schema.org", "@type": "SportsOrganization", "name": (info.get("club_name") or "SV Amisia Wolthusen") + " e.V.",
           "url": base + "/", "logo": base + LOGO, "foundingDate": "1929",
           "address": {"@type": "PostalAddress", "streetAddress": "Folkmar-Allena-Straße 13", "postalCode": "26725", "addressLocality": "Emden", "addressCountry": "DE"}}
    same = [u for _, u in social_links(info)]
    if same:
        obj["sameAs"] = same
    return obj


# Einträge der sitemap.xml mit Standard-Priorität; im Hub unter Webseite > Sitemap an/aus und Priorität (Einstellung web_sitemap)
SITEMAP_PAGES = [("", "Startseite", "1.0"), ("fussball", "Fußball", "0.9"), ("mannschaft/*", "Mannschaften", "0.8"), ("spielplan", "Spielplan", "0.9"),
                 ("news", "News (Übersicht)", "0.8"), ("news/*", "News-Artikel (die 3 neuesten)", "0.6"), ("american-football", "American Football", "0.6"),
                 ("turnen-gymnastik", "Turnen & Gymnastik", "0.6"), ("saal", "Unser Saal", "0.6"), ("partner", "Partner", "0.5"),
                 ("mitglied-werden", "Mitglied werden", "0.7"), ("kontakt", "Kontakt", "0.6"), ("newsletter", "Newsletter", "0.3"),
                 ("supporter-karte", "Dauerkarte (nur solange die Bestellung offen ist)", "0.5"),
                 ("impressum", "Impressum", "0.2"), ("datenschutz", "Datenschutz", "0.2")]
SITEMAP_PRIOS = tuple(f"{i / 10:.1f}" for i in range(11))


def sitemap(base, articles=(), card_open=False, cfg=None):
    """sitemap.xml mit den eingeschalteten öffentlichen Seiten und Artikeln. cfg: {schlüssel: [an, priorität]}, fehlt = Standard."""
    cfg = cfg or {}
    use = {k: cfg.get(k, [True, p]) for k, _, p in SITEMAP_PAGES}
    rows = "".join(f"<url><loc>{escape(base)}/{k}</loc><priority>{use[k][1]}</priority></url>"
                   for k, _, _ in SITEMAP_PAGES if use[k][0] and "*" not in k and (k != "supporter-karte" or card_open))
    if use["mannschaft/*"][0]:
        rows += "".join(f"<url><loc>{escape(base)}/mannschaft/{s}</loc><priority>{use['mannschaft/*'][1]}</priority></url>" for s in TEAM_SLUG.values())
    if use["news/*"][0]:
        newest = sorted(articles, key=lambda a: a["date"] or "", reverse=True)[:3]
        rows += "".join(f"<url><loc>{escape(base)}/news/{escape(a['slug'])}</loc><lastmod>{escape(a['date'])}</lastmod><priority>{use['news/*'][1]}</priority></url>" for a in newest)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</urlset>\n'


def robots(base):
    return ("User-agent: *\nAllow: /\nAllow: /static/icon-192.png\nDisallow: /hub\nDisallow: /api/\nDisallow: /static/\nDisallow: /media/\nDisallow: /login\n"
            "Disallow: /bestellen/\nDisallow: /teilen/\nDisallow: /invite/\nDisallow: /passwort-\n"
            "Disallow: /spielerbogen\nDisallow: /supporter-karte/storno/\nDisallow: /helfer/\n" + (f"Sitemap: {base}/sitemap.xml\n" if base else ""))
