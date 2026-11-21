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
  const pills = [
    medien ? ['Postplan', `${weekPosts} diese Woche`, 'b1'] : null,
    nextChk ? ['Nächstes Spiel', `${chkDone} von ${chkItems.length} vorbereitet`, 'b2'] : null,
    sg.length ? ['Saison', `${played} von ${sg.length} gespielt`, 'b3'] : null,
    ['Hinweise', `${notes.length} offen`, 'b4'],
  ].filter(Boolean);
  const bigs = [
    ['team', dash.counts.players, 'Spieler'],
    dash.counts.members !== undefined ? ['team', dash.counts.members, 'Mitglieder'] : ['user', dash.counts.staff, 'Coaches & Staff'],
    ['star', dash.counts.sponsors, 'Sponsoren'],
  ];
  const days = next ? daysUntil(next.date) : null;
  const ringPct = days === null ? 0 : Math.max(4, Math.min(100, Math.round((14 - Math.min(days, 14)) / 14 * 100)));
  const arrow = '<svg viewBox="0 0 24 24"><path d="M7 17 17 7M9 7h8v8"/></svg>';
  const go = (href, label) => `<a class="dash-go" href="${href}" aria-label="${label}">${arrow}</a>`;
  const maxDay = Math.max(1, ...week.map(d => postsOn(d).length));
  const oppName = g => esc(byId(App.cache.opponents, g.opponent_id)?.name || 'TBA');
  const calItems = d => [
    ...App.cache.games.filter(g => g.date === d).map(g => `<a class="dc-ev red" href="#/games"><b>${Number(g.home) ? 'Heimspiel' : 'Auswärts'}</b><small>${oppName(g)}${g.time ? ', ' + g.time : ''}</small></a>`),
    ...(medien ? postsOn(d).slice(0, 3).map((p, i) => `<a class="dc-ev ${i % 2 ? 'light' : 'dark'}" href="#/posts"><b>${esc(p.title || p.type || 'Post')}</b><small>${esc(p.type || '')}${p.time ? ', ' + p.time : ''}</small></a>`) : []),
  ].join('');
  const rows = list => list.map(([l, v, st]) => `<div class="sum-row"><span>${l}</span><b${st ? ` style="${st}"` : ''}>${v}</b></div>`).join('');
  const loading = '<p class="muted small">Lädt ...</p>';

  // Alle Widgets: html() baut den Inhalt, later(el) füllt Daten nach, die erst geladen werden; ok() = darf die Person es sehen
  const W = {
    game: { t: 'Nächstes Spiel', w: 1, cls: 'dash-photo', html: () => `<img src="/web/assets/img/spiel-960.webp" alt="" loading="lazy">
      ${next ? `<span class="dash-kick">${Number(next.home) ? 'Nächstes Heimspiel' : 'Nächstes Auswärtsspiel'}</span>
        <div class="dash-ph-in"><div><b>${esc(s.club_short || 'Amisia')} ${Number(next.home) ? 'vs' : '@'} ${esc(opp?.name || 'TBA')}</b>
          <small>${fmtDate(next.date, true)}${next.time ? ', ' + next.time + ' Uhr' : ''}${next.location || Number(next.home) ? ' | ' + esc(next.location || s.home_location || '') : ''}</small>
          ${medien ? `<div class="btn-row" style="margin-top:10px"><button class="btn sm" onclick="copyGameInfo(${next.id})">Infos kopieren</button>${mw ? `<button class="pp btn sm" onclick="planPost({type:'Gameday',game_id:${next.id}})">Gameday-Post</button>` : ''}</div>` : ''}</div>
          <span class="dash-tag">${days === 0 ? 'Heute' : days === 1 ? 'Morgen' : `in ${days} Tagen`}</span></div>`
        : `<div class="dash-ph-in"><div><b>Kein Spiel geplant</b><small>Die Termine stehen im Spielplan.</small></div>${vw ? '<button class="vw btn sm" onclick="editGame()">Spiel anlegen</button>' : ''}</div>`}` },
    posts: { t: 'Postplan der Woche', w: 1, ok: () => medien, html: () => `<h3>Postplan</h3>${go('#/posts', 'Zum Postplan')}
      <div class="dash-big">${weekPosts} Post${weekPosts === 1 ? '' : 's'}</div><div class="muted small">diese Woche geplant</div>
      <div class="bars">${week.map((d, i) => { const n = postsOn(d).length; return `<i title="${fmtDate(d, true)}: ${n}">${d === today && n ? `<em>${n}</em>` : ''}<span class="${d === today ? 'hot' : n ? '' : 'dim'}" style="height:${Math.max(8, Math.round(n / maxDay * 100))}%"></span>${WD[i]}</i>`; }).join('')}</div>` },
    countdown: { t: 'Bis zum Anstoß', w: 1, html: () => `<h3>Bis zum Anstoß</h3>${go('#/games', 'Zum Spielplan')}
      <div class="dash-ring" style="--p:${ringPct}%"><div><b>${days === null ? '-' : days === 0 ? 'Heute' : days}</b><small>${days === null ? 'kein Spiel' : days === 0 ? 'Gameday' : days === 1 ? 'Tag' : 'Tage'}</small></div></div>
      <div class="muted small" style="text-align:center">${next ? fmtDate(next.date, true) : 'Spielplan pflegen'}</div>` },
    prep: { t: 'Vorbereitung und Hinweise', w: 1, tall: true, html: () => `<div class="dash-tt"><h3>Vorbereitung</h3><b>${chkItems.length ? Math.round(chkDone / chkItems.length * 100) : 100} %</b></div>
      ${chkItems.length ? `<div class="dash-seg"><div>Gameday-Post<span class="${chkItems[0] ? 's1' : 's3'}"></span></div><div>Media Team<span class="${chkItems[1] ? 's1' : 's3'}"></span></div><div>Sponsor<span class="${chkItems[2] ? 's1' : 's3'}"></span></div></div>` : ''}
      <div class="dash-dark"><div class="dash-dh"><span>Hinweise</span><b>${notes.length}</b></div>
        ${notes.length ? notes.map(n => `<div class="dash-note"><span class="dn-dot"></span><div>${n}</div></div>`).join('') : '<div class="dash-note"><span class="dn-dot ok"></span><div>Alles im grünen Bereich.</div></div>'}</div>` },
    team: { t: 'Team', w: 1, cls: 'dash-acc', html: () => `<h3>Team</h3>${rows(team)}` },
    finance: { t: 'Finanzen', w: 1, cls: 'dash-acc', ok: () => !!dash.finance, html: () => `<h3>Finanzen ${dash.finance.year}</h3>${go('#/finance', 'Zu den Buchungen')}
      ${rows([['Einnahmen', eur(dash.finance.income)], ['Ausgaben', eur(dash.finance.expense)],
        ['Saldo', eur(dash.finance.income - dash.finance.expense), `color:${dash.finance.income - dash.finance.expense < 0 ? 'var(--red-text)' : 'var(--ok)'}`],
        ['Offene Buchungen', dash.finance.open]])}` },
    calendar: { t: 'Wochenkalender', w: 2, cls: 'dash-cal', html: () => `<div class="dc-h"><a class="dc-nav" href="#/games">Spielplan</a><b>${fmtDate(monday)} bis ${fmtDate(week[6])}</b>${medien ? '<a class="dc-nav" href="#/posts">Postplan</a>' : '<span></span>'}</div>
      <div class="dc-week">${week.map((d, i) => `<div class="dc-day${d === today ? ' today' : ''}"><div class="dc-d">${WD[i]}<b>${d.slice(8, 10)}</b></div>${calItems(d)}</div>`).join('')}</div>` },
    games: { t: 'Nächste Spiele', w: 1, html: () => `<h3>Nächste Spiele</h3>${go('#/games', 'Zum Spielplan')}
      ${dash.next_games.length ? `<div class="list" style="margin-top:12px">${dash.next_games.slice(0, 5).map(g => `<div class="list-item">${dateBox(g.date)}<div class="grow"><b>${Number(g.home) ? 'vs' : '@'} ${oppName(g)}</b><div class="muted small">${g.time ? 'Anstoß ' + g.time + ' Uhr' : ''}</div></div></div>`).join('')}</div>` : '<p class="muted">Keine Spiele geplant.</p>'}` },
    upcoming: { t: 'Anstehende Posts', w: 1, ok: () => medien, html: () => `<h3>Anstehende Posts</h3>${go('#/posts', 'Zum Postplan')}
      ${dash.upcoming_posts.length ? `<div class="list" style="margin-top:12px">${dash.upcoming_posts.slice(0, 6).map(p => `<div class="list-item">${dateBox(p.date)}<div class="grow"><b>${esc(p.title || p.type)}</b><div class="muted small">${esc(p.type || '')}${p.time ? ' | ' + p.time + ' Uhr' : ''}</div></div>${statusBadge(p.status)}</div>`).join('')}</div>` : '<p class="muted">Nichts geplant.</p>'}` },
    checks: { t: 'Content-Check der nächsten Spiele', w: 2, ok: () => !!checks, html: () => `<h3>Content-Check</h3><div class="grid g3 dash-checks" style="margin-top:12px">${checks}</div>` },
    contacts: { t: 'Neue Anfragen', w: 1, ok: () => can('mitglieder'), html: () => `<h3>Anfragen</h3>${go('#/contacts', 'Zu den Anfragen')}<div data-fill>${loading}</div>`,
      later: async el => { const r = (await load('contact_requests', true)).filter(x => x.status === 'Neu');
        el.innerHTML = `<div class="dash-big">${r.length}</div><div class="muted small">neue über die Webseite</div>${r.slice(0, 4).map(x => `<div class="sum-row"><span>${esc(x.name || '')}</span><span class="muted small">${esc(x.source || '')}</span></div>`).join('')}`; } },
    mail: { t: 'Postfach', w: 1, ok: () => can('postfach|ownmail'), html: () => `<h3>Postfach</h3>${go('#/postfach', 'Zum Postfach')}<div data-fill>${loading}</div>`,
      later: async el => { const boxes = [...(can('postfach') ? [['info', 'Vereinspostfach']] : []), ...(me.mail_boxes || []).map(b => [b.key, b.address])];
        const res = await Promise.all(boxes.map(([k, l]) => api('postfach/status' + (k === 'info' ? '' : '?box=' + k)).then(r => [l, Number(r.unseen) || 0]).catch(() => [l, '?'])));
        el.innerHTML = `<div class="dash-big">${res.reduce((n, [, v]) => n + (Number(v) || 0), 0)}</div><div class="muted small">ungelesene Mails</div>${rows(res.map(([l, v]) => [esc(l), v]))}`; } },
    newsletter: { t: 'Newsletter', w: 1, ok: () => medien, html: () => `<h3>Newsletter</h3>${go('#/newsletter', 'Zum Newsletter')}<div data-fill>${loading}</div>`,
      later: async el => { const d = await api('newsletter'); const act = d.subscribers.filter(x => x.status === 'aktiv').length, last = d.issues.find(i => i.status === 'gesendet');
        el.innerHTML = `<div class="dash-big">${act}</div><div class="muted small">aktive Abonnenten</div>${rows([['Unbestätigt', d.subscribers.filter(x => x.status === 'offen').length], ['Entwürfe', d.issues.filter(i => i.status === 'entwurf').length]])}
          ${last ? `<p class="muted small" style="margin-top:8px">Zuletzt: ${esc(last.subject)} (${fmtDate((last.sent_at || '').slice(0, 10))}, ${last.sent_count} erreicht)</p>` : ''}`; } },
    cards: { t: 'Dauerkarte', w: 1, ok: () => can('finanzen'), html: () => `<h3>Dauerkarte</h3>${go('#/cards', 'Zur Dauerkarte')}<div data-fill>${loading}</div>`,
      later: async el => { const c = await load('supporter_cards', true); const paid = c.filter(x => Number(x.paid)).length;
        el.innerHTML = `<div class="dash-big">${c.length}</div><div class="muted small">Karten insgesamt</div>${rows([['Bezahlt', paid], ['Offen', c.length - paid]])}`; } },
    sponsors: { t: 'Sponsoren', w: 1, html: () => { const sp = App.cache.sponsors.filter(x => Number(x.active));
      return `<h3>Sponsoren</h3>${go('#/sponsors', 'Zu den Sponsoren')}<div class="dash-big">${sp.length}</div><div class="muted small">aktiv</div>
        <div class="dash-logos">${sp.slice(0, 8).map(x => x.logo ? `<img src="${esc(x.logo)}" alt="${esc(x.name)}" title="${esc(x.name)}">` : `<span title="${esc(x.name)}">${esc((x.name || '?').slice(0, 2))}</span>`).join('')}</div>`; } },
    quick: { t: 'Schnellzugriff', w: 1, html: () => `<h3>Schnellzugriff</h3><div class="dash-quick">${tabChoices().filter(c => c.page !== 'dashboard').slice(0, 12).map(c => `<a href="${c.href}">${tabIcon(c.icon)}<span>${esc(c.full)}</span></a>`).join('')}</div>` },
  };
  const DEFAULT = ['game', 'posts', 'countdown', 'prep', 'team', 'finance', 'calendar'];
  const avail = k => W[k] && (!W[k].ok || W[k].ok());
  const layout = (Array.isArray(me.dash_layout) && me.dash_layout.length ? me.dash_layout : DEFAULT.map(k => ({ k, w: W[k].w }))).filter(x => avail(x.k));

  view.innerHTML = `
    <div id="dashMaint"></div><div id="dashTasks"></div>
    <section class="dash-hello">
      <div><h1>Willkommen, ${first}</h1>
        <p class="muted">${fmtDate(dash.today, true)}${me.groups?.length ? ' | ' + esc(me.groups.join(', ')) : ''}</p>
        <div class="dash-prog">${pills.map(([l, v, c]) => `<div><span>${l}</span><b class="dp ${c}">${v}</b></div>`).join('')}</div></div>
      <div class="dash-stats">${bigs.map(([ic, n, l]) => `<div><span class="ds-ic">${tabIcon(ic)}</span><div><b>${n ?? 0}</b><small>${esc(l)}</small></div></div>`).join('')}</div>
    </section>
    <div class="btn-row" style="margin:-6px 0 16px">${mw ? '<button class="pp btn primary" onclick="planPost()">+ Post planen</button>' : ''}${vw ? '<button class="vw btn" onclick="editGame()">+ Spiel</button>' : ''}
      <button class="btn keep" id="dashEdit" style="margin-left:auto">Anpassen</button></div>
    <section class="dash-grid">${layout.map(x => `<article class="card dash-w ${W[x.k].cls || ''}${x.w === 2 ? ' w2' : ''}${W[x.k].tall ? ' tall' : ''}" data-w="${x.k}">${W[x.k].html()}</article>`).join('')
      || '<div class="card muted">Keine Widgets ausgewählt. Über „Anpassen“ welche hinzufügen.</div>'}</section>`;
  layout.forEach(x => { const box = $(`[data-w="${x.k}"] [data-fill]`, view); if (W[x.k].later && box) W[x.k].later(box).catch(() => { box.innerHTML = '<p class="muted small">Gerade nicht verfügbar.</p>'; }); });

  $('#dashEdit').onclick = () => {   // Widgets an und aus, Reihenfolge, Breite; gespeichert im eigenen Konto
    let items = [...layout.map(x => ({ k: x.k, w: x.w, on: true })), ...Object.keys(W).filter(k => avail(k) && !layout.some(x => x.k === k)).map(k => ({ k, w: W[k].w, on: false }))];
    const draw = () => {
      openModal(`<h2>Übersicht anpassen</h2>
        <p class="muted small">Haken = Widget anzeigen, Pfeile = Reihenfolge, Breite = eine oder zwei Spalten. Es erscheinen nur Widgets, für die du Rechte hast. Gilt für dein Konto auf allen Geräten.</p>
        <div class="list dash-edit">${items.map((x, i) => `<div class="list-item${x.on ? '' : ' off'}">
          <label class="check grow"><input type="checkbox" data-on="${i}" ${x.on ? 'checked' : ''}> ${esc(W[x.k].t)}</label>
          <select class="input" data-wd="${i}" style="width:auto" aria-label="Breite von ${esc(W[x.k].t)}"><option value="1" ${x.w !== 2 ? 'selected' : ''}>Normal</option><option value="2" ${x.w === 2 ? 'selected' : ''}>Breit</option></select>
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

