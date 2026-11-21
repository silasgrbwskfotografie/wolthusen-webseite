/* ====================================================================== */
/* Rechte-Hilfen */
const LEVELS = ['Kein Zugriff', 'Lesen', 'Bearbeiten'];
const AREA_SHORT = { medien: 'Medien', verein: 'Verein', mitglieder: 'Mitglieder', finanzen: 'Finanzen', spieltag: 'Spieltag', wartung: 'Wartung', postfach: 'Postfach' };
function levelBadge(l) {
  return l >= 2 ? '<span class="badge ok">Bearbeiten</span>' : l === 1 ? '<span class="badge">Lesen</span>' : '<span class="badge muted-badge">kein Zugriff</span>';
}
function permChips(perms) {
  return Object.keys(AREA_SHORT).map(a => `<span class="perm-chip lvl${perms[a] || 0}" title="${AREA_SHORT[a]}: ${LEVELS[perms[a] || 0]}">${AREA_SHORT[a]}</span>`).join('');
}
function slug(t) {
  return (t || '').toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
    .normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '.').replace(/^\.|\.$/g, '').slice(0, 40);
}

/* ====================================================================== */
/* Mein Profil (alle) */
/* Mein Profil: eigene Tab-Leiste unten am Handy (bis zu 4 Seiten aus dem Menü, „Mehr“ bleibt immer rechts) */
function tabbarCard(box) {
  const choices = tabChoices();
  const cur = (App.me.tabbar || []).filter(p => choices.some(c => c.page === p));
  const def = TAB_CANDIDATES.filter(t => !t.area || can(t.area)).slice(0, 4).map(t => t.page);
  const sel = cur.length ? cur : def;
  box.innerHTML = `<h2>Leiste unten (Handy)</h2>
    <p class="muted small">Welche Seiten unten in der Leiste der App stehen. Bis zu vier, „Mehr“ mit dem ganzen Menü bleibt immer rechts. Gilt für dein Konto auf allen Geräten.</p>
    <div class="form">${[0, 1, 2, 3].map(i => `<div class="field"><label for="tb_${i}">Platz ${i + 1}</label><select class="input" id="tb_${i}"><option value="">(leer)</option>
      ${choices.map(c => `<option value="${esc(c.page)}" ${sel[i] === c.page ? 'selected' : ''}>${esc(c.full)}</option>`).join('')}</select></div>`).join('')}</div>
    <div class="btn-row" style="margin-top:10px"><button class="btn primary" id="tb_save">Leiste speichern</button><button class="btn" id="tb_reset">Standard</button></div>`;
  const store = async pages => {
    try { const r = await api('tabbar', 'PUT', { pages }); App.me.tabbar = r.tabbar; renderTabbar(); tabbarCard(box); toast('Leiste gespeichert'); }
    catch (e) { alert(e.message); }
  };
  $('#tb_save', box).onclick = () => store([...new Set([0, 1, 2, 3].map(i => $('#tb_' + i, box).value).filter(Boolean))]);
  $('#tb_reset', box).onclick = () => store([]);
}

