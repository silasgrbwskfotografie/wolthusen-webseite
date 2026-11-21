/* ====================================================================== */
/* Verwaltung: Konten */
async function accountDialog(user, member) {
  const [groups, members, players] = await Promise.all([api('admin/groups'), load('members', true).catch(() => []), load('players', true).catch(() => [])]);
  const isNew = !user;
  // Neuer Zugang: Person aus Kader & Staff übernehmen (füllt Name, Benutzername, E-Mail und passende Gruppen vor)
  const kader = [...players].filter(p => Number(p.active) || (user && p.id == user.player_id)).sort((a, b) => fullName(a).localeCompare(fullName(b)));
  const u = user || {
    username: member ? slug(`${member.first_name || ''} ${member.last_name || ''}`) : '', display_name: member ? fullName(member) : '',
    email: member?.email || '', member_id: member?.id || null, is_admin: false, active: 1, overrides: {},
    groups: member ? groups.filter(g => g.name.toLowerCase().startsWith((member.member_type || '').toLowerCase().slice(0, 5))).map(g => g.id) : [],
  };
  openModal(`
    <h2>${isNew ? 'Einladen' : 'Zugang bearbeiten'}</h2>
    ${isNew ? '<p class="muted small" style="margin-top:0">Lege hier schon Gruppen und Rechte fest. Die Person bekommt einen Einladungslink, wählt Benutzername und Passwort und trägt ihre Angaben selbst ein, bei Bedarf auch die für Kader &amp; Staff wie im Spielerbogen.</p>' : ''}
    <div class="form">
      ${isNew ? `<div class="field"><label>Angaben für Kader &amp; Staff abfragen</label><select class="input" id="ac_kind">
          <option value="">Nein, nur Zugang</option><option value="Spieler">Ja, als Spieler</option><option value="Coach">Ja, als Coach</option><option value="Staff">Ja, als Staff</option></select>
          <small class="muted">Die Angaben landen als Eingang unter Kader &amp; Staff und kommen erst nach deiner Prüfung in den Kader.</small></div>
        <div class="field" id="ac_team_f"><label>Mannschaft</label><select class="input" id="ac_team">${TEAMS.map(t => `<option>${esc(t)}</option>`).join('')}</select>
          <small class="muted">Jugendspieler (Minderjährige) bitte nicht per Einladung, nur Coaches und Staff der Jugend.</small></div>` : ''}
      ${kader.length ? `<div class="field full"><label>${isNew ? 'Aus Kader &amp; Staff übernehmen (optional)' : 'Person in Kader &amp; Staff'}</label>
        <select class="input" id="ac_pl"><option value="">${isNew ? 'Person wählen' : '(keine)'}</option>${kader.map(p => `<option value="${p.id}" ${user && p.id == user.player_id ? 'selected' : ''}>${esc(playerLabel(p))}</option>`).join('')}</select>
        <small class="muted">${isNew ? 'Füllt Anzeigename, Benutzername, E-Mail und passende Gruppen aus. Alles lässt sich danach noch ändern. ' : ''}Verknüpft das Konto mit der Person im Kader.</small></div>` : ''}
      <div class="field"><label>${isNew ? 'Name (optional, für die Übersicht)' : 'Anzeigename'}</label><input class="input" id="ac_dn" value="${esc(u.display_name || '')}"></div>
      <div class="field"><label>Benutzername (für die Anmeldung)</label><input class="input" id="ac_un" value="${esc(u.username || '')}" autocomplete="off" ${isNew ? 'placeholder="leer lassen: die Person wählt ihn selbst"' : ''}></div>
      <div class="field"><label>E-Mail (optional)</label><input class="input" id="ac_em" value="${esc(u.email || '')}">
        ${isNew ? '<label class="check" style="margin-top:6px"><input type="checkbox" id="ac_mail" checked> Einladungslink per E-Mail schicken</label>' : ''}
        ${!isNew && u.phone ? `<small class="muted">Telefon: ${esc(u.phone)}</small>` : ''}</div>
      <div class="field"><label>Mitgliedsprofil</label><select class="input" id="ac_mem"><option value="">(keins)</option>
        ${members.sort((a, b) => fullName(a).localeCompare(fullName(b))).map(m => `<option value="${m.id}" ${m.id == u.member_id ? 'selected' : ''}>${esc(fullName(m))}</option>`).join('')}</select></div>
      <div class="field full"><label>Gruppen</label><div class="chk-grid">
        ${groups.map(g => `<label class="check"><input type="checkbox" class="ac_g" value="${g.id}" ${u.groups.includes(g.id) ? 'checked' : ''}> ${esc(g.name)}</label>`).join('')}</div></div>
      <div class="field full"><label>Rechte pro Bereich</label>
        <table class="perm-table"><thead><tr><th>Bereich</th><th>Aus Gruppen</th><th>Ausnahme für diese Person</th><th>Ergebnis</th></tr></thead><tbody>
        ${Object.entries(AREA_SHORT).map(([a, l]) => `<tr><td><b>${l}</b></td><td id="ac_gl_${a}"></td>
          <td><select class="input" id="ac_ov_${a}"><option value="">wie Gruppe</option>${LEVELS.map((t, i) => `<option value="${i}" ${u.overrides[a] === i ? 'selected' : ''}>${t}</option>`).join('')}</select></td>
          <td id="ac_ef_${a}"></td></tr>`).join('')}
        </tbody></table></div>
      <div class="field"><label for="ac_role">Rolle in der Signatur (optional)</label><input class="input" id="ac_role" list="ac_roles" value="${esc(u.mail_role || '')}" placeholder="leer: Gruppen der Person, z. B. Vorstand | Media Team">
        <datalist id="ac_roles">${[...STAFF_ROLES, 'Vorstand', 'Abteilungsleitung', 'Kassenwart', 'Social Media Team', 'Media Team', 'Spieler'].map(r => `<option value="${esc(r)}">`).join('')}</datalist>
        <small class="muted">Steht in der Signatur unter dem Namen. Leer lassen, dann stehen dort die Gruppen (ohne „Wartung“).</small></div>
      <div class="field"><label class="check"><input type="checkbox" id="ac_admin" ${u.is_admin ? 'checked' : ''}> Admin (darf alles, inkl. Konten und Einstellungen)</label></div>
      <div class="field"><label class="check"><input type="checkbox" id="ac_active" ${Number(u.active) ? 'checked' : ''}> Zugang aktiv</label></div>
      ${!isNew ? `<div class="field full"><label>Mail-Konten</label><div class="muted small">${u.own_mail ? esc(u.own_mail) : 'keins, Antworten gehen über das Vereinspostfach'} · zuweisen unter <a href="#/emails" onclick="closeModal()">E-Mails</a></div></div>` : ''}
      ${!isNew ? `<div class="field full"><label>Anmeldung</label><div class="btn-row" style="align-items:center">
        ${u.twofa ? '<span class="badge ok">Zwei-Faktor an</span> <button class="btn sm" id="ac_2fa">Zwei-Faktor zurücksetzen</button>'
          : `<span class="badge ${u.twofa_required ? 'warn' : ''}">Zwei-Faktor aus${u.twofa_required ? ' (Pflicht)' : ''}</span>`}
        ${u.locked ? '<span class="badge warn">vorübergehend gesperrt</span> <button class="btn sm" id="ac_unlock">Sperre aufheben</button>' : ''}</div></div>` : ''}
    </div>
    <div class="modal-foot">
      <div class="btn-row">${!isNew ? '<button class="btn danger" id="ac_del">Löschen</button><button class="btn" id="ac_inv">Neuer Einladungslink</button>' : ''}</div>
      <div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="ac_save">${isNew ? 'Einladung erstellen' : 'Speichern'}</button></div>
    </div>`);
  const box = $('#modalBox');
  const calc = () => {
    const gsel = $$('.ac_g', box).filter(c => c.checked).map(c => Number(c.value));
    const admin = $('#ac_admin', box).checked;
    Object.keys(AREA_SHORT).forEach(a => {
      const gl = Math.max(0, ...groups.filter(g => gsel.includes(g.id)).map(g => g.perms[a] || 0));
      const ov = $(`#ac_ov_${a}`, box).value;
      const ef = admin ? 2 : ov === '' ? gl : Number(ov);
      $(`#ac_gl_${a}`, box).innerHTML = `<span class="muted small">${LEVELS[gl]}</span>`;
      $(`#ac_ef_${a}`, box).innerHTML = levelBadge(ef);
    });
  };
  box.addEventListener('change', calc); calc();
  if ($('#ac_kind', box)) {
    const kindChanged = () => {
      const k = $('#ac_kind', box).value;
      $('#ac_team_f', box).style.display = k ? '' : 'none';
      $$('#ac_team option', box).forEach(o => { o.disabled = k === 'Spieler' && YOUTH_TEAMS.includes(o.value); });
      if (k === 'Spieler' && YOUTH_TEAMS.includes($('#ac_team', box).value)) $('#ac_team', box).value = TEAMS[0];
      if (k) {   // passende Gruppe vorschlagen: Spieler -> Spieler, Coach -> Trainer, Staff -> Helfer
        const want = { Spieler: 'spieler', Coach: 'trainer', Staff: 'helfer' }[k];
        const g = groups.find(x => x.name.toLowerCase() === want);
        if (g) { const c = $$('.ac_g', box).find(x => x.value == g.id); if (c) c.checked = true; }
        calc();
      }
    };
    $('#ac_kind', box).onchange = kindChanged; kindChanged();
    const em = $('#ac_em', box), mail = $('#ac_mail', box);
    const mailState = () => { mail.disabled = !em.value.includes('@'); if (mail.disabled) mail.checked = false; };
    em.oninput = () => { mailState(); if (em.value.includes('@') && !mail.dataset.touched) mail.checked = true; };
    mail.onchange = () => { mail.dataset.touched = '1'; };
    mailState();
  }
  if ($('#ac_pl', box)) $('#ac_pl', box).onchange = e => {
    const p = kader.find(x => x.id == e.target.value);
    if (!p || !isNew) return;
    $('#ac_dn', box).value = fullName(p);
    $('#ac_un', box).value = slug(`${p.first_name || ''} ${p.last_name || ''}`);
    if (p.email) $('#ac_em', box).value = p.email;
    const m = members.find(x => fullName(x).toLowerCase() === fullName(p).toLowerCase());
    if (m) $('#ac_mem', box).value = m.id;
    // Gruppen passend zur Art: Spieler -> Spieler, Coach -> Trainer, Staff -> Helfer; Social Media Betreuer zusätzlich Media Team
    const want = [p.kind === 'Coach' ? 'trainer' : p.kind === 'Staff' ? 'helfer' : 'spieler'];
    if ([p.role, p.extra_role].includes('Social Media Betreuer')) want.push('media team');
    const ids = groups.filter(g => want.includes(g.name.toLowerCase())).map(g => String(g.id));
    $$('.ac_g', box).forEach(c => { c.checked = ids.includes(c.value); });
    calc();
  };
  const collect = () => {
    const overrides = {};
    Object.keys(AREA_SHORT).forEach(a => { const v = $(`#ac_ov_${a}`, box).value; if (v !== '') overrides[a] = Number(v); });
    return {
      display_name: $('#ac_dn', box).value, username: $('#ac_un', box).value.trim(), email: $('#ac_em', box).value,
      member_id: $('#ac_mem', box).value ? Number($('#ac_mem', box).value) : null,
      ...($('#ac_pl', box) ? { player_id: $('#ac_pl', box).value ? Number($('#ac_pl', box).value) : null } : {}),
      groups: $$('.ac_g', box).filter(c => c.checked).map(c => Number(c.value)), overrides,
      is_admin: $('#ac_admin', box).checked, active: $('#ac_active', box).checked,
      mail_role: $('#ac_role', box).value.trim(),
      ...($('#ac_kind', box) ? { kader: { kind: $('#ac_kind', box).value, team: $('#ac_team', box).value }, send_mail: $('#ac_mail', box).checked } : {}),
    };
  };
  $('#ac_save', box).onclick = async () => {
    try {
      if (isNew) {
        const data = collect();
        if (data.is_admin && !confirmBox('Diese Person wird Admin und darf alles, auch Konten und Einstellungen. Wirklich?')) return;
        const r = await api('admin/users', 'POST', data);
        showInvite(data.display_name, data.username, r.invite, r);
      } else {
        await api('admin/users/' + u.id, 'PUT', collect());
        closeModal(); toast('Gespeichert');
      }
      invalidate('members'); route();
    } catch (e) { alert(e.message); }
  };
  if (!isNew) {
    $('#ac_inv', box).onclick = async () => {
      const mail = !!u.email && confirmBox(`Den neuen Link auch per E-Mail an ${u.email} schicken? (Abbrechen = nur Link anzeigen)`);
      const r = await api(`admin/users/${u.id}/invite`, 'POST', { send_mail: mail });
      showInvite(u.invite_open && u.display_name === 'Einladung offen' ? '' : u.display_name, u.invite_open ? '' : u.username, r.invite, r);
    };
    if ($('#ac_2fa', box)) $('#ac_2fa', box).onclick = async () => {
      if (!confirmBox(`Zwei-Faktor-Anmeldung von ${u.display_name || u.username} zurücksetzen? Die Person meldet sich danach nur mit dem Passwort an und richtet sie neu ein. Das steht im Protokoll.`)) return;
      try { await api(`admin/users/${u.id}/2fa-reset`, 'POST'); closeModal(); toast('Zwei-Faktor-Anmeldung zurückgesetzt'); route(); } catch (e) { alert(e.message); }
    };
    if ($('#ac_unlock', box)) $('#ac_unlock', box).onclick = async () => {
      try { await api(`admin/users/${u.id}/unlock`, 'POST'); closeModal(); toast('Sperre aufgehoben'); route(); } catch (e) { alert(e.message); }
    };
    $('#ac_del', box).onclick = async () => {
      if (!confirmBox(`Zugang von ${u.display_name || u.username} löschen? Das Mitgliedsprofil bleibt erhalten.`)) return;
      try { await api('admin/users/' + u.id, 'DELETE'); closeModal(); toast('Zugang gelöscht'); route(); } catch (e) { alert(e.message); }
    };
  }
}

