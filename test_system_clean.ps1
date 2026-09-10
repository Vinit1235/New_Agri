# ============================================
# SoilEdge System Comprehensive Test Suite
# ============================================

$ErrorActionPreference = "Continue"
$baseUrl = "http://localhost:8000"
$testResults = @()

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url,
        [string]$Method = "GET",
        [hashtable]$Body = $null,
        [hashtable]$Headers = $null,
        [string]$ExpectedStatus = "200"
    )
    
    Write-Host "`n=== Testing: $Name ===" -ForegroundColor Cyan
    Write-Host "URL: $Method $Url"
    
    try {
        $params = @{
            Uri = $Url
            Method = $Method
            UseBasicParsing = $true
        }
        
        if ($Headers) {
            $params.Headers = $Headers
        }
        
        if ($Body) {
            $params.Body = ($Body | ConvertTo-Json)
            $params.ContentType = "application/json"
        }
        
        $response = Invoke-WebRequest @params -ErrorAction Stop
        $statusCode = $response.StatusCode
        $content = $response.Content | ConvertFrom-Json
        
        if ($statusCode -eq $ExpectedStatus) {
            Write-Host "âœ… PASS - Status: $statusCode" -ForegroundColor Green
            $script:testResults += @{
                Name = $Name
                Status = "PASS"
                StatusCode = $statusCode
                Response = $content
            }
            return $content
        } else {
            Write-Host "âš ï¸  WARN - Expected $ExpectedStatus, Got: $statusCode" -ForegroundColor Yellow
            $script:testResults += @{
                Name = $Name
                Status = "WARN"
                StatusCode = $statusCode
                Response = $content
            }
            return $content
        }
        
    } catch {
        Write-Host "âŒ FAIL - $($_.Exception.Message)" -ForegroundColor Red
        $script:testResults += @{
            Name = $Name
            Status = "FAIL"
            Error = $_.Exception.Message
        }
        return $null
    }
}

Write-Host @"

â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
â•‘                 SOILEDGE SYSTEM TEST SUITE                    â•‘
â•‘                      September 2, 2026                        â•‘
â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

"@ -ForegroundColor Magenta

# ============================================
# 1. HEALTH & BASIC CONNECTIVITY
# ============================================
Write-Host "`n[1] SECTION 1: HEALTH & CONNECTIVITY" -ForegroundColor Yellow

Test-Endpoint `
    -Name "API Health Check" `
    -Url "$baseUrl/api/health" `
    -Method "GET"

Test-Endpoint `
    -Name "Root Endpoint" `
    -Url "$baseUrl/" `
    -Method "GET"

# ============================================
# 2. AUTHENTICATION TESTS
# ============================================
Write-Host "`n[2] SECTION 2: AUTHENTICATION" -ForegroundColor Yellow

# Register new test user
$timestamp = [DateTimeOffset]::Now.ToUnixTimeSeconds()
$testUser = @{
    email = "test_$timestamp@soiledge.test"
    password = "TestPass123!"
    username = "testuser_$timestamp"
}

$registerResult = Test-Endpoint `
    -Name "User Registration" `
    -Url "$baseUrl/api/auth/register" `
    -Method "POST" `
    -Body $testUser

# Login
$loginBody = "username=$($testUser.email)&password=$($testUser.password)"
$loginResult = Test-Endpoint `
    -Name "User Login" `
    -Url "$baseUrl/api/auth/login" `
    -Method "POST" `
    -Body @{
        username = $testUser.email
        password = $testUser.password
    }

$token = $null
if ($loginResult -and $loginResult.access_token) {
    $token = $loginResult.access_token
    Write-Host "   Token obtained: $($token.Substring(0,20))..." -ForegroundColor Gray
}

# ============================================
# 3. FIELD MANAGEMENT (WITH AUTH)
# ============================================
Write-Host "`n[3] SECTION 3: FIELD MANAGEMENT" -ForegroundColor Yellow

