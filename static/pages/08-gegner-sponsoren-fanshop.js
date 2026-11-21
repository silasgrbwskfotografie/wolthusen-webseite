/* ====================================================================== */
/* Einfache Listen-Seiten */
function simpleList({ table, title, sub, fields, columns, newTitle, newRecord = {}, extraHead = '', sort }) {
  return async (view) => {
    const list = [...await load(table, true)];
    if (sort) list.sort(sort);
    const fl = typeof fields === 'function' ? fields() : fields;
    view.innerHTML = `
      <div class="page-head"><h1>${title}<small>${typeof sub === 'function' ? sub(list) : list.length + ' Einträge'}</small></h1>
        <div class="btn-row"><button class="btn primary" id="sl_new">+ ${newTitle}</button></div></div>
      ${extraHead ? await extraHead(list) : ''}
      <div class="table-wrap"><table><thead><tr>${columns.map(c => `<th>${c.label}</th>`).join('')}<th></th></tr></thead><tbody>
      ${list.map(r => `<tr>${columns.map(c => `<td>${c.html(r)}</td>`).join('')}<td class="actions">${c_actions(table, r)}<button class="btn sm ghost" data-e="${r.id}">Bearbeiten</button></td></tr>`).join('')
        || `<tr><td colspan="${columns.length + 1}" class="empty">Noch nichts eingetragen.</td></tr>`}
      </tbody></table></div>`;
    const edit = async rec => { const r = await editRecord(table, fl, rec, { newTitle, editTitle: 'Bearbeiten' }); if (r) route(); };
    $('#sl_new').onclick = () => edit({ ...newRecord });
    $$('[data-e]').forEach(b => b.onclick = () => edit(byId(list, b.dataset.e)));
  };
}
function c_actions(table, r) {
  if (table === 'sponsors') return `<button class="pp btn sm" onclick="planPost({type:'Sponsor',sponsor_id:${r.id}})">Post planen</button> `
    + (can('finanzen') ? `<a class="vw btn sm" href="#/sponsors/vertraege/${r.id}">Vertrag</a> ` : '');
  return '';
}

App.pages.opponents = simpleList({
  table: 'opponents', title: 'Gegner', fields: F.opponents, newTitle: 'Gegner',
  sort: (a, b) => (a.name || '').localeCompare(b.name || ''),
  columns: [
    { label: '', html: r => r.logo ? `<img class="thumb logo" src="${esc(r.logo)}">` : '<div class="thumb"></div>' },
    { label: 'Name', html: r => `<b>${esc(r.name)}</b>${r.short ? `<div class="muted small">${esc(r.short)}</div>` : ''}` },
    { label: 'Stadt', html: r => esc(r.city || '') },
    { label: 'Instagram', html: r => esc(handle(r.instagram)) },
  ],
});

// Trainingszeiten je Mannschaft: erscheinen auf der Webseite bei der Mannschaft (nur aktive)
const WD_ORDER = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];
App.pages.trainings = simpleList({
  table: 'trainings', title: 'Trainingszeiten', fields: F.trainings, newTitle: 'Trainingszeit', newRecord: { active: 1, team: TEAMS[0] },
  sub: list => `${list.filter(r => Number(r.active)).length} auf der Webseite`,
  sort: (a, b) => ((TEAMS.indexOf(a.team) + 1) || 99) - ((TEAMS.indexOf(b.team) + 1) || 99) || (a.team || '').localeCompare(b.team || '')
    || WD_ORDER.indexOf(a.weekday) - WD_ORDER.indexOf(b.weekday) || (a.start || '').localeCompare(b.start || ''),
  columns: [
    { label: 'Mannschaft', html: r => `<b>${esc(r.team || '')}</b>` },
    { label: 'Wann', html: r => `${esc(r.weekday || '')} ${esc(r.start || '')}${r.end ? ' bis ' + esc(r.end) : ''} Uhr${r.season ? `<div class="muted small">${esc(r.season)}</div>` : ''}` },
    { label: 'Ort', html: r => esc(r.place || '') },
    { label: 'Webseite', html: r => Number(r.active) ? '<span class="badge ok">sichtbar</span>' : '<span class="badge">aus</span>' },
  ],
});

