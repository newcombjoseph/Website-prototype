# Managing your bonnet store

The running **Django** website now uses database records. Static HTML previews still show the original illustrative collection and do not have a working admin or order database.

## Sign in

Open `/admin/` on the running website. Enter your individual username, password, and the current six-digit code from your authenticator app. A password alone cannot open the management area. Keep the ten recovery codes issued during setup somewhere safe and offline. They work once each in the token field; after a failed attempt the device selector lets you choose recovery codes. Ask your trusted operator to help reset lost access; there is no public MFA-reset endpoint.

If the site is still a private preview, its separate owner gate appears before the admin login. It can be disabled explicitly for a public storefront without disabling admin authentication or MFA.

## Add a bonnet

1. Choose **Products → Add product**. Enter the name, description, category, materials, sizing guidance and washing instructions. Keep it unpublished initially. The URL slug is suggested automatically.
2. In the Pictures section upload JPEG, PNG or WebP images, up to 8 MB and 20 megapixels each. Describe each picture in “Alt text” for accessibility. Use position 0 for the main picture. Images are resized to fit 2000 pixels and re-encoded to WebP with metadata removed.
3. Save the product. Choose **Inventory (sizes and styles) → Add inventory variant**, select the product, and add each size/style combination separately. Each combination needs a unique SKU, dollar price, and available stock. For example: Medium / Classic and Large / Roomy.
4. Return to the product and tick **Published** when its content, pictures and variants are ready. Inactive variants cannot be purchased. Out-of-stock options remain labeled as sold out.

A product can have multiple uploaded photos. The first is its main picture; additional photos appear on its product page. Product pages display the available size/style options with each option's exact price.

To retire products, unpublish them or deactivate variants. Products and variants are not deleted through the admin, preserving references from order history.

## Prices and inventory

Use **Inventory (sizes and styles)** to search by SKU, size, style or product name. Prices use dollars in this form, with cents stored internally. Filter “Stock level” to find low-stock or sold-out items.

Available stock excludes units reserved by pending checkouts. Enter the new available count and a reason, such as “Received 12 new bonnets” or “One damaged item.” Each adjustment records the amount, time and staff member. Reload if stock changed while you were editing; the form refuses to overwrite a concurrent sale.

Products already purchased keep their original names, sizes, styles and prices on the saved order, even after you edit the catalog.

## Orders and history

Use **Orders** to search by order ID, customer email, SKU or tracking number. Filter by date, status or payment mode. Open an order to see its line items, recorded shipping details, tracking and change history. Customer/shipping details are provided by Stripe test checkout; simulated orders do not collect personal information.

Payment amounts, purchased items and financial status cannot be edited directly. Supported actions are:

- Mark selected **paid test orders** shipped. Add tracking before using the action.
- Cancel unpaid **simulated** orders and return reserved stock.
- For Stripe test orders, expire the checkout session in Stripe; its verified expiration notification returns stock. Do not manually return that stock while payment is still possible.

The order history and inventory movements are also available as read-only records. Catalog staff can edit products and inventory; order staff can view orders and use permitted fulfillment actions. Only the owner should manage staff accounts and permissions. Staff actions are attributed to their individual accounts; infrastructure-level database access is outside this application audit trail.

## Test mode and go-live boundary

All orders are explicitly `simulated` or `stripe_test`. No live charges or actual shipping automation is enabled. The current shipping rule is still a demo ($6 below $75, otherwise free) and tax is still zero. Complete actual tax, shipping, refund, transactional email and store policy work before real sales.

Sample bonnet variants are drafts with zero stock. Replace their details and upload actual product photographs before publishing. The original eight products remain placeholders and can be unpublished in the admin.
