param(
  [string]$PostgresUser = 'postgres',
  [string]$AppUser = 'brewbill',
  [string]$DatabaseName = 'brewbill',
  [string]$HostName = '127.0.0.1',
  [int]$Port = 5432
)

$ErrorActionPreference = 'Stop'
$workspace = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $workspace 'backend'
$psql = 'C:\Program Files\PostgreSQL\17\bin\psql.exe'
$python = Join-Path $backend '.venv\Scripts\python.exe'

if (!(Test-Path -LiteralPath $psql)) { throw 'PostgreSQL 17 psql.exe was not found.' }
if (!(Test-Path -LiteralPath $python)) { throw 'Backend virtual environment was not found.' }

$adminPassword = Read-Host "PostgreSQL password for $PostgresUser" -AsSecureString
$appPassword = Read-Host "New password for BrewBill role $AppUser" -AsSecureString
$adminPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($adminPassword)
$appPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($appPassword)
$bootstrapFile = New-TemporaryFile
try {
  $adminPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($adminPointer)
  $appPlain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($appPointer)
  $env:PGPASSWORD = $adminPlain
  $bootstrapSql = @'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('ALTER ROLE %I WITH LOGIN PASSWORD %L', :'app_user', :'app_password') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'database_name', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'database_name') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'database_name', :'app_user') \gexec
'@
  [IO.File]::WriteAllText($bootstrapFile.FullName, $bootstrapSql)
  & $psql -v ON_ERROR_STOP=1 -v "app_user=$AppUser" -v "app_password=$appPlain" -v "database_name=$DatabaseName" -h $HostName -p $Port -U $PostgresUser -d postgres -f $bootstrapFile.FullName
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL role/database bootstrap failed.' }

  $encodedAdminPassword = [System.Uri]::EscapeDataString($adminPlain)
  $encodedAppPassword = [System.Uri]::EscapeDataString($appPlain)
  $adminDatabaseUrl = "postgresql+psycopg://${PostgresUser}:$encodedAdminPassword@${HostName}:${Port}/${DatabaseName}"
  $databaseUrl = "postgresql+psycopg://${AppUser}:$encodedAppPassword@${HostName}:${Port}/${DatabaseName}"
  $env:DATABASE_URL = $adminDatabaseUrl
  Push-Location $backend
  try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Alembic migration failed.' }
  } finally { Pop-Location }

  $grantSql = @'
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_user') \gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', :'app_user') \gexec
SELECT format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO %I', :'app_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', :'app_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I', :'app_user') \gexec
'@
  [IO.File]::WriteAllText($bootstrapFile.FullName, $grantSql)
  $env:PGPASSWORD = $adminPlain
  & $psql -v ON_ERROR_STOP=1 -v "app_user=$AppUser" -h $HostName -p $Port -U $PostgresUser -d $DatabaseName -f $bootstrapFile.FullName
  if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL runtime grants failed.' }

  $env:PGPASSWORD = $appPlain
  $env:DATABASE_URL = $databaseUrl
  Push-Location $backend
  try {
    & $python -m app.seed
    if ($LASTEXITCODE -ne 0) { throw 'Database seed failed.' }
  } finally { Pop-Location }

  $secretBytes = New-Object byte[] 48
  $randomGenerator = [Security.Cryptography.RandomNumberGenerator]::Create()
  try {
    $randomGenerator.GetBytes($secretBytes)
  } finally {
    $randomGenerator.Dispose()
  }
  $jwtSecret = [Convert]::ToBase64String($secretBytes)
  Push-Location $backend
  try {
    $licenseKeys = (& $python -m app.keygen | ConvertFrom-Json)
    if ($LASTEXITCODE -ne 0) { throw 'License key generation failed.' }
  } finally { Pop-Location }
  $envLines = @(
    "DATABASE_URL=$databaseUrl",
    "JWT_SECRET=$jwtSecret",
    'JWT_ACCESS_EXPIRE_MINUTES=15',
    'JWT_REFRESH_EXPIRE_DAYS=30',
    'OFFLINE_LICENSE_HOURS=48',
    'LICENSE_REFRESH_HOURS=6',
    "LICENSE_PRIVATE_KEY=$($licenseKeys.private_key)",
    "LICENSE_PUBLIC_KEY=$($licenseKeys.public_key)",
    'CORS_ORIGINS=http://localhost:4200,http://127.0.0.1:4200,null'
  )
  [IO.File]::WriteAllLines((Join-Path $backend '.env'), $envLines)
  Write-Host 'BrewBill PostgreSQL role, database, migrations, seed, and backend .env are ready.' -ForegroundColor Green
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($adminPointer)
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($appPointer)
  Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
  Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $bootstrapFile.FullName -Force -ErrorAction SilentlyContinue
}
