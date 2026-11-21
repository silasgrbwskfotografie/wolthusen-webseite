/* ====================================================================== */
/* Teamkleidung: Artikel mit eigenen Bestellfeldern, Bestellung über einen Link ohne Anmeldung */
const AP_TYPES = [['text', 'Text'], ['number', 'Zahl'], ['select', 'Auswahl'], ['check', 'Ja/Nein']];
const AP_PRESETS = [
  { label: 'Name', type: 'text', required: true },
  { label: 'Rückennummer', type: 'number' },
  { label: 'Größe', type: 'select', options: ['XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL'], required: true },
  { label: 'Flock (Name auf dem Rücken)', type: 'text' },
  { label: 'Telefon', type: 'text', internal: true },
];
const apKey = () => 'f' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const apFields = a => { try { const f = JSON.parse(a.fields || '[]'); return Array.isArray(f) ? f : []; } catch { return []; } };
const apData = o => { try { return JSON.parse(o.data || '{}') || {}; } catch { return {}; } };
const apLink = a => `${location.origin}/bestellen/${a.public_token}`;
const apOpen = a => !!Number(a.active) && (!a.deadline || todayStr() <= a.deadline);
const apOrders = id => App.cache.apparel_orders.filter(o => o.apparel_id == id).sort((x, y) => x.id - y.id);
const apQty = o => Number(o.quantity) || 1;
const apValue = (f, v) => f.type === 'check' ? (Number(v) ? 'ja' : '') : String(v ?? '');

F.apparel = [
  { key: 'name', label: 'Bezeichnung', placeholder: 'z. B. Hoodie 2027', full: true },
  { key: 'price', label: 'Preis pro Stück (€)', type: 'number' },
  { key: 'deadline', label: 'Bestellschluss', type: 'date', hint: 'An diesem Tag kann noch bestellt werden.' },
  { key: 'active', label: 'Bestellungen über den Link annehmen', type: 'check', default: 1 },
  { key: 'show_list', label: 'Bisherige Bestellungen auf der Bestellseite zeigen', type: 'check', default: 1, hint: 'Interne Felder und „bezahlt“ erscheinen dort nie.' },
  { key: 'image', label: 'Bild', type: 'image', full: true },
  { key: 'description', label: 'Beschreibung für die Bestellseite', type: 'textarea', rows: 4, placeholder: 'z. B. Material, Farbe, Lieferzeit, wie bezahlt wird' },
  { key: 'notes', label: 'Interne Notizen', type: 'textarea', rows: 2 },
];

App.pages.apparel = async (view, args) => {
  await Promise.all([load('apparel', true), load('apparel_orders', true)]);
  if (args[0]) return apparelDetail(view, Number(args[0]));
  const list = [...App.cache.apparel].sort((x, y) => Number(apOpen(y)) - Number(apOpen(x)) || y.id - x.id);
  view.innerHTML = `
    <div class="page-head"><h1>Teamkleidung<small>${list.length} Artikel</small></h1>
      <div class="btn-row"><button class="aw btn primary" id="ap_new">+ Neue Klamotte</button></div></div>
    <div class="grid g3">${list.map(a => {
      const os = apOrders(a.id), pcs = os.reduce((s, o) => s + apQty(o), 0);
      return `<a class="card mag-card ap-card" href="#/apparel/${a.id}">${a.image ? `<img src="${esc(a.image)}" alt="">` : ''}
        <div style="display:flex;justify-content:space-between;gap:8px"><h3 style="margin:0">${esc(a.name || 'Ohne Namen')}</h3>${apOpen(a) ? '<span class="badge ok">offen</span>' : '<span class="badge">geschlossen</span>'}</div>
        <div class="small muted" style="margin-top:4px">${os.length} Bestellungen, ${pcs} Stück${Number(a.price) ? ' | ' + eur(a.price) : ''}${a.deadline ? ' | Bestellschluss ' + fmtDate(a.deadline) : ''}</div></a>`;
    }).join('') || '<div class="card empty" style="grid-column:1/-1">Noch keine Teamkleidung angelegt.</div>'}</div>`;
  $('#ap_new').onclick = async () => {
    const r = await editRecord('apparel', F.apparel, { active: 1, show_list: 1 }, { newTitle: 'Neue Klamotte',
      fixed: { fields: JSON.stringify(AP_PRESETS.slice(0, 3).map(f => ({ ...f, key: apKey() }))) } });
    if (r?.id) go(`#/apparel/${r.id}`);
  };
};