App.pages.profile = async (view) => {
  const prof = await api('profile');
  const me = App.me, m = prof.member, pl = prof.player;
  view.innerHTML = `
    <div class="page-head"><h1>Mein Profil<small>${esc(prof.account.username)}${me.is_admin ? ' | Admin' : ''}</small></h1></div>
    <div class="grid g2" style="margin-bottom:16px">
      <div class="card"><h2>Konto</h2>
        <div class="form">
          <div class="field full"><label>Anzeigename</label><input class="input" id="pf_dn" value="${esc(prof.account.display_name || '')}"></div>
          <div class="field full"><label for="pf_acc_email">E-Mail-Adresse</label><input class="input" id="pf_acc_email" type="email" value="${esc(prof.account.email || m?.email || '')}" placeholder="name@beispiel.de">
            <div class="hint">Für „Passwort vergessen“ bei der Anmeldung und für Benachrichtigungen.</div></div>
          <div class="field full"><label for="pf_sig_phone">Telefon in der Mail-Signatur (optional)</label><input class="input" id="pf_sig_phone" type="tel" maxlength="40" value="${esc(prof.account.sig_phone || '')}" placeholder="z. B. 0151 23456789">
            <div class="hint">Steht unter deinem Namen in Mails aus dem Hub, zum Antippen auf dem Handy. Leer lassen = keine Nummer.</div></div>
        </div>
        <div class="btn-row" style="margin-top:10px"><button class="btn" id="pf_dn_save">Speichern</button></div>
        <h3 style="margin-top:22px">Passwort ändern</h3>
        <form class="form" id="pw_form" onsubmit="return false">
          <input type="text" autocomplete="username" value="${esc(prof.account.username)}" hidden>
          <div class="field full"><label>Bisheriges Passwort</label><input class="input" type="password" id="pw_old" autocomplete="current-password"></div>
          <div class="field"><label>Neues Passwort</label><input class="input" type="password" id="pw_new" autocomplete="new-password"></div>
          <div class="field"><label>Wiederholen</label><input class="input" type="password" id="pw_new2" autocomplete="new-password"></div>
        </form>
        <div class="btn-row" style="margin-top:10px"><button class="btn" id="pw_save">Passwort ändern</button></div>
      </div>
      <div class="card"><h2>Meine Rechte</h2>
        <p class="muted">${me.is_admin ? 'Als Admin darfst du alles.' : me.groups.length ? 'Gruppen: <b>' + esc(me.groups.join(', ')) + '</b>' : 'Du bist noch keiner Gruppe zugeordnet.'}</p>
        <div class="list">${Object.entries(AREA_SHORT).map(([a, l]) => `<div class="list-item"><div class="grow">${l}</div>${levelBadge(me.perms[a] || 0)}</div>`).join('')}</div>
        ${pl ? `<h3 style="margin-top:18px">Im Kader</h3><div class="muted">${esc([pl.number ? '#' + pl.number : '', pl.kind === 'Spieler' ? [pl.position, pl.unit].filter(Boolean).join(' | ') : pl.role].filter(Boolean).join(' | '))}</div>` : ''}
      </div>
    </div>
    <div class="card" id="tf_card" style="margin-bottom:16px"></div>
    <div class="card"><h2>Meine Daten</h2>
      ${m ? `<form class="form" id="pf_form" onsubmit="return false">
          <div class="field"><label>Name</label><input class="input" value="${esc(fullName(m))}" disabled></div>
          <div class="field"><label>Mitglied seit</label><input class="input" value="${esc(fmtDate(m.member_since) || '')}" disabled></div>
          <div class="field"><label>E-Mail</label><input class="input" id="pf_email" type="text" value="${esc(m.email || '')}"></div>
          <div class="field"><label>Telefon</label><input class="input" id="pf_phone" value="${esc(m.phone || '')}"></div>
          <div class="field full"><label>Straße und Hausnummer</label><input class="input" id="pf_street" value="${esc(m.street || '')}"></div>
          <div class="field"><label>PLZ</label><input class="input" id="pf_zip" value="${esc(m.zip || '')}"></div>
          <div class="field"><label>Ort</label><input class="input" id="pf_city" value="${esc(m.city || '')}"></div>
          <div class="field full"><label>Notfallkontakt (Name und Telefon)</label><input class="input" id="pf_emergency" value="${esc(m.emergency_contact || '')}"></div>
          <div class="field full"><label class="check"><input type="checkbox" id="pf_consent" ${Number(m.consent_photo) ? 'checked' : ''}> Ich bin einverstanden, dass Fotos und Videos von mir auf den Kanälen des SV Amisia Wolthusen veröffentlicht werden.</label>
            <div class="hint">Du kannst die Einwilligung jederzeit hier widerrufen.</div></div>
        </form>
        <div class="btn-row" style="margin-top:12px"><button class="btn primary" id="pf_save">Daten speichern</button></div>`
      : '<div class="muted">Dein Zugang ist noch keinem Mitgliedsprofil zugeordnet. Das macht der Admin unter Konten.</div>'}
    </div>
    ${prof.notify_kinds.length ? `<div class="card" style="margin-top:16px"><h2>Benachrichtigungen per E-Mail</h2>
      ${prof.mail_ready ? '' : '<div class="warnline" style="margin-bottom:8px">Der E-Mail-Versand ist noch nicht eingerichtet (Admin: Einstellungen). Deine Auswahl gilt, sobald er läuft.</div>'}
      <p class="muted small">Die Mails gehen an die E-Mail-Adresse oben bei „Konto“.</p>
      <div class="form">
        ${prof.notify_kinds.map(k => `<div class="field full"><label class="check"><input type="checkbox" data-nf="${k.key}" ${(() => { try { return JSON.parse(prof.account.notify || '[]'); } catch { return []; } })().includes(k.key) ? 'checked' : ''}> ${esc(k.label)}</label></div>`).join('')}</div>
      <div class="btn-row" style="margin-top:10px"><button class="btn" id="nf_save">Benachrichtigungen speichern</button></div></div>` : ''}`;
  view.insertAdjacentHTML('beforeend', '<div class="card" style="margin-top:16px" id="push_card"></div><div class="card" style="margin-top:16px" id="tabbar_card"></div>');
  pushCard($('#push_card'));
  tabbarCard($('#tabbar_card'));
  twofaCard($('#tf_card'), prof.account.username);
  if ($('#nf_save')) $('#nf_save').onclick = async () => {
    try {
      if (!$('#pf_acc_email').value.trim() && $$('[data-nf]').some(c => c.checked)) return alert('Bitte oben bei „Konto“ zuerst eine E-Mail-Adresse eintragen und speichern.');
      await api('profile', 'PUT', { account_email: $('#pf_acc_email').value.trim(), notify: $$('[data-nf]').filter(c => c.checked).map(c => c.dataset.nf) });
      toast('Benachrichtigungen gespeichert');
    } catch (e) { alert(e.message); }
  };
  $('#pf_dn_save').onclick = async () => {
    try { await api('profile', 'PUT', { display_name: $('#pf_dn').value, account_email: $('#pf_acc_email').value.trim(), sig_phone: $('#pf_sig_phone').value.trim() }); }
    catch (e) { return alert(e.message); }
    App.me = await api('me'); renderSideFoot(); toast('Gespeichert');
  };
  $('#pw_save').onclick = async () => {
    if ($('#pw_new').value !== $('#pw_new2').value) return alert('Die neuen Passwörter stimmen nicht überein.');
    try { await api('me/password', 'PUT', { old: $('#pw_old').value, new: $('#pw_new').value }); toast('Passwort geändert'); $('#pw_form').reset(); }
    catch (e) { alert(e.message); }
  };
  if (m) $('#pf_save').onclick = async () => {
    await api('profile', 'PUT', {
      email: $('#pf_email').value, phone: $('#pf_phone').value, street: $('#pf_street').value, zip: $('#pf_zip').value,
      city: $('#pf_city').value, emergency_contact: $('#pf_emergency').value, consent_photo: $('#pf_consent').checked ? 1 : 0,
    });
    toast('Deine Daten wurden gespeichert');
  };
};

