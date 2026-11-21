/* ====================================================================== */
/* Einstellungen */

App.pages.settings = async (view) => {
  const s = App.settings;
  const fields = [
    { key: 'club_name', label: 'Vereinsname' },
    { key: 'club_short', label: 'Kurzname', hint: 'z. B. AMISIA' },
    { key: 'instagram', label: 'Instagram-Account des Vereins', hint: 'Wird in Captions nie selbst markiert.' },
    { key: 'season', label: 'Aktuelle Saison' },
    { key: 'logo', label: 'Anderes Logo verwenden (optional)', type: 'image', hint: 'Leer lassen für das Vereinswappen.' },
    { key: 'color_primary', label: 'Akzentfarbe der Oberfläche', type: 'color' },
    { key: 'home_location', label: 'Heimspielort' },
    { key: 'entry_fee', label: 'Eintritt Heimspiel (€)', type: 'number' },
    { key: 'card_price', label: 'Preis Dauerkarte (€)', type: 'number' },
    { key: 'card_share_wolthusen', label: 'Anteil Eintritt an Wolthusen je Karte (€)', type: 'number' },
    { key: 'default_hashtags', label: 'Standard-Hashtags', full: true, hint: 'Pro Caption werden maximal 5 Hashtags genutzt.' },
    { key: 'training_text', label: 'Trainingszeiten (für Probetraining-Hinweise)', type: 'textarea', rows: 2 },
    { key: 'media_tasks', label: 'Aufgaben im Media Team pro Spiel (eine pro Zeile)', type: 'textarea', rows: 4 },
  ];
  view.innerHTML = `
    <div class="page-head"><h1>Einstellungen<small>Vereinsdaten, Standardwerte, Datensicherung</small></h1>
      <div class="btn-row"><a class="btn" href="#/accounts">Konten</a><a class="btn" href="#/groups">Gruppen &amp; Rechte</a></div></div>
    <div class="card" style="margin-bottom:16px"><form class="form" id="st_form" onsubmit="return false">${fields.map(f => fieldHtml(f, s[f.key])).join('')}</form>
      <div class="btn-row" style="margin-top:16px"><button class="btn primary" id="st_save">Speichern</button></div></div>
    <div class="card" style="margin-bottom:16px"><h2>Webseite</h2>
      <p class="muted small">Texte, Bilder und Aufbau der öffentlichen Webseite pflegst du jetzt unter Medien > Webseite.</p>
      <div class="btn-row"><a class="btn primary" href="#/website">Zur Webseite im Hub</a><a class="btn" href="/" target="_blank" rel="noopener">Webseite ansehen</a></div></div>
    <div class="card"><h2>Datensicherung</h2>
      <p class="muted">Der Server legt jede Nacht automatisch eine Sicherung der Datenbank an. Das Backup-ZIP enthält alle Daten und Bilder, aber keine Passwörter.</p>
      <div class="btn-row"><a class="btn dark" href="/api/backup">Backup herunterladen (ZIP)</a><a class="btn" href="/api/export" download="wolthusen-hub-export.json">Daten als JSON</a>
        <button class="btn" id="rs_btn">Backup einspielen</button><input type="file" id="rs_file" accept=".zip,.db" hidden></div>
      <div class="hint" style="margin-top:8px">Einspielen ersetzt alle Vereinsdaten durch das Backup (z. B. aus einer älteren Version). Vorher wird automatisch eine Sicherung angelegt. Konten, Gruppen und Rechte bleiben erhalten.</div>
      <div id="bk_list" class="small muted" style="margin-top:10px"></div></div>
    <div class="card" style="margin-top:16px"><h2>Serverumzug: Komplett-Export und -Import</h2>
      <p class="muted">Für den Umzug auf einen neuen Server. Die Datei enthält <b>alles</b>: Vereinsdaten, Bilder und Videos, Konten mit Passwörtern, Gruppen und Rechte,
        Facebook-Verbindung, E-Mail-Versand und das Protokoll. Sie ist mit dem Passwort verschlüsselt, das du hier festlegst. Ohne dieses Passwort lässt sie sich nicht öffnen.</p>
      <div class="grid g2">
        <div><h3>1. Auf dem alten Server exportieren</h3>
          <div class="form"><div class="field full"><label for="mg_pw1">Passwort für die Umzugsdatei (mind. 10 Zeichen)</label><input class="input" id="mg_pw1" type="password" autocomplete="new-password"></div>
            <div class="field full"><label for="mg_pw2">Passwort wiederholen</label><input class="input" id="mg_pw2" type="password" autocomplete="new-password"></div></div>
          <div class="btn-row" style="margin-top:10px"><button class="btn dark" id="mg_export">Komplett-Export herunterladen</button></div>
          <div class="hint" style="margin-top:6px">Die Datei lässt sich einmal herunterladen. Bewahre das Passwort getrennt von der Datei auf.</div></div>
        <div><h3>2. Auf dem neuen Server importieren</h3>
          <div class="form"><div class="field full"><label for="mg_file">Umzugsdatei (.wolthusen)</label><input class="input" id="mg_file" type="file" accept=".wolthusen"></div>
            <div class="field full"><label for="mg_pw3">Passwort der Umzugsdatei</label><input class="input" id="mg_pw3" type="password" autocomplete="off"></div></div>
          <div class="btn-row" style="margin-top:10px"><button class="btn danger" id="mg_import">Alles ersetzen und importieren</button></div>
          <div class="hint" style="margin-top:6px">Ersetzt den kompletten Stand dieses Hubs, auch Konten. Vorher wird automatisch eine Sicherung angelegt. Danach meldest du dich mit den Zugangsdaten des alten Servers an.</div></div>
      </div><div id="mg_status" class="small" style="margin-top:10px"></div></div>
    <div class="card" style="margin-top:16px" id="mail_card"><h2>E-Mail-Versand für Benachrichtigungen</h2><div class="muted">Lade ...</div></div>`;
  $('#mg_export').onclick = async () => {
    const pw = $('#mg_pw1').value;
    if (pw.length < 10) return alert('Das Passwort braucht mindestens 10 Zeichen.');
    if (pw !== $('#mg_pw2').value) return alert('Die Passwörter stimmen nicht überein.');
    $('#mg_status').textContent = 'Erstelle die Umzugsdatei, das kann bei vielen Bildern etwas dauern ...';
    try {
      const r = await api('migrate/export', 'POST', { password: pw });
      $('#mg_status').textContent = `Fertig (${(r.size / 1048576).toFixed(1).replace('.', ',')} MB). Der Download startet.`;
      $('#mg_pw1').value = $('#mg_pw2').value = '';
      location.href = r.download;
    } catch (e) { $('#mg_status').textContent = ''; alert(e.message); }
  };
  $('#mg_import').onclick = async () => {
    const f = $('#mg_file').files[0], pw = $('#mg_pw3').value;
    if (!f || !pw) return alert('Bitte Umzugsdatei auswählen und Passwort eingeben.');
    if (!confirmBox(`„${f.name}“ importieren? Der komplette Stand dieses Hubs wird ersetzt, auch alle Konten.`)) return;
    $('#mg_status').textContent = 'Lade hoch und prüfe die Datei ...';
    const r = await fetch('/api/migrate/import', { method: 'POST', body: f, headers: { 'X-TMH': '1', 'Content-Type': 'application/octet-stream',
      'X-Umzug-Passwort': btoa(String.fromCharCode(...new TextEncoder().encode(pw))) } });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { $('#mg_status').textContent = ''; return alert('Import fehlgeschlagen: ' + (d.error || r.status)); }
    alert(`Umzug eingespielt: Stand vom ${fmtStamp(d.created)} (Version ${d.version}), ${d.users} Konten, ${d.media} Dateien.\nBitte jetzt mit den Zugangsdaten des alten Servers anmelden.`);
    location.href = '/login';
  };
  const mailCard = async () => {
    const c = await api('notify');
    $('#mail_card').innerHTML = `<h2>E-Mail-Versand für Benachrichtigungen</h2>
      <p class="muted small">Über dieses Postfach verschickt der Hub die Benachrichtigungen, die jeder unter „Mein Profil“ auswählt. Bei Gmail ein App-Passwort verwenden.</p>
      <div class="form">
        <div class="field"><label for="ml_host">Mailserver (SMTP)</label><input class="input" id="ml_host" value="${esc(c.smtp_host || '')}" placeholder="z. B. smtp.gmail.com"></div>
        <div class="field"><label for="ml_port">Port</label><input class="input" id="ml_port" value="${esc(c.smtp_port || '')}" placeholder="587"></div>
        <div class="field"><label for="ml_sec">Verschlüsselung</label><select class="input" id="ml_sec">${[['starttls', 'STARTTLS (Port 587)'], ['ssl', 'SSL/TLS (Port 465)'], ['none', 'keine']].map(([v, l]) => `<option value="${v}" ${(c.smtp_security || 'starttls') === v ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
        <div class="field"><label for="ml_user">Benutzername</label><input class="input" id="ml_user" value="${esc(c.smtp_user || '')}" autocomplete="off"></div>
        <div class="field"><label for="ml_pw">Passwort</label><input class="input" id="ml_pw" type="password" autocomplete="new-password" placeholder="${c.password_set ? 'hinterlegt, nur zum Ändern neu eintragen' : ''}"></div>
        <div class="field"><label for="ml_from">Absender</label><input class="input" id="ml_from" value="${esc(c.smtp_from || '')}" placeholder="z. B. SV Amisia Wolthusen"><small class="muted">Name, der als Absender erscheint. Ohne Adresse nimmt der Hub die Adresse des Postfachs (Benutzername). Eine andere Adresse nur, wenn sie zu diesem Postfach gehört.</small></div>
        <div class="field"><label for="ml_imap">Posteingang (IMAP-Server, optional)</label><input class="input" id="ml_imap" value="${esc(c.imap_host || '')}" placeholder="leer: aus SMTP abgeleitet, z. B. imap.strato.de"><small class="muted">Für die Seite Postfach. Gleicher Benutzer und gleiches Passwort, Port 993.</small></div>
        <div class="field full"><label for="ml_url">Adresse des Hubs für Links in der Mail</label><input class="input" id="ml_url" value="${esc(c.hub_url || '')}" placeholder="z. B. https://hub.emdentigers.de"></div></div>
      <div class="field full" style="margin-top:10px"><label>Bei neuen Mails benachrichtigen (Push und Zahl am App-Symbol)</label><div class="chk-grid" id="ml_groups">Lade ...</div>
        <small class="muted">Mitglieder dieser Gruppen bekommen jede neue Mail im Posteingang gemeldet, bis jemand sie erledigt. Die Gruppe braucht dafür mindestens „Lesen“ im Bereich Postfach.</small></div>
      <p class="muted small" style="margin-top:10px"><b>Signatur:</b> Mails aus dem Postfach bekommen die Vereinssignatur mit Logo. Der Name kommt aus dem Konto, die Rolle aus den Gruppen der Person (oder „Rolle in der Signatur“ unter Konten).</p>
      ${c.last_error ? `<div class="warnline" style="margin-top:8px">Letzter Fehler beim Versand: ${esc(c.last_error)}</div>` : ''}
      <div class="btn-row" style="margin-top:12px"><button class="btn primary" id="ml_save">Speichern</button>
        <input class="input" id="ml_to" placeholder="Test an E-Mail-Adresse" style="max-width:240px"><button class="btn" id="ml_test">Test-Mail senden</button></div>`;
    api('admin/groups').then(gs => {
      let sel = []; try { sel = JSON.parse(App.settings.pf_notify_groups || '[]'); } catch { sel = []; }
      $('#ml_groups').innerHTML = gs.map(g => `<label class="check"><input type="checkbox" class="ml_g" value="${esc(g.name)}" ${sel.includes(g.name) ? 'checked' : ''}> ${esc(g.name)}
        ${(g.perms.postfach || 0) < 1 ? '<span class="badge warn" title="Hat kein Recht im Bereich Postfach">ohne Postfach-Recht</span>' : ''}</label>`).join('');
    }).catch(() => {});
    $('#ml_save').onclick = async () => {
      await api('notify', 'PUT', { smtp_host: $('#ml_host').value, smtp_port: $('#ml_port').value, smtp_security: $('#ml_sec').value,
        smtp_user: $('#ml_user').value, smtp_password: $('#ml_pw').value, smtp_from: $('#ml_from').value, hub_url: $('#ml_url').value, imap_host: $('#ml_imap').value });
      if ($('#ml_groups .ml_g')) App.settings = await api('settings', 'PUT', { pf_notify_groups: JSON.stringify($$('#ml_groups .ml_g').filter(c => c.checked).map(c => c.value)) });
      toast('E-Mail-Versand gespeichert'); mailCard();
    };
    $('#ml_test').onclick = async () => {
      try { await api('notify/test', 'POST', { to: $('#ml_to').value }); toast('Test-Mail verschickt'); } catch (e) { alert(e.message); }
    };
  };
  mailCard().catch(() => {});
  $$('input[name="color_primary"]').forEach(i => i.type = 'color');
  bindImageFields($('#st_form'));
  $('#st_save').onclick = async () => {
    App.settings = await api('settings', 'PUT', readForm($('#st_form'), fields));
    applyBranding(); toast('Einstellungen gespeichert');
  };
  $('#rs_btn').onclick = () => $('#rs_file').click();
  $('#rs_file').onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    if (!confirmBox(`„${f.name}“ einspielen? Alle aktuellen Vereinsdaten werden durch das Backup ersetzt.`)) return;
    toast('Spiele Backup ein ...');
    const r = await fetch('/api/restore', { method: 'POST', headers: { 'X-TMH': '1', 'Content-Type': 'application/octet-stream' }, body: f });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) return alert('Einspielen fehlgeschlagen: ' + (d.error || r.status));
    App.cache = {}; await loadSettings();
    alert(`Backup eingespielt. ${d.media} Bilder übernommen.`); route();
  };
  api('backups').then(list => { const el = $('#bk_list'); if (el && list.length) el.innerHTML = 'Automatische Sicherungen auf dem Server: ' + list.slice(0, 5).map(b => esc(b.name)).join(', ') + (list.length > 5 ? ' ...' : ''); }).catch(() => {});
};

/* ---------- Post planen (Grafik kommt aus Canva) ---------- */
async function planPost(rec = {}) {
  await loadAll('games', 'opponents', 'sponsors', 'players', 'posts');
  const social = await api('social').catch(() => ({}));
  const r = { status: 'Idee', format: 'Feed', time: '18:00', targets: 'Facebook', ...rec };
  if (!rec.id) {
    const g = byId(App.cache.games, r.game_id);
    if (!r.date) {
      if (g && r.type === 'Gameday') r.date = addDays(g.date, -2) < todayStr() ? g.date : addDays(g.date, -2);
      else if (g) r.date = g.date;
      else r.date = todayStr();
    }
    if (r.type === 'Ergebnis') r.time = '20:00';
    if (!r.title) {
      const p = byId(App.cache.players, r.player_id), sp = byId(App.cache.sponsors, r.sponsor_id);
      r.title = g ? `${r.type}: ${gameLabel(g)}` : p ? `${r.type}: ${fullName(p)}` : sp ? `${r.type}: ${sp.name}` : (r.type || '');
    }
    if (g && !r.sponsor_id && g.sponsor_id) r.sponsor_id = g.sponsor_id;
    if (!r.caption && r.type) r.caption = suggestCaption(r);
  }
  const saved = await editRecord('posts', F.posts, r, {
    newTitle: 'Post planen', editTitle: 'Post bearbeiten',
    onOpen: box => {
      const cap = $('#f_caption', box);
      cap.closest('.field').insertAdjacentHTML('beforeend', `<div class="btn-row" style="margin-top:6px">
        <button type="button" class="btn sm" id="pp_sug">Caption-Vorschlag aus den Daten</button>
        <button type="button" class="btn sm ghost" id="pp_copy">Kopieren</button>
        <span class="muted small" id="pp_info"></span></div><div id="pp_warn"></div>`);
      const check = () => {
        const v = cap.value, tags = (v.match(/#[\wÄÖÜäöüß]+/g) || []).length;
        $('#pp_info', box).textContent = `${v.length} Zeichen | ${tags} Hashtags`;
        const w = [];
        if (hasDashes(v)) w.push('Enthält Gedankenstriche. <button type="button" class="btn sm" id="pp_fix">Entfernen</button>');
        if (tags > 5) w.push('Mehr als 5 Hashtags.');
        if (/\[[^\]]+\]/.test(v)) w.push('Noch Platzhalter in eckigen Klammern drin.');
        const pl = byId(App.cache.players, $('#f_player_id', box).value);
        if (pl && !Number(pl.consent)) w.push('Für diese Person ist keine Foto-Einwilligung hinterlegt.');
        const f = readForm(box, F.posts);
        if (Number(f.auto_publish) && !['gepostet', 'läuft'].includes(rec.publish_state)) {
          if (!social.connected) w.push('Automatisch posten: Es ist noch keine Facebook-Seite verbunden (Auto-Posting).');
          if (!f.date || !f.time) w.push('Automatisch posten: Datum und Uhrzeit fehlen.');
          else if (new Date(`${f.date}T${f.time}`) < new Date(Date.now() - 24 * 3600 * 1000)) w.push('Automatisch posten: Der Zeitpunkt liegt mehr als 24 Stunden zurück, der Post wird nicht mehr automatisch gepostet.');
          else if (new Date(`${f.date}T${f.time}`) < new Date()) w.push('Automatisch posten: Der Zeitpunkt liegt in der Vergangenheit, der Post geht nach dem Speichern innerhalb einer Minute raus.');
          const media = parseFiles(f.media), ext = m => (m.path.split('.').pop() || '').toLowerCase();
          if (f.format === 'Karussell' && (media.length < 2 || media.length > 10 || media.some(m => !['jpg', 'jpeg', 'png', 'webp'].includes(ext(m)))))
            w.push('Automatisch posten: Ein Karussell braucht 2 bis 10 Bilder (JPG oder PNG).');
          if (f.format === 'Reel' && (media.length !== 1 || !['mp4', 'mov'].includes(ext(media[0]))))
            w.push('Automatisch posten: Ein Reel braucht genau ein Video (MP4 oder MOV).');
          if (!f.image && (f.format === 'Story' || (f.format === 'Feed' && /instagram/i.test(f.targets)))) w.push('Automatisch posten: Für Storys und Instagram wird ein Bild gebraucht.');
          if (/instagram/i.test(f.targets) && social.connected && !social.instagram) w.push('Automatisch posten: Mit der Facebook-Seite ist kein Instagram-Konto verknüpft.');        }
        $('#pp_warn', box).innerHTML = w.map(x => `<div class="warnline">⚠ ${x}</div>`).join('');
        const fx = $('#pp_fix', box); if (fx) fx.onclick = () => { cap.value = noDashes(cap.value); check(); };
      };
      $('#pp_sug', box).onclick = () => {
        if (cap.value.trim() && !confirmBox('Aktuelle Caption durch einen Vorschlag ersetzen?')) return;
        cap.value = suggestCaption(readForm(box, F.posts)); check();
      };
      $('#pp_copy', box).onclick = () => copyText(cap.value);
      if (rec.publish_state || rec.publish_log) {
        $('[data-fkey="auto_publish"]', box).insertAdjacentHTML('beforebegin', `<div class="field full"><label>Automatisch posten</label>
          <div>${publishBadge(rec)} <span class="small muted">${esc(rec.publish_log || '')}</span></div></div>`);
      }
      cap.addEventListener('input', check); box.addEventListener('change', check); check();
    },
  });
  if (saved) route();
}

async function copyGameInfo(id) {
  await loadAll('games', 'opponents', 'sponsors');
  copyText(noDashes(gameInfoText(byId(App.cache.games, id))));
}

async function exportGamesCsv() {
  await loadAll('games', 'opponents', 'sponsors');
  const season = App._season || App.settings.season;
  const list = App.cache.games.filter(g => season === 'alle' || (g.season || '') == season)
    .sort((a, b) => ((a.date || '') + (a.time || '')).localeCompare((b.date || '') + (b.time || '')));
  downloadCsv(`spielplan-${season}-canva.csv`,
    ['Datum', 'Datum kurz', 'Wochentag', 'Anstoß', 'Gegner', 'Heim/Auswärts', 'Spielort', 'Art', 'Ergebnis', 'Sponsor'],
    list.map(g => {
      const d = parseDate(g.date), o = byId(App.cache.opponents, g.opponent_id), home = Number(g.home);
      return [fmtDate(g.date), d ? `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.` : '', d ? WD[d.getDay()] : '',
        g.time ? g.time + ' Uhr' : '', o?.name || 'TBA', home ? 'Heim' : 'Auswärts', g.location || (home ? App.settings.home_location : ''), g.kind || '',
        g.score_us !== null && g.score_us !== '' ? `${g.score_us}:${g.score_them}` : '', byId(App.cache.sponsors, g.sponsor_id)?.name || ''];
    }));
}

