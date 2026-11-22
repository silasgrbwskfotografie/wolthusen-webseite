/* ====================================================================== */
/* Spielplan */
async function editGame(id) {
  await loadAll('games', 'opponents', 'sponsors');
  const rec = id ? byId(App.cache.games, id) : {};
  const r = await editRecord('games', F.games(), rec, { newTitle: 'Neues Spiel', editTitle: 'Spiel bearbeiten' });
  if (r) route();
}

async function assignGame(gameId) {
  await loadAll('media_team', 'assignments', 'games', 'opponents');
  const g = byId(App.cache.games, gameId);
  const tasks = mediaTasks();
  const team = App.cache.media_team.filter(m => Number(m.active));
  const cur = App.cache.assignments.filter(a => a.game_id == gameId);
  openModal(`<h2>Media Team: ${esc(gameLabel(g))}</h2>
    ${!team.length ? '<div class="warnline" style="margin-bottom:10px">Noch keine Mitglieder im Media Team angelegt.</div>' : ''}
    <table><thead><tr><th>Aufgabe</th><th>Wer</th><th>Zugesagt</th></tr></thead><tbody>
    ${tasks.map((t, i) => { const a = cur.find(x => x.task === t) || {}; return `<tr><td><b>${esc(t)}</b></td>
      <td><select class="input" id="as_m_${i}"><option value="">(offen)</option>${team.map(m => `<option value="${m.id}" ${m.id == a.member_id ? 'selected' : ''}>${esc(m.name)}</option>`).join('')}</select></td>
      <td><input type="checkbox" id="as_c_${i}" ${Number(a.confirmed) ? 'checked' : ''} style="accent-color:var(--red);width:18px;height:18px"></td></tr>`; }).join('')}
    </tbody></table>
    <div class="hint" style="margin-top:8px">Aufgaben änderst du unter Einstellungen.</div>
    <div class="modal-foot"><button class="btn" id="as_copy">Als Nachricht kopieren</button><div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="as_save">Speichern</button></div></div>`);
  const collectA = () => tasks.map((t, i) => ({ task: t, member_id: $('#as_m_' + i).value ? Number($('#as_m_' + i).value) : null, confirmed: $('#as_c_' + i).checked ? 1 : 0 }));
  $('#as_copy').onclick = () => {
    const lines = collectA().map(a => `${a.task}: ${byId(team, a.member_id)?.name || 'noch offen'}`);
    copyText(noDashes(`💜 Media Team Einteilung ${fmtDate(g.date, true)} ${Number(g.home) ? 'gegen' : 'bei'} ${byId(App.cache.opponents, g.opponent_id)?.name || 'TBA'}${g.time ? ', Anstoß ' + g.time + ' Uhr' : ''}\n\n${lines.join('\n')}\n\nBitte kurz bestätigen 👍`));
  };
  $('#as_save').onclick = async () => {
    for (const a of cur) await api('assignments/' + a.id, 'DELETE');
    for (const a of collectA()) if (a.member_id) await api('assignments', 'POST', { ...a, game_id: gameId });
    invalidate('assignments'); closeModal(); toast('Einteilung gespeichert'); route();
  };
}

