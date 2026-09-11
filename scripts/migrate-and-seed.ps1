param(
  [string]$DatabaseUser = 'postgres',
  [string]$AppUser = 'brewbill',
  [string]$DatabaseName = 'brewbill',
  [string]$DatabaseHost = '127.0.0.1',
  [int]$DatabasePort = 5432,
  [switch]$SkipSeed
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
$psql = 'C:\Program Files\PostgreSQL\17\bin\psql.exe'

if (-not (Test-Path $python)) {
  throw 'Backend virtual environment is missing. Run the initial setup first.'
}
if (-not (Test-Path $psql)) {
  throw 'PostgreSQL 17 psql.exe was not found.'
}

$securePassword = Read-Host "PostgreSQL password for $DatabaseUser" -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
  $plainPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
  $encodedPassword = [Uri]::EscapeDataString($plainPassword)
  $env:PGPASSWORD = $plainPassword
  $env:DATABASE_URL = "postgresql+psycopg://${DatabaseUser}:${encodedPassword}@${DatabaseHost}:${DatabasePort}/${DatabaseName}"
  Push-Location $backendRoot
  & $python -m alembic upgrade head
  if ($LASTEXITCODE -ne 0) { throw 'Alembic migration failed.' }
  if (-not $SkipSeed) {
    & $python -m app.seed
    if ($LASTEXITCODE -ne 0) { throw 'Database seed failed.' }
  }

  $grantFile = New-TemporaryFile
  try {
    $grantSql = @'
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_user') \gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', :'app_user') \gexec
SELECT format('GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO %I', :'app_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', :'app_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I', :'app_user') \gexec
'@
    [IO.File]::WriteAllText($grantFile.FullName, $grantSql)
    & $psql -v ON_ERROR_STOP=1 -v "app_user=$AppUser" -h $DatabaseHost -p $DatabasePort -U $DatabaseUser -d $DatabaseName -f $grantFile.FullName
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL runtime grants failed.' }
  } finally {
    Remove-Item -LiteralPath $grantFile.FullName -Force -ErrorAction SilentlyContinue
  }
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
  Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
  Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
  Pop-Location
}
