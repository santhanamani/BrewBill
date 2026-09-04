# BrewBill POS

BrewBill is a cloud-connected Electron + Angular POS with a tenant-isolated FastAPI/PostgreSQL API. PostgreSQL is the only source of runtime business data. Electron stores only encrypted device/license metadata and printer preferences under `userData`; it never substitutes local products, orders, holds, KOT or inventory.

## Development

Detailed Windows startup instructions are available in [docs/RUN_PROJECT.md](docs/RUN_PROJECT.md).

```powershell
cd D:\Project\BrewBill
npm.cmd run desktop:dev
```

The desktop sign-in and product grid use the cloud API in [runtime-config.json](public/runtime-config.json). The file is intentionally safe to replace per environment and must never contain secrets.

## PostgreSQL migration and development catalogue

For a first-time machine, run the bootstrap script. It securely prompts for the PostgreSQL
administrator password and a new BrewBill database password, creates the role/database,
generates Ed25519 license keys, applies every Alembic migration, seeds data, and writes
`backend/.env` without printing secrets:

```powershell
cd D:\Project\BrewBill
.\scripts\setup-postgres.ps1
```

For later migration/seed runs against an existing BrewBill database, use
`.\scripts\migrate-and-seed.ps1`.

The command imports versioned records from `backend/seed_data`. `backend/app/seed.py`
is an idempotent loader only and contains no embedded catalogue, user, outlet, image,
or ingredient dataset. Runtime screens never read those JSON files; they read PostgreSQL.

It applies Alembic migrations and seeds the development tenant, outlet, terminal, Admin/Cashier accounts, categories, and requested café catalogue. Existing products are not overwritten.

Run the API in a second terminal:

```powershell
cd D:\Project\BrewBill\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --port 8000
```

Development logins are `admin` / `Admin@123` and `cashier` / `Cashier@123`. Change or disable these before any non-development deployment.

## AWS deployment configuration

Host FastAPI behind HTTPS (for example ECS/Fargate or EC2 + ALB), PostgreSQL in RDS, and the Angular build in S3 + CloudFront. Before publishing the frontend, replace the non-secret values in `public/runtime-config.json`:

```json
{
  "apiBaseUrl": "https://api.example.com/api",
  "assetsBaseUrl": "https://cdn.example.com/assets/images",
  "terminalCode": "POS01",
  "tenantName": "Your Tenant Name",
  "environment": "production"
}
```

Product `image_path` values are relative to `assetsBaseUrl`. BrewBill's raster catalogue and login photography live under `public/assets/images/products/photos` and `public/assets/images/brand`. Upload the same folder structure to the configured CDN and store only relative PostgreSQL keys, for example `products/photos/filter-coffee.jpg`.

Set `DATABASE_URL`, `JWT_SECRET`, signing keys, and `CORS_ORIGINS` only as cloud environment
secrets (AWS Secrets Manager or SSM Parameter Store). Never package the private Ed25519 key
inside Electron. [`.env.example`](backend/.env.example) lists required values.

## Validation and packaging

```powershell
npm.cmd run build
npm.cmd run test:license
cd backend
.\.venv\Scripts\python.exe -B -m pytest
npm.cmd run desktop:package
```

The final Windows installer requires Visual Studio **Desktop development with C++** so the encrypted device metadata store can rebuild for Electron. The customer installer includes Electron/Angular and the device-security store only; FastAPI and PostgreSQL are hosted separately.
