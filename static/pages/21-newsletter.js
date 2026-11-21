/* ====================================================================== */
/* Newsletter (Bereich Medien): Ausgaben schreiben und verschicken, Abonnenten, Gruppen.
   Anmeldung auf der Webseite mit Double-Opt-In (/newsletter), jede Ausgabe mit persönlichem Abmeldelink. Daten über /api/newsletter, Gruppen über die Tabelle nl_groups. */
const NL_TABS = [['', 'Ausgaben'], ['abonnenten', 'Abonnenten'], ['gruppen', 'Gruppen']];
const NL_STATUS = { aktiv: ['ok', 'aktiv'], offen: ['warn', 'unbestätigt'], abgemeldet: ['', 'abgemeldet'] };
const NL_GROUP_FIELDS = [
  { key: 'name', label: 'Name', full: true },
  { key: 'description', label: 'Beschreibung (steht bei der Anmeldung unter dem Namen)', type: 'textarea', full: true },
  { key: 'public', label: 'Auf der Webseite zur Auswahl anbieten', type: 'check' },
  { key: 'active', label: 'Aktiv', type: 'check' },
  { key: 'sort', label: 'Reihenfolge', type: 'number' },
];

App.pages.newsletter = async (view, args = []) => {
  const tab = NL_TABS.some(t => t[0] === (args[0] || '')) ? (args[0] || '') : '';
  const d = await api('newsletter');
  const gName = id => (d.groups.find(g => g.id == id) || {}).name || '?';
  const gNames = ids => ids.length ? ids.map(gName).join(', ') : 'alle Abonnenten';
  const active = d.subscribers.filter(s => s.status === 'aktiv');
  const reach = ids => active.filter(s => !ids.length || s.groups.some(g => ids.includes(g))).length;
  const w = can('medien', 2);
  const head = `<div class="page-head"><h1>Newsletter<small>${active.length} aktive Abonnenten</small></h1>
      <div class="btn-row"><a class="btn keep" href="/newsletter" target="_blank" rel="noopener">Anmeldeseite</a></div></div>
    <div class="toolbar">${NL_TABS.map(([k, l]) => `<a class="btn sm ${k === tab ? 'dark' : ''}" href="#/newsletter${k ? '/' + k : ''}">${l}</a>`).join('')}</div>
    ${d.link_ok ? '' : '<div class="card" style="margin-bottom:12px"><span class="badge warn">Hinweis</span> DOMAIN fehlt in der .env, die Links in den Mails nutzen dann die gerade aufgerufene Adresse.</div>'}`;
  const groupChecks = (sel = [], name = 'nlg') => d.groups.length ? `<div class="check-list">${d.groups.map(g => `<label class="check"><input type="checkbox" name="${name}" value="${g.id}" ${sel.includes(g.id) ? 'checked' : ''}> ${esc(g.name)}${Number(g.active) ? '' : ' <span class="muted small">(inaktiv)</span>'}</label>`).join('')}</div>`
    : '<p class="muted small">Noch keine Gruppen. Dann geht alles an alle Abonnenten.</p>';
  const picked = name => $$(`[name=${name}]:checked`).map(c => Number(c.value));

  if (tab === 'gruppen') {
    view.innerHTML = `${head}
      <div class="btn-row" style="margin-bottom:12px">${w ? '<button class="btn primary" id="ng_new">+ Neue Gruppe</button>' : ''}</div>
      <p class="muted small">Gruppen sind die Themen, die Abonnenten bei der Anmeldung wählen (zum Beispiel Herren, Jugend, Sponsoren, Fanshop). Nicht angebotene Gruppen kannst du im Hub selbst befüllen.</p>
      <div class="table-wrap"><table><thead><tr><th>Gruppe</th><th>Abonnenten</th><th>Webseite</th><th></th></tr></thead><tbody>
      ${d.groups.map(g => `<tr><td><b>${esc(g.name)}</b>${g.description ? `<div class="muted small">${esc(g.description)}</div>` : ''}</td>
        <td>${active.filter(s => s.groups.includes(g.id)).length}</td>
        <td>${Number(g.public) ? '<span class="badge ok">zur Auswahl</span>' : '<span class="badge">nur intern</span>'}${Number(g.active) ? '' : ' <span class="badge">inaktiv</span>'}</td>
        <td class="actions">${w ? `<button class="btn sm ghost" data-g="${g.id}">Bearbeiten</button>` : ''}</td></tr>`).join('') || '<tr><td colspan="4" class="empty">Noch keine Gruppen.</td></tr>'}
      </tbody></table></div>`;
    const edit = async rec => { const r = await editRecord('nl_groups', NL_GROUP_FIELDS, rec, { newTitle: 'Neue Gruppe', editTitle: 'Gruppe bearbeiten' }); if (r) route(); };
    if ($('#ng_new')) $('#ng_new').onclick = () => edit({ public: 1, active: 1 });
    $$('[data-g]').forEach(b => b.onclick = () => edit(d.groups.find(g => g.id == b.dataset.g)));
    return;
  }

  if (tab === 'abonnenten') {
    const st = App._nlFilter || (App._nlFilter = { g: '', s: 'aktiv', q: '' });
    const list = d.subscribers.filter(s => (!st.s || s.status === st.s) && (!st.g || s.groups.includes(Number(st.g)))
      && (!st.q || (s.email + ' ' + s.name).toLowerCase().includes(st.q.toLowerCase())));
    const cnt = k => d.subscribers.filter(s => s.status === k).length;
    view.innerHTML = `${head}
      <div class="toolbar">
        <select class="input" id="ns_s" style="max-width:190px"><option value="">Alle (${d.subscribers.length})</option>${Object.entries(NL_STATUS).map(([k, [, l]]) => `<option value="${k}" ${st.s === k ? 'selected' : ''}>${l} (${cnt(k)})</option>`).join('')}</select>
        <select class="input" id="ns_g" style="max-width:190px"><option value="">Alle Gruppen</option>${d.groups.map(g => `<option value="${g.id}" ${st.g == g.id ? 'selected' : ''}>${esc(g.name)}</option>`).join('')}</select>
        <input class="input" id="ns_q" type="search" placeholder="Suchen" value="${esc(st.q)}" style="max-width:220px">
        ${w ? '<button class="btn primary" id="ns_new">+ Abonnent eintragen</button>' : ''}</div>
      <div class="table-wrap"><table><thead><tr><th>E-Mail</th><th>Name</th><th>Status</th><th>Gruppen</th><th>Einwilligung</th><th></th></tr></thead><tbody>
      ${list.map(s => `<tr><td><b>${esc(s.email)}</b></td><td>${esc(s.name)}</td><td><span class="badge ${NL_STATUS[s.status]?.[0] || ''}">${NL_STATUS[s.status]?.[1] || esc(s.status)}</span></td>
        <td class="small">${s.groups.map(gName).map(esc).join(', ')}</td>
        <td class="small">${s.consent_at ? fmtStamp(s.consent_at) : '<span class="muted">noch nicht</span>'}<div class="muted">${esc(s.source)}</div></td>
        <td class="actions">${w ? `<button class="btn sm ghost" data-se="${s.id}">Gruppen</button>${s.status !== 'abgemeldet' ? `<button class="btn sm ghost" data-su="${s.id}">Abmelden</button>` : ''}<button class="btn sm ghost danger" data-sd="${s.id}">Löschen</button>` : ''}</td></tr>`).join('')
        || '<tr><td colspan="6" class="empty">Keine Abonnenten in dieser Auswahl.</td></tr>'}
      </tbody></table></div>
      <p class="muted small">Unbestätigte Anmeldungen löscht der Hub nach 30 Tagen, Abmeldungen nach drei Jahren (Nachweis der Einwilligung). „Löschen“ entfernt die Adresse sofort ganz.</p>`;
    $('#ns_s').onchange = e => { st.s = e.target.value; route(); };
    $('#ns_g').onchange = e => { st.g = e.target.value; route(); };
    $('#ns_q').onkeydown = e => { if (e.key === 'Enter') { st.q = e.target.value.trim(); route(); } };
    if ($('#ns_new')) $('#ns_new').onclick = () => {
      openModal(`<h2>Abonnent eintragen</h2>
        <p class="muted small">Nur Personen eintragen, die nachweisbar eingewilligt haben, zum Beispiel per Unterschrift oder E-Mail. Sonst bitte über die Anmeldeseite.</p>
        <div class="form"><div class="field"><label>E-Mail<input class="input" id="na_e" type="email" maxlength="150"></label></div>
          <div class="field"><label>Name (optional)<input class="input" id="na_n" maxlength="80"></label></div>
          <div class="field full"><label>Gruppen</label>${groupChecks([], 'nag')}</div>
          <div class="field full"><label>Woher kommt die Einwilligung? (optional)<input class="input" id="na_note" maxlength="300" placeholder="z. B. Formular am Heimspieltag 12.04."></label></div>
          <div class="field full"><label class="check"><input type="checkbox" id="na_c"> Die Person hat eingewilligt, den Newsletter zu bekommen.</label></div></div>
        <div class="modal-foot"><div></div><div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="na_go">Eintragen</button></div></div>`);
      $('#na_go').onclick = async () => {
        try { await api('newsletter/subscribers', 'POST', { email: $('#na_e').value.trim(), name: $('#na_n').value.trim(), groups: picked('nag'), note: $('#na_note').value, consent: $('#na_c').checked });
          closeModal(); toast('Eingetragen'); route(); } catch (e) { alert(e.message); }
      };
    };
    $$('[data-se]').forEach(b => b.onclick = () => {
      const s = d.subscribers.find(x => x.id == b.dataset.se);
      openModal(`<h2>${esc(s.email)}</h2><div class="form"><div class="field full"><label>Name<input class="input" id="ne_n" maxlength="80" value="${esc(s.name)}"></label></div>
        <div class="field full"><label>Gruppen</label>${groupChecks(s.groups, 'neg')}</div></div>
        <div class="modal-foot"><div></div><div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="ne_go">Speichern</button></div></div>`);
      $('#ne_go').onclick = async () => { try { await api('newsletter/subscribers/' + s.id, 'PUT', { name: $('#ne_n').value, groups: picked('neg') }); closeModal(); toast('Gespeichert'); route(); } catch (e) { alert(e.message); } };
    });
    $$('[data-su]').forEach(b => b.onclick = async () => { if (!confirmBox('Diese Person vom Newsletter abmelden?')) return; await api(`newsletter/subscribers/${b.dataset.su}/unsubscribe`, 'POST'); toast('Abgemeldet'); route(); });
    $$('[data-sd]').forEach(b => b.onclick = async () => { if (!confirmBox('Adresse endgültig löschen (auch den Nachweis der Einwilligung)? Das lässt sich nicht rückgängig machen.')) return; await api('newsletter/subscribers/' + b.dataset.sd, 'DELETE'); toast('Gelöscht'); route(); });
    return;
  }

  // Ausgaben
  const ST = { entwurf: ['', 'Entwurf'], 'läuft': ['warn', 'wird verschickt'], gesendet: ['ok', 'verschickt'] };
  view.innerHTML = `${head}
    <div class="btn-row" style="margin-bottom:12px">${w ? '<button class="btn primary" id="ni_new">+ Neuer Newsletter</button>' : ''}</div>
    <div class="table-wrap"><table><thead><tr><th>Betreff</th><th>An</th><th>Status</th><th>Datum</th><th></th></tr></thead><tbody>
    ${d.issues.map(i => `<tr><td><b>${esc(i.subject)}</b></td><td class="small">${esc(gNames(i.groups))}</td>
      <td><span class="badge ${ST[i.status]?.[0] || ''}">${ST[i.status]?.[1] || esc(i.status)}</span>${i.status === 'gesendet' ? `<div class="muted small">${i.sent_count} erreicht${i.failed ? `, ${i.failed} fehlgeschlagen` : ''}</div>` : ''}</td>
      <td class="small">${fmtStamp(i.sent_at || i.created)}</td>
      <td class="actions"><button class="btn sm ghost" data-ie="${i.id}">${i.status === 'entwurf' && w ? 'Bearbeiten' : 'Ansehen'}</button></td></tr>`).join('') || '<tr><td colspan="5" class="empty">Noch kein Newsletter.</td></tr>'}
    </tbody></table></div>
    <p class="muted small">Verschickt wird über das Vereinspostfach, an jeden einzeln mit eigenem Abmeldelink, mit einer Sekunde Pause zwischen den Mails. Öffnungen und Klicks werden nicht gemessen.</p>`;
  const editor = (it = { subject: '', body: '', groups: [], status: 'entwurf' }) => {
    const ro = it.status !== 'entwurf' || !w;
    openModal(`<h2>${ro ? esc(it.subject) : it.id ? 'Newsletter bearbeiten' : 'Neuer Newsletter'}</h2>
      <div class="form">
        <div class="field full"><label>Betreff<input class="input" id="ni_s" maxlength="200" value="${esc(it.subject)}" ${ro ? 'disabled' : ''}></label></div>
        <div class="field full"><label>Text<textarea class="input" id="ni_b" rows="14" ${ro ? 'disabled' : ''} placeholder="Absätze mit einer Leerzeile trennen.">${esc(it.body)}</textarea></label>
          <small class="muted">Logo oben, Anschrift und Abmeldelink unten setzt der Hub selbst.</small></div>
        <div class="field full"><label>An welche Gruppen? (keine gewählt = alle Abonnenten)</label>${ro ? `<p>${esc(gNames(it.groups))}</p>` : groupChecks(it.groups, 'nig')}
          <small class="muted" id="ni_reach"></small></div>
      </div>
      <div class="modal-foot"><div>${!ro && it.id ? '<button class="btn ghost danger" id="ni_del">Löschen</button>' : ''}</div><div class="btn-row"><button class="btn" onclick="closeModal()">Schließen</button>
        ${ro ? '' : '<button class="btn" id="ni_save">Speichern</button><button class="btn" id="ni_test">Test an mich</button><button class="btn primary" id="ni_send">Senden</button>'}</div></div>`);
    if (ro) return;
    const upd = () => { $('#ni_reach').textContent = `Geht an ${reach(picked('nig'))} aktive Abonnenten.`; };
    $$('[name=nig]').forEach(c => c.onchange = upd); upd();
    const save = async () => {
      if (hasDashes($('#ni_s').value + $('#ni_b').value) && !confirmBox('Im Text stehen Gedankenstriche. Trotzdem speichern?')) return null;
      const body = { subject: $('#ni_s').value, body: $('#ni_b').value, groups: picked('nig') };
      const r = it.id ? await api('newsletter/issues/' + it.id, 'PUT', body) : await api('newsletter/issues', 'POST', body);
      it.id = r.id; return r.id;
    };
    $('#ni_save').onclick = async () => { try { if (await save()) { toast('Gespeichert'); closeModal(); route(); } } catch (e) { alert(e.message); } };
    $('#ni_test').onclick = async () => { try { const id = await save(); if (!id) return; const r = await api(`newsletter/issues/${id}/test`, 'POST'); toast('Test an ' + r.to + ' geschickt'); } catch (e) { alert(e.message); } };
    $('#ni_send').onclick = async () => {
      const n = reach(picked('nig'));
      if (!confirmBox(`Newsletter jetzt an ${n} Abonnenten verschicken? Das lässt sich nicht zurückholen.`)) return;
      try { const id = await save(); if (!id) return; const r = await api(`newsletter/issues/${id}/send`, 'POST');
        closeModal(); alert(`${r.count} Mails werden jetzt einzeln verschickt. Du bekommst eine Nachricht, wenn alle raus sind.`); route(); } catch (e) { alert(e.message); }
    };
    if ($('#ni_del')) $('#ni_del').onclick = async () => { if (!confirmBox('Diesen Entwurf löschen?')) return; await api('newsletter/issues/' + it.id, 'DELETE'); closeModal(); toast('Gelöscht'); route(); };
  };
  if ($('#ni_new')) $('#ni_new').onclick = () => editor();
  $$('[data-ie]').forEach(b => b.onclick = () => editor({ ...d.issues.find(i => i.id == b.dataset.ie) }));
};
