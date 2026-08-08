param(
  [Parameter(Mandatory = $true)]
  [string]$InstallerPath,
  [switch]$RequireSignature
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$installer = (Resolve-Path $InstallerPath).Path
if (-not (Test-Path $installer -PathType Leaf)) {
  throw "Windows installer was not found: $InstallerPath"
}
if ((Get-Item $installer).Length -ge 2GB) {
  throw "The one-file Windows download exceeds GitHub's 2 GiB release-asset limit"
}

$signature = Get-AuthenticodeSignature -FilePath $installer
if ($RequireSignature -and $signature.Status -ne "Valid") {
  throw "Sale installer signature is not valid: $($signature.Status)"
}

$installRoot = Join-Path $env:RUNNER_TEMP "jarvis-v4-clean-install-$PID"
$appDataRoot = Join-Path $env:APPDATA "jarvis-v4-desktop"
$first = $null
$second = $null

try {
  if (Test-Path $installRoot) { Remove-Item $installRoot -Recurse -Force }
  $install = Start-Process -FilePath $installer -ArgumentList @("/S", "/D=$installRoot") -Wait -PassThru
  if ($install.ExitCode -ne 0) { throw "Silent installation failed with exit code $($install.ExitCode)" }

  $appExe = Join-Path $installRoot "JARVIS v4.exe"
  $resources = Join-Path $installRoot "resources"
  $required = @(
    $appExe,
    (Join-Path $resources "backend\jarvis-server\jarvis-server.exe"),
    (Join-Path $resources "speech-runtime\whisper-server.exe"),
    (Join-Path $resources "speech-runtime\ggml-large-v3-turbo-q8_0.bin"),
    (Join-Path $resources "speech-runtime\ggml-silero-v6.2.0.bin"),
    (Join-Path $resources "voice-pack\bin\jarvis-voice-engine.exe"),
    (Join-Path $resources "voice-pack\profile-de.npy"),
    (Join-Path $resources "voice-pack\profile-en.npy"),
    (Join-Path $resources "voice-pack\voice-pack.json")
  )
  foreach ($target in $required) {
    if (-not (Test-Path $target -PathType Leaf) -or (Get-Item $target).Length -eq 0) {
      throw "Installed Windows component is missing or empty: $target"
    }
  }

  $voiceManifest = Get-Content (Join-Path $resources "voice-pack\voice-pack.json") -Raw | ConvertFrom-Json
  if ($voiceManifest.platform -ne "win32" -or $voiceManifest.arch -ne "x64") {
    throw "Installed voice pack is not the Windows x64 build"
  }
  if (@($voiceManifest.accelerators).Count -ne 1 -or $voiceManifest.accelerators[0] -ne "cpu") {
    throw "Installed voice pack must be CPU-only"
  }
  if (-not (@($voiceManifest.languages) -contains "de") -or -not (@($voiceManifest.languages) -contains "en")) {
    throw "Installed voice pack must contain German and English"
  }

  # A sale installer must also be safe to run over an existing copy. Keep a
  # customer-data marker, run the exact installer again, and require both the
  # installed application and private data to survive the repair/upgrade.
  New-Item -ItemType Directory -Path $appDataRoot -Force | Out-Null
  $upgradeMarker = Join-Path $appDataRoot "upgrade-smoke-marker.txt"
  Set-Content -Path $upgradeMarker -Value "must survive an in-place upgrade"
  $upgrade = Start-Process -FilePath $installer -ArgumentList @("/S", "/D=$installRoot") -Wait -PassThru
  if ($upgrade.ExitCode -ne 0) { throw "Silent in-place upgrade failed with exit code $($upgrade.ExitCode)" }
  if (-not (Test-Path $appExe -PathType Leaf)) { throw "In-place upgrade removed the installed application" }
  if (-not (Test-Path $upgradeMarker -PathType Leaf)) { throw "In-place upgrade removed private customer data" }

  $first = Start-Process -FilePath $appExe -PassThru
  $deadline = (Get-Date).AddSeconds(75)
  $backend = $null
  while ((Get-Date) -lt $deadline) {
    if ($first.HasExited) { throw "Installed JARVIS app exited during first launch" }
    $backend = Get-CimInstance Win32_Process -Filter "Name = 'jarvis-server.exe'" |
      Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($installRoot, [System.StringComparison]::OrdinalIgnoreCase) } |
      Select-Object -First 1
    if ($backend) { break }
    Start-Sleep -Milliseconds 500
  }
  if (-not $backend) { throw "Installed JARVIS backend did not start" }

  if ($backend.CommandLine -notmatch '--port\s+(\d+)') { throw "Installed backend did not expose its local port" }
  $port = [int]$Matches[1]
  $health = Invoke-RestMethod -Uri "http://127.0.0.1:$port/api/health" -TimeoutSec 10
  if ($health.status -ne "online" -or $health.name -ne "JARVIS v4") {
    throw "Installed backend health check failed"
  }

  # A second launch must hand off to the existing window and exit. This catches
  # the duplicate-tab/duplicate-backend regression seen in earlier Windows builds.
  $second = Start-Process -FilePath $appExe -PassThru
  if (-not $second.WaitForExit(15000)) {
    throw "A second JARVIS launch stayed open instead of reusing the first app"
  }
  if ($first.HasExited) { throw "The original JARVIS instance closed during second-launch handoff" }

  Set-Content -Path (Join-Path $appDataRoot "uninstall-smoke-marker.txt") -Value "temporary CI data"
}
finally {
  if ($second -and -not $second.HasExited) { Stop-Process -Id $second.Id -Force -ErrorAction SilentlyContinue }
  if ($first -and -not $first.HasExited) {
    & taskkill.exe /PID $first.Id /T /F 2>$null | Out-Null
  }

  $uninstaller = Get-ChildItem $installRoot -Filter "Uninstall*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($uninstaller) {
    $remove = Start-Process -FilePath $uninstaller.FullName -ArgumentList "/S" -Wait -PassThru
    if ($remove.ExitCode -ne 0) { throw "Silent uninstall failed with exit code $($remove.ExitCode)" }
  }
}

if (Test-Path $installRoot) { throw "Windows uninstall left the application directory behind" }
if (Test-Path $appDataRoot) { throw "Windows uninstall left private application data behind" }

Write-Host "Windows installer smoke test passed: signature=$($signature.Status), install, upgrade, backend, single instance, voice, CPU STT, uninstall"
