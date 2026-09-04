# BrewBill POS — Production Implementation Contract

Build and verify BrewBill as a production-ready, subscription-based, multi-tenant café/restaurant POS desktop and web application. The implementation must satisfy every requirement below; placeholder screens, hardcoded runtime business rows, and silent local fallbacks are not accepted.

## 1. Required architecture

- Angular standalone feature components for the user interface.
- FastAPI, SQLAlchemy and Alembic for the API and persistence layer.
- PostgreSQL is the only runtime source of truth for catalogue, orders, held bills, KOT, payments, products, ingredient inventory, purchases, expenses, customers and settings.
- Electron is a secure desktop shell with context isolation, validated IPC and receipt-printer integration. It may keep only device/license/security metadata locally; it must not silently substitute local business data when the API is unavailable.
- All API URLs, media base URLs and deployment settings are supplied through environment/runtime configuration so Angular, FastAPI and PostgreSQL can be hosted independently on AWS.
- All API access is authenticated and scoped by `tenant_id`; outlet-owned data is additionally scoped by `outlet_id`.

## 2. Multi-tenant catalogue and outlet stock

- A tenant owns a shared product catalogue. Shared products are visible at every outlet in that tenant.
- An outlet may create additional outlet-only products without exposing them to another outlet.
- Product name, category, prices, tax, variants, image, favourite/KOT flags and availability are catalogue data.
- Product stock is never global. Every outlet has a separate inventory balance for each visible product.
- Selling or voiding at Outlet A must never change Outlet B inventory.
- Product create/edit/activate/deactivate and image-path management are available to authorized users.

## 3. Ingredient inventory

- Maintain tenant-shared ingredient/item definitions and independent outlet balances.
- Seed/importable examples include Arabica Coffee Beans, Milk (Whole), Sugar, French Fries (Frozen), Veg Patty, Tea Leaves, Chocolate Syrup, Paper Cups, Tomato Ketchup and Mayonnaise.
- Each outlet stock row exposes opening stock, stock added, stock used, available stock, low-stock limit, unit and status.
- Authorized users can create and edit inventory items and record Stock In, Stock Out, Damage, Wastage and Manual Correction entries.
- Every adjustment is transactional and auditable; negative stock is rejected unless an explicitly authorized policy permits it.

## 4. POS and held-order workflow

- POS categories/products/variants and prices load from PostgreSQL.
- A cashier can build a cart, change quantities, apply permitted discounts and complete cash/UPI/card/split payments.
- Holding a bill persists the order and all line items in PostgreSQL.
- Held Orders shows searchable/filterable summary cards, a held-bill list and a selected bill preview with item, variant, quantity, tax and totals.
- Reopen/Proceed restores the held cart into POS. Successful payment completes that same held order rather than creating an unrelated duplicate.
- Delete Hold performs an audited cancellation/soft delete; it does not erase financial history.

## 5. Screens and visual contract

- Match the supplied Brew Haven references: dark coffee header, white cards, warm neutral background, fixed operational navigation, compact data tables, green success, amber warning and red destructive actions.
- Required live screens: Login, Admin Dashboard, POS, Held Orders, KOT, Product Management, Ingredient Inventory, Purchases, Expenses, Reports, Customers, Closing and Settings.
- Product Management is a screenshot-style full list with image, category, price, GST, current-outlet stock, favourite, KOT, status and edit actions.
- Inventory includes the screenshot-style metrics, list, low-stock alerts, recent movement panel and quick adjustments.
- Images are loaded through the configured media base path; database rows store relative object keys/paths, not workstation-specific absolute paths.
- Date and time use the configured business timezone (default `Asia/Kolkata`) and the real current clock.

## 6. Security, subscription and reliability

- Argon2/bcrypt-grade password hashing, short-lived JWT access tokens, rotated/revocable refresh tokens and role authorization.
- Ed25519-signed terminal licenses, public-key pinning, secure device storage, trusted server timestamps, clock rollback detection and subscription/terminal enforcement.
- Tenant filters are mandatory for every database read/write, including lookup by ID.
- Order completion, stock deduction, payment creation, KOT creation and held-order conversion run in database transactions.
- Validation errors are explicit. The UI must show API failures and a retry action; it must never display invented fallback rows.

## 7. Seed/import policy

- `backend/app/seed.py` contains loader/orchestration logic only—no embedded catalogue, outlet, user, ingredient or image dictionaries/lists.
- Development bootstrap records live in versioned JSON fixtures and are imported once into PostgreSQL.
- Runtime Angular and FastAPI code reads those records only from PostgreSQL.
- Fixture import is idempotent and creates outlet inventory rows for shared products and shared ingredient definitions.

## 8. Acceptance tests

- Alembic upgrades a clean PostgreSQL database to head and the fixture loader can run twice without duplicates.
- Login, catalogue, product CRUD, ingredient CRUD/adjustment, held bill create/list/preview/cancel/reopen/complete, sale/void and KOT transitions are API-tested.
- A two-outlet test proves shared product visibility and isolated stock balances.
- Angular production build and Python tests pass.
- The Windows installer is rebuilt only after the verified application build.

This file is both the full implementation prompt and the release checklist. A feature is complete only when its API, PostgreSQL persistence, tenant/outlet authorization, Angular binding and automated verification are all present.
