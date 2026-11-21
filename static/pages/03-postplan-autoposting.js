/* ====================================================================== */
/* Postplan */
App.pages.posts = async (view) => {
  await loadAll('posts', 'games', 'opponents', 'sponsors', 'players');
  let filter = App._postFilter || 'offen';
  const draw = () => {
    App._postFilter = filter;
    let list = [...App.cache.posts].sort((a, b) => ((a.date || '9') + (a.time || '')).localeCompare((b.date || '9') + (b.time || '')));
    if (filter === 'offen') list = list.filter(p => p.status !== 'Gepostet');
    else if (filter !== 'alle') list = list.filter(p => p.status === filter);
    const groups = {};
    list.forEach(p => { const d = parseDate(p.date); const k = d ? `${MON[d.getMonth()]} ${d.getFullYear()}` : 'Ohne Datum'; (groups[k] = groups[k] || []).push(p); });
    view.innerHTML = `
      <div class="page-head"><h1>Postplan<small>${App.cache.posts.length} Beiträge insgesamt</small></h1>
        <div class="btn-row"><button class="btn primary" id="p_new">+ Post planen</button></div></div>
      <div class="toolbar">${['offen', ...POST_STATUS, 'alle'].map(f => `<button class="btn sm ${f === filter ? 'dark' : ''}" data-f="${f}">${f === 'offen' ? 'Offen' : f === 'alle' ? 'Alle' : f}</button>`).join('')}</div>
      ${list.length ? Object.entries(groups).map(([m, ps]) => `<div class="month"><h3>${m}</h3>${ps.map(p => `
        <div class="post-row">
          ${p.image ? `<img src="${esc(p.image)}">` : '<img>'}
          ${dateBox(p.date)}
          <div style="min-width:0"><div class="t">${esc(p.title || p.type || 'Post')}</div><div class="c">${esc((p.caption || '').split('\n')[0])}</div>
            <div class="small muted">${esc(p.type || '')} | ${esc(p.format || 'Feed')}${p.time ? ' | ' + p.time + ' Uhr' : ''} ${publishBadge(p)}</div></div>
          <select class="input" data-st="${p.id}" style="width:auto">${POST_STATUS.map(s => `<option ${s === (p.status || 'Idee') ? 'selected' : ''}>${s}</option>`).join('')}</select>
          <div class="btn-row">
            <button class="btn sm" data-copy="${p.id}" title="Caption kopieren">Caption</button>
            ${p.image ? `<a class="btn sm" href="${esc(p.image)}" download>Bild</a>` : ''}
            <button class="btn sm ghost" data-edit="${p.id}">Bearbeiten</button>
          </div>
        </div>`).join('')}</div>`).join('') : '<div class="card empty">Keine Beiträge in dieser Ansicht.</div>'}`;
    $$('[data-f]').forEach(b => b.onclick = () => { filter = b.dataset.f; draw(); });
    $$('[data-st]').forEach(sel => sel.onchange = async () => { await api('posts/' + sel.dataset.st, 'PUT', { status: sel.value }); invalidate('posts'); await load('posts'); toast('Status: ' + sel.value); draw(); });
    $$('[data-copy]').forEach(b => b.onclick = () => copyText(byId(App.cache.posts, b.dataset.copy).caption || ''));
    $$('[data-edit]').forEach(b => b.onclick = () => planPost(byId(App.cache.posts, b.dataset.edit)));
    $('#p_new').onclick = () => planPost();
  };
  draw();
};

/* ====================================================================== */
/* Auto-Posting: Verbindung zu Facebook/Instagram, Warteschlange, wiederkehrende Storys */
const WEEKDAYS = [1, 2, 3, 4, 5, 6, 7];   // ISO: 1 = Montag
const ruleDays = r => (r.weekdays || '').split(',').filter(Boolean).map(d => WD_S[Number(d) % 7]).join(', ');
const postWhen = p => `${p.date || ''} ${p.time || '00:00'}`;

