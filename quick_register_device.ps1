# Quick Device Registration
# Uses the test account from earlier

$baseUrl = "http://localhost:8000"

Write-Host "`n=============================================" -ForegroundColor Cyan
Write-Host "   QUICK ESP32 DEVICE REGISTRATION" -ForegroundColor Magenta
Write-Host "=============================================`n" -ForegroundColor Cyan

# Using test account
$email = "esp32test_1788345274@test.com"
$password = "TestPass123!"

Write-Host "Using test account: $email" -ForegroundColor Gray

# Login
Write-Host "Logging in..." -ForegroundColor Yellow
$loginForm = "username=$([uri]::EscapeDataString($email))&password=$([uri]::EscapeDataString($password))"

try {
    $loginResult = Invoke-RestMethod -Uri "$baseUrl/api/auth/login" `
        -Method POST `
        -Body $loginForm `
        -ContentType "application/x-www-form-urlencoded"
    
    $userToken = $loginResult.access_token
    Write-Host "SUCCESS" -ForegroundColor Green
} catch {
    Write-Host "FAILED - Creating new account..." -ForegroundColor Yellow
    
    # Register new account
    $timestamp = [DateTimeOffset]::Now.ToUnixTimeSeconds()
    $newUser = @{
        email = "esp32_$timestamp@test.com"
        password = "TestPass123!"
        full_name = "ESP32 User"
    }
    
    $registerResult = Invoke-RestMethod -Uri "$baseUrl/api/auth/register" `
        -Method POST `
        -Body ($newUser | ConvertTo-Json) `
        -ContentType "application/json"
    
    $userToken = $registerResult.access_token
    $email = $newUser.email
    Write-Host "New account created: $email" -ForegroundColor Green
}

# Get or create field
Write-Host "Checking fields..." -ForegroundColor Yellow
$fields = Invoke-RestMethod -Uri "$baseUrl/api/fields" `
    -Method GET `
    -Headers @{Authorization="Bearer $userToken"}

if ($fields.Count -eq 0) {
    Write-Host "No fields found - creating one..." -ForegroundColor Yellow
    
    $fieldData = @{
        name = "My Field"
        latitude = 19.712879
        longitude = 72.793093
        area_hectares = 2.5
        crop_type = "wheat"
    }
    
    $field = Invoke-RestMethod -Uri "$baseUrl/api/fields" `
        -Method POST `
        -Body ($fieldData | ConvertTo-Json) `
        -ContentType "application/json" `
        -Headers @{Authorization="Bearer $userToken"}
    
    Write-Host "Field created: $($field.name) (ID: $($field.id))" -ForegroundColor Green
} else {
    $field = $fields[0]
    Write-Host "Using field: $($field.name) (ID: $($field.id))" -ForegroundColor Green
}

# Register device
Write-Host "Registering device 'esp32-01'..." -ForegroundColor Yellow

$deviceData = @{
    device_id = "esp32-01"
    name = "Field 1 ESP32"
    field_id = $field.id
}

try {
    $device = Invoke-RestMethod -Uri "$baseUrl/api/devices/register" `
        -Method POST `
        -Body ($deviceData | ConvertTo-Json) `
        -ContentType "application/json" `
        -Headers @{Authorization="Bearer $userToken"}
    
    Write-Host "`n=============================================" -ForegroundColor Green
    Write-Host "   SUCCESS!" -ForegroundColor Green
    Write-Host "=============================================`n" -ForegroundColor Green
    
    Write-Host "Account:      $email" -ForegroundColor White
    Write-Host "Password:     TestPass123!" -ForegroundColor White
    Write-Host "Field:        $($field.name) (ID: $($field.id))" -ForegroundColor White
    Write-Host "Device ID:    $($device.device_id)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Device Token (copy this):" -ForegroundColor Yellow
    Write-Host "$($device.token)" -ForegroundColor White
    Write-Host ""
    
    # Create config file
    $config = @"
ESP32 Configuration
Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
==========================================

LOGIN CREDENTIALS:
  Email:    $email
  Password: TestPass123!

DEVICE INFORMATION:
  Device ID:   $($device.device_id)
  Device Name: $($device.name)
  Field:       $($field.name) (ID: $($field.id))

DEVICE TOKEN (copy to firmware):
$($device.token)

==========================================
COPY TO ARDUINO FIRMWARE:
==========================================

Open: esp32-firmware\SoilEdge_FieldNode\SoilEdge_FieldNode.ino

Update these lines:

const char* WIFI_SSID     = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* BACKEND_URL   = "http://YOUR_PC_IP:8000/api/telemetry";
const char* DEVICE_ID     = "$($device.device_id)";
const char* DEVICE_TOKEN  = "$($device.token)";

==========================================
GET YOUR PC IP:
==========================================

Run in PowerShell:
  ipconfig

Look for "IPv4 Address" under your WiFi adapter
Example: 192.168.1.105

Then update BACKEND_URL:
  "http://192.168.1.105:8000/api/telemetry"

==========================================
"@
    
    $config | Out-File "ESP32_CONFIG.txt" -Encoding UTF8
    
    Write-Host "Configuration saved to: ESP32_CONFIG.txt" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Next: Get your PC's IP with 'ipconfig' and update firmware" -ForegroundColor Yellow
    Write-Host ""
    
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response.StatusCode.value__ -eq 400) {
        Write-Host "Device 'esp32-01' is already registered" -ForegroundColor Yellow
        Write-Host "Use a different device_id or check dashboard" -ForegroundColor Yellow
    }
}
