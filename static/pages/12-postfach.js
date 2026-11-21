/* Postfach (Bereich postfach): Mails von info@... live über IMAP, nur als Text. Lesen 1, Antworten und Löschen 2 */
async function refreshMailBadge() {
  const b = $('#pfBadge'); if (!b || !can('postfach|ownmail')) return;
  // ungelesene Mails aus info@ und dem eigenen Postfach zusammen
  const boxes = [];
  if (can('postfach')) boxes.push('postfach/status');
  for (const mb of App.me?.mail_boxes || []) boxes.push('postfach/status?box=' + mb.key);
  let n = 0;
  for (const p of boxes) { try { const s = await api(p); n += Number(s.unseen) || 0; } catch { /* Postfach gerade nicht erreichbar */ } }
  b.style.display = n > 0 ? '' : 'none'; b.textContent = n > 99 ? '99+' : n;
  b.title = n === 1 ? '1 ungelesene Mail' : `${n} ungelesene Mails`;
}
const pfDate = d => { const x = new Date(d); if (isNaN(x)) return esc(d || '');
  const today = new Date().toDateString() === x.toDateString();
  return today ? x.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) : x.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit' }); };
const pfAddr = f => { const m = String(f || '').match(/<([^>]+)>/); return (m ? m[1] : String(f || '')).trim(); };
const pfEnc = s => encodeURIComponent(s);   // auch / wird kodiert, der Router trennt nur an echten /

