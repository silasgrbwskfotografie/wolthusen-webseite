/* Wolthusen Hub: Kernfunktionen (API, Router, Formulare, Hilfen) */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const App = {
  settings: {},
  cache: {},
  pages: {},
};

/* Zweite Schutzschicht: Links mit javascript: nie öffnen (der Server nimmt solche Links schon nicht an).
   blob: bleibt erlaubt, darüber laufen die eigenen CSV-Downloads. */
document.addEventListener('click', ev => {
  const a = ev.target.closest && ev.target.closest('a[href]');
  if (a && /^[\s\x00-\x1f]*(javascript|vbscript)\s*:/i.test((a.getAttribute('href') || '').replace(/[\t\n\r]/g, ''))) {
    ev.preventDefault(); ev.stopImmediatePropagation();
  }
}, true);

/* ---------- API ---------- */
async function api(path, method = 'GET', body) {
  const opt = { method, headers: { 'X-TMH': '1' } };
  if (body !== undefined) {
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(body);
  }
  const r = await fetch('/api/' + path, opt);
  if (r.status === 401) { location.href = '/login'; throw new Error('Nicht angemeldet'); }
  const data = await r.json().catch(() => null);
  // Zwei-Faktor-Pflicht, aber noch nicht eingerichtet: der Server lässt nur das Profil zu
  if (r.status === 403 && data && data.need_2fa && location.hash !== '#/profile') location.hash = '#/profile';
  if (!r.ok) { const e = new Error((data && data.error) || 'Fehler ' + r.status); e.status = r.status; throw e; }
  return data;
}

async function load(table, force = false) {
  if (!force && App.cache[table]) return App.cache[table];
  try { App.cache[table] = await api(table); }
  catch (e) { if (e.status === 403) App.cache[table] = []; else throw e; }  // kein Leserecht: leer behandeln
  return App.cache[table];
}
function invalidate(...tables) { tables.forEach(t => delete App.cache[t]); }
async function loadAll(...tables) { return Promise.all(tables.map(t => load(t))); }

const APP_VERSION = '1.2';
async function checkVersion() {
  try {
    const info = await api('');
    if (info.version !== APP_VERSION) {
      document.body.insertAdjacentHTML('afterbegin', `<div style="position:fixed;top:0;left:0;right:0;z-index:100;background:#a86400;color:#fff;padding:12px 20px;font-weight:600">
        Es läuft noch die alte Programmversion ${esc(info.version || '')}. Bitte alle schwarzen Hub-Fenster schließen
        (oder im Task-Manager alle python.exe beenden) und Start.bat neu starten.</div>`);
    }
  } catch (e) { /* ignorieren */ }
}

/* ---------- Rechte ---------- */
// Teamkleidung dürfen Verein, Finanzen und Medien verwalten (wie TABLE_AREAS_ANY im Server)
const APPAREL_AREAS = 'verein|finanzen|medien';
const PAGE_AREA = {
  posts: 'medien', autopost: 'medien', shop: 'medien', newsletter: 'medien', media: 'medien', team: 'medien', magazine: 'medien', website: 'medien', news: 'medien',
  games: 'verein', teams: 'verein', players: 'verein', opponents: 'verein', trainings: 'verein', bookings: 'verein', sponsors: 'verein', apparel: APPAREL_AREAS,
  members: 'mitglieder', contacts: 'mitglieder', finance: 'finanzen', cards: 'finanzen',
  spieltag: 'spieltag', accounts: 'admin', groups: 'admin', emails: 'admin', notes: 'admin', settings: 'admin', log: 'admin', admin: 'admin', wartung: 'wartung', postfach: 'postfach|ownmail',
};
function can(area, lvl = 1) {
  const me = App.me; if (!me) return false;
  if (area === 'admin') return !!me.is_admin;
  return area.split('|').some(a => (me.perms?.[a] || 0) >= lvl);   // 'a|b': eines der Bereiche reicht
}
function applyPermissions() {
  decorateNav();
  $$('#nav [data-area]').forEach(el => { el.style.display = can(el.dataset.area) ? '' : 'none'; });
  // Überschrift nur zeigen, wenn darunter (bis zur nächsten Überschrift) etwas sichtbar ist
  $$('#nav .nav-group[data-group]').forEach(g => {
    let el = g.nextElementSibling, any = false;
    for (; el && !el.classList.contains('nav-group'); el = el.nextElementSibling) if (el.style.display !== 'none') any = true;
    g.style.display = any ? '' : 'none';
  });
  initNavGroups();
  document.body.toggleAttribute('data-mw', can('medien', 2));
  document.body.toggleAttribute('data-vw', can('verein', 2));
  document.body.toggleAttribute('data-aw', can(APPAREL_AREAS, 2));
  renderTabbar();
  renderTopnav();
}

/* Großer Bildschirm (ab 701 px): Oberkategorien als Pillen oben statt der Seitenleiste, Unterpunkte im Aufklappmenü.
   Gebaut aus #nav (dort stehen Rechte und Zahlen), neu gebaut nach Rechten, Zahlen und Darstellung. */
