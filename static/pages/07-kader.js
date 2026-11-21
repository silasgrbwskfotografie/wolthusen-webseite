/* ====================================================================== */
/* Kader */
App.pages.players = async (view) => {
  await load('players');
  let unit = App._unit || 'Alle', team = App._kteam || 'Alle Mannschaften', q = '', showInactive = false;
  const draw = () => {
    App._unit = unit; App._kteam = team;
    let list = App.cache.players.filter(p => (showInactive || Number(p.active)) && (team === 'Alle Mannschaften' || teamOf(p) === team));
    if (unit === 'Trainer & Betreuer') list = list.filter(p => p.kind !== 'Spieler');
    else if (unit === 'Neuzugänge') list = list.filter(p => p.kind === 'Spieler' && Number(p.rookie));
    else if (unit !== 'Alle') list = list.filter(p => p.kind === 'Spieler' && p.position === unit);
    if (q) list = list.filter(p => (fullName(p) + ' ' + p.number + ' ' + p.position + ' ' + p.role + ' ' + (p.extra_role || '')).toLowerCase().includes(q));
    list.sort((a, b) => (a.kind === 'Spieler') - (b.kind === 'Spieler') || (Number(a.number) || 999) - (Number(b.number) || 999) || fullName(a).localeCompare(fullName(b)));
    const total = App.cache.players.filter(p => Number(p.active) && p.kind === 'Spieler' && (team === 'Alle Mannschaften' || teamOf(p) === team)).length;
    view.innerHTML = `
      <div class="page-head"><h1>Kader &amp; Trainer<small>${total} aktive Spieler</small></h1>
        <div class="btn-row"><button class="btn keep" id="k_csv" title="Aktuelle Ansicht als CSV für Canva-Massenerstellung">CSV für Canva</button><button class="btn primary" id="k_new">+ Person</button></div></div>
      <div id="pf_box"></div>
      <div class="toolbar">${teamBar(team, 'data-t')}</div>
      <div class="toolbar">${['Alle', ...POSITIONS, 'Neuzugänge', 'Trainer & Betreuer'].map(u => `<button class="btn sm ${u === unit ? 'dark' : ''}" data-u="${u}">${u}</button>`).join('')}
        <input class="input" id="k_q" placeholder="Suchen" value="${esc(q)}" style="max-width:220px">
        <label class="check small"><input type="checkbox" id="k_in" ${showInactive ? 'checked' : ''}> inaktive zeigen</label></div>
      <div class="table-wrap"><table><thead><tr><th></th><th>#</th><th>Name</th><th>Position / Rolle</th><th>Instagram</th><th>Einwilligung</th><th></th></tr></thead><tbody>
      ${list.map(p => `<tr style="${Number(p.active) ? '' : 'opacity:.5'}">
        <td>${p.photo ? `<img class="thumb" src="${esc(p.photo)}">` : '<div class="thumb"></div>'}</td>
        <td><b>${esc(p.number || '')}</b></td>
        <td><b>${esc(fullName(p))}</b> ${p.source === 'Tabelle' ? '<span class="badge" title="Früher aus der Google-Tabelle angelegt">Tabelle</span>' : ''} ${Number(p.rookie) ? '<span class="badge warn">Neu</span>' : ''} ${teamBadge(p)} ${p.kind !== 'Spieler' ? `<span class="badge dark">${esc(p.kind)}</span>` : ''}</td>
        <td>${esc(p.kind === 'Spieler' ? p.position || '' : p.role || '')}${p.kind === 'Spieler' && p.extra_role ? `<div class="muted small">${esc(p.extra_role)}</div>` : ''}</td>
        <td class="small">${esc(handle(p.instagram))}</td>
        <td>${Number(p.consent) ? '<span class="badge ok">ja</span>' : '<span class="badge warn">fehlt</span>'}</td>
        <td class="actions"><button class="pp btn sm" onclick="planPost({type:'Spielervorstellung',player_id:${p.id}})">Post planen</button> <button class="btn sm ghost" data-e="${p.id}">Bearbeiten</button></td>
      </tr>`).join('') || '<tr><td colspan="7" class="empty">Noch niemand eingetragen.</td></tr>'}
      </tbody></table></div>`;
    $$('[data-u]').forEach(b => b.onclick = () => { unit = b.dataset.u; draw(); });
    $$('[data-t]').forEach(b => b.onclick = () => { team = b.dataset.t; draw(); });
    $('#k_q').oninput = e => { q = e.target.value.toLowerCase(); const pos = e.target.selectionStart; draw(); const el = $('#k_q'); el.focus(); el.setSelectionRange(pos, pos); };
    $('#k_in').onchange = e => { showInactive = e.target.checked; draw(); };
    const edit = async rec => { const r = await editRecord('players', F.players, rec, { newTitle: 'Neue Person', editTitle: 'Person bearbeiten' }); if (r) { await load('players'); draw(); } };
    $('#k_new').onclick = () => edit({ kind: 'Spieler', active: 1, team: TEAMS.includes(team) ? team : TEAMS[0] });
    $$('[data-e]').forEach(b => b.onclick = () => edit(byId(App.cache.players, b.dataset.e)));
    $('#k_csv').onclick = () => {
      const ps = list.filter(p => p.kind === 'Spieler' ? Number(p.consent) : true);
      downloadCsv('kader-canva.csv', ['Nummer', 'Vorname', 'Nachname', 'Name', 'Position', 'Mannschaft', 'Rolle', 'Neuzugang', 'Dabei seit', 'Instagram'],
        ps.map(p => [p.number, p.first_name, p.last_name, fullName(p), p.position, teamOf(p), p.kind === 'Spieler' ? (p.extra_role || '') : (p.role || p.kind), Number(p.rookie) ? 'Neuzugang' : '', p.since, handle(p.instagram)]));
      if (ps.length < list.length) toast(`${list.length - ps.length} Spieler ohne Einwilligung nicht exportiert`);
    };
    playerFormBox($('#pf_box'), draw);
  };
  draw();
};

