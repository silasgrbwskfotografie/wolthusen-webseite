/* ======================================================================
   Heimspieltag (Bereich spieltag): Schichten mit Helfern, Checkliste und Link zum Eintragen ohne Konto (/helfer/<token>).
   Lesen 1 = ansehen und sich selbst eintragen (Push-Erinnerung am Vortag), Bearbeiten 2 = planen.
   ====================================================================== */
F.gd_shifts = [
  { key: 'role', label: 'Aufgabe', placeholder: 'z. B. Kasse' },
  { key: 'slots', label: 'Anzahl Helfer', type: 'number' },
  { key: 'start', label: 'Beginn', type: 'time' },
  { key: 'end', label: 'Ende', type: 'time' },
  { key: 'sort', label: 'Reihenfolge', type: 'number', hint: 'Kleine Zahl steht oben.' },
  { key: 'notes', label: 'Hinweis für die Helfer (erscheint auch auf dem Link)', type: 'textarea', full: true },
];
const gdWhen = g => `${fmtDate(g.date)}${g.time ? ', ' + esc(g.time) + ' Uhr' : ''}`;
const gdTitle = g => `${esc(g.team || TEAMS[0])}${g.opponent ? ' gegen ' + esc(g.opponent) : ''}`;

App.pages.spieltag = async (view, args = []) => {
  if (/^\d+$/.test(args[0] || '')) return gdGame(view, Number(args[0]));
  const list = await api('gameday');
  const edit = can('spieltag', 2);
  view.innerHTML = `<div class="page-head"><h1>Heimspieltag<small>Helfer, Aufgaben und Checkliste für jedes Heimspiel. Helfer tragen sich über einen Link auch ohne Konto ein.</small></h1>
      ${edit ? '<button class="btn" id="gd_tpl">Vorlagen</button>' : ''}</div>
    <div class="grid g3">${list.map(g => {
      const pct = g.slots ? Math.round(100 * Math.min(g.filled, g.slots) / g.slots) : 0;
      return `<a class="card gd-card" href="#/spieltag/${g.id}">
        <div class="gd-date"><b>${esc(new Date(g.date).toLocaleDateString('de-DE', { day: '2-digit' }))}</b><span>${esc(new Date(g.date).toLocaleDateString('de-DE', { month: 'short' }))}</span></div>
        <div class="gd-info"><b>${gdTitle(g)}</b><span class="muted small">${gdWhen(g)}</span>
          <div class="progress" title="${g.filled} von ${g.slots} Plätzen besetzt"><b style="width:${pct}%"></b></div>
          <span class="small">${g.slots ? `${g.filled} von ${g.slots} Helfern` : 'noch keine Aufgaben'}${g.checks ? ` · Checkliste ${g.checks_done}/${g.checks}` : ''}${g.mine ? ' · <span class="badge ok">du hilfst</span>' : ''}</span></div></a>`;
    }).join('') || '<div class="card empty">Keine kommenden Heimspiele. Heimspiele legst du im Spielplan an.</div>'}</div>`;
  if ($('#gd_tpl')) $('#gd_tpl').onclick = async () => {
    const t = await api('gameday/templates');
    openModal(`<h2>Vorlagen für den Spieltag</h2><div class="form">
        <div class="field full"><label for="gt_roles">Aufgaben (eine pro Zeile: Aufgabe | Anzahl | Beginn-Ende)</label><textarea class="input" id="gt_roles" rows="9">${esc(t.gd_roles || '')}</textarea>
          <small class="muted">Beispiel: Kasse | 2 | 13:00-17:00. Zeit darf fehlen.</small></div>
        <div class="field full"><label for="gt_checks">Checkliste (ein Punkt pro Zeile)</label><textarea class="input" id="gt_checks" rows="9">${esc(t.gd_checklist || '')}</textarea></div></div>
      <div class="modal-foot"><div></div><div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="gt_ok">Speichern</button></div></div>`);
    $('#gt_ok').onclick = async () => { try { await api('gameday/templates', 'PUT', { gd_roles: $('#gt_roles').value, gd_checklist: $('#gt_checks').value }); closeModal(); toast('Vorlagen gespeichert'); } catch (e) { alert(e.message); } };
  };
};