function navCount(a) { return $$('.nav-count', a).reduce((x, b) => x + (b.style.display === 'none' ? 0 : (parseInt(b.textContent, 10) || 0)), 0); }
function renderTopnav() {
  const bar = $('#topnav'); if (!bar || !App.me) return;
  const vis = el => el.style.display !== 'none';
  const cnt = n => n ? `<span class="tn-count">${n > 99 ? '99+' : n}</span>` : '';
  const top = [], groups = []; let cur = null;
  for (const el of $('#nav').children) {
    if (el.classList.contains('nav-group')) { cur = { key: el.dataset.group, label: (el.querySelector('.ng-label') || el).textContent.trim(), items: [], show: vis(el) }; groups.push(cur); continue; }
    if (el.matches('a[data-page]') && vis(el) && el.dataset.page !== 'profile') (cur ? cur.items : top).push(el);
  }
  const link = a => `<a href="${a.getAttribute('href')}" data-tp="${a.dataset.page}">${esc(navText(a))}${cnt(navCount(a))}</a>`;
  const me = App.me, th = themeGet();
  bar.innerHTML = `<a class="tn-brand" href="#/" aria-label="Übersicht"><img src="${esc(App.settings?.logo || '/static/logo.png')}" alt=""><span>Wolthusen Hub</span></a>
    <nav class="tn-pills">${top.map(link).join('')}${groups.filter(g => g.show && g.items.length).map(g => `<div class="tn-dd" data-g="${g.key}">
      <button type="button" aria-haspopup="true" aria-expanded="false">${esc(g.label)}${cnt(g.items.reduce((n, a) => n + navCount(a), 0))}</button>
      <div class="tn-menu"><div class="tn-box">${g.items.map(link).join('')}</div></div></div>`).join('')}</nav>
    <div class="tn-tools">
      <div class="tn-theme" role="group" aria-label="Darstellung">${[['auto', 'Automatisch', 'auto'], ['light', 'Hell', 'sun'], ['dark', 'Dunkel', 'moon']].map(([k, l, ic]) =>
        `<button type="button" data-tn-theme="${k}" class="${th === k ? 'on' : ''}" aria-pressed="${th === k}" title="${l}">${tabIcon(ic)}</button>`).join('')}</div>
      <div class="tn-dd tn-me"><button type="button" aria-haspopup="true" aria-expanded="false" title="${esc(me.display_name || me.username)}"><span class="tn-av">${esc((me.display_name || me.username || '?').trim().charAt(0).toUpperCase())}</span></button>
        <div class="tn-menu"><div class="tn-box"><div class="tn-who"><b>${esc(me.display_name || me.username)}</b><span>${me.is_admin ? 'Admin' : esc((me.groups || []).join(', '))}</span></div>
          <a href="#/profile" data-tp="profile">Mein Profil</a><button type="button" id="tnLogout">Abmelden</button><span class="tn-ver">v${APP_VERSION}</span></div></div></div>
    </div>`;
  $$('.tn-dd > button', bar).forEach(b => b.onclick = e => {   // Klick (auch Touch und Tastatur) öffnet, ein zweites Mal oder daneben schließt
    e.stopPropagation(); const dd = b.parentElement, open = !dd.classList.contains('open');
    $$('.tn-dd.open', bar).forEach(x => { x.classList.remove('open'); x.firstElementChild.setAttribute('aria-expanded', 'false'); });
    dd.classList.toggle('open', open); b.setAttribute('aria-expanded', String(open));
  });
  $$('[data-tn-theme]', bar).forEach(b => b.onclick = () => themeSet(b.dataset.tnTheme));
  $('#tnLogout').onclick = async () => { await fetch('/auth/logout', { method: 'POST', headers: { 'X-TMH': '1' } }); location.href = '/login'; };
  markTopnav(location.hash.replace(/^#\/?/, '').split('/')[0] || 'dashboard');
}
function closeTopnav() { $$('#topnav .tn-dd.open').forEach(x => { x.classList.remove('open'); x.firstElementChild.setAttribute('aria-expanded', 'false'); }); }
document.addEventListener('click', e => { if (!e.target.closest('#topnav .tn-dd')) closeTopnav(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeTopnav(); });
function markTopnav(page) {
  $$('#topnav [data-tp]').forEach(a => a.classList.toggle('on', a.dataset.tp === page));
  $$('#topnav .tn-dd[data-g]').forEach(dd => dd.classList.toggle('on', !!dd.querySelector(`[data-tp="${page}"]`)));
  closeTopnav();
}

/* Oberreiter (Medien, Verein, ...) zum Einklappen, pro Gerät gemerkt. Am Oberreiter die Summe der Zahlen seiner Unterreiter. */
const NAV_FOLD_KEY = 'tmh_nav_fold';
const navFolded = () => { try { return new Set(JSON.parse(localStorage.getItem(NAV_FOLD_KEY) || '[]')); } catch { return new Set(); } };
function navGroupItems(g) { const out = []; for (let el = g.nextElementSibling; el && !el.classList.contains('nav-group'); el = el.nextElementSibling) out.push(el); return out; }
function initNavGroups() {
  const folded = navFolded();
  $$('#nav .nav-group[data-group]').forEach(g => {
    if (!g.dataset.ready) {
      g.dataset.ready = '1';
      const label = g.textContent.trim();
      g.innerHTML = `<span class="ng-label">${esc(label)}</span><span class="badge red ng-count" style="display:none"></span><span class="ng-chev" aria-hidden="true">▾</span>`;
      g.setAttribute('role', 'button'); g.tabIndex = 0;
      const toggle = () => {
        const f = navFolded();
        f.has(g.dataset.group) ? f.delete(g.dataset.group) : f.add(g.dataset.group);
        try { localStorage.setItem(NAV_FOLD_KEY, JSON.stringify([...f])); } catch { /* ohne Speicher: nur bis zum Neuladen */ }
        initNavGroups();
      };
      g.onclick = toggle;
      g.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } };
    }
    const closed = folded.has(g.dataset.group);
    g.classList.toggle('folded', closed);
    g.setAttribute('aria-expanded', String(!closed));
    g.setAttribute('aria-label', `${g.querySelector('.ng-label').textContent} ${closed ? 'aufklappen' : 'einklappen'}`);
    navGroupItems(g).forEach(a => a.classList.toggle('nav-folded', closed));
  });
  updateNavGroupCounts();
}
function updateNavGroupCounts() {
  $$('#nav .nav-group[data-group]').forEach(g => {
    const n = navGroupItems(g).filter(a => a.style.display !== 'none')
      .reduce((sum, a) => sum + $$('.nav-count', a).reduce((x, b) => x + (b.style.display === 'none' ? 0 : (parseInt(b.textContent, 10) || 0)), 0), 0);
    const b = g.querySelector('.ng-count'); if (!b) return;
    b.style.display = n ? '' : 'none'; b.textContent = n > 99 ? '99+' : String(n);   // nicht hidden: .badge setzt display selbst
    b.title = n === 1 ? '1 neue Meldung' : `${n} neue Meldungen`;
  });
}
async function refreshNavCounts() {
  if (!App.me) return;
  let r; try { r = await api('navcounts'); } catch { return; }
  $$('#nav .nav-count[data-count]').forEach(b => {
    const n = Number(r[b.dataset.count]) || 0;
    b.style.display = n > 0 ? '' : 'none'; b.textContent = n > 99 ? '99+' : n;
  });
  updateNavGroupCounts();
  renderTopnav();
}

/* Handy: Tab-Leiste unten wie in einer App. Bis zu 4 Bereiche nach Rechten, dazu „Mehr“ für das ganze Menü. */
const TAB_ICONS = {
  home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h5v-6h4v6h5V10"/>',
  cal: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/>',
  post: '<path d="M4 5h16v11H9l-5 4z"/>',
  team: '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-5 6-5s6 1.7 6 5"/><circle cx="17" cy="9" r="2.5"/><path d="M16 14.6c2.9.2 5 1.7 5 4.4"/>',
  img: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 8"/>',
  euro: '<path d="M17 6.5A7 7 0 1 0 17 17.5"/><path d="M4 10h9M4 14h9"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6 8-6s8 2 8 6"/>',
  more: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
  web: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 2.5 15.3 0 18M12 3c-2.5 2.7-2.5 15.3 0 18"/>',
  news: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 9h8M8 13h8M8 17h5"/>',
  shop: '<path d="M5 8h14l-1 12H6z"/><path d="M9 8a3 3 0 0 1 6 0"/>',
  card: '<rect x="3" y="6" width="18" height="12" rx="2"/><path d="M3 10h18"/>',
  star: '<path d="M12 4l2.4 5 5.6.6-4.2 3.8 1.2 5.6L12 16.3 7 19l1.2-5.6L4 9.6 9.6 9z"/>',
  note: '<path d="M5 4h10l4 4v12H5z"/><path d="M15 4v4h4M8 13h8M8 17h6"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
  dot: '<circle cx="12" cy="12" r="4"/>',
  flag: '<path d="M5 21V4"/><path d="M5 4h12l-2.5 4L17 12H5"/>',
  shirt: '<path d="M8 3 3 6l2 4 3-1v12h8V9l3 1 2-4-5-3a4 4 0 0 1-8 0z"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
  book: '<path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z"/><path d="M4 20.5V5.5M8 7h8"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3"/>',
  tool: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2.4-.6-.6-2.4z"/>',
  list: '<path d="M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01"/>',
  inbox: '<path d="M4 13l2.5-7h11L20 13v6H4z"/><path d="M4 13h4.5l1 2.5h5l1-2.5H20"/>',
  send: '<path d="M21 3 3 10.5l7 2.5 2.5 7z"/><path d="M10 13l5-5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>',
  auto: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
};
// Symbole für Seiten aus dem Menü, die man sich in die eigene Tab-Leiste legen kann (sonst ein Punkt)
const PAGE_ICONS = { dashboard: 'home', postfach: 'mail', newsletter: 'send', games: 'cal', posts: 'post', players: 'team', media: 'img', members: 'team', finance: 'euro', profile: 'user',
  website: 'web', news: 'news', shop: 'shop', cards: 'card', sponsors: 'star', notes: 'note', settings: 'gear', admin: 'tool', contacts: 'inbox', autopost: 'send', team: 'team',
  spieltag: 'flag', magazine: 'book', opponents: 'shield', teams: 'team', trainings: 'cal', bookings: 'cal', apparel: 'shirt', accounts: 'user', groups: 'key', emails: 'mail', wartung: 'tool', log: 'list' };
const navText = a => [...a.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();   // Name ohne Symbol und Zahl
/* Symbol vor jeden Menüpunkt (einmalig) */
function decorateNav() {
  $$('#nav a[data-page]').forEach(a => {
    if (a.dataset.ic) return;
    a.dataset.ic = '1';
    a.insertAdjacentHTML('afterbegin', tabIcon(PAGE_ICONS[a.dataset.page] || 'dot').replace('<svg ', '<svg class="nav-ic" '));
  });
}
/* Darstellung hell, dunkel oder wie das Gerät (pro Gerät gemerkt, index.html setzt sie schon vor dem ersten Bild) */
const THEME_KEY = 'tmh_theme';
function themeGet() { try { const t = localStorage.getItem(THEME_KEY); return t === 'light' || t === 'dark' ? t : 'auto'; } catch { return 'auto'; } }
function themeSet(t) {
  try { t === 'auto' ? localStorage.removeItem(THEME_KEY) : localStorage.setItem(THEME_KEY, t); } catch { /* ohne Speicher nur bis zum Neuladen */ }
  if (t === 'auto') delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  renderSideFoot(); renderTopnav();
}
// Kurze Namen für die schmale Leiste
const TAB_LABELS = { dashboard: 'Start', postfach: 'Mail', games: 'Spiele', posts: 'Posts', players: 'Kader', media: 'Medien', members: 'Mitglieder', finance: 'Finanzen',
  spieltag: 'Spieltag', profile: 'Profil', website: 'Webseite', cards: 'Karten', sponsors: 'Sponsoren', contacts: 'Anfragen', autopost: 'Auto', team: 'Team', magazine: 'Heft', apparel: 'Kleidung' };
/* Alle Seiten, die die Person im Menü sieht (für die eigene Tab-Leiste) */
function tabChoices() {
  return $$('#nav a[data-page]').filter(a => a.style.display !== 'none').map(a => {
    const page = a.dataset.page, label = navText(a);
    return { page, href: a.getAttribute('href'), label: TAB_LABELS[page] || label, full: label, icon: PAGE_ICONS[page] || 'dot' };
  });
}
const TAB_CANDIDATES = [
  { page: 'dashboard', href: '#/', label: 'Start', icon: 'home' },
  { page: 'postfach', href: '#/postfach', label: 'Mail', icon: 'mail', area: 'postfach|ownmail' },
  { page: 'games', href: '#/games', label: 'Spiele', icon: 'cal', area: 'verein' },
  { page: 'posts', href: '#/posts', label: 'Posts', icon: 'post', area: 'medien' },
  { page: 'players', href: '#/players', label: 'Kader', icon: 'team', area: 'verein' },
  { page: 'media', href: '#/media', label: 'Medien', icon: 'img', area: 'medien' },
  { page: 'members', href: '#/members', label: 'Mitglieder', icon: 'team', area: 'mitglieder' },
  { page: 'finance', href: '#/finance', label: 'Finanzen', icon: 'euro', area: 'finanzen' },
  { page: 'profile', href: '#/profile', label: 'Profil', icon: 'user' },
];
const tabIcon = k => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${TAB_ICONS[k]}</svg>`;
function renderTabbar() {
  const bar = $('#tabbar');
  if (!bar || !App.me) return;
  const own = (App.me.tabbar || []).map(p => tabChoices().find(c => c.page === p)).filter(Boolean);   // eigene Auswahl (Mein Profil), nur sichtbare Seiten
  const tabs = own.length ? own.slice(0, 4) : TAB_CANDIDATES.filter(t => !t.area || can(t.area)).slice(0, 4);
  bar.innerHTML = tabs.map(t => `<a href="${t.href}" data-tab="${t.page}">${tabIcon(t.icon)}<span>${t.label}</span></a>`).join('')
    + `<button type="button" id="tabMore">${tabIcon('more')}<span>Mehr</span></button>`;
  $('#tabMore').onclick = () => setNav(!document.body.classList.contains('nav-open'));
  markTab(location.hash.replace(/^#\/?/, '').split('/')[0] || 'dashboard');
}
function markTab(name) {
  $$('#tabbar [data-tab]').forEach(a => a.classList.toggle('active', a.dataset.tab === name));
  markTopnav(name);
  const link = $(`#nav a[data-page="${name}"]`);
  if ($('#topTitle')) $('#topTitle').textContent = link ? navText(link) : 'Wolthusen Hub';
}
function renderSideFoot() {
  const me = App.me;
  const th = themeGet();
  $('#sideFoot').innerHTML = `<div class="theme-sw" role="group" aria-label="Darstellung">${[['auto', 'Auto', 'auto'], ['light', 'Hell', 'sun'], ['dark', 'Dunkel', 'moon']].map(([k, l, ic]) =>
    `<button type="button" data-theme-set="${k}" class="${th === k ? 'on' : ''}" aria-pressed="${th === k}">${tabIcon(ic)}${l}</button>`).join('')}</div><a href="#/profile" class="me-link"><b>${esc(me.display_name || me.username)}</b><span>${me.is_admin ? 'Admin' : esc((me.groups || []).join(', ') || 'Mein Profil')}</span></a><button id="logoutBtn">Abmelden</button>`;
  $$('[data-theme-set]').forEach(b => b.onclick = () => themeSet(b.dataset.themeSet));
  $('#logoutBtn').onclick = async () => { await fetch('/auth/logout', { method: 'POST', headers: { 'X-TMH': '1' } }); location.href = '/login'; };
}

async function loadSettings() {
  App.settings = await api('settings');
  applyBranding();
}

function applyBranding() {
  const s = App.settings;
  document.documentElement.style.setProperty('--red', s.color_primary || '#3D2F96');
  $('#brandName').textContent = s.club_name || 'SV Amisia Wolthusen';
  const mark = $('#brandMark');
  mark.innerHTML = `<img src="${s.logo || '/static/logo.png'}" alt="SV Amisia Wolthusen">`;
  $('#brandVer').textContent = 'v' + APP_VERSION;
}

async function uploadDataUrl(dataUrl, name, library = true, tags = '') {
  const res = await api('upload', 'POST', { data: dataUrl, name, library, tags });
  invalidate('media');
  return res.path;
}

function fileToDataUrl(file) {
  return new Promise((ok, err) => {
    const fr = new FileReader();
    fr.onload = () => ok(fr.result);
    fr.onerror = err;
    fr.readAsDataURL(file);
  });
}

/* Große Fotos vor dem Speichern verkleinern (längste Seite max. 2400 px) */
async function shrinkImage(file, max = 2400) {
  const url = await fileToDataUrl(file);
  if (!/^data:image\/(jpeg|png|webp)/.test(url)) return url;
  const img = await loadImage(url);
  const scale = Math.min(1, max / Math.max(img.width, img.height));
  if (scale >= 1 && file.size < 3_000_000) return url;
  const c = document.createElement('canvas');
  c.width = Math.round(img.width * scale);
  c.height = Math.round(img.height * scale);
  c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
  return file.type === 'image/png' ? c.toDataURL('image/png') : c.toDataURL('image/jpeg', 0.9);
}

async function uploadFile(file, tags = '') {
  const data = await shrinkImage(file);
  return uploadDataUrl(data, file.name, true, tags);
}

const imgCache = {};
function loadImage(src) {
  if (!src) return Promise.resolve(null);
  if (imgCache[src]) return imgCache[src];
  imgCache[src] = new Promise(ok => {
    const i = new Image();
    i.onload = () => ok(i);
    i.onerror = () => ok(null);
    i.src = src;
  });
  return imgCache[src];
}

/* ---------- Helfer ---------- */
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const WD = ['Sonntag', 'Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag'];
const WD_S = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
const MON = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
const MON_S = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];