async function apparelDetail(view, id) {
  const a = byId(App.cache.apparel, id);
  if (!a) { view.innerHTML = '<div class="card empty">Diesen Artikel gibt es nicht mehr. <a href="#/apparel">Zur Übersicht</a></div>'; return; }
  const aw = can(APPAREL_AREAS, 2), fields = apFields(a), orders = apOrders(id), price = Number(a.price) || 0;
  const pcs = orders.reduce((s, o) => s + apQty(o), 0), openPcs = orders.filter(o => !Number(o.paid)).reduce((s, o) => s + apQty(o), 0);
  const toBook = orders.filter(o => Number(o.paid) && !o.booked_tx), toBookPcs = toBook.reduce((s, o) => s + apQty(o), 0);
  const rerender = async () => { const st = $('#main').scrollTop; await Promise.all([load('apparel', true), load('apparel_orders', true)]); await apparelDetail(view, id); $('#main').scrollTop = st; };

  // Stückzahl pro Auswahl (z. B. Größe), nach Menge gewichtet
  const summary = fields.filter(f => f.type === 'select').map(f => {
    const cnt = {};
    orders.forEach(o => { const v = apData(o)[f.key] || 'ohne Angabe'; cnt[v] = (cnt[v] || 0) + apQty(o); });
    const keys = [...(f.options || []).filter(o => cnt[o]), ...Object.keys(cnt).filter(k => !(f.options || []).includes(k))];
    return { label: f.label, items: keys.map(k => [k, cnt[k]]) };
  });
  const pub = fields.filter(f => !f.internal);
  const supplierText = [a.name, `${pcs} Stück gesamt`, ...summary.map(s => `\n${s.label}:\n` + s.items.map(([k, n]) => `${k}: ${n}`).join('\n')),
    '\nEinzelaufstellung:', ...orders.map(o => { const d = apData(o);
      return pub.filter(f => f.type === 'check' ? Number(d[f.key]) : String(d[f.key] ?? '').trim()).map(f => f.type === 'check' ? f.label : d[f.key]).join(', ') + (apQty(o) > 1 ? ` (${apQty(o)} Stück)` : ''); })].join('\n');

  view.innerHTML = `
    <div class="page-head"><h1>${esc(a.name || 'Ohne Namen')}<small><a href="#/apparel">Teamkleidung</a> | ${apOpen(a) ? 'Bestellungen offen' : 'geschlossen'}${a.deadline ? ' | Bestellschluss ' + fmtDate(a.deadline) : ''}</small></h1>
      <div class="btn-row"><button class="btn keep" id="ap_copylink">Link kopieren</button>
        <a class="btn keep" href="${esc(apLink(a))}" target="_blank" rel="noopener">Bestellseite öffnen</a>
        <button class="aw btn" id="ap_fields">Bestellfelder</button><button class="aw btn" id="ap_edit">Bearbeiten</button></div></div>
    <div class="grid g4" style="margin-bottom:16px">
      <div class="card stat"><span>Bestellungen</span><b>${orders.length}</b></div>
      <div class="card stat"><span>Stück</span><b>${pcs}</b></div>
      ${price ? `<div class="card stat"><span>Summe</span><b>${eur(price * pcs)}</b></div>
      <div class="card stat"><span>Noch nicht bezahlt</span><b style="color:${openPcs ? 'var(--red)' : 'var(--ok)'}">${eur(price * openPcs)}</b></div>` : ''}</div>
    ${price && can('finanzen', 2) ? `<div class="card" style="margin-bottom:16px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
      <div><b>Finanzen</b><div class="muted small">${toBook.length ? `${toBook.length} bezahlte Bestellung${toBook.length > 1 ? 'en' : ''} (${toBookPcs} Stück, ${eur(price * toBookPcs)}) noch nicht gebucht.` : 'Alle bezahlten Bestellungen sind gebucht.'}</div></div>
      ${toBook.length ? '<button class="btn primary" id="ap_book">In die Finanzen übernehmen</button>' : '<a class="btn" href="#/finance">Zu den Buchungen</a>'}</div>` : ''}
    <div class="grid g2" style="margin-bottom:16px">
      <div class="card"><h2>Bestell-Link</h2><code class="ap-link">${esc(apLink(a))}</code>
        <div class="muted small" style="margin:8px 0">Jeder mit diesem Link kann ohne Anmeldung bestellen${Number(a.show_list) ? ' und die bisherigen Bestellungen sehen (ohne interne Felder und ohne „bezahlt“)' : ''}.
          ${apOpen(a) ? '' : '<b>Zurzeit nimmt der Link keine Bestellungen an.</b>'}</div>
        <button class="aw btn sm" id="ap_newlink">Neuen Link erzeugen</button></div>
      <div class="card"><div class="mag-sec-head"><h2>Für den Lieferanten</h2><div class="btn-row"><button class="btn sm keep" id="ap_copysum">Text kopieren</button><button class="btn sm keep" id="ap_csv">CSV</button></div></div>
        ${summary.length ? summary.map(s => `<div class="sum-row"><span>${esc(s.label)}</span><span>${s.items.map(([k, n]) => `<b>${esc(k)}</b> ${n}`).join(' &nbsp; ') || '<span class="muted">noch nichts</span>'}</span></div>`).join('')
          : '<div class="muted">Mit einem Auswahlfeld (z. B. Größe) steht hier die Stückzahl pro Größe.</div>'}</div></div>
    <div class="mag-sec-head"><h2>Bestellungen</h2><button class="aw btn primary" id="ap_add">+ Bestellung</button></div>
    <div class="table-wrap"><table><thead><tr>${fields.map(f => `<th>${esc(f.label)}${f.internal ? ' <span class="muted small">(intern)</span>' : ''}</th>`).join('')}<th>Menge</th>${price ? '<th>Summe</th>' : ''}<th>Bezahlt</th><th>Eingang</th><th></th></tr></thead><tbody>
      ${orders.map(o => { const d = apData(o); return `<tr>${fields.map(f => `<td>${esc(apValue(f, d[f.key]))}</td>`).join('')}
        <td>${apQty(o)}</td>${price ? `<td>${eur(price * apQty(o))}</td>` : ''}
        <td><input type="checkbox" data-paid="${o.id}" ${Number(o.paid) ? 'checked' : ''} ${aw && !o.booked_tx ? '' : 'disabled'}>${o.booked_tx ? ' <span class="badge ok" title="In den Finanzen gebucht">gebucht</span>' : ''}</td>
        <td class="small muted">${fmtDate((o.created || o.created_at || '').slice(0, 10))}${o.source ? ' | ' + esc(o.source) : ''}</td>
        <td class="actions"><button class="btn sm ghost keep" data-o="${o.id}">${aw ? 'Bearbeiten' : 'Ansehen'}</button></td></tr>`; }).join('')
        || `<tr><td colspan="${fields.length + (price ? 6 : 5)}" class="empty">Noch keine Bestellungen.</td></tr>`}
    </tbody></table></div>`;

  $('#ap_copylink').onclick = () => copyText(apLink(a));
  if ($('#ap_book')) $('#ap_book').onclick = async () => {
    if (!confirmBox(`Eine Einnahme über ${eur(price * toBookPcs)} für ${toBook.length} bezahlte Bestellung${toBook.length > 1 ? 'en' : ''} anlegen?`)) return;
    try { const r = await api(`apparel/${id}/book`, 'POST', {}); invalidate('transactions'); toast(`Gebucht: ${eur(r.amount)}`); rerender(); }
    catch (e) { alert(e.message); }
  };
  $('#ap_copysum').onclick = () => copyText(noDashes(supplierText));
  $('#ap_csv').onclick = () => downloadCsv(`${slug(a.name || 'teamkleidung')}-bestellungen.csv`,
    [...fields.map(f => f.label), 'Menge', 'Einzelpreis', 'Summe', 'Bezahlt', 'Eingang', 'Quelle', 'Notizen'],
    orders.map(o => { const d = apData(o); return [...fields.map(f => apValue(f, d[f.key])), apQty(o), price ? String(price).replace('.', ',') : '',
      price ? String(price * apQty(o)).replace('.', ',') : '', Number(o.paid) ? 'ja' : 'nein', fmtDate((o.created || '').slice(0, 10)), o.source || '', o.notes || '']; }));
  $('#ap_newlink').onclick = async () => {
    if (!confirmBox('Neuen Bestell-Link erzeugen? Der bisherige Link funktioniert danach nicht mehr.')) return;
    await api(`apparel/${id}/new-link`, 'POST', {}); toast('Neuer Link erzeugt'); rerender();
  };
  $('#ap_edit').onclick = async () => {
    const r = await editRecord('apparel', F.apparel, a, { editTitle: 'Klamotte bearbeiten' });
    if (r?.deleted) go('#/apparel'); else if (r) rerender();
  };
  $('#ap_fields').onclick = async () => { if (await editApparelFields(a)) rerender(); };
  $('#ap_add').onclick = async () => { if (await editApparelOrder(a, { quantity: 1 })) rerender(); };
  $$('[data-o]', view).forEach(b => b.onclick = async () => { if (await editApparelOrder(a, byId(orders, b.dataset.o))) rerender(); });
  $$('[data-paid]', view).forEach(cb => cb.onchange = async () => {
    await api(`apparel_orders/${cb.dataset.paid}`, 'PUT', { paid: cb.checked ? 1 : 0 }); toast(cb.checked ? 'Als bezahlt markiert' : 'Als offen markiert'); rerender();
  });
}

