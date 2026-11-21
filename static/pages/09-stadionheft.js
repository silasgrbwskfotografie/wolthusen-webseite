/* ====================================================================== */
/* Stadionheft: alle Infos für ein Heft an einem Ort, zum Rauskopieren nach Canva (Gestaltung bleibt in Canva) */
const MAG_STATUS = ['Planung', 'In Arbeit', 'Im Druck', 'Fertig'];
// Fragebogen „Behind the Helmet“ wie im Heft 2026
const BTH_QUESTIONS = ['Was waren deine bisherigen Vereine?', 'Auf welcher Position würdest du sonst spielen?', 'Wie bist du zum Fußball gekommen?',
  'Was macht für dich Wolthusen aus?', 'Lieblingsverein?', 'Lieblingsspieler?', 'Was würdest du jedem raten, der mit Fußball anfangen möchte?'];
const MAG_REFS = ['Schiedsrichter', 'Assistent 1', 'Assistent 2'];
const POS_PLURAL = { Tor: 'Torhüter', Abwehr: 'Abwehr', Mittelfeld: 'Mittelfeld', Sturm: 'Sturm' };
// Beiträge, die im Heft angelegt werden (Tabelle magazine_pages, Spalte section). reuse: wird aus dem letzten Heft übernommen
const MAG_ITEMS = {
  'Vorwort': { title: 'Vorwort', add: 'Vorwort anlegen', single: true },
  'Behind the Helmet': { title: 'Behind the Helmet', add: 'Spieler hinzufügen' },
  'Gegner': { title: 'Gegner', add: 'Eigenen Text zum Gegner', single: true },
  'Spielbericht': { title: 'Spielberichte', add: 'Spielbericht hinzufügen' },
  'Schiedsrichter': { title: 'Schiedsrichter', add: 'Crew eintragen', single: true },
  'Fan-Info': { title: 'Fan-Info', add: 'Fan-Info hinzufügen', reuse: true },
  'Jugend': { title: 'Jugend', add: 'Jugendseite anlegen', reuse: true },
  'Rückseite': { title: 'Rückseite: Werde Teil von Wolthusen', add: 'Rückseite anlegen', single: true, reuse: true },
};

const magLabel = m => [m.title || 'Stadionheft', m.number, m.season].filter(Boolean).join(' ');
const magItems = (id, section) => App.cache.magazine_pages.filter(p => p.magazine_id == id && (!section || p.section === section)).sort((a, b) => a.id - b.id);
const magSponsorIds = m => { try { const a = JSON.parse(m.sponsor_ids || '[]'); return Array.isArray(a) ? a.map(Number) : []; } catch { return []; } };
const magAnswers = it => { try { return JSON.parse(it.answers || '{}') || {}; } catch { return {}; } };
const magBadge = st => `<span class="badge ${{ Fertig: 'ok', 'Im Druck': 'dark', 'In Arbeit': 'warn' }[st] || ''}">${esc(st || 'Planung')}</span>`;
const magFace = (src, alt) => src ? `<img class="mag-face" src="${esc(src)}" alt="${esc(alt || '')}">` : '<div class="mag-face"></div>';
const magPlayedResult = g => g && g.score_us !== null && g.score_us !== '' && g.score_us !== undefined;

F.magazines = () => [
  { key: 'title', label: 'Titel', default: 'Amisia Echo' },
  { key: 'number', label: 'Ausgabe', placeholder: 'z. B. 1 von 4' },
  { key: 'season', label: 'Saison', default: App.settings.season },
  { key: 'status', label: 'Status', type: 'select', options: MAG_STATUS },
  { key: 'game_id', label: 'Heimspiel', type: 'ref', ref: { table: 'games', label: gameLabel }, hint: 'Daraus kommen Gegner und Spieltag.' },
  { key: 'deadline', label: 'Redaktionsschluss', type: 'date' },
  { key: 'print_date', label: 'Druckabgabe', type: 'date' },
  { key: 'canva_url', label: 'Canva-Link', full: true },
  { key: 'files', label: 'Dateien', type: 'files', full: true, hint: 'z. B. das fertige PDF für die Druckerei' },
  { key: 'notes', label: 'Notizen', type: 'textarea', rows: 2 },
];