function parseDate(d) { if (!d) return null; const [y, m, t] = d.split('-').map(Number); return new Date(y, m - 1, t); }
function fmtDate(d, withWd = false) {
  const x = parseDate(d); if (!x) return '';
  const s = `${String(x.getDate()).padStart(2, '0')}.${String(x.getMonth() + 1).padStart(2, '0')}.${x.getFullYear()}`;
  return withWd ? `${WD[x.getDay()]}, ${s}` : s;
}
function todayStr() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
function addDays(d, n) { const x = parseDate(d); x.setDate(x.getDate() + n); return `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, '0')}-${String(x.getDate()).padStart(2, '0')}`; }
function daysUntil(d) { const x = parseDate(d); if (!x) return null; const t = parseDate(todayStr()); return Math.round((x - t) / 86400000); }
function eur(n) { return (Number(n) || 0).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' }); }
function handle(h) { h = (h || '').trim().replace(/^@/, '').replace(/^https?:\/\/(www\.)?instagram\.com\//, '').replace(/\/.*$/, ''); return h ? '@' + h : ''; }
function fullName(p) { return p ? [p.first_name, p.last_name].filter(Boolean).join(' ') : ''; }
function byId(list, id) { return (list || []).find(x => x.id == id); }

function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add('hidden'), 2200);
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); }
  catch { const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove(); }
  toast('In die Zwischenablage kopiert');
}