function editApparelOrder(a, rec) {
  const fields = apFields(a), d = apData(rec);
  const form = [
    ...fields.map(f => ({ key: 'd_' + f.key, label: f.label + (f.internal ? ' (intern)' : ''), type: f.type === 'text' ? 'text' : f.type,
      options: f.type === 'select' ? ['', ...(f.options || [])] : undefined })),
    { key: 'quantity', label: 'Menge', type: 'number', default: 1 },
    { key: 'paid', label: 'Bezahlt', type: 'check' },
    { key: 'notes', label: 'Interne Notizen', type: 'textarea', rows: 2 },
  ];
  const r = { ...rec };
  fields.forEach(f => { r['d_' + f.key] = d[f.key] ?? ''; });
  return editRecord('apparel_orders', form, r, {
    newTitle: 'Neue Bestellung', editTitle: 'Bestellung', fixed: { apparel_id: a.id },
    beforeSave: vals => {
      const out = {};
      fields.forEach(f => { out[f.key] = vals['d_' + f.key]; delete vals['d_' + f.key]; });
      vals.data = JSON.stringify(out);
      vals.quantity = Math.max(1, Number(vals.quantity) || 1);
      if (!rec.id) { vals.source = 'Hub'; vals.created = `${todayStr()}T${new Date().toTimeString().slice(0, 8)}`; }
    },
  });
}

