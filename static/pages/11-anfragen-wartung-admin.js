/* ====================================================================== */
/* Anfragen über das Kontaktformular der Webseite */
const CONTACT_STATUS = ['Neu', 'In Bearbeitung', 'Erledigt'];
F.contact_requests = [
  { key: 'status', label: 'Status', type: 'select', options: CONTACT_STATUS },
  { key: 'created', label: 'Eingang', type: 'text' },
  { key: 'name', label: 'Name' },
  { key: 'email', label: 'E-Mail' },
  { key: 'phone', label: 'Telefon' },
  { key: 'source', label: 'Über' },
  { key: 'message', label: 'Nachricht', type: 'textarea', rows: 6 },
  { key: 'notes', label: 'Interne Notizen', type: 'textarea', rows: 3 },
];
App.pages.contacts = simpleList({
  table: 'contact_requests', title: 'Anfragen', fields: F.contact_requests, newTitle: 'Anfrage',
  sub: l => `${l.filter(r => r.status === 'Neu').length} neu, ${l.length} insgesamt. Kommen über das Kontaktformular der Webseite.`,
  sort: (a, b) => (CONTACT_STATUS.indexOf(a.status) - CONTACT_STATUS.indexOf(b.status)) || (b.created || '').localeCompare(a.created || ''),
  columns: [
    { label: 'Eingang', html: r => `<span class="small">${fmtStamp(r.created)}</span>` },
    { label: 'Name', html: r => `<b>${esc(r.name || '')}</b><div class="muted small">${esc((r.message || '').slice(0, 90))}${(r.message || '').length > 90 ? ' ...' : ''}</div>` },
    { label: 'Kontakt', html: r => [r.email ? `<a href="mailto:${esc(r.email)}">${esc(r.email)}</a>` : '', r.phone ? `<a href="tel:${esc(r.phone)}">${esc(r.phone)}</a>` : ''].filter(Boolean).join('<br>') },
    { label: 'Status', html: r => `<span class="badge ${r.status === 'Neu' ? 'red' : r.status === 'Erledigt' ? 'ok' : 'warn'}">${esc(r.status || 'Neu')}</span>` },
  ],
});

/* ====================================================================== */
/* Änderungsprotokoll (nur Admins) */
const TABLE_NAMES = { shop_products: 'Fanshop', sponsor_packages: 'Sponsorenpakete', mail_accounts: 'E-Mails', admin_notes: 'Notizen', posts: 'Postplan', games: 'Spielplan', players: 'Kader & Trainer', opponents: 'Gegner', trainings: 'Trainingszeit', bookings: 'Belegung', sponsors: 'Sponsoren', media: 'Mediathek',
  media_team: 'Media Team', assignments: 'Einteilung', members: 'Mitglieder', transactions: 'Buchungen', supporter_cards: 'Dauerkarte',
  magazines: 'Stadionheft', magazine_pages: 'Stadionheft-Beitrag', apparel: 'Teamkleidung', apparel_orders: 'Bestellung', story_rules: 'Story-Regel',
  settings: 'Einstellungen', social: 'Auto-Posting', users: 'Konten', groups: 'Gruppen', backup: 'Backup', sheet_players: 'Social Media Spieler',
  contact_requests: 'Anfragen', player_signups: 'Spielerbogen', card_orders: 'Dauerkarte Bestellung' };