/* Gedankenstriche vermeiden (Wunsch: wirkt sonst nach KI) */
function noDashes(text) {
  return String(text || '')
    .replace(/\s+[–—]\s+/g, ', ')
    .replace(/(\d)\s*[–—]\s*(\d)/g, '$1:$2')
    .replace(/[–—]/g, '-');
}
function hasDashes(text) { return /[–—]/.test(text || ''); }

/* ---------- Modal & Formulare ---------- */
function openModal(html) {
  App.beforeModalClose = null;   // ein Fenster kann beim Schließen nachfragen (z. B. Entwurf speichern), siehe closeModal
  $('#modalBox').innerHTML = html;
  $('#modal').classList.remove('hidden');
}
function closeModal(force) {
  if (force !== true && App.beforeModalClose && App.beforeModalClose() === false) return;   // Fenster will vorher fragen
  App.beforeModalClose = null; $('#modal').classList.add('hidden'); $('#modalBox').innerHTML = '';
}
$('#modal').addEventListener('mousedown', e => { if (e.target.id === 'modal') closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

function confirmBox(text) { return window.confirm(text); }

/*
  Feldtypen: text, number, date, time, textarea, select, check, image, file, files, ref, url
  { key, label, type, options, ref:{table, label:fn}, full, hint, show:fn(values) }
  files: mehrere beliebige Dateien, gespeichert als JSON-Liste [{name, path, size, added}]
*/
function parseFiles(v) {
  try { const a = JSON.parse(v || '[]'); return Array.isArray(a) ? a : []; } catch { return []; }
}
function fmtSize(n) {
  n = Number(n) || 0;
  return n >= 1048576 ? (n / 1048576).toFixed(1).replace('.', ',') + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB';
}
const INLINE_EXT = /\.(png|jpe?g|gif|webp|pdf)$/i;
function fieldHtml(f, val) {
  const id = 'f_' + f.key;
  const v = val ?? f.default ?? '';
  const cls = 'field' + (f.full || f.type === 'textarea' ? ' full' : '');
  let input = '';
  switch (f.type) {
    case 'textarea':
      input = `<textarea id="${id}" name="${f.key}" rows="${f.rows || 3}" placeholder="${esc(f.placeholder || '')}">${esc(v)}</textarea>`; break;
    case 'select':
      input = `<select id="${id}" name="${f.key}">${(f.options || []).map(o => `<option ${o == v ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>`; break;
    case 'ref': {
      const list = App.cache[f.ref.table] || [];
      input = `<select id="${id}" name="${f.key}" data-num="1"><option value="">(keine Auswahl)</option>${list.map(o => `<option value="${o.id}" ${o.id == v ? 'selected' : ''}>${esc(f.ref.label(o))}</option>`).join('')}</select>`; break;
    }
    case 'check':
      return `<div class="${cls}" data-fkey="${f.key}"><label>&nbsp;</label><label class="check"><input type="checkbox" id="${id}" name="${f.key}" ${Number(v) ? 'checked' : ''}> ${esc(f.label)}</label>${f.hint ? `<div class="hint">${esc(f.hint)}</div>` : ''}</div>`;
    case 'file':
      input = `<div class="img-field"><a id="${id}_link" class="btn sm" target="_blank" rel="noopener" ${v ? `href="${esc(v)}"` : 'style="display:none"'}>Ansehen</a>
        <input type="hidden" id="${id}" name="${f.key}" value="${esc(v)}">
        <input type="file" id="${id}_file" accept="image/*,application/pdf" hidden>
        <div class="btn-row"><button type="button" class="btn sm" data-filepick="${f.key}">Datei wählen</button>
        <button type="button" class="btn sm ghost" data-fileclear="${f.key}">Entfernen</button></div></div>`; break;
    case 'files':
      input = `<div class="files-field" data-filesbox="${f.key}">
        <input type="hidden" id="${id}" name="${f.key}" value="${esc(JSON.stringify(parseFiles(v)))}">
        <ul class="file-list" id="${id}_list"></ul>
        <input type="file" id="${id}_file" multiple hidden ${f.accept ? `accept="${esc(f.accept)}"` : ''}>
        <div class="btn-row"><button type="button" class="btn sm" data-filesadd="${f.key}" data-maxmb="${f.maxMb || 25}">Dateien hinzufügen</button>
        <span class="hint">oder hierher ziehen, max. ${f.maxMb || 25} MB pro Datei</span></div></div>`; break;
    case 'image':
      input = `<div class="img-field"><img id="${id}_prev" ${v ? `src="${esc(v)}"` : 'style="opacity:.3"'} alt="">
        <input type="hidden" id="${id}" name="${f.key}" value="${esc(v)}">
        <div class="btn-row"><button type="button" class="btn sm" data-imgpick="${f.key}">Bild wählen</button>
        <button type="button" class="btn sm ghost" data-imgclear="${f.key}">Entfernen</button></div></div>`; break;
    default:
      input = `<input type="${f.type || 'text'}" id="${id}" name="${f.key}" value="${esc(v)}" placeholder="${esc(f.placeholder || '')}" ${f.type === 'number' ? 'step="any"' : ''} ${f.list ? `list="${id}_dl"` : ''}>`
        + (f.list ? `<datalist id="${id}_dl">${f.list.map(o => `<option value="${esc(o)}">`).join('')}</datalist>` : '');
  }
  return `<div class="${cls}" data-fkey="${f.key}"><label for="${id}">${esc(f.label)}</label>${input}${f.hint ? `<div class="hint">${esc(f.hint)}</div>` : ''}</div>`;
}

function readForm(root, fields) {
  const out = {};
  fields.forEach(f => {
    const el = $('#f_' + f.key, root);
    if (!el) return;
    if (f.type === 'check') out[f.key] = el.checked ? 1 : 0;
    else if (f.type === 'ref') out[f.key] = el.value ? Number(el.value) : null;
    else out[f.key] = el.value;
  });
  return out;
}

function bindFileFields(root) {
  $$('[data-filepick]', root).forEach(b => {
    const key = b.dataset.filepick, inp = $('#f_' + key + '_file', root);
    b.onclick = () => inp.click();
    inp.onchange = async () => {
      const f = inp.files[0]; if (!f) return;
      if (f.size > 25 * 1024 * 1024) return alert('Die Datei ist zu groß (max. 25 MB).');
      toast('Lade hoch ...');
      const data = f.type.startsWith('image/') ? await shrinkImage(f) : await fileToDataUrl(f);
      const path = await uploadDataUrl(data, f.name, false);
      $('#f_' + key, root).value = path;
      const l = $('#f_' + key + '_link', root); l.href = path; l.style.display = '';
      toast('Hochgeladen');
    };
  });
  $$('[data-fileclear]', root).forEach(b => b.onclick = () => {
    const key = b.dataset.fileclear;
    $('#f_' + key, root).value = ''; $('#f_' + key + '_link', root).style.display = 'none';
  });
  $$('[data-filesbox]', root).forEach(box => {
    const key = box.dataset.filesbox, hidden = $('#f_' + key, root), inp = $('#f_' + key + '_file', root);
    const draw = () => {
      const list = parseFiles(hidden.value);
      $('#f_' + key + '_list', root).innerHTML = list.map((x, i) => `<li>
        <a href="${esc(x.path)}" target="_blank" rel="noopener" ${INLINE_EXT.test(x.path) ? '' : `download="${esc(x.name)}"`}>${esc(x.name)}</a>
        <span class="muted small">${fmtSize(x.size)}${x.added ? ', ' + fmtDate(x.added) : ''}</span>
        ${hidden.disabled ? '' : `<button type="button" class="btn sm ghost" data-filesrm="${i}">Entfernen</button>`}</li>`).join('')
        || '<li class="muted small">Noch keine Dateien</li>';
      $$('[data-filesrm]', box).forEach(b => b.onclick = () => {
        const l = parseFiles(hidden.value); l.splice(Number(b.dataset.filesrm), 1);
        hidden.value = JSON.stringify(l); draw();
      });
    };
    const maxMb = Number($('[data-filesadd]', box).dataset.maxmb) || 25;
    const add = async files => {
      for (const f of files) {
        if (f.size > maxMb * 1024 * 1024) { alert(`${f.name} ist zu groß (max. ${maxMb} MB).`); continue; }
        toast(`Lade ${f.name} hoch ...`);
        try {
          const path = await uploadDataUrl(await fileToDataUrl(f), f.name, false);
          const l = parseFiles(hidden.value); l.push({ name: f.name, path, size: f.size, added: todayStr() });
          hidden.value = JSON.stringify(l); draw();
        } catch (e) { alert(`${f.name} konnte nicht hochgeladen werden: ${e.message}`); }
      }
      toast('Hochgeladen. Zum Übernehmen speichern.');
    };
    $('[data-filesadd]', box).onclick = () => inp.click();
    inp.onchange = () => { add([...inp.files]); inp.value = ''; };
    box.ondragover = e => { if (hidden.disabled) return; e.preventDefault(); box.classList.add('over'); };
    box.ondragleave = () => box.classList.remove('over');
    box.ondrop = e => { e.preventDefault(); box.classList.remove('over'); if (!hidden.disabled) add([...e.dataTransfer.files]); };
    box.redraw = draw;  // nach Änderung von außen (z. B. Dateien vom Sponsor übernehmen)
    draw();
  });
}

function bindImageFields(root) {
  bindFileFields(root);
  $$('[data-imgpick]', root).forEach(b => b.onclick = async () => {
    const key = b.dataset.imgpick;
    const path = await pickImage();
    if (path) {
      const inp = $('#f_' + key, root); inp.value = path;
      const p = $('#f_' + key + '_prev', root); p.src = path; p.style.opacity = 1;
      inp.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });
  $$('[data-imgclear]', root).forEach(b => b.onclick = () => {
    const key = b.dataset.imgclear;
    const inp = $('#f_' + key, root); inp.value = '';
    const p = $('#f_' + key + '_prev', root); p.removeAttribute('src'); p.style.opacity = .3;
    inp.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

/* Bildauswahl: aus Mediathek oder neu hochladen. Liefert Pfad oder null. */
function pickImage() {
  return new Promise(async resolve => {
    const media = await load('media', true);
    const layer = document.createElement('div');
    layer.className = 'modal';
    layer.style.zIndex = 70;
    layer.innerHTML = `<div class="modal-box" style="width:min(900px,100%)">
      <h2>Bild wählen</h2>
      <div class="dropzone" id="pk_drop">Bild hierher ziehen oder <button class="btn sm" id="pk_up">Datei hochladen</button>
        <input type="file" id="pk_file" accept="image/*" multiple hidden></div>
      <input class="input" id="pk_q" placeholder="Mediathek durchsuchen (Name, Tags)" style="margin-bottom:10px">
      <div class="media-grid" id="pk_grid" style="max-height:52vh;overflow:auto"></div>
      <div class="modal-foot"><span class="hint">Tipp: Spielfotos in der Mediathek mit Tags versehen, z. B. Spielname oder Spieler.</span><button class="btn" id="pk_cancel">Abbrechen</button></div>
    </div>`;
    document.body.appendChild(layer);
    const done = v => { layer.remove(); resolve(v); };
    const render = () => {
      const q = $('#pk_q', layer).value.toLowerCase();
      const items = [...media].reverse().filter(m => !q || (m.name + ' ' + (m.tags || '')).toLowerCase().includes(q));
      $('#pk_grid', layer).innerHTML = items.length ? items.map(m => `<figure data-p="${esc(m.path)}"><img loading="lazy" src="${esc(m.path)}"><figcaption>${esc(m.tags || m.name)}</figcaption></figure>`).join('') : '<div class="empty">Noch keine Bilder in der Mediathek</div>';
      $$('figure', layer).forEach(f => f.onclick = () => done(f.dataset.p));
    };
    const handleFiles = async files => {
      let last = null;
      for (const f of files) last = await uploadFile(f);
      if (last) done(last);
    };
    $('#pk_q', layer).oninput = render;
    $('#pk_cancel', layer).onclick = () => done(null);
    $('#pk_up', layer).onclick = () => $('#pk_file', layer).click();
    $('#pk_file', layer).onchange = e => handleFiles([...e.target.files]);
    const dz = $('#pk_drop', layer);
    dz.ondragover = e => { e.preventDefault(); dz.classList.add('over'); };
    dz.ondragleave = () => dz.classList.remove('over');
    dz.ondrop = e => { e.preventDefault(); dz.classList.remove('over'); handleFiles([...e.dataTransfer.files].filter(f => f.type.startsWith('image/'))); };
    layer.addEventListener('mousedown', e => { if (e.target === layer) done(null); });
    render();
  });
}

/* Generisches Bearbeiten-Formular für eine Tabelle */
async function editRecord(table, fields, record = {}, opts = {}) {
  const refs = [...new Set(fields.filter(f => f.type === 'ref').map(f => f.ref.table))];
  await loadAll(...refs);
  const isNew = !record.id;
  const ro = !!App.readOnly && !opts.allowWrite;
  openModal(`
    <h2>${esc(isNew ? (opts.newTitle || 'Neu anlegen') : (opts.editTitle || 'Bearbeiten'))}</h2>
    <form class="form" id="recForm" onsubmit="return false">${fields.map(f => fieldHtml(f, record[f.key])).join('')}</form>
    <div class="modal-foot">
      <div>${!isNew && !ro ? '<button class="btn danger" id="recDel">Löschen</button>' : ''}</div>
      <div class="btn-row"><button class="btn" id="recCancel">${ro ? 'Schließen' : 'Abbrechen'}</button>${ro ? '' : '<button class="btn primary" id="recSave">Speichern</button>'}</div>
    </div>`);
  const box = $('#modalBox');
  if (ro) { $$('input, select, textarea', $('#recForm')).forEach(el => el.disabled = true); $$('#recForm .btn').forEach(b => b.style.display = 'none'); }
  bindImageFields(box);
  const applyShow = () => {
    const vals = readForm(box, fields);
    fields.forEach(f => { if (f.show) { const el = $(`[data-fkey="${f.key}"]`, box) || $('#f_' + f.key, box)?.closest('.field'); if (el) el.style.display = f.show(vals) ? '' : 'none'; } });
  };
  box.addEventListener('change', applyShow); applyShow();
  if (opts.onOpen) opts.onOpen(box);
  return new Promise(resolve => {
    $('#recCancel').onclick = () => { closeModal(); resolve(null); };
    if (ro) return;
    $('#recSave').onclick = async () => {
      const vals = { ...(opts.fixed || {}), ...readForm(box, fields) };
      if (opts.beforeSave) opts.beforeSave(vals);
      try {
        const saved = isNew ? await api(table, 'POST', vals) : await api(`${table}/${record.id}`, 'PUT', vals);
        invalidate(table); closeModal(); toast('Gespeichert'); resolve(saved);
      } catch (e) { alert('Speichern fehlgeschlagen: ' + e.message); }
    };
    if (!isNew) $('#recDel').onclick = async () => {
      if (!confirmBox('Wirklich löschen?')) return;
      try { await api(`${table}/${record.id}`, 'DELETE'); } catch (e) { alert('Löschen nicht möglich: ' + e.message); return; }
      invalidate(table, 'assignments'); closeModal(); toast('Gelöscht'); resolve({ deleted: true });
    };
  });
}

/* ---------- Router ---------- */
async function route() {
  const hash = location.hash.replace(/^#\/?/, '');
  const [page, ...args] = hash.split('/');
  const name = page || 'dashboard';
  $$('#nav a').forEach(a => a.classList.toggle('active', a.dataset.page === name));
  markTab(name);
  refreshNavCounts();
  let fn = App.pages[name] || App.pages.dashboard;
  const view = $('#view');
  const area = PAGE_AREA[name];
  App.readOnly = false;
  if (area && !can(area)) {
    fn = v => { v.innerHTML = `<div class="card empty"><h2>Kein Zugriff</h2>Für diesen Bereich hast du keine Rechte. Wende dich an den Vorstand oder Admin.</div>`; };
  } else if (area && area !== 'admin' && !can(area, 2)) {
    App.readOnly = true;
  }
  document.body.toggleAttribute('data-ro', App.readOnly);
  setNav(false);
  if (window.innerWidth <= 700) window.scrollTo(0, 0);
  try { await fn(view, args); }
  catch (e) { view.innerHTML = `<div class="card">Fehler: ${esc(e.message)}</div>`; console.error(e); }
  $('#main').scrollTop = 0;
}
window.addEventListener('hashchange', route);

/* Handy: Menü als Schublade, App auf dem Startbildschirm */
/* Menü auf dem Handy: solange es offen ist, steht die Seite dahinter still. Über overflow:hidden an html/body (Klasse nav-lock),
   nicht über position:fixed: das verschob in der iPhone-App beim Scrollen im Menü die ganze Seite und zeigte unten einen hellen Streifen. */
function setNav(open) {
  const b = document.body;
  if (open === b.classList.contains('nav-open')) return;
  b.classList.toggle('nav-open', open);
  document.documentElement.classList.toggle('nav-lock', open);
}
$('#navToggle').onclick = () => setNav(!document.body.classList.contains('nav-open'));
$('#navShade').onclick = () => setNav(false);
// Service Worker nur für den Hub, nicht für die öffentliche Webseite
if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js', { scope: '/hub' }).catch(() => {});

/* Hinweis „Als App installieren“ auf dem Handy: Android mit Knopf (beforeinstallprompt), iPhone mit Anleitung
   (Apple erlaubt keinen Knopf). Nicht, wenn der Hub schon als App läuft; „Später“ blendet ihn 30 Tage aus. */
let installEvent = null;
window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); installEvent = e; showInstallHint(); });
window.addEventListener('appinstalled', () => { $('#installHint')?.remove(); });
function installHintMuted() {
  try { return Date.now() - Number(localStorage.getItem('tmh_install_later') || 0) < 30 * 864e5; } catch { return false; }
}
function showInstallHint() {
  const standalone = matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const ios = /iPhone|iPad|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
  const android = /Android/.test(navigator.userAgent);
  if (standalone || installHintMuted() || !(ios || android) || !App.me) return;
  $('#installHint')?.remove();
  const text = installEvent ? 'Installiere den Wolthusen Hub als App auf deinem Handy, dann ist er mit einem Tipp auf dem Startbildschirm.'
    : ios ? 'Wolthusen Hub als App: Tippe unten auf <b>Teilen</b> (Quadrat mit Pfeil nach oben) und dann auf <b>„Zum Home-Bildschirm“</b>.'
      : 'Wolthusen Hub als App: Tippe oben rechts auf <b>⋮</b> und dann auf <b>„App installieren“</b> bzw. <b>„Zum Startbildschirm hinzufügen“</b>.';
  document.body.insertAdjacentHTML('beforeend', `<div id="installHint" role="dialog" aria-label="App installieren" style="position:fixed;left:12px;right:12px;bottom:12px;z-index:90;
      background:#15122B;color:#fff;border-radius:12px;padding:14px 16px;box-shadow:0 10px 30px rgba(0,0,0,.35);display:flex;gap:12px;align-items:center">
    <img src="/static/icon-192.png" alt="" width="44" height="44" style="border-radius:10px;flex:none">
    <div style="flex:1;font-size:14px;line-height:1.45">${text}</div>
    <div style="display:grid;gap:6px;flex:none">${installEvent ? '<button class="btn primary sm" id="installYes">Installieren</button>' : ''}
      <button class="btn sm" id="installLater" style="background:transparent;color:#fff;border-color:#555">${installEvent ? 'Später' : 'OK'}</button></div></div>`);
  $('#installLater').onclick = () => { try { localStorage.setItem('tmh_install_later', String(Date.now())); } catch { /* ohne Speicher: nur ausblenden */ } $('#installHint')?.remove(); };
  if ($('#installYes')) $('#installYes').onclick = async () => {
    const ev = installEvent; installEvent = null; $('#installHint')?.remove();
    try { ev.prompt(); await ev.userChoice; } catch { /* Browser hat abgelehnt */ }
  };
}
// Ohne Install-Ereignis (iPhone, oder Android mit ungültigem Zertifikat auf dem Test-Server) nach kurzer Zeit die Anleitung zeigen
setTimeout(showInstallHint, 4000);   // spätestens dann (App.me ist geladen); mit Install-Ereignis erscheint der Knopf

/* Push-Benachrichtigungen auf diesem Gerät (Web Push). iPhone: nur wenn der Hub als App auf dem Startbildschirm liegt (iOS 16.4+). */
const pushSupported = () => 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
const pushIOSNeedsApp = () => /iPhone|iPad|iPod/.test(navigator.userAgent) && !(matchMedia('(display-mode: standalone)').matches || navigator.standalone === true);
async function pushReg() { return navigator.serviceWorker.getRegistration('/hub') || navigator.serviceWorker.register('/sw.js', { scope: '/hub' }); }
async function pushCurrent() { try { const r = await pushReg(); return r ? await r.pushManager.getSubscription() : null; } catch { return null; } }
async function pushEnable() {
  if (!pushSupported()) throw new Error(pushIOSNeedsApp() ? 'Auf dem iPhone gehen Push-Nachrichten nur, wenn der Hub als App auf dem Home-Bildschirm liegt. Bitte zuerst „Zum Home-Bildschirm“ und den Hub von dort öffnen.' : 'Dieser Browser unterstützt keine Push-Nachrichten.');
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') throw new Error('Benachrichtigungen wurden nicht erlaubt. Das lässt sich in den Einstellungen des Browsers bzw. Handys ändern.');
  const { key } = await api('push/key');
  const raw = Uint8Array.from(atob(key.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - key.length % 4) % 4)), c => c.charCodeAt(0));
  const reg = await pushReg(); await navigator.serviceWorker.ready;
  let sub = await reg.pushManager.getSubscription();
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: raw });
  await api('push/subscribe', 'POST', sub.toJSON());
  return sub;
}
async function pushDisable() {
  const sub = await pushCurrent(); if (!sub) return;
  try { await api('push/unsubscribe', 'POST', { endpoint: sub.endpoint }); } catch { /* trotzdem abmelden */ }
  await sub.unsubscribe();
}

/* Zahl am App-Symbol setzen und Meldungen zu inzwischen erledigten Mails/Aufgaben vom Handy räumen */
async function syncAppBadge(r) {
  try { r = r || await api('mailtasks'); } catch { return; }
  try { if ('setAppBadge' in navigator) { r.badge > 0 ? navigator.setAppBadge(r.badge) : navigator.clearAppBadge(); } } catch { /* nicht unterstützt */ }
  try {
    const reg = 'serviceWorker' in navigator ? await navigator.serviceWorker.getRegistration('/hub') : null;
    if (!reg) return;
    const keep = new Set([...(r.inbox || []).map(x => 'mail-' + x.id), ...r.mine.filter(t => t.status === 'offen').map(t => 'task-' + t.id)]);
    (await reg.getNotifications()).forEach(n => { if (/^(mail|task)-\d+$/.test(n.tag) && !keep.has(n.tag)) n.close(); });
  } catch { /* ohne Service Worker */ }
}

/* Hinweis beim Öffnen des Hubs: neue Mail-Aufgaben (wie ein Banner unten), mit „Push aktivieren“, falls noch aus */
async function showTaskBanner() {
  let r; try { r = await api('mailtasks'); } catch { return; }
  syncAppBadge(r);
  const fresh = r.mine.filter(t => t.status === 'offen' && !Number(t.banner_seen));
  if (!fresh.length) return;
  const pushOff = pushSupported() && !(await pushCurrent());
  $('#taskBanner')?.remove();
  document.body.insertAdjacentHTML('beforeend', `<div id="taskBanner" role="dialog" aria-label="Neue Mail-Aufgaben" class="task-banner">
    <div class="tb-icon">✉</div>
    <div class="tb-text"><b>${fresh.length === 1 ? 'Neue Mail-Aufgabe für dich' : fresh.length + ' neue Mail-Aufgaben für dich'}</b>
      ${fresh.slice(0, 3).map(t => `<div class="small">${esc(t.subject)} <span class="muted">von ${esc(pfName(t.sender))}, zugewiesen von ${esc(t.by_name)}</span></div>`).join('')}
      ${pushOff ? '<div class="small" style="margin-top:4px">Tipp: Mit Push bekommst du neue Aufgaben direkt aufs Handy.</div>' : ''}</div>
    <div class="tb-btns"><button class="btn primary sm" id="tb_open">Öffnen</button>${pushOff ? '<button class="btn sm" id="tb_push">Push aktivieren</button>' : ''}
      <button class="btn sm tb-later" id="tb_later">Später</button></div></div>`);
  const seen = async () => { $('#taskBanner')?.remove(); await Promise.all(fresh.map(t => api(`mailtasks/${t.id}/seen`, 'POST').catch(() => {}))); };
  $('#tb_open').onclick = async () => { await seen(); location.hash = fresh.length === 1 ? `#/mailaufgabe/${fresh[0].id}` : '#/'; };
  $('#tb_later').onclick = seen;
  if ($('#tb_push')) $('#tb_push').onclick = async () => { try { await pushEnable(); toast('Push aktiviert'); $('#tb_push').remove(); } catch (e) { alert(e.message); } };
}
const pfName = f => { const m = String(f || '').match(/^\s*"?([^"<]*?)"?\s*<([^>]+)>/); return m ? (m[1].trim() || m[2]) : String(f || ''); };
function go(h) { if (location.hash === h) route(); else location.hash = h; }

/* Start erfolgt in static/pages/99-start.js (die Seiten liegen in static/pages/, geladen in der Reihenfolge aus index.html) */
