'use strict';
(() => {
  const body = document.body;
  const products = JSON.parse(document.getElementById('catalog-data').textContent);
  const byId = Object.fromEntries(products.map(p => [String(p.id), p]));
  const money = cents => new Intl.NumberFormat('en-US', {style:'currency',currency:'USD'}).format(cents / 100);
  let toastTimer;
  function toast(message, bagLink = false) {
    const el = document.querySelector('.toast');
    el.replaceChildren(document.createTextNode(message));
    if (bagLink) {const a = document.createElement('a'); a.href='/cart/'; a.textContent='View bag ↗'; el.append(a);}
    el.classList.add('visible'); clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove('visible'), 5500);
  }
  // Shared progressive enhancement: HTML forms remain fully functional on Django without JS.
  document.addEventListener('click', event => {
    const step = event.target.closest('[data-quantity-step]');
    if (!step) return;
    const input = step.parentElement.querySelector('input');
    input.value = Math.max(1, Math.min(9, (Number(input.value) || 1) + Number(step.dataset.quantityStep)));
    input.dispatchEvent(new Event('change', {bubbles:true}));
  });
  const cards = [...document.querySelectorAll('.catalog-grid .product-card')];
  if (cards.length) {
    let category = 'all';
    const search = document.getElementById('product-search');
    const sort = document.getElementById('product-sort');
    const grid = document.querySelector('.catalog-grid');
    const original = new Map(cards.map((card, index) => [card, index]));
    function filter() {
      let visible = 0;
      for (const card of cards) {
        card.hidden = !((category === 'all' || card.dataset.category === category) &&
          (card.dataset.name + ' ' + card.dataset.category.toLowerCase()).includes(search.value.toLowerCase().trim()));
        if (!card.hidden) visible++;
      }
      document.querySelector('[data-result-count]').textContent = `${visible} ${visible === 1 ? 'everyday essential' : 'thoughtfully chosen essentials'}`;
      document.querySelector('.empty-search').hidden = visible !== 0;
      cards.sort((a,b) => sort.value === 'price-low' ? Number(a.dataset.price)-Number(b.dataset.price) :
        sort.value === 'price-high' ? Number(b.dataset.price)-Number(a.dataset.price) :
        sort.value === 'name' ? a.dataset.name.localeCompare(b.dataset.name) : original.get(a)-original.get(b)).forEach(card => grid.append(card));
    }
    document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
      category = button.dataset.filter;
      document.querySelectorAll('[data-filter]').forEach(b => {b.classList.toggle('active', b === button); b.setAttribute('aria-pressed', String(b === button));});
      filter();
    }));
    search.addEventListener('input', filter); sort.addEventListener('change', filter);
  }
  if (body.dataset.runtime !== 'preview') return;
  // Owner-private hosted preview. All state here is illustrative, never a payment record.
  const cartKey = 'fieldform.preview.bag.v1';
  const receiptKey = 'fieldform.preview.receipt.v1';
  function readCart() {
    try {
      const raw = JSON.parse(localStorage.getItem(cartKey) || '{}');
      if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {};
      return Object.fromEntries(Object.entries(raw).filter(([id,n]) => byId[id] && Number.isInteger(n) && n >= 1 && n <= Math.min(9,byId[id].stock)));
    } catch { return {}; }
  }
  function saveCart(cart) {
    try {localStorage.setItem(cartKey, JSON.stringify(cart)); return true;}
    catch {toast('Browser storage is unavailable. Allow site storage to use the demo bag.'); return false;}
  }
  function summary() {
    const lines = Object.entries(readCart()).map(([id,quantity]) => ({p:byId[id],quantity,total:byId[id].price*quantity}));
    const subtotal = lines.reduce((n,line) => n+line.total,0);
    const shipping = !subtotal || subtotal >= 7500 ? 0 : 600;
    return {lines,subtotal,shipping,total:subtotal+shipping,count:lines.reduce((n,l)=>n+l.quantity,0)};
  }
  const image = p => `/static/shop/images/${p.image}`;
  const shippingText = s => s.shipping ? money(s.shipping) : 'Free';
  function updateCount() {document.querySelectorAll('[data-cart-count]').forEach(el=>{el.textContent=summary().count;});}
  function renderCart() {
    const target = document.getElementById('cart-content'); if (!target) return;
    const s = summary();
    if (!s.lines.length) {
      target.innerHTML = '<div class="empty-state"><div class="empty-icon">✳</div><h2>A little room for good things.</h2><p>Your bag is empty. Find an everyday companion<br>in our small collection.</p><a class="button" href="/shop/">Explore the collection <span>↗</span></a></div>';
      return;
    }
    // All interpolated text below comes from the bundled, immutable sample catalog.
    target.innerHTML = `<div class="cart-layout"><div class="cart-items"><div class="cart-column-label"><span>PRODUCT</span><span>QUANTITY & TOTAL</span></div>${s.lines.map(({p,quantity,total})=>`<article class="cart-row"><a class="cart-image" href="/products/${p.slug}/"><img src="${image(p)}" alt="${p.name}" width="160" height="160"></a><div class="cart-item-info"><a href="/products/${p.slug}/">${p.name}</a><span>${p.color}</span><span>${money(p.price)} each</span><button class="remove-button" data-remove="${p.id}" aria-label="Remove ${p.name}">Remove</button></div><div class="cart-item-end"><div class="quantity-control"><button type="button" data-quantity-step="-1" aria-label="Decrease ${p.name} quantity">−</button><input type="number" min="1" max="9" value="${quantity}" data-cart-quantity="${p.id}" aria-label="${p.name} quantity"><button type="button" data-quantity-step="1" aria-label="Increase ${p.name} quantity">+</button></div><strong>${money(total)}</strong></div></article>`).join('')}<a href="/shop/" class="text-link continue-link">← Keep exploring</a></div><aside class="order-summary"><span class="eyebrow">A LITTLE SOMETHING FOR YOU</span><h2>Bag summary</h2><div><span>Subtotal</span><span>${money(s.subtotal)}</span></div><div><span>Demo shipping</span><span>${shippingText(s)}</span></div><p class="shipping-progress">${s.shipping?`You’re ${money(7500-s.subtotal)} from free demo shipping.`:'Your bag has free demo shipping.'}</p><div class="summary-total"><strong>Total</strong><strong>${money(s.total)}</strong></div><p class="tax-note">USD · Demo tax $0.00 · No real charges.</p><a class="button" href="/checkout/">Continue to checkout <span>↗</span></a><p class="secure-note">Sandbox only. No card details collected here.</p></aside></div>`;
  }
  function renderCheckout() {
    const target = document.getElementById('checkout-summary'); if(!target) return;
    const s = summary();
    target.innerHTML = `<span class="eyebrow">YOUR EVERYDAY ESSENTIALS</span><h2>Ready when you are.</h2>${s.lines.map(({p,quantity,total})=>`<div><span>${p.name} × ${quantity}</span><span>${money(total)}</span></div>`).join('')}<div><span>Demo shipping</span><span>${shippingText(s)}</span></div><div class="summary-total"><strong>Demo total</strong><strong>${money(s.total)}</strong></div><p class="tax-note">USD · Demo tax $0.00 · No real charges.</p>${s.lines.length?'<form id="checkout-form"><button class="button" type="submit">Simulate checkout <span>↗</span></button></form>':'<p>Your bag is empty.</p><a class="button" href="/shop/">Explore the collection ↗</a>'}<a class="cancel-link" href="/checkout/cancel/">Cancel & return to bag</a><p class="secure-note">No real transactions. No card data on this store.</p>`;
  }
  document.addEventListener('submit', event => {
    const form = event.target;
    if (form.matches('.cart-add')) {
      event.preventDefault();
      const data = new FormData(form), id = String(data.get('product_id')), amount = Number(data.get('quantity'));
      if (!byId[id] || !Number.isInteger(amount) || amount < 1 || amount > 9) {toast('Choose a quantity from 1 to 9.'); return;}
      const cart = readCart(), next = (cart[id] || 0) + amount;
      if (next > Math.min(9,byId[id].stock)) {toast('You can add up to 9 of each sample product.'); return;}
      cart[id] = next;
      if (saveCart(cart)) {updateCount();toast(`${byId[id].name} added to your bag.`,true);document.querySelectorAll('.bag-count').forEach(el=>{el.classList.remove('bump');void el.offsetWidth;el.classList.add('bump');});}
    }
    if (form.id === 'checkout-form') {
      event.preventDefault();
      const s = summary(); if (!s.lines.length) {renderCheckout();return;}
      try {
        const nonce = Array.from(crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2,'0')).join('');
        localStorage.setItem(receiptKey,JSON.stringify({nonce,total:s.total,created:Date.now()}));
        if (!saveCart({})) return;
        location.assign(`/checkout/complete/?demo=${encodeURIComponent(nonce)}`);
      } catch {toast('Browser storage is unavailable. Your bag has not been checked out.');}
    }
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-remove]'); if (!button) return;
    const cart = readCart(), id = button.dataset.remove; delete cart[id];
    if(saveCart(cart)){updateCount();renderCart();toast(`${byId[id].name} removed.`);}
  });
  document.addEventListener('change', event => {
    const input = event.target.closest('[data-cart-quantity]'); if(!input) return;
    const quantity = Number(input.value), id = input.dataset.cartQuantity;
    if(!Number.isInteger(quantity) || quantity < 1 || quantity > 9){toast('Choose a quantity from 1 to 9.');renderCart();return;}
    const cart = readCart();cart[id] = quantity;
    if(saveCart(cart)){updateCount();renderCart();}
  });
  if (body.dataset.page === 'complete') {
    let receipt;
    try {receipt=JSON.parse(localStorage.getItem(receiptKey)||'null');}catch{}
    const requested = new URLSearchParams(location.search).get('demo');
    if(!receipt || receipt.nonce !== requested || Date.now()-receipt.created > 1800000 || !Number.isInteger(receipt.total)) {
      location.replace('/checkout/'); return;
    }
    document.getElementById('demo-receipt').innerHTML=`<span>DEMO CONFIRMATION</span><div><span>Sample bag total</span><strong>${money(receipt.total)}</strong></div><div><span>Real amount charged</span><strong>$0.00</strong></div>`;
  }
  updateCount();renderCart();renderCheckout();
  window.addEventListener('storage',event=>{if(event.key===cartKey){updateCount();renderCart();renderCheckout();}});
  window.addEventListener('pageshow',()=>{updateCount();renderCart();renderCheckout();});
})();