/* Import aus dem DFBnet: Vereinsspielplan als CSV oder Excel, erst Vorschau, dann übernehmen (Abgleich im Server, dfb_plan) */
const DFB_ACTION = { neu: ['neu', 'ok'], 'ändern': ['geändert', 'warn'], abgesetzt: ['abgesetzt', 'red'], gleich: ['unverändert', ''] };
const DFB_FIELD = { date: 'Datum', time: 'Anstoß', home: 'Heim', league: 'Staffel', match_no: 'Spielkennung', team: 'Mannschaft', location: 'Spielort', score_us: 'Tore wir', score_them: 'Tore Gegner' };
async function dfbImport() {
  openModal(`<h2>Spielplan aus dem DFBnet</h2>
    <p class="muted small">Den Vereinsspielplan im DFBnet als Excel- oder CSV-Datei exportieren und hier auswählen. Der Hub zeigt erst eine Vorschau und ändert nichts,
      bevor du auf „Übernehmen“ klickst. Neue Spiele und Gegner werden angelegt, verlegte Spiele aktualisiert, abgesetzte markiert.
      Eingetragene Ergebnisse, Sponsoren, Livestream und Notizen bleiben unverändert.</p>
    <div class="form">
      <div class="field full"><label for="dfb_file">Datei (.xlsx oder .csv)</label><input type="file" id="dfb_file" accept=".xlsx,.csv,.txt,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"></div>
      <div class="field"><label for="dfb_team">Mannschaft, falls nicht erkennbar</label><select class="input" id="dfb_team">${TEAMS.map(t => `<option>${esc(t)}</option>`).join('')}</select></div>
      <div class="field"><label for="dfb_season">Saison für neue Spiele</label><input class="input" id="dfb_season" value="${esc(App.settings.season || '')}"></div>
    </div>
    <div id="dfb_out"></div>
    <div class="modal-foot"><div></div><div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button>
      <button class="btn" id="dfb_preview">Vorschau</button><button class="btn primary" id="dfb_apply" disabled>Übernehmen</button></div></div>`);
  let body = null;
  const out = $('#dfb_out'), applyBtn = $('#dfb_apply');
  const send = async extra => {
    const f = $('#dfb_file').files[0];
    if (!f) { alert('Bitte zuerst die Datei aus dem DFBnet auswählen.'); return null; }
    body = { file: await fileToDataUrl(f), filename: f.name, team: $('#dfb_team').value, season: $('#dfb_season').value.trim() };
    return api('dfbnet-import', 'POST', { ...body, ...extra });
  };
  $('#dfb_file').onchange = $('#dfb_team').onchange = () => { applyBtn.disabled = true; out.innerHTML = ''; };
  $('#dfb_preview').onclick = async () => {
    let r;
    try { r = await send({}); } catch (e) { out.innerHTML = `<div class="warnline">${esc(e.message)}</div>`; return; }
    if (!r) return;
    const todo = r.items.filter(x => x.action !== 'gleich' && !(x.action === 'abgesetzt' && !x.id));
    const count = k => r.items.filter(x => x.action === k).length;
    out.innerHTML = `<div class="toolbar" style="margin-top:10px">${Object.keys(DFB_ACTION).map(k => `<span class="badge ${DFB_ACTION[k][1]}">${count(k)} ${DFB_ACTION[k][0]}</span>`).join(' ')}</div>
      ${r.items.length ? `<div class="table-wrap" style="max-height:340px;overflow:auto"><table><thead><tr><th>Datum</th><th>Mannschaft</th><th>Spiel</th><th>Status</th></tr></thead><tbody>
      ${r.items.map(x => `<tr><td style="white-space:nowrap">${fmtDate(x.date)}${x.time ? ' ' + esc(x.time) : ''}</td><td>${esc(x.team)}</td>
        <td>${Number(x.home) ? 'vs' : '@'} ${esc(x.opponent)}<div class="muted small">${esc(x.league || x.kind)}${x.match_no ? ' | ' + esc(x.match_no) : ''}</div>
          ${Object.entries(x.changes).map(([k, [a, b]]) => `<div class="small">${esc(DFB_FIELD[k] || k)}: <span class="muted">${esc(a || 'leer')}</span> auf <b>${esc(b)}</b></div>`).join('')}</td>
        <td><span class="badge ${DFB_ACTION[x.action][1]}">${DFB_ACTION[x.action][0]}</span>${x.action === 'abgesetzt' && !x.id ? '<div class="muted small">nicht im Hub, wird übersprungen</div>' : ''}</td></tr>`).join('')}
      </tbody></table></div>` : ''}
      <details style="margin-top:8px"><summary class="muted small">Hinweise zur Datei (${r.notes.length})</summary><div class="small muted">${r.notes.map(n => esc(n)).join('<br>')}</div></details>`;
    applyBtn.disabled = !todo.length;
    applyBtn.textContent = todo.length ? `Übernehmen (${todo.length})` : 'Nichts zu übernehmen';
  };
  applyBtn.onclick = async () => {
    if (!body) return;
    applyBtn.disabled = true;
    try {
      const r = await api('dfbnet-import', 'POST', { ...body, apply: true });
      invalidate('games', 'opponents'); closeModal();
      toast(`Übernommen: ${r.counts['neu']} neu, ${r.counts['ändern']} geändert, ${r.counts['abgesetzt']} abgesetzt`);
      route();
    } catch (e) { applyBtn.disabled = false; alert('Import fehlgeschlagen: ' + e.message); }
  };
}