function showInvite(name, username, link, res = {}) {
  const first = (name || '').split(' ')[0];
  const text = noDashes(`Hallo${first ? ' ' + first : ''}, hier ist deine Einladung zum Wolthusen Hub 💜\n\n${username ? `Benutzername: ${username}\n` : ''}Zugang anlegen und Angaben eintragen: ${link}\n\nDer Link ist ${res.days || 14} Tage gültig und nur für dich.`);
  openModal(`<h2>Einladungslink</h2>
    ${res.mailed ? '<p><span class="badge ok">Per E-Mail verschickt</span></p>' : res.mail_error ? `<p><span class="badge warn">E-Mail nicht verschickt</span> <span class="small">${esc(res.mail_error)}</span></p>` : ''}
    <p>${res.mailed ? 'Zusätzlich kannst du den Link auch selbst schicken.' : `Schick diesen Link an <b>${esc(name || username || 'die Person')}</b>.`} Damit legt die Person Benutzername und Passwort fest und trägt ihre Angaben ein. Der Link ist ${res.days || 14} Tage gültig und funktioniert nur einmal.</p>
    <textarea class="input" id="inv_txt" rows="7" style="width:100%">${esc(text)}</textarea>
    <div class="modal-foot"><div class="btn-row"><button class="btn" id="inv_link">Nur Link kopieren</button>
      <a class="btn" target="_blank" rel="noopener" href="https://wa.me/?text=${encodeURIComponent(text)}">Per WhatsApp senden</a></div>
      <div class="btn-row"><button class="btn primary" id="inv_copy">Nachricht kopieren</button><button class="btn" onclick="closeModal()">Fertig</button></div></div>`);
  $('#inv_copy').onclick = () => copyText($('#inv_txt').value);
  $('#inv_link').onclick = () => copyText(link);
}

