/* ====================================================================== */
/* Webseite: Texte, Bilder, Aufbau der Startseite, Hinweis-Leiste, Vorschau (Bereich Medien) */
// Texte der öffentlichen Webseite nach Seiten (Schlüssel site_* in den Einstellungen, siehe DEFAULT_SETTINGS in server.py)
const SITE_TEXT_GROUPS = [
  ['Allgemein', '/', [
    { key: 'site_contact_email', label: 'Kontakt-E-Mail', hint: 'Steht im Footer und auf der Kontaktseite, Anfragen aus dem Formular gehen hierhin.' },
    { key: 'site_contact_confirm', label: 'Bestätigung an Anfragende (E-Mail)', type: 'textarea', rows: 4, full: true,
      hint: 'Geht automatisch an alle, die das Kontaktformular mit E-Mail-Adresse abschicken. Leer = keine Bestätigung. Die Nachricht selbst wird nicht mitgeschickt.' },
    { key: 'site_shop_url', label: 'Fanshop (Link)', placeholder: 'https://...', hint: 'Erscheint als „Fanshop“ im Menü und im Footer. Leer = kein Shop-Link.' },
  ]],
  ['Startseite', '/', [
    { key: 'site_hero_text', label: 'Satz unter der Überschrift', type: 'textarea', rows: 2, full: true },
    { key: 'site_about', label: 'Über uns', type: 'textarea', rows: 5, full: true, hint: 'Leerzeile = neuer Absatz.' },
    { key: 'site_card_short', label: 'Karte Dauerkarte: Kurztext', type: 'textarea', rows: 2, full: true },
    { key: 'site_insta_hide', label: 'Diese Instagram-Beiträge nicht zeigen', type: 'textarea', rows: 3, full: true, placeholder: 'https://www.instagram.com/p/...',
      hint: 'Ein Link pro Zeile (in Instagram: ··· > Link kopieren), z. B. für angepinnte Beiträge. Das Raster auf der Startseite zeigt dann die nächsten Beiträge.' },
  ]],
  ['Mannschaften', '/fussball', [
    { key: 'site_trial_text', label: 'Hinweise zum Probetraining (auf jeder Mannschaftsseite)', type: 'textarea', rows: 3, full: true },
    { key: 'site_training_address', label: 'Adresse Sportplatz (unter den Trainingszeiten)', hint: 'Die Trainingszeiten selbst pflegst du unter Verein > Trainingszeiten.' },
  ]],
  ['Spielplan', '/spielplan', [
    { key: 'site_home_address', label: 'Adresse Sportplatz', hint: 'Erscheint auf dem Spielplan, verlinkt auf die Karte.' },
    { key: 'site_home_maps_url', label: 'Karten-Link Sportplatz', placeholder: 'https://maps.app.goo.gl/...', hint: 'Link für Adresse und „Anfahrt auf der Karte“, z. B. aus Google Maps „Teilen“. Leer = Suche auf OpenStreetMap.' },
    { key: 'site_gameday_text', label: 'Am Spieltag: Infos für Zuschauer (Parken, Essen, Kinder)', type: 'textarea', rows: 3, full: true },
  ]],
  ['Partner und Dauerkarte', '/partner', [
    { key: 'site_sponsor_text', label: 'Partner werden (Ansprechpartner, Möglichkeiten)', type: 'textarea', rows: 4, full: true },
    { key: 'site_card_text', label: 'Dauerkarte: Leistungen und wo es sie gibt', type: 'textarea', rows: 3, full: true },
    { key: 'site_card_order_text', label: 'Dauerkarte online: So geht es weiter (Bezahlung, Abholung)', type: 'textarea', rows: 3, full: true, hint: 'Steht auf der Bestellseite und in der Bestätigungsmail.' },
    { key: 'site_card_terms', label: 'Dauerkarte online: Hinweise vor der Bestellung (Widerruf, Spielausfall)', type: 'textarea', rows: 5, full: true, hint: 'Steht direkt über dem Knopf „Zahlungspflichtig bestellen“ und in der Bestätigungsmail. Bitte rechtlich prüfen lassen.' },
    { key: 'site_card_cancel_text', label: 'Dauerkarte online: Freiwillige Stornierung', type: 'textarea', rows: 3, full: true, hint: 'Steht über dem Bestellknopf, im Ablauf und in der Bestätigungsmail. Nicht „Widerrufsrecht“ nennen.' },
    { key: 'site_card_process', label: 'Dauerkarte online: Ablauf der Bestellung', type: 'textarea', rows: 7, full: true, hint: 'Eine Zeile pro Schritt, beginnend mit „1.“, „2.“ usw.' },
    { key: 'site_card_delivery_text', label: 'Dauerkarte online: Lieferung', type: 'textarea', rows: 3, full: true, hint: 'Steht auf der Bestellseite und in der Bestätigungsmail. Leer = „Infos zur Lieferung folgen“.' },
  ]],
  ['News', '/news', [
    { key: 'site_news_cta_text', label: 'Kasten unter jedem Artikel', type: 'textarea', rows: 3, full: true, hint: 'Leer = kein Kasten. Der Knopf führt zum Probetraining, bei Artikeln der Jugend zum Probetraining Jugend.' },
    { key: 'site_news_cta_button', label: 'Beschriftung des Knopfs', placeholder: 'Zum Probetraining' },
  ]],
  ['Suchmaschinen (Google, Bing, Yahoo)', '/', [
    { key: 'site_seo_title', label: 'Zusatz im Titel der Startseite', placeholder: 'Sportverein in Emden-Wolthusen', hint: 'Erscheint als blaue Überschrift bei Google: „SV Amisia Wolthusen | …“. Kurz halten (bis ca. 40 Zeichen).' },
    { key: 'site_seo_start', label: 'Beschreibung Startseite', type: 'textarea', rows: 2, full: true, hint: 'Der graue Text unter dem Link in den Suchergebnissen. Ideal 120 bis 155 Zeichen, mit den Wörtern, nach denen Leute suchen (z. B. Fußball, Emden, Wolthusen, Probetraining).' },
    { key: 'site_seo_herren', label: 'Beschreibung Mannschaftsseiten (Herren)', type: 'textarea', rows: 2, full: true },
    { key: 'site_seo_spielplan', label: 'Beschreibung Spielplan', type: 'textarea', rows: 2, full: true },
    { key: 'site_seo_news', label: 'Beschreibung News', type: 'textarea', rows: 2, full: true, hint: 'Artikel nutzen ihren eigenen Vorspann.' },
    { key: 'site_seo_sponsoren', label: 'Beschreibung Partner', type: 'textarea', rows: 2, full: true },
    { key: 'site_seo_kontakt', label: 'Beschreibung Kontakt', type: 'textarea', rows: 2, full: true },
    { key: 'site_verify_google', label: 'Bestätigungscode Google Search Console', placeholder: 'Code oder ganzes <meta>-Tag einfügen', hint: 'Bei Google Search Console „URL-Präfix“ und „HTML-Tag“ wählen, den Code hier einfügen, speichern, dann bei Google „Bestätigen“. Danach dort die Sitemap /sitemap.xml einreichen.' },
    { key: 'site_verify_bing', label: 'Bestätigungscode Bing Webmaster Tools', placeholder: 'Code oder ganzes <meta>-Tag einfügen', hint: 'Bing liefert auch die Ergebnisse für Yahoo, Ecosia und DuckDuckGo. Alternativ dort einfach „Aus Google Search Console importieren“ wählen.' },
  ]],
  ['Rechtliches: Impressum', '/impressum', [
    { key: 'site_impressum', label: 'Impressum', type: 'textarea', rows: 22, full: true,
      hint: 'Format: „## “ am Zeilenanfang = Überschrift, Leerzeile = neuer Absatz, „- “ = Liste. [Eckige Klammern] erscheinen gelb und müssen noch ausgefüllt werden. {E-Mail} und {Instagram} setzt die Webseite automatisch ein. Bitte vor dem Veröffentlichen rechtlich prüfen lassen.' },
  ]],
  ['Rechtliches: Datenschutzerklärung', '/datenschutz', [
    { key: 'site_datenschutz', label: 'Datenschutzerklärung', type: 'textarea', rows: 30, full: true,
      hint: 'Beschreibt, was Webseite und Hub tatsächlich verarbeiten. Bei Änderungen an der Webseite (neue Formulare, neue Dienste) hier anpassen. Format wie beim Impressum.' },
  ]],
];
const SITE_NOTICE_FIELDS = [
  { key: 'site_notice_text', label: 'Text der Hinweis-Leiste', full: true, placeholder: 'z. B. Heimspiel am Sonntag um 15 Uhr: Kommt vorbei!', hint: 'Leer lassen = keine Leiste.' },
  { key: 'site_notice_link', label: 'Link „Mehr erfahren“ (optional)', placeholder: '/spielplan oder https://...' },
  { key: 'site_notice_until', label: 'Anzeigen bis einschließlich', type: 'date', hint: 'Danach verschwindet die Leiste von selbst. Leer = ohne Ende.' },
];
const WEB_TABS = [['uebersicht', 'Übersicht'], ['texte', 'Texte'], ['bilder', 'Bilder'], ['startseite', 'Aufbau Startseite'], ['hinweis', 'Hinweis-Leiste'], ['menu', 'Menü'], ['links', 'Link-Seite'], ['sitemap', 'Sitemap'], ['vorschau', 'Vorschau']];
const WEB_PAGES = [['/', 'Start'], ['/fussball', 'Fußball'], ['/mannschaft/erste-herren', 'Erste Herren'], ['/spielplan', 'Spielplan'], ['/news', 'News'], ['/partner', 'Partner'], ['/kontakt', 'Kontakt']];