if ($token) {
    $authHeaders = @{
        "Authorization" = "Bearer $token"
    }
    
    # Create field
    $fieldData = @{
        name = "Test Field $(Get-Date -Format 'HHmmss')"
        latitude = 19.712879
        longitude = 72.793093
        area_hectares = 2.5
        crop_type = "wheat"
    }
    
    $fieldResult = Test-Endpoint `
        -Name "Create Field" `
        -Url "$baseUrl/api/fields" `
        -Method "POST" `
        -Body $fieldData `
        -Headers $authHeaders
    
    # List fields
    Test-Endpoint `
        -Name "List User Fields" `
        -Url "$baseUrl/api/fields" `
        -Method "GET" `
        -Headers $authHeaders
    
    if ($fieldResult -and $fieldResult.id) {
        $fieldId = $fieldResult.id
        
        # Get specific field
        Test-Endpoint `
            -Name "Get Field Details" `
            -Url "$baseUrl/api/fields/$fieldId" `
            -Method "GET" `
            -Headers $authHeaders
    }
} else {
    Write-Host "âš ï¸  Skipping field tests - no auth token" -ForegroundColor Yellow
}

# ============================================
# 4. DEVICE REGISTRATION
# ============================================
Write-Host "`n[4] SECTION 4: DEVICE MANAGEMENT" -ForegroundColor Yellow

if ($token -and $fieldId) {
    $deviceData = @{
        device_id = "TEST_ESP32_$(Get-Date -Format 'HHmmss')"
        field_id = $fieldId
        device_type = "esp32"
    }
    
    $deviceResult = Test-Endpoint `
        -Name "Register Device" `
        -Url "$baseUrl/api/devices/register" `
        -Method "POST" `
        -Body $deviceData `
        -Headers $authHeaders
    
    if ($deviceResult -and $deviceResult.device_token) {
        Write-Host "   Device Token: $($deviceResult.device_token.Substring(0,20))..." -ForegroundColor Gray
    }
}

# ============================================
# 5. TELEMETRY & SENSOR DATA
# ============================================
Write-Host "`n[5] SECTION 5: TELEMETRY & SENSOR DATA" -ForegroundColor Yellow

if ($token -and $fieldId) {
    # Simulate telemetry post
    $telemetryData = @{
        device_id = "TEST_ESP32_$(Get-Date -Format 'HHmmss')"
        moisture = 28.5
        temperature = 24.3
        ph = 6.8
        ec = 1.9
        action = 0
        action_name = "monitor"
        pump = $false
        fertilizer = $true
        timestamp = (Get-Date -Format "o")
    }
    
    Test-Endpoint `
        -Name "Post Telemetry Data" `
        -Url "$baseUrl/api/telemetry" `
        -Method "POST" `
        -Body $telemetryData `
        -Headers $authHeaders
    
    # Get latest readings
    Test-Endpoint `
        -Name "Get Latest Sensor Readings" `
        -Url "$baseUrl/api/fields/$fieldId/readings/latest" `
        -Method "GET" `
        -Headers $authHeaders
    
    # Get historical data
    Test-Endpoint `
        -Name "Get Historical Readings (24h)" `
        -Url "$baseUrl/api/data/history/field/$fieldId" `
        -Method "GET" `
        -Headers $authHeaders
}

# ============================================
# 6. ML MODEL PREDICTION
# ============================================
Write-Host "`n[6] SECTION 6: ML MODEL PREDICTION" -ForegroundColor Yellow

$predictionData = @{
    ph = 6.8
    temperature = 24.5
    moisture = 28.0
    ec = 1.9
}

Test-Endpoint `
    -Name "ML Prediction (Optimal)" `
    -Url "$baseUrl/api/model/predict" `
    -Method "POST" `
    -Body $predictionData

# Test high salinity
$highSaltData = @{
    ph = 7.2
    temperature = 26.0
    moisture = 35.0
    ec = 5.5
}

Test-Endpoint `
    -Name "ML Prediction (High Salinity)" `
    -Url "$baseUrl/api/model/predict" `
    -Method "POST" `
    -Body $highSaltData

# Test low moisture
$dryData = @{
    ph = 6.5
    temperature = 28.0
    moisture = 12.0
    ec = 2.1
}

Test-Endpoint `
    -Name "ML Prediction (Low Moisture)" `
    -Url "$baseUrl/api/model/predict" `
    -Method "POST" `
    -Body $dryData

# ============================================
# 7. VOICE ASSISTANT API
# ============================================
Write-Host "`n[7] SECTION 7: VOICE ASSISTANT" -ForegroundColor Yellow

$voiceData = @{
    text = "What is my soil moisture level?"
    moisture = 28.5
    ph = 6.8
    ec = 1.9
    last_action = "Fertilizer applied"
}

Test-Endpoint `
    -Name "Voice Assistant Query" `
    -Url "$baseUrl/api/voice/chat" `
    -Method "POST" `
    -Body $voiceData

# Test multilingual (Hindi)
$voiceHindi = @{
    text = "à¤¨à¤®à¥€ à¤•à¤¿à¤¤à¤¨à¥€ à¤¹à¥ˆ?"
    moisture = 28.5
    ph = 6.8
    ec = 1.9
    last_action = "Fertilizer applied"
}

Test-Endpoint `
    -Name "Voice Assistant (Hindi)" `
    -Url "$baseUrl/api/voice/chat" `
    -Method "POST" `
    -Body $voiceHindi

# ============================================
# 8. RATE LIMITING TEST
# ============================================
Write-Host "`n[8] SECTION 8: RATE LIMITING" -ForegroundColor Yellow

Write-Host "Testing rate limiting (11 requests in quick succession)..." -ForegroundColor Gray
$rateLimitPassed = 0
$rateLimitBlocked = 0

for ($i = 1; $i -le 11; $i++) {
    try {
        $response = Invoke-WebRequest `
            -Uri "$baseUrl/api/voice/chat" `
            -Method POST `
            -Body (@{text="test $i"} | ConvertTo-Json) `
            -ContentType "application/json" `
            -UseBasicParsing `
            -ErrorAction Stop
        
        $rateLimitPassed++
        Write-Host "   Request $i : âœ… Passed (Status: $($response.StatusCode))" -ForegroundColor Green
    } catch {
        $rateLimitBlocked++
        $statusCode = $_.Exception.Response.StatusCode.value__
        if ($statusCode -eq 429) {
            Write-Host "   Request $i : ðŸš« Rate Limited (429)" -ForegroundColor Yellow
        } else {
            Write-Host "   Request $i : âŒ Error ($statusCode)" -ForegroundColor Red
        }
    }
    Start-Sleep -Milliseconds 100
}

Write-Host "`nRate Limit Results:" -ForegroundColor Cyan
Write-Host "   Passed: $rateLimitPassed" -ForegroundColor Green
Write-Host "   Blocked: $rateLimitBlocked" -ForegroundColor Yellow

if ($rateLimitBlocked -gt 0) {
    Write-Host "âœ… Rate limiting is WORKING" -ForegroundColor Green
} else {
    Write-Host "âš ï¸  Rate limiting may not be active" -ForegroundColor Yellow
}

# ============================================
# 9. SATELLITE DATA (NDVI)
# ============================================
Write-Host "`n[9] SECTION 9: SATELLITE DATA (NDVI)" -ForegroundColor Yellow

if ($token -and $fieldId) {
    Test-Endpoint `
        -Name "Fetch NDVI Data" `
        -Url "$baseUrl/api/fields/$fieldId/ndvi" `
        -Method "GET" `
        -Headers $authHeaders
}

# ============================================
# 10. EDGE AI MODEL TESTS
# ============================================
Write-Host "`n[10] SECTION 10: EDGE AI MODEL VALIDATION" -ForegroundColor Yellow

Write-Host "Testing Edge AI decision tree logic..." -ForegroundColor Gray

# Test scenarios
$scenarios = @(
    @{Name="Optimal Conditions"; ph=6.8; temp=24.0; moisture=28.0; ec=1.5; expected="monitor"},
    @{Name="Low Moisture"; ph=6.5; temp=26.0; moisture=12.0; ec=1.8; expected="irrigate"},
    @{Name="High Salinity"; ph=7.0; temp=25.0; moisture=30.0; ec=4.5; expected="leach"},
    @{Name="Critical Salinity"; ph=7.2; temp=27.0; moisture=35.0; ec=8.5; expected="reclamation"},
    @{Name="Wrong pH"; ph=5.2; temp=23.0; moisture=30.0; ec=1.5; expected="amend"}
)

foreach ($scenario in $scenarios) {
    $result = Test-Endpoint `
        -Name "Edge AI: $($scenario.Name)" `
        -Url "$baseUrl/api/model/predict" `
        -Method "POST" `
        -Body @{
            ph = $scenario.ph
            temperature = $scenario.temp
            moisture = $scenario.moisture
            ec = $scenario.ec
        }
    
    if ($result -and $result.action_name -eq $scenario.expected) {
        Write-Host "   âœ… Correct prediction: $($scenario.expected)" -ForegroundColor Green
    } else {
        Write-Host "   âš ï¸  Expected '$($scenario.expected)', got '$($result.action_name)'" -ForegroundColor Yellow
    }
}

# ============================================
# TEST SUMMARY
# ============================================
Write-Host "`n`nâ•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—" -ForegroundColor Magenta
Write-Host "â•‘                      TEST SUMMARY                             â•‘" -ForegroundColor Magenta
Write-Host "â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•`n" -ForegroundColor Magenta

$passCount = ($testResults | Where-Object { $_.Status -eq "PASS" }).Count
$warnCount = ($testResults | Where-Object { $_.Status -eq "WARN" }).Count
$failCount = ($testResults | Where-Object { $_.Status -eq "FAIL" }).Count
$totalTests = $testResults.Count

Write-Host "Total Tests: $totalTests" -ForegroundColor Cyan
Write-Host "âœ… Passed:   $passCount" -ForegroundColor Green
Write-Host "âš ï¸  Warnings: $warnCount" -ForegroundColor Yellow
Write-Host "âŒ Failed:   $failCount" -ForegroundColor Red

$successRate = [math]::Round(($passCount / $totalTests) * 100, 1)
Write-Host "`nSuccess Rate: $successRate%" -ForegroundColor $(if ($successRate -ge 90) { "Green" } elseif ($successRate -ge 70) { "Yellow" } else { "Red" })

if ($failCount -eq 0 -and $successRate -ge 90) {
    Write-Host "`n[SUCCESS] SYSTEM IS PRODUCTION-READY!" -ForegroundColor Green
} elseif ($failCount -eq 0) {
    Write-Host "`n[OK] System is operational with minor issues" -ForegroundColor Yellow
} else {
    Write-Host "`n[WARNING] System has critical issues that need attention" -ForegroundColor Red
}

# Export results
$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$reportPath = "test_results_$timestamp.json"
$testResults | ConvertTo-Json -Depth 10 | Out-File $reportPath
Write-Host "Detailed results saved to: $reportPath" -ForegroundColor Cyan