App.pages.accounts = async (view) => {
  const [users, groups, , policy] = await Promise.all([api('admin/users'), api('admin/groups'), load('members', true).catch(() => []), api('admin/2fa-policy')]);
  const gname = id => groups.find(g => g.id === id)?.name || '';
  const status = u => (!Number(u.active) ? '<span class="badge">deaktiviert</span>' : u.invite_open ? `<span class="badge warn">Einladung offen${u.invite_kader ? ' (' + esc(u.invite_kader) + ')' : ''}</span>` : '<span class="badge ok">aktiv</span>')
    + (u.locked ? ' <span class="badge warn">gesperrt</span>' : '')
    + (u.twofa ? ' <span class="badge ok" title="Zwei-Faktor-Anmeldung an">2FA</span>' : u.twofa_required ? ' <span class="badge warn" title="Zwei-Faktor-Anmeldung ist Pflicht, aber noch nicht eingerichtet">2FA fehlt</span>' : '');
  view.innerHTML = `
    <div class="page-head"><h1>Konten<small>${users.length} Zugänge</small></h1>
      <div class="btn-row"><a class="btn" href="#/groups">Gruppen &amp; Rechte</a><button class="btn primary" id="ac_new">+ Einladen</button></div></div>
    <div class="table-wrap"><table><thead><tr><th>Name</th><th>Benutzername</th><th>Gruppen</th><th>Rechte</th><th>Status</th><th>Zuletzt angemeldet</th><th></th></tr></thead><tbody>
    ${users.map(u => `<tr style="${Number(u.active) ? '' : 'opacity:.55'}">
      <td><b>${esc(u.display_name || u.username)}</b> ${u.is_admin ? '<span class="badge dark">Admin</span>' : ''}${u.member_id ? `<div class="muted small">Mitglied: ${esc(fullName(byId(App.cache.members, u.member_id)))}</div>` : ''}</td>
      <td class="small">${esc(u.username)}${u.own_mail ? `<div class="muted">✉ ${esc(u.own_mail)}</div>` : ''}${u.mail_role ? `<div class="muted">${esc(u.mail_role)}</div>` : ''}</td>
      <td>${u.groups.map(id => `<span class="badge">${esc(gname(id))}</span>`).join(' ') || '<span class="muted small">keine</span>'}${Object.keys(u.overrides).length ? ' <span class="badge warn" title="Hat Ausnahmen">Ausnahme</span>' : ''}</td>
      <td style="white-space:nowrap">${permChips(u.effective)}</td>
      <td>${status(u)}</td>
      <td class="small muted">${u.last_login ? new Date(u.last_login).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : 'nie'}</td>
      <td class="actions"><button class="btn sm ghost" data-e="${u.id}">Bearbeiten</button></td></tr>`).join('')}
    </tbody></table></div>
    <div class="hint" style="margin-top:10px">Mit „+ Einladen“ legst du Gruppen und Rechte vorab fest. Die Person bekommt einen Link (per Mail oder zum Weiterschicken), wählt Benutzername und Passwort und trägt ihre Angaben ein, auf Wunsch auch die für Kader &amp; Staff.</div>
    <div class="card" style="margin-top:16px"><h2>Zwei-Faktor-Anmeldung als Pflicht</h2>
      <p class="muted small">Wer betroffen ist und sie noch nicht eingerichtet hat, kann im Hub nur noch sein Profil öffnen, bis die Einrichtung erledigt ist.
        Unabhängig davon gilt: Nach 5 falschen Versuchen ist ein Konto für 15 Minuten gesperrt, die Person bekommt dazu eine Mail.</p>
      <div class="form">
        <div class="field full"><label class="check"><input type="checkbox" id="tfp_admins" ${policy.twofa_admins ? 'checked' : ''}> Pflicht für Admins</label></div>
        <div class="field full"><label class="check"><input type="checkbox" id="tfp_finance" ${policy.twofa_finance ? 'checked' : ''}> Pflicht für Konten mit Schreibrecht bei Finanzen</label></div>
      </div></div>`;
  $$('#tfp_admins, #tfp_finance').forEach(c => c.onchange = async () => {
    try { await api('admin/2fa-policy', 'PUT', { twofa_admins: $('#tfp_admins').checked, twofa_finance: $('#tfp_finance').checked }); toast('Gespeichert'); route(); }
    catch (e) { alert(e.message); route(); }
  });
  $('#ac_new').onclick = () => accountDialog(null, null);
  $$('[data-e]').forEach(b => b.onclick = () => accountDialog(users.find(u => u.id == b.dataset.e)));
};

