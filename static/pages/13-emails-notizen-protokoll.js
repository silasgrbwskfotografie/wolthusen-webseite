App.pages.emails = async (view) => {
  const { accounts, users } = await api('admin/mail');
  view.innerHTML = `
    <div class="page-head"><h1>E-Mails<small>Alle Mail-Konten des Vereins. Ist ein Konto einer Person zugewiesen, sieht sie es im Hub unter Postfach zusätzlich zum Vereinspostfach und kann darüber lesen, antworten und schreiben. Passwörter sind nach dem Speichern nicht mehr lesbar.</small></h1>
      <button class="btn primary" id="em_new">+ Mail-Konto</button></div>
    <div class="table-wrap"><table><thead><tr><th>Adresse</th><th>Server</th><th>Zugewiesen an</th><th></th></tr></thead><tbody>
    ${accounts.map(a => `<tr><td><b>${esc(a.address)}</b>${a.username && a.username !== a.address ? `<div class="muted small">${esc(a.username)}</div>` : ''}${a.password_set ? '' : '<div class="small" style="color:var(--red)">Passwort fehlt</div>'}</td>
      <td class="small">${esc(a.smtp_host)}${a.smtp_port ? ':' + esc(a.smtp_port) : ''}</td>
      <td>${a.users.map(u => `<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;white-space:nowrap">
          <button class="btn sm" data-remove="${a.id}" data-user="${u.id}" title="Zuweisung lösen" aria-label="${esc(u.name)} von ${esc(a.address)} lösen">×</button><b>${esc(u.name)}</b>
          <label class="check small"><input type="checkbox" data-noshared="${a.id}" data-user="${u.id}" ${u.no_shared ? 'checked' : ''}> kein Vereinspostfach</label></div>`).join('')}
        <select class="input" data-assign="${a.id}" aria-label="Person zuweisen: ${esc(a.address)}"><option value="">+ Person zuweisen</option>
        ${users.filter(u => !a.users.some(x => x.id === u.id)).map(u => `<option value="${u.id}">${esc(u.name)}</option>`).join('')}</select></td>
      <td><div class="btn-row"><button class="btn sm" data-edit="${a.id}">Bearbeiten</button><button class="btn sm" data-check="${a.id}">Prüfen</button></div><div class="small" id="em_msg_${a.id}"></div></td></tr>`).join('')
      || '<tr><td colspan="4" class="empty">Noch keine Mail-Konten hinterlegt.</td></tr>'}
    </tbody></table></div>
    <p class="muted small">Ein Mail-Konto kann mehreren Personen zugewiesen sein (z. B. ein Postfach für alle Coaches), und eine Person kann mehrere Mail-Konten haben. Im Postfach schaltet sie oben zwischen ihnen um. „Kein Vereinspostfach“: die Person sieht nur ihr eigenes Postfach. Wird ihr eine Mail aus dem Vereinspostfach zugewiesen, bekommt sie diese an ihre Adresse weitergeleitet (gleich wie die Ausnahme „Postfach: kein Zugriff“ unter Konten).</p>`;
  const edit = (a = {}) => {
    openModal(`<h2>${a.id ? 'Mail-Konto bearbeiten' : 'Neues Mail-Konto'}</h2>
      <div class="form">
        <div class="field"><label for="mb_addr">Adresse</label><input class="input" id="mb_addr" value="${esc(a.address || '')}" placeholder="vorname@amisia-stern.de"></div>
        <div class="field"><label for="mb_user">Benutzername</label><input class="input" id="mb_user" value="${esc(a.username || '')}" autocomplete="off" placeholder="leer: die Adresse"></div>
        <div class="field"><label for="mb_pw">Passwort</label><input class="input" id="mb_pw" type="password" autocomplete="new-password" placeholder="${a.password_set ? 'hinterlegt, nur zum Ändern eintragen' : ''}"></div>
        <div class="field"><label for="mb_smtp">Mailserver (SMTP)</label><input class="input" id="mb_smtp" value="${esc(a.smtp_host || '')}" placeholder="smtp.strato.de"></div>
        <div class="field"><label for="mb_port">Port</label><input class="input" id="mb_port" value="${esc(a.smtp_port || '')}" placeholder="587"></div>
        <div class="field"><label for="mb_imap">IMAP-Server (Lesen und „Gesendet“)</label><input class="input" id="mb_imap" value="${esc(a.imap_host || '')}" placeholder="leer: imap.strato.de"></div>
      </div>
      <div class="modal-foot">${a.id ? '<button class="btn danger" id="mb_del">Löschen</button>' : '<div></div>'}<div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="mb_save">Speichern</button></div></div>`);
    $('#mb_save').onclick = async () => {
      const body = { address: $('#mb_addr').value, username: $('#mb_user').value, password: $('#mb_pw').value,
        smtp_host: $('#mb_smtp').value || 'smtp.strato.de', smtp_port: $('#mb_port').value || '587', smtp_security: 'starttls', imap_host: $('#mb_imap').value };
      try { await api(a.id ? `admin/mail/${a.id}` : 'admin/mail', a.id ? 'PUT' : 'POST', body); closeModal(); toast('Gespeichert'); route(); } catch (e) { alert(e.message); }
    };
    if (a.id) $('#mb_del').onclick = async () => {
      if (!confirmBox(`Mail-Konto ${a.address} löschen?${a.users.length ? ` ${a.users.map(u => u.name).join(', ')} schreiben danach wieder über das Vereinspostfach.` : ''} Das Postfach beim Anbieter bleibt bestehen.`)) return;
      try { await api(`admin/mail/${a.id}`, 'DELETE'); closeModal(); toast('Gelöscht'); route(); } catch (e) { alert(e.message); }
    };
  };
  $('#em_new').onclick = () => edit();
  view.querySelectorAll('[data-edit]').forEach(b => { b.onclick = () => edit(accounts.find(a => a.id == b.dataset.edit)); });
  view.querySelectorAll('[data-check]').forEach(b => { b.onclick = async () => {
    const m = $('#em_msg_' + b.dataset.check); m.textContent = 'Prüfe ...';
    try { const r = await api(`admin/mail/${b.dataset.check}/check`, 'POST'); m.textContent = `Senden: ${r.smtp === 'ok' ? 'OK' : r.smtp} | Lesen: ${r.imap === 'ok' ? 'OK' : r.imap}`; }
    catch (e) { m.textContent = e.message; }
  }; });
  view.querySelectorAll('[data-assign]').forEach(sel => { sel.onchange = async () => {
    if (!sel.value) return;
    try { await api(`admin/mail/${sel.dataset.assign}`, 'PUT', { add_user: Number(sel.value) }); toast('Zugewiesen'); route(); } catch (e) { alert(e.message); route(); }
  }; });
  view.querySelectorAll('[data-remove]').forEach(b => { b.onclick = async () => {
    try { await api(`admin/mail/${b.dataset.remove}`, 'PUT', { remove_user: Number(b.dataset.user) }); toast('Zuweisung gelöst'); route(); } catch (e) { alert(e.message); }
  }; });
  view.querySelectorAll('[data-noshared]').forEach(c => { c.onchange = async () => {
    try { await api(`admin/mail/${c.dataset.noshared}`, 'PUT', { no_shared: c.checked, user_id: Number(c.dataset.user) }); toast(c.checked ? 'Nur eigenes Postfach' : 'Vereinspostfach wie Gruppe'); }
    catch (e) { alert(e.message); c.checked = !c.checked; }
  }; });
};