/* Spielerbogen (/spielerbogen): Passwort, an/aus und Eingänge prüfen und in den Kader übernehmen */
async function playerFormBox(box, redraw) {
  if (!box) return;
  let st, signups;
  try { [st, signups] = await Promise.all([api('player-form'), api('player_signups')]); } catch { return; }
  const w = can('verein', 2);
  const open = signups.filter(s => s.status === 'Neu').sort((a, b) => (a.created || '').localeCompare(b.created || ''));
  const norm = s => (s || '').toLowerCase().replace(/\s+/g, ' ').trim();
  const match = s => App.cache.players.find(p => norm(fullName(p)) === norm(`${s.first_name} ${s.last_name}`))
    || (s.instagram ? App.cache.players.find(p => norm(handle(p.instagram)) === norm(handle(s.instagram))) : null);
  const opts = s => {
    const m = match(s);
    return `<option value="">Neu anlegen</option>` + [...App.cache.players].sort((a, b) => fullName(a).localeCompare(fullName(b)))
      .map(p => `<option value="${p.id}" ${m && m.id === p.id ? 'selected' : ''}>${esc(playerLabel(p))} ergänzen</option>`).join('');
  };
  const row = s => `<div class="list-item" style="align-items:flex-start;gap:14px">
      <div class="grow"><b>${esc(s.first_name)} ${esc(s.last_name)}</b>${s.nickname ? ` <span class="muted">(${esc(s.nickname)})</span>` : ''}
        <span class="badge dark">${esc(s.kind)}</span> <span class="badge">${esc(s.team || TEAMS[0])}</span>
        ${s.source === 'Einladung' ? '<span class="badge" title="Aus einer Einladung: beim Übernehmen wird das Konto mit der Person verknüpft">Einladung</span>' : ''}
        ${Number(s.consent) ? '<span class="badge ok">Einwilligung ja</span>' : '<span class="badge warn">keine Einwilligung</span>'}
        <div class="small">${[s.number ? '#' + esc(s.number) : '', esc(s.position || ''), esc(s.role || ''), s.instagram ? '@' + esc(s.instagram) : '', s.since ? 'seit ' + esc(s.since) : '']
          .filter(Boolean).join(' | ')}</div>
        <div class="small muted">${esc(s.email || '')}${s.phone ? ' | ' + esc(s.phone) : ''} | eingegangen ${fmtStamp(s.created)}</div>
        ${s.facts ? `<div class="small" style="margin-top:4px">${esc(s.facts)}</div>` : ''}
        ${s.message ? `<div class="small muted" style="margin-top:4px">Nachricht: ${esc(s.message)}</div>` : ''}</div>
      ${w ? `<div style="display:grid;gap:6px;min-width:240px"><select class="input" data-pf-target="${s.id}">${opts(s)}</select>
        <div class="btn-row"><button class="btn primary sm" data-pf-apply="${s.id}">Übernehmen</button><button class="btn sm danger" data-pf-drop="${s.id}">Verwerfen</button></div></div>` : ''}
    </div>`;
  box.innerHTML = `<div class="card" style="margin-bottom:16px"><h2>Spielerbogen ${st.open ? '<span class="badge ok">offen</span>' : '<span class="badge">geschlossen</span>'}
      ${open.length ? `<span class="badge red">${open.length} neu</span>` : ''}</h2>
    <p class="muted small">Ersetzt die Google-Tabelle: Spieler, Coaches und Staff tragen sich selbst ein (Name, Spitzname, Nummer, Position bzw. Rolle, Instagram, Einwilligung,
      dazu E-Mail und Telefon, die nur intern bleiben). Geschützt mit einem Passwort, das du hier festlegst. Eingänge kommen erst mit „Übernehmen“ in den Kader.
      Angaben aus Einladungen (Verwaltung &gt; Konten &gt; Einladen) landen ebenfalls hier.</p>
    <div class="btn-row"><input class="input" readonly value="${esc(st.url)}" style="max-width:340px"><button class="btn keep" id="pf_copy">Link kopieren</button>
      <a class="btn keep" href="/spielerbogen" target="_blank" rel="noopener">Ansehen</a>
      ${w ? `<button class="btn ${st.open ? '' : 'primary'}" id="pf_toggle">${st.open ? 'Schließen' : 'Öffnen'}</button>` : ''}</div>
    ${w ? `<div class="btn-row" style="margin-top:10px"><input class="input" id="pf_pw" type="password" autocomplete="new-password" placeholder="${st.has_pw ? 'Neues Passwort (mind. 8 Zeichen)' : 'Passwort festlegen (mind. 8 Zeichen)'}" style="max-width:280px">
      <button class="btn" id="pf_pw_save">${st.has_pw ? 'Passwort ändern' : 'Passwort speichern'}</button>
      <span class="muted small">${st.has_pw ? 'Ein Passwort ist gesetzt. Es wird nur verschlüsselt gespeichert und kann nicht angezeigt werden.' : 'Noch kein Passwort gesetzt.'}</span></div>` : ''}
    ${open.length ? `<div class="list" style="margin-top:14px">${open.map(row).join('')}</div>` : '<p class="muted small" style="margin-top:10px">Keine neuen Eingänge.</p>'}
  </div>`;
  $('#pf_copy', box).onclick = () => copyText(st.url);
  if ($('#pf_toggle', box)) $('#pf_toggle', box).onclick = async () => {
    try { await api('player-form', 'PUT', { open: !st.open }); toast(st.open ? 'Spielerbogen geschlossen' : 'Spielerbogen geöffnet'); playerFormBox(box, redraw); } catch (e) { alert(e.message); }
  };
  if ($('#pf_pw_save', box)) $('#pf_pw_save', box).onclick = async () => {
    try { await api('player-form', 'PUT', { password: $('#pf_pw', box).value }); toast('Passwort gespeichert'); playerFormBox(box, redraw); } catch (e) { alert(e.message); }
  };
  $$('[data-pf-apply]', box).forEach(b => b.onclick = async () => {
    const id = b.dataset.pfApply, target = $(`[data-pf-target="${id}"]`, box).value;
    try { await api(`player-form/signups/${id}/apply`, 'POST', { player_id: target ? Number(target) : null }); toast(target ? 'Person ergänzt' : 'Neue Person angelegt'); await load('players', true); redraw(); }
    catch (e) { alert(e.message); }
  });
  $$('[data-pf-drop]', box).forEach(b => b.onclick = async () => {
    if (!confirmBox('Diesen Eingang verwerfen? Er wird nicht in den Kader übernommen.')) return;
    try { await api(`player_signups/${b.dataset.pfDrop}`, 'PUT', { status: 'Verworfen' }); toast('Verworfen'); playerFormBox(box, redraw); } catch (e) { alert(e.message); }
  });
}