/* ====================================================================== */
/* Verwaltung: Gruppen und Rechte */
App.pages.groups = async (view) => {
  const groups = await api('admin/groups');
  view.innerHTML = `
    <div class="page-head"><h1>Gruppen &amp; Rechte<small>Was jede Gruppe in welchem Bereich darf</small></h1>
      <div class="btn-row"><a class="btn" href="#/accounts">Konten</a><button class="btn primary" id="g_new">+ Gruppe</button></div></div>
    <div class="table-wrap"><table class="perm-matrix"><thead><tr><th>Gruppe</th>${Object.values(AREA_SHORT).map(l => `<th>${l}</th>`).join('')}<th>Personen</th><th></th></tr></thead><tbody>
    ${groups.map(g => `<tr data-g="${g.id}">
      <td><input class="input g_name" value="${esc(g.name)}" style="font-weight:600"><input class="input g_desc small" value="${esc(g.description || '')}" placeholder="Beschreibung" style="margin-top:4px"></td>
      ${Object.keys(AREA_SHORT).map(a => `<td><select class="input g_lvl lvl${g.perms[a] || 0}" data-a="${a}">${LEVELS.map((t, i) => `<option value="${i}" ${(g.perms[a] || 0) === i ? 'selected' : ''}>${t}</option>`).join('')}</select></td>`).join('')}
      <td>${g.members}</td>
      <td class="actions"><button class="btn sm ghost danger" data-del="${g.id}">Löschen</button></td></tr>`).join('')}
    </tbody></table></div>
    <div class="card" style="margin-top:16px"><h2>So funktionieren die Rechte</h2>
      <div class="small" style="line-height:1.6">
        <b>Lesen</b> heißt ansehen, <b>Bearbeiten</b> heißt anlegen, ändern und löschen. Wer in mehreren Gruppen ist, bekommt pro Bereich das höchste Recht.
        Unter <a href="#/accounts">Konten</a> kannst du für einzelne Personen Ausnahmen festlegen, die das Gruppenrecht ersetzen. Admins dürfen immer alles.<br>
        <b>Medien:</b> Postplan, Auto-Posting, Webseite, News, Mediathek, Media Team &nbsp;|&nbsp; <b>Verein:</b> Spielplan, Kader, Gegner, Sponsoren &nbsp;|&nbsp;
        <b>Mitglieder:</b> Mitgliederliste mit Kontaktdaten &nbsp;|&nbsp; <b>Finanzen:</b> Buchungen, Dauerkarte, Sponsorenbeträge.<br>
        Spielplan, Kader, Gegner und Sponsoren (ohne Beträge) können alle sehen, die mindestens einen Bereich lesen dürfen, damit z. B. das Media Team Spiele für Posts auswählen kann.
        Sein eigenes Profil kann jeder selbst pflegen.
      </div></div>`;
  const save = async tr => {
    const perms = {}; $$('.g_lvl', tr).forEach(s => { perms[s.dataset.a] = Number(s.value); s.className = `input g_lvl lvl${s.value}`; });
    try { await api('admin/groups/' + tr.dataset.g, 'PUT', { name: $('.g_name', tr).value, description: $('.g_desc', tr).value, perms }); toast('Gespeichert'); }
    catch (e) { alert(e.message); }
  };
  $$('tr[data-g]').forEach(tr => tr.addEventListener('change', () => save(tr)));
  $$('[data-del]').forEach(b => b.onclick = async () => {
    const g = groups.find(x => x.id == b.dataset.del);
    if (!confirmBox(`Gruppe „${g.name}“ löschen?${g.members ? ` ${g.members} Personen verlieren damit die Rechte dieser Gruppe.` : ''}`)) return;
    await api('admin/groups/' + g.id, 'DELETE'); route();
  });
  $('#g_new').onclick = async () => {
    const name = prompt('Name der neuen Gruppe:'); if (!name) return;
    try { await api('admin/groups', 'POST', { name, perms: {} }); route(); } catch (e) { alert(e.message); }
  };
};