App.pages.games = async (view) => {
  await loadAll('games', 'opponents', 'sponsors', 'assignments', 'posts');
  const seasons = [...new Set([App.settings.season, ...App.cache.games.map(g => g.season)].filter(Boolean))].sort().reverse();
  let season = App._season || App.settings.season, team = App._gteam || 'Alle Mannschaften';
  const tasks = mediaTasks();
  const draw = () => {
    App._season = season; App._gteam = team;
    const list = App.cache.games.filter(g => (season === 'alle' || (g.season || '') == season) && (team === 'Alle Mannschaften' || teamOf(g) === team)).sort((a, b) => ((a.date || '') + (a.time || '')).localeCompare((b.date || '') + (b.time || '')));
    view.innerHTML = `
      <div class="page-head"><h1>Spielplan<small>${list.length} Spiele</small></h1>
        <div class="btn-row"><button class="btn keep" onclick="exportGamesCsv()">CSV für Canva</button><button class="vw btn" onclick="dfbImport()">Import aus DFBnet</button><button class="vw btn primary" onclick="editGame()">+ Spiel</button></div></div>
      <div class="toolbar">${[...seasons, 'alle'].map(s => `<button class="btn sm ${s == season ? 'dark' : ''}" data-s="${esc(s)}">${s === 'alle' ? 'Alle' : 'Saison ' + esc(s)}</button>`).join('')}</div>
      <div class="toolbar">${teamBar(team, 'data-t')}</div>
      <div class="table-wrap"><table><thead><tr><th>Datum</th><th></th><th>Gegner</th><th>Ort</th><th>Ergebnis</th><th>Sponsor</th><th>Media Team</th><th>Posts</th><th></th></tr></thead><tbody>
      ${list.map(g => {
        const o = byId(App.cache.opponents, g.opponent_id) || {};
        const sp = byId(App.cache.sponsors, g.sponsor_id);
        const asg = App.cache.assignments.filter(a => a.game_id == g.id && a.member_id).length;
        const posts = App.cache.posts.filter(p => p.game_id == g.id);
        const res = resultOf(g.score_us ?? '', g.score_them ?? '');
        return `<tr>
          <td style="white-space:nowrap"><b>${fmtDate(g.date)}</b><div class="muted small">${g.date ? WD[parseDate(g.date).getDay()] : ''}${g.time ? ', ' + g.time + ' Uhr' : ''}</div></td>
          <td>${o.logo ? `<img class="thumb logo" src="${esc(o.logo)}">` : ''}</td>
          <td><b>${Number(g.home) ? 'vs' : '@'} ${esc(o.name || 'TBA')}</b><div class="muted small">${esc(g.kind || '')}${g.league ? ' | ' + esc(g.league) : ''}</div>${teamBadge(g)}</td>
          <td>${Number(g.home) ? '<span class="badge red">Heim</span>' : '<span class="badge">Auswärts</span>'}<div class="muted small">${esc(g.location || (Number(g.home) ? App.settings.home_location : ''))}</div></td>
          <td>${g.score_us !== null && g.score_us !== '' ? `<b>${g.score_us}:${g.score_them}</b> <span class="badge ${res === 'SIEG' ? 'ok' : res === 'NIEDERLAGE' ? '' : 'warn'}">${res.charAt(0) + res.slice(1).toLowerCase()}</span>` : '<span class="muted">offen</span>'}</td>
          <td>${sp ? esc(sp.name) : '<span class="muted">keiner</span>'}</td>
          <td><button class="pp btn sm" onclick="assignGame(${g.id})">${asg}/${tasks.length}</button></td>
          <td>${posts.length ? posts.map(p => statusBadge(p.type)).join(' ') : '<span class="muted small">keine</span>'}</td>
          <td class="actions"><button class="btn sm keep" onclick="copyGameInfo(${g.id})">Infos kopieren</button> <button class="pp btn sm" onclick="planPost({type:'Gameday',game_id:${g.id}})">Gameday</button> <button class="pp btn sm" onclick="planPost({type:'Ergebnis',game_id:${g.id}})">Endstand</button> <button class="vw btn sm ghost" onclick="editGame(${g.id})">Bearbeiten</button></td>
        </tr>`; }).join('') || '<tr><td colspan="9" class="empty">Noch keine Spiele in dieser Saison.</td></tr>'}
      </tbody></table></div>`;
    $$('[data-s]').forEach(b => b.onclick = () => { season = b.dataset.s; draw(); });
    $$('[data-t]').forEach(b => b.onclick = () => { team = b.dataset.t; draw(); });
  };
  draw();
};