async function gdGame(view, id) {
  let d;
  const reload = async () => { d = await api('gameday/' + id); draw(); };
  const draw = () => {
    const g = d.game, edit = d.can_edit;
    const total = d.shifts.reduce((n, s) => n + (Number(s.slots) || 1), 0), filled = d.shifts.reduce((n, s) => n + s.signups.length, 0);
    view.innerHTML = `<div class="page-head"><h1>${gdTitle(g)}<small>${gdWhen(g)}${g.location ? ' · ' + esc(g.location) : ''} · ${filled} von ${total} Helfern</small></h1>
        <div class="btn-row"><a class="btn keep" href="#/spieltag">← Alle Heimspiele</a>${edit && !d.shifts.length ? '<button class="btn primary" id="gd_fill">Vorlage einfügen</button>' : ''}</div></div>
      ${edit ? `<div class="card gd-link">${d.link ? `<div class="grow"><b>Link für Helfer</b> ${d.link.open ? '<span class="badge ok">offen</span>' : '<span class="badge">geschlossen</span>'}
          <div class="cmd"><code>${esc(d.link.url)}</code><button class="btn sm keep" id="gd_copy">Kopieren</button></div>
          <span class="muted small">In die WhatsApp-Gruppe schicken. Wer den Link hat, kann sich ohne Konto eintragen und sieht nur Vornamen.</span></div>
          <div class="btn-row"><button class="btn sm" id="gd_open">${d.link.open ? 'Schließen' : 'Öffnen'}</button><button class="btn sm" id="gd_new">Neuer Link</button></div>`
        : '<div class="grow"><b>Link für Helfer</b><div class="muted small">Noch kein Link. Damit tragen sich Helfer ohne Hub-Konto ein.</div></div><button class="btn primary" id="gd_new">Link erzeugen</button>'}</div>` : ''}
      <div class="gd-grid">
        <div><div class="sec-head-hub"><h2>Aufgaben</h2>${edit ? '<button class="btn sm" id="gd_addshift">+ Aufgabe</button>' : ''}</div>
          ${d.shifts.map(s => {
            const free = (Number(s.slots) || 1) - s.signups.length, mine = s.signups.some(x => x.user_id === d.me);
            return `<div class="card gd-shift-hub ${free <= 0 ? 'full' : ''}">
              <div class="gd-sh-head"><div class="grow"><b>${esc(s.role || '')}</b><div class="muted small">${s.start ? esc(s.start) + (s.end ? ' bis ' + esc(s.end) : '') + ' Uhr · ' : ''}${s.signups.length}/${Number(s.slots) || 1}${free > 0 ? ` · ${free} frei` : ' · voll'}</div>
                ${s.notes ? `<div class="small">${esc(s.notes)}</div>` : ''}</div>
                <div class="btn-row">${mine ? `<button class="btn sm keep" data-out="${s.id}">Austragen</button>` : free > 0 ? `<button class="btn sm primary keep" data-in="${s.id}">Ich helfe</button>` : ''}
                  ${edit ? `<button class="btn sm" data-addp="${s.id}" title="Helfer von Hand eintragen">+ Person</button><button class="btn sm ghost" data-eds="${s.id}">Bearbeiten</button>` : ''}</div></div>
              ${s.signups.length ? `<ul class="gd-people">${s.signups.map(p => `<li><span class="pf-av" style="--h:${[...(p.name || '?')].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7)}">${esc((p.name || '?').charAt(0).toUpperCase())}</span>
                <span class="grow"><b>${esc(p.name || '')}</b>${p.phone ? ` <a class="small" href="tel:${esc(p.phone.replace(/[^+0-9]/g, ''))}">${esc(p.phone)}</a>` : ''}</span>
                <span class="badge">${esc(p.source || '')}</span>${edit ? `<button class="btn sm ghost" data-rmp="${p.id}" aria-label="${esc(p.name)} austragen">✕</button>` : ''}</li>`).join('')}</ul>` : ''}
            </div>`;
          }).join('') || `<div class="card empty">Noch keine Aufgaben.${edit ? ' Mit „Vorlage einfügen“ kommen Kasse, Grill, Aufbau und Co. auf einen Klick.' : ''}</div>`}
        </div>
        <div><div class="sec-head-hub"><h2>Checkliste</h2>${edit ? '<button class="btn sm" id="gd_addcheck">+ Punkt</button>' : ''}</div>
          <div class="card">${d.checks.map(c => `<label class="check gd-check ${Number(c.done) ? 'done' : ''}"><input type="checkbox" data-chk="${c.id}" ${Number(c.done) ? 'checked' : ''} ${edit ? '' : 'disabled'}>
              <span class="grow">${esc(c.text || '')}${Number(c.done) && c.done_by ? `<span class="muted small"> · ${esc(c.done_by)}</span>` : ''}</span>${edit ? `<button type="button" class="btn sm ghost" data-rmc="${c.id}" aria-label="Punkt löschen">✕</button>` : ''}</label>`).join('')
            || '<div class="muted">Noch keine Punkte.</div>'}</div></div>
      </div>`;
    bind();
  };
  const bind = () => {
    const act = async (fn, msg) => { try { await fn(); if (msg) toast(msg); await reload(); } catch (e) { alert(e.message); } };
    if ($('#gd_fill')) $('#gd_fill').onclick = () => act(() => api(`gameday/${id}/template`, 'POST'), 'Vorlage eingefügt');
    if ($('#gd_new')) $('#gd_new').onclick = () => { if (!d.link || confirmBox('Neuen Link erzeugen? Der alte Link funktioniert danach nicht mehr.')) act(() => api(`gameday/${id}/link`, 'POST'), 'Link erzeugt'); };
    if ($('#gd_open')) $('#gd_open').onclick = () => act(() => api(`gameday/${id}/link`, 'PUT', { open: !d.link.open }), d.link.open ? 'Link geschlossen' : 'Link geöffnet');
    if ($('#gd_copy')) $('#gd_copy').onclick = () => { navigator.clipboard?.writeText(d.link.url); toast('Link kopiert'); };
    $$('[data-in]', view).forEach(b => b.onclick = () => act(() => api(`gameday/${id}/me`, 'POST', { shift_id: Number(b.dataset.in) }), 'Eingetragen, wir erinnern dich am Vortag'));
    $$('[data-out]', view).forEach(b => b.onclick = () => act(() => api(`gameday/${id}/me?shift_id=${b.dataset.out}`, 'DELETE'), 'Ausgetragen'));
    $$('[data-rmp]', view).forEach(b => b.onclick = () => { if (confirmBox('Diese Person aus der Aufgabe austragen?')) act(() => api('gd_signups/' + b.dataset.rmp, 'DELETE'), 'Ausgetragen'); });
    $$('[data-rmc]', view).forEach(b => b.onclick = e => { e.preventDefault(); if (confirmBox('Punkt löschen?')) act(() => api('gd_checks/' + b.dataset.rmc, 'DELETE')); });
    $$('[data-chk]', view).forEach(c => c.onchange = () => act(() => api('gd_checks/' + c.dataset.chk, 'PUT',
      { done: c.checked ? 1 : 0, done_by: c.checked ? (App.me.display_name || App.me.username) : '', done_at: c.checked ? new Date().toISOString().slice(0, 16) : '' })));
    const editShift = async rec => { const r = await editRecord('gd_shifts', F.gd_shifts, rec, { newTitle: 'Neue Aufgabe', editTitle: 'Aufgabe bearbeiten' }); if (r) reload(); };
    if ($('#gd_addshift')) $('#gd_addshift').onclick = () => editShift({ game_id: id, slots: 1, sort: d.shifts.length });
    $$('[data-eds]', view).forEach(b => b.onclick = () => editShift(d.shifts.find(s => s.id == b.dataset.eds)));
    $$('[data-addp]', view).forEach(b => b.onclick = () => {
      openModal(`<h2>Helfer eintragen</h2><div class="form"><div class="field"><label for="gp_name">Name</label><input class="input" id="gp_name" maxlength="80"></div>
          <div class="field"><label for="gp_phone">Telefon (optional)</label><input class="input" id="gp_phone" maxlength="40"></div></div>
        <div class="modal-foot"><div></div><div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="gp_ok">Eintragen</button></div></div>`);
      $('#gp_ok').onclick = () => { const n = $('#gp_name').value.trim(); if (!n) return alert('Bitte einen Namen angeben.');
        closeModal(); act(() => api('gd_signups', 'POST', { shift_id: Number(b.dataset.addp), game_id: id, name: n, phone: $('#gp_phone').value.trim(), source: 'von Hand', created: new Date().toISOString().slice(0, 19) }), 'Eingetragen'); };
      $('#gp_name').focus();
    });
    if ($('#gd_addcheck')) $('#gd_addcheck').onclick = () => {
      const t = prompt('Neuer Punkt für die Checkliste:'); if (t && t.trim()) act(() => api('gd_checks', 'POST', { game_id: id, text: t.trim().slice(0, 200), done: 0, sort: d.checks.length }));
    };
  };
  await reload();
}