/* Verwaltung > Notizen (Tabelle admin_notes, nur Admins). Einzelne Notizen mit Passwort: AES-GCM im Browser (PBKDF2, 600000 Runden),
   der Server sieht nur den verschlüsselten Text, das Passwort verlässt den Browser nie. Der Titel bleibt lesbar. */
const NoteCrypto = {
  b64: b => { let s = ''; for (const x of new Uint8Array(b)) s += String.fromCharCode(x); return btoa(s); },
  unb64: s => Uint8Array.from(atob(s), c => c.charCodeAt(0)),
  async key(pw, salt, it) {
    const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(pw), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey({ name: 'PBKDF2', salt, iterations: it, hash: 'SHA-256' }, base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
  },
  async seal(text, pw) {
    const salt = crypto.getRandomValues(new Uint8Array(16)), iv = crypto.getRandomValues(new Uint8Array(12)), it = 600000;
    const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, await this.key(pw, salt, it), new TextEncoder().encode(text));
    return JSON.stringify({ v: 1, it, salt: this.b64(salt), iv: this.b64(iv), ct: this.b64(ct) });
  },
  async open(json, pw) {
    const d = JSON.parse(json);
    const k = await this.key(pw, this.unb64(d.salt), Number(d.it) || 600000);
    return new TextDecoder().decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: this.unb64(d.iv) }, k, this.unb64(d.ct)));
  },
};

