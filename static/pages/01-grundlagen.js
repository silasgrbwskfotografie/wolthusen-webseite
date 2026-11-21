/* Wolthusen Hub: Seiten */

/* ---------- Feld-Definitionen ---------- */
const POSITIONS = ['Tor', 'Abwehr', 'Mittelfeld', 'Sturm'];
const POST_TYPES = ['Gameday', 'Ergebnis', 'Spielervorstellung', 'Sponsor', 'Spielplan', 'Training & Behind the Scenes', 'Verein & Community', 'Saisonabschluss', 'Sonstiges'];
const POST_STATUS = ['Idee', 'In Arbeit', 'Geplant', 'Gepostet'];
const SOCIAL_TARGETS = ['Facebook', 'Instagram', 'Facebook + Instagram'];
// Zustand beim automatischen Posten (setzt nur der Server): [Text, Badge-Klasse]
const PUBLISH_STATE = { '': ['Auto: wartet', 'red'], 'läuft': ['Auto: läuft', 'warn'], gepostet: ['Auto: gepostet', 'ok'],
  teilweise: ['Auto: teilweise', 'warn'], fehler: ['Auto: Fehler', 'warn'], verpasst: ['Auto: verpasst', 'warn'] };
const publishBadge = p => Number(p.auto_publish) || p.publish_state ? `<span class="badge ${PUBLISH_STATE[p.publish_state || '']?.[1] || ''}" title="${esc(p.publish_log || '')}">${PUBLISH_STATE[p.publish_state || '']?.[0] || esc(p.publish_state)}</span>` : '';
const TEAMS = ['Erste Herren', 'Zweite Herren', 'Alte Herren', 'D-Jugend', 'E-Jugend', 'F-Jugend', 'G-Jugend'];   // gleiche Liste in server.py (TEAMS)
const YOUTH_TEAMS = ['D-Jugend', 'E-Jugend', 'F-Jugend', 'G-Jugend'];   // wie YOUTH_TEAMS in server.py: Spieler nie auf der Webseite
const teamOf = r => TEAMS.includes(r.team) ? r.team : TEAMS[0];
const teamBadge = r => teamOf(r) !== TEAMS[0] ? `<span class="badge red">${esc(teamOf(r))}</span>` : '';
const teamBar = (cur, attr) => TEAMS.length > 1 ? ['Alle Mannschaften', ...TEAMS].map(t => `<button class="btn sm ${t === cur ? 'dark' : ''}" ${attr}="${esc(t)}">${esc(t)}</button>`).join('') : '';
const SPONSOR_PACKAGES = ['Premiumpartner', 'Hauptsponsor', 'Trikotsponsor', 'Bandenwerbung', 'Spieltagssponsor', 'Jugendförderung', 'Partner', 'Förderer'];

const oppLabel = o => o.name || '';
const sponsorLabel = s => s.name || '';
const playerLabel = p => [p.number ? '#' + p.number : '', fullName(p), p.kind !== 'Spieler' ? '(' + (p.role || p.kind) + ')' : ''].filter(Boolean).join(' ');
const gameLabel = g => `${fmtDate(g.date)} ${Number(g.home) ? 'vs' : '@'} ${byId(App.cache.opponents, g.opponent_id)?.name || 'TBA'}`;

// Rollen für Coaches und Staff, auch als Zusatzrolle für Spieler (Reihenfolge wie COACH_ROLES in website.py)
const STAFF_ROLES = ['Trainer', 'Co-Trainer', 'Torwarttrainer', 'Betreuer', 'Teammanager', 'Physio', 'Zeugwart', 'Jugendleitung', 'Social Media Betreuer'];