function magItemFields(section) {
  const notes = { key: 'notes', label: 'Interne Notizen', type: 'textarea', rows: 2 };
  switch (section) {
    case 'Vorwort': return [
      { key: 'author', label: 'Autor', list: App.cache.players.filter(p => Number(p.active)).map(fullName) },
      { key: 'role', label: 'Funktion', placeholder: 'z. B. Social Media Manager' },
      { key: 'title', label: 'Überschrift', full: true },
      { key: 'image', label: 'Foto', type: 'image', full: true },
      { key: 'text', label: 'Text', type: 'textarea', rows: 14 }, notes];
    case 'Behind the Helmet': return [
      { key: 'player_id', label: 'Spieler', type: 'ref', ref: { table: 'players', label: playerLabel } },
      { key: 'image', label: 'Foto (leer lassen für das Foto aus Kader & Staff)', type: 'image', full: true },
      ...BTH_QUESTIONS.map((q, i) => ({ key: 'q' + i, label: q, type: 'textarea', rows: 2 })), notes];
    case 'Spielbericht': return [
      { key: 'game_id', label: 'Spiel', type: 'ref', ref: { table: 'games', label: gameLabel } },
      { key: 'title', label: 'Überschrift', full: true },
      { key: 'text', label: 'Text', type: 'textarea', rows: 12, hint: 'Leer lassen: der Hub trägt Ergebnis, Halbzeitstand und Torschützen aus dem Spielplan ein.' },
      { key: 'files', label: 'Fotos', type: 'files', full: true }, notes];
    case 'Schiedsrichter': return [{ key: 'text', label: 'Crew', type: 'textarea', rows: 9 }, notes];
    default: return [
      { key: 'title', label: 'Überschrift', full: true },
      { key: 'text', label: 'Text', type: 'textarea', rows: 10 },
      { key: 'files', label: 'Bilder und Dateien', type: 'files', full: true }, notes];
  }
}

/* ---------- Texte für Canva ---------- */
function magPersonLine(p) {
  return p ? [`${p.number ? '#' + p.number + ' ' : ''}${fullName(p)}`, p.kind === 'Spieler' ? [p.position, teamOf(p)].filter(Boolean).join(', ') : (p.role || p.kind)].filter(Boolean).join(', ') : '';
}
function magGameText(g) {
  if (!g) return '';
  const o = byId(App.cache.opponents, g.opponent_id)?.name || 'TBA', club = App.settings.club_name;
  return [fmtDate(g.date, true), Number(g.home) ? `${club} vs ${o}` : `${o} vs ${club}`,
    magPlayedResult(g) ? `Endstand ${g.score_us}:${g.score_them}${g.quarters ? ' (' + g.quarters + ')' : ''}` : '', g.highlights || ''].filter(Boolean).join('\n');
}
function magCoaches() {
  const roles = F.players.find(f => f.key === 'role').list;
  return App.cache.players.filter(p => p.kind !== 'Spieler' && Number(p.active))
    .sort((a, b) => ((roles.indexOf(a.role) + 1) || 99) - ((roles.indexOf(b.role) + 1) || 99) || fullName(a).localeCompare(fullName(b)));
}
// Kader der Ersten Herren nach Position: [{ unit, groups: [{ pos, label, players }] }]
function magRoster() {
  const ps = App.cache.players.filter(p => p.kind === 'Spieler' && Number(p.active) && teamOf(p) === TEAMS[0]);
  return [''].map(u => {
    const byPos = {};
    ps.forEach(p => (byPos[p.position || 'Ohne Position'] ??= []).push(p));
    const groups = Object.keys(byPos).sort((a, b) => ((POSITIONS.indexOf(a) + 1) || 99) - ((POSITIONS.indexOf(b) + 1) || 99))
      .map(pos => ({ pos, label: POS_PLURAL[pos] || pos, players: byPos[pos].sort((a, b) => (Number(a.number) || 0) - (Number(b.number) || 0)) }));
    return { unit: 'Kader', groups };
  }).filter(u => u.groups.length);
}
const magRosterText = units => units.map(u => `${u.unit}:\n` + u.groups.map(g => `${g.label}: ` +
  g.players.map(p => `${p.number ? '#' + p.number + ' ' : ''}${fullName(p)}`).join(', ')).join('\n')).join('\n\n');
