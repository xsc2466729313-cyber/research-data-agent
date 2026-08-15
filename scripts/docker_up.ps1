[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$workspacePath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$drive = @("Z:", "Y:", "X:") |
    Where-Object { -not (Test-Path -LiteralPath "$_\") } |
    Select-Object -First 1

if (-not $drive) {
    throw "No temporary drive letter is available for the Docker build."
}

$mapped = $false
try {
    & subst.exe $drive $workspacePath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to map $drive to the workspace."
    }
    $mapped = $true

    Push-Location -LiteralPath "$drive\"
    try {
        & docker compose build
        if ($LASTEXITCODE -ne 0) {
            throw "Docker image build failed."
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($mapped) {
        & subst.exe $drive /D
    }
}

Push-Location -LiteralPath $workspacePath
try {
    & docker compose up -d
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose startup failed."
    }
    & docker compose ps
}
finally {
    Pop-Location
}

