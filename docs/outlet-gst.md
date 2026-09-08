# Outlet GST and shared-master access

Products → Outlet Catalogue Mapping → Edit Mapping now offers:

- Enable GST: off saves an outlet tax override of 0%.
- Use shared master GST rate: on saves null, inheriting future master-rate changes.
- Custom GST: with inheritance off, enter 0–100% with at most two decimal places.

The existing nullable `tax_override` column is reused; no migration is required.
GST remains exclusive/additive to selling price. Disabled mappings use 0%; a
previous custom percentage is not retained separately after saving GST disabled.
When re-enabling, choose the master default or enter the desired custom rate.
Changes affect newly calculated bills, not historical completed invoices.

Both POS and hold calculations resolve null to the current shared-master rate.
Outlet and tenant scoping and validation remain enforced server-side.

Global Product Master in Products has a read-only details action. Mapping new
shared products is available in the Outlet Catalogue Mapping panel. Super Admin
creates/edits global definitions in Administration → Shared Product Master. The
legacy POST /api/products path also requires SUPER_ADMIN, since it can insert a
shared master. Master POST/PATCH already require SUPER_ADMIN. Tenant admins keep
their own outlet mapping controls; cashiers cannot change GST.

Verification: backend/tests/test_catalogue_gst.py covers persistence, invalid
rates, tenant/outlet isolation, role restrictions including the legacy create
path, hold and completed-order tax amounts, and unchanged invoice history.
scripts/test-products-stock.cjs covers GST controls and the read-only action.
