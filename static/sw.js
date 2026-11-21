/* Wolthusen Hub: Service Worker für die App auf dem Startbildschirm.
   Speichert bewusst nichts zwischen (keine Vereinsdaten auf dem Handy), zeigt ohne Netz nur einen Hinweis. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', e => {
  if (e.request.mode !== 'navigate') return;
  e.respondWith(fetch(e.request).catch(() => new Response(
    '<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">' +
    '<title>Keine Verbindung</title><body style="font-family:system-ui,sans-serif;background:#0b0b0b;color:#fff;display:grid;place-items:center;height:100vh;margin:0;text-align:center">' +
    '<div><h2>Keine Verbindung</h2><p>Der Hub braucht Internet. Bitte später erneut versuchen.</p>' +
    '<button onclick="location.reload()" style="padding:10px 18px;border-radius:8px;border:0;background:#3D2F96;color:#fff">Erneut laden</button></div></body></html>',
    { headers: { 'Content-Type': 'text/html; charset=utf-8' } })));
});

/* Push-Benachrichtigungen (z. B. neue Mail-Aufgabe). Der Inhalt kommt Ende-zu-Ende verschlüsselt vom Hub, gespeichert wird nichts. */
self.addEventListener('push', e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { body: e.data ? e.data.text() : '' }; }
  const setBadge = () => {   // Zahl am App-Symbol (iPhone ab iOS 16.4 als App, Android/Chrome je nach Startbildschirm)
    const nav = self.navigator;
    if (typeof d.badge !== 'number' || !nav || !('setAppBadge' in nav)) return Promise.resolve();
    return (d.badge > 0 ? nav.setAppBadge(d.badge) : nav.clearAppBadge()).catch(() => {});
  };
  const tag = d.tag || 'hub';
  const show = self.registration.showNotification(d.title || 'Wolthusen Hub', {
    body: d.body || '', icon: '/static/icon-192.png', badge: '/static/icon-192.png', tag, renotify: d.type !== 'done', silent: d.type === 'done',
    data: { url: (typeof d.url === 'string' && d.url.startsWith('/')) ? d.url : '/hub' },
  });
  // „Erledigt“: ersetzt die alte Meldung mit gleichem Tag und schließt sich nach ein paar Sekunden selbst
  const closeLater = d.type === 'done'
    ? show.then(() => new Promise(r => setTimeout(r, 4000))).then(() => self.registration.getNotifications({ tag })).then(list => list.forEach(n => n.close()))
    : show;
  e.waitUntil(Promise.all([closeLater, setBadge()]));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/hub';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
    const open = list.find(c => new URL(c.url).pathname.startsWith('/hub'));
    if (open) { open.navigate(url).catch(() => {}); return open.focus(); }
    return self.clients.openWindow(url);
  }));
});
