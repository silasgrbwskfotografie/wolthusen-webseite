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
        <div class="btn-row"><button class="btn keep" onclick="exportGamesCsv()">CSV für Canva</button><button class="vw btn primary" onclick="editGame()">+ Spiel</button></div></div>
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

