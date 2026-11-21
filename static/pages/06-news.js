/* ====================================================================== */
/* News (Artikel auf der Webseite unter /news, die 3 neuesten auf der Startseite) */
const ARTICLE_STATUS = ['Entwurf', 'Veröffentlicht'];
F.articles = () => [
  { key: 'title', label: 'Überschrift', full: true, placeholder: 'z. B. Erste Herren gewinnen das Heimspiel gegen Borssum' },
  { key: 'date', label: 'Datum', type: 'date', default: todayStr(), hint: 'Erst ab diesem Tag auf der Webseite sichtbar.' },
  { key: 'status', label: 'Status', type: 'select', options: ARTICLE_STATUS, default: 'Entwurf', hint: 'Nur „Veröffentlicht“ erscheint auf der Webseite.' },
  { key: 'team', label: 'Mannschaft (optional)', type: 'select', options: ['', ...TEAMS] },
  { key: 'game_id', label: 'Spiel (optional)', type: 'ref', ref: { table: 'games', label: gameLabel }, hint: 'Zeigt Paarung und Ergebnis im Artikel, z. B. für Spielberichte.' },
  { key: 'teaser', label: 'Vorspann', type: 'textarea', rows: 2, placeholder: 'Ein bis zwei Sätze für die Übersicht und die Startseite' },
  { key: 'format', label: 'Textformat', type: 'select', options: ['Blöcke', 'Text', 'HTML'], default: 'Blöcke',
    hint: 'Blöcke: Artikel aus Bausteinen zusammensetzen (Editor unten). Text: Leerzeile = neuer Absatz. HTML: erlaubt sind <p> <h2> <h3> <h4> <strong> <em> <u> <ul> <ol> <li> <a href> <blockquote> <br> <hr>, alles andere wird entfernt.' },
  { key: 'body', label: 'Text', type: 'textarea', rows: 14, hint: 'Bitte keine Namen von Kindern und Jugendlichen.', show: v => v.format !== 'Blöcke' },
  { key: 'image', label: 'Foto', type: 'image', full: true, hint: 'Am besten im Instagram-Hochformat 4:5 (1080 x 1350), so wird es ohne Beschnitt gezeigt. Ohne Foto zeigt die Webseite das Tiger-Logo.' },
  { key: 'image_alt', label: 'Bildbeschreibung', full: true, placeholder: 'z. B. Runningback mit dem Ball im Heimspiel', hint: 'Für Screenreader und Google.' },
  { key: 'photo_by', label: 'Fotograf', placeholder: 'z. B. silasgrbwsk.fotografie', hint: 'Steht unter dem Artikel als „Foto: …“. Leer = kein Hinweis.' },
  { key: 'photo_url', label: 'Link zum Fotografen', placeholder: 'https://... oder @instagramname', hint: 'Der Name unter dem Artikel wird hierhin verlinkt.' },
  { key: 'notes', label: 'Interne Notizen (nicht öffentlich)', type: 'textarea', rows: 2 },
];
const DEFAULT_PHOTO = { photo_by: 'silasgrbwsk.fotografie', photo_url: 'https://silasgrbwskfotografie.de' };   // Teamfotograf, im Artikel änderbar
const articleSlug = a => `${a.id}-` + ((a.title || '').toLowerCase().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
  .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60).replace(/-+$/, '') || 'artikel');

App.pages.news = async (view) => {
  const list = [...await load('articles', true)].sort((a, b) => (b.date || '').localeCompare(a.date || '') || b.id - a.id);
  await loadAll('games', 'opponents');
  const today = todayStr();
  const state = a => a.status !== 'Veröffentlicht' ? ['Entwurf', ''] : (a.date || '') > today ? ['Geplant ab ' + fmtDate(a.date), 'warn'] : ['Online', 'ok'];
  const online = list.filter(a => state(a)[0] === 'Online');
  view.innerHTML = `
    <div class="page-head"><h1>News<small>${online.length} online, die 3 neuesten auf der Startseite</small></h1>
      <div class="btn-row"><a class="btn keep" href="/news" target="_blank" rel="noopener">Auf der Webseite ansehen</a><button class="pp btn primary" id="nw_new">+ Artikel</button></div></div>
    <div class="table-wrap"><table><thead><tr><th>Datum</th><th></th><th>Überschrift</th><th>Status</th><th>Mannschaft</th><th></th></tr></thead><tbody>
    ${list.map(a => { const [st, cls] = state(a); return `<tr>
      <td style="white-space:nowrap"><b>${fmtDate(a.date) || '<span class="muted">ohne Datum</span>'}</b></td>
      <td>${a.image ? `<img class="thumb" src="${esc(a.image)}" alt="">` : '<div class="thumb"></div>'}</td>
      <td><b>${esc(a.title || '(ohne Überschrift)')}</b>${a.teaser ? `<div class="muted small">${esc(a.teaser.slice(0, 120))}</div>` : ''}${online.slice(0, 3).includes(a) ? '<div><span class="badge red">Startseite</span></div>' : ''}</td>
      <td><span class="badge ${cls}">${esc(st)}</span></td>
      <td>${esc(a.team || '')}</td>
      <td class="actions">${st === 'Online' ? `<a class="btn sm keep" href="/news/${esc(articleSlug(a))}" target="_blank" rel="noopener">Ansehen</a> ` : ''}<button class="btn sm ghost keep" data-e="${a.id}">${App.readOnly ? 'Ansehen' : 'Bearbeiten'}</button></td>
    </tr>`; }).join('') || '<tr><td colspan="6" class="empty">Noch keine Artikel. Lege oben den ersten an.</td></tr>'}
    </tbody></table></div>`;
  const edit = async rec => { if (await editArticle(rec)) route(); };
  if ($('#nw_new')) $('#nw_new').onclick = () => edit({ status: 'Entwurf', date: todayStr(), format: 'Blöcke', ...DEFAULT_PHOTO });
  $$('[data-e]').forEach(b => b.onclick = () => edit(byId(list, b.dataset.e)));
};