/* Foto im Browser als WebP in 640, 960, 1280 und 1920 px Breite erzeugen (der Server hat keine Bildbearbeitung) */
async function webpVariants(file) {
  const img = await new Promise((ok, err) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => err(new Error('Das Bild lässt sich nicht öffnen.')); i.src = URL.createObjectURL(file); });
  const files = {};
  let w = 0, h = 0;
  for (const target of [640, 960, 1280, 1920]) {
    if (target > img.naturalWidth && Object.keys(files).length) break;   // nicht hochrechnen
    const scale = Math.min(1, target / img.naturalWidth);
    const c = document.createElement('canvas');
    c.width = Math.round(img.naturalWidth * scale); c.height = Math.round(img.naturalHeight * scale);
    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
    const data = c.toDataURL('image/webp', 0.76);
    if (!data.startsWith('data:image/webp')) throw new Error('Dieser Browser kann keine WebP-Bilder erzeugen. Bitte Chrome, Edge oder Firefox nutzen.');
    files[target] = data; w = c.width; h = c.height;
  }
  URL.revokeObjectURL(img.src);
  return { files, w, h };
}

function webHead(tab, data) {
  const open = data.checks.filter(c => c.level === 'fehlt').length;
  return `<div class="page-head"><h1>Webseite<small>Texte, Bilder und Aufbau der öffentlichen Vereinswebseite</small></h1>
      <div class="btn-row"><a class="btn keep" href="/" target="_blank" rel="noopener">Webseite öffnen</a></div></div>
    <div class="toolbar">${WEB_TABS.map(([k, l]) => `<a class="btn sm ${k === tab ? 'dark' : ''}" href="#/website/${k}">${l}${k === 'uebersicht' && open ? ` <span class="badge red">${open}</span>` : ''}</a>`).join('')}</div>`;
}