App.pages.postfach = async (view, args = []) => {
  // Vereinspostfach (#/postfach/...) und die eigenen Mail-Konten der Person (#/postfach/acc<id>/...)
  let box = 'info';
  if (/^(own|acc\d+)$/.test(args[0] || '')) { box = args[0]; args = args.slice(1); }
  else if (!can('postfach') && (App.me.mail_boxes || []).length) box = App.me.mail_boxes[0].key;
  const pre = box === 'info' ? '#/postfach' : '#/postfach/' + box;
  const bq = box === 'info' ? '' : '&box=' + box;
  App._pfs = App._pfs || {};
  const st = App._pfs[box] || (App._pfs[box] = { folder: 'INBOX', page: 0, q: '' });
  if (args[0] === 'f' && args[1]) { st.folder = decodeURIComponent(args[1]); st.page = 0; }
  view.innerHTML = '<div class="card empty">Postfach wird geladen ...</div>';
  let info;
  try { info = await api('postfach/folders' + (box === 'info' ? '' : '?box=' + box)); }
  catch (e) {
    view.innerHTML = `<div class="page-head"><h1>Postfach</h1></div><div class="card"><b>Postfach nicht erreichbar</b><p>${esc(e.message)}</p>
      ${App.me.is_admin ? '<a class="btn" href="#/settings">Zu den Einstellungen</a>' : ''}</div>`;
    return;
  }
  const w = info.can_write;
  App._pfAddr = info.address;
  const folders = info.folders;
  if (!folders.some(f => f.name === st.folder)) st.folder = (folders.find(f => f.role === 'inbox') || folders[0] || { name: 'INBOX' }).name;
  const head = `<div class="page-head pf-head"><h1>Postfach<small>${esc(info.address)}</small></h1>
    <div class="btn-row">${w ? '<button class="btn primary pf-new" id="pf_new" aria-label="Neue Mail"><span aria-hidden="true">✎</span><span class="pf-lbl">Neue Mail</span></button>' : ''}${can('postfach') ? '<button class="btn keep" id="pf_lists" title="Gespeicherte Empfängerlisten">Verteiler</button>' : ''}<a class="btn keep pf-reload" href="${pre}/f/${pfEnc(st.folder)}" id="pf_reload" aria-label="Aktualisieren" title="Aktualisieren"><span aria-hidden="true">↻</span><span class="pf-lbl">Aktualisieren</span></a></div></div>`;
  const addrParts = a => { const i = String(a || '').indexOf('@'); return i > 0 ? [a.slice(0, i), a.slice(i)] : [a || '', '']; };
  const boxes = (info.boxes || []).length > 1 ? `<div class="pf-boxes" role="tablist" aria-label="Postfächer">${info.boxes.map(b => { const [loc, dom] = addrParts(b.address); const on = b.key === (info.box || box);
    return `<a role="tab" aria-selected="${on}" href="${b.key === 'info' ? '#/postfach/f/INBOX' : '#/postfach/' + b.key}" class="${on ? 'active' : ''}" title="${esc(b.address)} (${b.key === 'info' ? 'Vereinspostfach' : 'eigenes Postfach'})"><span class="pf-box-ic" aria-hidden="true">${esc(loc.charAt(0).toUpperCase())}</span><b>${esc(loc)}</b><span class="pf-dom">${esc(dom)}</span><span class="badge red pf-box-n" data-boxn="${b.key}" style="display:none"></span></a>`; }).join('')}</div>` : '';
  const side = `<div class="pf-side">${boxes}<nav class="pf-folders" aria-label="Ordner">${folders.map(f => `<a href="${pre}/f/${pfEnc(f.name)}" class="${f.name === st.folder ? 'active' : ''}"${f.name === st.folder ? ' aria-current="page"' : ''}>${esc(f.label)}${f.unseen ? ` <span class="badge red">${f.unseen}</span>` : ''}</a>`).join('')}</nav>${pfQuota(info.quota)}</div>`;
  view.innerHTML = `${head}<div class="pf-layout">${side}<div id="pf_main"><div class="card empty">Lädt ...</div></div></div>`;
  // ungelesene Mails je Postfach im Umschalter (jedes Postfach einzeln, blockiert die Seite nicht)
  if ((info.boxes || []).length > 1) info.boxes.forEach(async b => {
    try {
      const r = await api('postfach/status' + (b.key === 'info' ? '' : '?box=' + b.key)), n = Number(r.unseen) || 0, el = $(`[data-boxn="${b.key}"]`, view);
      if (el && n) { el.style.display = ''; el.textContent = n > 99 ? '99+' : n; el.title = n === 1 ? '1 ungelesene Mail' : `${n} ungelesene Mails`; }
    } catch { /* Postfach gerade nicht erreichbar */ }
  });
  const act = $('.pf-folders a.active', view), fnav = $('.pf-folders', view);   // aktiven Ordner in der Leiste sichtbar halten (Handy)
  if (act && fnav.scrollWidth > fnav.clientWidth && act.offsetLeft + act.offsetWidth > fnav.clientWidth) fnav.scrollLeft = act.offsetLeft - 14;
  if ($('#pf_lists')) $('#pf_lists').onclick = () => pfLists();
  if ($('#pf_new')) $('#pf_new').onclick = () => pfCompose({ box, signature_html: info.signature_html, send_as: info.send_as, senders: info.senders, sender: info.sender });
  const main = $('#pf_main');
  if (args[0] === 'm' && args[2]) return pfShow(main, decodeURIComponent(args[1]), args[2], w, { box });
  const isDone = f => f.split(/[./]/).pop().trim().toLowerCase() === 'erledigt';
  const role = (folders.find(f => f.name === st.folder) || {}).role || '';
  const quickDone = w && !isDone(st.folder) && !['sent', 'drafts', 'trash', 'junk'].includes(role);

  const loadList = async () => {
    main.innerHTML = '<div class="card empty">Lädt ...</div>';
    let r;
    try { r = await api(`postfach/messages?folder=${encodeURIComponent(st.folder)}&page=${st.page}${st.q ? '&q=' + encodeURIComponent(st.q) : ''}${bq}`); }
    catch (e) { main.innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
    const who = m => pfName(st.folder.match(/sent|gesend/i) ? m.to : m.from);
    main.innerHTML = `<div class="toolbar pf-toolbar"><label class="pf-search"><span aria-hidden="true">⌕</span><input class="input" id="pf_q" type="search" enterkeyhint="search" aria-label="Mails durchsuchen" placeholder="Suchen (Absender, Betreff, Text)" value="${esc(st.q)}"></label>
        <button class="btn sm keep" id="pf_qbtn">Suchen</button>${st.q ? '<button class="btn sm ghost keep" id="pf_qclr">Alle zeigen</button>' : ''}
        <span class="muted small pf-count">${r.total} Mail${r.total === 1 ? '' : 's'}</span>${r.items.length ? '<button class="btn sm keep" id="pf_selmode">Auswählen</button>' : ''}${r.total ? '<button class="btn sm ghost keep" id="pf_allread" title="Alle Mails in diesem Ordner als gelesen markieren">Alle gelesen</button>' : ''}${box === 'info' && r.items.some(m => m.inbox === 'neu') ? '<button class="btn sm ghost keep" id="pf_alldone" title="Alle neu-Hinweise in diesem Ordner entfernen, die Mails bleiben liegen">Alle erledigt</button>' : ''}</div>
      <div id="pf_bulk"></div>
      <div class="card pf-list">${r.items.map(m => `<a class="pf-row ${m.seen ? '' : 'unread'}" data-uid="${m.uid}" href="${pre}/m/${pfEnc(st.folder)}/${m.uid}">
          <span class="pf-av" role="checkbox" aria-checked="false" tabindex="0" aria-label="Mail auswählen" title="Auswählen" style="--h:${[...who(m)].reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 360, 7)}">${esc((who(m).replace(/[^\p{L}\p{N}]/gu, '').charAt(0) || '?').toUpperCase())}</span>
          <span class="pf-from">${esc(who(m))}</span>
          <span class="pf-subj">${m.inbox === 'neu' ? '<span class="badge red" title="noch nicht erledigt">neu</span> ' : ''}${m.answered ? '<span class="badge" title="beantwortet">↩</span> ' : ''}${esc(m.subject)}${m.attachment ? ' <span class="badge" title="mit Anhang">Anhang</span>' : ''}${m.task ? ` <span class="badge ${m.task.status === 'offen' ? 'warn' : 'ok'}" title="zugewiesen">→ ${esc(m.task.user)}</span>` : ''}</span>
          <span class="pf-date">${pfDate(m.date)}${quickDone ? `<button class="pf-done keep" data-done="${m.uid}" title="Erledigt: in den Ordner Erledigt verschieben" aria-label="Erledigt">✓</button>` : ''}</span></a>`).join('') || `<div class="empty pf-empty"><span aria-hidden="true">✉</span>${st.q ? 'Keine Treffer.' : 'Keine Mails in diesem Ordner.'}</div>`}</div>
      ${r.pages > 1 ? `<div class="btn-row" style="margin-top:10px">${st.page > 0 ? '<button class="btn sm keep" id="pf_prev">Neuere</button>' : ''}
        <span class="muted small">Seite ${r.page + 1} von ${r.pages}</span>${st.page < r.pages - 1 ? '<button class="btn sm keep" id="pf_next">Ältere</button>' : ''}</div>` : ''}`;
    // Auswahl: Avatar antippen (oder Leertaste) setzt den Haken, die Leiste bietet Gelesen, Erledigt, Zuweisen und Löschen für alle markierten
    const sel = new Set();
    let selMode = false;
    const bulk = () => {
      selMode = selMode || sel.size > 0;
      main.classList.toggle('pf-selmode', selMode);
      $$('.pf-row', main).forEach(a => { const on = sel.has(Number(a.dataset.uid)); a.classList.toggle('sel', on); $('.pf-av', a).setAttribute('aria-checked', on); });
      $('#pf_bulk').innerHTML = selMode ? `<div class="toolbar pf-bulk"><b>${sel.size} ausgewählt</b>${sel.size ? '' : ' <span class="muted small">Mails antippen, um sie zu markieren</span>'}
        <button class="btn sm keep" data-bulk="all">Alle auf dieser Seite</button>
        ${sel.size ? `<button class="btn sm keep" data-bulk="read">Gelesen</button>
        ${quickDone ? '<button class="btn sm keep" data-bulk="done" title="Wie der Haken an der Mail: erledigt und in den Ordner Erledigt">Erledigt</button>' : ''}
        ${w && box === 'info' ? '<button class="btn sm keep" data-bulk="assign">Zuweisen</button>' : ''}
        ${w ? '<button class="btn sm keep danger" data-bulk="del">Löschen</button>' : ''}` : ''}
        <button class="btn sm ghost keep" data-bulk="none">Fertig</button></div>` : '';
      $$('[data-bulk]', main).forEach(b => b.onclick = () => bulkRun(b.dataset.bulk));
    };
    const each = async (path, extra, okText) => {   // nacheinander, damit der Mailserver nicht überlastet wird
      const uids = [...sel]; let ok = 0, err = '';
      toast(`${uids.length} Mails werden bearbeitet ...`);
      for (const uid of uids) { try { await api(path, 'POST', { box, folder: st.folder, uid, ...extra }); ok++; } catch (e) { err = e.message; } }
      toast(err ? `${ok} von ${uids.length} ${okText}, Fehler: ${err}` : `${ok} Mail${ok === 1 ? '' : 's'} ${okText}`);
      sel.clear(); syncAppBadge(); refreshMailBadge(); loadList();
    };
    const bulkRun = async what => {
      if (what === 'all') { r.items.forEach(m => sel.add(m.uid)); return bulk(); }
      if (what === 'none') { sel.clear(); selMode = false; return bulk(); }
      if (what === 'read') return each('postfach/flag', { flag: 'seen', value: true }, 'als gelesen markiert');
      if (what === 'done') return each('postfach/handled', {}, 'erledigt');
      if (what === 'del') {
        if (!confirmBox(`${sel.size} Mail${sel.size === 1 ? '' : 's'} löschen? Sie kommen in den Papierkorb, im Papierkorb selbst werden sie endgültig gelöscht.`)) return;
        return each('postfach/delete', {}, 'gelöscht');
      }
      if (what === 'assign') pfAssign(st.folder, [...sel], { subject: sel.size === 1 ? (r.items.find(m => sel.has(m.uid)) || {}).subject : `${sel.size} Mails`, from: '' },
        () => { sel.clear(); refreshMailBadge(); loadList(); });
    };
    const toggle = (e, row) => { e.preventDefault(); e.stopPropagation(); const uid = Number(row.dataset.uid); sel.has(uid) ? sel.delete(uid) : sel.add(uid); bulk(); };
    $$('.pf-row', main).forEach(row => {
      const av = $('.pf-av', row);
      av.onclick = e => toggle(e, row); av.onkeydown = e => { if (e.key === ' ' || e.key === 'Enter') toggle(e, row); };
      row.addEventListener('click', e => { if (selMode && !e.target.closest('[data-done]')) toggle(e, row); });   // im Auswahlmodus markiert die ganze Zeile
    });
    if ($('#pf_selmode')) $('#pf_selmode').onclick = () => { selMode = true; bulk(); };
    const search = () => { st.q = $('#pf_q').value.trim(); st.page = 0; loadList(); };
    $('#pf_qbtn').onclick = search; $('#pf_q').onkeydown = e => { if (e.key === 'Enter') search(); };
    if ($('#pf_qclr')) $('#pf_qclr').onclick = () => { st.q = ''; st.page = 0; loadList(); };
    if ($('#pf_prev')) $('#pf_prev').onclick = () => { st.page--; loadList(); };
    if ($('#pf_alldone')) $('#pf_alldone').onclick = async () => {
      if (!confirmBox('Alle Mails in diesem Ordner als erledigt markieren? Die Hinweise „neu“ und die Erinnerungen verschwinden für alle, die Mails bleiben im Ordner.')) return;
      try { const x = await api('postfach/allhandled', 'POST', { box, folder: st.folder }); toast(`${x.count} Mail${x.count === 1 ? '' : 's'} als erledigt markiert`); syncAppBadge(); loadList(); refreshMailBadge(); }
      catch (err) { alert(err.message); }
    };
    if ($('#pf_allread')) $('#pf_allread').onclick = async () => {
      try { const x = await api('postfach/allread', 'POST', { box, folder: st.folder }); toast(x.count ? `${x.count} Mail${x.count === 1 ? '' : 's'} als gelesen markiert` : 'Alles schon gelesen'); loadList(); refreshMailBadge(); }
      catch (err) { alert(err.message); }
    };
    if ($('#pf_next')) $('#pf_next').onclick = () => { st.page++; loadList(); };
    $$('[data-done]', main).forEach(b => b.onclick = async e => {
      e.preventDefault(); e.stopPropagation(); b.disabled = true;
      try { const x = await api('postfach/handled', 'POST', { box, folder: st.folder, uid: Number(b.dataset.done) }); toast(x.note || 'Erledigt'); syncAppBadge(); loadList(); }
      catch (err) { alert(err.message); b.disabled = false; }
    });
  };
  loadList();
  refreshMailBadge();
};

async function pfShow(main, folder, uid, w, opts = {}) {
  let m;
  const box = opts.box || 'info', bq = box === 'info' ? '' : '&box=' + box;
  try { m = await api(`postfach/message?folder=${encodeURIComponent(folder)}&uid=${uid}${bq}`); }
  catch (e) { main.innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
  w = m.can_write;
  const back = opts.back || `${box === 'info' ? '#/postfach' : '#/postfach/' + box}/f/${pfEnc(folder)}`;
  const openTasks = m.tasks.filter(t => t.status === 'offen');
  const inDone = folder.split(/[./]/).pop().trim().toLowerCase() === 'erledigt';
  main.innerHTML = `<div class="card pf-msg">
      <div class="btn-row" style="margin-bottom:12px"><a class="btn sm keep" href="${back}">Zurück</a>
        ${w && m.draft ? '<button class="btn sm primary keep" id="pm_edit">Entwurf bearbeiten</button>' : ''}
        ${w && !m.draft ? '<button class="btn sm primary keep" id="pm_reply">Antworten</button><button class="btn sm keep" id="pm_all">Allen antworten</button>' : ''}
        ${m.can_assign ? '<button class="btn sm" id="pm_fwd">Weiterleiten</button><button class="btn sm" id="pm_assign">Zuweisen</button>' : ''}
        ${box !== 'info' && w ? '<button class="btn sm" id="pm_fwd">Weiterleiten</button>' : ''}
        ${!opts.task && !inDone && (m.can_assign || w) ? '<button class="btn sm keep" id="pm_handled" title="Als erledigt markieren und in den Ordner Erledigt verschieben">Erledigt</button>' : ''}
        ${opts.task ? `<button class="btn sm keep ${opts.task.status === 'offen' ? '' : 'ghost'}" id="pm_done">${opts.task.status === 'offen' ? 'Als erledigt markieren' : 'Wieder öffnen'}</button>` : ''}
        ${m.can_assign || (box !== 'info' && w) ? '<button class="btn sm keep" id="pm_unread">Als ungelesen</button><button class="btn sm danger" id="pm_del">Löschen</button>' : ''}</div>
      ${m.tasks.length ? `<div class="pf-tasks">${m.tasks.map(t => `<span class="badge ${t.status === 'offen' ? 'warn' : 'ok'}">${t.status === 'offen' ? 'Zugewiesen' : 'Erledigt'}: ${esc(t.user_name)}</span>
          ${t.note ? `<span class="small muted">${esc(t.note)}</span>` : ''}${m.can_assign ? ` <button class="btn sm ghost" data-untask="${t.id}" title="Zuweisung entfernen">×</button>` : ''}`).join(' ')}</div>` : ''}
      ${m.inbox ? (m.inbox.status === 'neu'
          ? `<div class="pf-tasks"><span class="badge red">Neu, noch nicht erledigt</span></div>`
          : `<div class="pf-tasks"><span class="badge ok">Erledigt</span><span class="small muted">${esc(m.inbox.by || 'außerhalb des Hubs')} hat sie ${esc(m.inbox.action)}${m.inbox.at ? ', ' + fmtStamp(m.inbox.at) : ''}</span></div>`) : ''}
      ${opts.task && opts.task.note ? `<div class="warnline" style="margin-bottom:10px"><b>Hinweis von ${esc(opts.task.by_name)}:</b> ${esc(opts.task.note)}</div>` : ''}
      <h2 style="margin:0 0 8px">${esc(m.subject)}</h2>
      <div class="small"><b>Von:</b> ${esc(m.from)}</div>
      <div class="small"><b>An:</b> ${esc(m.to)}${m.cc ? ` <b>Cc:</b> ${esc(m.cc)}` : ''}</div>
      <div class="small muted">${esc(new Date(m.date).toString() !== 'Invalid Date' ? new Date(m.date).toLocaleString('de-DE') : m.date)}${m.answered ? ' | beantwortet' : ''}</div>
      ${m.attachments.length ? `<div class="pf-att">${m.attachments.map(a => `<a class="btn sm keep" href="/api/postfach/attachment?folder=${encodeURIComponent(folder)}&uid=${uid}&i=${a.i}${bq}">${esc(a.name)} <span class="muted">${fmtSize(a.size)}</span></a>`).join('')}</div>` : ''}
      <pre class="pf-text">${esc(m.text || '(kein Text)')}</pre></div>`;
  if (typeof refreshMailBadge === 'function') refreshMailBadge();
  const quote = () => ({ head: `Am ${new Date(m.date).toLocaleString('de-DE')} schrieb ${m.from}:`, text: m.text || '' });
  const re = s => /^(re|aw):/i.test(s) ? s : 'Re: ' + s;
  const meAddrs = [(App._pfAddr || ''), (m.send_as || '')].map(a => a.toLowerCase());
  const base = { box, signature_html: m.signature_html, send_as: m.send_as, senders: m.senders, sender: m.sender, reply: { folder, uid }, after: opts.after };
  // Anfragen über die Webseite (ältere ohne Reply-To): Antwort an die E-Mail aus dem Formular statt an uns selbst
  const replyTo = () => {
    const a = pfAddr(m.reply_to || m.from);
    const web = /^Webseite: Anfrage von /.test(m.subject || '') && (m.text || '').match(/^E-Mail: ([^@\s]+@[^@\s]+\.[^@\s]+)$/m);
    return web && (meAddrs.includes(a.toLowerCase()) || !m.reply_to) ? web[1] : a;
  };
  if ($('#pm_edit')) $('#pm_edit').onclick = () => pfCompose({ box, signature_html: m.signature_html, send_as: m.send_as, senders: m.senders, sender: m.sender,
    to: m.to, cc: m.cc, subject: m.subject === '(ohne Betreff)' ? '' : m.subject, body: m.text, draft: { folder, uid } });
  if ($('#pm_reply')) $('#pm_reply').onclick = () => pfCompose({ ...base, to: replyTo(), subject: re(m.subject), quote: quote() });
  if ($('#pm_all')) $('#pm_all').onclick = () => {
    const others = [m.to, m.cc].join(',').split(',').map(pfAddr).filter(a => a && a.includes('@') && !meAddrs.includes(a.toLowerCase()));
    pfCompose({ ...base, to: replyTo(), cc: [...new Set(others)].join(', '), subject: re(m.subject), quote: quote() });
  };
  if ($('#pm_fwd')) $('#pm_fwd').onclick = () => pfCompose({ box, signature_html: m.signature_html, send_as: m.send_as, senders: m.senders, sender: m.sender, subject: /^(fwd|wg):/i.test(m.subject) ? m.subject : 'WG: ' + m.subject,
    source: { folder, uid },
    quote: { head: `---------- Weitergeleitete Nachricht ----------\nVon: ${m.from}\nDatum: ${m.date}\nBetreff: ${m.subject}\nAn: ${m.to}`, text: m.text || '', forward: true },
    note: m.attachments.length ? 'Anhänge werden nicht mit weitergeleitet. Bei Bedarf herunterladen und selbst anhängen.' : '' });
  if ($('#pm_handled')) $('#pm_handled').onclick = async () => { const r = await api('postfach/handled', 'POST', { box, folder, uid: Number(uid) }); toast(r.note || (r.moved ? 'Erledigt und in den Ordner Erledigt verschoben' : 'Als erledigt markiert')); syncAppBadge(); location.hash = back; };
  if ($('#pm_assign')) $('#pm_assign').onclick = () => pfAssign(folder, uid, m, () => pfShow(main, folder, uid, w, opts));
  if ($('#pm_done')) $('#pm_done').onclick = async () => {
    const r = await api(`mailtasks/${opts.task.id}/${opts.task.status === 'offen' ? 'done' : 'reopen'}`, 'POST'); toast(r.note || (opts.task.status === 'offen' ? 'Erledigt, Mail liegt im Ordner Erledigt' : 'Wieder offen')); route();
  };
  $$('[data-untask]', main).forEach(b => b.onclick = async () => { if (!confirmBox('Zuweisung entfernen?')) return; await api('mailtasks/' + b.dataset.untask, 'DELETE'); pfShow(main, folder, uid, w, opts); });
  if ($('#pm_unread')) $('#pm_unread').onclick = async () => { await api('postfach/flag', 'POST', { box, folder, uid: Number(uid), flag: 'seen', value: false }); toast('Als ungelesen markiert'); location.hash = back; };
  if ($('#pm_del')) $('#pm_del').onclick = async () => {
    if (!confirmBox('Diese Mail löschen? Sie kommt in den Papierkorb, im Papierkorb selbst wird sie endgültig gelöscht.')) return;
    try { const r = await api('postfach/delete', 'POST', { box, folder, uid: Number(uid) }); toast(r.action === 'endgültig gelöscht' ? 'Endgültig gelöscht' : 'In den Papierkorb verschoben'); location.hash = back; }
    catch (e) { alert(e.message); }
  };
}

async function pfAssign(folder, uid, m, done) {   // uid: eine Mail oder eine Liste (Auswahl in der Liste)
  const uids = [].concat(uid).map(Number);
  let people; try { people = await api('postfach/people'); } catch (e) { return alert(e.message); }
  openModal(`<h2>Mail zuweisen</h2>
    <p class="muted small">${uids.length > 1 ? `<b>${uids.length} Mails</b>.` : `„${esc(m.subject)}“${m.from ? ` von ${esc(pfName(m.from))}` : ''}.`} Die Mail wird mit Anhängen in das Postfach der Person weitergeleitet (eigenes Postfach im Hub, sonst die Adresse im Konto, markiert mit ✉), dazu eine Push-Nachricht und ein Hinweis im Hub.
      Antworten von dort gehen direkt an den Absender. Wer Zugriff auf das Vereinspostfach hat, kann die Mail auch dort lesen und beantworten.</p>
    <div class="form">
      <div class="field full"><label for="pa_user">Wer soll sie bearbeiten?</label><select class="input" id="pa_user"><option value="">Person wählen</option>
        ${people.map(p => `<option value="${p.id}" ${p.forward === '-' ? 'disabled' : ''}>${esc(p.name)}${p.role ? ' (' + esc(p.role) + ')' : ''}${p.forward ? (p.forward === '-' ? ' (keine E-Mail-Adresse)' : ' ✉ Weiterleitung an ' + esc(p.forward)) : ''}</option>`).join('')}</select></div>
      <div class="field full"><label for="pa_note">Hinweis (optional)</label><textarea class="input" id="pa_note" rows="3" maxlength="1000" placeholder="z. B. Bitte bis Freitag antworten"></textarea></div>
    </div>
    <div class="modal-foot"><div></div><div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="pa_save">Zuweisen</button></div></div>`);
  $('#pa_save').onclick = async () => {
    if (!$('#pa_user').value) return alert('Bitte eine Person wählen.');
    const pick = $('#pa_user').value, note = $('#pa_note').value;   // vor closeModal merken
    if (uids.length > 1) {   // mehrere: nacheinander zuweisen, Fehler am Ende melden
      let ok = 0, err = ''; closeModal(); toast(`${uids.length} Mails werden zugewiesen ...`);
      for (const u of uids) { try { await api('postfach/assign', 'POST', { folder, uid: u, user_id: Number(pick), note }); ok++; } catch (e) { err = e.message; } }
      toast(err ? `${ok} von ${uids.length} zugewiesen, Fehler: ${err}` : `${ok} Mails zugewiesen`); return done();
    }
    try { const r = await api('postfach/assign', 'POST', { folder, uid: uids[0], user_id: Number($('#pa_user').value), note: $('#pa_note').value }); closeModal(); toast(r.forwarded ? 'Zugewiesen und an ' + r.forwarded + ' weitergeleitet' : 'Zugewiesen'); done(); }
    catch (e) { alert(e.message); }
  };
}

function pfCompose(d) {
  const q = d.quote || null;
  openModal(`<h2>${d.draft ? 'Entwurf' : d.reply ? 'Antworten' : 'Neue Mail'}</h2>
    <div class="form">
      <div class="field full"><label for="pc_to">An</label><input class="input" id="pc_to" value="${esc(d.to || '')}" placeholder="name@beispiel.de, mehrere mit Komma"></div>
      ${d.reply ? '' : `<div class="field full" id="pc_list_f" hidden><label for="pc_list">Verteiler einfügen</label><select class="input" id="pc_list"><option value="">Verteiler wählen</option></select></div>
      <div class="field full"><label class="check"><input type="checkbox" id="pc_sep"> An jeden einzeln senden</label>
        <small class="muted">Jeder bekommt eine eigene Mail und sieht nur sich selbst als Empfänger.</small></div>`}
      <div class="field full" id="pc_cc_f"><label for="pc_cc">Cc (optional)</label><input class="input" id="pc_cc" value="${esc(d.cc || '')}"></div>
      <div class="field full"><label for="pc_subj">Betreff</label><input class="input" id="pc_subj" value="${esc(d.subject || '')}" maxlength="250"></div>
      <div class="field full"><label for="pc_body">Text</label><textarea class="input" id="pc_body" rows="10">${esc(d.body || '')}</textarea>
        ${d.note ? `<small class="muted">${esc(d.note)}</small>` : ''}</div>
      ${d.signature_html ? `<div class="field full"><label class="check"><input type="checkbox" id="pc_sig" checked> Signatur anhängen</label>
        <iframe id="pc_sig_prev" class="pf-sig" title="Vorschau der Signatur" sandbox srcdoc="${esc('<base target=_blank><body style=margin:8px;background:#fff>' + d.signature_html)}"></iframe></div>` : ''}
      ${q ? `<div class="field full"><details><summary class="small">${q.forward ? 'Weitergeleitete Nachricht' : 'Ursprüngliche Nachricht'} (wird angehängt)</summary>
        <pre class="pf-text" style="max-height:220px;overflow:auto">${esc(q.head + '\n' + q.text)}</pre></details></div>` : ''}
    </div>
    ${(d.senders || []).length > 1 ? `<div class="form"><div class="field full"><label for="pc_from">Absender</label><select class="input" id="pc_from">
      ${d.senders.map(x => `<option value="${x.key}" ${x.key === d.sender ? 'selected' : ''}>${esc(x.address)}${x.key === 'info' ? ' (Vereinspostfach)' : ' (eigenes Postfach)'}</option>`).join('')}</select></div></div>` : ''}
    <p class="muted small">${(d.senders || []).length > 1 ? '' : `Absender: <b>${esc(d.send_as || App._pfAddr || 'Vereinspostfach')}</b>. `}Die Mail landet zusätzlich im Ordner „Gesendet“ des Postfachs, über das sie verschickt wird.</p>
    <div id="pc_ask"></div>
    <div class="modal-foot"><div><button class="btn ghost" id="pc_draft">Als Entwurf speichern</button></div><div class="btn-row"><button class="btn" onclick="closeModal()">Abbrechen</button><button class="btn primary" id="pc_send">Senden</button></div></div>`);
  const body = $('#pc_body'); body.focus();
  if ($('#pc_sig')) $('#pc_sig').onchange = e => { $('#pc_sig_prev').style.display = e.target.checked ? '' : 'none'; };
  if ($('#pc_sep')) $('#pc_sep').onchange = e => { $('#pc_cc_f').style.display = e.target.checked ? 'none' : ''; };   // einzeln senden geht ohne Cc
  if ($('#pc_list') && can('postfach')) load('mail_lists', true).then(lists => {   // Verteiler: Adressen anhängen und einzeln senden
    if (!lists.length || !$('#pc_list')) return;
    $('#pc_list').innerHTML += lists.slice().sort((a, b) => (a.name || '').localeCompare(b.name || '')).map(l => `<option value="${l.id}">${esc(l.name)} (${pfListAddrs(l).length})</option>`).join('');
    $('#pc_list_f').hidden = false;
    $('#pc_list').onchange = () => {
      const l = byId(lists, $('#pc_list').value); if (!l) return;
      const cur = $('#pc_to').value.split(/[,;]/).map(x => x.trim()).filter(Boolean);
      $('#pc_to').value = [...new Set([...cur, ...pfListAddrs(l)])].join(', ');
      $('#pc_sep').checked = true; $('#pc_cc_f').style.display = 'none'; $('#pc_list').value = '';
      toast(`${l.name} eingefügt, jeder bekommt eine eigene Mail`);
    };
  }).catch(() => {});
  // Entwurf: speichern im Ordner „Entwürfe“; beim Schließen mit Änderungen nachfragen
  const vals = () => ({ to: $('#pc_to').value, cc: $('#pc_cc').value, subject: $('#pc_subj').value, body: body.value });
  const start = JSON.stringify(vals());
  const saveDraft = async () => {
    try { await api('postfach/draft', 'POST', { box: d.box || 'info', ...vals(), replace: d.draft || null }); toast('Entwurf gespeichert'); return true; }
    catch (e) { alert(e.message); return false; }
  };
  $('#pc_draft').onclick = async () => { if (await saveDraft()) { closeModal(true); if (d.draft) route(); } };
  App.beforeModalClose = () => {
    if (JSON.stringify(vals()) === start) return true;   // nichts geändert: einfach schließen
    $('#pc_ask').innerHTML = `<div class="card pf-ask"><b>Diese Mail als Entwurf speichern?</b>
      <div class="btn-row" style="margin-top:8px"><button class="btn primary" id="pa_keep">Als Entwurf speichern</button><button class="btn danger" id="pa_drop">Verwerfen</button><button class="btn ghost" id="pa_back">Weiter schreiben</button></div></div>`;
    $('#pa_keep').onclick = async () => { if (await saveDraft()) { closeModal(true); if (d.draft) route(); } };
    $('#pa_drop').onclick = () => closeModal(true);
    $('#pa_back').onclick = () => { $('#pc_ask').innerHTML = ''; body.focus(); };
    $('#pc_ask').scrollIntoView({ block: 'nearest' });
    return false;
  };
  $('#pc_send').onclick = async () => {
    const btn = $('#pc_send'); btn.disabled = true; btn.textContent = 'Wird gesendet ...';
    try {
      const sep = !!$('#pc_sep')?.checked;
      const r = await api('postfach/send', 'POST', { to: $('#pc_to').value, cc: sep ? '' : $('#pc_cc').value, separate: sep, subject: $('#pc_subj').value, body: body.value,
        quote: q, signature: $('#pc_sig') ? $('#pc_sig').checked : false, reply: d.reply || null, source: d.source || null,
        box: d.box || 'info', from: $('#pc_from') ? $('#pc_from').value : (d.sender || ''), draft: d.draft || null });
      if (r.background) { closeModal(true); alert(r.note); return; }
      closeModal(true); toast(r.task_done ? 'Mail gesendet, Aufgabe erledigt' : 'Mail gesendet'); if (r.note) alert(r.note);
      syncAppBadge();
      if (d.reply || d.source || d.draft) route();
    } catch (e) { alert(e.message); btn.disabled = false; btn.textContent = 'Senden'; }
  };
}

/* Mail-Aufgabe: die zugewiesene Mail lesen und beantworten (auch ohne Recht auf das ganze Postfach) */
App.pages.mailaufgabe = async (view, args = []) => {
  let t; try { t = await api('mailtasks/' + Number(args[0])); } catch (e) { view.innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
  view.innerHTML = `<div class="page-head"><h1>Mail-Aufgabe<small>Zugewiesen von ${esc(t.by_name)} an ${esc(t.user_name)} am ${fmtStamp(t.created)}</small></h1></div><div id="ma_main"><div class="card empty">Lädt ...</div></div>`;
  if (t.user_id === App.me.id && !Number(t.banner_seen)) api(`mailtasks/${t.id}/seen`, 'POST').catch(() => {});
  pfShow($('#ma_main'), t.folder, String(t.uid), false, { back: '#/', task: t });
};

/* Startseite: eigene Mail-Aufgaben */
async function dashMailTasks(box) {
  if (!box) return;
  let r; try { r = await api('mailtasks'); } catch { return; }
  const open = r.mine.filter(t => t.status === 'offen');
  syncAppBadge(r);
  if (!open.length && !r.others.length && !(r.inbox || []).length) { box.innerHTML = ''; return; }
  box.innerHTML = `${(r.inbox || []).length ? `<div class="card" style="margin-bottom:16px"><h2>Neue Mails im Postfach <span class="badge red">${r.inbox.length}</span></h2>
      <p class="muted small">Noch nicht erledigt. Erledigt ist eine Mail, sobald jemand antwortet, weiterleitet, zuweist, löscht oder „Erledigt“ klickt. „Erledigt“ verschiebt sie in den Ordner Erledigt.</p>
      <div class="list">${r.inbox.map(x => `<div class="list-item"><div class="grow"><a href="#/postfach/m/${encodeURIComponent(x.folder)}/${x.uid}"><b>${esc(x.subject)}</b></a>
        <div class="muted small">von ${esc(pfName(x.sender))} | ${fmtStamp(x.received)}</div></div>
        <a class="btn sm primary" href="#/postfach/m/${encodeURIComponent(x.folder)}/${x.uid}">Öffnen</a><button class="btn sm" data-ihandled="${x.folder}|${x.uid}">Erledigt</button></div>`).join('')}</div></div>` : ''}
    ${open.length || r.others.length ? `<div class="card" style="margin-bottom:16px"><h2>Mail-Aufgaben ${open.length ? `<span class="badge red">${open.length}</span>` : ''}</h2>
    ${open.length ? `<div class="list">${open.map(t => `<div class="list-item"><div class="grow"><a href="#/mailaufgabe/${t.id}"><b>${esc(t.subject)}</b></a>
        <div class="muted small">von ${esc(pfName(t.sender))} | zugewiesen von ${esc(t.by_name)}, ${fmtStamp(t.created)}${t.note ? ' | ' + esc(t.note) : ''}</div></div>
        <a class="btn sm primary" href="#/mailaufgabe/${t.id}">Öffnen</a><button class="btn sm" data-tdone="${t.id}">Erledigt</button></div>`).join('')}</div>` : '<p class="muted small">Für dich ist nichts offen.</p>'}
    ${r.others.length ? `<details style="margin-top:10px"><summary class="small">Offen bei anderen (${r.others.length})</summary><div class="list">${r.others.map(t => `<div class="list-item"><div class="grow">
        <a href="#/mailaufgabe/${t.id}">${esc(t.subject)}</a><div class="muted small">${esc(t.user_name)} | seit ${fmtStamp(t.created)}</div></div></div>`).join('')}</div></details>` : ''}</div>` : ''}`;
  $$('[data-ihandled]', box).forEach(b => b.onclick = async () => { const [f, u] = b.dataset.ihandled.split('|'); await api('postfach/handled', 'POST', { folder: f, uid: Number(u) }); toast('Erledigt'); dashMailTasks(box); });
  $$('[data-tdone]', box).forEach(b => b.onclick = async () => { await api(`mailtasks/${b.dataset.tdone}/done`, 'POST'); toast('Erledigt'); dashMailTasks(box); });
}

/* Profil: Push auf diesem Gerät */
async function pushCard(box) {
  if (!box) return;
  const sub = pushSupported() ? await pushCurrent() : null;
  let info = { devices: 0 }; try { info = await api('push/key'); } catch { /* ohne Schlüssel */ }
  box.innerHTML = `<h2>Push-Nachrichten auf dem Handy</h2>
    <p class="muted small">Zum Beispiel, wenn dir eine Mail zum Bearbeiten zugewiesen wird. Der Inhalt geht verschlüsselt über den Push-Dienst deines Geräts (Google, Apple oder Mozilla).
      Auf dem iPhone geht das nur, wenn der Hub als App auf dem Home-Bildschirm liegt.</p>
    <p>${sub ? '<span class="badge ok">Auf diesem Gerät aktiv</span>' : '<span class="badge">Auf diesem Gerät aus</span>'} <span class="muted small">Aktiv auf ${info.devices} Gerät${info.devices === 1 ? '' : 'en'}</span></p>
    ${!pushSupported() ? `<div class="warnline">${pushIOSNeedsApp() ? 'Bitte den Hub zuerst über „Teilen“ und „Zum Home-Bildschirm“ als App hinzufügen und von dort öffnen.' : 'Dieser Browser unterstützt keine Push-Nachrichten.'}</div>`
      : `<div class="btn-row">${sub ? '<button class="btn" id="pu_test">Test-Nachricht senden</button><button class="btn ghost" id="pu_off">Auf diesem Gerät ausschalten</button>' : '<button class="btn primary" id="pu_on">Push aktivieren</button>'}</div>`}`;
  if ($('#pu_on', box)) $('#pu_on', box).onclick = async () => { try { await pushEnable(); toast('Push aktiviert'); pushCard(box); } catch (e) { alert(e.message); } };
  if ($('#pu_off', box)) $('#pu_off', box).onclick = async () => { await pushDisable(); toast('Push ausgeschaltet'); pushCard(box); };
  if ($('#pu_test', box)) $('#pu_test', box).onclick = async () => { const r = await api('push/test', 'POST'); toast(r.ok ? 'Test-Nachricht verschickt' : 'Zustellung fehlgeschlagen, bitte Push neu aktivieren'); };
}

/* Speicher des Postfachs (IMAP QUOTA): Balken und Warnung, wenn fast voll (Grenze in server.py: MAIL_QUOTA_WARN_FREE) */
function pfQuota(q) {
  if (!q || !q.limit) return '';
  const gb = n => (n / 2 ** 30).toFixed(n >= 10 * 2 ** 30 ? 0 : 1).replace('.', ',') + ' GB';
  const pct = Math.min(100, Math.round(q.used / q.limit * 100));
  return `<div class="pf-quota${q.warn ? ' warn' : ''}" title="Speicher dieses Postfachs">
    <div class="pf-qbar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}" aria-label="Speicher belegt"><span style="width:${pct}%"></span></div>
    <small>${gb(q.used)} von ${gb(q.limit)} belegt</small>
    ${q.warn ? '<small class="pf-qwarn">Fast voll! Bitte alte Mails oder große Anhänge löschen und den Papierkorb leeren.</small>' : ''}</div>`;
}

/* Verteiler (Tabelle mail_lists, Bereich Postfach): gespeicherte Empfängerlisten verwalten */
const pfListAddrs = l => [...new Set(String(l.addresses || '').split(/[\s,;]+/).map(x => x.trim()).filter(x => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(x)))];
const PF_LIST_FIELDS = [
  { key: 'name', label: 'Name', full: true },
  { key: 'addresses', label: 'E-Mail-Adressen', type: 'textarea', full: true, hint: 'Eine Adresse pro Zeile (Komma oder Semikolon gehen auch). Höchstens 200, jeder bekommt eine eigene Mail.' },
  { key: 'notes', label: 'Notiz', type: 'textarea', full: true },
];
async function pfLists() {
  const lists = (await load('mail_lists', true)).slice().sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  const edit = async rec => { const r = await editRecord('mail_lists', PF_LIST_FIELDS, rec, { newTitle: 'Neuer Verteiler', editTitle: 'Verteiler bearbeiten' }); if (r !== undefined) pfLists(); };
  openModal(`<h2>Verteiler</h2>
    <p class="muted small">Gespeicherte Empfängerlisten. Beim Schreiben unter „Verteiler einfügen“ auswählen: jede Adresse bekommt eine eigene Mail und sieht nur sich selbst.</p>
    <div class="list">${lists.map(l => `<div class="list-item"><div class="grow"><b>${esc(l.name || 'Ohne Namen')}</b><div class="muted small">${pfListAddrs(l).length} Adressen${l.notes ? ' · ' + esc(l.notes) : ''}</div></div>
      ${can('postfach', 2) ? `<button class="btn sm" data-le="${l.id}">Bearbeiten</button>` : ''}</div>`).join('') || '<div class="muted">Noch keine Verteiler.</div>'}</div>
    <div class="modal-foot"><div>${can('postfach', 2) ? '<button class="btn primary" id="pl_new">+ Neuer Verteiler</button>' : ''}</div><div class="btn-row"><button class="btn" onclick="closeModal()">Schließen</button></div></div>`);
  if ($('#pl_new')) $('#pl_new').onclick = () => edit({});
  $$('[data-le]').forEach(b => b.onclick = () => edit(byId(lists, b.dataset.le)));
}