function magOpponentText(m) {
  const g = byId(App.cache.games, m.game_id), o = byId(App.cache.opponents, g?.opponent_id);
  if (!o) return '';
  const past = App.cache.games.filter(x => x.opponent_id == o.id && magPlayedResult(x)).sort((a, b) => (a.date || '').localeCompare(b.date || ''));
  const res = x => Number(x.score_us) > Number(x.score_them) ? 'Sieg' : Number(x.score_us) < Number(x.score_them) ? 'Niederlage' : 'Unentschieden';
  return [`Zum heutigen Heimspiel begrüßen wir ${o.name}${o.city ? ' aus ' + o.city : ''}.`, o.instagram ? 'Instagram: ' + handle(o.instagram) : '', o.notes || '',
    past.length ? '\nBisherige Duelle:\n' + past.map(x => `${fmtDate(x.date)}, ${Number(x.home) ? 'Heim' : 'Auswärts'}: ${x.score_us}:${x.score_them} (${res(x)})`).join('\n') : ''].filter(Boolean).join('\n');
}
function magItemText(it) {
  if (it.section === 'Vorwort') return [it.title || 'Vorwort', [it.author, it.role].filter(Boolean).join(', '), '', it.text].filter(x => x !== undefined && x !== null).join('\n').trim();
  if (it.section === 'Behind the Helmet') {
    const a = magAnswers(it);
    return ['Behind the Helmet', magPersonLine(byId(App.cache.players, it.player_id)), '',
      ...BTH_QUESTIONS.filter(q => (a[q] || '').trim()).map(q => `${q}\n${a[q].trim()}\n`)].join('\n').trim();
  }
  return [it.title, it.text].filter(Boolean).join('\n\n');
}
function magSponsorsText(m) {
  return App.cache.sponsors.filter(s => magSponsorIds(m).includes(s.id))
    .sort((a, b) => ((SPONSOR_PACKAGES.indexOf(a.package) + 1) || 99) - ((SPONSOR_PACKAGES.indexOf(b.package) + 1) || 99) || (a.name || '').localeCompare(b.name || ''))
    .map(s => [s.name, s.package ? '(' + s.package + ')' : '', s.website || ''].filter(Boolean).join(' ')).join('\n');
}

/* Was fehlt noch? [Bereich, erledigt, Hinweis] */
function magChecklist(m) {
  const has = s => magItems(m.id, s).length > 0, sp = magSponsorIds(m).length;
  return [
    ['Sponsoren', sp > 0, sp ? `${sp} ausgewählt` : 'noch keine ausgewählt'],
    ['Vorwort', has('Vorwort')],
    ['Gegner', !!m.game_id, m.game_id ? '' : 'kein Heimspiel zugeordnet'],
    ['Behind the Helmet', has('Behind the Helmet')],
    ['Spielberichte', has('Spielbericht')],
    ['Schiedsrichter', has('Schiedsrichter')],
    ['Fan-Info', has('Fan-Info')],
    ['Jugend', has('Jugend')],
    ['Rückseite', has('Rückseite')],
  ];
}

