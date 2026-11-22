/* ====================================================================== */
/* Mannschaften (Verein > Mannschaften): links alle Mannschaften nach Sportart, rechts alles zu einer Mannschaft.
   Daten: Tabelle teams; Training, Kader, Trainer und Spiele hängen über den Namen dran (Umbenennen zieht der Server mit). */
const TEAM_DAYS = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag', 'Sonntag'];
const teamSportOf = t => SPORTS.includes(t.sport) ? t.sport : 'Sonstiges';
const teamSort = list => [...list].sort((a, b) => SPORTS.indexOf(teamSportOf(a)) - SPORTS.indexOf(teamSportOf(b))
  || Number(a.youth || 0) - Number(b.youth || 0) || Number(a.sort || 0) - Number(b.sort || 0) || a.id - b.id);

async function teamsRefresh() {   // Auswahllisten im ganzen Hub (TEAMS) auf den neuen Stand bringen
  invalidate('teams');
  try { App.me = await api('me'); setTeams(App.me.teams); } catch { /* Liste bleibt bis zum Neuladen */ }
}

function teamGo(id) {
  const h = '#/teams/' + (id || '');
  if (location.hash === h) route(); else location.hash = h;
}

async function teamEdit(rec) {
  const r = await editRecord('teams', F.teams, rec, { newTitle: 'Neue Mannschaft', editTitle: 'Mannschaft bearbeiten' });
  if (!r) return;
  await teamsRefresh();
  teamGo(r.deleted ? '' : r.id);
}

async function teamSub(table, fields, rec, titles) {
  const r = await editRecord(table, fields, rec, titles);
  if (r) route();
}