const F = {
  players: [
    { key: 'kind', label: 'Art', type: 'select', options: ['Spieler', 'Coach', 'Staff'], hint: 'Coach = Trainer, Staff = Betreuer, Physio, Zeugwart.' },
    { key: 'team', label: 'Mannschaft', type: 'select', options: TEAMS, default: TEAMS[0], hint: 'Spieler der Jugendmannschaften erscheinen nie auf der Webseite, nur Trainer und Betreuer.' },
    { key: 'active', label: 'Aktiv im Team', type: 'check', default: 1 },
    { key: 'first_name', label: 'Vorname' },
    { key: 'last_name', label: 'Nachname' },
    { key: 'number', label: 'Rückennummer', show: v => v.kind === 'Spieler' },
    { key: 'position', label: 'Position', list: POSITIONS, show: v => v.kind === 'Spieler' },
    { key: 'rookie', label: 'Neuzugang', type: 'check', show: v => v.kind === 'Spieler' },
    { key: 'extra_role', label: 'Zusatzrolle (optional)', list: STAFF_ROLES, show: v => v.kind === 'Spieler',
      hint: 'Wenn der Spieler zusätzlich eine Aufgabe hat, z. B. Social Media Betreuer oder Co-Trainer. Steht auf der Webseite unter der Position.' },
    { key: 'role', label: 'Rolle', list: STAFF_ROLES, show: v => v.kind !== 'Spieler',
      hint: 'Auf der Webseite stehen Trainer und Betreuer unter „Trainer und Betreuer“ auf der Seite der Mannschaft.' },
    { key: 'since', label: 'Dabei seit', placeholder: 'z. B. 2023' },
    { key: 'instagram', label: 'Instagram', placeholder: '@handle' },
    { key: 'email', label: 'E-Mail (intern)', hint: 'Nur im Hub, nie auf der Webseite.' },
    { key: 'phone', label: 'Telefon (intern)', hint: 'Nur im Hub, nie auf der Webseite.' },
    { key: 'consent', label: 'Einwilligung Foto & Social Media liegt vor', type: 'check', hint: 'Ohne Einwilligung warnt der Hub bei Posts.' },
    { key: 'photo', label: 'Foto', type: 'image', full: true },
    { key: 'facts', label: 'Infos für Posts (Fußball-Geschichte, Funfacts)', type: 'textarea' },
    { key: 'notes', label: 'Interne Notizen', type: 'textarea', rows: 2 },
  ],
  trainings: [
    { key: 'team', label: 'Mannschaft / Gruppe', list: [...TEAMS, 'Fit for Fun', 'Gymnastikgruppe', 'Herren-Gymnastik'], default: TEAMS[0] },
    { key: 'weekday', label: 'Wochentag', type: 'select', options: ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'] },
    { key: 'start', label: 'Beginn', type: 'time' },
    { key: 'end', label: 'Ende', type: 'time' },
    { key: 'place', label: 'Ort', list: ['Sportplatz Wolthusen', 'Turnhalle Grundschule Wolthusen', 'Cirksena-Schule'], default: 'Sportplatz Wolthusen' },
    { key: 'season', label: 'Zeitraum (optional)', placeholder: 'z. B. Sommer oder Winterpause', hint: 'Leer lassen, wenn die Zeit das ganze Jahr gilt.' },
    { key: 'active', label: 'Auf der Webseite zeigen', type: 'check', default: 1 },
    { key: 'notes', label: 'Interne Notizen', type: 'textarea', rows: 2 },
  ],
  bookings: [
    { key: 'resource', label: 'Was', type: 'select', options: ['Saal', 'Sportplatz', 'Kunstrasen', 'Turnhalle', 'Sportheim'], default: 'Saal' },
    { key: 'status', label: 'Status', type: 'select', options: ['Anfrage', 'Bestätigt', 'Abgesagt'], default: 'Anfrage' },
    { key: 'date', label: 'Datum', type: 'date' },
    { key: 'start', label: 'Von', type: 'time' },
    { key: 'end', label: 'Bis', type: 'time' },
    { key: 'title', label: 'Anlass', placeholder: 'z. B. Geburtstag, Teetafel, Training E-Jugend' },
    { key: 'renter', label: 'Mieter / Mannschaft' },
    { key: 'contact', label: 'Kontakt (Telefon oder E-Mail)' },
    { key: 'persons', label: 'Personen', type: 'number' },
    { key: 'price', label: 'Miete (€)', type: 'number' },
    { key: 'deposit', label: 'Kaution (€)', type: 'number' },
    { key: 'paid', label: 'Bezahlt', type: 'check' },
    { key: 'notes', label: 'Notizen', type: 'textarea', rows: 2, full: true },
  ],
  opponents: [
    { key: 'name', label: 'Name', full: true },
    { key: 'short', label: 'Kurzname', placeholder: 'z. B. Borssum' },
    { key: 'city', label: 'Stadt' },
    { key: 'instagram', label: 'Instagram', placeholder: '@handle' },
    { key: 'logo', label: 'Logo', type: 'image' },
    { key: 'notes', label: 'Notizen', type: 'textarea', rows: 2 },
  ],
  games: () => [
    { key: 'season', label: 'Saison', default: App.settings.season },
    { key: 'team', label: 'Mannschaft', type: 'select', options: TEAMS, default: TEAMS[0] },
    { key: 'kind', label: 'Art', type: 'select', options: ['Liga', 'Pokal', 'Freundschaftsspiel', 'Turnier', 'Hallenturnier', 'Sonstiges'] },
    { key: 'date', label: 'Datum', type: 'date' },
    { key: 'time', label: 'Anstoß', type: 'time' },
    { key: 'opponent_id', label: 'Gegner', type: 'ref', ref: { table: 'opponents', label: oppLabel }, hint: 'Neue Gegner unter „Gegner“ anlegen.' },
    { key: 'home', label: 'Heimspiel', type: 'check', default: 1 },
    { key: 'location', label: 'Spielort', hint: 'Leer lassen bei Heimspielen für den Standard-Ort.' },
    { key: 'league', label: 'Liga / Staffel', placeholder: 'z. B. Kreisliga Ostfriesland' },
    { key: 'sponsor_id', label: 'Spieltagssponsor', type: 'ref', ref: { table: 'sponsors', label: sponsorLabel } },
    { key: 'stream_url', label: 'Livestream-Link', placeholder: 'https://...', hint: 'Erscheint auf der Webseite als Knopf „Livestream“ beim Spiel.' },
    { key: 'score_us', label: 'Tore wir', type: 'number' },
    { key: 'score_them', label: 'Tore Gegner', type: 'number' },
    { key: 'quarters', label: 'Halbzeitstand', placeholder: '1:0' },
    { key: 'highlights', label: 'Torschützen / Spielbericht-Notizen', type: 'textarea' },
    { key: 'notes', label: 'Interne Notizen', type: 'textarea', rows: 2 },
  ],
  sponsors: [
    { key: 'name', label: 'Name' },
    { key: 'package', label: 'Paket', list: SPONSOR_PACKAGES },
    { key: 'instagram', label: 'Instagram', placeholder: '@handle' },
    { key: 'website', label: 'Website' },
    { key: 'contact', label: 'Ansprechpartner' },
    { key: 'package_id', label: 'Sponsorenpaket (intern)', type: 'ref', ref: { table: 'sponsor_packages', label: p => p.name + (p.season ? ` (${p.season})` : '') + (Number(p.active) ? '' : ' (inaktiv)') },
      hint: 'Nur im Hub sichtbar, nie auf der Webseite. Pakete legst du unter Sponsoren > Pakete an.' },
    { key: 'amount', label: 'Betrag / Leistung', placeholder: 'z. B. 500 € oder Gerüst', show: () => can('finanzen') },
    { key: 'start', label: 'Beginn', type: 'date' },
    { key: 'end', label: 'Ende', type: 'date' },
    { key: 'posts_agreed', label: 'Vereinbarte Posts', type: 'number', hint: 'Der Hub zählt gepostete Beiträge mit diesem Sponsor mit.' },
    { key: 'active', label: 'Aktiv', type: 'check', default: 1 },
    { key: 'logo', label: 'Logo', type: 'image', full: true },
    { key: 'files', label: 'Dateien', type: 'files', full: true, hint: 'Verträge, Rechnungen, Bilder, Druckdaten. Sichtbar für alle, die Sponsoren sehen dürfen.' },
    { key: 'notes', label: 'Vereinbarungen / Notizen', type: 'textarea' },
  ],
  shop_products: [
    { key: 'name', label: 'Produkt', placeholder: 'z. B. Hoodie 2027' },
    { key: 'price', label: 'Preis (Anzeige)', placeholder: 'z. B. 39,90 €' },
    { key: 'url', label: 'Link zum Produkt im Fanshop', placeholder: 'https://...', hint: 'Leer lassen = Link zum Fanshop allgemein.' },
    { key: 'sort', label: 'Reihenfolge', type: 'number', hint: 'Kleine Zahl kommt zuerst.' },
    { key: 'is_new', label: 'Als „Neu“ markieren', type: 'check', hint: 'Zeigt im Laufband ein rotes „Neu“ am Bild.' },
    { key: 'colors', label: '„In verschiedenen Farben erhältlich“', type: 'check', hint: 'Zeigt den Hinweis im Laufband unter dem Preis.' },
    { key: 'active', label: 'Auf der Startseite zeigen', type: 'check', default: 1 },
    { key: 'image', label: 'Produktbild', type: 'image', full: true, hint: 'Am besten quadratisch, freigestellt oder auf hellem Grund. Ohne Bild erscheint das Produkt nicht.' },
  ],
  sponsor_packages: [
    { key: 'name', label: 'Name', placeholder: 'z. B. Gold' },
    { key: 'season', label: 'Saison', placeholder: 'z. B. 2027' },
    { key: 'price', label: 'Preis', placeholder: 'z. B. 1.500 € pro Saison', show: () => can('finanzen') },
    { key: 'sort', label: 'Reihenfolge', type: 'number', hint: 'Kleine Zahl steht oben.' },
    { key: 'active', label: 'Aktiv', type: 'check', default: 1 },
    { key: 'services', label: 'Leistungen (eine pro Zeile)', type: 'textarea', full: true },
    { key: 'notes', label: 'Notizen', type: 'textarea', full: true },
  ],
  media_team: () => [
    { key: 'name', label: 'Name' },
    { key: 'role', label: 'Hauptaufgabe', list: (App.settings.media_tasks || '').split('\n').filter(Boolean) },
    { key: 'phone', label: 'Telefon' },
    { key: 'instagram', label: 'Instagram', placeholder: '@handle' },
    { key: 'active', label: 'Aktiv', type: 'check', default: 1 },
    { key: 'notes', label: 'Notizen', type: 'textarea', rows: 2 },
  ],
  supporter_cards: () => [
    { key: 'season', label: 'Saison', default: App.settings.season },
    { key: 'number', label: 'Kartennummer', hint: 'Leer lassen: Sobald die Karte bezahlt ist, vergibt der Hub automatisch die nächste Nummer (00001, 00002, ...).' },
    { key: 'holder', label: 'Inhaber', full: true },
    { key: 'sold_on', label: 'Verkauft am', type: 'date', default: todayStr() },
    { key: 'price', label: 'Preis (€)', type: 'number', default: App.settings.card_price },
    { key: 'paid', label: 'Bezahlt', type: 'check' },
    { key: 'email', label: 'E-Mail' },
    { key: 'phone', label: 'Telefon' },
    { key: 'notes', label: 'Notizen', type: 'textarea', rows: 2 },
  ],
  posts: [
    { key: 'date', label: 'Datum', type: 'date', default: todayStr() },
    { key: 'time', label: 'Uhrzeit', type: 'time' },
    { key: 'type', label: 'Art', type: 'select', options: POST_TYPES },
    { key: 'status', label: 'Status', type: 'select', options: POST_STATUS },
    { key: 'format', label: 'Format', type: 'select', options: ['Feed', 'Karussell', 'Story', 'Reel'] },
    { key: 'title', label: 'Titel (intern)' },
    { key: 'caption', label: 'Caption', type: 'textarea', rows: 10 },
    { key: 'image', label: 'Fertige Grafik aus Canva (optional)', type: 'image', full: true, hint: 'Export aus Canva hier ablegen, dann liegt alles an einem Ort.' },
    { key: 'game_id', label: 'Spiel', type: 'ref', ref: { table: 'games', label: gameLabel } },
    { key: 'sponsor_id', label: 'Sponsor', type: 'ref', ref: { table: 'sponsors', label: sponsorLabel } },
    { key: 'player_id', label: 'Spieler / Coach', type: 'ref', ref: { table: 'players', label: playerLabel } },
    { key: 'posted_url', label: 'Link zum Post' },
    { key: 'media', label: 'Bilder fürs Karussell (2 bis 10) bzw. Video fürs Reel', type: 'files', full: true, maxMb: 40,
      accept: 'image/jpeg,image/png,video/mp4,video/quicktime', show: v => ['Karussell', 'Reel'].includes(v.format),
      hint: 'Karussell: JPG oder PNG in der gewünschten Reihenfolge. Reel: ein Video als MP4 im Hochformat, höchstens 40 MB.' },
    { key: 'auto_publish', label: 'Automatisch posten (Freigabe)', type: 'check', hint: 'Geht zu Datum und Uhrzeit oben automatisch raus: Feed-Post, Story, Karussell oder Reel.' },
    { key: 'targets', label: 'Posten auf', type: 'select', options: SOCIAL_TARGETS, show: v => Number(v.auto_publish) },
    { key: 'notes', label: 'Notizen', type: 'textarea', rows: 2 },
  ],
};

function statusBadge(st) {
  const cls = { 'Gepostet': 'ok', 'Geplant': 'red', 'In Arbeit': 'warn' }[st] || '';
  return `<span class="badge ${cls}">${esc(st || 'Idee')}</span>`;
}

function dateBox(d) {
  const x = parseDate(d);
  if (!x) return '<div class="date-box"><b>?</b><span>offen</span></div>';
  return `<div class="date-box"><b>${x.getDate()}</b><span>${MON_S[x.getMonth()]} ${WD_S[x.getDay()]}</span></div>`;
}

function mediaTasks() { return (App.settings.media_tasks || '').split('\n').map(t => t.trim()).filter(Boolean); }