// Belegung von Saal, Platz und Halle (nur intern): kommende zuerst, dann vergangene
const bkFuture = r => (r.date || '') >= todayStr();
App.pages.bookings = simpleList({
  table: 'bookings', title: 'Belegung Saal &amp; Platz', fields: F.bookings, newTitle: 'Belegung', newRecord: { resource: 'Saal', status: 'Anfrage', date: todayStr() },
  sub: list => `${list.filter(r => r.status !== 'Abgesagt' && bkFuture(r)).length} kommende`,
  sort: (a, b) => bkFuture(b) - bkFuture(a) || (bkFuture(a) ? (a.date || '').localeCompare(b.date || '') : (b.date || '').localeCompare(a.date || ''))
    || (a.start || '').localeCompare(b.start || ''),
  columns: [
    { label: 'Datum', html: r => `<b>${fmtDate(r.date)}</b><div class="muted small">${r.start ? esc(r.start) + (r.end ? ' bis ' + esc(r.end) : '') + ' Uhr' : ''}</div>` },
    { label: 'Was', html: r => `${esc(r.resource || '')}<div class="muted small">${esc(r.title || '')}</div>` },
    { label: 'Mieter', html: r => `${esc(r.renter || '')}<div class="muted small">${esc(r.contact || '')}</div>` },
    { label: 'Status', html: r => `<span class="badge ${r.status === 'Bestätigt' ? 'ok' : r.status === 'Abgesagt' ? '' : 'warn'}">${esc(r.status || '')}</span>`
      + (Number(r.price) ? ` <span class="badge ${Number(r.paid) ? 'ok' : 'warn'}">${esc(String(r.price).replace('.', ','))} € ${Number(r.paid) ? 'bezahlt' : 'offen'}</span>` : '') },
  ],
});

const sponsorTabs = act => `<div class="toolbar">${[['', 'Sponsoren'], ['pakete', 'Pakete'], ...(can('finanzen') ? [['vertraege', 'Verträge']] : [])].map(([k, l]) =>
  `<a class="btn sm ${k === act ? 'dark' : ''}" href="#/sponsors${k ? '/' + k : ''}">${l}</a>`).join('')}</div>`;
App.pages.sponsors = async (view, args = []) => {
  if (args[0] === 'pakete') return sponsorPackages(view);
  if (args[0] === 'vertraege') return sponsorContracts(view, args[1]);
  await loadAll('posts', 'sponsor_packages');
  return simpleList({
    extraHead: () => sponsorTabs(''),
    table: 'sponsors', title: 'Sponsoren', fields: F.sponsors, newTitle: 'Sponsor', newRecord: { active: 1 },
    sub: l => `${l.filter(s => Number(s.active)).length} aktiv`,
    sort: (a, b) => Number(b.active) - Number(a.active) || (a.name || '').localeCompare(b.name || ''),
    columns: [
      { label: '', html: r => r.logo ? `<img class="thumb logo" src="${esc(r.logo)}">` : '<div class="thumb"></div>' },
      { label: 'Name', html: r => `<b style="${Number(r.active) ? '' : 'opacity:.5'}">${esc(r.name)}</b>${r.contact ? `<div class="muted small">${esc(r.contact)}</div>` : ''}` },
      { label: 'Paket', html: r => (r.package ? `<span class="badge">${esc(r.package)}</span>` : '')
        + (r.package_id ? `<div class="muted small" title="internes Sponsorenpaket">${esc(byId(App.cache.sponsor_packages, r.package_id)?.name || '')}</div>` : '') },
      ...(can('finanzen') ? [{ label: 'Leistung', html: r => esc(r.amount || '') }] : []),
      { label: 'Laufzeit', html: r => [fmtDate(r.start), fmtDate(r.end)].filter(Boolean).join(' bis ') },
      { label: 'Posts', html: r => { const done = App.cache.posts.filter(p => p.sponsor_id == r.id && p.status === 'Gepostet').length; const ag = Number(r.posts_agreed) || 0; return ag ? `<span class="badge ${done >= ag ? 'ok' : 'warn'}">${done}/${ag}</span>` : `<span class="muted small">${done} gepostet</span>`; } },
      { label: 'Instagram', html: r => esc(handle(r.instagram)) },
      { label: 'Dateien', html: r => { const n = parseFiles(r.files).length; return n ? `<span class="badge">${n} ${n === 1 ? 'Datei' : 'Dateien'}</span>` : ''; } },
    ],
  })(view);
};

