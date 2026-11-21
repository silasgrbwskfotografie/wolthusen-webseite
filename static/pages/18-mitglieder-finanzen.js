/* ====================================================================== */
/* Mitglieder */
const MEMBER_TYPES = ['Spieler', 'Trainer', 'Vorstand', 'Helfer', 'Fotograf', 'Förderer', 'Sonstige'];
const MEMBER_STATUS = ['Aktiv', 'Probetraining', 'Passiv', 'Ausgetreten'];
F.members = [
  { key: 'first_name', label: 'Vorname' },
  { key: 'last_name', label: 'Nachname' },
  { key: 'member_type', label: 'Art', type: 'select', options: MEMBER_TYPES },
  { key: 'status', label: 'Status', type: 'select', options: MEMBER_STATUS },
  { key: 'birthdate', label: 'Geburtsdatum', type: 'date' },
  { key: 'member_since', label: 'Mitglied seit', type: 'date' },
  { key: 'email', label: 'E-Mail' },
  { key: 'phone', label: 'Telefon' },
  { key: 'street', label: 'Straße und Hausnummer', full: true },
  { key: 'zip', label: 'PLZ' },
  { key: 'city', label: 'Ort' },
  { key: 'emergency_contact', label: 'Notfallkontakt', full: true },
  { key: 'player_id', label: 'Im Kader', type: 'ref', ref: { table: 'players', label: playerLabel } },
  { key: 'exit_date', label: 'Ausgetreten am', type: 'date', show: v => v.status === 'Ausgetreten' },
  { key: 'consent_photo', label: 'Foto-Einwilligung liegt vor', type: 'check' },
  { key: 'equipment', label: 'Ausrüstung (Helm, Pads, Trikot)', type: 'textarea', rows: 2 },
  { key: 'notes', label: 'Notizen', type: 'textarea', rows: 2 },
];

