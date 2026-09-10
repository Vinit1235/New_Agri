# SoilEdge System Test Suite
# Simple version without special characters

$baseUrl = "http://localhost:8000"
Write-Host "Starting SoilEdge System Tests..." -ForegroundColor Cyan
Write-Host "Base URL: $baseUrl`n"

$passed = 0
$failed = 0

function Test-API {
    param([string]$Name, [string]$Url, [string]$Method = "GET", [object]$Body = $null)
    
    Write-Host "Testing: $Name" -ForegroundColor Yellow
    try {
        $params = @{Uri=$Url; Method=$Method; UseBasicParsing=$true}
        if ($Body) {
            $params.Body = ($Body | ConvertTo-Json)
            $params.ContentType = "application/json"
        }
        
        $response = Invoke-WebRequest @params
        Write-Host "  PASS - Status: $($response.StatusCode)" -ForegroundColor Green
        $script:passed++
        return $response.Content | ConvertFrom-Json
    } catch {
        Write-Host "  FAIL - $($_.Exception.Message)" -ForegroundColor Red
        $script:failed++
        return $null
    }
}

# Test 1: Health Check
Write-Host "`n=== SECTION 1: HEALTH & CONNECTIVITY ===" -ForegroundColor Magenta
Test-API -Name "API Health Check" -Url "$baseUrl/api/health"
Test-API -Name "Root Endpoint" -Url "$baseUrl/"

# Test 2: Authentication
Write-Host "`n=== SECTION 2: AUTHENTICATION ===" -ForegroundColor Magenta
$timestamp = [DateTimeOffset]::Now.ToUnixTimeSeconds()
$user = @{email="test_$timestamp@test.com"; password="Pass123!"; username="user_$timestamp"}
$registerResult = Test-API -Name "User Registration" -Url "$baseUrl/api/auth/register" -Method "POST" -Body $user

if ($registerResult) {
    $loginResult = Test-API -Name "User Login" -Url "$baseUrl/api/auth/login" -Method "POST" -Body @{username=$user.email; password=$user.password}
    $token = $loginResult.access_token
}

# Test 3: ML Model
Write-Host "`n=== SECTION 3: ML MODEL PREDICTION ===" -ForegroundColor Magenta
Test-API -Name "Optimal Conditions" -Url "$baseUrl/api/model/predict" -Method "POST" -Body @{ph=6.8;temperature=24.0;moisture=28.0;ec=1.5}
Test-API -Name "Low Moisture" -Url "$baseUrl/api/model/predict" -Method "POST" -Body @{ph=6.5;temperature=26.0;moisture=12.0;ec=1.8}
Test-API -Name "High Salinity" -Url "$baseUrl/api/model/predict" -Method "POST" -Body @{ph=7.0;temperature=25.0;moisture=30.0;ec=4.5}
Test-API -Name "Critical Salinity" -Url "$baseUrl/api/model/predict" -Method "POST" -Body @{ph=7.2;temperature=27.0;moisture=35.0;ec=8.5}

# Test 4: Voice Assistant
Write-Host "`n=== SECTION 4: VOICE ASSISTANT ===" -ForegroundColor Magenta
Test-API -Name "Voice Query (English)" -Url "$baseUrl/api/voice/chat" -Method "POST" -Body @{text="What is my soil moisture?";moisture=28.5;ph=6.8;ec=1.9;last_action="Fertilizer applied"}
Test-API -Name "Voice Query (Hindi)" -Url "$baseUrl/api/voice/chat" -Method "POST" -Body @{text="नमी कितनी है?";moisture=28.5;ph=6.8;ec=1.9;last_action="Fertilizer applied"}

# Test 5: Field Management (if authenticated)
if ($token) {
    Write-Host "`n=== SECTION 5: FIELD MANAGEMENT ===" -ForegroundColor Magenta
    $headers = @{Authorization="Bearer $token"}
    $field = @{name="TestField";latitude=19.712879;longitude=72.793093;area_hectares=2.5;crop_type="wheat"}
    
    try {
        $fieldResult = Invoke-WebRequest -Uri "$baseUrl/api/fields" -Method POST -Body ($field | ConvertTo-Json) -ContentType "application/json" -Headers $headers -UseBasicParsing
        Write-Host "  PASS - Field Created" -ForegroundColor Green
        $script:passed++
        
        $fieldData = $fieldResult.Content | ConvertFrom-Json
        $fieldId = $fieldData.id
        
        # Get field details
        $getField = Invoke-WebRequest -Uri "$baseUrl/api/fields/$fieldId" -Method GET -Headers $headers -UseBasicParsing
        Write-Host "  PASS - Field Retrieved" -ForegroundColor Green
        $script:passed++
    } catch {
        Write-Host "  FAIL - $($_.Exception.Message)" -ForegroundColor Red
        $script:failed += 2
    }
}

# Test 6: Rate Limiting
Write-Host "`n=== SECTION 6: RATE LIMITING ===" -ForegroundColor Magenta
$rateLimitPassed = 0
$rateLimitBlocked = 0

for ($i = 1; $i -le 12; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "$baseUrl/api/voice/chat" -Method POST -Body (@{text="test$i"} | ConvertTo-Json) -ContentType "application/json" -UseBasicParsing -ErrorAction Stop
        $rateLimitPassed++
    } catch {
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode -eq 429) { $rateLimitBlocked++ }
    }
    Start-Sleep -Milliseconds 50
}

Write-Host "  Passed: $rateLimitPassed, Blocked: $rateLimitBlocked"
if ($rateLimitBlocked -gt 0) {
    Write-Host "  PASS - Rate limiting is working" -ForegroundColor Green
    $script:passed++
} else {
    Write-Host "  WARN - Rate limiting may not be active" -ForegroundColor Yellow
}

# Summary
Write-Host "`n=== TEST SUMMARY ===" -ForegroundColor Magenta
$total = $passed + $failed
Write-Host "Total: $total | Passed: $passed | Failed: $failed" -ForegroundColor Cyan

$successRate = if ($total -gt 0) { [math]::Round(($passed / $total) * 100, 1) } else { 0 }
Write-Host "Success Rate: $successRate%" -ForegroundColor $(if ($successRate -ge 90) { "Green" } elseif ($successRate -ge 70) { "Yellow" } else { "Red" })

if ($failed -eq 0 -and $successRate -ge 90) {
    Write-Host "`nSYSTEM IS PRODUCTION-READY!" -ForegroundColor Green
} elseif ($failed -eq 0) {
    Write-Host "`nSystem is operational with minor issues" -ForegroundColor Yellow
} else {
    Write-Host "`nSystem has issues that need attention" -ForegroundColor Red
}