F.story_rules = () => [
  { key: 'name', label: 'Bezeichnung', placeholder: 'z. B. Training heute', full: true },
  ...WEEKDAYS.map(n => ({ key: 'wd' + n, label: WD[n % 7], type: 'check' })),
  { key: 'time', label: 'Uhrzeit', type: 'time' },
  { key: 'targets', label: 'Posten auf', type: 'select', options: SOCIAL_TARGETS },
  { key: 'image', label: 'Story-Bild aus Canva', type: 'image', full: true, hint: 'Hochformat 1080 x 1920. Für Instagram am besten als JPG exportieren.' },
  { key: 'active', label: 'Aktiv', type: 'check', default: 1 },
  { key: 'valid_from', label: 'Gültig ab', type: 'date' },
  { key: 'valid_until', label: 'Gültig bis', type: 'date', hint: 'z. B. Saisonende oder Beginn der Winterpause' },
  { key: 'notes', label: 'Notizen', type: 'textarea', rows: 2 },
];

function editStoryRule(rec) {
  const r = { ...rec }, days = (r.weekdays || '').split(',');
  WEEKDAYS.forEach(n => { r['wd' + n] = days.includes(String(n)) ? 1 : 0; });
  return editRecord('story_rules', F.story_rules(), r, {
    newTitle: 'Neue Story-Regel', editTitle: 'Story-Regel',
    beforeSave: v => { v.weekdays = WEEKDAYS.filter(n => Number(v['wd' + n])).join(','); WEEKDAYS.forEach(n => delete v['wd' + n]); },
  });
}

const AO_TABS = [['kalender', 'Kalender'], ['online', 'Online'], ['statistik', 'Statistik'], ['einrichtung', 'Einrichtung & Storys']];
const fmtNum = n => n === null || n === undefined ? '-' : Number(n).toLocaleString('de-DE');
const fmtStamp = s => s ? new Date(s).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';

function aoHead(social, tab) {
  return `<div class="page-head"><h1>Auto-Posting<small>${social.connected ? `verbunden mit ${esc(social.page)}${social.instagram ? ' und Instagram @' + esc(social.instagram) : ', ohne Instagram'}` : 'noch nicht verbunden'}</small></h1>
      <div class="btn-row"><a class="btn keep" href="#/posts">Zum Postplan</a></div></div>
    <div class="toolbar">${AO_TABS.map(([k, l]) => `<a class="btn sm ${k === tab ? 'dark' : ''}" href="#/autopost/${k}">${l}</a>`).join('')}</div>`;
}

App.pages.autopost = async (view, args) => {
  const social = await api('social');
  const tab = AO_TABS.some(t => t[0] === args[0]) ? args[0] : 'kalender';
  if (tab === 'einrichtung') return autopostSetup(view, social);
  if (tab !== 'kalender' && !social.connected) {
    view.innerHTML = `${aoHead(social, tab)}<div class="card empty">Es ist noch keine Facebook-Seite verbunden. <a href="#/autopost/einrichtung">Zur Einrichtung</a></div>`;
    return;
  }
  if (tab === 'kalender') return autopostCalendar(view, social);
  if (tab === 'online') return autopostOnline(view, social, false);
  return autopostStats(view, social, args[1] === '7' ? 7 : 28, false);
};