/* Bestellfelder bearbeiten: Bezeichnung, Typ, Auswahlwerte, Pflicht, intern. Keys bleiben stabil, damit alte Bestellungen passen. */
function editApparelFields(a) {
  const list = apFields(a).map(f => ({ ...f, options: [...(f.options || [])] }));
  return new Promise(resolve => {
    const draw = () => {
      openModal(`<h2>Bestellfelder: ${esc(a.name || '')}</h2>
        <p class="muted small">Diese Felder füllen die Besteller über den Link aus. Interne Felder (z. B. Telefon) erscheinen nicht in der öffentlichen Liste.</p>
        <div>${list.map((f, i) => `<div class="ap-frow" data-i="${i}">
          <input class="input" data-k="label" value="${esc(f.label || '')}" placeholder="Bezeichnung, z. B. Größe">
          <select class="input" data-k="type">${AP_TYPES.map(([v, l]) => `<option value="${v}" ${f.type === v ? 'selected' : ''}>${l}</option>`).join('')}</select>
          <input class="input" data-k="options" value="${esc(f.options.join(', '))}" placeholder="Auswahl, mit Komma getrennt" style="${f.type === 'select' ? '' : 'visibility:hidden'}">
          <label class="check"><input type="checkbox" data-k="required" ${f.required ? 'checked' : ''}> Pflicht</label>
          <label class="check"><input type="checkbox" data-k="internal" ${f.internal ? 'checked' : ''}> intern</label>
          <span class="btn-row"><button type="button" class="btn sm ghost" data-up="${i}" ${i ? '' : 'disabled'} title="nach oben">↑</button><button type="button" class="btn sm ghost" data-rm="${i}">Entfernen</button></span></div>`).join('')
          || '<div class="muted">Noch keine Felder.</div>'}</div>
        <div class="btn-row" style="margin-top:10px"><button type="button" class="btn sm" id="apf_add">+ Feld</button>
          ${AP_PRESETS.map((p, i) => list.some(f => f.label === p.label) ? '' : `<button type="button" class="btn sm ghost" data-preset="${i}">+ ${esc(p.label)}</button>`).join('')}</div>
        ${apOrders(a.id).length ? '<p class="warnline">Es gibt schon Bestellungen. Entfernte Felder bleiben dort gespeichert, werden aber nicht mehr angezeigt.</p>' : ''}
        <div class="modal-foot"><div></div><div class="btn-row"><button class="btn" id="apf_cancel">Abbrechen</button><button class="btn primary" id="apf_save">Speichern</button></div></div>`);
      const box = $('#modalBox');
      $$('.ap-frow', box).forEach(row => {
        const f = list[Number(row.dataset.i)];
        $$('[data-k]', row).forEach(el => { el.oninput = el.onchange = () => {
          const k = el.dataset.k;
          if (k === 'options') f.options = el.value.split(',').map(s => s.trim()).filter(Boolean);
          else if (el.type === 'checkbox') f[k] = el.checked;
          else f[k] = el.value;
          if (k === 'type' && el === document.activeElement) draw();
        }; });
      });
      $$('[data-up]', box).forEach(b => b.onclick = () => { const i = Number(b.dataset.up); [list[i - 1], list[i]] = [list[i], list[i - 1]]; draw(); });
      $$('[data-rm]', box).forEach(b => b.onclick = () => { list.splice(Number(b.dataset.rm), 1); draw(); });
      $$('[data-preset]', box).forEach(b => b.onclick = () => { const p = AP_PRESETS[Number(b.dataset.preset)]; list.push({ ...p, options: [...(p.options || [])], key: apKey() }); draw(); });
      $('#apf_add', box).onclick = () => { list.push({ key: apKey(), label: '', type: 'text', options: [] }); draw(); };
      $('#apf_cancel', box).onclick = () => { closeModal(); resolve(false); };
      $('#apf_save', box).onclick = async () => {
        if (list.some(f => !String(f.label || '').trim())) return alert('Bitte jedem Feld eine Bezeichnung geben.');
        if (list.some(f => f.type === 'select' && !f.options.length)) return alert('Bitte bei Auswahlfeldern die Auswahl eintragen, z. B. S, M, L.');
        const clean = list.map(f => ({ key: f.key, label: f.label.trim(), type: f.type, options: f.type === 'select' ? f.options : [], required: !!f.required, internal: !!f.internal }));
        try { await api(`apparel/${a.id}`, 'PUT', { fields: JSON.stringify(clean) }); } catch (e) { return alert('Speichern fehlgeschlagen: ' + e.message); }
        closeModal(); toast('Bestellfelder gespeichert'); resolve(true);
      };
    };
    draw();
  });
}

