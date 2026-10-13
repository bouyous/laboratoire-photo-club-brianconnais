param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$Models,
    [Parameter(Mandatory=$true)][string]$Iscc
)
$ErrorActionPreference = 'Stop'
$repoDir = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$stageDir = Join-Path $PSScriptRoot 'stage'
if (Test-Path -LiteralPath $stageDir) { throw 'Le dossier stage existe déjà : utiliser un checkout neuf ou le mettre de côté avant de reconstruire.' }
Push-Location $repoDir
try {
    $env:CRAFT_FONTS_DIR = '../craft-fonts'
    $env:CRAFT_FONTS_REQUIRED = '1'
    $env:LIGHTCRAFT_REQUIRE_WINRES = '1'
    $env:CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_RUSTFLAGS = '-C target-feature=+crt-static'
    cargo xtask ci
    if ($LASTEXITCODE -ne 0) { throw 'Les contrôles Rust ont échoué' }
    cargo build --release --locked -p lightcraft -p lightcraft-cli --target x86_64-pc-windows-msvc
    if ($LASTEXITCODE -ne 0) { throw 'Compilation Rust en échec' }
    Push-Location ai
    try {
        & $Python -m PyInstaller --noconfirm --clean --distpath dist --workpath build PhotoLabAI.spec
        if ($LASTEXITCODE -ne 0) { throw 'Compilation du moteur IA en échec' }
    } finally { Pop-Location }
    New-Item -ItemType Directory -Path $stageDir | Out-Null
    Copy-Item target/x86_64-pc-windows-msvc/release/lightcraft*.exe $stageDir
    Copy-Item ai/dist/PhotoLabAI (Join-Path $stageDir 'ai') -Recurse
    Get-ChildItem (Join-Path $stageDir 'ai') -Recurse -Filter '*ffmpeg*.dll' | ForEach-Object {
        $resolvedDll = [IO.Path]::GetFullPath($_.FullName)
        if (-not $resolvedDll.StartsWith($stageDir + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'DLL hors du stage' }
        Remove-Item -LiteralPath $resolvedDll
    }
    Copy-Item ai/ai-runtime.json $stageDir
    Copy-Item assets/club/club.ico $stageDir
    Copy-Item assets/club/logo-club.png $stageDir
    Copy-Item LICENSE-MIT,LICENSE-APACHE,NOTICE,README.md $stageDir
    Copy-Item docs/LICENCES-CLUB.md,docs/MODIFICATIONS-CLUB.md,docs/VALIDATION-CLUB.md $stageDir
    Copy-Item (Join-Path $PSScriptRoot 'licences') (Join-Path $stageDir 'licences') -Recurse
    $modelStage = Join-Path $stageDir 'models'
    New-Item -ItemType Directory -Path $modelStage | Out-Null
    $manifest = Get-Content (Join-Path $PSScriptRoot 'models-manifest.json') -Raw | ConvertFrom-Json
    foreach ($model in $manifest) {
        $modelFile = Join-Path $Models $model.file
        if ((Get-FileHash -LiteralPath $modelFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $model.sha256) { throw "Modèle invalide : $($model.file)" }
        Copy-Item -LiteralPath $modelFile -Destination $modelStage
    }
    Copy-Item (Join-Path $PSScriptRoot 'models-manifest.json') (Join-Path $modelStage 'manifest.json')
    & $Iscc "/DStageDir=$stageDir" (Join-Path $PSScriptRoot 'installer.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Création de l’installateur en échec' }
} finally { Pop-Location }