/* Kalender: geplante Posts aus dem Postplan und die wiederkehrenden Storys */
async function autopostCalendar(view, social) {
  await Promise.all([load('posts', true), load('story_rules', true)]);
  const month = App._aoMonth || todayStr().slice(0, 7);
  const [y, m] = month.split('-').map(Number);
  const start = (new Date(y, m - 1, 1).getDay() + 6) % 7, days = new Date(y, m, 0).getDate();
  const pad = n => String(n).padStart(2, '0');
  const cells = [...Array(start).fill(null), ...Array.from({ length: days }, (_, i) => `${y}-${pad(m)}-${pad(i + 1)}`)];
  while (cells.length % 7) cells.push(null);
  const postCls = p => p.publish_state === 'gepostet' || p.status === 'Gepostet' ? 'ok' : ['fehler', 'verpasst', 'teilweise'].includes(p.publish_state) ? 'err' : Number(p.auto_publish) ? 'auto' : 'plan';
  const rulesOn = ds => App.cache.story_rules.filter(r => Number(r.active) && (r.weekdays || '').split(',').includes(String(parseDate(ds).getDay() || 7))
    && (!r.valid_from || ds >= r.valid_from) && (!r.valid_until || ds <= r.valid_until));
  const today = todayStr();
  view.innerHTML = `${aoHead(social, 'kalender')}
    <div class="mag-sec-head"><div class="btn-row"><button class="btn sm" data-mon="-1">‹</button><h2 style="margin:0 6px;min-width:150px;text-align:center">${MON[m - 1]} ${y}</h2><button class="btn sm" data-mon="1">›</button><button class="btn sm ghost" data-mon="0">Heute</button></div>
      <button class="pp btn primary" id="cal_new">+ Post planen</button></div>
    <div class="cal-wrap"><div class="cal">${['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'].map(d => `<div class="cal-h">${d}</div>`).join('')}
      ${cells.map(ds => !ds ? '<div class="cal-d empty"></div>' : `<div class="cal-d ${ds === today ? 'today' : ''} ${ds < today ? 'past' : ''}" data-day="${ds}"><span class="cal-n">${Number(ds.slice(8))}</span>
        ${App.cache.posts.filter(p => p.date === ds).sort((a, b) => (a.time || '').localeCompare(b.time || '')).map(p => `<div class="cal-item ${postCls(p)}" data-post="${p.id}" title="${esc((p.status || 'Idee') + (p.publish_log ? ' | ' + p.publish_log : ''))}">${p.time ? esc(p.time) + ' ' : ''}${p.format === 'Story' ? 'Story: ' : ''}${esc(p.title || p.type || 'Post')}</div>`).join('')}
        ${rulesOn(ds).map(r => `<div class="cal-item story" data-rule="${r.id}" title="Wiederkehrende Story, ${esc(r.targets || 'Facebook')}">${esc(r.time || '')} Story: ${esc(r.name || '')}</div>`).join('')}</div>`).join('')}</div></div>
    <div class="cal-legend small muted"><span class="cal-item auto">automatisch geplant</span><span class="cal-item plan">geplant, ohne Freigabe</span><span class="cal-item ok">gepostet</span><span class="cal-item err">nicht geklappt</span><span class="cal-item story">wiederkehrende Story</span></div>`;
  $$('[data-mon]', view).forEach(b => b.onclick = () => {
    const d = Number(b.dataset.mon), nd = new Date(y, m - 1 + d, 1);
    App._aoMonth = d ? `${nd.getFullYear()}-${pad(nd.getMonth() + 1)}` : todayStr().slice(0, 7);
    autopostCalendar(view, social);
  });
  $('#cal_new').onclick = () => planPost({ auto_publish: 1 });
  $$('[data-post]', view).forEach(el => el.onclick = e => { e.stopPropagation(); planPost(byId(App.cache.posts, el.dataset.post)); });
  $$('[data-rule]', view).forEach(el => el.onclick = async e => { e.stopPropagation(); if (await editStoryRule(byId(App.cache.story_rules, el.dataset.rule))) route(); });
  $$('[data-day]', view).forEach(el => el.onclick = () => { if (can('medien', 2) && el.dataset.day >= today) planPost({ date: el.dataset.day, auto_publish: 1 }); });
}