App.pages.members = async (view) => {
  await loadAll('members', 'players');
  const users = App.me.is_admin ? await api('admin/users') : [];
  let st = App._mStatus || 'aktiv', type = App._mType || 'Alle', q = '';
  const draw = () => {
    App._mStatus = st; App._mType = type;
    let list = [...App.cache.members];
    if (st === 'aktiv') list = list.filter(m => m.status !== 'Ausgetreten');
    else if (st !== 'alle') list = list.filter(m => m.status === st);
    if (type !== 'Alle') list = list.filter(m => m.member_type === type);
    if (q) list = list.filter(m => (fullName(m) + ' ' + (m.email || '') + ' ' + (m.phone || '')).toLowerCase().includes(q));
    list.sort((a, b) => (a.last_name || '').localeCompare(b.last_name || '') || (a.first_name || '').localeCompare(b.first_name || ''));
    const counts = MEMBER_STATUS.map(s => [s, App.cache.members.filter(m => m.status === s).length]);
    const userOf = m => users.find(u => u.member_id == m.id);
    view.innerHTML = `
      <div class="page-head"><h1>Mitglieder<small>${counts.filter(c => c[1]).map(c => `${c[1]} ${c[0].toLowerCase()}`).join(', ') || 'noch keine Einträge'}</small></h1>
        <div class="btn-row"><button class="btn keep" id="m_csv">CSV exportieren</button><button class="btn" id="m_import">Aus Kader übernehmen</button><button class="btn primary" id="m_new">+ Mitglied</button></div></div>
      <div class="toolbar">
        ${[['aktiv', 'Aktuelle'], ...MEMBER_STATUS.map(s => [s, s]), ['alle', 'Alle']].map(([k, l]) => `<button class="btn sm ${k === st ? 'dark' : ''}" data-ms="${k}">${l}</button>`).join('')}
        <select class="input" id="m_type" style="width:auto">${['Alle', ...MEMBER_TYPES].map(t => `<option ${t === type ? 'selected' : ''}>${t}</option>`).join('')}</select>
        <input class="input" id="m_q" placeholder="Suchen" style="max-width:220px" value="${esc(q)}">
      </div>
      <div class="table-wrap"><table><thead><tr><th>Name</th><th>Art</th><th>Status</th><th>Telefon</th><th>E-Mail</th><th>Mitglied seit</th><th>Foto</th>${App.me.is_admin ? '<th>Zugang</th>' : ''}<th></th></tr></thead><tbody>
      ${list.map(m => { const u = userOf(m); return `<tr style="${m.status === 'Ausgetreten' ? 'opacity:.55' : ''}">
        <td><b>${esc(fullName(m))}</b>${m.player_id ? ' <span class="badge" title="Im Kader">Kader</span>' : ''}</td>
        <td>${esc(m.member_type || '')}</td>
        <td><span class="badge ${m.status === 'Aktiv' ? 'ok' : m.status === 'Probetraining' ? 'warn' : ''}">${esc(m.status || '')}</span></td>
        <td class="small">${m.phone ? `<a href="tel:${esc(m.phone.replace(/\s/g, ''))}">${esc(m.phone)}</a>` : ''}</td>
        <td class="small">${m.email ? `<a href="mailto:${esc(m.email)}">${esc(m.email)}</a>` : ''}</td>
        <td class="small">${fmtDate(m.member_since)}</td>
        <td>${Number(m.consent_photo) ? '<span class="badge ok">ja</span>' : '<span class="badge warn">fehlt</span>'}</td>
        ${App.me.is_admin ? `<td>${u ? `<span class="badge ${u.invite_open ? 'warn' : 'ok'}">${u.invite_open ? 'eingeladen' : esc(u.username)}</span>` : `<button class="btn sm keep" data-acc="${m.id}">Zugang anlegen</button>`}</td>` : ''}
        <td class="actions"><button class="btn sm ghost" data-e="${m.id}">Bearbeiten</button></td></tr>`; }).join('')
        || `<tr><td colspan="9" class="empty">Keine Mitglieder in dieser Ansicht.</td></tr>`}
      </tbody></table></div>`;
    $$('[data-ms]').forEach(b => b.onclick = () => { st = b.dataset.ms; draw(); });
    $('#m_type').onchange = e => { type = e.target.value; draw(); };
    $('#m_q').oninput = e => { q = e.target.value.toLowerCase(); const pos = e.target.selectionStart; draw(); const el = $('#m_q'); el.focus(); el.setSelectionRange(pos, pos); };
    const edit = async rec => { const r = await editRecord('members', F.members, rec, { newTitle: 'Neues Mitglied', editTitle: 'Mitglied bearbeiten' }); if (r) { await load('members', true); draw(); } };
    $('#m_new').onclick = () => edit({ status: 'Aktiv', member_type: 'Spieler', member_since: todayStr() });
    $$('[data-e]').forEach(b => b.onclick = () => edit(byId(App.cache.members, b.dataset.e)));
    $$('[data-acc]').forEach(b => b.onclick = () => accountDialog(null, byId(App.cache.members, b.dataset.acc)));
    $('#m_csv').onclick = () => downloadCsv(`mitglieder-${todayStr()}.csv`,
      ['Vorname', 'Nachname', 'Art', 'Status', 'Geburtsdatum', 'E-Mail', 'Telefon', 'Straße', 'PLZ', 'Ort', 'Mitglied seit', 'Foto-Einwilligung'],
      list.map(m => [m.first_name, m.last_name, m.member_type, m.status, fmtDate(m.birthdate), m.email, m.phone, m.street, m.zip, m.city, fmtDate(m.member_since), Number(m.consent_photo) ? 'ja' : 'nein']));
    $('#m_import').onclick = async () => {
      const linked = new Set(App.cache.members.map(m => String(m.player_id)));
      const todo = App.cache.players.filter(p => Number(p.active) && !linked.has(String(p.id)));
      if (!todo.length) return toast('Alle aktiven Kader-Personen sind schon Mitglieder');
      if (!confirmBox(`${todo.length} Personen aus dem Kader als Mitglieder anlegen?`)) return;
      for (const p of todo) await api('members', 'POST', {
        first_name: p.first_name, last_name: p.last_name, player_id: p.id, status: 'Aktiv', consent_photo: Number(p.consent) ? 1 : 0,
        member_type: p.kind === 'Spieler' ? 'Spieler' : 'Trainer',
      });
      await load('members', true); toast(`${todo.length} Mitglieder angelegt`); draw();
    };
  };
  draw();
};

/* ====================================================================== */
/* Finanzen */
const TX_CATEGORIES = ['Sponsoring', 'Dauerkarte', 'Spenden', 'Mitgliedsbeiträge', 'Eintritt', 'Verkauf / Merch', 'Ausrüstung', 'Platz / Halle',
  'Schiedsrichter', 'Verband / Liga', 'Fahrtkosten', 'Medien / Technik', 'Veranstaltungen', 'Versicherung', 'Sonstiges'];