App.pages.teams = async (view, args) => {
  await loadAll('teams', 'trainings', 'players', 'games', 'opponents');
  const list = teamSort(App.cache.teams);
  const cur = byId(list, Number(args[0])) || list.find(t => Number(t.active)) || list[0];
  const groups = [];
  for (const sport of SPORTS) {
    const ts = list.filter(t => teamSportOf(t) === sport);
    if (sport === 'Fußball') {
      groups.push(['Fußball', ts.filter(t => !Number(t.youth))], ['Fußball Jugend', ts.filter(t => Number(t.youth))]);
    } else groups.push([sport, ts]);
  }
  const navHtml = groups.filter(g => g[1].length).map(([head, ts]) => `<h4>${esc(head)}</h4>${ts.map(t =>
    `<a href="#/teams/${t.id}" class="${cur && t.id === cur.id ? 'on' : ''} ${Number(t.active) ? '' : 'off'}">${esc(t.name)}${Number(t.active) ? '' : ' <span class="badge">inaktiv</span>'}</a>`).join('')}`).join('');

  if (!cur) {
    view.innerHTML = `<div class="page-head"><h1>Mannschaften</h1><div class="btn-row"><button class="vw btn primary" id="tm_new">+ Mannschaft</button></div></div>
      <div class="card empty">Noch keine Mannschaft angelegt.</div>`;
    $('#tm_new').onclick = () => teamEdit({ active: 1, page: 1, sport: SPORTS[0] });
    return;
  }

  const name = cur.name, youth = Number(cur.youth), live = Number(cur.active) && Number(cur.page);
  const trainings = App.cache.trainings.filter(t => t.team === name)
    .sort((a, b) => (TEAM_DAYS.indexOf(a.weekday) - TEAM_DAYS.indexOf(b.weekday)) || (a.start || '').localeCompare(b.start || ''));
  const people = App.cache.players.filter(p => p.team === name);
  const staff = people.filter(p => p.kind !== 'Spieler').sort((a, b) => Number(b.active) - Number(a.active));
  const squad = people.filter(p => p.kind === 'Spieler').sort((a, b) => Number(b.active) - Number(a.active) || (Number(a.number) || 999) - (Number(b.number) || 999));
  const games = App.cache.games.filter(g => g.team === name).sort((a, b) => ((a.date || '') + (a.time || '')).localeCompare((b.date || '') + (b.time || '')));
  const today = todayStr();
  const next = games.filter(g => (g.date || '') >= today).slice(0, 6);
  const done = games.filter(g => g.date && g.date < today).slice(-6).reverse();
  const showGames = ['Fußball', 'American Football'].includes(teamSportOf(cur)) || games.length;
  const links = (cur.links || '').split('\n').map(l => l.trim()).filter(Boolean);
  const img = live ? await api('team-image/' + cur.id).catch(() => null) : null;
  const gameRow = g => {
    const o = byId(App.cache.opponents, g.opponent_id) || {};
    const res = g.score_us !== null && g.score_us !== '' && g.score_us !== undefined ? `<b>${esc(g.score_us)}:${esc(g.score_them)}</b>` : '<span class="muted">offen</span>';
    return `<tr><td style="white-space:nowrap">${fmtDate(g.date)}${g.time ? ' ' + esc(g.time) : ''}</td><td>${Number(g.home) ? 'vs' : '@'} ${esc(o.name || 'TBA')}<div class="muted small">${esc(g.league || g.kind || '')}</div></td>
      <td>${res}</td><td class="actions"><button class="vw btn sm ghost" data-game="${g.id}">Bearbeiten</button></td></tr>`;
  };
  const personRow = p => `<tr class="${Number(p.active) ? '' : 'muted'}"><td>${p.kind === 'Spieler' && p.number ? '#' + esc(p.number) + ' ' : ''}<b>${esc(fullName(p))}</b></td>
    <td>${esc(p.kind === 'Spieler' ? (p.position || '') : (p.role || p.kind))}${Number(p.active) ? '' : ' <span class="badge">inaktiv</span>'}</td>
    <td class="actions"><button class="vw btn sm ghost" data-person="${p.id}">Bearbeiten</button></td></tr>`;

  view.innerHTML = `
    <div class="page-head"><h1>${esc(name)}<small>${esc(teamSportOf(cur))}${youth ? ', Jugend' : ''}</small></h1>
      <div class="btn-row">${live ? `<a class="btn keep" href="/mannschaft/${esc(cur.slug)}" target="_blank" rel="noopener">Seite ansehen</a>` : ''}
        <button class="vw btn" id="tm_edit">Bearbeiten</button><button class="vw btn primary" id="tm_new">+ Mannschaft</button></div></div>
    <div class="team-layout">
      <nav class="card team-nav" aria-label="Mannschaften">${navHtml}</nav>
      <div class="team-main">
        <div class="toolbar">${Number(cur.active) ? '<span class="badge ok">aktiv</span>' : '<span class="badge warn">inaktiv: nicht auf der Webseite</span>'}
          ${Number(cur.page) ? `<span class="badge">Seite /mannschaft/${esc(cur.slug)}</span>` : '<span class="badge">ohne eigene Seite</span>'}
          ${youth ? '<span class="badge red">Jugend: Spieler nie auf der Webseite</span>' : ''}
          ${cur.schedule === 'nur fussball.de-Link' ? '<span class="badge">Spielplan: nur fussball.de-Link</span>' : ''}</div>
        <div class="grid2">
          <div class="card"><h3>Webseite</h3>
            <p><b>${esc(cur.lead || '')}</b>${cur.lead ? '' : '<span class="muted">Kein Untertitel</span>'}</p>
            <p class="small" style="white-space:pre-line">${esc((cur.intro || '').slice(0, 400))}${(cur.intro || '').length > 400 ? ' ...' : ''}${cur.intro ? '' : '<span class="muted">Kein Text</span>'}</p>
            ${links.length ? `<p class="small"><b>Links</b><br>${links.map(l => esc(l)).join('<br>')}</p>` : ''}
            <button class="vw btn sm" id="tm_edit2">Texte und Links bearbeiten</button></div>
          ${img ? `<div class="card web-img" id="tm_img"><h3>Titelbild ${img.own ? '<span class="badge ok">eigenes Bild</span>' : '<span class="badge">Standard</span>'}</h3>
            <div class="web-img-pic">${img.preview ? `<img src="${esc(img.preview)}" alt="">` : `<div class="empty">Standardbild (${youth ? 'Jugendfußball' : teamSportOf(cur).startsWith('Turnen') ? 'Turnen' : 'Herrenfußball'})</div>`}</div>
            <label class="small">Alt-Text<textarea class="input" rows="2" data-alt>${esc(img.alt)}</textarea></label>
            <div class="btn-row" style="margin-top:8px"><button class="vw btn sm primary" data-up>Bild hochladen</button><button class="vw btn sm" data-alt-save>Alt-Text speichern</button>
              ${img.own ? '<button class="vw btn sm ghost" data-reset>Standardbild</button>' : ''}<input type="file" accept="image/jpeg,image/png,image/webp" hidden></div>
            <p class="muted small">Querformat ab 1920 px Breite. Nur Fotos, mit denen alle Abgebildeten einverstanden sind${youth ? ' (bei Kindern die Eltern)' : ''}.</p></div>`
          : `<div class="card"><h3>Titelbild</h3><p class="muted">Nur Mannschaften mit eigener Seite (aktiv) haben ein Titelbild.</p></div>`}
        </div>
        <div class="grid2" style="margin-top:16px">
          <div class="card"><div class="page-head" style="margin:0 0 8px"><h3 style="margin:0">Trainingszeiten</h3><button class="vw btn sm" id="tm_tr_new">+ Zeit</button></div>
            <table><tbody>${trainings.map(t => `<tr class="${Number(t.active) ? '' : 'muted'}"><td><b>${esc(t.weekday || '')}</b></td>
              <td>${t.start ? esc(t.start) + (t.end ? ' bis ' + esc(t.end) : '') + ' Uhr' : '<span class="muted">Uhrzeit folgt</span>'}</td><td class="small">${esc(t.place || '')}</td>
              <td class="actions"><button class="vw btn sm ghost" data-tr="${t.id}">Bearbeiten</button></td></tr>`).join('') || '<tr><td class="empty">Noch keine Trainingszeiten.</td></tr>'}</tbody></table></div>
          <div class="card"><div class="page-head" style="margin:0 0 8px"><h3 style="margin:0">Trainer und Betreuer</h3><button class="vw btn sm" id="tm_staff_new">+ Person</button></div>
            <table><tbody>${staff.map(personRow).join('') || '<tr><td class="empty">Noch niemand eingetragen.</td></tr>'}</tbody></table></div>
        </div>
        <div class="grid2" style="margin-top:16px">
          <div class="card"><div class="page-head" style="margin:0 0 8px"><h3 style="margin:0">Kader <small class="muted">${squad.filter(p => Number(p.active)).length} aktiv</small></h3><button class="vw btn sm" id="tm_pl_new">+ Spieler</button></div>
            ${youth ? '<p class="muted small">Jugend: Die Spieler stehen nur im Hub, nie auf der Webseite.</p>' : ''}
            <table><tbody>${squad.map(personRow).join('') || '<tr><td class="empty">Noch keine Spieler.</td></tr>'}</tbody></table></div>
          ${showGames ? `<div class="card"><div class="page-head" style="margin:0 0 8px"><h3 style="margin:0">Spiele</h3><div class="btn-row"><a class="btn sm keep" href="#/games">Spielplan</a><button class="vw btn sm" id="tm_g_new">+ Spiel</button></div></div>
            ${cur.schedule === 'nur fussball.de-Link' ? `<p class="muted small">Auf der Webseite steht für diese Mannschaft nur der fussball.de-Link${links.length ? '' : ' (noch keiner eingetragen)'}. Spiele hier bleiben intern.</p>` : ''}
            <h4 class="muted small">Nächste Spiele</h4><table><tbody>${next.map(gameRow).join('') || '<tr><td class="empty">Keine kommenden Spiele.</td></tr>'}</tbody></table>
            ${done.length ? `<h4 class="muted small" style="margin-top:12px">Zuletzt gespielt</h4><table><tbody>${done.map(gameRow).join('')}</tbody></table>` : ''}</div>` : ''}
        </div>
        ${cur.notes ? `<div class="card" style="margin-top:16px"><h3>Interne Notizen</h3><p style="white-space:pre-line">${esc(cur.notes)}</p></div>` : ''}
      </div>
    </div>`;

  $('#tm_new').onclick = () => teamEdit({ active: 1, page: 1, sport: teamSportOf(cur), youth: cur.youth });
  $('#tm_edit').onclick = $('#tm_edit2').onclick = () => teamEdit(cur);
  $('#tm_tr_new').onclick = () => teamSub('trainings', F.trainings, { team: name, active: 1 }, { newTitle: 'Trainingszeit ' + name });
  $('#tm_staff_new').onclick = () => teamSub('players', F.players, { team: name, kind: 'Coach', active: 1 }, { newTitle: 'Trainer oder Betreuer' });
  $('#tm_pl_new').onclick = () => teamSub('players', F.players, { team: name, kind: 'Spieler', active: 1 }, { newTitle: 'Neuer Spieler' });
  if ($('#tm_g_new')) $('#tm_g_new').onclick = () => teamSub('games', F.games(), { team: name, home: 1 }, { newTitle: 'Neues Spiel ' + name });
  $$('[data-tr]').forEach(b => b.onclick = () => teamSub('trainings', F.trainings, byId(App.cache.trainings, b.dataset.tr), { editTitle: 'Trainingszeit bearbeiten' }));
  $$('[data-person]').forEach(b => b.onclick = () => teamSub('players', F.players, byId(App.cache.players, b.dataset.person), { editTitle: 'Person bearbeiten' }));
  $$('[data-game]').forEach(b => b.onclick = () => teamSub('games', F.games(), byId(App.cache.games, b.dataset.game), { editTitle: 'Spiel bearbeiten' }));

  const box = $('#tm_img');
  if (box) {
    const file = $('input[type=file]', box), alt = () => $('[data-alt]', box).value.trim();
    $('[data-up]', box).onclick = () => file.click();
    file.onchange = async () => {
      const f = file.files[0]; if (!f) return;
      if (!alt() && !confirmBox('Ohne Alt-Text hochladen? Besser vorher kurz beschreiben, was zu sehen ist.')) return;
      try {
        toast('Bild wird vorbereitet ...');
        const v = await webpVariants(f);
        await api('team-image/' + cur.id, 'POST', { ...v, alt: alt() });
        toast('Bild gespeichert'); route();
      } catch (e) { alert(e.message); }
    };
    $('[data-alt-save]', box).onclick = async () => { await api('team-image/' + cur.id, 'PUT', { alt: alt() }); toast('Alt-Text gespeichert'); };
    if ($('[data-reset]', box)) $('[data-reset]', box).onclick = async () => {
      if (!confirmBox('Eigenes Bild entfernen und wieder das Standardbild zeigen?')) return;
      await api('team-image/' + cur.id, 'DELETE'); toast('Standardbild wiederhergestellt'); route();
    };
  }
};
