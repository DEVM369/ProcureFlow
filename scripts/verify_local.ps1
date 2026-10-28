param(
    [string]$Python = "python",
    [switch]$WithMcp,
    [switch]$WithAgentBoundary,
    [switch]$WithDeepAgentsGraph,
    [switch]$WithHITLGraph
)

$ErrorActionPreference = "Stop"
$project = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path -LiteralPath (Join-Path $project "demo\server.py") -PathType Leaf)) {
    throw "STOP: This script must remain inside the repository"
}

Push-Location $project
try {
    & $Python -B -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "STOP: Offline unit tests failed"
    }
    Write-Host "OFFLINE_TESTS=PASS"

    & $Python -B scripts/audit_release.py
    if ($LASTEXITCODE -ne 0) {
        throw "STOP: Release audit requires manual review"
    }
    Write-Host "SOURCE_SCAN=PASS"

    if ($WithMcp) {
        Write-Host "===== READ-ONLY MCP -> MOCK ERP ====="
        & $Python -B scripts/verify_mcp_read_only.py
        if ($LASTEXITCODE -ne 0) {
            throw "STOP: MCP read-only smoke failed"
        }
        Write-Host "REAL_MCP_READ_ONLY=PASS"
    }

    if ($WithAgentBoundary) {
        Write-Host "===== REAL AGENT MIDDLEWARE -> MCP MOCK ====="
        & $Python -B scripts/verify_agent_mcp_boundary.py
        if ($LASTEXITCODE -ne 0) {
            throw "STOP: Safe Agent/MCP boundary contract failed"
        }
        Write-Host "SAFE_AGENT_MCP_BOUNDARY=PASS"
    }

    if ($WithDeepAgentsGraph) {
        Write-Host "===== REAL DEEPAGENTS GRAPH -> LOCAL MCP -> MOCK ERP ====="
        & $Python -B scripts/verify_deepagents_graph.py
        if ($LASTEXITCODE -ne 0) {
            throw "STOP: Real DeepAgents graph verification failed"
        }
        Write-Host "SAFE_DEEPAGENTS_GRAPH=PASS"
    }

    if ($WithHITLGraph) {
        Write-Host "===== REAL DEEPAGENTS HITL -> RAM-ONLY FAKE ERP ====="
        & $Python -B scripts/verify_deepagents_hitl.py
        if ($LASTEXITCODE -ne 0) {
            throw "STOP: Real DeepAgents HITL verification failed"
        }
        Write-Host "SAFE_HITL_GRAPH=PASS"
    }

    Write-Host "PROCUREFLOW_VERIFY=PASS"
}
finally {
    Pop-Location
}
