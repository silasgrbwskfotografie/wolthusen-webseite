/* SV Amisia Wolthusen: nur kleine Extras, die Seite funktioniert auch ohne JavaScript. */
document.documentElement.classList.add('js');

// Abschnitte beim Scrollen sanft einblenden
const items = document.querySelectorAll('.reveal');
if ('IntersectionObserver' in window) {
  const io = new IntersectionObserver(entries => entries.forEach(en => {
    if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
  }), { rootMargin: '0px 0px -10% 0px' });
  items.forEach(el => io.observe(el));
} else {
  items.forEach(el => el.classList.add('in'));
}

// Untermenüs (Sportarten, Verein): auf- und zuklappen per Klick, Escape und Klick daneben schließen
const dds = [...document.querySelectorAll('.dd')];
const closeAll = except => dds.forEach(d => { if (d !== except) { d.classList.remove('open'); d.querySelector('.dd-btn').setAttribute('aria-expanded', 'false'); } });
dds.forEach(d => d.querySelector('.dd-btn').addEventListener('click', () => {
  const open = !d.classList.contains('open');
  closeAll(d);
  d.classList.toggle('open', open);
  d.querySelector('.dd-btn').setAttribute('aria-expanded', String(open));
}));
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeAll(); });
document.addEventListener('click', e => { if (!e.target.closest('.dd')) closeAll(); });

// Handy-Menü nach dem Antippen eines Links schließen
document.querySelectorAll('.site-nav a').forEach(a => a.addEventListener('click', () => { document.getElementById('menu').checked = false; }));

// Dauerkarte bestellen: nur so viele Namensfelder wie Karten, Anschrift nur bei Post, Summe live (ohne JS: alle Felder sichtbar)
const cardForm = document.querySelector('form.card-order');
if (cardForm) {
  const num = v => Number(String(v || '').replace(',', '.')) || 0;
  const eur = x => x.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' €';
  const price = num(cardForm.dataset.price);
  const ships = { post: ['Versand per Post', num(cardForm.dataset.ship)], einschreiben: ['Versand per Einschreiben', num(cardForm.dataset.shipReg)] };
  const count = cardForm.elements.count, sum = cardForm.querySelector('[data-sum]'), addr = cardForm.querySelector('.address');
  const update = () => {
    const n = Number(count.value) || 1, way = ships[cardForm.elements.delivery.value], post = !!way, ship = way ? way[1] : 0;
    cardForm.querySelectorAll('.holder').forEach(l => { l.hidden = Number(l.dataset.n) > n; });
    addr.hidden = !post;
    ['street', 'zip', 'city'].forEach(k => { cardForm.elements[k].required = post; });
    if (price && sum) {
      const lines = [`${n} × Dauerkarte zu je ${eur(price)}`];
      if (post) lines.push(`${way[0]}: ${eur(ship)}`);
      sum.textContent = '';
      lines.forEach(t => { sum.append(t, document.createElement('br')); });
      const b = document.createElement('b'); b.textContent = `Gesamt: ${eur(price * n + (post ? ship : 0))}`;
      sum.append(b);
    }
  };
  cardForm.addEventListener('change', update);
  update();
}
