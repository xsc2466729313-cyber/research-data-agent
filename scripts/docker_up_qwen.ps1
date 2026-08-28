param(
    [Parameter(Mandatory = $true)]
    [string]$CredentialCsv,
    [string]$Model = "qwen3.8-max"
)

$ErrorActionPreference = "Stop"
$resolvedCredential = (Resolve-Path -LiteralPath $CredentialCsv).Path
$rows = Import-Csv -LiteralPath $resolvedCredential -Encoding UTF8
if (-not $rows -or $rows.Count -eq 0) {
    throw "Qwen credential CSV is empty."
}

$columnNames = @($rows[0].PSObject.Properties.Name)
if ($columnNames -notcontains "id") {
    throw "Qwen credential CSV must contain an 'id' column."
}
$valueColumns = @($columnNames | Where-Object { $_ -ne "id" })
if ($valueColumns.Count -eq 0) {
    throw "Qwen credential CSV must contain a value column next to 'id'."
}

$mapping = @{}
foreach ($row in $rows) {
    $value = ""
    foreach ($columnName in $valueColumns) {
        $candidate = [string]$row.$columnName
        if (-not [string]::IsNullOrWhiteSpace($candidate)) {
            $value = $candidate
            break
        }
    }
    $mapping[[string]$row.id] = $value
}

$required = @("apiKey", "openAiCompatible", "workspaceId")
$missing = @($required | Where-Object { -not $mapping.ContainsKey($_) -or [string]::IsNullOrWhiteSpace($mapping[$_]) })
if ($missing.Count -gt 0) {
    throw "Qwen credential CSV is missing fields: $($missing -join ', ')"
}

$env:DASHSCOPE_API_KEY = $mapping.apiKey
$env:QWEN_BASE_URL = $mapping.openAiCompatible.TrimEnd('/')
$env:QWEN_WORKSPACE_ID = $mapping.workspaceId
$env:QWEN_MODEL = $Model

try {
    & (Join-Path $PSScriptRoot "docker_up.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Docker startup failed."
    }
    Write-Host "Qwen research data agent started. Credentials were injected through the current process and were not written to project files."
}
finally {
    Remove-Item Env:DASHSCOPE_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:QWEN_BASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:QWEN_WORKSPACE_ID -ErrorAction SilentlyContinue
    Remove-Item Env:QWEN_MODEL -ErrorAction SilentlyContinue
}
