/* ====================================================================== */
App.pages.dashboard = async (view) => {
  const [dash] = await Promise.all([api('dashboard'), loadAll('opponents', 'sponsors', 'posts', 'assignments', 'media_team', 'players', 'games'),
    load('magazines', true), load('magazine_pages', true)]);
  const s = App.settings;
  const me = App.me;
  const next = dash.next_games[0];
  const opp = next ? byId(App.cache.opponents, next.opponent_id) : null;
  const tasks = mediaTasks();
  const medien = can('medien'), mw = can('medien', 2), vw = can('verein', 2);

  const checks = !medien ? '' : dash.next_games.slice(0, 3).map(g => {
    const o = byId(App.cache.opponents, g.opponent_id);
    const posts = App.cache.posts.filter(p => p.game_id == g.id);
    const has = t => posts.find(p => p.type === t);
    const asg = App.cache.assignments.filter(a => a.game_id == g.id && a.member_id);
    const items = [
      { label: 'Gameday-Ankündigung', ok: has('Gameday'), act: `<button class="btn sm pp" onclick="planPost({type:'Gameday',game_id:${g.id}})">Planen</button>` },
      { label: 'Media Team eingeteilt', ok: tasks.length && asg.length >= tasks.length, part: asg.length > 0, act: `<button class="btn sm pp" onclick="assignGame(${g.id})">Einteilen</button>`, extra: `${asg.length}/${tasks.length}` },
      { label: 'Spieltagssponsor', ok: !!g.sponsor_id, act: `<button class="btn sm vw" onclick="editGame(${g.id})">Eintragen</button>` },
      { label: 'Endstand-Post', ok: has('Ergebnis'), act: `<button class="btn sm pp" onclick="planPost({type:'Ergebnis',game_id:${g.id}})">Planen</button>`, later: true },
    ];
    return `<div class="card"><h3>${fmtDate(g.date, true)} ${Number(g.home) ? 'vs' : '@'} ${esc(o?.name || 'TBA')}</h3>
      ${items.map(i => `<div class="check-row"><span class="dot ${i.ok ? 'ok' : i.part ? 'warn' : i.later ? '' : 'red'}"></span><span style="flex:1">${i.label}${i.extra ? ` <span class="muted small">${i.extra}</span>` : ''}</span>${i.ok ? '<span class="badge ok">erledigt</span>' : i.act}</div>`).join('')}
    </div>`;
  }).join('');

  // Hinweise je nach Rechten
  const notes = [];
  const lg = dash.last_game;
  if (vw && lg && (lg.score_us === null || lg.score_us === '')) notes.push(`Ergebnis vom ${fmtDate(lg.date)} fehlt noch. <button class="vw btn sm" onclick="editGame(${lg.id})">Eintragen</button>`);
  if (mw && lg && !App.cache.posts.find(p => p.game_id == lg.id && p.type === 'Ergebnis')) notes.push(`Kein Endstand-Post für das Spiel am ${fmtDate(lg.date)}. <button class="pp btn sm" onclick="planPost({type:'Ergebnis',game_id:${lg.id}})">Planen</button>`);
  if (vw && dash.counts.no_consent) notes.push(`${dash.counts.no_consent} aktive Personen ohne hinterlegte Foto-Einwilligung. <a class="btn sm" href="#/players">Ansehen</a>`);
  if (medien) App.cache.posts.filter(p => ['fehler', 'teilweise', 'verpasst'].includes(p.publish_state) && (p.date || '') >= addDays(todayStr(), -7))
    .forEach(p => notes.push(`Automatisch posten hat bei „${esc(p.title || p.type || 'Post')}“ nicht geklappt: ${esc(p.publish_log || p.publish_state)} <a class="btn sm" href="#/autopost">Auto-Posting</a>`));
  if (medien) dash.overdue_posts.forEach(p => notes.push(`Post „${esc(p.title || p.type)}“ war für ${fmtDate(p.date)} geplant und ist noch nicht als gepostet markiert. <a class="btn sm" href="#/posts">Postplan</a>`));
  if (mw) App.cache.sponsors.filter(sp => Number(sp.active) && Number(sp.posts_agreed)).forEach(sp => {
    const done = App.cache.posts.filter(p => p.sponsor_id == sp.id && p.status === 'Gepostet').length;
    if (done < Number(sp.posts_agreed)) notes.push(`${esc(sp.name)}: ${done} von ${sp.posts_agreed} vereinbarten Posts erledigt. <button class="pp btn sm" onclick="planPost({type:'Sponsor',sponsor_id:${sp.id}})">Planen</button>`);
  });
  if (medien) App.cache.magazines.filter(m => m.status !== 'Fertig' && m.deadline).forEach(m => {
    const d = daysUntil(m.deadline), open = magChecklist(m).filter(c => !c[1]).map(c => c[0]);
    if (d <= 14 && open.length) notes.push(`Stadionheft „${esc(magLabel(m))}“: ${d < 0 ? 'Redaktionsschluss war am' : 'Redaktionsschluss am'} ${fmtDate(m.deadline)}, noch offen: ${esc(open.join(', '))}. <a class="btn sm" href="#/magazine/${m.id}">Ansehen</a>`);
  });
  if (can('mitglieder')) {
    const reqs = (await load('contact_requests', true)).filter(r => r.status === 'Neu').length;
    if (reqs) notes.push(`${reqs} neue Anfrage${reqs > 1 ? 'n' : ''} über die Webseite. <a class="btn sm" href="#/contacts">Ansehen</a>`);
  }
  if (dash.finance?.open) notes.push(`${dash.finance.open} offene Buchung(en) in den Finanzen. <a class="btn sm" href="#/finance">Ansehen</a>`);
  if (me.member_id === null && !me.is_admin) notes.push('Dein Zugang ist noch keinem Mitgliedsprofil zugeordnet. Das macht der Admin unter Konten.');

  const team = [
    ['Aktive Spieler', dash.counts.players], ['Coaches &amp; Staff', dash.counts.staff],
    ['Aktive Sponsoren', dash.counts.sponsors],
    dash.counts.members !== undefined ? ['Mitglieder (aktiv)', dash.counts.members] : null,
    dash.counts.posts_done !== undefined ? ['Gepostete Beiträge', dash.counts.posts_done] : null,
  ].filter(Boolean);

  setTimeout(() => dashMailTasks($('#dashTasks')), 0);
  // Wartungsmodus an: Hinweis oben (nur mit Recht Wartung, kommt nach dem Aufbau der Seite)
  if (can('wartung')) api('maintenance').then(m => {
    const box = $('#dashMaint'); if (!box || !m.on) return;
    box.innerHTML = `<div class="card maint-note"><b>Wartungsmodus ist an.</b> Besucher sehen statt der Webseite die Wartungsseite.
      <a class="btn sm" href="#/wartung">Wartungsmodus</a></div>`;
  }).catch(() => {});

  // Übersicht aus Widgets (5.16): welche, in welcher Reihenfolge und wie breit, legt jede Person unter „Anpassen“ fest (users.dash_layout)
  const first = esc((me.display_name || me.username).split(' ')[0]);
  const today = todayStr(), dow = (new Date(today + 'T12:00:00').getDay() + 6) % 7, monday = addDays(today, -dow);
  const week = [0, 1, 2, 3, 4, 5, 6].map(i => addDays(monday, i));
  const WD = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
  const postsOn = d => App.cache.posts.filter(p => p.date === d);
  const weekPosts = week.reduce((n, d) => n + postsOn(d).length, 0);
  const season = s.season || '';
  const sg = App.cache.games.filter(g => !season || String(g.season || '') === String(season));
  const played = sg.filter(g => g.score_us !== null && g.score_us !== '' && g.score_us !== undefined).length;
  const nextChk = dash.next_games[0];
  const chkItems = nextChk ? [
    !!App.cache.posts.find(p => p.game_id == nextChk.id && p.type === 'Gameday'),
    (() => { const asg = App.cache.assignments.filter(x => x.game_id == nextChk.id && x.member_id).length; return tasks.length && asg >= tasks.length; })(),
    !!nextChk.sponsor_id,
  ] : [];
  const chkDone = chkItems.filter(Boolean).length;
  const days = next ? daysUntil(next.date) : null;
  const oppName = g => esc(byId(App.cache.opponents, g.opponent_id)?.name || 'TBA');
  const rows = list => list.map(([l, v, st]) => `<div class="sum-row"><span>${l}</span><b${st ? ` style="${st}"` : ''}>${v}</b></div>`).join('');
  const num = (n, l) => `<div class="dash-num"><b>${n}</b><span>${l}</span></div>`;
  const none = t => `<div class="empty-s">${t}</div>`;
  const loading = '<p class="muted small">Lädt ...</p>';
  const inDays = d => d === 0 ? 'heute' : d === 1 ? 'morgen' : `in ${d} Tagen`;
  const agendaItems = d => [
    ...App.cache.games.filter(g => g.date === d).map(g => `<a class="ev game" href="#/games" title="${Number(g.home) ? 'Heimspiel' : 'Auswärts'}: ${oppName(g)}">${g.time ? g.time + ' ' : ''}${Number(g.home) ? 'vs' : '@'} ${oppName(g)}</a>`),
    ...(medien ? postsOn(d).slice(0, 3).map(p => `<a class="ev" href="#/posts" title="${esc(p.title || p.type || 'Post')}">${p.time ? p.time + ' ' : ''}${esc(p.title || p.type || 'Post')}</a>`) : []),
  ].join('');

  // Alle Widgets (5.19 schlicht): t = Titel, link = [Adresse, Text] oben rechts, body() = Inhalt, later(el) füllt nach, ok() = darf die Person es sehen
  const W = {
    game: { t: 'Nächstes Spiel', w: 1, cls: 'dash-game', link: ['#/games', 'Spielplan'], body: () => next
      ? `<b class="t">${esc(s.club_short || 'Amisia')} ${Number(next.home) ? 'vs' : '@'} ${esc(opp?.name || 'TBA')}</b>
        <div class="muted small">${fmtDate(next.date, true)}${next.time ? ', ' + next.time + ' Uhr' : ''}${next.location || Number(next.home) ? ' | ' + esc(next.location || s.home_location || '') : ''}</div>
        <div style="margin:8px 0"><span class="badge ${days <= 7 ? 'red' : ''}">${Number(next.home) ? 'Heimspiel' : 'Auswärtsspiel'} ${inDays(days)}</span></div>
        ${medien ? `<div class="btn-row"><button class="btn sm" onclick="copyGameInfo(${next.id})">Infos kopieren</button>${mw ? `<button class="pp btn sm" onclick="planPost({type:'Gameday',game_id:${next.id}})">Gameday-Post</button>` : ''}</div>` : ''}`
      : `${none('Kein Spiel geplant.')}${vw ? '<button class="vw btn sm" onclick="editGame()">Spiel anlegen</button>' : ''}` },
    posts: { t: 'Postplan der Woche', w: 1, ok: () => medien, link: ['#/posts', 'Postplan'], body: () => `${num(weekPosts, weekPosts === 1 ? 'Post diese Woche' : 'Posts diese Woche')}
      ${rows(week.map((d, i) => [`${WD[i]} ${d.slice(8, 10)}.${d === today ? ' <span class="badge red">heute</span>' : ''}`, postsOn(d).length || '<span class="muted">-</span>']))}` },
    countdown: { t: 'Bis zum Anstoß', w: 1, link: ['#/games', 'Spielplan'], body: () => next
      ? `${num(days === 0 ? 'Heute' : days, days === 0 ? 'ist Gameday' : days === 1 ? 'Tag' : 'Tage')}${rows([['Datum', fmtDate(next.date, true)], ['Anstoß', next.time ? next.time + ' Uhr' : '-'], ['Gegner', esc(opp?.name || 'TBA')]])}`
      : none('Kein Spiel geplant.') },
    prep: { t: 'Vorbereitung und Hinweise', w: 1, tall: true, body: () => `
      ${chkItems.length ? [['Gameday-Post', chkItems[0]], ['Media Team eingeteilt', chkItems[1]], ['Spielsponsor', chkItems[2]]].map(([l, okk]) => `<div class="dash-chk"><span>${l}</span><span class="${okk ? 'ok' : 'no'}">${okk ? 'erledigt' : 'offen'}</span></div>`).join('') : ''}
      ${notes.length ? notes.map(n => `<div class="dash-hint"><span class="dn-dot"></span><div>${n}</div></div>`).join('') : '<div class="dash-hint"><span class="dn-dot ok"></span><div>Keine offenen Hinweise.</div></div>'}` },
    team: { t: 'Team', w: 1, link: ['#/players', 'Kader'], body: () => rows(team) },
    finance: { t: 'Finanzen', w: 1, ok: () => !!dash.finance, link: ['#/finance', 'Buchungen'], body: () => rows([['Einnahmen ' + dash.finance.year, eur(dash.finance.income)], ['Ausgaben ' + dash.finance.year, eur(dash.finance.expense)],
        ['Saldo', eur(dash.finance.income - dash.finance.expense), `color:${dash.finance.income - dash.finance.expense < 0 ? 'var(--red-text)' : 'var(--ok)'}`],
        ['Offene Buchungen', dash.finance.open]]) },
    calendar: { t: `Diese Woche <span>${fmtDate(monday)} bis ${fmtDate(week[6])}</span>`, name: 'Wochenkalender', w: 2, cls: 'dash-cal', link: medien ? ['#/posts', 'Postplan'] : ['#/games', 'Spielplan'], body: () =>
      `<div class="dash-agenda">${week.map((d, i) => `<div class="ad${d === today ? ' today' : ''}"><div class="ad-d">${WD[i]} ${d.slice(8, 10)}.${d === today ? ' heute' : ''}</div>${agendaItems(d)}</div>`).join('')}</div>` },
    games: { t: 'Nächste Spiele', w: 1, link: ['#/games', 'Spielplan'], body: () => dash.next_games.length
      ? `<div class="list">${dash.next_games.slice(0, 5).map(g => `<div class="list-item">${dateBox(g.date)}<div class="grow"><b>${Number(g.home) ? 'vs' : '@'} ${oppName(g)}</b><div class="muted small">${g.time ? 'Anstoß ' + g.time + ' Uhr' : ''}</div></div></div>`).join('')}</div>` : none('Keine Spiele geplant.') },
    upcoming: { t: 'Anstehende Posts', w: 1, ok: () => medien, link: ['#/posts', 'Postplan'], body: () => dash.upcoming_posts.length
      ? `<div class="list">${dash.upcoming_posts.slice(0, 6).map(p => `<div class="list-item">${dateBox(p.date)}<div class="grow"><b>${esc(p.title || p.type)}</b><div class="muted small">${esc(p.type || '')}${p.time ? ' | ' + p.time + ' Uhr' : ''}</div></div>${statusBadge(p.status)}</div>`).join('')}</div>`
      : `${none('Nichts geplant.')}${mw ? '<button class="pp btn sm" onclick="planPost()">+ Post planen</button>' : ''}` },
    checks: { t: 'Content-Check der nächsten Spiele', w: 2, ok: () => !!checks, body: () => `<div class="grid g3 dash-checks" style="margin-top:8px">${checks}</div>` },
    contacts: { t: 'Neue Anfragen', w: 1, ok: () => can('mitglieder'), link: ['#/contacts', 'Anfragen'], body: () => `<div data-fill>${loading}</div>`,
      later: async el => { const r = (await load('contact_requests', true)).filter(x => x.status === 'Neu');
        el.innerHTML = num(r.length, 'neu über die Webseite') + rows(r.slice(0, 4).map(x => [esc(x.name || ''), `<span class="muted small">${esc(x.source || '')}</span>`])); } },
    mail: { t: 'Postfach', w: 1, ok: () => can('postfach|ownmail'), link: ['#/postfach', 'Öffnen'], body: () => `<div data-fill>${loading}</div>`,
      later: async el => { const boxes = [...(can('postfach') ? [['info', 'Vereinspostfach']] : []), ...(me.mail_boxes || []).map(b => [b.key, b.address])];
        const res = await Promise.all(boxes.map(([k, l]) => api('postfach/status' + (k === 'info' ? '' : '?box=' + k)).then(r => [l, Number(r.unseen) || 0]).catch(() => [l, '?'])));
        el.innerHTML = num(res.reduce((n, [, v]) => n + (Number(v) || 0), 0), 'ungelesen') + rows(res.map(([l, v]) => [esc(l), v])); } },
    newsletter: { t: 'Newsletter', w: 1, ok: () => medien, link: ['#/newsletter', 'Newsletter'], body: () => `<div data-fill>${loading}</div>`,
      later: async el => { const d = await api('newsletter'); const act = d.subscribers.filter(x => x.status === 'aktiv').length, last = d.issues.find(i => i.status === 'gesendet');
        el.innerHTML = num(act, 'aktive Abonnenten') + rows([['Unbestätigt', d.subscribers.filter(x => x.status === 'offen').length], ['Entwürfe', d.issues.filter(i => i.status === 'entwurf').length]])
          + (last ? `<p class="muted small" style="margin:8px 0 0">Zuletzt: ${esc(last.subject)} (${fmtDate((last.sent_at || '').slice(0, 10))}, ${last.sent_count} erreicht)</p>` : ''); } },
    cards: { t: 'Dauerkarte', w: 1, ok: () => can('finanzen'), link: ['#/cards', 'Karten'], body: () => `<div data-fill>${loading}</div>`,
      later: async el => { const c = await load('supporter_cards', true); const paid = c.filter(x => Number(x.paid)).length;
        el.innerHTML = num(c.length, 'Karten insgesamt') + rows([['Bezahlt', paid], ['Offen', c.length - paid]]); } },
    sponsors: { t: 'Sponsoren', w: 1, link: ['#/sponsors', 'Alle'], body: () => { const sp = App.cache.sponsors.filter(x => Number(x.active));
      return `${num(sp.length, 'aktiv')}<div class="dash-logos">${sp.slice(0, 8).map(x => x.logo ? `<img src="${esc(x.logo)}" alt="${esc(x.name)}" title="${esc(x.name)}">` : `<span title="${esc(x.name)}">${esc((x.name || '?').slice(0, 2))}</span>`).join('')}</div>`; } },
    quick: { t: 'Schnellzugriff', w: 1, body: () => `<div class="dash-quick">${tabChoices().filter(c => c.page !== 'dashboard').slice(0, 12).map(c => `<a href="${c.href}">${tabIcon(c.icon)}<span>${esc(c.full)}</span></a>`).join('')}</div>` },
  };
  Object.values(W).forEach(x => { x.name = x.name || x.t; });
  const DEFAULT = ['game', 'prep', 'mail', 'team', 'finance', 'upcoming', 'sponsors', 'calendar'];
  const avail = k => W[k] && (!W[k].ok || W[k].ok());
  const layout = (Array.isArray(me.dash_layout) && me.dash_layout.length ? me.dash_layout : DEFAULT.filter(k => W[k]).map(k => ({ k, w: W[k].w }))).filter(x => avail(x.k));
  const kpis = [
    ['Spieler aktiv', dash.counts.players, '#/players'],
    ['Coaches & Staff', dash.counts.staff, '#/players'],
    dash.counts.members !== undefined ? ['Mitglieder', dash.counts.members, '#/members'] : null,
    ['Sponsoren', dash.counts.sponsors, '#/sponsors'],
    medien ? ['Posts diese Woche', weekPosts, '#/posts'] : null,
    next ? ['Bis zum Spiel', days === 0 ? 'heute' : `${days} ${days === 1 ? 'Tag' : 'Tage'}`, '#/games'] : null,
    ['Hinweise', notes.length, '#/', notes.length ? 'hot' : ''],
  ].filter(Boolean);

  view.innerHTML = `
    <div id="dashMaint"></div>
    <div class="dash-head"><div><h1>Übersicht</h1><div class="muted small">${fmtDate(dash.today, true)} | ${first}${me.groups?.length ? ' | ' + esc(me.groups.join(', ')) : ''}</div></div>
      <div class="btn-row">${mw ? '<button class="pp btn primary" onclick="planPost()">+ Post planen</button>' : ''}${vw ? '<button class="vw btn" onclick="editGame()">+ Spiel</button>' : ''}<button class="btn keep" id="dashEdit">Anpassen</button></div></div>
    <section class="dash-kpis">${kpis.map(([l, v, href, cls]) => `<a href="${href}"><small>${esc(l)}</small><b class="${cls || ''}">${v ?? 0}</b></a>`).join('')}</section>
    <div id="dashTasks"></div>
    <section class="dash-grid">${layout.map(x => `<article class="card dash-w ${W[x.k].cls || ''}${x.w === 2 ? ' w2' : ''}${W[x.k].tall ? ' tall' : ''}" data-w="${x.k}">
        <div class="dash-wh"><h3>${W[x.k].t}</h3>${W[x.k].link ? `<a href="${W[x.k].link[0]}">${W[x.k].link[1]}</a>` : ''}</div><div class="dash-wb">${W[x.k].body()}</div></article>`).join('')
      || '<div class="card muted">Keine Widgets ausgewählt. Über „Anpassen“ welche hinzufügen.</div>'}</section>`;
  layout.forEach(x => { const box = $(`[data-w="${x.k}"] [data-fill]`, view); if (W[x.k].later && box) W[x.k].later(box).catch(() => { box.innerHTML = '<p class="muted small">Gerade nicht verfügbar.</p>'; }); });

  $('#dashEdit').onclick = () => {   // Widgets an und aus, Reihenfolge, Breite; gespeichert im eigenen Konto
    let items = [...layout.map(x => ({ k: x.k, w: x.w, on: true })), ...Object.keys(W).filter(k => avail(k) && !layout.some(x => x.k === k)).map(k => ({ k, w: W[k].w, on: false }))];
    const draw = () => {
      openModal(`<h2>Übersicht anpassen</h2>
        <p class="muted small">Haken = Widget anzeigen, Pfeile = Reihenfolge, Breite = eine oder zwei Spalten. Es erscheinen nur Widgets, für die du Rechte hast. Gilt für dein Konto auf allen Geräten.</p>
        <div class="list dash-edit">${items.map((x, i) => `<div class="list-item${x.on ? '' : ' off'}">
          <label class="check grow"><input type="checkbox" data-on="${i}" ${x.on ? 'checked' : ''}> ${esc(W[x.k].name)}</label>
          <select class="input" data-wd="${i}" style="width:auto" aria-label="Breite von ${esc(W[x.k].name)}"><option value="1" ${x.w !== 2 ? 'selected' : ''}>Normal</option><option value="2" ${x.w === 2 ? 'selected' : ''}>Breit</option></select>
          <button class="btn sm" data-mv="${i}" data-d="-1" ${i ? '' : 'disabled'} aria-label="nach oben">↑</button><button class="btn sm" data-mv="${i}" data-d="1" ${i < items.length - 1 ? '' : 'disabled'} aria-label="nach unten">↓</button></div>`).join('')}</div>
        <div class="modal-foot"><div><button class="btn ghost" id="de_reset">Standard</button></div><div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="de_save">Speichern</button></div></div>`);
      $$('[data-on]').forEach(c => c.onchange = () => { items[c.dataset.on].on = c.checked; c.closest('.list-item').classList.toggle('off', !c.checked); });
      $$('[data-wd]').forEach(c => c.onchange = () => { items[c.dataset.wd].w = Number(c.value); });
      $$('[data-mv]').forEach(b => b.onclick = () => { const i = Number(b.dataset.mv), j = i + Number(b.dataset.d); [items[i], items[j]] = [items[j], items[i]]; draw(); });
      const save = async widgets => { try { const r = await api('dashlayout', 'PUT', { widgets }); App.me.dash_layout = r.dash_layout; closeModal(); toast('Übersicht gespeichert'); route(); } catch (e) { alert(e.message); } };
      $('#de_save').onclick = () => save(items.filter(x => x.on).map(({ k, w }) => ({ k, w })));
      $('#de_reset').onclick = () => save(null);
    };
    draw();
  };
};