/* Wartungsmodus der Webseite: Besucher sehen nur die Wartungsseite. Lesen = Webseite trotzdem sehen, Bearbeiten = schalten und Text/Bild ändern */
const MAINT_FIELDS = [
  { key: 'title', label: 'Überschrift', full: true },
  { key: 'text', label: 'Text', type: 'textarea', rows: 5 },
  { key: 'until', label: 'Voraussichtlich wieder da (optional)', type: 'datetime-local', full: true,
    hint: 'Erscheint als „Voraussichtlich wieder da: ...“. Leer lassen, wenn es noch offen ist.' },
];
App.pages.wartung = async (view) => {
  const m = await api('maintenance');
  const ed = m.can_edit;
  const last = m.last ? `Zuletzt ${esc(m.last.action)} am ${fmtStamp(m.last.time)} von ${esc(m.last.user_name || 'unbekannt')}.` : '';
  view.innerHTML = `
    <div class="page-head"><h1>Wartungsmodus<small>Öffentliche Webseite vorübergehend durch eine Wartungsseite ersetzen</small></h1>
      <div class="btn-row"><a class="btn keep" href="/?wartung-vorschau=1" target="_blank" rel="noopener">Wartungsseite öffnen</a>
        <a class="btn keep" href="/" target="_blank" rel="noopener">Webseite öffnen</a></div></div>
    <div class="card maint-state ${m.on ? 'on' : ''}" style="margin-bottom:16px">
      <div class="grow"><h2 style="margin:0 0 4px">${m.on ? 'Wartungsmodus ist an' : 'Wartungsmodus ist aus'}</h2>
        <p class="muted small" style="margin:0">${m.on ? 'Besucher sehen gerade die Wartungsseite. Du und die Gruppe „Wartung“ sehen die Webseite normal, solange ihr angemeldet seid.'
          : 'Die Webseite ist für alle erreichbar.'} ${last}</p></div>
      ${ed ? `<button class="btn ${m.on ? 'primary' : 'danger-fill'}" id="mt_toggle">${m.on ? 'Wartungsmodus ausschalten' : 'Wartungsmodus einschalten'}</button>` : ''}
    </div>
    <div class="grid2">
      <div class="card"><h2>Text der Wartungsseite</h2>
        <form class="form" id="mt_form" onsubmit="return false">${MAINT_FIELDS.map(f => fieldHtml(f, f.key === 'until' && m.until.length === 10 ? m.until + 'T00:00' : m[f.key])).join('')}</form>
        ${ed ? '<div class="btn-row"><button class="btn primary" id="mt_save">Text speichern</button><button class="btn ghost" id="mt_until_clear">Zeitpunkt leeren</button></div>' : ''}
        <p class="muted small" style="margin-top:12px">Darunter stehen automatisch Instagram und die Kontakt-E-Mail aus den Webseiten-Texten, unten Impressum und Datenschutz.</p>
      </div>
      <div class="card web-img"><h2>Bild der Wartungsseite ${m.image.own ? '<span class="badge ok">eigenes Bild</span>' : '<span class="badge">Titelbild der Startseite</span>'}</h2>
        <div class="web-img-pic"><img src="${esc(m.image.preview)}" alt=""></div>
        <p class="muted small">Großes Hintergrundbild, wird abgedunkelt. Am besten Querformat ab 1920 px Breite. Ohne eigenes Bild nimmt die Seite das Titelbild der Startseite.</p>
        ${ed ? `<label class="small">Alt-Text<textarea class="input" rows="2" id="mt_alt">${esc(m.image.alt)}</textarea></label>
        <div class="btn-row" style="margin-top:8px"><button class="btn sm primary" id="mt_up">${m.image.own ? 'Bild ersetzen' : 'Eigenes Bild hochladen'}</button>
          ${m.image.own ? '<button class="btn sm" id="mt_alt_save">Alt-Text speichern</button><button class="btn sm ghost" id="mt_reset">Titelbild nehmen</button>' : ''}
          <input type="file" id="mt_file" accept="image/jpeg,image/png,image/webp" hidden></div>` : ''}
      </div>
    </div>
    <div class="card" style="margin-top:16px"><h2>Wer sieht was?</h2>
      <ul class="checklist plain">
        <li><b>Besucher</b> sehen auf allen Seiten nur die Wartungsseite. Kontaktformular und Kartenbestellung nehmen nichts an.</li>
        <li><b>Erreichbar bleiben</b>: Impressum, Datenschutz, Spielerbogen, Storno-Links der Dauerkarte, Bestelllinks der Teamkleidung, Kalender-Abos und der ganze Hub.</li>
        <li><b>Angemeldet mit Recht „Wartung“</b> (Lesen) sieht die Webseite normal, mit einem Hinweis oben. Mit „Bearbeiten“ auch schalten und Text und Bild ändern. Admins dürfen immer.</li>
        <li>Dafür gibt es die Gruppe <b>„Wartung“</b>${App.me.is_admin ? ' unter <a href="#/groups">Gruppen &amp; Rechte</a>. Personen zuordnen unter <a href="#/accounts">Konten</a>' : ''}.</li>
      </ul></div>
    <div class="card" style="margin-top:16px"><div class="page-head" style="margin:0 0 10px"><h2 style="margin:0">Vorschau</h2></div>
      <iframe class="web-preview" src="/?wartung-vorschau=1" title="Vorschau der Wartungsseite" style="width:100%;height:560px;border:1px solid var(--line, #ddd);border-radius:6px"></iframe></div>`;
  if (!ed) { $$('#mt_form input, #mt_form textarea').forEach(el => { el.disabled = true; }); return; }
  const reload = () => App.pages.wartung(view);
  $('#mt_toggle').onclick = async () => {
    const on = !m.on;
    if (!confirmBox(on ? 'Wartungsmodus einschalten? Besucher sehen dann nur noch die Wartungsseite.' : 'Wartungsmodus ausschalten? Die Webseite ist dann wieder für alle sichtbar.')) return;
    await api('maintenance', 'PUT', { on }); toast(on ? 'Wartungsmodus ist an' : 'Wartungsmodus ist aus'); reload();
  };
  $('#mt_save').onclick = async () => {
    const r = readForm($('#mt_form'), MAINT_FIELDS);
    const vals = { title: r.title.trim(), text: r.text.trim(), until: r.until };
    if (!vals.title || !vals.text) return alert('Bitte Überschrift und Text ausfüllen.');
    if ((hasDashes(vals.title) || hasDashes(vals.text)) && !confirmBox('Im Text stehen Gedankenstriche. Trotzdem speichern?')) return;
    await api('maintenance', 'PUT', vals); toast('Text gespeichert'); reload();
  };
  $('#mt_until_clear').onclick = () => { $('#f_until').value = ''; };
  const alt = () => $('#mt_alt').value.trim();
  $('#mt_up').onclick = () => $('#mt_file').click();
  $('#mt_file').onchange = async () => {
    const f = $('#mt_file').files[0]; if (!f) return;
    if (!alt() && !confirmBox('Ohne Alt-Text hochladen? Besser vorher kurz beschreiben, was zu sehen ist.')) return;
    try {
      toast('Bild wird vorbereitet ...');
      const v = await webpVariants(f);
      await api('maintenance/image', 'POST', { ...v, alt: alt() }); toast('Bild gespeichert'); reload();
    } catch (e) { alert(e.message); }
  };
  if ($('#mt_alt_save')) $('#mt_alt_save').onclick = async () => { await api('maintenance/image', 'PUT', { alt: alt() }); toast('Alt-Text gespeichert'); };
  if ($('#mt_reset')) $('#mt_reset').onclick = async () => {
    if (!confirmBox('Eigenes Bild entfernen und wieder das Titelbild der Startseite nehmen?')) return;
    await api('maintenance/image', 'DELETE'); toast('Titelbild wird genutzt'); reload();
  };
};