App.pages.notes = async (view) => {
  let list = await api('admin_notes'), q = '';
  const draw = () => {
    const ql = q.toLowerCase();
    const rows = list.filter(n => !ql || (n.title || '').toLowerCase().includes(ql) || (!Number(n.encrypted) && (n.body || '').toLowerCase().includes(ql)))
      .sort((a, b) => (Number(b.pinned) - Number(a.pinned)) || String(b.updated || '').localeCompare(String(a.updated || '')));
    $('#nt_list').innerHTML = rows.map(n => `<button type="button" class="card note-card" data-note="${n.id}">
        <h3>${Number(n.pinned) ? '<span title="angeheftet">📌</span>' : ''}${Number(n.encrypted) ? '<span title="mit Passwort verschlüsselt">🔒</span>' : ''}${esc(n.title || '(ohne Titel)')}</h3>
        ${Number(n.encrypted) ? '<div class="note-prev note-lock">Verschlüsselt, zum Lesen Passwort eingeben</div>' : `<div class="note-prev">${esc((n.body || '').slice(0, 400))}</div>`}
        <div class="note-meta">${n.updated ? fmtStamp(n.updated) : ''}</div></button>`).join('')
      || `<div class="card empty">${q ? 'Keine Treffer.' : 'Noch keine Notizen.'}</div>`;
    $$('[data-note]', view).forEach(b => b.onclick = () => openNote(list.find(n => n.id == b.dataset.note)));
  };
  const reload = async () => { list = await api('admin_notes'); draw(); };
  const askPw = (title, twice) => new Promise(res => {
    openModal(`<h2>${esc(title)}</h2><form class="form" id="np_f" autocomplete="off">
        <div class="field full"><label for="np_1">Passwort</label><input class="input" id="np_1" type="password" autocomplete="${twice ? 'new-password' : 'current-password'}" required></div>
        ${twice ? `<div class="field full"><label for="np_2">Passwort wiederholen</label><input class="input" id="np_2" type="password" autocomplete="new-password" required></div>
        <div class="field full"><div class="warnline">Ohne dieses Passwort ist die Notiz nicht mehr lesbar. Es wird nirgends gespeichert und lässt sich nicht zurücksetzen.</div></div>` : ''}
      </form><div class="modal-foot"><div></div><div class="btn-row"><button class="btn" id="np_x">Abbrechen</button><button class="btn primary" id="np_ok">OK</button></div></div>`);
    $('#np_1').focus();
    const ok = () => {
      const a = $('#np_1').value;
      if (!a) return;
      if (twice && a.length < 8) return alert('Bitte mindestens 8 Zeichen.');
      if (twice && a !== $('#np_2').value) return alert('Die Passwörter stimmen nicht überein.');
      closeModal(); res(a);
    };
    $('#np_ok').onclick = ok; $('#np_f').onsubmit = e => { e.preventDefault(); ok(); };
    $('#np_x').onclick = () => { closeModal(); res(null); };
  });
  const openNote = async (n = {}) => {
    if (!(window.crypto && crypto.subtle)) { if (Number(n.encrypted)) return alert('Verschlüsselte Notizen gehen nur über https.'); }
    let pw = null, body = n.body || '';
    if (Number(n.encrypted)) {
      pw = await askPw(`Passwort für „${n.title || 'Notiz'}“`, false);
      if (pw == null) return;
      try { body = await NoteCrypto.open(n.body, pw); } catch { return alert('Falsches Passwort.'); }
    }
    openModal(`<h2>${n.id ? 'Notiz' : 'Neue Notiz'}</h2>
      <div class="form">
        <div class="field full"><label for="nt_title">Titel</label><input class="input" id="nt_title" value="${esc(n.title || '')}" maxlength="200"></div>
        <div class="field full"><label for="nt_body">Notiz</label><textarea class="input" id="nt_body">${esc(body)}</textarea></div>
        <div class="field"><label class="check"><input type="checkbox" id="nt_enc" ${pw != null ? 'checked' : ''}> 🔒 Mit Passwort verschlüsseln</label>
          <small class="muted">Der Titel bleibt lesbar. Ohne Passwort ist der Inhalt verloren.</small></div>
        <div class="field"><label class="check"><input type="checkbox" id="nt_pin" ${Number(n.pinned) ? 'checked' : ''}> 📌 Oben anheften</label></div>
      </div>
      <div class="modal-foot">${n.id ? '<button class="btn danger" id="nt_del">Löschen</button>' : '<div></div>'}<div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="nt_save">Speichern</button></div></div>`);
    $('#nt_save').onclick = async () => {
      const title = $('#nt_title').value.trim(), text = $('#nt_body').value, enc = $('#nt_enc').checked, pinned = $('#nt_pin').checked ? 1 : 0;
      const keep = { title, text, enc, pinned };
      let usePw = pw;
      if (enc && usePw == null) {
        if (!(window.crypto && crypto.subtle)) return alert('Verschlüsseln geht nur über https.');
        usePw = await askPw('Passwort für diese Notiz festlegen', true);
        if (usePw == null) return openNote({ ...n, title: keep.title, body: keep.text, encrypted: 0, pinned: keep.pinned });
      }
      const rec = { title: keep.title, pinned: keep.pinned, encrypted: keep.enc ? 1 : 0, updated: new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 19),
        body: keep.enc ? await NoteCrypto.seal(keep.text, usePw) : keep.text };
      try { n.id ? await api('admin_notes/' + n.id, 'PUT', rec) : await api('admin_notes', 'POST', rec); closeModal(); toast('Gespeichert'); reload(); }
      catch (e) { alert(e.message); }
    };
    if (n.id) $('#nt_del').onclick = async () => {
      if (!confirmBox(`Notiz „${n.title || 'ohne Titel'}“ löschen?`)) return;
      try { await api('admin_notes/' + n.id, 'DELETE'); closeModal(); toast('Gelöscht'); reload(); } catch (e) { alert(e.message); }
    };
  };
  view.innerHTML = `<div class="page-head"><h1>Notizen<small>Nur für Admins. Einzelne Notizen lassen sich mit einem eigenen Passwort verschlüsseln, das nur du kennst.</small></h1>
      <button class="btn primary" id="nt_new">+ Notiz</button></div>
    <div class="toolbar"><input class="input" id="nt_q" type="search" placeholder="Suchen (Titel, unverschlüsselter Text)" aria-label="Notizen durchsuchen" style="max-width:320px"></div>
    <div class="note-grid" id="nt_list"></div>`;
  $('#nt_new').onclick = () => openNote();
  $('#nt_q').oninput = e => { q = e.target.value; draw(); };
  draw();
};