/* Block-Editor für News: Bausteine wie im Vereinsdesign der Webseite. Gespeichert wird JSON in articles.body (format „Blöcke“),
   der Server prüft jeden Block (article_blocks) und die Webseite baut daraus den Artikel (render_blocks). */
const BLOCK_TYPES = {
  p: { label: 'Absatz', fields: [['text', 'Text', 'area', 5]] },
  h: { label: 'Zwischentitel', fields: [['text', 'Zwischentitel', 'line']] },
  quote: { label: 'Zitat', fields: [['text', 'Zitat', 'area', 3], ['by', 'Von wem (z. B. Maximilian Trant, Head Coach)', 'line']] },
  list: { label: 'Liste', fields: [['items', 'Punkte (einer pro Zeile)', 'area', 4]] },
  highlight: { label: 'Hervorhebung', fields: [['text', 'Großer Satz, z. B. zum Abschluss', 'line']] },
  cta: { label: 'Roter Kasten mit Knopf (zusätzlich)', fields: [['text', 'Text im Kasten', 'area', 2], ['label', 'Knopf-Beschriftung', 'line'], ['link', 'Knopf-Link (z. B. /kontakt?anliegen=herren#formular)', 'line']] },
  image: { label: 'Bild', fields: [['src', '', 'image'], ['alt', 'Bildbeschreibung', 'line'], ['caption', 'Bildunterschrift (optional)', 'line']] },
  note: { label: 'Kleingedrucktes', fields: [['text', 'z. B. Foto: silasgrbwsk.fotografie', 'line']] },
};
const parseBlocks = s => { try { const v = JSON.parse(s || '[]'); return Array.isArray(v) ? v.filter(b => b && BLOCK_TYPES[b.t]) : []; } catch { return []; } };
const blocksToText = bl => bl.map(b => b.t === 'list' ? (b.items || []).map(x => '- ' + x).join('\n') : b.t === 'quote' ? `„${b.text || ''}“ ${b.by || ''}`.trim() : b.t === 'cta' ? b.text : b.t === 'image' ? '' : b.text || '')
  .filter(Boolean).join('\n\n');
const textToBlocks = t => String(t || '').split(/\n\s*\n/).map(x => x.trim()).filter(Boolean).map(x => ({ t: 'p', text: x }));