App.pages.website = async (view, args) => {
  const tab = WEB_TABS.some(t => t[0] === args[0]) ? args[0] : 'uebersicht';
  let data = await api('website');
  const saveTexts = async (vals, msg) => {
    if (Object.values(vals).some(hasDashes) && !confirmBox('In den Texten stehen Gedankenstriche. Trotzdem speichern?')) return false;
    data = await api('website', 'PUT', { texts: vals }); toast(msg); return true;
  };

  if (tab === 'uebersicht') {
    const fehlt = data.checks.filter(c => c.level === 'fehlt'), hinweis = data.checks.filter(c => c.level !== 'fehlt');
    const row = c => `<li>${esc(c.text)}${c.link ? ` <a href="${esc(c.link)}">Beheben</a>` : ''}</li>`;
    view.innerHTML = `${webHead(tab, data)}
      <div class="grid2">
        <div class="card"><h2>Was noch fehlt</h2>${fehlt.length ? `<ul class="checklist warn">${fehlt.map(row).join('')}</ul>` : '<p class="muted">Alle Texte sind ausgefüllt.</p>'}
          ${hinweis.length ? `<h3 style="margin-top:16px">Hinweise</h3><ul class="checklist">${hinweis.map(row).join('')}</ul>` : ''}</div>
        <div class="card"><h2>Was kommt woher?</h2>
          <ul class="checklist plain">
            <li><b>Texte</b>: hier unter <a href="#/website/texte">Texte</a>, nach Seiten sortiert.</li>
            <li><b>Bilder</b>: Titelbilder und Galerie unter <a href="#/website/bilder">Bilder</a>.</li>
            <li><b>Kader und Coaches</b>: aus <a href="#/players">Kader &amp; Staff</a>. Fotos nur mit Einwilligung, Jugendspieler nie.</li>
            <li><b>Spiele und Ergebnisse</b>: aus dem <a href="#/games">Spielplan</a>, Logos aus <a href="#/opponents">Gegner</a>.</li>
            <li><b>Sponsoren</b>: alle aktiven aus <a href="#/sponsors">Sponsoren</a> mit Logo und Website.</li>
            <li><b>Instagram</b>: die 6 neuesten Beiträge über <a href="#/autopost/einrichtung">Auto-Posting</a>.</li>
            <li><b>Anfragen</b> aus dem Kontaktformular: unter <a href="#/contacts">Anfragen</a>.</li>
          </ul>
          <h3 style="margin-top:16px">Seiten</h3>
          <div class="btn-row">${WEB_PAGES.map(([u, l]) => `<a class="btn sm" href="${u}" target="_blank" rel="noopener">${l}</a>`).join('')}</div></div>
      </div>`;
    return;
  }

  if (tab === 'texte') {
    view.innerHTML = `${webHead(tab, data)}
      <p class="muted small">Leere Felder erscheinen auf der Webseite als gelb markierter Platzhalter. Bitte keine Gedankenstriche verwenden.</p>
      ${SITE_TEXT_GROUPS.map(([title, url, fields], i) => `<div class="card" style="margin-bottom:16px">
        <div class="page-head" style="margin:0 0 10px"><h2 style="margin:0">${esc(title)}</h2><a class="btn sm keep" href="${url}" target="_blank" rel="noopener">Seite ansehen</a></div>
        <form class="form" id="wt_${i}" onsubmit="return false">${fields.map(f => fieldHtml(f, data.texts[f.key])).join('')}</form></div>`).join('')}
      <div class="btn-row"><button class="btn primary" id="wt_save">Alle Texte speichern</button></div>`;
    $('#wt_save').onclick = async () => {
      const vals = Object.assign({}, ...SITE_TEXT_GROUPS.map(([, , fields], i) => readForm($('#wt_' + i), fields)));
      if (await saveTexts(vals, 'Texte gespeichert')) App.pages.website(view, ['texte']);
    };
    return;
  }

  if (tab === 'bilder') {
    view.innerHTML = `${webHead(tab, data)}
      <p class="muted small">Neue Fotos werden automatisch verkleinert und als WebP in drei Größen gespeichert (schnell auf dem Handy). Am besten Querformat ab 1920 px Breite.
        Der Alt-Text beschreibt das Bild für Suchmaschinen und Menschen, die nicht sehen können. Bitte nur Fotos verwenden, mit denen alle Abgebildeten einverstanden sind.</p>
      <div class="web-imgs">${data.images.map(m => `<div class="card web-img" data-slot="${m.slot}">
        <div class="web-img-pic">${m.preview ? `<img src="${esc(m.preview)}" alt="">` : '<div class="empty">Kein Bild</div>'}</div>
        <h3>${esc(m.label)} ${m.own ? '<span class="badge ok">eigenes Bild</span>' : '<span class="badge">Standard</span>'}</h3>
        <p class="muted small">${esc(m.where)}${m.w ? ` (${m.w} x ${m.h} px)` : ''}</p>
        <label class="small">Alt-Text<textarea class="input" rows="2" data-alt>${esc(m.alt)}</textarea></label>
        <div class="btn-row" style="margin-top:8px"><button class="btn sm primary" data-up>Bild ersetzen</button><button class="btn sm" data-alt-save>Alt-Text speichern</button>
          ${m.own ? '<button class="btn sm ghost" data-reset>Standardbild</button>' : ''}<input type="file" accept="image/jpeg,image/png,image/webp" hidden></div></div>`).join('')}</div>`;
    $$('.web-img').forEach(box => {
      const slot = box.dataset.slot, file = $('input[type=file]', box), alt = () => $('[data-alt]', box).value.trim();
      $('[data-up]', box).onclick = () => file.click();
      file.onchange = async () => {
        const f = file.files[0]; if (!f) return;
        if (!alt() && !confirmBox('Ohne Alt-Text hochladen? Besser vorher kurz beschreiben, was zu sehen ist.')) return;
        try {
          toast('Bild wird vorbereitet ...');
          const v = await webpVariants(f);
          data = await api('website/image/' + slot, 'POST', { ...v, alt: alt() });
          toast('Bild gespeichert'); App.pages.website(view, ['bilder']);
        } catch (e) { alert(e.message); }
      };
      $('[data-alt-save]', box).onclick = async () => { data = await api('website/image/' + slot, 'PUT', { alt: alt() }); toast('Alt-Text gespeichert'); };
      if ($('[data-reset]', box)) $('[data-reset]', box).onclick = async () => {
        if (!confirmBox('Eigenes Bild entfernen und wieder das Standardbild zeigen?')) return;
        data = await api('website/image/' + slot, 'DELETE'); toast('Standardbild wiederhergestellt'); App.pages.website(view, ['bilder']);
      };
    });
    return;
  }

  if (tab === 'startseite') {
    let list = data.layout.map(x => ({ ...x }));
    const draw = () => {
      view.innerHTML = `${webHead(tab, data)}
        <div class="card"><h2>Abschnitte der Startseite</h2>
          <p class="muted small">Reihenfolge mit den Pfeilen ändern, Haken weg = Abschnitt ausblenden. Das Titelbild bleibt immer ganz oben.
            Abschnitte ohne Inhalt (z. B. noch keine Ergebnisse) erscheinen von selbst nicht.</p>
          <ol class="web-order">${list.map((x, i) => `<li class="${x.visible ? '' : 'off'}">
            <label class="check"><input type="checkbox" data-vis="${i}" ${x.visible ? 'checked' : ''}> ${esc(x.label)}</label>
            <span class="btn-row"><button class="btn sm" data-upi="${i}" ${i ? '' : 'disabled'} aria-label="nach oben">↑</button><button class="btn sm" data-downi="${i}" ${i < list.length - 1 ? '' : 'disabled'} aria-label="nach unten">↓</button></span></li>`).join('')}</ol>
          <div class="btn-row" style="margin-top:12px"><button class="btn primary" id="wl_save">Aufbau speichern</button><button class="btn" id="wl_reset">Standard-Reihenfolge</button>
            <a class="btn keep" href="/" target="_blank" rel="noopener">Startseite ansehen</a></div></div>`;
      $$('[data-vis]').forEach(c => c.onchange = () => { list[c.dataset.vis].visible = c.checked; draw(); });
      $$('[data-upi]').forEach(b => b.onclick = () => { const i = +b.dataset.upi; [list[i - 1], list[i]] = [list[i], list[i - 1]]; draw(); });
      $$('[data-downi]').forEach(b => b.onclick = () => { const i = +b.dataset.downi; [list[i + 1], list[i]] = [list[i], list[i + 1]]; draw(); });
      $('#wl_reset').onclick = () => { list = WEB_DEFAULT_ORDER.map(k => ({ ...data.layout.find(x => x.key === k), visible: true })); draw(); };
      $('#wl_save').onclick = async () => { data = await api('website', 'PUT', { layout: list.map(x => [x.key, x.visible]) }); list = data.layout.map(x => ({ ...x })); toast('Aufbau gespeichert'); draw(); };
    };
    const WEB_DEFAULT_ORDER = ['wer', 'karten', 'teams', 'training', 'ergebnisse', 'band', 'sponsoren', 'instagram'];
    draw();
    return;
  }

  if (tab === 'links') {
    let items = data.links.map(x => ({ ...x }));
    const addr = (data.site_url || location.origin).replace(/\/$/, '') + '/links';
    const draw = () => {
      view.innerHTML = `${webHead(tab, data)}
        <div class="card"><h2>Link-Seite für die Instagram-Bio</h2>
          <p class="muted small">Eine eigene Seite mit Knöpfen wie bei Linktree. Sie steht nirgends im Menü, nicht in der Sitemap und nicht bei Google, nur wer die Adresse kennt, kommt hin.
            Diese Adresse in die Bio bei Instagram (und gern auch TikTok oder Facebook) eintragen:</p>
          <div class="btn-row" style="margin:6px 0 14px"><input class="input" id="lk_addr" value="${esc(addr)}" readonly style="max-width:360px">
            <button class="btn" id="lk_copy">Kopieren</button><a class="btn keep" href="/links" target="_blank" rel="noopener">Seite öffnen</a></div>
          <p class="muted small">Ziel: eine Adresse mit https:// oder eine eigene Seite mit / (z. B. /spielplan, /supporter-karte). Roter Knopf = hervorgehoben. Höchstens ${data.links_max} Knöpfe.
            Die Social-Media-Symbole kommen aus dem Reiter <a href="#/website/menu">Menü</a>.${data.links_default ? ' <b>Gerade gilt die Standardliste.</b>' : ''}</p>
          <div class="table-wrap"><table><thead><tr><th></th><th>Text auf dem Knopf</th><th>Ziel</th><th>Hervorheben</th><th></th></tr></thead><tbody>
          ${items.map((it, i) => `<tr>
            <td class="nowrap"><button class="btn sm" data-mv="${i}" data-d="-1" ${i ? '' : 'disabled'} aria-label="nach oben">↑</button><button class="btn sm" data-mv="${i}" data-d="1" ${i < items.length - 1 ? '' : 'disabled'} aria-label="nach unten">↓</button></td>
            <td><input class="input" data-f="label" data-i="${i}" value="${esc(it.label)}" maxlength="60" placeholder="z. B. Tickets fürs Heimspiel" aria-label="Text auf Knopf ${i + 1}"></td>
            <td><input class="input" data-f="url" data-i="${i}" value="${esc(it.url)}" maxlength="500" placeholder="https://... oder /seite" aria-label="Ziel von Knopf ${i + 1}"></td>
            <td><label class="check"><input type="checkbox" data-hot="${i}" ${it.hot ? 'checked' : ''} aria-label="Knopf ${i + 1} rot"></label></td>
            <td><button class="btn sm ghost" data-del="${i}" aria-label="Knopf ${i + 1} entfernen">Entfernen</button></td></tr>`).join('')}
          </tbody></table></div>
          <div class="btn-row" style="margin-top:12px"><button class="btn" id="lk_add" ${items.length >= data.links_max ? 'disabled' : ''}>Knopf hinzufügen</button>
            <button class="btn primary" id="lk_save">Link-Seite speichern</button><button class="btn" id="lk_reset">Standard</button></div></div>`;
      $$('[data-mv]').forEach(b => b.onclick = () => { const i = Number(b.dataset.mv), j = i + Number(b.dataset.d); [items[i], items[j]] = [items[j], items[i]]; draw(); });
      $$('[data-f]').forEach(c => c.oninput = () => { items[c.dataset.i][c.dataset.f] = c.value; });
      $$('[data-hot]').forEach(c => c.onchange = () => { items[c.dataset.hot].hot = c.checked; });
      $$('[data-del]').forEach(b => b.onclick = () => { items.splice(Number(b.dataset.del), 1); draw(); });
      $('#lk_add').onclick = () => { items.push({ label: '', url: 'https://', hot: false }); draw(); };
      $('#lk_copy').onclick = async () => { try { await navigator.clipboard.writeText(addr); toast('Adresse kopiert'); } catch { $('#lk_addr').select(); } };
      $('#lk_reset').onclick = async () => {
        if (!confirmBox('Eigene Knöpfe verwerfen und wieder die Standardliste zeigen?')) return;
        data = await api('website', 'PUT', { links_reset: true }); items = data.links.map(x => ({ ...x })); toast('Standardliste aktiv'); draw();
      };
      $('#lk_save').onclick = async () => {
        const list = items.filter(it => it.label.trim() || (it.url.trim() && it.url.trim() !== 'https://'));
        if (list.some(it => hasDashes(it.label)) && !confirmBox('In den Knöpfen stehen Gedankenstriche. Trotzdem speichern?')) return;
        try { data = await api('website', 'PUT', { links: list }); items = data.links.map(x => ({ ...x })); toast('Link-Seite gespeichert'); draw(); }
        catch (e) { alert(e.message); }
      };
    };
    draw();
    return;
  }

  if (tab === 'menu') {
    let items = data.nav.map(x => ({ ...x }));
    const socials = [['site_social_instagram', 'Instagram', 'https://www.instagram.com/...'], ['site_social_facebook', 'Facebook', 'https://www.facebook.com/...'], ['site_social_tiktok', 'TikTok', 'https://www.tiktok.com/@...']];
    const draw = () => {
      view.innerHTML = `${webHead(tab, data)}
        <div class="grid2">
        <div class="card"><h2>Zusätzliche Menüpunkte</h2>
          <p class="muted small">Das Hauptmenü (Start, Sportarten, Verein, Kontakt, Mitglied werden) steht fest. Hier schaltest du die Zusatzpunkte Dauerkarte und Fanshop ein oder aus
            und gibst ihnen einen eigenen Namen.</p>
          <div class="table-wrap"><table><thead><tr><th></th><th>Anzeigen</th><th>Name im Menü</th><th>Hervorheben</th></tr></thead><tbody>
          ${items.map((it, i) => `<tr class="${it.show ? '' : 'muted'}">
            <td class="nowrap"><button class="btn sm" data-mv="${i}" data-d="-1" ${i ? '' : 'disabled'} aria-label="${esc(it.title)} nach oben">↑</button><button class="btn sm" data-mv="${i}" data-d="1" ${i < items.length - 1 ? '' : 'disabled'} aria-label="${esc(it.title)} nach unten">↓</button></td>
            <td><label class="check"><input type="checkbox" data-show="${i}" ${it.show ? 'checked' : ''}> <b>${esc(it.title)}</b></label>
              ${it.key === 'supporter-karte' ? '<div class="muted small">nur solange die Online-Bestellung offen ist</div>' : ''}${it.key === 'fanshop' ? '<div class="muted small">nur mit Fanshop-Adresse (Texte)</div>' : ''}</td>
            <td><input class="input" data-label="${i}" value="${esc(it.label)}" placeholder="${esc(it.title)}" maxlength="40" aria-label="Name im Menü für ${esc(it.title)}"></td>
            <td><label class="check"><input type="checkbox" data-btn="${i}" ${it.button ? 'checked' : ''} aria-label="${esc(it.title)} hervorheben"></label></td></tr>`).join('')}
          </tbody></table></div>
          <div class="btn-row" style="margin-top:12px"><button class="btn primary" id="mn_save">Menü speichern</button><button class="btn" id="mn_reset">Standard</button></div></div>
        <div class="card"><h2>Social Media im Menü</h2>
          <p class="muted small">Links im Footer der Webseite und auf der Link-Seite. Leer lassen = kein Link. Nur Adressen mit https:// der jeweiligen Plattform. Besucher laden dabei nichts von Instagram, Facebook oder TikTok, erst ein Klick öffnet den Kanal.</p>
          <div class="form">${socials.map(([k, l, ph]) => `<div class="field full"><label for="so_${k}">${l}</label><input class="input" id="so_${k}" value="${esc(data.texts[k] || '')}" placeholder="${ph}"></div>`).join('')}</div>
          <div class="btn-row" style="margin-top:12px"><button class="btn primary" id="so_save">Kanäle speichern</button></div></div>
        </div>`;
      $$('[data-mv]').forEach(b => b.onclick = () => { const i = Number(b.dataset.mv), j = i + Number(b.dataset.d); [items[i], items[j]] = [items[j], items[i]]; draw(); });
      $$('[data-show]').forEach(c => c.onchange = () => { items[c.dataset.show].show = c.checked; draw(); });
      $$('[data-btn]').forEach(c => c.onchange = () => { items[c.dataset.btn].button = c.checked; });
      $$('[data-label]').forEach(c => c.oninput = () => { items[c.dataset.label].label = c.value; });
      $('#mn_reset').onclick = () => { items = ['supporter-karte', 'fanshop'].map(k => items.find(x => x.key === k)).filter(Boolean)
        .map(x => ({ ...x, show: true, label: '', button: false })); draw(); };
      $('#mn_save').onclick = async () => {
        try { data = await api('website', 'PUT', { nav: items.map(({ key, show, label, button }) => ({ key, show, label, button })) }); items = data.nav.map(x => ({ ...x })); toast('Menü gespeichert'); draw(); }
        catch (e) { alert(e.message); }
      };
      $('#so_save').onclick = async () => {
        const texts = Object.fromEntries(socials.map(([k]) => [k, $('#so_' + k).value.trim()]));
        const bad = socials.filter(([k]) => texts[k] && !/^https:\/\/\S+$/.test(texts[k])).map(([, l]) => l);
        if (bad.length) return alert(`Bitte eine vollständige Adresse mit https:// eintragen: ${bad.join(', ')}`);
        try { data = await api('website', 'PUT', { texts }); toast('Kanäle gespeichert'); draw(); } catch (e) { alert(e.message); }
      };
    };
    draw();
    return;
  }

  if (tab === 'sitemap') {
    let list = data.sitemap.map(x => ({ ...x }));
    const prios = ['1.0', '0.9', '0.8', '0.7', '0.6', '0.5', '0.4', '0.3', '0.2', '0.1', '0.0'];
    const draw = () => {
      view.innerHTML = `${webHead(tab, data)}
        <div class="card"><h2>Sitemap für Suchmaschinen</h2>
          <p class="muted small">Die Sitemap (<a href="/sitemap.xml" target="_blank" rel="noopener">/sitemap.xml</a>) sagt Google, Bing und Co., welche Seiten es gibt.
            Haken weg = Seite steht nicht in der Sitemap (sie bleibt aber erreichbar und kann trotzdem gefunden werden).
            Die Priorität (1.0 = am wichtigsten) ist nur ein Hinweis an die Suchmaschine, wie wichtig die Seiten im Vergleich zueinander sind.</p>
          <div class="table-wrap"><table><thead><tr><th>In der Sitemap</th><th>Priorität</th></tr></thead><tbody>
          ${list.map((x, i) => `<tr class="${x.on ? '' : 'muted'}"><td><label class="check"><input type="checkbox" data-smon="${i}" ${x.on ? 'checked' : ''}> ${esc(x.label)}</label>
              <div class="muted small">/${esc(x.key)}</div></td>
            <td><select class="input" data-smp="${i}" aria-label="Priorität ${esc(x.label)}" ${x.on ? '' : 'disabled'}>${prios.map(p => `<option ${p === x.prio ? 'selected' : ''}>${p}</option>`).join('')}</select>
              ${x.prio !== x.default ? `<div class="muted small">Standard ${x.default}</div>` : ''}</td></tr>`).join('')}
          </tbody></table></div>
          <div class="btn-row" style="margin-top:12px"><button class="btn primary" id="sm_save">Sitemap speichern</button><button class="btn" id="sm_reset">Standard</button></div></div>`;
      $$('[data-smon]').forEach(c => c.onchange = () => { list[c.dataset.smon].on = c.checked; draw(); });
      $$('[data-smp]').forEach(s => s.onchange = () => { list[s.dataset.smp].prio = s.value; draw(); });
      $('#sm_reset').onclick = () => { list = list.map(x => ({ ...x, on: true, prio: x.default })); draw(); };
      $('#sm_save').onclick = async () => {
        try { data = await api('website', 'PUT', { sitemap: Object.fromEntries(list.map(x => [x.key, [x.on, x.prio]])) }); list = data.sitemap.map(x => ({ ...x })); toast('Sitemap gespeichert'); draw(); }
        catch (e) { alert(e.message); }
      };
    };
    draw();
    return;
  }

  if (tab === 'hinweis') {
    const active = data.texts.site_notice_text && (!data.texts.site_notice_until || data.texts.site_notice_until >= todayStr());
    view.innerHTML = `${webHead(tab, data)}
      <div class="card"><h2>Hinweis-Leiste</h2>
        <p class="muted small">Eine violette Leiste ganz oben auf jeder Seite, z. B. für ein Heimspiel, ein Event oder eine Trainingsabsage.</p>
        <p>${active ? '<span class="badge ok">wird gerade angezeigt</span>' : '<span class="badge">nicht sichtbar</span>'}</p>
        <form class="form" id="wn_form" onsubmit="return false">${SITE_NOTICE_FIELDS.map(f => fieldHtml(f, data.texts[f.key])).join('')}</form>
        <div class="btn-row" style="margin-top:12px"><button class="btn primary" id="wn_save">Speichern</button><button class="btn" id="wn_off">Leiste entfernen</button></div></div>`;
    $('#wn_save').onclick = async () => {
      const vals = readForm($('#wn_form'), SITE_NOTICE_FIELDS);
      if (vals.site_notice_link && !/^(\/(?!\/)|https?:\/\/)/.test(vals.site_notice_link)) return alert('Der Link muss mit / (Seite der Webseite) oder https:// beginnen.');
      if (await saveTexts(vals, 'Hinweis-Leiste gespeichert')) App.pages.website(view, ['hinweis']);
    };
    $('#wn_off').onclick = async () => { await saveTexts({ site_notice_text: '', site_notice_link: '', site_notice_until: '' }, 'Leiste entfernt'); App.pages.website(view, ['hinweis']); };
    return;
  }

  // Vorschau: die echte Webseite in Handy-, Tablet- oder Desktopbreite
  const page = App._webPage || '/', width = App._webWidth || 390;
  view.innerHTML = `${webHead(tab, data)}
    <div class="toolbar">${WEB_PAGES.map(([u, l]) => `<button class="btn sm ${u === page ? 'dark' : ''}" data-pg="${u}">${l}</button>`).join('')}
      <span style="flex:1"></span>${[[390, 'Handy'], [768, 'Tablet'], [1280, 'Desktop']].map(([w, l]) => `<button class="btn sm ${w === width ? 'dark' : ''}" data-w="${w}">${l}</button>`).join('')}</div>
    <div class="web-preview"><iframe src="${page}" title="Vorschau der Webseite" style="width:${width}px"></iframe></div>`;
  $$('[data-pg]').forEach(b => b.onclick = () => { App._webPage = b.dataset.pg; App.pages.website(view, ['vorschau']); });
  $$('[data-w]').forEach(b => b.onclick = () => { App._webWidth = +b.dataset.w; App.pages.website(view, ['vorschau']); });
};

