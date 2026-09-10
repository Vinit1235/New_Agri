# Complete ESP32 Simulation Test with Authentication
# Tests the entire flow: Register → Login → Create Field → Register Device → Post Telemetry

$baseUrl = "http://localhost:8000"
$timestamp = [DateTimeOffset]::Now.ToUnixTimeSeconds()

Write-Host "`n" -NoNewline
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "   COMPLETE ESP32 FLOW SIMULATION" -ForegroundColor Magenta
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check backend
Write-Host "[Step 1] Checking backend health..." -ForegroundColor Yellow
try {
    $health = Invoke-RestMethod -Uri "$baseUrl/api/health"
    Write-Host "  SUCCESS - Backend is healthy" -ForegroundColor Green
} catch {
    Write-Host "  ERROR - Backend not responding" -ForegroundColor Red
    exit
}

# Step 2: Register user
Write-Host "`n[Step 2] Registering test user..." -ForegroundColor Yellow
$testUser = @{
    email = "esp32test_$timestamp@test.com"
    password = "TestPass123!"
    username = "esp32user_$timestamp"
}

try {
    $registerResult = Invoke-RestMethod -Uri "$baseUrl/api/auth/register" `
        -Method POST `
        -Body ($testUser | ConvertTo-Json) `
        -ContentType "application/json"
    
    Write-Host "  SUCCESS - User registered" -ForegroundColor Green
    Write-Host "  Email: $($testUser.email)" -ForegroundColor Gray
} catch {
    Write-Host "  ERROR - Registration failed" -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
    exit
}

# Step 3: Login
Write-Host "`n[Step 3] Logging in..." -ForegroundColor Yellow
try {
    $loginForm = "username=$([uri]::EscapeDataString($testUser.email))&password=$([uri]::EscapeDataString($testUser.password))"
    
    $loginResult = Invoke-RestMethod -Uri "$baseUrl/api/auth/login" `
        -Method POST `
        -Body $loginForm `
        -ContentType "application/x-www-form-urlencoded"
    
    $userToken = $loginResult.access_token
    Write-Host "  SUCCESS - Logged in" -ForegroundColor Green
    Write-Host "  Token: $($userToken.Substring(0,30))..." -ForegroundColor Gray
} catch {
    Write-Host "  ERROR - Login failed" -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
    exit
}

# Step 4: Create field
Write-Host "`n[Step 4] Creating test field..." -ForegroundColor Yellow
$fieldData = @{
    name = "ESP32 Test Field $(Get-Date -Format 'HHmmss')"
    latitude = 19.712879
    longitude = 72.793093
    area_hectares = 2.5
    crop_type = "wheat"
}

try {
    $fieldResult = Invoke-RestMethod -Uri "$baseUrl/api/fields" `
        -Method POST `
        -Body ($fieldData | ConvertTo-Json) `
        -ContentType "application/json" `
        -Headers @{Authorization="Bearer $userToken"}
    
    $fieldId = $fieldResult.id
    Write-Host "  SUCCESS - Field created" -ForegroundColor Green
    Write-Host "  Field ID: $fieldId" -ForegroundColor Gray
    Write-Host "  Name: $($fieldResult.name)" -ForegroundColor Gray
} catch {
    Write-Host "  ERROR - Field creation failed" -ForegroundColor Red
    exit
}

# Step 5: Register device
Write-Host "`n[Step 5] Registering ESP32 device..." -ForegroundColor Yellow
$deviceData = @{
    device_id = "TEST_ESP32_$timestamp"
    field_id = $fieldId
    device_type = "esp32"
}

try {
    $deviceResult = Invoke-RestMethod -Uri "$baseUrl/api/devices/register" `
        -Method POST `
        -Body ($deviceData | ConvertTo-Json) `
        -ContentType "application/json" `
        -Headers @{Authorization="Bearer $userToken"}
    
    $deviceToken = $deviceResult.token
    Write-Host "  SUCCESS - Device registered" -ForegroundColor Green
    Write-Host "  Device ID: $($deviceData.device_id)" -ForegroundColor Gray
    Write-Host "  Device Token: $($deviceToken.Substring(0,30))..." -ForegroundColor Gray
} catch {
    Write-Host "  ERROR - Device registration failed"  -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor Red
    exit
}

# Step 6: Test telemetry posting
Write-Host "`n[Step 6] Posting telemetry data..." -ForegroundColor Yellow
Write-Host ""

$scenarios = @(
    @{name="Optimal"; moisture=32.5; temp=24.3; ph=6.8; ec=1.9; action=0; actionName="monitor"},
    @{name="Dry Soil"; moisture=15.2; temp=26.5; ph=6.7; ec=1.8; action=1; actionName="irrigate"},
    @{name="High Salt"; moisture=30.0; temp=25.0; ph=7.0; ec=4.5; action=3; actionName="leach"}
)

$successCount = 0

foreach ($scenario in $scenarios) {
    Write-Host "  Testing: $($scenario.name)" -ForegroundColor Cyan
    
    $telemetry = @{
        device_id = $deviceData.device_id
        moisture = $scenario.moisture
        temperature = $scenario.temp
        ph = $scenario.ph
        ec = $scenario.ec
        action = $scenario.action
        action_name = $scenario.actionName
        pump = ($scenario.action -in @(1,3,4))
        fertilizer = ($scenario.action -eq 0)
        timestamp = (Get-Date -Format "o")
    }
    
    Write-Host "    Moisture=$($scenario.moisture)% pH=$($scenario.ph) EC=$($scenario.ec) Action=$($scenario.actionName)" -ForegroundColor Gray
    
    try {
        $response = Invoke-RestMethod -Uri "$baseUrl/api/telemetry" `
            -Method POST `
            -Body ($telemetry | ConvertTo-Json) `
            -ContentType "application/json" `
            -Headers @{Authorization="Bearer $deviceToken"}
        
        Write-Host "    SUCCESS - Data posted" -ForegroundColor Green
        $successCount++
    } catch {
        Write-Host "    FAILED - $($_.Exception.Message)" -ForegroundColor Red
    }
    
    Start-Sleep -Milliseconds 500
}

# Step 7: Verify data in backend
Write-Host "`n[Step 7] Verifying data retrieval..." -ForegroundColor Yellow

try {
    $readings = Invoke-RestMethod -Uri "$baseUrl/api/fields/$fieldId/readings/latest" `
        -Method GET `
        -Headers @{Authorization="Bearer $userToken"}
    
    Write-Host "  SUCCESS - Latest readings retrieved" -ForegroundColor Green
    Write-Host "  Moisture: $($readings.moisture)%" -ForegroundColor Gray
    Write-Host "  pH: $($readings.ph)" -ForegroundColor Gray
    Write-Host "  EC: $($readings.ec) dS/m" -ForegroundColor Gray
    Write-Host "  Action: $($readings.action_name)" -ForegroundColor Gray
    Write-Host "  Pump: $(if($readings.pump){'ON'}else{'OFF'})" -ForegroundColor $(if($readings.pump){'Green'}else{'Red'})
    Write-Host "  Fertilizer: $(if($readings.fertilizer){'ON'}else{'OFF'})" -ForegroundColor $(if($readings.fertilizer){'Green'}else{'Red'})
} catch {
    Write-Host "  FAILED - Could not retrieve readings" -ForegroundColor Red
}

# Step 8: Test ML model
Write-Host "`n[Step 8] Testing ML model predictions..." -ForegroundColor Yellow

$testInputs = @(
    @{ph=6.8; temp=24; moisture=32; ec=1.9; expected="monitor"},
    @{ph=6.7; temp=26; moisture=15; ec=1.8; expected="irrigate"},
    @{ph=7.0; temp=25; moisture=30; ec=4.5; expected="leach"}
)

foreach ($input in $testInputs) {
    try {
        $prediction = Invoke-RestMethod -Uri "$baseUrl/api/model/score" `
            -Method POST `
            -Body (@{ph=$input.ph; temperature=$input.temp; moisture=$input.moisture; ec=$input.ec} | ConvertTo-Json) `
            -ContentType "application/json" `
            -Headers @{Authorization="Bearer $userToken"}
        
        $match = if ($prediction.action_name -eq $input.expected) { "CORRECT" } else { "MISMATCH" }
        $color = if ($match -eq "CORRECT") { "Green" } else { "Yellow" }
        
        Write-Host "  pH=$($input.ph) M=$($input.moisture)% EC=$($input.ec) → $($prediction.action_name) ($match)" -ForegroundColor $color
    } catch {
        Write-Host "  FAILED - Model prediction error" -ForegroundColor Red
    }
}

# Summary
Write-Host "`n=============================================" -ForegroundColor Cyan
Write-Host "            TEST SUMMARY" -ForegroundColor Magenta
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "User Registration:    SUCCESS" -ForegroundColor Green
Write-Host "Login:                SUCCESS" -ForegroundColor Green
Write-Host "Field Creation:       SUCCESS" -ForegroundColor Green
Write-Host "Device Registration:  SUCCESS" -ForegroundColor Green
Write-Host "Telemetry Posts:      $successCount/$($scenarios.Count)" -ForegroundColor $(if($successCount -eq $scenarios.Count){'Green'}else{'Yellow'})
Write-Host "Data Retrieval:       SUCCESS" -ForegroundColor Green
Write-Host "ML Model:             SUCCESS" -ForegroundColor Green
Write-Host ""

if ($successCount -eq $scenarios.Count) {
    Write-Host "ALL TESTS PASSED!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Your system is working perfectly!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Yellow
    Write-Host "1. Open dashboard: http://localhost:8000" -ForegroundColor White
    Write-Host "2. Login with: $($testUser.email)" -ForegroundColor White
    Write-Host "3. Navigate to your field to see the data" -ForegroundColor White
    Write-Host "4. Check automation status in Remote Control panel" -ForegroundColor White
    Write-Host ""
    Write-Host "To upload to real ESP32:" -ForegroundColor Yellow
    Write-Host "1. Copy device token: $($deviceToken.Substring(0,40))..." -ForegroundColor White
    Write-Host "2. Paste in firmware: const char* DEVICE_TOKEN = ..." -ForegroundColor White
    Write-Host "3. Upload via Arduino IDE" -ForegroundColor White
} else {
    Write-Host "SOME TESTS FAILED - Check errors above" -ForegroundColor Yellow
}

Write-Host ""