/* Fertigen HTML-Artikel (z. B. aus einer Vorlage) in Blöcke zerlegen. DOMParser führt nichts aus, die Webseite filtert zusätzlich. */
function htmlToArticle(html) {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const txt = el => (el?.textContent || '').replace(/\s+/g, ' ').trim();
  const res = { title: txt(doc.querySelector('h1')), teaser: '', image_alt: doc.querySelector('img')?.getAttribute('alt') || '', blocks: [] };
  const lead = doc.querySelector('.blog-lead, .lead');
  res.teaser = txt(lead) || doc.querySelector('meta[name="description"]')?.getAttribute('content') || '';
  const walk = root => [...root.children].forEach(el => {
    const tag = el.tagName.toLowerCase(), cls = el.className || '';
    if (el === lead || ['h1', 'img', 'script', 'style', 'header', 'nav', 'footer', 'time'].includes(tag) || /blog-meta/.test(cls)) return;
    if (/^h[2-4]$/.test(tag)) return res.blocks.push({ t: 'h', text: txt(el) });
    if (tag === 'blockquote') { const by = el.querySelector('footer, cite'); const c = el.cloneNode(true); c.querySelector('footer, cite')?.remove(); return res.blocks.push({ t: 'quote', text: txt(c), by: txt(by) }); }
    if (tag === 'ul' || tag === 'ol') return res.blocks.push({ t: 'list', items: [...el.querySelectorAll('li')].map(txt).filter(Boolean) });
    // Probetraining-Kasten und Fotohinweis setzt die Webseite unter jeden Artikel selbst, daher nicht als Block übernehmen
    if ((tag === 'aside' || /cta/.test(cls)) && /probetraining/i.test(el.textContent)) return;
    if (tag === 'aside' || /cta/.test(cls)) { const a = el.querySelector('a'); const c = el.cloneNode(true); c.querySelectorAll('a').forEach(x => x.remove());
      return res.blocks.push({ t: 'cta', text: txt(c), label: txt(a), link: a?.getAttribute('href') || '' }); }
    if (tag === 'p') {
      if (/abschluss|highlight/.test(cls)) return res.blocks.push({ t: 'highlight', text: txt(el) });
      if (/credit/.test(cls) || /^(Foto|Fotos)\s*:/i.test(txt(el))) { res.photo_by = txt(el).replace(/^(Foto|Fotos)\s*:\s*/i, ''); return; }
      if (/note|small/.test(cls)) return res.blocks.push({ t: 'note', text: txt(el) });
      const inner = el.innerHTML.replace(/\s+/g, ' ').trim();
      return inner && res.blocks.push({ t: 'p', text: inner });
    }
    walk(el);   // Container wie article, section, div
  });
  walk(doc.querySelector('article') || doc.body);
  return res;
}