/* Was ist gerade online: Beiträge und aktive Storys auf Facebook und Instagram */
async function autopostOnline(view, social, refresh) {
  view.innerHTML = `${aoHead(social, 'online')}<div class="card empty">Lade Beiträge von Meta ...</div>`;
  let d;
  try { d = await api('social/online' + (refresh ? '?refresh=1' : '')); }
  catch (e) { view.innerHTML = `${aoHead(social, 'online')}<div class="card empty">${esc(e.message)}</div>`; return; }
  const card = (p, stats) => `<a class="card on-card" href="${esc(p.url || '#')}" target="_blank" rel="noopener">
      ${p.image ? `<img src="${esc(p.image)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : '<div class="on-noimg">kein Bild</div>'}
      <div class="small muted">${fmtStamp(p.created)}${p.type ? ' | ' + esc(String(p.type).toLowerCase()) : ''}</div>
      ${p.text ? `<div class="on-text">${esc(p.text)}</div>` : ''}
      <div class="on-stats">${stats.filter(([, v]) => v !== null && v !== undefined).map(([l, v]) => `<span><b>${fmtNum(v)}</b> ${l}</span>`).join('')}</div></a>`;
  const grid = (list, stats, empty) => list.length ? `<div class="on-grid">${list.map(p => card(p, stats(p))).join('')}</div>` : `<div class="muted">${empty}</div>`;
  view.innerHTML = `${aoHead(social, 'online')}
    <div class="mag-sec-head"><span class="small muted">Stand ${fmtStamp(d.fetched_at)}. Meta liefert Zahlen teils mit Verzögerung.</span><button class="btn sm" id="ao_refresh">Aktualisieren</button></div>
    <section class="card mag-sec"><h2>Facebook: aktive Storys</h2>${grid(d.facebook_stories, () => [], 'Gerade keine aktive Story.')}</section>
    <section class="card mag-sec"><h2>Facebook: Beiträge</h2>${grid(d.facebook, p => [['Aufrufe', p.views], ['Reaktionen', p.reactions], ['Kommentare', p.comments], ['Geteilt', p.shares]], 'Keine Beiträge gefunden.')}</section>
    ${social.instagram ? `<section class="card mag-sec"><h2>Instagram: aktive Storys</h2>${grid(d.instagram_stories, p => [['Aufrufe', p.views], ['Erreicht', p.reach]], 'Gerade keine aktive Story.')}</section>
    <section class="card mag-sec"><h2>Instagram: Beiträge</h2>${grid(d.instagram, p => [['Aufrufe', p.views], ['Erreicht', p.reach], ['Likes', p.likes], ['Kommentare', p.comments]], 'Keine Beiträge gefunden.')}</section>` : ''}
    ${d.errors.length ? `<div class="card small"><b>Nicht alles konnte geladen werden</b><div class="muted">${d.errors.map(esc).join('<br>')}</div>
      <div class="muted" style="margin-top:6px">Meist fehlt im Seiten-Token eine Berechtigung (read_insights, instagram_manage_insights). Dann das Token neu erzeugen und unter Einrichtung eintragen.</div></div>` : ''}`;
  $('#ao_refresh').onclick = () => autopostOnline(view, social, true);
}

/* Säulendiagramm für einen Verlauf: eine Reihe, Tooltip beim Überfahren, Tabelle als Alternative */
function barChart(series, unit) {
  if (!series.length) return '<div class="muted small">Für diesen Zeitraum liefert Meta keinen Tagesverlauf.</div>';
  const W = 640, H = 150, max = Math.max(1, ...series.map(s => s.value)), step = W / series.length, bw = Math.max(2, step - 2);
  const bars = series.map((s, i) => {
    const h = Math.max(s.value ? 2 : 0, Math.round(s.value / max * (H - 6))), x = i * step, yy = H - h, r = Math.min(4, bw / 2, h);
    const tip = `${fmtDate(s.date)}: ${fmtNum(s.value)} ${unit}`;
    return `<g class="bar" data-tip="${esc(tip)}"><rect x="${x}" y="0" width="${step}" height="${H}" fill="transparent"/>
      ${h ? `<path d="M${x},${H} V${yy + r} Q${x},${yy} ${x + r},${yy} H${x + bw - r} Q${x + bw},${yy} ${x + bw},${yy + r} V${H} Z" fill="var(--red)"/>` : ''}</g>`;
  }).join('');
  return `<div class="chart"><div class="chart-tip" hidden></div>
    <svg viewBox="0 0 ${W} ${H + 18}" preserveAspectRatio="none" role="img" aria-label="${esc(unit)} pro Tag">
      <line x1="0" y1="${H}" x2="${W}" y2="${H}" stroke="var(--line)" stroke-width="1"/>${bars}</svg>
    <div class="chart-axis small muted"><span>${fmtDate(series[0].date)}</span><span>höchster Tag: ${fmtNum(max)}</span><span>${fmtDate(series[series.length - 1].date)}</span></div>
    <details class="small"><summary>Werte als Tabelle</summary><table>${series.map(s => `<tr><td>${fmtDate(s.date)}</td><td style="text-align:right">${fmtNum(s.value)}</td></tr>`).join('')}</table></details></div>`;
}

function bindCharts(root) {
  $$('.chart', root).forEach(c => {
    const tip = $('.chart-tip', c);
    $$('.bar', c).forEach(b => {
      b.onmouseenter = e => { tip.textContent = b.dataset.tip; tip.hidden = false; };
      b.onmousemove = e => { const r = c.getBoundingClientRect(); tip.style.left = Math.min(e.clientX - r.left + 10, r.width - 160) + 'px'; tip.style.top = (e.clientY - r.top - 30) + 'px'; };
      b.onmouseleave = () => { tip.hidden = true; };
    });
  });
}

/* Statistik: Kennzahlen der Seite und des Instagram-Kontos für 7 oder 28 Tage */
async function autopostStats(view, social, days, refresh) {
  view.innerHTML = `${aoHead(social, 'statistik')}<div class="card empty">Lade Statistik von Meta ...</div>`;
  let d;
  try { d = await api(`social/insights?days=${days}${refresh ? '&refresh=1' : ''}`); }
  catch (e) { view.innerHTML = `${aoHead(social, 'statistik')}<div class="card empty">${esc(e.message)}</div>`; return; }
  const block = (title, data, chartKey, chartUnit, igNote) => {
    if (!data) return '';
    const tiles = [['Follower', data.followers], ...data.metrics.map(m => [m.label, m.value])];
    const ch = data.metrics.find(mm => mm.key === chartKey);
    return `<section class="card mag-sec"><h2>${title}</h2>
      <div class="grid g4" style="margin-bottom:14px">${tiles.map(([l, v]) => `<div class="stat-tile"><span>${esc(l)}</span><b>${fmtNum(v)}</b></div>`).join('')}</div>
      ${ch ? `<h3 style="margin:0 0 6px">${esc(ch.label)} pro Tag</h3>${barChart(ch.series, chartUnit)}` : ''}${igNote || ''}</section>`;
  };
  view.innerHTML = `${aoHead(social, 'statistik')}
    <div class="mag-sec-head"><div class="btn-row">${[7, 28].map(n => `<a class="btn sm ${n === days ? 'dark' : ''}" href="#/autopost/statistik/${n}">Letzte ${n} Tage</a>`).join('')}</div>
      <div class="btn-row"><span class="small muted">Stand ${fmtStamp(d.fetched_at)}</span><button class="btn sm" id="ao_refresh">Aktualisieren</button></div></div>
    ${block(`Facebook: ${esc(social.page)}`, d.facebook, 'page_media_view', 'Aufrufe')}
    ${block(`Instagram: @${esc(social.instagram || '')}`, d.instagram, 'reach', 'erreichte Konten',
      days > 30 ? '' : '<div class="small muted" style="margin-top:8px">Instagram liefert Werte bis zu 48 Stunden verzögert. Follower erst ab 100 Followern.</div>')}
    ${d.errors.length ? `<div class="card small"><b>Nicht alle Kennzahlen verfügbar</b><div class="muted">${d.errors.map(esc).join('<br>')}</div>
      <div class="muted" style="margin-top:6px">Meta ändert Kennzahlen regelmäßig. Fehlt eine Berechtigung (read_insights, instagram_manage_insights), das Seiten-Token neu erzeugen.</div></div>` : ''}`;
  bindCharts(view);
  $('#ao_refresh').onclick = () => autopostStats(view, social, days, true);
}

async function autopostSetup(view, social) {
  await Promise.all([load('posts', true), load('story_rules', true)]);
  const now = `${todayStr()} ${new Date().toTimeString().slice(0, 5)}`;
  const queue = App.cache.posts.filter(p => Number(p.auto_publish) && !p.publish_state).sort((a, b) => postWhen(a).localeCompare(postWhen(b)));
  const results = App.cache.posts.filter(p => p.publish_state).sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '') || b.id - a.id).slice(0, 15);
  const rules = [...App.cache.story_rules].sort((a, b) => Number(b.active) - Number(a.active) || (a.time || '').localeCompare(b.time || ''));
  const steps = `<ol class="small" style="margin:8px 0 0 18px;padding:0">
    <li>Auf <a href="https://developers.facebook.com/apps" target="_blank" rel="noopener">developers.facebook.com</a> eine App vom Typ „Business“ anlegen. Du musst Admin der Facebook-Seite sein.</li>
    <li>Im <a href="https://developers.facebook.com/tools/explorer" target="_blank" rel="noopener">Graph API Explorer</a> die App wählen und diese Berechtigungen anhaken: pages_show_list, pages_read_engagement, pages_manage_posts, read_insights, für Instagram zusätzlich instagram_basic, instagram_content_publish und instagram_manage_insights. Dann „Generate Access Token“.</li>
    <li>Das Token im <a href="https://developers.facebook.com/tools/debug/accesstoken" target="_blank" rel="noopener">Access Token Debugger</a> verlängern („Extend Access Token“).</li>
    <li>Mit dem verlängerten Token im Explorer <code>me/accounts</code> abrufen und dort das <b>access_token eurer Seite</b> kopieren. Dieses Seiten-Token läuft nicht ab.</li>
    <li>Hier einfügen und „Verbinden“. Der Hub erkennt Seite und verknüpftes Instagram-Konto selbst.</li></ol>
    <div class="small muted" style="margin-top:6px">Instagram geht nur mit einem Business- oder Creator-Konto, das mit der Facebook-Seite verknüpft ist, und nur auf dem Server mit Domain: Instagram holt die Bilder selbst über die öffentliche Adresse ab.</div>`;

  view.innerHTML = `${aoHead(social, 'einrichtung')}
    <div class="card" style="margin-bottom:16px"><h2>Verbindung</h2>
      ${social.connected ? `<div class="check-row"><span class="dot ok"></span><span style="flex:1">Facebook-Seite <b>${esc(social.page)}</b></span></div>
        <div class="check-row"><span class="dot ${social.instagram ? 'ok' : ''}"></span><span style="flex:1">${social.instagram ? `Instagram <b>@${esc(social.instagram)}</b>` : 'Kein Instagram-Konto mit der Seite verknüpft'}</span></div>
        <div class="check-row"><span class="dot ${(social.public_url || '').startsWith('https://') ? 'ok' : ''}"></span><span style="flex:1">Öffentliche Adresse für Instagram: ${social.public_url ? esc(social.public_url) : '<span class="muted">nicht eingetragen</span>'}</span></div>`
        : '<div class="muted">Es ist noch keine Facebook-Seite verbunden. Bis dahin postet der Hub nichts.</div>'}
      ${social.is_admin ? `<details style="margin-top:12px" ${social.connected ? '' : 'open'}><summary><b>${social.connected ? 'Verbindung ändern' : 'Verbindung einrichten'}</b></summary>${steps}
        <div class="form" style="margin-top:12px">
          <div class="field full"><label for="ao_token">Seiten-Token</label><input class="input" id="ao_token" type="password" autocomplete="off" placeholder="${social.connected ? 'hinterlegt, nur zum Ändern neu eintragen' : 'EAA...'}"></div>
          <div class="field full"><label for="ao_url">Öffentliche Adresse des Hubs (für Instagram)</label><input class="input" id="ao_url" value="${esc(social.public_url || '')}" placeholder="z. B. https://hub.emdentigers.de"></div></div>
        <div class="btn-row" style="margin-top:10px"><button class="btn primary" id="ao_connect">Verbinden und prüfen</button>${social.connected ? '<button class="btn ghost" id="ao_disconnect">Verbindung trennen</button>' : ''}</div></details>`
        : social.connected ? '' : '<div class="small muted" style="margin-top:6px">Die Verbindung richtet ein Admin ein.</div>'}
    </div>
    <div class="card" style="margin-bottom:16px"><div class="mag-sec-head"><h2>Wiederkehrende Storys</h2><button class="pp btn sm primary" id="ao_rule">+ Story-Regel</button></div>
      ${rules.length ? `<div class="table-wrap" style="border:0"><table><thead><tr><th></th><th>Bezeichnung</th><th>Tage</th><th>Uhrzeit</th><th>Ziel</th><th>Zuletzt</th><th></th></tr></thead><tbody>
        ${rules.map(r => `<tr style="${Number(r.active) ? '' : 'opacity:.5'}"><td>${r.image ? `<img class="thumb" src="${esc(r.image)}">` : '<div class="thumb"></div>'}</td>
          <td><b>${esc(r.name || 'Story')}</b>${Number(r.active) ? '' : ' <span class="badge">pausiert</span>'}${r.valid_until ? `<div class="muted small">bis ${fmtDate(r.valid_until)}</div>` : ''}${r.image ? '' : '<div class="warnline">Bild fehlt</div>'}</td>
          <td>${esc(ruleDays(r)) || '<span class="warnline">kein Tag</span>'}</td><td>${esc(r.time || '')}</td><td>${esc(r.targets || 'Facebook')}</td>
          <td class="small">${esc(r.last_result || 'noch nie')}</td>
          <td class="actions"><button class="pp btn sm" data-test="${r.id}">Jetzt testen</button> <button class="btn sm ghost keep" data-rule="${r.id}">${can('medien', 2) ? 'Bearbeiten' : 'Ansehen'}</button></td></tr>`).join('')}
        </tbody></table></div>` : '<div class="muted">Noch keine Regel. Beispiel: „Training heute“ jeden Dienstag und Donnerstag um 12:00 Uhr mit eurem Canva-Story-Bild.</div>'}
      <div class="small muted" style="margin-top:8px">Läuft der Hub zur geplanten Uhrzeit nicht, holt er die Story bis zu 3 Stunden später nach, danach fällt sie für den Tag aus.</div></div>
    <div class="grid g2">
      <div class="card"><h2>Warteschlange</h2>
        ${queue.length ? `<div class="list">${queue.map(p => `<div class="list-item">${dateBox(p.date)}<div class="grow"><b>${esc(p.title || p.type || 'Post')}</b>
          <div class="muted small">${p.time ? p.time + ' Uhr | ' : ''}${esc(p.format || 'Feed')} | ${esc(p.targets || 'Facebook')}${postWhen(p) <= now ? ' | <b>jetzt fällig</b>' : ''}</div>
          ${!p.image && (p.format === 'Story' || /instagram/i.test(p.targets)) ? '<div class="warnline">Bild fehlt</div>' : ''}</div>
          <button class="btn sm ghost keep" data-post="${p.id}">Ansehen</button></div>`).join('')}</div>`
          : '<div class="muted">Keine freigegebenen Posts. Im Postplan beim Post „Automatisch posten“ anhaken.</div>'}</div>
      <div class="card"><h2>Zuletzt</h2>
        ${results.length ? `<div class="list">${results.map(p => `<div class="list-item"><div class="grow"><b>${esc(p.title || p.type || 'Post')}</b> ${publishBadge(p)}
          <div class="muted small">${esc(p.publish_log || '')}</div></div>
          <div class="btn-row">${['fehler', 'teilweise', 'verpasst'].includes(p.publish_state) ? `<button class="pp btn sm" data-now="${p.id}">Jetzt posten</button><button class="pp btn sm ghost" data-reset="${p.id}">Neu einplanen</button>` : ''}
          <button class="btn sm ghost keep" data-post="${p.id}">Ansehen</button></div></div>`).join('')}</div>` : '<div class="muted">Noch nichts automatisch gepostet.</div>'}</div>
    </div>`;

  const run = async (body, question) => {
    if (!confirmBox(question)) return;
    toast('Wird gepostet ...');
    try { const r = await api('social/publish', 'POST', body); alert(r.log); } catch (e) { alert(e.message); }
    route();
  };
  $('#ao_rule').onclick = async () => {
    const days = WD.map((d, i) => (App.settings.training_text || '').includes(d) ? (i || 7) : 0).filter(Boolean);
    if (await editStoryRule({ name: 'Training heute', time: '12:00', targets: 'Facebook', active: 1, weekdays: days.join(',') })) route();
  };
  $$('[data-rule]', view).forEach(b => b.onclick = async () => { if (await editStoryRule(byId(rules, b.dataset.rule))) route(); });
  $$('[data-test]', view).forEach(b => b.onclick = () => run({ rule_id: Number(b.dataset.test) }, 'Diese Story jetzt sofort posten? Sie erscheint wirklich auf der Seite.'));
  $$('[data-now]', view).forEach(b => b.onclick = () => run({ post_id: Number(b.dataset.now), again: true }, 'Diesen Post jetzt sofort posten?'));
  $$('[data-reset]', view).forEach(b => b.onclick = async () => { await api('social/reset', 'POST', { post_id: Number(b.dataset.reset) }); toast('Wieder eingeplant'); route(); });
  $$('[data-post]', view).forEach(b => b.onclick = () => planPost(byId(App.cache.posts, b.dataset.post)));
  if ($('#ao_connect')) $('#ao_connect').onclick = async () => {
    try {
      const r = await api('social/connection', 'PUT', { token: $('#ao_token').value.trim(), public_url: $('#ao_url').value.trim() });
      toast(`Verbunden mit ${r.page}${r.instagram ? ' und @' + r.instagram : ''}`); route();
    } catch (e) { alert(e.message); }
  };
  if ($('#ao_disconnect')) $('#ao_disconnect').onclick = async () => {
    if (!confirmBox('Verbindung trennen? Danach postet der Hub nichts mehr automatisch.')) return;
    await api('social/connection', 'DELETE'); toast('Verbindung getrennt'); route();
  };
}