App.pages.log = async (view) => {
  const rows = await api('admin/log?limit=1000');
  let q = '', tbl = '', who = '';
  const tables = [...new Set(rows.map(r => r.table_name).filter(Boolean))].sort((a, b) => (TABLE_NAMES[a] || a).localeCompare(TABLE_NAMES[b] || b));
  const users = [...new Set(rows.map(r => r.user_name).filter(Boolean))].sort();
  const details = r => {
    let d; try { d = JSON.parse(r.details || 'null'); } catch { d = null; }
    if (!d || typeof d !== 'object') return '';
    return Object.entries(d).map(([k, v]) => Array.isArray(v)
      ? `<div><b>${esc(k)}</b>: <span class="muted">${esc(v[0] || 'leer')}</span> → ${esc(v[1] || 'leer')}</div>`
      : `<div><b>${esc(k)}</b>: ${esc(typeof v === 'object' ? JSON.stringify(v) : v)}</div>`).join('');
  };
  const cls = a => a.startsWith('gelöscht') ? 'red' : a.startsWith('neu') ? 'ok' : a.startsWith('geändert') ? 'warn' : '';
  const draw = () => {
    const ql = q.toLowerCase();
    const list = rows.filter(r => (!tbl || r.table_name === tbl) && (!who || r.user_name === who)
      && (!ql || [r.label, r.action, r.user_name, r.details, TABLE_NAMES[r.table_name]].join(' ').toLowerCase().includes(ql)));
    $('#lg_rows').innerHTML = list.map(r => `<tr><td class="small" style="white-space:nowrap">${fmtStamp(r.time)}</td><td>${esc(r.user_name || '')}</td>
      <td><span class="badge ${cls(r.action || '')}">${esc(r.action || '')}</span></td><td>${esc(TABLE_NAMES[r.table_name] || r.table_name || '')}</td>
      <td>${esc(r.label || '')}${r.record_id ? ` <span class="muted small">#${r.record_id}</span>` : ''}
        ${r.details ? `<details class="small"><summary>Details</summary>${details(r)}</details>` : ''}</td></tr>`).join('')
      || '<tr><td colspan="5" class="empty">Keine Einträge.</td></tr>';
    $('#lg_count').textContent = `${list.length} von ${rows.length} Einträgen`;
  };
  view.innerHTML = `
    <div class="page-head"><h1>Protokoll<small>Wer hat wann was angelegt, geändert oder gelöscht. Einträge werden nach gut einem Jahr entfernt.</small></h1></div>
    <div class="toolbar"><input class="input" id="lg_q" placeholder="Suchen (Name, Eintrag, Inhalt)" style="max-width:280px">
      <select class="input" id="lg_t"><option value="">Alle Bereiche</option>${tables.map(t => `<option value="${esc(t)}">${esc(TABLE_NAMES[t] || t)}</option>`).join('')}</select>
      <select class="input" id="lg_u"><option value="">Alle Personen</option>${users.map(u => `<option>${esc(u)}</option>`).join('')}</select>
      <span class="muted small" id="lg_count"></span></div>
    <div class="table-wrap"><table><thead><tr><th>Zeit</th><th>Wer</th><th>Aktion</th><th>Bereich</th><th>Eintrag</th></tr></thead><tbody id="lg_rows"></tbody></table></div>`;
  $('#lg_q').oninput = e => { q = e.target.value; draw(); };
  $('#lg_t').onchange = e => { tbl = e.target.value; draw(); };
  $('#lg_u').onchange = e => { who = e.target.value; draw(); };
  draw();
};