async function editArticle(rec) {
  let blocks = rec.format === 'Blöcke' ? parseBlocks(rec.body) : [];
  const ro = !!App.readOnly;
  return editRecord('articles', F.articles(), rec, {
    newTitle: 'Neuer Artikel', editTitle: 'Artikel bearbeiten',
    onOpen: box => {
      const fmt = $('#f_format', box), body = $('#f_body', box);
      if (fmt.value === 'Blöcke') body.value = '';
      const wrap = document.createElement('div');
      wrap.className = 'field full blk-editor';
      wrap.innerHTML = `<label>Inhalt</label><div id="blk_list"></div>
        ${ro ? '' : `<div class="blk-add"><span class="muted small">Block hinzufügen:</span>${Object.entries(BLOCK_TYPES).map(([k, v]) => `<button type="button" class="btn sm" data-add="${k}">${esc(v.label)}</button>`).join('')}</div>
        <div class="blk-import"><button type="button" class="btn sm ghost" id="blk_imp">HTML-Datei einlesen</button><input type="file" id="blk_file" accept=".html,.htm,text/html" hidden>
          <span class="hint">Liest einen fertigen Artikel (z. B. eine Vorlage als .html) ein und zerlegt ihn in Blöcke. Überschrift und Vorspann werden mit übernommen, das Titelbild bitte oben unter „Foto“ wählen.</span></div>`}`;
      $('[data-fkey="body"]', box).after(wrap);
      const list = $('#blk_list', wrap);
      const draw = () => {
        list.innerHTML = blocks.map((b, i) => {
          const def = BLOCK_TYPES[b.t];
          const inputs = def.fields.map(([k, label, kind, rows]) => {
            const v = k === 'items' ? (b.items || []).join('\n') : (b[k] || '');
            if (kind === 'image') return `<div class="blk-img">${v ? `<img src="${esc(v)}" alt="">` : '<div class="thumb"></div>'}${ro ? '' : `<button type="button" class="btn sm" data-pick="${i}">${v ? 'Anderes Bild' : 'Bild wählen'}</button>`}</div>`;
            const attr = `data-i="${i}" data-k="${k}" placeholder="${esc(label)}" ${ro ? 'disabled' : ''}`;
            return kind === 'area' ? `<textarea rows="${rows}" ${attr}>${esc(v)}</textarea>` : `<input class="input" value="${esc(v)}" ${attr}>`;
          }).join('');
          const tools = b.t === 'p' && !ro ? `<button type="button" class="btn sm ghost" data-wrap="${i}" data-tag="strong" title="Markierten Text fett"><b>F</b></button><button type="button" class="btn sm ghost" data-link="${i}" title="Markierten Text verlinken">Link</button>` : '';
          return `<div class="blk blk-${b.t}"><div class="blk-head"><b>${esc(def.label)}</b><span>${tools}${ro ? '' : `<button type="button" class="btn sm ghost" data-up="${i}" ${i ? '' : 'disabled'} title="Nach oben">↑</button><button type="button" class="btn sm ghost" data-down="${i}" ${i < blocks.length - 1 ? '' : 'disabled'} title="Nach unten">↓</button><button type="button" class="btn sm ghost" data-del="${i}" title="Block löschen">✕</button>`}</span></div>${inputs}</div>`;
        }).join('') || '<div class="empty small">Noch keine Blöcke. Füge unten den ersten hinzu, zum Beispiel einen Absatz.</div>';
        $$('[data-k]', list).forEach(el => el.oninput = () => { const b = blocks[el.dataset.i]; b[el.dataset.k] = el.dataset.k === 'items' ? el.value.split('\n') : el.value; });
        $$('[data-up]', list).forEach(x => x.onclick = () => { const i = +x.dataset.up; [blocks[i - 1], blocks[i]] = [blocks[i], blocks[i - 1]]; draw(); });
        $$('[data-down]', list).forEach(x => x.onclick = () => { const i = +x.dataset.down; [blocks[i + 1], blocks[i]] = [blocks[i], blocks[i + 1]]; draw(); });
        $$('[data-del]', list).forEach(x => x.onclick = () => { if (confirmBox('Diesen Block löschen?')) { blocks.splice(+x.dataset.del, 1); draw(); } });
        $$('[data-pick]', list).forEach(x => x.onclick = async () => { const p = await pickImage(); if (p) { blocks[+x.dataset.pick].src = p; draw(); } });
        const sel = i => { const ta = $(`textarea[data-i="${i}"]`, list); return [ta, ta.selectionStart, ta.selectionEnd]; };
        $$('[data-wrap]', list).forEach(x => x.onclick = () => { const [ta, a, z] = sel(x.dataset.wrap); if (a === z) return toast('Erst Text markieren');
          ta.value = ta.value.slice(0, a) + `<strong>${ta.value.slice(a, z)}</strong>` + ta.value.slice(z); ta.dispatchEvent(new Event('input')); });
        $$('[data-link]', list).forEach(x => x.onclick = () => { const [ta, a, z] = sel(x.dataset.link); if (a === z) return toast('Erst Text markieren');
          const url = prompt('Link (https://... oder /kontakt)'); if (!url) return;
          ta.value = ta.value.slice(0, a) + `<a href="${url.replace(/"/g, '')}">${ta.value.slice(a, z)}</a>` + ta.value.slice(z); ta.dispatchEvent(new Event('input')); });
      };
      $$('[data-add]', wrap).forEach(x => x.onclick = () => { blocks.push({ t: x.dataset.add }); draw(); list.lastElementChild?.querySelector('textarea, input')?.focus(); });
      if ($('#blk_imp', wrap)) {
        $('#blk_imp', wrap).onclick = () => $('#blk_file', wrap).click();
        $('#blk_file', wrap).onchange = async e => {
          const f = e.target.files[0]; if (!f) return;
          const r = htmlToArticle(await f.text());
          if (blocks.length && !confirmBox(`${r.blocks.length} Blöcke aus „${f.name}“ übernehmen? Die bisherigen Blöcke werden ersetzt.`)) return;
          blocks = r.blocks;
          if (r.title && !$('#f_title', box).value) $('#f_title', box).value = r.title;
          if (r.teaser && !$('#f_teaser', box).value) $('#f_teaser', box).value = r.teaser;
          if (r.image_alt && !$('#f_image_alt', box).value) $('#f_image_alt', box).value = r.image_alt;
          if (r.photo_by && $('#f_photo_by', box).value !== r.photo_by) { $('#f_photo_by', box).value = r.photo_by; if (r.photo_by !== DEFAULT_PHOTO.photo_by) $('#f_photo_url', box).value = ''; }
          draw(); toast(`${r.blocks.length} Blöcke übernommen`);
        };
      }
      const sync = () => { wrap.style.display = fmt.value === 'Blöcke' ? '' : 'none'; };
      let last = fmt.value;
      fmt.addEventListener('change', () => {   // beim Wechsel den Inhalt mitnehmen
        if (last === 'Blöcke' && fmt.value !== 'Blöcke' && !body.value.trim()) body.value = blocksToText(blocks);
        if (last !== 'Blöcke' && fmt.value === 'Blöcke' && !blocks.length && body.value.trim())
          blocks = last === 'HTML' ? htmlToArticle(body.value).blocks : textToBlocks(body.value);
        last = fmt.value; draw(); sync();
      });
      draw(); sync();
    },
    beforeSave: vals => {
      if (vals.format !== 'Blöcke') return;
      vals.body = JSON.stringify(blocks.map(b => b.t === 'list' ? { ...b, items: (b.items || []).map(x => x.trim()).filter(Boolean) } : b));
    },
  });
}


