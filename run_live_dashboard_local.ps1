$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$docsRoot = Join-Path $repoRoot "docs"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
$python = if (Test-Path -LiteralPath $venvPython) { $venvPython } else { "python" }

Push-Location $repoRoot
try {
    & $python -m pa_scanner.cli --tws --live --web docs --no-html
    if ($LASTEXITCODE -ne 0) {
        throw "The live TWS scan failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

function Test-Dashboard([int]$Port) {
    try {
        $probe = "http://127.0.0.1:$Port/data/latest.json"
        $response = Invoke-WebRequest -UseBasicParsing -Uri $probe -TimeoutSec 1
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Test-PortInUse([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        return $task.Wait(250) -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

$port = $null
foreach ($candidate in 8765..8775) {
    if (Test-Dashboard $candidate) {
        $port = $candidate
        break
    }
    if (-not (Test-PortInUse $candidate)) {
        $port = $candidate
        Start-Process -FilePath $python `
            -ArgumentList @("-m", "http.server", "$port", "--bind", "127.0.0.1", "--directory", $docsRoot) `
            -WorkingDirectory $repoRoot `
            -WindowStyle Hidden

        foreach ($attempt in 1..20) {
            Start-Sleep -Milliseconds 250
            if (Test-Dashboard $port) { break }
        }
        break
    }
}

if ($null -eq $port -or -not (Test-Dashboard $port)) {
    throw "Could not start the local dashboard server on ports 8765-8775."
}

Start-Process "http://127.0.0.1:$port/"
