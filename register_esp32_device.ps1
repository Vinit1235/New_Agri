# Register ESP32 Device and Get Token
# This script registers your ESP32 device and returns the token

$baseUrl = "http://localhost:8000"

Write-Host "`n=============================================" -ForegroundColor Cyan
Write-Host "   ESP32 DEVICE REGISTRATION" -ForegroundColor Magenta
Write-Host "=============================================`n" -ForegroundColor Cyan

# Step 1: Get user credentials
Write-Host "Enter your login credentials:" -ForegroundColor Yellow
$email = Read-Host "Email"
$password = Read-Host "Password" -AsSecureString
$passwordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($password))

# Step 2: Login
Write-Host "`nLogging in..." -ForegroundColor Yellow
try {
    $loginForm = "username=$([uri]::EscapeDataString($email))&password=$([uri]::EscapeDataString($passwordPlain))"
    
    $loginResult = Invoke-RestMethod -Uri "$baseUrl/api/auth/login" `
        -Method POST `
        -Body $loginForm `
        -ContentType "application/x-www-form-urlencoded"
    
    $userToken = $loginResult.access_token
    Write-Host "SUCCESS - Logged in" -ForegroundColor Green
} catch {
    Write-Host "ERROR - Login failed: $($_.Exception.Message)" -ForegroundColor Red
    exit
}

# Step 3: Get user's fields
Write-Host "`nFetching your fields..." -ForegroundColor Yellow
try {
    $fields = Invoke-RestMethod -Uri "$baseUrl/api/fields" `
        -Method GET `
        -Headers @{Authorization="Bearer $userToken"}
    
    if ($fields.Count -eq 0) {
        Write-Host "ERROR - You don't have any fields yet" -ForegroundColor Red
        Write-Host "Please create a field first via the dashboard" -ForegroundColor Yellow
        exit
    }
    
    Write-Host "SUCCESS - Found $($fields.Count) field(s)" -ForegroundColor Green
    Write-Host ""
    
    # List fields
    for ($i = 0; $i -lt $fields.Count; $i++) {
        Write-Host "  [$($i+1)] $($fields[$i].name) (ID: $($fields[$i].id))" -ForegroundColor White
        Write-Host "      Crop: $($fields[$i].crop_type) | Area: $($fields[$i].area_hectares) ha" -ForegroundColor Gray
    }
    
    Write-Host ""
    $fieldChoice = Read-Host "Select field number (1-$($fields.Count))"
    $selectedField = $fields[[int]$fieldChoice - 1]
    
    Write-Host "Selected: $($selectedField.name) (ID: $($selectedField.id))" -ForegroundColor Cyan
    
} catch {
    Write-Host "ERROR - Failed to fetch fields: $($_.Exception.Message)" -ForegroundColor Red
    exit
}

# Step 4: Get device details
Write-Host "`nEnter device details:" -ForegroundColor Yellow
$deviceId = Read-Host "Device ID (e.g., esp32-01)" 
if ([string]::IsNullOrWhiteSpace($deviceId)) {
    $deviceId = "esp32-01"
}

$deviceName = Read-Host "Device Name (e.g., Field 1 ESP32)"
if ([string]::IsNullOrWhiteSpace($deviceName)) {
    $deviceName = "Field 1 ESP32"
}

# Step 5: Register device
Write-Host "`nRegistering device..." -ForegroundColor Yellow

$deviceData = @{
    device_id = $deviceId
    name = $deviceName
    field_id = $selectedField.id
}

try {
    $deviceResult = Invoke-RestMethod -Uri "$baseUrl/api/devices/register" `
        -Method POST `
        -Body ($deviceData | ConvertTo-Json) `
        -ContentType "application/json" `
        -Headers @{Authorization="Bearer $userToken"}
    
    $deviceToken = $deviceResult.token
    
    Write-Host "`n=============================================" -ForegroundColor Green
    Write-Host "   DEVICE REGISTERED SUCCESSFULLY!" -ForegroundColor Green
    Write-Host "=============================================`n" -ForegroundColor Green
    
    Write-Host "Device Details:" -ForegroundColor Cyan
    Write-Host "  Device ID:   $($deviceResult.device_id)" -ForegroundColor White
    Write-Host "  Device Name: $($deviceResult.name)" -ForegroundColor White
    Write-Host "  Field:       $($selectedField.name) (ID: $($selectedField.id))" -ForegroundColor White
    Write-Host ""
    Write-Host "Device Token (SAVE THIS - shown only once):" -ForegroundColor Yellow
    Write-Host "  $deviceToken" -ForegroundColor White
    
    # Save to file
    $configFile = "esp32_device_config.txt"
    $configContent = @"
ESP32 Device Configuration
Generated: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
==========================================

Device ID:     $($deviceResult.device_id)
Device Name:   $($deviceResult.name)
Field ID:      $($selectedField.id)
Field Name:    $($selectedField.name)

Device Token:
$deviceToken

==========================================
ARDUINO IDE CONFIGURATION:
==========================================

Copy these lines into your ESP32 firmware:

const char* DEVICE_ID     = "$($deviceResult.device_id)";
const char* DEVICE_TOKEN  = "$deviceToken";
const char* BACKEND_URL   = "http://YOUR_PC_IP:8000/api/telemetry";

IMPORTANT: Replace YOUR_PC_IP with your actual IP address
Get it by running: ipconfig

==========================================
"@
    
    $configContent | Out-File $configFile -Encoding UTF8
    
    Write-Host "`nConfiguration saved to: $configFile" -ForegroundColor Cyan
    Write-Host ""
    
    # Show next steps
    Write-Host "=============================================" -ForegroundColor Cyan
    Write-Host "   NEXT STEPS" -ForegroundColor Magenta
    Write-Host "=============================================`n" -ForegroundColor Cyan
    
    Write-Host "1. Get your PC's IP address:" -ForegroundColor Yellow
    Write-Host "   Run: ipconfig" -ForegroundColor White
    Write-Host "   Look for IPv4 Address (e.g., 192.168.1.105)" -ForegroundColor Gray
    Write-Host ""
    
    Write-Host "2. Open your firmware in Arduino IDE:" -ForegroundColor Yellow
    Write-Host "   File: esp32-firmware\SoilEdge_FieldNode\SoilEdge_FieldNode.ino" -ForegroundColor White
    Write-Host ""
    
    Write-Host "3. Update these lines (around line 10-25):" -ForegroundColor Yellow
    Write-Host "   const char* WIFI_SSID     = `"YourWiFiName`";" -ForegroundColor White
    Write-Host "   const char* WIFI_PASSWORD = `"YourWiFiPassword`";" -ForegroundColor White
    Write-Host "   const char* BACKEND_URL   = `"http://YOUR_PC_IP:8000/api/telemetry`";" -ForegroundColor White
    Write-Host "   const char* DEVICE_ID     = `"$($deviceResult.device_id)`";" -ForegroundColor Cyan
    Write-Host "   const char* DEVICE_TOKEN  = `"$deviceToken`";" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "4. Upload to ESP32:" -ForegroundColor Yellow
    Write-Host "   - Tools → Board → ESP32 Dev Module" -ForegroundColor White
    Write-Host "   - Tools → Port → Select your COM port" -ForegroundColor White
    Write-Host "   - Click Upload (→)" -ForegroundColor White
    Write-Host ""
    
    Write-Host "5. Monitor output:" -ForegroundColor Yellow
    Write-Host "   - Tools → Serial Monitor" -ForegroundColor White
    Write-Host "   - Set to 115200 baud" -ForegroundColor White
    Write-Host "   - Look for 'WiFi connected!' and 'HTTP 200'" -ForegroundColor White
    Write-Host ""
    
} catch {
    $statusCode = $_.Exception.Response.StatusCode.value__
    Write-Host "`nERROR - Device registration failed" -ForegroundColor Red
    
    if ($statusCode -eq 400) {
        Write-Host "This device ID is already registered" -ForegroundColor Yellow
        Write-Host "Try a different device ID or check existing devices in dashboard" -ForegroundColor Yellow
    } else {
        Write-Host "$($_.Exception.Message)" -ForegroundColor Red
    }
    exit
}