/* Zwei-Faktor-Anmeldung (TOTP) im eigenen Profil: einrichten, Wiederherstellungscodes, ausschalten */
async function twofaCard(box, username) {
  const st = await api('me/2fa');
  const pwField = id => `<form onsubmit="return false"><input type="text" autocomplete="username" value="${esc(username)}" hidden>
    <div class="field full"><label for="${id}">Dein Passwort zur Bestätigung</label><input class="input" type="password" id="${id}" autocomplete="current-password"></div></form>`;
  const showCodes = codes => {
    box.innerHTML = `<h2>Wiederherstellungscodes</h2>
      <div class="warnline" style="margin-bottom:10px">Speichere diese Codes jetzt (ausdrucken oder im Passwort-Manager ablegen). Sie werden nur dieses eine Mal angezeigt.
        Jeder Code funktioniert genau einmal, falls du dein Handy nicht zur Hand hast.</div>
      <pre id="tf_codes" style="font-size:16px;line-height:1.7;background:var(--bg-soft,#f4f4f4);padding:12px 16px;border-radius:8px;columns:2">${codes.map(esc).join('\n')}</pre>
      <div class="btn-row" style="margin-top:10px"><button class="btn" id="tf_copy">Codes kopieren</button><button class="btn primary" id="tf_done">Gespeichert, weiter</button></div>`;
    $('#tf_copy', box).onclick = () => copyText(codes.join('\n'));
    $('#tf_done', box).onclick = async () => { App.me = await api('me'); applyPermissions(); twofaCard(box, username); };
  };
  if (!st.enabled) {
    box.innerHTML = `<h2>Zwei-Faktor-Anmeldung</h2>
      ${st.required ? '<div class="warnline" style="margin-bottom:10px"><b>Für dein Konto ist die Zwei-Faktor-Anmeldung Pflicht.</b> Bis sie eingerichtet ist, kannst du im Hub nur dein Profil öffnen.</div>' : ''}
      <p class="muted">Schützt dein Konto, auch wenn jemand dein Passwort kennt: Bei der Anmeldung fragt der Hub zusätzlich nach einem Code aus einer Authenticator-App
        (z. B. Google Authenticator, Microsoft Authenticator, 2FAS oder die Passwort-App am iPhone).</p>
      <div class="form">${pwField('tf_pw')}</div>
      <div class="btn-row" style="margin-top:10px"><button class="btn primary" id="tf_start">Einrichten</button></div>`;
    $('#tf_start', box).onclick = async () => {
      let s;
      try { s = await api('me/2fa/setup', 'POST', { password: $('#tf_pw', box).value }); } catch (e) { return alert(e.message); }
      const grouped = s.secret.match(/.{1,4}/g).join(' ');
      box.innerHTML = `<h2>Zwei-Faktor-Anmeldung einrichten</h2>
        <ol style="line-height:1.7;padding-left:20px;margin-top:0">
          <li>Authenticator-App auf dem Handy öffnen.</li>
          ${window.qrSvg && window.qrSvg(s.uri) ? `<li>In der App „QR-Code scannen“ wählen und diesen Code scannen:<br>
            <div id="tf_qr" style="display:inline-block;margin:8px 0;padding:8px;background:#fff;border:1px solid var(--line);border-radius:8px">${window.qrSvg(s.uri, 220)}</div><br>
            <span class="muted small">Der QR-Code wird hier im Browser erzeugt und enthält deinen geheimen Schlüssel. Nicht abfotografieren oder weitergeben.</span></li>` : ''}
          <li>${window.qrSvg && window.qrSvg(s.uri) ? 'Oder direkt am Handy' : 'Am Handy'}: <a class="btn sm" href="${esc(s.uri)}">In der App öffnen</a><br>
            Sonst in der App „Schlüssel eingeben“ wählen und eintragen:<br>
            Konto: <b>${esc(s.issuer)} (${esc(s.account)})</b><br>
            Schlüssel: <code id="tf_secret" style="font-size:16px;letter-spacing:1px;user-select:all">${esc(grouped)}</code> <button class="btn sm" id="tf_cp">Kopieren</button><br>
            <span class="muted small">Art: zeitbasiert, 6 Ziffern, 30 Sekunden</span></li>
          <li>Den 6-stelligen Code aus der App hier eingeben:</li>
        </ol>
        <div class="form"><div class="field"><label for="tf_code">Code aus der App</label><input class="input" id="tf_code" inputmode="numeric" autocomplete="one-time-code" maxlength="7"></div></div>
        <div class="btn-row" style="margin-top:10px"><button class="btn" id="tf_cancel">Abbrechen</button><button class="btn primary" id="tf_ok">Bestätigen und einschalten</button></div>`;
      $('#tf_cp', box).onclick = () => copyText(s.secret);
      $('#tf_cancel', box).onclick = () => twofaCard(box, username);
      $('#tf_code', box).focus();
      $('#tf_ok', box).onclick = async () => {
        try { const r = await api('me/2fa/enable', 'POST', { code: $('#tf_code', box).value }); toast('Zwei-Faktor-Anmeldung ist eingeschaltet'); showCodes(r.codes); }
        catch (e) { alert(e.message); }
      };
    };
    return;
  }
  box.innerHTML = `<h2>Zwei-Faktor-Anmeldung <span class="badge ok">eingeschaltet</span></h2>
    <p class="muted">Bei der Anmeldung fragt der Hub nach dem Code aus deiner Authenticator-App.
      ${st.required ? 'Für dein Konto ist sie Pflicht.' : ''}</p>
    <p class="${st.recovery_left <= 2 ? 'warnline' : 'muted small'}">Übrige Wiederherstellungscodes: <b>${st.recovery_left}</b>${st.recovery_left <= 2 ? '. Erzeuge bitte neue.' : ''}</p>
    <div class="form">${pwField('tf_pw')}</div>
    <div class="btn-row" style="margin-top:10px"><button class="btn" id="tf_new">Neue Wiederherstellungscodes</button>
      ${st.required ? '' : '<button class="btn danger" id="tf_off">Ausschalten</button>'}</div>
    <div class="hint" style="margin-top:8px">Neues Handy oder App verloren und keine Codes mehr? Dann kann ein Admin die Zwei-Faktor-Anmeldung zurücksetzen.</div>`;
  $('#tf_new', box).onclick = async () => {
    if (!confirmBox('Neue Wiederherstellungscodes erzeugen? Die bisherigen gelten danach nicht mehr.')) return;
    try { const r = await api('me/2fa/recovery', 'POST', { password: $('#tf_pw', box).value }); showCodes(r.codes); } catch (e) { alert(e.message); }
  };
  if ($('#tf_off', box)) $('#tf_off', box).onclick = async () => {
    if (!confirmBox('Zwei-Faktor-Anmeldung wirklich ausschalten? Dein Konto ist dann nur noch mit dem Passwort geschützt.')) return;
    try { await api('me/2fa/disable', 'POST', { password: $('#tf_pw', box).value }); toast('Ausgeschaltet'); twofaCard(box, username); } catch (e) { alert(e.message); }
  };
}