App.pages.magazine = async (view, args) => {
  await Promise.all([load('magazines', true), load('magazine_pages', true), loadAll('games', 'opponents', 'sponsors', 'players')]);
  if (args[0]) return magazineDetail(view, Number(args[0]));
  const mags = [...App.cache.magazines].sort((a, b) => (b.season || '').localeCompare(a.season || '') || (b.deadline || '').localeCompare(a.deadline || '') || b.id - a.id);
  view.innerHTML = `
    <div class="page-head"><h1>Stadionheft<small>${mags.length} ${mags.length === 1 ? 'Ausgabe' : 'Ausgaben'}</small></h1>
      <div class="btn-row"><button class="pp btn primary" id="mg_new">+ Neues Heft</button></div></div>
    <div class="grid g3">${mags.map(m => {
      const cl = magChecklist(m), ok = cl.filter(c => c[1]).length, g = byId(App.cache.games, m.game_id), d = daysUntil(m.deadline);
      return `<a class="card mag-card" href="#/magazine/${m.id}">
        <div style="display:flex;justify-content:space-between;gap:8px;align-items:flex-start"><h3 style="margin:0">${esc(magLabel(m))}</h3>${magBadge(m.status)}</div>
        <div class="muted small" style="margin:4px 0 10px">${g ? esc(gameLabel(g)) : 'Kein Heimspiel zugeordnet'}</div>
        <div class="progress"><b style="width:${Math.round(ok / cl.length * 100)}%"></b></div>
        <div class="small" style="margin-top:6px">${ok} von ${cl.length} Bereichen gefüllt${m.deadline && m.status !== 'Fertig' ? ` | Redaktionsschluss ${fmtDate(m.deadline)}${d >= 0 ? ` (in ${d} Tagen)` : ' (vorbei)'}` : ''}</div>
      </a>`;
    }).join('') || '<div class="card empty" style="grid-column:1/-1">Noch kein Stadionheft angelegt. Mit „+ Neues Heft“ geht es los.</div>'}</div>`;
  $('#mg_new').onclick = async () => {
    const r = await editRecord('magazines', F.magazines(), { title: 'Amisia Echo', season: App.settings.season, status: 'Planung' }, { newTitle: 'Neues Stadionheft' });
    if (r?.id) go(`#/magazine/${r.id}`);
  };
};