/* Medien > Fanshop: Produkte für das Laufband auf der Startseite (Tabelle shop_products) */
App.pages.shop = simpleList({
  table: 'shop_products', title: 'Fanshop', fields: F.shop_products, newTitle: 'Produkt', newRecord: { active: 1 },
  sub: l => `${l.filter(p => Number(p.active) && p.image).length} auf der Startseite. Das Laufband an- und ausschalten und verschieben: Webseite > Startseite`,
  sort: (a, b) => Number(b.active) - Number(a.active) || (Number(a.sort) || 0) - (Number(b.sort) || 0) || (a.name || '').localeCompare(b.name || ''),
  columns: [
    { label: '', html: r => r.image ? `<img class="thumb" src="${esc(r.image)}" alt="">` : '<div class="thumb"></div>' },
    { label: 'Produkt', html: r => `<b style="${Number(r.active) ? '' : 'opacity:.5'}">${esc(r.name || '')}</b>${Number(r.is_new) ? ' <span class="badge red">Neu</span>' : ''}${Number(r.colors) ? ' <span class="badge">mehrere Farben</span>' : ''}${r.image ? '' : '<div class="small" style="color:var(--red)">ohne Bild, erscheint nicht</div>'}` },
    { label: 'Preis', html: r => esc(r.price || '') },
    { label: 'Link', html: r => r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener" class="small">Produkt öffnen</a>` : '<span class="muted small">Fanshop allgemein</span>' },
  ],
});

/* Sponsoren > Pakete: intern (Tabelle sponsor_packages), Zuweisung über Sponsor bearbeiten > Sponsorenpaket */
async function sponsorPackages(view) {
  await load('sponsors', true);
  const lines = t => String(t || '').split('\n').map(x => x.trim()).filter(Boolean);
  return simpleList({
    table: 'sponsor_packages', title: 'Sponsorenpakete', fields: F.sponsor_packages, newTitle: 'Paket', newRecord: { active: 1 },
    sub: l => `${l.filter(p => Number(p.active)).length} aktiv, nur intern`,
    sort: (a, b) => Number(b.active) - Number(a.active) || (Number(a.sort) || 0) - (Number(b.sort) || 0) || (a.name || '').localeCompare(b.name || ''),
    extraHead: () => sponsorTabs('pakete'),
    columns: [
      { label: 'Paket', html: r => `<b style="${Number(r.active) ? '' : 'opacity:.5'}">${esc(r.name || '')}</b>${r.season ? `<div class="muted small">${esc(r.season)}</div>` : ''}` },
      ...(can('finanzen') ? [{ label: 'Preis', html: r => esc(r.price || '') }] : []),
      { label: 'Leistungen', html: r => { const l = lines(r.services); return l.length ? `<ul class="small" style="margin:0;padding-left:18px">${l.slice(0, 6).map(x => `<li>${esc(x)}</li>`).join('')}${l.length > 6 ? `<li class="muted">und ${l.length - 6} weitere</li>` : ''}</ul>` : ''; } },
      { label: 'Sponsoren', html: r => { const s = App.cache.sponsors.filter(x => x.package_id == r.id); return s.length ? s.map(x => `<span class="badge" style="${Number(x.active) ? '' : 'opacity:.5'}">${esc(x.name)}</span>`).join(' ') : '<span class="muted small">keiner</span>'; } },
    ],
  })(view);
}

App.pages.team = async (view) => {
  await loadAll('games', 'opponents', 'assignments');
  return simpleList({
    table: 'media_team', title: 'Media Team', fields: F.media_team, newTitle: 'Mitglied', newRecord: { active: 1 },
    sub: l => `${l.filter(m => Number(m.active)).length} aktiv`,
    sort: (a, b) => Number(b.active) - Number(a.active) || (a.name || '').localeCompare(b.name || ''),
    extraHead: async () => {
      const today = todayStr();
      const next = App.cache.games.filter(g => g.date >= today).sort((a, b) => a.date.localeCompare(b.date)).slice(0, 4);
      if (!next.length) return '';
      return `<h2>Einteilung kommende Spiele</h2><div class="grid g4" style="margin-bottom:20px">${next.map(g => {
        const asg = App.cache.assignments.filter(a => a.game_id == g.id && a.member_id).length;
        return `<div class="card"><b>${fmtDate(g.date)}</b><div class="muted small" style="margin-bottom:8px">${Number(g.home) ? 'vs' : '@'} ${esc(byId(App.cache.opponents, g.opponent_id)?.name || 'TBA')}</div>
          <button class="btn sm ${asg >= mediaTasks().length ? '' : 'primary'}" onclick="assignGame(${g.id})">${asg}/${mediaTasks().length} eingeteilt</button></div>`;
      }).join('')}</div>`;
    },
    columns: [
      { label: 'Name', html: r => `<b style="${Number(r.active) ? '' : 'opacity:.5'}">${esc(r.name)}</b>` },
      { label: 'Hauptaufgabe', html: r => esc(r.role || '') },
      { label: 'Telefon', html: r => esc(r.phone || '') },
      { label: 'Instagram', html: r => esc(handle(r.instagram)) },
      { label: 'Einsätze', html: r => App.cache.assignments.filter(a => a.member_id == r.id).length },
    ],
  })(view);
};

/* Sponsoren > Verträge: Sponsoringvertrag als PDF erstellen, speichern (hängt auch als Datei am Sponsor) und herunterladen.
   Vorlage, keine Rechtsberatung. Eingaben prüft der Server (contract_clean), das PDF baut er selbst (sponsor_contract_pdf). */
async function sponsorContracts(view, forSponsor) {
  const [res, sponsors, packages] = await Promise.all([api('sponsor-contracts'), load('sponsors', true), load('sponsor_packages', true)]);
  const list = res.contracts;
  const money = v => Number(v || 0).toLocaleString('de-DE', { minimumFractionDigits: 2 }) + ' €';
  const download = (path, name) => { const a = document.createElement('a'); a.href = path; a.download = name; document.body.appendChild(a); a.click(); a.remove(); };
  view.innerHTML = `
    <div class="page-head"><h1>Sponsoren<small>Sponsoringverträge als PDF</small></h1>
      <div class="btn-row"><button class="btn primary vw" id="ct_new">+ Neuer Vertrag</button></div></div>
    ${sponsorTabs('vertraege')}
    <p class="muted small">Die Vorlage folgt dem deutschen Recht, ersetzt aber keine Rechtsberatung. Lass sie vor dem ersten Einsatz einmal von einem Anwalt prüfen.
      Absender und Bankverbindung kommen aus Dauerkarte &gt; Einstellungen. Jeder Vertrag wird gespeichert und hängt zusätzlich als Datei am Sponsor.</p>
    <div class="table-wrap"><table><thead><tr><th>Nr.</th><th>Sponsor</th><th>Laufzeit</th><th>Betrag</th><th>Erstellt</th><th></th></tr></thead><tbody>
    ${list.map(c => `<tr><td><b>${esc(c.number)}</b></td><td>${esc(c.sponsor)}</td><td>${fmtDate(c.data.start)} bis ${fmtDate(c.data.end)}</td>
      <td>${money(c.data.amount)}${(c.data.inkind || []).length ? ' <span class="badge">+ Sachleistung</span>' : ''}</td><td>${fmtDate((c.created || '').slice(0, 10))}</td>
      <td class="actions"><a class="btn sm keep" href="${esc(c.file)}" download="Sponsoringvertrag ${esc(c.number)}.pdf">PDF</a>
        ${Number(c.data.amount) > 0 && can('finanzen', 2) ? `<button class="btn sm" data-inv="${c.id}">Rechnung</button>` : ''}
        <button class="btn sm vw" data-edit="${c.id}">Bearbeiten</button><button class="btn sm vw" data-copy="${c.id}">Als Vorlage</button><button class="btn sm ghost vw" data-del="${c.id}">Löschen</button></td></tr>`).join('')
      || '<tr><td colspan="6" class="empty">Noch keine Verträge erstellt.</td></tr>'}
    </tbody></table></div>
    <h2 style="margin-top:24px">Rechnungen an Sponsoren</h2>
    <p class="muted small">Nummern laufen in derselben Folge wie alle Rechnungen des Vereins (RE-Jahr-0001). Rechnungen werden nicht gelöscht. Ist eine falsch, schreib eine Korrektur oder Gutschrift.</p>
    <div class="table-wrap"><table><thead><tr><th>Nr.</th><th>Sponsor</th><th>Vertrag</th><th>Datum</th><th>Fällig</th><th>Betrag</th><th></th></tr></thead><tbody>
    ${(res.invoices || []).map(i => `<tr><td><b>${esc(i.number)}</b></td><td>${esc(i.sponsor)}</td><td>${esc(i.contract)}</td><td>${fmtDate(i.data.date)}</td><td>${fmtDate(i.data.due)}</td>
      <td>${money(i.data.gross)}</td><td class="actions"><a class="btn sm keep" href="${esc(i.file)}" download="Rechnung ${esc(i.number)}.pdf">PDF</a></td></tr>`).join('')
      || '<tr><td colspan="7" class="empty">Noch keine Rechnungen an Sponsoren.</td></tr>'}
    </tbody></table></div>`;

  const form = (pre = {}, edit = null) => {   // edit: bestehender Vertrag (gleiche Nummer, neues PDF)
    const sp = byId(sponsors, pre.sponsor_id) || {};
    const pk = byId(packages, sp.package_id) || {};
    const last = list.find(c => String(c.sponsor_id) === String(pre.sponsor_id))?.data || {};
    const v = { partner_name: sp.name || '', services: pk.services || '', start: sp.start || '', end: sp.end || '', amount: sp.amount || pk.price || '',
      package_ids: sp.package_id ? [Number(sp.package_id)] : [], inkind: '', tax: '', pay: 'einmal', renew: false, notice: 3, place: 'Emden', court: 'Emden', club_rep: res.club_rep, ...last, ...pre };
    v.kind = v.kind || (Number(v.amount) > 0 || !(v.inkind || []).length ? ((v.inkind || []).length ? 'beides' : 'geld') : 'sach');
    const pkgs = packages.filter(p => Number(p.active) || (v.package_ids || []).includes(Number(p.id)))
      .sort((a, b) => (Number(a.sort) || 0) - (Number(b.sort) || 0) || (a.name || '').localeCompare(b.name || ''));
    const num = t => Number(String(t || '').replace(/[^\d,.]/g, '').replace(/\.(?=\d{3}(\D|$))/g, '').replace(',', '.')) || 0;
    const opt = (o, cur) => o.map(([k, l]) => `<option value="${k}" ${k === cur ? 'selected' : ''}>${l}</option>`).join('');
    openModal(`<h2>${edit ? `Vertrag ${esc(edit.number)} bearbeiten` : 'Sponsoringvertrag erstellen'}</h2>
      ${edit ? `<p class="muted small">Nummer bleibt gleich, das PDF wird neu erstellt und ersetzt das alte. Nur ändern, solange noch nicht unterschrieben ist.${
        (res.invoices || []).some(i => i.contract_id == edit.id) ? ' <b>Zu diesem Vertrag gibt es schon Rechnungen, die bleiben unverändert.</b>' : ''}</p>` : ''}
      <p class="muted small">Verein: ${esc((res.sender || '').split('\n')[0] || 'bitte unter Dauerkarte > Einstellungen eintragen')}</p>
      <form class="form" id="ct_form" onsubmit="return false">
        <div class="field full"><label for="ct_sp">Sponsor</label><select class="input" id="ct_sp" name="sponsor_id"><option value="">Sponsor wählen</option>
          ${sponsors.slice().sort((a, b) => (a.name || '').localeCompare(b.name || '')).map(s => `<option value="${s.id}" ${String(s.id) === String(v.sponsor_id) ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}</select></div>
        <div class="field"><label>Firma des Sponsors<input class="input" name="partner_name" maxlength="200" value="${esc(v.partner_name)}"></label></div>
        <div class="field"><label>Vertreten durch (Sponsor)<input class="input" name="partner_rep" maxlength="200" value="${esc(v.partner_rep || '')}" placeholder="z. B. Max Muster, Geschäftsführer"></label></div>
        <div class="field full"><label>Anschrift des Sponsors<textarea class="input" name="partner_address" rows="3" maxlength="500" placeholder="Straße Hausnummer&#10;PLZ Ort">${esc(v.partner_address || '')}</textarea></label></div>
        <div class="field full"><label>Verein vertreten durch<input class="input" name="club_rep" maxlength="200" value="${esc(v.club_rep || '')}" placeholder="Name und Vorstandsamt"></label></div>
        <div class="field full"><label>Art des Sponsorings<select class="input" name="kind" id="ct_kind">${opt([['geld', 'Geldsponsoring'], ['sach', 'Sachsponsoring'], ['beides', 'Geld- und Sachsponsoring']], v.kind)}</select></label></div>
        <div class="field full"><label>Sponsorenpakete</label>
          ${pkgs.length ? `<div class="check-list">${pkgs.map(p => `<label class="check"><input type="checkbox" name="pkg" value="${p.id}" ${(v.package_ids || []).includes(Number(p.id)) ? 'checked' : ''}>
            ${esc(p.name)}${p.season ? ` <span class="muted small">${esc(p.season)}</span>` : ''}${p.price ? ` <span class="muted small">(${esc(p.price)})</span>` : ''}</label>`).join('')}</div>
            <small class="muted">Mehrere möglich. Ein Haken füllt Leistungen und Betrag neu aus den Paketen, danach frei änderbar.</small>`
            : '<small class="muted">Noch keine Pakete angelegt (Sponsoren &gt; Pakete).</small>'}</div>
        <div class="field full"><label>Leistungen des Vereins (eine pro Zeile)<textarea class="input" name="services" rows="5">${esc(Array.isArray(v.services) ? v.services.join('\n') : v.services)}</textarea></label></div>
        <div class="field full" data-for="sach"><label>Sachleistungen des Sponsors (eine pro Zeile)<textarea class="input" name="inkind" rows="3" placeholder="z. B. Mediengerüst für alle Heimspiele (Wert etwa 800 €)">${esc(Array.isArray(v.inkind) ? v.inkind.join('\n') : v.inkind)}</textarea></label>
          <small class="muted">Was der Sponsor statt oder zusätzlich zum Geld stellt. Als Gegenleistung im Vertrag ist das keine Spende, eine Spendenquittung gibt es dafür nicht.</small></div>
        <div class="field"><label>Beginn<input class="input" type="date" name="start" value="${esc(v.start)}"></label></div>
        <div class="field"><label>Ende<input class="input" type="date" name="end" value="${esc(v.end)}"></label></div>
        <div class="field" data-for="geld"><label>Geldbetrag für die ganze Laufzeit (Euro)<input class="input" name="amount" inputmode="decimal" value="${esc(v.amount)}" placeholder="1.500,00"></label></div>
        <div class="field" data-for="geld"><label>Umsatzsteuer<select class="input" name="tax"><option value="">Bitte wählen</option>${opt([['zzgl', 'zuzüglich Umsatzsteuer'], ['inkl', 'inklusive Umsatzsteuer'], ['ku', 'Kleinunternehmer (keine Umsatzsteuer)']], v.tax)}</select></label>
          <small class="muted">Im Zweifel mit Kassenwart oder Steuerberater klären.</small></div>
        <div class="field" data-for="geld"><label>Zahlung<select class="input" name="pay">${opt([['einmal', 'in einer Summe'], ['zwei', 'in zwei Raten'], ['jahr', 'jährlich im Voraus']], v.pay)}</select></label></div>
        <div class="field"><label class="check"><input type="checkbox" name="renew" ${v.renew ? 'checked' : ''}> Verlängert sich automatisch um ein Jahr</label>
          <label>Kündigungsfrist (Monate vor Ende)<input class="input" type="number" name="notice" min="1" max="12" value="${esc(v.notice)}"></label></div>
        <div class="field full"><label>Sondervereinbarungen (optional)<textarea class="input" name="special" rows="3" maxlength="4000">${esc(v.special || '')}</textarea></label></div>
        <div class="field"><label>Ort der Unterschrift<input class="input" name="place" maxlength="80" value="${esc(v.place)}"></label></div>
        <div class="field"><label>Gerichtsstand<input class="input" name="court" maxlength="80" value="${esc(v.court)}"></label></div>
      </form>
      <div class="modal-foot"><div></div><div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="ct_save">${edit ? 'Speichern und herunterladen' : 'Erstellen und herunterladen'}</button></div></div>`);
    const showKind = () => { const k = $('#ct_kind').value;   // Geld: Betrag, Steuer, Zahlung; Sach: Sachleistungen; beides: alles
      $$('#ct_form [data-for]').forEach(el => el.style.display = k === 'beides' || el.dataset.for === k ? '' : 'none'); };
    $('#ct_kind').onchange = showKind; showKind();
    const checked = () => $$('#ct_form [name=pkg]:checked').map(c => Number(c.value));
    $$('#ct_form [name=pkg]').forEach(c => c.onchange = () => {   // Pakete: Leistungen zusammenführen (ohne doppelte Zeilen), Preise addieren
      const sel = checked().map(id => byId(packages, id)).filter(Boolean);
      $('#ct_form [name=services]').value = [...new Set(sel.flatMap(p => String(p.services || '').split('\n').map(x => x.trim()).filter(Boolean)))].join('\n');
      const sum = sel.reduce((a, p) => a + num(p.price), 0);
      if (sum) $('#ct_form [name=amount]').value = sum.toLocaleString('de-DE', { minimumFractionDigits: 2 });
    });
    $('#ct_sp').onchange = () => {   // anderer Sponsor: dessen Name, Paket, Betrag und Laufzeit neu vorbelegen, den Rest behalten
      const f = Object.fromEntries(new FormData($('#ct_form')));
      ['partner_name', 'partner_address', 'partner_rep', 'services', 'amount', 'start', 'end', 'pkg', 'inkind'].forEach(k => delete f[k]);
      form({ ...f, sponsor_id: $('#ct_sp').value }, edit);
    };
    $('#ct_save').onclick = async () => {
      const f = Object.fromEntries(new FormData($('#ct_form')));
      f.renew = !!$('#ct_form [name=renew]').checked;
      delete f.pkg; f.package_ids = checked();
      if (f.kind === 'sach') { f.amount = '0'; f.tax = ''; }
      if (f.kind === 'geld') f.inkind = '';
      if (Object.values(f).some(x => typeof x === 'string' && hasDashes(x)) && !confirmBox('In den Angaben stehen Gedankenstriche. Trotzdem erstellen?')) return;
      try {
        const r = edit ? await api('sponsor-contracts/' + edit.id, 'PUT', f) : await api('sponsor-contracts', 'POST', f);
        closeModal(); toast(`Vertrag ${r.number} gespeichert`); download(r.file, `Sponsoringvertrag ${r.number}.pdf`);
        App.cache.sponsors = null; sponsorContracts(view);
      } catch (e) { alert(e.message); }
    };
  };
  $('#ct_new').onclick = () => form();
  $$('[data-inv]').forEach(b => b.onclick = () => {   // Rechnung zum Vertrag: Betrag (bei Raten die Rate), Text und Datum vorbelegt
    const c = byId(list, b.dataset.inv), d = c.data, n = (res.invoices || []).filter(i => i.contract_id == c.id).length;
    const rate = d.pay === 'zwei' ? Number(d.amount) / 2 : Number(d.amount);
    const text = [`Sponsoring ${d.packages?.length ? '(' + d.packages.join(', ') + ') ' : ''}laut Sponsoringvertrag ${c.number}${d.pay === 'zwei' ? `, ${n + 1}. Rate` : d.pay === 'jahr' ? ', Vertragsjahr ' + (n + 1) : ''}`,
      ...(d.services || [])].join('\n');
    openModal(`<h2>Rechnung zu ${esc(c.number)}</h2>
      <p class="muted small">${esc(d.partner_name)}, ${({ zzgl: 'Betrag netto, zuzüglich 19 % Umsatzsteuer', inkl: 'Betrag brutto, inklusive 19 % Umsatzsteuer', ku: 'Kleinunternehmer, ohne Umsatzsteuer' })[d.tax] || ''}.
        Zahlungsziel und Bank aus Dauerkarte &gt; Einstellungen.${n ? ` Zu diesem Vertrag gibt es schon ${n} Rechnung${n > 1 ? 'en' : ''}.` : ''}</p>
      <form class="form" id="iv_form" onsubmit="return false">
        <div class="field"><label>Betrag (Euro, wie im Vertrag ${d.tax === 'inkl' ? 'brutto' : 'netto'})<input class="input" name="amount" inputmode="decimal" value="${rate.toLocaleString('de-DE', { minimumFractionDigits: 2 })}"></label></div>
        <div class="field"><label>Rechnungsdatum<input class="input" type="date" name="date" value="${new Date().toISOString().slice(0, 10)}"></label></div>
        <div class="field full"><label>Beschreibung (erste Zeile fett, weitere Zeilen klein darunter)<textarea class="input" name="text" rows="5">${esc(text)}</textarea></label></div>
      </form>
      <div class="modal-foot"><div></div><div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="iv_save">Rechnung erstellen</button></div></div>`);
    $('#iv_save').onclick = async () => {
      const f = Object.fromEntries(new FormData($('#iv_form')));
      if (hasDashes(f.text) && !confirmBox('In der Beschreibung stehen Gedankenstriche. Trotzdem erstellen?')) return;
      if (!confirmBox('Rechnung jetzt erstellen? Sie bekommt eine feste Nummer und lässt sich danach nicht mehr löschen.')) return;
      try { const r = await api(`sponsor-contracts/${c.id}/invoice`, 'POST', f); closeModal(); toast(`Rechnung ${r.number} erstellt`); download(r.file, `Rechnung ${r.number}.pdf`); App.cache.sponsors = null; sponsorContracts(view); }
      catch (e) { alert(e.message); }
    };
  });
  $$('[data-edit]').forEach(b => b.onclick = () => { const c = byId(list, b.dataset.edit); form({ ...c.data, sponsor_id: c.sponsor_id }, c); });
  $$('[data-copy]').forEach(b => b.onclick = () => { const c = byId(list, b.dataset.copy); form({ ...c.data, sponsor_id: c.sponsor_id }); });
  $$('[data-del]').forEach(b => b.onclick = async () => {
    const c = byId(list, b.dataset.del);
    if (!confirmBox(`Vertrag ${c.number} und das PDF endgültig löschen? Das lässt sich nicht rückgängig machen.`)) return;
    await api('sponsor-contracts/' + c.id, 'DELETE'); toast('Vertrag gelöscht'); App.cache.sponsors = null; sponsorContracts(view);
  });
  if (forSponsor && /^\d+$/.test(forSponsor)) form({ sponsor_id: forSponsor });
}
