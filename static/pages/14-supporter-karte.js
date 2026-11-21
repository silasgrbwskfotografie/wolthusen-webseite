App.pages.cards = async (view) => {
  const s = App.settings;
  return simpleList({
    table: 'supporter_cards', title: 'Dauerkarte', fields: F.supporter_cards, newTitle: 'Karte verkauft',
    newRecord: { season: s.season, price: s.card_price, sold_on: todayStr() },
    sort: (a, b) => (b.sold_on || '').localeCompare(a.sold_on || ''),
    sub: l => `${l.length} Karten verkauft`,
    extraHead: async list => {
      const seasons = [...new Set(list.map(c => c.season).filter(Boolean))].sort().reverse();
      const on = await api('cards/online');
      const url = on.url.startsWith('http') ? on.url : location.origin + on.url;
      const orders = (await api('card_orders').catch(() => [])).sort((a, b) => (b.created || '').localeCompare(a.created || ''));
      const unpaid = orders.filter(o => !Number(o.paid) && !o.cancelled);
      const w = can('finanzen', 2);
      const holders = o => { try { return JSON.parse(o.holders || '[]'); } catch { return []; } };
      const missing = [!on.inv_iban && 'IBAN', /\[[^\]]+\]/.test((on.inv_sender || '') + (on.inv_tax_note || '')) && 'Angaben in [Klammern]',
        !on.smtp && 'E-Mail-Versand (Einstellungen)'].filter(Boolean);
      const reload = () => { delete App.cache.supporter_cards; delete App.cache.card_orders; route(); };
      setTimeout(() => {   // Knöpfe erst nach dem Zeichnen der Seite verbinden
        if ($('#co_copy')) $('#co_copy').onclick = () => { copyText(url); toast('Link kopiert'); };
        if ($('#co_toggle')) $('#co_toggle').onclick = async () => { await api('cards/online', 'PUT', { open: !on.open }); toast(on.open ? 'Online-Bestellung geschlossen' : 'Online-Bestellung geöffnet'); route(); };
        if ($('#co_orders')) $('#co_orders').onclick = async ev => {
          const b = ev.target.closest('button[data-act]'); if (!b) return;
          const o = orders.find(x => x.id == b.dataset.id); if (!o) return;
          b.disabled = true;
          try {
            if (b.dataset.act === 'paid') {
              if (!confirmBox(`Bestellung ${o.order_no} (${eur(o.total)}) als bezahlt markieren? Die Rechnung wird erstellt und an ${o.email} geschickt.`)) { b.disabled = false; return; }
              const r = await api(`cards/orders/${o.id}/paid`, 'POST', {});
              toast(r.mail_error ? `Rechnung ${r.invoice_no} erstellt, Mail nicht verschickt` : `Rechnung ${r.invoice_no} verschickt`);
              if (r.mail_error) alert(r.mail_error);
            } else if (b.dataset.act === 'resend') {
              const r = await api(`cards/orders/${o.id}/invoice`, 'POST', {});
              if (r.mail_error) alert(r.mail_error); else toast('Rechnung erneut verschickt');
            } else if (b.dataset.act === 'cancel') {
              if (!confirmBox(`Bestellung ${o.order_no} von ${o.buyer} stornieren? Die unbezahlten Karten werden entfernt und ${o.email} bekommt eine Stornobestätigung.`)) { b.disabled = false; return; }
              const r = await api(`cards/orders/${o.id}/cancel`, 'POST', {});
              if (r.mail_error) alert(r.mail_error); else toast('Storniert, Bestätigung verschickt');
            } else if (b.dataset.act === 'shipped') {
              let tracking = '';
              if (o.delivery === 'Einschreiben') {
                tracking = (window.prompt(`Sendungsnummer des Einschreibens für ${o.order_no} (${o.buyer}):\nSie wird dem Kunden mit der Versandbestätigung geschickt.`) || '').replace(/\s+/g, '');
                if (!tracking) { b.disabled = false; return; }
              } else if (!confirmBox(`Bestellung ${o.order_no} als verschickt markieren? ${o.buyer} bekommt eine Versandbestätigung an ${o.email}.`)) { b.disabled = false; return; }
              const r = await api(`cards/orders/${o.id}/shipped`, 'POST', { tracking_no: tracking });
              if (r.mail_error) alert(r.mail_error); else toast('Versandbestätigung verschickt');
            } else if (b.dataset.act === 'delivered') {
              await api(`card_orders/${o.id}`, 'PUT', { delivered: Number(o.delivered) ? 0 : 1 });
              toast(Number(o.delivered) ? 'Als nicht geliefert markiert' : 'Als geliefert markiert');
            } else if (b.dataset.act === 'del') {
              if (!confirmBox(`Bestellung ${o.order_no} von ${o.buyer} löschen? Unbezahlte Karten dieser Bestellung werden mit gelöscht.`)) { b.disabled = false; return; }
              await api(`card_orders/${o.id}`, 'DELETE');
              toast('Bestellung gelöscht');
            }
            reload();
          } catch (e) { b.disabled = false; alert(e.message); }
        };
        if ($('#inv_save')) $('#inv_save').onclick = async () => {
          const data = {};
          $$('#inv_form [data-k]').forEach(el => { data[el.dataset.k] = noDashes(el.value); });
          try { await api('cards/online', 'PUT', data); toast('Gespeichert'); route(); } catch (e) { alert(e.message); }
        };
      });
      const orderRow = o => {
        const hs = holders(o), post = o.delivery === 'Post' || o.delivery === 'Einschreiben', done = Number(o.delivered);
        const status = o.cancelled ? `<span class="badge red">storniert</span><div class="muted small">${fmtStamp(o.cancelled)}<br>${o.cancelled_by === 'Kunde' ? 'vom Kunden per Link' : 'im Hub: ' + esc(o.cancelled_by || '')}</div>`
          : Number(o.paid) ? `<span class="badge ok">bezahlt</span><div class="muted small">${fmtDate(o.paid_on)}</div>` : '<span class="badge warn">offen</span>';
        const inv = o.invoice_no ? `<a href="/api/cards/orders/${o.id}/invoice.pdf" target="_blank" rel="noopener">${esc(o.invoice_no)}</a>
            <div class="muted small">${o.invoice_sent ? 'verschickt ' + fmtStamp(o.invoice_sent) : 'nicht verschickt'}</div>` : o.cancelled ? '' : '<span class="muted small">nach Zahlung</span>';
        const letter = `<a class="btn sm keep${Number(o.paid) && !done ? ' primary' : ''}" href="/api/cards/orders/${o.id}/letter.pdf" target="_blank" rel="noopener" title="Fanbrief mit Kartennummern zum Ausdrucken, passt in einen Fensterumschlag DIN lang">Fanbrief drucken</a>`;
        const acts = o.cancelled ? (w ? `<button class="btn sm danger" data-act="del" data-id="${o.id}">Löschen</button>` : '') : (w ? [
          !Number(o.paid) ? `<button class="btn primary sm" data-act="paid" data-id="${o.id}">Bezahlt</button>` : '',
          !Number(o.paid) ? `<button class="btn sm" data-act="cancel" data-id="${o.id}">Stornieren</button>` : '',
          Number(o.paid) ? letter : '',
          o.invoice_no ? `<button class="btn sm" data-act="resend" data-id="${o.id}">Rechnung erneut senden</button>` : '',
          post && !done ? `<button class="btn sm" data-act="shipped" data-id="${o.id}">${o.delivery === 'Einschreiben' ? 'Verschickt (Sendungsnummer)' : 'Verschickt'}</button>`
            : `<button class="btn sm" data-act="delivered" data-id="${o.id}">${done ? 'Nicht geliefert' : 'Übergeben'}</button>`,
          `<button class="btn sm danger" data-act="del" data-id="${o.id}">Löschen</button>`] : [Number(o.paid) ? letter : '']).join(' ');
        return `<tr><td><b>${esc(o.order_no || '')}</b><div class="muted small">${fmtStamp(o.created)}</div></td>
          <td><b>${esc(o.buyer || '')}</b><div class="small"><a href="mailto:${esc(o.email || '')}">${esc(o.email || '')}</a>${o.phone ? '<br>' + esc(o.phone) : ''}</div>
            ${o.message ? `<div class="muted small">${esc(o.message)}</div>` : ''}</td>
          <td>${o.count} × <div class="small">${(() => {
            const cs = list.filter(c => c.order_id == o.id);
            return (cs.length ? cs.map(c => `${c.number ? `<b>${esc(c.number)}</b> ` : ''}${esc(c.holder || '')}`) : hs.map(esc)).join('<br>');
          })()}</div></td>
          <td>${post ? `<b>${esc(o.delivery)}</b><div class="small">${esc(o.street || '')}<br>${esc(o.zip || '')} ${esc(o.city || '')}</div>` : '<b>Einlass</b>'}
            ${done ? `<div><span class="badge ok">${post ? 'verschickt' : 'übergeben'}</span>${o.shipped_on ? ` <span class="muted small">${fmtDate(o.shipped_on)}</span>` : ''}</div>` : ''}
            ${o.tracking_no ? `<div class="small">Sendungsnr. ${esc(o.tracking_no)}</div>` : ''}
            ${done && post ? `<div class="muted small">${o.shipped_mail ? 'Kunde informiert' : 'Kunde nicht informiert'}</div>` : ''}</td>
          <td style="white-space:nowrap">${eur(o.total)}${post ? `<div class="muted small">inkl. ${eur(o.shipping)} Versand</div>` : ''}</td>
          <td>${status}</td><td>${inv}</td><td class="btn-row">${acts}</td></tr>`;
      };
      const field = (k, label, opts = {}) => `<label class="field${opts.full ? ' full' : ''}"><span>${label}</span>${opts.area
        ? `<textarea class="input" rows="${opts.rows || 3}" data-k="${k}" ${w ? '' : 'readonly'}>${esc(on[k] || '')}</textarea>`
        : `<input class="input" data-k="${k}" value="${esc(on[k] || '')}" ${opts.ph ? `placeholder="${esc(opts.ph)}"` : ''} ${w ? '' : 'readonly'}>`}
        ${opts.hint ? `<small class="muted">${opts.hint}</small>` : ''}</label>`;
      return `<div class="card" style="margin-bottom:16px"><h2>Online-Bestellung ${on.open ? '<span class="badge ok">offen</span>' : '<span class="badge">geschlossen</span>'}</h2>
        <p class="muted small">Über diesen Link können alle ohne Anmeldung Dauerkarten bestellen (bis zu 10 Karten, ein Name pro Karte, Abholung am Einlass, Versand per Post oder per Einschreiben). Mit „Verschickt“ bekommt der Kunde eine Versandbestätigung, beim Einschreiben mit Sendungsnummer.
          Bezahlte Karten bekommen automatisch die nächste Kartennummer; „Fanbrief drucken“ erstellt den Brief mit Kartennummern für den Umschlag.
          Der Besteller bekommt sofort eine Bestätigung mit den Überweisungsdaten. Sobald das Geld da ist, klickst du bei der Bestellung auf „Bezahlt“: Dann werden die Karten als bezahlt markiert und die Rechnung (PDF) geht automatisch per E-Mail raus.</p>
        <div class="btn-row"><input class="input" readonly value="${esc(url)}" style="max-width:380px"><button class="btn keep" id="co_copy">Link kopieren</button>
          <a class="btn keep" href="/supporter-karte" target="_blank" rel="noopener">Ansehen</a>
          ${w ? `<button class="btn ${on.open ? '' : 'primary'}" id="co_toggle">${on.open ? 'Bestellung schließen' : 'Bestellung öffnen'}</button>` : ''}</div>
        ${missing.length ? `<div class="warnline" style="margin-top:10px">Vor dem Öffnen noch ausfüllen: ${esc(missing.join(', '))}.</div>` : ''}</div>
      <div class="card" style="margin-bottom:16px"><h2>Online-Bestellungen ${unpaid.length ? `<span class="badge warn">${unpaid.length} offen</span>` : ''}</h2>
        ${orders.length ? `<div class="table-wrap"><table><thead><tr><th>Bestellung</th><th>Besteller</th><th>Karten</th><th>Lieferung</th><th>Summe</th><th>Zahlung</th><th>Rechnung</th><th></th></tr></thead>
          <tbody id="co_orders">${orders.map(orderRow).join('')}</tbody></table></div>` : '<p class="muted">Noch keine Online-Bestellungen.</p>'}</div>
      <details class="card" style="margin-bottom:16px"${missing.length && w ? ' open' : ''}><summary><b>Bankverbindung, Rechnung, Ablauf und Lieferung</b></summary>
        <div class="form" id="inv_form" style="margin-top:12px">
          ${field('inv_account_holder', 'Kontoinhaber', { ph: 'SV Amisia Stern Wolthusen e.V.' })}
          ${field('inv_iban', 'IBAN')}${field('inv_bic', 'BIC')}${field('inv_bank', 'Bank')}
          ${field('inv_due_days', 'Zahlungsziel (Tage)')}${field('card_shipping', 'Versand per Post (€ pro Bestellung)')}
          ${field('card_shipping_registered', 'Versand per Einschreiben (€ pro Bestellung)')}
          ${field('inv_sender', 'Absender auf der Rechnung', { area: true, rows: 4, hint: 'Name des Vereins und Anschrift, eine Angabe pro Zeile.' })}
          ${field('inv_tax_no', 'Steuernummer des Vereins', { hint: 'Pflichtangabe auf Rechnungen (oder USt-IdNr.).' })}
          ${field('inv_tax_note', 'Hinweis zur Umsatzsteuer', { area: true, hint: 'Bitte mit dem Kassenwart klären, z. B. Steuerbefreiung oder enthaltene Umsatzsteuer.' })}
          ${field('site_card_cancel_text', 'Freiwillige Stornierung (Bestellseite und Bestätigungsmail)', { area: true, rows: 3, full: true, hint: 'Kunden können bis Zahlungseingang über den Link in der Bestätigungsmail stornieren. Bitte nicht „Widerrufsrecht“ nennen, ein gesetzliches Widerrufsrecht besteht nicht.' })}
          ${field('card_letter_text', 'Begleitbrief (liegt den Karten bei)', { area: true, rows: 8, full: true, hint: '{Name} wird durch den Vornamen des Bestellers ersetzt, {Saison} durch die Saison. Darunter druckt der Hub automatisch die Kartennummern mit Namen und die nächsten Heimspiele der Herren. Leer = Standardtext.' })}
          ${field('site_card_process', 'Ablauf der Bestellung (Webseite)', { area: true, rows: 7, full: true, hint: 'Eine Zeile pro Schritt, beginnend mit „1.“, „2.“ usw.' })}
          ${field('site_card_delivery_text', 'Lieferung (Webseite und Bestätigungsmail)', { area: true, rows: 3, full: true, hint: 'Zum Beispiel wann die Karten verschickt werden oder ab welchem Heimspiel sie am Einlass liegen. Leer = „Infos zur Lieferung folgen“.' })}
        </div>${w ? '<div class="btn-row" style="margin-top:12px"><button class="btn primary" id="inv_save">Speichern</button></div>' : ''}</details>
      <div class="grid g${Math.min(Math.max(seasons.length, 1), 3)}" style="margin-bottom:20px">${(seasons.length ? seasons : [s.season]).map(se => {
        const cs = list.filter(c => c.season == se);
        const sum = cs.reduce((a, c) => a + (Number(c.price) || 0), 0);
        const paid = cs.filter(c => Number(c.paid)).reduce((a, c) => a + (Number(c.price) || 0), 0);
        const wol = cs.length * (Number(s.card_share_wolthusen) || 0);
        return `<div class="card"><h2>Saison ${esc(se)}</h2>
          <div class="sum-row"><span>Verkaufte Karten</span><b>${cs.length}</b></div>
          <div class="sum-row"><span>Umsatz</span><b>${eur(sum)}</b></div>
          <div class="sum-row"><span>Davon bezahlt</span><b>${eur(paid)}</b></div>
          <div class="sum-row"><span>Anteil Eintritt Wolthusen (${eur(s.card_share_wolthusen)} je Karte)</span><b>${eur(wol)}</b></div>
          <div class="sum-row"><span>Verbleibt beim Verein</span><b style="color:var(--red)">${eur(sum - wol)}</b></div></div>`;
      }).join('')}</div>`;
    },
    columns: [
      { label: 'Nr.', html: r => esc(r.number || '') },
      { label: 'Inhaber', html: r => `<b>${esc(r.holder || '')}</b> ${r.source === 'Online' ? '<span class="badge red">Online</span>' : ''}` },
      { label: 'Kontakt', html: r => [r.email ? `<a href="mailto:${esc(r.email)}">${esc(r.email)}</a>` : '', esc(r.phone || '')].filter(Boolean).join('<br>') },
      { label: 'Saison', html: r => esc(r.season || '') },
      { label: 'Verkauft', html: r => fmtDate(r.sold_on) },
      { label: 'Preis', html: r => eur(r.price) },
      { label: 'Bezahlt', html: r => Number(r.paid) ? '<span class="badge ok">ja</span>' : '<span class="badge warn">offen</span>' },
    ],
  })(view);
};

