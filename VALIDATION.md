# Validation — October 23, 2026

## Automated Django checks

`python scripts/verify.py` passes eight test groups. `manage.py check --deploy` reports no issues, with warnings treated as failures. Tests use HTTPS requests and real CSRF checks; Stripe SDK calls are mocked, not live.

- Home, catalog, all eight product routes, cart, checkout, and policy pages render. Unknown products return 404.
- Cart ignores supplied prices and calculates totals from catalog cents. Two totes plus one mug total $80 with free demo shipping; one tote plus one mug total $58 including $6 shipping.
- Updates, removal, empty cart, and quantity/unknown-product rejection work. Values outside 1–9 and noninteger values are rejected. GET cannot mutate the cart; missing CSRF receives 403.
- Cancellation retains the cart. Forged completion tokens fail. A valid simulated completion clears the matching cart and cannot be replayed through the normal session.
- Secure cookies, HTTPS redirection, invalid-host rejection, HSTS, CSP, no-store, frame protection, and no-index headers are checked.
- Owner access fails closed without credentials. Wrong credentials and unauthenticated static requests fail; authenticated requests can load collected CSS with the correct content type.
- Stripe test sessions use server prices and redirect only to Stripe's hosted URL. An unpaid return cannot complete. A live response is rejected. Completion verifies the expected session and total.

`node --check shop/static/shop/js/store.js` passes. `collectstatic` emits compressed, hashed assets; the preview export renders 16 routes.

## Browser walkthrough

Verified in the managed browser against the same static artifact prepared for the owner-private Sites deployment:

- Homepage CSS and generated hero render. Catalog images load.
- Category filtering reduces the catalog to the correct products. Search combines with filters. Unknown searches display a helpful empty state.
- Price ascending sort puts the $16 tea towel first and $32 bottle last.
- Product details display descriptions, quantity input, and care/shipping disclosures.
- Adding two totes and one mug yields three items and $80 free-shipping total.
- Decreasing tote quantity survives reload, produces $52 subtotal and $58 total, and updates the free-shipping message.
- Removing the mug yields $34 including shipping.
- Checkout cancellation preserves the tote. Resuming and simulating checkout yields a $34 demo confirmation with $0 charged, then an empty bag.

The local HTTP preview initially exposed an unsupported `crypto.randomUUID()` call. The preview now generates its demo reference with `crypto.getRandomValues()`, and successful completion was rechecked.

## Scope and verification limits

The Sites audience is owner-only, with no group, other-viewer, or external-visitor grants. No public access change was requested or made. Native deployment success verifies publication and URL. The managed browser cannot reach deployed Sites origins, so browser QA uses the internal preview.

The hosted URL is an interactive preview rendered from Django templates, not a deployed Python runtime. The actual Django server is built and tested; deployment to AWS or another Python host requires a connected account and an authorized host. No AWS infrastructure was provisioned, no domain registered, and no service purchased.

No real Stripe sandbox key was available, so the deployed experience uses a clearly labeled simulation. Real Stripe-hosted sandbox operation is covered by mocked integration tests only. No real transactions, orders, customer addresses, inventory reservations, tax calculations, or fulfillment are implemented.
