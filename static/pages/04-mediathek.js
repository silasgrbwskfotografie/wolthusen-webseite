/* ====================================================================== */
/* Mediathek */
App.pages.media = async (view) => {
  const media = await load('media', true);
  view.innerHTML = `
    <div class="page-head"><h1>Mediathek<small>${media.length} Dateien</small></h1></div>
    <div class="dropzone" id="m_drop">Fotos hierher ziehen oder <button class="btn sm" id="m_up">Dateien wählen</button>
      <input type="file" id="m_file" accept="image/*" multiple hidden>
      <div style="margin-top:10px"><input class="input" id="m_tags" placeholder="Tags für den Upload, z. B. Gameday Borssum 2027" style="max-width:420px"></div></div>
    <div class="toolbar"><input class="input" id="m_q" placeholder="Suchen" style="max-width:300px"></div>
    <div class="media-grid" id="m_grid"></div>`;
  const grid = () => {
    const q = $('#m_q').value.toLowerCase();
    const items = [...media].reverse().filter(m => !q || (m.name + ' ' + (m.tags || '')).toLowerCase().includes(q));
    $('#m_grid').innerHTML = items.map(m => `<figure data-id="${m.id}"><img loading="lazy" src="${esc(m.path)}"><figcaption>${esc(m.tags || m.name)}</figcaption><button class="btn sm del" data-del="${m.id}">✕</button></figure>`).join('') || '<div class="empty">Noch keine Bilder</div>';
    $$('[data-del]').forEach(b => b.onclick = async e => { e.stopPropagation(); if (!confirmBox('Aus der Mediathek entfernen?')) return; await api('media/' + b.dataset.del, 'DELETE'); invalidate('media'); App.pages.media(view); });
    $$('figure[data-id]').forEach(f => f.onclick = async () => {
      const m = byId(media, f.dataset.id);
      const r = await editRecord('media', [{ key: 'tags', label: 'Tags', full: true }, { key: 'name', label: 'Dateiname', full: true }], m, { editTitle: 'Bild' , onOpen: box => box.insertAdjacentHTML('afterbegin', `<img src="${esc(m.path)}" style="max-width:100%;max-height:340px;border-radius:8px;margin-bottom:12px;display:block">`) });
      if (r) App.pages.media(view);
    });
  };
  const up = async files => {
    const tags = $('#m_tags').value;
    toast(`Lade ${files.length} Datei(en) hoch ...`);
    for (const f of files) await uploadFile(f, tags);
    invalidate('media'); App.pages.media(view);
  };
  $('#m_q').oninput = grid;
  $('#m_up').onclick = () => $('#m_file').click();
  $('#m_file').onchange = e => up([...e.target.files]);
  const dz = $('#m_drop');
  dz.ondragover = e => { e.preventDefault(); dz.classList.add('over'); };
  dz.ondragleave = () => dz.classList.remove('over');
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove('over'); up([...e.dataTransfer.files].filter(f => f.type.startsWith('image/'))); };
  grid();
};