/* Admin: Zustand des Servers, Update-Anleitung, Befehle und Notfall (nur Admins, Daten aus /api/admin/info) */
const ADMIN_TABS = [['', 'Übersicht'], ['updates', 'Updates'], ['planung', 'Planung']];
function adminHead(tab, sub, extra = '') {
  return `<div class="page-head"><h1>Admin<small>${sub}</small></h1><div class="btn-row">${extra}</div></div>
    <div class="toolbar">${ADMIN_TABS.map(([k, l]) => `<a class="btn sm ${k === tab ? 'dark' : ''}" href="#/admin${k ? '/' + k : ''}">${l}</a>`).join('')}</div>`;
}

App.pages.admin = async (view, args = []) => {
  if (args[0] === 'planung') return adminPlanning(view);
  if (args[0] === 'updates') return adminUpdates(view);
  const d = await api('admin/info' + (args[0] === 'neu' ? '?neu=1' : ''));
  const host = (d.site_url || location.origin).replace(/^https?:\/\//, '');
  const gb = n => (n / 2 ** 30).toFixed(1).replace('.', ',') + ' GB';
  const cmd = (text, note = '') => `<div class="cmd"><code>${esc(text)}</code><button type="button" class="btn sm keep" data-copy="${esc(text)}">Kopieren</button>${note ? `<span class="muted small">${note}</span>` : ''}</div>`;
  const yesNo = (ok, okText, noText, link) => `<div class="check-row"><span class="dot ${ok ? 'ok' : 'warn'}"></span><span style="flex:1">${ok ? okText : noText}</span>${!ok && link ? `<a class="btn sm" href="${link}">Einrichten</a>` : ''}</div>`;
  const dir = d.host_dir, u = d.users, s = d.status;
  const since = d.uptime_h >= 24 ? `${Math.floor(d.uptime_h / 24)} Tagen` : d.uptime_h >= 1 ? `${Math.floor(d.uptime_h)} Stunden` : 'unter 1 Stunde';
  const commands = [
    ['Status aller Container', 'docker ps'],
    ['Logs des Hubs', `cd ${dir} && docker compose logs -f --tail 100`],
    ...(d.behind_proxy ? [['Logs des Proxys (Zertifikate, Fehler)', `cd ${d.proxy_dir} && docker compose logs -f --tail 100`]] : []),
    ['Hub neu starten', `cd ${dir} && docker compose restart`],
    ...(d.behind_proxy ? [['Proxy neu starten', `cd ${d.proxy_dir} && docker compose restart`],
      ['Caddyfile neu laden (ohne Unterbrechung)', `cd ${d.proxy_dir} && docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile`],
      ['Caddy aktualisieren', `cd ${d.proxy_dir} && docker compose pull && docker compose up -d`]] : []),
    ['Installierte Version', `cd ${dir} && git log -1 --oneline`],
    ['Speicherplatz', 'df -h /'],
    ['Firewall', 'sudo ufw status verbose'],
    ['Gesperrte IPs (SSH)', 'sudo fail2ban-client status sshd'],
    ['Neustart nach Systemupdates nötig?', 'ls /var/run/reboot-required'],
  ];
  view.innerHTML = `
    ${adminHead('', 'Server, Updates und wichtige Abläufe. Nur für Admins sichtbar.',
      `<a class="btn keep" href="#/admin/neu">Neu prüfen</a><a class="btn keep" href="${esc(d.repo)}/blob/main/CHANGELOG.md" target="_blank" rel="noopener">Änderungen (CHANGELOG)</a>`)}
    ${d.checks.length ? `<div class="card" style="margin-bottom:16px"><h2>Hinweise</h2><ul class="checklist">${d.checks.map(c =>
      `<li class="${c.level === 'warn' ? 'warn' : ''}">${c.level === 'warn' ? '<span class="badge warn">offen</span> ' : '<span class="badge">Info</span> '}${esc(c.text)}${c.link ? ` <a href="${esc(c.link)}">Öffnen</a>` : ''}</li>`).join('')}</ul></div>`
      : '<div class="card" style="margin-bottom:16px"><span class="badge ok">Alles in Ordnung</span> Keine offenen Hinweise.</div>'}
    <div class="grid g4" style="margin-bottom:16px">
      <div class="card stat"><span>Version</span><b>${esc(d.version)}</b><span class="muted small">${d.newer ? `Neu auf GitHub: <b>${esc(d.latest)}</b>` : d.latest ? 'aktuell' : esc(d.latest_error || 'nicht geprüft')}</span></div>
      <div class="card stat"><span>Läuft seit</span><b style="font-size:20px">${since}</b><span class="muted small">Start ${fmtStamp(d.started)}</span></div>
      <div class="card stat"><span>Speicher frei</span><b>${gb(d.disk.free)}</b><span class="muted small">von ${gb(d.disk.total)}, Datenbank ${fmtSize(d.db_size)}, Mediathek ${d.media.count} Dateien (${fmtSize(d.media.size)})</span></div>
      <div class="card stat"><span>Konten</span><b>${u.active}</b><span class="muted small">Admins mit 2FA ${u.admins_2fa} von ${u.admins}, alle mit 2FA ${u.with_2fa}${u.pending ? `, ${u.pending} Einladung offen` : ''}</span></div>
    </div>
    <div class="grid g2" style="margin-bottom:16px">
      <div class="card"><h2>Einrichtung</h2>
        ${yesNo(s.smtp, 'E-Mail-Versand eingerichtet', 'E-Mail-Versand fehlt', '#/settings')}
        ${yesNo(s.meta, 'Facebook und Instagram verbunden', 'Facebook und Instagram nicht verbunden', '#/autopost/einrichtung')}
        ${yesNo(s.twofa_admins, 'Zwei-Faktor-Pflicht für Admins an', 'Zwei-Faktor-Pflicht für Admins aus', '#/accounts')}
        ${yesNo(s.twofa_finance, 'Zwei-Faktor-Pflicht für Finanzen an', 'Zwei-Faktor-Pflicht für Finanzen aus', '#/accounts')}
        ${yesNo(!s.maintenance, 'Webseite öffentlich sichtbar', 'Wartungsmodus an (Besucher sehen die Wartungsseite)', '#/wartung')}
      </div>
      <div class="card"><h2>Server und Zugang</h2>
        <ul class="checklist plain">
          <li><b>Adresse</b>: ${esc(d.site_url || location.origin)} (Webseite unter /, Hub unter /hub)</li>
          <li><b>Aufbau</b>: ${d.behind_proxy ? `Docker hinter dem zentralen Proxy (Caddy) in <code>${esc(d.proxy_dir)}</code>, Hub in <code>${esc(dir)}</code>` : `Docker mit eigenem Caddy in <code>${esc(dir)}</code>`}</li>
          <li><b>Daten</b>: <code>${esc(dir)}/data</code> (Datenbank, Mediathek, Sicherungen), Zugangsdaten in <code>${esc(dir)}/.env</code>${d.behind_proxy ? ` und <code>${esc(d.proxy_dir)}/.env</code>` : ''}</li>
          <li><b>SSH</b>: nur mit Schlüssel als <code>${esc(d.ssh_user)}</code> (Putty-Sitzung mit <code>wolthusen_vps.ppk</code>), Anmeldung als root und mit Passwort ist aus. <code>sudo</code> fragt nach dem Passwort von ${esc(d.ssh_user)}.</li>
          <li><b>Schutz</b>: Firewall nur SSH, 80 und 443, Sperre nach falschen SSH-Anmeldungen, Sicherheitsupdates automatisch, HTTPS-Zertifikat erneuert sich selbst.</li>
          <li><b>Technik</b>: Python ${esc(d.python)}, ${d.server ? 'Serverbetrieb' : 'lokaler Betrieb'}</li>
        </ul>
        ${cmd(`ssh -i $env:USERPROFILE\\.ssh\\wolthusen_vps ${d.ssh_user}@${host}`, 'Anmelden aus PowerShell (statt Putty)')}
      </div>
    </div>
    <div class="card" style="margin-bottom:16px"><h2>Update einspielen</h2>
      ${d.newer ? `<p><span class="badge ok">Neu</span> Auf GitHub liegt Version <b>${esc(d.latest)}</b>, hier läuft ${esc(d.version)}.</p>` : ''}
      <ol class="steps">
        <li><b>Am PC</b>: Änderungen committen, in GitHub Desktop oben <b>Current Branch: main</b> wählen und <b>Push origin</b> klicken. Der Server holt immer <code>main</code>.</li>
        <li><b>Auf dem Server</b>: Putty öffnen (Sitzung mit <code>wolthusen_vps.ppk</code>), dann: ${cmd(`cd ${dir} && sudo bash update.sh`, `fragt nach dem Passwort von ${esc(d.ssh_user)}`)}
          Das Skript sichert vorher die Datenbank (<code>data/backups/vor-update-...db</code>), holt den neuen Stand, baut den Hub neu und prüft, ob er antwortet.</li>
        <li><b>Prüfen</b>: Diese Seite neu laden, oben muss die neue Version stehen. Zeigt der Hub „Neue Version verfügbar“, einmal die Seite neu laden.</li>
      </ol>
      <details><summary>Zurück auf eine ältere Version</summary>
        ${cmd(`cd ${dir} && git log --oneline -10`, 'gewünschten Stand suchen')}
        ${cmd(`cd ${dir} && sudo git checkout <commit> && docker compose up -d --build`, '&lt;commit&gt; durch die Nummer ersetzen')}
        ${cmd(`cd ${dir} && sudo git checkout main && sudo bash update.sh`, 'später wieder auf den aktuellen Stand')}
        <p class="muted small">Datenbank-Änderungen sind nur additiv, eine ältere Version läuft mit neueren Daten weiter. Im Notfall die Sicherung von vor dem Update einspielen.</p>
      </details>
    </div>
    <div class="card" style="margin-bottom:16px"><h2>Wichtige Befehle</h2><p class="muted small">In Putty eingeben. Befehle mit sudo fragen nach dem Passwort von ${esc(d.ssh_user)}.</p>
      <div class="table-wrap"><table class="admin-cmds"><tbody>${commands.map(([l, c]) => `<tr><td style="width:32%"><b>${esc(l)}</b></td><td>${cmd(c)}</td></tr>`).join('')}</tbody></table></div></div>
    <div class="grid g2" style="margin-bottom:16px">
      <div class="card"><h2>Sicherungen</h2>
        <p class="muted small">Jede Nacht automatisch, die letzten ${d.backup_keep} Tage bleiben (insgesamt ${d.backup_count} Dateien). Zusätzlich vor jedem Update. Sie liegen auf demselben Server, darum regelmäßig eine Kopie auf den PC holen.</p>
        <div class="list">${d.backups.map(b => `<div class="list-item"><div class="grow"><b>${esc(b.name)}</b><div class="muted small">${fmtStamp(b.time)}</div></div><span class="muted small">${fmtSize(b.size)}</span></div>`).join('') || '<div class="muted">Noch keine Sicherung.</div>'}</div>
        <div class="btn-row" style="margin-top:10px"><a class="btn dark keep" href="/api/backup">Backup herunterladen (ZIP)</a><a class="btn keep" href="#/settings">Serverumzug</a></div>
        ${cmd(`scp -i $env:USERPROFILE\\.ssh\\wolthusen_vps -r ${d.ssh_user}@${host}:${dir}/data/backups .\\WolthusenHub-Sicherung`, 'alle Datenbank-Sicherungen auf den PC (PowerShell)')}
      </div>
      <div class="card"><h2>Notfall</h2>
        <ul class="checklist plain">
          <li><b>Seite nicht erreichbar</b>: <code>docker ps</code>, dann die Logs von Hub${d.behind_proxy ? ' und Proxy' : ''} (Befehle oben).</li>
          <li><b>Zertifikat fehlt</b>: in den Logs des ${d.behind_proxy ? 'Proxys' : 'Hubs'} nach „error“ suchen. Meist zeigt der DNS nicht auf den Server oder Port 80 ist beim Anbieter gesperrt.</li>
          <li><b>Admin-Passwort vergessen</b>: in <code>${esc(dir)}/.env</code> <code>TMH_RESET_PASSWORD=1</code> und <code>TMH_ADMIN_PASSWORD='neues-passwort'</code> setzen, <code>docker compose up -d</code>, danach beide Zeilen wieder entfernen.</li>
          <li><b>2FA-Gerät verloren</b>: mit einem Wiederherstellungscode anmelden oder ein anderer Admin setzt 2FA unter Konten zurück.</li>
          <li><b>SSH-Schlüssel verloren</b>: über die Web-Konsole des Anbieters anmelden und einen neuen Schlüssel in <code>/home/${esc(d.ssh_user)}/.ssh/authorized_keys</code> eintragen.</li>
        </ul>
        <div class="btn-row"><a class="btn keep" href="${esc(d.repo)}/blob/main/deploy/DEPLOY.md" target="_blank" rel="noopener">Ausführliche Anleitung (DEPLOY.md)</a><a class="btn keep" href="#/log">Protokoll</a></div>
      </div>
    </div>`;
  $$('[data-copy]', view).forEach(b => b.onclick = () => copyText(b.dataset.copy));
};

/* Admin > Planung: neue Projekte für den Hub als Board (Tabelle hub_plans, nur Admins) */
const PLAN_STATUS = ['Idee', 'Geplant', 'In Arbeit', 'Erledigt'];
const PLAN_PRIO = ['Hoch', 'Mittel', 'Niedrig'];
const PLAN_CATS = ['Webseite', 'Hub', 'Team', 'Medien', 'Finanzen', 'Server', 'Sonstiges'];
F.hub_plans = [
  { key: 'title', label: 'Projekt', full: true, placeholder: 'z. B. Spieltagsbericht als PDF' },
  { key: 'status', label: 'Stand', type: 'select', options: PLAN_STATUS, default: 'Idee' },
  { key: 'priority', label: 'Wichtigkeit', type: 'select', options: PLAN_PRIO, default: 'Mittel' },
  { key: 'category', label: 'Bereich', type: 'select', options: PLAN_CATS, default: 'Hub' },
  { key: 'target_version', label: 'Geplante Version', placeholder: 'z. B. 4.21' },
  { key: 'due', label: 'Ziel bis', type: 'date' },
  { key: 'description', label: 'Worum geht es?', type: 'textarea', rows: 3, placeholder: 'Ziel, wer es nutzt, was es können soll' },
  { key: 'steps', label: 'Schritte', type: 'textarea', rows: 6, hint: 'Ein Schritt pro Zeile. Erledigte Schritte mit [x] am Anfang, offene mit [ ] oder ohne Zeichen. Auf der Karte lassen sie sich direkt abhaken.' },
  { key: 'notes', label: 'Notizen', type: 'textarea', rows: 3, placeholder: 'Ideen, Links, offene Fragen' },
];
function planSteps(text) {
  return String(text || '').split('\n').map(l => l.trim()).filter(Boolean).map(l => {
    const m = l.match(/^\[( |x|X)\]\s*(.*)$/) || l.match(/^(x)\s+(.*)$/i);
    return m ? { done: m[1].toLowerCase() === 'x', text: m[2] } : { done: false, text: l.replace(/^[-*]\s*/, '') };
  });
}
const planStepsText = steps => steps.map(st => `[${st.done ? 'x' : ' '}] ${st.text}`).join('\n');

async function adminPlanning(view) {
  let list = await load('hub_plans', true);
  const ui = App._plan || (App._plan = { cat: '', q: '', done: true });
  const today = new Date().toISOString().slice(0, 10);
  const prioRank = { Hoch: 0, Mittel: 1, Niedrig: 2 };
  const save = async (rec, vals, msg) => {
    if (vals.status) vals.done_at = vals.status === 'Erledigt' ? (rec.done_at || today) : '';
    await api('hub_plans/' + rec.id, 'PUT', vals); if (msg) toast(msg);
    list = await load('hub_plans', true); draw();
  };
  const edit = async rec => {
    const r = await editRecord('hub_plans', F.hub_plans, rec || { status: 'Idee', priority: 'Mittel', category: 'Hub' },
      { newTitle: 'Neues Projekt', editTitle: 'Projekt bearbeiten',
        beforeSave: v => { v.done_at = v.status === 'Erledigt' ? ((rec && rec.done_at) || today) : ''; } });
    if (r) { list = await load('hub_plans', true); draw(); }
  };
  const card = r => {
    const steps = planSteps(r.steps), done = steps.filter(st => st.done).length;
    const late = r.due && r.due < today && r.status !== 'Erledigt';
    const i = PLAN_STATUS.indexOf(r.status || 'Idee');
    return `<div class="plan-card prio-${esc((r.priority || 'Mittel').toLowerCase())}" draggable="true" data-id="${r.id}">
      <div class="plan-top"><b data-open="${r.id}">${esc(r.title || 'Ohne Titel')}</b></div>
      <div class="plan-tags"><span class="badge ${r.priority === 'Hoch' ? 'red' : r.priority === 'Niedrig' ? '' : 'warn'}">${esc(r.priority || 'Mittel')}</span>
        ${r.category ? `<span class="badge">${esc(r.category)}</span>` : ''}${r.target_version ? `<span class="badge dark">v${esc(r.target_version)}</span>` : ''}
        ${r.due ? `<span class="badge ${late ? 'red' : ''}" title="Ziel">${late ? 'überfällig ' : 'bis '}${fmtDate(r.due)}</span>` : ''}</div>
      ${r.description ? `<p class="plan-desc">${esc(r.description)}</p>` : ''}
      ${steps.length ? `<div class="plan-prog"><span style="width:${Math.round(done / steps.length * 100)}%"></span></div>
        <details class="plan-steps"><summary>${done} von ${steps.length} Schritten</summary>
          ${steps.map((st, k) => `<label class="check"><input type="checkbox" data-step="${r.id}:${k}" ${st.done ? 'checked' : ''}> ${esc(st.text)}</label>`).join('')}</details>` : ''}
      <div class="plan-move">${i > 0 ? `<button class="btn sm" data-move="${r.id}:${i - 1}" title="nach ${PLAN_STATUS[i - 1]}">← ${PLAN_STATUS[i - 1]}</button>` : '<span></span>'}
        <button class="btn sm ghost" data-open="${r.id}">Öffnen</button>
        ${i < PLAN_STATUS.length - 1 ? `<button class="btn sm" data-move="${r.id}:${i + 1}" title="nach ${PLAN_STATUS[i + 1]}">${PLAN_STATUS[i + 1]} →</button>` : '<span></span>'}</div>
    </div>`;
  };
  function draw() {
    const ql = ui.q.toLowerCase();
    const shown = list.filter(r => (!ui.cat || r.category === ui.cat) && (!ql || [r.title, r.description, r.notes, r.steps, r.target_version].join(' ').toLowerCase().includes(ql)));
    const cols = PLAN_STATUS.filter(st => ui.done || st !== 'Erledigt');
    const open = list.filter(r => r.status !== 'Erledigt');
    view.innerHTML = `${adminHead('planung', 'Neue Projekte für den Hub planen. Nur für Admins sichtbar.', '<button class="btn primary" id="pl_new">+ Neues Projekt</button>')}
      <div class="toolbar">
        <input class="input" id="pl_q" placeholder="Suchen ..." value="${esc(ui.q)}" style="max-width:220px">
        <select class="input" id="pl_cat" style="max-width:180px"><option value="">Alle Bereiche</option>${PLAN_CATS.map(c => `<option ${c === ui.cat ? 'selected' : ''}>${c}</option>`).join('')}</select>
        <label class="check"><input type="checkbox" id="pl_done" ${ui.done ? 'checked' : ''}> Erledigte zeigen</label>
        <span class="muted small">${open.filter(r => r.priority === 'Hoch').length} offen mit hoher Wichtigkeit${open.some(r => r.due && r.due < today) ? `, ${open.filter(r => r.due && r.due < today).length} überfällig` : ''}</span>
      </div>
      <div class="plan-board" style="--cols:${cols.length}">${cols.map(st => {
        const items = shown.filter(r => (r.status || 'Idee') === st)
          .sort((a, b) => st === 'Erledigt' ? String(b.done_at || '').localeCompare(String(a.done_at || '')) : (prioRank[a.priority] ?? 1) - (prioRank[b.priority] ?? 1) || String(a.due || '9999').localeCompare(String(b.due || '9999')) || String(a.title).localeCompare(String(b.title)));
        return `<div class="plan-col" data-col="${st}"><h3>${st} <span class="muted">${items.length}</span></h3>${items.map(card).join('') || '<div class="plan-empty">Hierher ziehen</div>'}</div>`;
      }).join('')}</div>
      ${list.length ? '' : '<div class="card empty" style="margin-top:16px">Noch keine Projekte. Mit „+ Neues Projekt“ die erste Idee festhalten.</div>'}`;
    $('#pl_new').onclick = () => edit(null);
    $('#pl_q').oninput = e => { ui.q = e.target.value; const pos = e.target.selectionStart; draw(); const el = $('#pl_q'); el.focus(); el.setSelectionRange(pos, pos); };
    $('#pl_cat').onchange = e => { ui.cat = e.target.value; draw(); };
    $('#pl_done').onchange = e => { ui.done = e.target.checked; draw(); };
    $$('[data-open]', view).forEach(b => b.onclick = () => edit(list.find(r => r.id == b.dataset.open)));
    $$('[data-move]', view).forEach(b => b.onclick = () => { const [id, i] = b.dataset.move.split(':'); const r = list.find(x => x.id == id); save(r, { status: PLAN_STATUS[i] }, 'Verschoben nach ' + PLAN_STATUS[i]); });
    $$('[data-step]', view).forEach(c => c.onchange = () => {
      const [id, k] = c.dataset.step.split(':'); const r = list.find(x => x.id == id);
      const steps = planSteps(r.steps); steps[k].done = c.checked; save(r, { steps: planStepsText(steps) });
    });
    $$('.plan-card', view).forEach(el => el.ondragstart = e => { e.dataTransfer.setData('text/plain', el.dataset.id); el.classList.add('dragging'); });
    $$('.plan-card', view).forEach(el => el.ondragend = () => el.classList.remove('dragging'));
    $$('.plan-col', view).forEach(col => {
      col.ondragover = e => { e.preventDefault(); col.classList.add('over'); };
      col.ondragleave = () => col.classList.remove('over');
      col.ondrop = e => { e.preventDefault(); col.classList.remove('over'); const r = list.find(x => x.id == e.dataTransfer.getData('text/plain'));
        if (r && r.status !== col.dataset.col) save(r, { status: col.dataset.col }, 'Verschoben nach ' + col.dataset.col); };
    });
  }
  draw();
}

/* Admin > Updates: Versionen von Hub, Python, Caddy, Docker und Ubuntu, Updates über den Helfer auf dem VPS (deploy/updater).
   Der Hub schreibt nur ein Wort in data/updater/request, der Helfer führt die feste Aktion aus. Nur Admins mit 2FA, Passwort vor jedem Update. */
async function adminUpdates(view) {
  const d = await api('admin/updates');
  const h = d.helper, busy = d.pending || d.running;
  const cmd = t => `<div class="cmd"><code>${esc(t)}</code><button type="button" class="btn sm keep" data-copy="${esc(t)}">Kopieren</button></div>`;
  const label = a => d.actions[a] || a;
  const old = h && h.checked_at && (Date.now() - new Date(h.checked_at).getTime() > 13 * 3600 * 1000);
  const comps = h ? h.components || [] : [];
  view.innerHTML = `
    ${adminHead('updates', 'Versionen und Updates des Servers', h && !busy ? '<button class="btn keep" data-act="check">Jetzt prüfen</button>' : '')}
    ${busy ? `<div class="card" style="margin-bottom:16px"><span class="badge warn">läuft</span> ${esc(label((d.running || {}).action || 'Anfrage'))} wird ausgeführt${d.running ? ` (seit ${fmtStamp(d.running.since)})` : ', der Helfer startet gleich'}. Diese Seite aktualisiert sich von selbst.
      ${(d.running || {}).action === 'hub' ? '<p class="muted small">Beim Hub-Update startet der Hub neu. Die Seite ist dann kurz nicht erreichbar.</p>' : ''}</div>` : ''}
    ${!h ? `<div class="card" style="margin-bottom:16px"><h2>Update-Helfer einrichten</h2>
      <p>Der Hub läuft abgeschottet im Container und darf den Server nicht selbst ändern. Ein kleiner Helfer auf dem VPS führt deshalb nur fest vorgegebene Updates aus, wenn du sie hier anstößt.</p>
      <ol class="steps"><li>Dieses Update wie gewohnt einspielen (<code>sudo bash update.sh</code>).</li>
        <li>Einmal in Putty: ${cmd(`cd ${d.host_dir} && sudo bash deploy/updater/install.sh`)}</li>
        <li>Nach etwa einer Minute diese Seite neu laden.</li></ol>
      <p class="muted small">Für Updates braucht dein Konto die Zwei-Faktor-Anmeldung. Vor jedem Update fragt der Hub nach deinem Passwort.</p></div>` : ''}
    ${h ? `<div class="card" style="margin-bottom:16px"><h2>Komponenten</h2>
      <p class="muted small">Zuletzt geprüft ${fmtStamp(h.checked_at)}${old ? ' <span class="badge warn">veraltet</span>' : ''}, automatisch alle 6 Stunden.
        ${h.last ? ` Letzte Aktion: ${esc(label(h.last.action))} am ${fmtStamp(h.last.at)} ${h.last.ok ? '<span class="badge ok">erfolgreich</span>' : '<span class="badge warn">mit Fehler</span>'}` : ''}</p>
      <div class="table-wrap"><table><thead><tr><th>Komponente</th><th>Installiert</th><th>Verfügbar</th><th></th></tr></thead><tbody>
      ${comps.map(c => `<tr><td><b>${esc(c.name)}</b>${c.note ? `<div class="muted small">${esc(c.note)}</div>` : ''}</td><td>${esc(c.installed || 'unbekannt')}</td>
        <td>${c.available ? `<span class="badge ok">${esc(c.available)}</span>` : '<span class="muted small">aktuell</span>'}</td>
        <td class="actions">${c.available && !busy ? `<button class="btn sm primary" data-act="${esc(c.update)}">${esc(label(c.update))}</button>` : ''}</td></tr>`).join('')}
      </tbody></table></div>
      ${h.reboot_required ? `<p style="margin-top:12px"><span class="badge warn">Neustart nötig</span> Nach den Ubuntu-Updates muss der Server neu starten. Webseite und Hub sind dabei etwa eine Minute weg.
        ${busy ? '' : '<button class="btn sm" data-act="reboot">Server neu starten</button>'}</p>` : ''}
      ${(h.packages || []).length ? `<details style="margin-top:10px"><summary class="small">Aktualisierbare Pakete (${h.packages.length})</summary><p class="muted small">${h.packages.map(esc).join(', ')}</p></details>` : ''}
    </div>` : ''}
    <div class="card" style="margin-bottom:16px"><h2>Im Hub selbst</h2>
      <ul class="checklist plain"><li><b>Hub</b>: ${esc(d.hub.version)}${d.hub.latest && d.hub.latest !== d.hub.version ? ` (auf GitHub: ${esc(d.hub.latest)})` : ''}</li>
        <li><b>Python</b>: ${esc(d.hub.python)}, <b>SQLite</b>: ${esc(d.hub.sqlite)}, <b>OpenSSL</b>: ${esc(d.hub.openssl)}</li></ul></div>
    ${d.log ? `<div class="card"><h2>Protokoll der letzten Aktion</h2><details ${busy ? 'open' : ''}><summary class="small">anzeigen</summary><pre class="log-box">${esc(d.log)}</pre></details></div>` : ''}`;
  $$('[data-copy]', view).forEach(b => b.onclick = () => navigator.clipboard.writeText(b.dataset.copy).then(() => toast('Kopiert')));
  $$('[data-act]', view).forEach(b => b.onclick = () => {
    const act = b.dataset.act;
    if (act === 'check') return send(act, '');
    openModal(`<h2>${esc(label(act))}</h2>
      <p>${({ hub: 'Holt den neuen Stand von GitHub, sichert vorher die Datenbank und startet den Hub neu.', caddy: 'Lädt das neue Caddy-Image und startet den Webserver neu. Die Webseite ist dabei wenige Sekunden weg.',
        system: 'Spielt alle Ubuntu-Updates ein (auch Docker). Danach ist eventuell ein Neustart nötig.', reboot: 'Startet den ganzen Server neu. Webseite und Hub sind etwa eine Minute nicht erreichbar.' })[act] || ''}</p>
      <form class="form" onsubmit="return false"><div class="field full"><label>Dein Passwort zur Bestätigung<input class="input" type="password" id="up_pw" autocomplete="current-password"></label></div></form>
      <div class="modal-foot"><div></div><div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="up_go">${esc(label(act))}</button></div></div>`);
    $('#up_pw').focus();
    $('#up_go').onclick = () => send(act, $('#up_pw').value);
  });
  async function send(action, password) {
    try { await api('admin/updates', 'POST', { action, password }); closeModal(); toast(`${label(action)} angestoßen`); adminUpdates(view); }
    catch (e) { alert(e.message); }
  }
  if (busy) setTimeout(() => { if (location.hash === '#/admin/updates' && !document.hidden) adminUpdates(view).catch(() => {}); }, 5000);   // während des Updates nachsehen (beim Hub-Neustart kurz nicht erreichbar)
}