F.transactions = [
  { key: 'date', label: 'Datum', type: 'date', default: todayStr() },
  { key: 'kind', label: 'Art', type: 'select', options: ['Ausgabe', 'Einnahme'] },
  { key: 'amount', label: 'Betrag (€)', type: 'number' },
  { key: 'category', label: 'Kategorie', list: TX_CATEGORIES },
  { key: 'description', label: 'Beschreibung', full: true },
  { key: 'status', label: 'Status', type: 'select', options: ['Erledigt', 'Offen'], hint: 'Offen = noch nicht bezahlt bzw. noch nicht eingegangen' },
  { key: 'paid_by', label: 'Bezahlt von / an' },
  { key: 'sponsor_id', label: 'Sponsor', type: 'ref', ref: { table: 'sponsors', label: sponsorLabel } },
  { key: 'member_id', label: 'Mitglied', type: 'ref', ref: { table: 'members', label: m => fullName(m) } },
  { key: 'receipt', label: 'Beleg (Foto oder PDF)', type: 'file', full: true },
  { key: 'notes', label: 'Notizen', type: 'textarea', rows: 2 },
];

App.pages.finance = async (view) => {
  await loadAll('transactions', 'sponsors', 'members', 'supporter_cards');
  const years = [...new Set([String(new Date().getFullYear()), ...App.cache.transactions.map(t => (t.date || '').slice(0, 4)).filter(Boolean)])].sort().reverse();
  let year = App._finYear || years[0], kind = 'Alle', cat = 'Alle';
  const draw = () => {
    App._finYear = year;
    const inYear = App.cache.transactions.filter(t => year === 'alle' || (t.date || '').startsWith(year));
    let list = inYear;
    if (kind !== 'Alle') list = list.filter(t => t.kind === kind || (kind === 'Offen' && t.status === 'Offen'));
    if (cat !== 'Alle') list = list.filter(t => t.category === cat);
    list = [...list].sort((a, b) => (b.date || '').localeCompare(a.date || '') || b.id - a.id);
    const sum = (arr, k) => arr.filter(t => t.kind === k).reduce((a, t) => a + (Number(t.amount) || 0), 0);
    const inc = sum(inYear, 'Einnahme'), exp = sum(inYear, 'Ausgabe');
    const cats = {};
    inYear.forEach(t => { const k = (t.category || 'Ohne Kategorie'); cats[k] = cats[k] || { inc: 0, exp: 0 }; cats[k][t.kind === 'Einnahme' ? 'inc' : 'exp'] += Number(t.amount) || 0; });
    const cards = App.cache.supporter_cards.filter(c => year === 'alle' || c.season == year);
    const cardSum = cards.reduce((a, c) => a + (Number(c.price) || 0), 0);
    const sponsorSum = App.cache.sponsors.filter(s => Number(s.active)).reduce((a, s) => a + (parseFloat(String(s.amount || '').replace(/\./g, '').replace(',', '.')) || 0), 0);
    view.innerHTML = `
      <div class="page-head"><h1>Finanzen<small>Einnahmen und Ausgaben ${year === 'alle' ? 'gesamt' : year}</small></h1>
        <div class="btn-row"><button class="btn keep" id="f_csv">CSV exportieren</button><button class="btn primary" id="f_new">+ Buchung</button></div></div>
      <div class="toolbar">${[...years, 'alle'].map(y => `<button class="btn sm ${y === year ? 'dark' : ''}" data-y="${y}">${y === 'alle' ? 'Alle Jahre' : y}</button>`).join('')}</div>
      <div class="grid g4" style="margin-bottom:16px">
        <div class="card stat"><span>Einnahmen</span><b style="color:var(--ok)">${eur(inc)}</b></div>
        <div class="card stat"><span>Ausgaben</span><b>${eur(exp)}</b></div>
        <div class="card stat"><span>Saldo</span><b style="color:${inc - exp < 0 ? 'var(--red)' : 'var(--ok)'}">${eur(inc - exp)}</b></div>
        <div class="card stat"><span>Offen</span><b>${inYear.filter(t => t.status === 'Offen').length}</b></div>
      </div>
      <div class="grid g2" style="margin-bottom:16px">
        <div class="card"><h2>Nach Kategorie</h2>
          ${Object.keys(cats).length ? Object.entries(cats).sort((a, b) => (b[1].inc + b[1].exp) - (a[1].inc + a[1].exp)).map(([k, v]) =>
            `<div class="sum-row"><span>${esc(k)}</span><span>${v.inc ? `<b style="color:var(--ok)">+${eur(v.inc)}</b> ` : ''}${v.exp ? `<b>-${eur(v.exp)}</b>` : ''}</span></div>`).join('') : '<div class="muted">Noch keine Buchungen.</div>'}
        </div>
        <div class="card"><h2>Weitere Quellen</h2>
          <div class="sum-row"><span>Dauerkarten ${year === 'alle' ? '' : year} (${cards.length} Stück)</span><b>${eur(cardSum)}</b></div>
          <div class="sum-row"><span>Davon Anteil Wolthusen</span><b>${eur(cards.length * (Number(App.settings.card_share_wolthusen) || 0))}</b></div>
          <div class="sum-row"><span>Vereinbarte Beträge aktiver Sponsoren</span><b>${eur(sponsorSum)}</b></div>
          <div class="hint" style="margin-top:8px">Diese Werte sind nur zur Übersicht. Tatsächliche Zahlungseingänge bitte als Buchung erfassen.</div>
        </div>
      </div>
      <div class="toolbar">
        ${['Alle', 'Einnahme', 'Ausgabe', 'Offen'].map(k => `<button class="btn sm ${k === kind ? 'dark' : ''}" data-k="${k}">${k === 'Alle' ? 'Alle' : k === 'Offen' ? 'Offen' : k + 'n'}</button>`).join('')}
        <select class="input" id="f_cat" style="width:auto">${['Alle', ...new Set([...TX_CATEGORIES, ...App.cache.transactions.map(t => t.category).filter(Boolean)])].map(c => `<option ${c === cat ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>
      </div>
      <div class="table-wrap"><table><thead><tr><th>Datum</th><th>Beschreibung</th><th>Kategorie</th><th>Bezahlt von / an</th><th style="text-align:right">Betrag</th><th>Status</th><th>Beleg</th><th></th></tr></thead><tbody>
      ${list.map(t => `<tr>
        <td class="small" style="white-space:nowrap">${fmtDate(t.date)}</td>
        <td><b>${esc(t.description || '')}</b>${t.sponsor_id ? `<div class="muted small">${esc(byId(App.cache.sponsors, t.sponsor_id)?.name || '')}</div>` : ''}</td>
        <td class="small">${esc(t.category || '')}</td>
        <td class="small">${esc(t.paid_by || (t.member_id ? fullName(byId(App.cache.members, t.member_id)) : ''))}</td>
        <td style="text-align:right;white-space:nowrap"><b style="color:${t.kind === 'Einnahme' ? 'var(--ok)' : 'inherit'}">${t.kind === 'Einnahme' ? '+' : '-'}${eur(t.amount)}</b></td>
        <td>${t.status === 'Offen' ? '<span class="badge warn">offen</span>' : '<span class="badge ok">erledigt</span>'}</td>
        <td>${t.receipt ? `<a class="btn sm keep" href="${esc(t.receipt)}" target="_blank" rel="noopener">Ansehen</a>` : ''}</td>
        <td class="actions"><button class="btn sm ghost" data-e="${t.id}">Bearbeiten</button></td></tr>`).join('')
        || '<tr><td colspan="8" class="empty">Keine Buchungen in dieser Ansicht.</td></tr>'}
      </tbody></table></div>`;
    $$('[data-y]').forEach(b => b.onclick = () => { year = b.dataset.y; draw(); });
    $$('[data-k]').forEach(b => b.onclick = () => { kind = b.dataset.k; draw(); });
    $('#f_cat').onchange = e => { cat = e.target.value; draw(); };
    const edit = async rec => { const r = await editRecord('transactions', F.transactions, rec, { newTitle: 'Neue Buchung', editTitle: 'Buchung bearbeiten' }); if (r) { await load('transactions', true); draw(); } };
    $('#f_new').onclick = () => edit({ date: todayStr(), kind: 'Ausgabe', status: 'Erledigt' });
    $$('[data-e]').forEach(b => b.onclick = () => edit(byId(App.cache.transactions, b.dataset.e)));
    $('#f_csv').onclick = () => downloadCsv(`buchungen-${year}.csv`, ['Datum', 'Art', 'Betrag', 'Kategorie', 'Beschreibung', 'Bezahlt von / an', 'Status', 'Beleg'],
      list.map(t => [fmtDate(t.date), t.kind, String(Number(t.amount) || 0).replace('.', ','), t.category, t.description, t.paid_by, t.status, t.receipt ? location.origin + t.receipt : '']));
  };
  draw();
};