async function magazineDetail(view, id) {
  const m = byId(App.cache.magazines, id);
  if (!m) { view.innerHTML = '<div class="card empty">Dieses Heft gibt es nicht mehr. <a href="#/magazine">Zur Übersicht</a></div>'; return; }
  const mw = can('medien', 2);
  const g = byId(App.cache.games, m.game_id);
  const prev = App.cache.magazines.filter(x => x.id !== id).sort((a, b) => (b.season || '').localeCompare(a.season || '') || b.id - a.id)[0];
  const rerender = async () => { const st = $('#main').scrollTop; await Promise.all([load('magazines', true), load('magazine_pages', true)]); await magazineDetail(view, id); $('#main').scrollTop = st; };
  const copyBtn = key => `<button class="btn sm keep" data-copy="${key}">Text kopieren</button>`;
  const texts = {};   // Bereich -> Text für „Text kopieren“

  // --- Sponsoren
  const chosen = magSponsorIds(m);
  const sponsors = [...App.cache.sponsors].filter(s => Number(s.active) || chosen.includes(s.id))
    .sort((a, b) => ((SPONSOR_PACKAGES.indexOf(a.package) + 1) || 99) - ((SPONSOR_PACKAGES.indexOf(b.package) + 1) || 99) || (a.name || '').localeCompare(b.name || ''));
  texts.sponsors = magSponsorsText(m);
  const secSponsors = `<div class="mag-sponsors">${sponsors.map(s => {
    const files = parseFiles(s.files);
    return `<label class="mag-sponsor ${chosen.includes(s.id) ? 'on' : ''}"><input type="checkbox" data-sp="${s.id}" ${chosen.includes(s.id) ? 'checked' : ''} ${mw ? '' : 'disabled'}>
      ${s.logo ? `<img class="thumb logo" src="${esc(s.logo)}">` : '<div class="thumb"></div>'}
      <span><b>${esc(s.name)}</b><span class="muted small">${esc(s.package || '')}${files.length ? ` | ${files.map(f => `<a href="${esc(f.path)}" target="_blank" rel="noopener">${esc(f.name)}</a>`).join(', ')}` : ''}</span></span></label>`;
  }).join('') || '<div class="muted">Keine aktiven Sponsoren eingetragen.</div>'}</div>
    ${mw && sponsors.length ? '<div class="btn-row" style="margin-top:10px"><button class="btn sm" id="mg_spall">Alle aktiven auswählen</button></div>' : ''}`;

  // --- Trainerteam
  const coaches = magCoaches();
  texts.coaches = coaches.length ? `Coaches ${App.settings.club_name} ${m.season || ''}`.trim() + '\n\n' + coaches.map(p => `${fullName(p)}\n${p.role || p.kind}`).join('\n\n') : '';
  const secCoaches = coaches.length ? `<div class="mag-people">${coaches.map(p => `<div class="mag-person">${magFace(p.photo, fullName(p))}<b>${esc(fullName(p))}</b><span class="muted small">${esc(p.role || p.kind)}</span>${p.photo ? '' : '<span class="warnline">Foto fehlt</span>'}</div>`).join('')}</div>`
    : '<div class="muted">Unter „Kader &amp; Staff“ sind noch keine Coaches eingetragen.</div>';

  // --- Kader nach Positionen
  const roster = magRoster();
  texts.roster = roster.length ? `${App.settings.club_name} Kader ${m.season || ''}`.trim() + '\n\n' + magRosterText(roster) : '';
  roster.forEach(u => { texts['roster_' + u.unit] = magRosterText([u]); });
  const secRoster = roster.length ? `<div class="grid g3">${roster.map(u => `<div class="mag-unit"><div class="mag-unit-head"><h3>${esc(u.unit)}</h3>${copyBtn('roster_' + u.unit)}</div>
      ${u.groups.map(gr => `<div class="mag-pos"><b>${esc(gr.label)}</b> <span class="muted small">(${gr.players.length})</span><div>${gr.players.map(p => `${p.number ? '#' + esc(p.number) + ' ' : ''}${esc(fullName(p))}`).join('<br>')}</div></div>`).join('')}</div>`).join('')}</div>`
    : '<div class="muted">Unter „Kader &amp; Staff“ sind noch keine aktiven Spieler eingetragen.</div>';

  // --- Beiträge (Vorwort, Behind the Helmet, ...)
  const itemHtml = it => {
    const pl = byId(App.cache.players, it.player_id), gm = byId(App.cache.games, it.game_id), files = parseFiles(it.files);
    const img = it.image || (it.section === 'Behind the Helmet' ? pl?.photo : '');
    const head = it.section === 'Vorwort' ? [it.author, it.role].filter(Boolean).join(', ') || 'Autor fehlt'
      : it.section === 'Behind the Helmet' ? magPersonLine(pl) || 'Spieler fehlt'
      : it.section === 'Spielbericht' ? (gm ? gameLabel(gm) : 'Spiel fehlt') : '';
    const body = it.section === 'Behind the Helmet' ? `${Object.values(magAnswers(it)).filter(a => (a || '').trim()).length} von ${BTH_QUESTIONS.length} Fragen beantwortet` : (it.text || '');
    texts['item' + it.id] = magItemText(it);
    const warn = it.section === 'Behind the Helmet' && pl && !Number(pl.consent) ? '<div class="warnline">Keine Foto-Einwilligung hinterlegt</div>' : '';
    return `<div class="mag-item">${['Vorwort', 'Behind the Helmet'].includes(it.section) ? magFace(img) : ''}
      <div class="grow"><b>${esc(it.title || head || MAG_ITEMS[it.section]?.title || '')}</b>${it.title && head ? `<div class="muted small">${esc(head)}</div>` : ''}
        ${body ? `<div class="mag-text">${esc(body)}</div>` : '<div class="muted small">Noch kein Text</div>'}${warn}
        ${files.length ? `<div class="small">${files.map(f => `<a href="${esc(f.path)}" target="_blank" rel="noopener">${esc(f.name)}</a>`).join(' | ')}</div>` : ''}</div>
      <div class="btn-row">${copyBtn('item' + it.id)}<button class="btn sm ghost keep" data-item="${it.id}">${mw ? 'Bearbeiten' : 'Ansehen'}</button></div></div>`;
  };
  const itemSection = (section, extra = '') => {
    const list = magItems(id, section), cfg = MAG_ITEMS[section];
    texts['sec_' + section] = list.map(magItemText).join('\n\n\n');
    return `${extra}${list.map(itemHtml).join('')}
      ${mw && !(cfg.single && list.length) ? `<button class="btn sm" data-add="${esc(section)}">+ ${esc(cfg.add)}</button>` : ''}
      ${!list.length && !mw && !extra ? '<div class="muted">Noch nichts eingetragen.</div>' : ''}`;
  };

  // --- Gegner automatisch aus dem Heimspiel
  texts.opponent = magOpponentText(m);
  const oppAuto = texts.opponent ? `<div class="mag-text" style="margin-bottom:10px">${esc(texts.opponent)}</div>` : '<div class="muted" style="margin-bottom:10px">Dem Heft ist noch kein Heimspiel zugeordnet (Heft bearbeiten).</div>';

  // --- Spielberichte: gespielte Spiele der Saison ohne Bericht als Vorschlag
  const reported = new Set(magItems(id, 'Spielbericht').map(i => String(i.game_id)));
  const openGames = App.cache.games.filter(x => magPlayedResult(x) && (!m.season || x.season == m.season) && !reported.has(String(x.id)))
    .sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  const gameHint = mw && openGames.length ? `<div class="muted small" style="margin-bottom:8px">Gespielt, aber noch ohne Bericht: ${openGames.map(x => `<a href="#" data-addgame="${x.id}">${esc(gameLabel(x))}</a>`).join(', ')}</div>` : '';

  const sections = [
    ['sponsors', 'Sponsoren', secSponsors, 'sponsors'],
    ['vorwort', 'Vorwort', itemSection('Vorwort'), 'sec_Vorwort'],
    ['coaches', 'Trainerteam', secCoaches, 'coaches'],
    ['roster', 'Kader nach Positionen', secRoster, 'roster'],
    ['bth', 'Behind the Helmet', itemSection('Behind the Helmet'), 'sec_Behind the Helmet'],
    ['opponent', 'Gegner', itemSection('Gegner', oppAuto), 'opponent'],
    ['reports', 'Spielberichte', itemSection('Spielbericht', gameHint), 'sec_Spielbericht'],
    ['refs', 'Schiedsrichter', itemSection('Schiedsrichter'), 'sec_Schiedsrichter'],
    ['fan', 'Fan-Info', itemSection('Fan-Info'), 'sec_Fan-Info'],
    ['youth', 'Jugend', itemSection('Jugend'), 'sec_Jugend'],
    ['back', 'Rückseite', itemSection('Rückseite'), 'sec_Rückseite'],
  ];
  // Eigener Text zum Gegner hängt an den automatischen an
  if (texts['sec_Gegner']) texts.opponent = [texts.opponent, texts['sec_Gegner']].filter(Boolean).join('\n\n');
  texts.all = sections.map(([, title, , key]) => texts[key] ? `===== ${title} =====\n\n${texts[key]}` : '').filter(Boolean).join('\n\n\n');

  const cl = magChecklist(m), d = daysUntil(m.deadline);
  view.innerHTML = `
    <div class="page-head"><h1>${esc(magLabel(m))}<small><a href="#/magazine">Stadionheft</a> | ${g ? esc(gameLabel(g)) : 'kein Heimspiel zugeordnet'}${m.deadline ? ` | Redaktionsschluss ${fmtDate(m.deadline)}${m.status !== 'Fertig' && d !== null ? (d >= 0 ? ` (in ${d} Tagen)` : ' (vorbei)') : ''}` : ''}</small></h1>
      <div class="btn-row">${magBadge(m.status)}
        ${m.canva_url ? `<a class="btn keep" href="${esc(m.canva_url)}" target="_blank" rel="noopener">In Canva öffnen</a>` : ''}
        <button class="btn keep" data-copy="all">Alles kopieren</button>
        ${prev ? `<button class="pp btn" id="mg_prev" title="Sponsoren, Fan-Info, Jugend und Rückseite">Aus „${esc(magLabel(prev))}“ übernehmen</button>` : ''}
        <button class="pp btn" id="mg_edit">Heft bearbeiten</button></div></div>
    <div class="card mag-check">${cl.map(([name, ok, hint]) => `<span class="mag-chip ${ok ? 'ok' : ''}" title="${esc(hint || '')}"><span class="dot ${ok ? 'ok' : 'red'}"></span>${esc(name)}</span>`).join('')}</div>
    <div class="mag-nav">${sections.map(([key, title]) => `<a href="#" data-jump="${key}">${esc(title)}</a>`).join('')}</div>
    ${sections.map(([key, title, html, copyKey]) => `<section class="card mag-sec" id="mag_${key}">
      <div class="mag-sec-head"><h2>${esc(title)}</h2>${texts[copyKey] ? copyBtn(copyKey) : ''}</div>${html}</section>`).join('')}`;

  $$('[data-copy]', view).forEach(b => b.onclick = () => copyText(noDashes(texts[b.dataset.copy] || '')));
  $$('[data-jump]', view).forEach(a => a.onclick = e => { e.preventDefault(); $('#mag_' + a.dataset.jump).scrollIntoView({ behavior: 'smooth', block: 'start' }); });
  $$('[data-item]', view).forEach(b => b.onclick = async () => { if (await editMagItem(m, byId(App.cache.magazine_pages, b.dataset.item))) rerender(); });
  $$('[data-add]', view).forEach(b => b.onclick = async () => { if (await editMagItem(m, { section: b.dataset.add })) rerender(); });
  $$('[data-addgame]', view).forEach(a => a.onclick = async e => { e.preventDefault(); if (await editMagItem(m, { section: 'Spielbericht', game_id: Number(a.dataset.addgame) })) rerender(); });
  const saveSponsors = async ids => { await api(`magazines/${id}`, 'PUT', { sponsor_ids: JSON.stringify(ids) }); toast('Sponsoren gespeichert'); rerender(); };
  $$('[data-sp]', view).forEach(cb => cb.onchange = () => saveSponsors($$('[data-sp]', view).filter(c => c.checked).map(c => Number(c.dataset.sp))));
  if ($('#mg_spall')) $('#mg_spall').onclick = () => saveSponsors(App.cache.sponsors.filter(s => Number(s.active)).map(s => s.id));
  $('#mg_edit').onclick = async () => {
    const r = await editRecord('magazines', F.magazines(), m, { editTitle: 'Heft bearbeiten' });
    if (r?.deleted) { invalidate('magazine_pages'); go('#/magazine'); } else if (r) rerender();
  };
  if ($('#mg_prev')) $('#mg_prev').onclick = async () => {
    const take = Object.keys(MAG_ITEMS).filter(s => MAG_ITEMS[s].reuse && !magItems(id, s).length);
    const items = magItems(prev.id).filter(i => take.includes(i.section));
    const sp = !magSponsorIds(m).length && magSponsorIds(prev).length;
    if (!items.length && !sp) return toast('Nichts zu übernehmen');
    if (!confirmBox(`Aus „${magLabel(prev)}“ übernehmen: ${[sp ? 'Sponsorenauswahl' : '', ...new Set(items.map(i => i.section))].filter(Boolean).join(', ')}?`)) return;
    if (sp) await api(`magazines/${id}`, 'PUT', { sponsor_ids: prev.sponsor_ids });
    for (const i of items) await api('magazine_pages', 'POST', { magazine_id: id, section: i.section, title: i.title, text: i.text, files: i.files, image: i.image });
    toast('Übernommen'); rerender();
  };
}

