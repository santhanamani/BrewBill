# Products screen and outlet stock

## Cause

`saveMapping()` previously sent price/flags/low-stock limit but omitted current
stock. `OutletProductMappingUpdate` had no stock field, so arbitrary stock fields
would be ignored. The current checkout's dialog only offered opening stock for
new mappings and redirected edits to Inventory; no persisted inline editor existed.

## Single source of truth

Catalogue stock is read from `inventory.available_quantity`, scoped by
`tenant_id`, `outlet_id`, and the mapping's `legacy_product_id`. It is not stored
on the global master or outlet mapping. POS `/api/products` reads the same ledger.
Sales, purchases and reversals use `inventory_service.adjust_stock`.

The Inventory screen manages separate ingredient balances in `ingredient_stocks`.
It is not the source for the mapped finished-product quantity; this fix does not
change ingredient quantities or introduce a duplicate balance.

## Update contract

`PATCH /api/products/catalogue/{mapping_id}` accepts:

```json
{"stock_quantity":"35.000","expected_stock_quantity":"40.000"}
```

Tenant/outlet come from the authenticated user, not request fields. Only outlet
administrators may update mappings. The server locks the outlet's inventory row,
rejects stale expected quantities with 409, and records a `CORRECTION` through
the existing stock movement service. Mapping changes and the movement commit
atomically. Values must be nonnegative with at most three decimal places.
Unknown fields and missing expected quantities are rejected, not silently ignored.

Click a stock value, enter a quantity, then press Enter or click the checkmark.
Escape/cancel discards the draft. The UI waits for server persistence before
publishing the new value, then refetches the catalogue. Failures retain/restore
the previous displayed value; a stale value requires Sync and another edit.
The mapping dialog also supports current-stock corrections.

Category filters and four-row pagination operate independently on both panels.
All visual changes are scoped to the Products component; header/navigation and
other screens remain unchanged.

## Verification

- `python -m pytest backend/tests -q`: API persistence, precision/validation,
  database reconnect, ledger audit, POS reads, same-tenant outlet isolation,
  cross-tenant isolation, permission checks, stale-write conflict/rollback.
- `node --test scripts/test-products-stock.cjs`: component-state tests for
  server-confirmed updates, duplicate submission, restore on error, refetch failure,
  filters/pagination, mapping modal payload, and toggle persistence.
- `npm.cmd run build`: Angular template/type/style compilation.

The isolated backend tests use a file-backed SQLite database; they do not change
live tenant data. Live PostgreSQL validation on 6 September 2026 changed RS Puram
Cheese Sandwich from 40.000 to 35.000 through the UI and confirmed its -5.000 audit
movement and the unchanged Chennai balance of 40.000 using a new DB connection.
