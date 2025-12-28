# scripts/demo.ps1
# Demo script for the Experimentation API (Windows PowerShell)
# Requires: PowerShell 5+ (or pwsh), API running on localhost:8000

$ErrorActionPreference = "Stop"

$BASE = $env:BASE_URL
if (-not $BASE) { $BASE = "http://localhost:8000" }

$TOKEN = $env:API_TOKEN
if (-not $TOKEN) { $TOKEN = "dev-token-1" }

$headers = @{ Authorization = "Bearer $TOKEN" }

Write-Host "Base URL: $BASE"
Write-Host "Token:    $TOKEN"
Write-Host ""

# 1) Create experiment
$payload = @{
  name = "CTA Test Demo"
  description = "Demo experiment created by scripts/demo.ps1"
  variants = @(
    @{ key = "control"; allocation_percent = 50; metadata = @{ note = "baseline" } }
    @{ key = "treatment"; allocation_percent = 50; metadata = @{ note = "new CTA" } }
  )
} | ConvertTo-Json -Depth 10

Write-Host "==> Creating experiment..."
$exp = Invoke-RestMethod -Method Post -Uri "$BASE/experiments" -Headers $headers -ContentType "application/json" -Body $payload
$exp_id = $exp.id
Write-Host "Created experiment_id: $exp_id"
Write-Host ""

# 2) Idempotent assignment (same user, multiple calls -> same variant)
$user = "user_demo_123"
Write-Host "==> Getting assignment for $user (first call)..."
$a1 = Invoke-RestMethod -Method Get -Uri "$BASE/experiments/$exp_id/assignment/$user" -Headers $headers
Write-Host ("Assigned variant: {0} ({1}) at {2}" -f $a1.variant_key, $a1.variant_id, $a1.assigned_at)

Write-Host "==> Getting assignment for $user (second call, should match)..."
$a2 = Invoke-RestMethod -Method Get -Uri "$BASE/experiments/$exp_id/assignment/$user" -Headers $headers
Write-Host ("Assigned variant: {0} ({1}) at {2}" -f $a2.variant_key, $a2.variant_id, $a2.assigned_at)

if ($a1.variant_id -ne $a2.variant_id) {
  throw "Idempotency failed: variant_id changed between calls!"
}
Write-Host "Idempotency OK"
Write-Host ""

# 3) Create a few assignments for distribution (optional)
Write-Host "==> Creating a few more assignments..."
$users = @("userA_demo", "userB_demo", "userC_demo", "userD_demo")
foreach ($u in $users) {
  $ax = Invoke-RestMethod -Method Get -Uri "$BASE/experiments/$exp_id/assignment/$u" -Headers $headers
  Write-Host ("  {0} -> {1}" -f $u, $ax.variant_key)
}
Write-Host ""

# 4) Record events
# Note: This API may require the user to have an assignment before posting events.
# We already assigned user_demo_123 above.
$now = (Get-Date).ToUniversalTime().ToString("o")

Write-Host "==> Recording events..."
$event1 = @{
  experiment_id = $exp_id
  user_id = $user
  type = "click"
  timestamp = $now
  properties = @{ button = "cta"; page = "landing" }
} | ConvertTo-Json -Depth 10

$event2 = @{
  experiment_id = $exp_id
  user_id = $user
  type = "purchase"
  timestamp = $now
  properties = @{ amount = 49.99; currency = "USD" }
} | ConvertTo-Json -Depth 10

$e1 = Invoke-RestMethod -Method Post -Uri "$BASE/events" -Headers $headers -ContentType "application/json" -Body $event1
Write-Host ("  click event id: {0}" -f $e1.id)

$e2 = Invoke-RestMethod -Method Post -Uri "$BASE/events" -Headers $headers -ContentType "application/json" -Body $event2
Write-Host ("  purchase event id: {0}" -f $e2.id)

Write-Host ""

# 5) Results endpoint
Write-Host "==> Fetching results (event_type=click)..."
$res_click = Invoke-RestMethod -Method Get -Uri "$BASE/experiments/$exp_id/results?event_type=click" -Headers $headers
$res_click | ConvertTo-Json -Depth 20
Write-Host ""

Write-Host "==> Fetching results (event_type=purchase)..."
$res_purchase = Invoke-RestMethod -Method Get -Uri "$BASE/experiments/$exp_id/results?event_type=purchase" -Headers $headers
$res_purchase | ConvertTo-Json -Depth 20
Write-Host ""

Write-Host "Done."