async function editMagItem(m, rec) {
  const section = rec.section, fields = magItemFields(section), isNew = !rec.id;
  rec = { ...rec };
  if (section === 'Behind the Helmet') { const a = magAnswers(rec); BTH_QUESTIONS.forEach((q, i) => { rec['q' + i] = a[q] || ''; }); }
  if (isNew && section === 'Vorwort') rec.title = 'Vorwort';
  if (isNew && section === 'Schiedsrichter') rec.text = 'Heute für uns im Einsatz:\n' + MAG_REFS.map(r => r + ': ').join('\n');
  if (isNew && section === 'Rückseite') { const s = App.settings; rec.title = 'Werde Teil von Wolthusen!'; rec.text = [s.training_text ? 'Training: ' + s.training_text : '', s.club_name, s.instagram ? 'Instagram: @' + s.instagram : ''].filter(Boolean).join('\n'); }
  const name = MAG_ITEMS[section]?.title || section;
  return editRecord('magazine_pages', fields, rec, {
    newTitle: name, editTitle: name, fixed: { magazine_id: m.id, section },
    beforeSave: vals => {
      if (section === 'Behind the Helmet') {
        const a = {}; BTH_QUESTIONS.forEach((q, i) => { a[q] = vals['q' + i] || ''; delete vals['q' + i]; });
        vals.answers = JSON.stringify(a);
      }
      if (section === 'Spielbericht' && !String(vals.text || '').trim()) vals.text = magGameText(byId(App.cache.games, vals.game_id));
    },
  });
}

