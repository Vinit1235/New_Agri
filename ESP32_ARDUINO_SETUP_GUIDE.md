# 🔧 ESP32 Arduino IDE Setup & Upload Guide

## 📋 COMPLETE STEP-BY-STEP INSTRUCTIONS

### **What You'll Learn:**
1. Configure Arduino IDE for ESP32
2. Install required libraries
3. Configure your device settings
4. Upload firmware to ESP32
5. Test and verify operation

---

## ✅ **STEP 1: CONFIGURE ARDUINO IDE FOR ESP32**

### **1.1 Add ESP32 Board Manager URL**

1. **Open Arduino IDE**
2. Click **File → Preferences** (or press `Ctrl+,`)
3. Find **"Additional Board Manager URLs"** field
4. Paste this URL:
   ```
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
   ```
5. If there's already text, add a comma and paste on a new line
6. Click **OK**

---

### **1.2 Install ESP32 Board Package**

1. Click **Tools → Board → Boards Manager**
2. In the search box, type: `esp32`
3. Find **"esp32 by Espressif Systems"**
4. Click **Install** (this may take 5-10 minutes)
5. Wait for "INSTALLED" to appear
6. Close the Boards Manager

---

### **1.3 Select Your ESP32 Board**

1. Click **Tools → Board → ESP32 Arduino**
2. Select your board type:
   - **ESP32 Dev Module** (most common)
   - **ESP32-WROOM-DA Module**
   - **NodeMCU-32S**
   - **DOIT ESP32 DEVKIT V1**
   
   **💡 Tip:** If unsure, choose **"ESP32 Dev Module"** - it works for most boards

---

## ✅ **STEP 2: INSTALL REQUIRED LIBRARIES**

### **2.1 DHT Sensor Library (for Temperature & Humidity)**

1. Click **Sketch → Include Library → Manage Libraries**
2. Search: `DHT sensor library`
3. Find **"DHT sensor library by Adafruit"**
4. Click **Install**
5. When prompted to install dependencies, click **Install All**

---

### **2.2 Adafruit Unified Sensor Library**

1. In Library Manager, search: `Adafruit Unified Sensor`
2. Find **"Adafruit Unified Sensor by Adafruit"**
3. Click **Install**

---

### **2.3 HTTPClient Library (Built-in)**

✅ Already included with ESP32 board package - no installation needed

---

### **2.4 WiFi Library (Built-in)**

✅ Already included with ESP32 board package - no installation needed

---

## ✅ **STEP 3: CONFIGURE FIRMWARE SETTINGS**

### **3.1 Open Your Firmware**

1. In Arduino IDE, click **File → Open**
2. Navigate to:
   ```
   C:\Users\VINIT\Desktop\Smile_Clinc\New_Agri\esp32-firmware\SoilEdge_FieldNode\
   ```
3. Open: **SoilEdge_FieldNode.ino**

---

### **3.2 Configure WiFi Credentials**

Find these lines near the top of the file (around line 10-15):

```cpp
// ---- WiFi ----
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
```

**Change to your actual WiFi:**

```cpp
const char* WIFI_SSID     = "Your_Network_Name";
const char* WIFI_PASSWORD = "Your_WiFi_Password";
```

**Example:**
```cpp
const char* WIFI_SSID     = "JioFiber_Home";
const char* WIFI_PASSWORD = "MyPassword123";
```

---

### **3.3 Configure Backend URL**

Find this line (around line 17):

```cpp
const char* BACKEND_URL   = "http://192.168.1.100:8000/api/telemetry";
```

**Get Your PC's Local IP Address:**

**On Windows (PowerShell):**
1. Press `Win + X` → Select **Windows PowerShell** or **Terminal**
2. Type: `ipconfig`
3. Look for **"Wireless LAN adapter Wi-Fi"** or **"Ethernet adapter"**
4. Find **"IPv4 Address"** - it looks like `192.168.1.XXX`

**Example Output:**
```
Wireless LAN adapter Wi-Fi:
   IPv4 Address. . . . . . . . . . . : 192.168.1.105
```

**Update the URL:**
```cpp
const char* BACKEND_URL   = "http://192.168.1.105:8000/api/telemetry";
//                                    ↑ Your PC's IP
```

**⚠️ IMPORTANT:**
- Use your **actual local IP** (192.168.1.XXX)
- Keep port **8000**
- Keep `/api/telemetry` path
- Backend server must be running!

---

### **3.4 Register Your Device and Get Token**

**Option A: Use Existing Device (if you have one)**

If you already registered a device through the web dashboard, skip to 3.5.

**Option B: Register New Device via API**

1. Make sure backend is running (`uvicorn app.main:app --reload --port 8000`)
2. Open PowerShell and run:

```powershell
# Replace with your actual values
$token = "YOUR_USER_TOKEN_HERE"  # From login
$fieldId = 1  # Your field ID

# Register device
$body = @{
    device_id = "ESP32_FIELD_NODE_001"
    field_id = $fieldId
    device_type = "esp32"
} | ConvertTo-Json

$response = Invoke-RestMethod -Uri "http://localhost:8000/api/devices/register" `
    -Method POST `
    -Body $body `
    -ContentType "application/json" `
    -Headers @{Authorization="Bearer $token"}

Write-Host "Device Token: $($response.device_token)"
```

3. **Copy the device token** - you'll need it next!

---

### **3.5 Set Device ID and Token**

Find these lines (around line 20-25):

```cpp
const char* DEVICE_ID     = "ESP32_FIELD_001";
const char* DEVICE_TOKEN  = "your_device_token_here";
```

**Update with your values:**

```cpp
const char* DEVICE_ID     = "ESP32_FIELD_NODE_001";
const char* DEVICE_TOKEN  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...";
//                          ↑ Paste your actual token here
```

**💡 Example Complete Configuration:**

```cpp
// ---- WiFi ----
const char* WIFI_SSID     = "JioFiber_Home";
const char* WIFI_PASSWORD = "MyPassword123";

// ---- Backend ----
const char* BACKEND_URL   = "http://192.168.1.105:8000/api/telemetry";
const char* DEVICE_ID     = "ESP32_FIELD_NODE_001";
const char* DEVICE_TOKEN  = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJFU1AzMl9GSUVMRF9OT0RFXzAwMSIsImV4cCI6MTcyNTI4ODAwMH0.abc123";
```

---

### **3.6 Save Your Changes**

Click **File → Save** (or press `Ctrl+S`)

---

## ✅ **STEP 4: CONFIGURE UPLOAD SETTINGS**

### **4.1 Connect ESP32 to Computer**

1. **Plug in** your ESP32 board via USB cable
2. Wait for Windows to install drivers (if needed)
3. **Check Device Manager:**
   - Press `Win + X` → Device Manager
   - Look under **"Ports (COM & LPT)"**
   - You should see **"Silicon Labs CP210x USB to UART Bridge (COM3)"** or similar
   - **Note the COM port number** (e.g., COM3, COM4, COM5)

**⚠️ Troubleshooting:**
- If no COM port appears, you need to install **CP210x drivers**:
  1. Download from: https://www.silabs.com/developers/usb-to-uart-bridge-vcp-drivers
  2. Install and restart computer
  3. Reconnect ESP32

---

### **4.2 Select COM Port in Arduino IDE**

1. Click **Tools → Port**
2. Select your ESP32's COM port (e.g., **COM3**)

---

### **4.3 Configure Upload Settings**

Go to **Tools** menu and set:

| Setting | Value |
|---------|-------|
| **Board** | ESP32 Dev Module |
| **Upload Speed** | 115200 |
| **CPU Frequency** | 240MHz (WiFi/BT) |
| **Flash Frequency** | 80MHz |
| **Flash Mode** | QIO |
| **Flash Size** | 4MB (32Mb) |
| **Partition Scheme** | Default 4MB with spiffs |
| **Core Debug Level** | None |
| **PSRAM** | Disabled |
| **Port** | COM3 (or your port) |

**💡 Tip:** If unsure, these are safe defaults for most ESP32 boards.

---

## ✅ **STEP 5: VERIFY AND COMPILE**

### **5.1 Verify Code**

1. Click the **✓ Verify** button (top-left)
2. Watch the bottom console for compilation messages
3. You should see: **"Done compiling."**

**⚠️ If You See Errors:**

**Error: "DHT.h: No such file or directory"**
→ Go back to Step 2.1 and install DHT library

**Error: "WiFi.h: No such file or directory"**
→ Make sure ESP32 board package is installed (Step 1.2)

**Error: "'classify' was not declared"**
→ Make sure both `model_tree.c` and `model_tree.h` are in the same folder

---

### **5.2 Check Compilation Output**

Look for these in the console:

```
Sketch uses XXXXX bytes (X%) of program storage space.
Global variables use XXXXX bytes (X%) of dynamic memory.
```

✅ As long as both are under 100%, you're good!

---

## ✅ **STEP 6: UPLOAD FIRMWARE**

### **6.1 Upload to ESP32**

1. Click the **→ Upload** button (next to Verify)
2. Watch the console - you'll see:
   ```
   Connecting........_____....
   Writing at 0x00001000... (X%)
   Writing at 0x00008000... (X%)
   ...
   Leaving...
   Hard resetting via RTS pin...
   ```

3. Wait for **"Hard resetting via RTS pin..."** 
4. **✅ Upload complete!**

**⚠️ Troubleshooting Upload Issues:**

**"Failed to connect to ESP32: Timed out waiting for packet header"**

**Solution 1: Press BOOT Button**
1. Hold down the **BOOT** button on ESP32
2. Press **Upload** in Arduino IDE
3. Wait for "Connecting........"
4. **Release BOOT button** when you see "Writing at..."

**Solution 2: Check Cables**
- Use a **data cable** (not charge-only cable)
- Try a different USB port
- Try a different cable

**Solution 3: Lower Upload Speed**
- Tools → Upload Speed → **115200** (try slower speeds if needed)

---

## ✅ **STEP 7: MONITOR SERIAL OUTPUT**

### **7.1 Open Serial Monitor**

1. Click **Tools → Serial Monitor** (or press `Ctrl+Shift+M`)
2. Set baud rate to **115200** (bottom-right dropdown)
3. You should see output like:

```
SoilEdge field node booting...
Connecting to WiFi: JioFiber_Home
WiFi connected! IP: 192.168.1.142

=== Reading #1 ===
Moisture:    28.50%
Temperature: 24.30°C
pH:          6.80
EC:          1.90 dS/m
Action:      0 (monitor)
  action=0 (monitor)  pump=0  fert=1

Telemetry: HTTP 200

=== Next reading in 10 minutes ===
```

**✅ Success Indicators:**
- "WiFi connected!" → WiFi is working
- "HTTP 200" → Backend communication successful
- Action codes appearing → AI model is working
- pump/fert values → Automation is active

**⚠️ Error Messages:**

**"WiFi connection failed!"**
→ Check WiFi SSID and password

**"Telemetry failed: connection refused"**
→ Check backend URL and make sure server is running

**"HTTP 401 Unauthorized"**
→ Check device token is correct

---

## ✅ **STEP 8: VERIFY IN BACKEND**

### **8.1 Check Dashboard**

1. Open your browser
2. Go to: `http://localhost:8000` (or open dashboard.html)
3. Login to your account
4. Navigate to your field
5. **You should see:**
   - Latest sensor readings updating
   - Pump status changing based on moisture
   - Fertilizer status based on EC/pH
   - Real-time automation

---

### **8.2 Check Database**

Open PowerShell and run:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/fields/1/readings/latest" `
    -Headers @{Authorization="Bearer YOUR_TOKEN"}
```

You should see JSON with latest readings:
```json
{
  "moisture": 28.5,
  "temperature": 24.3,
  "ph": 6.8,
  "ec": 1.9,
  "action": 0,
  "action_name": "monitor",
  "pump": false,
  "fertilizer": true,
  "timestamp": "2026-09-02T10:30:00Z"
}
```

---

## 📊 **UNDERSTANDING THE OUTPUT**

### **Serial Monitor Messages Explained:**

```
=== Reading #1 ===
Moisture:    28.50%        ← Soil moisture sensor
Temperature: 24.30°C       ← DHT22 temperature
pH:          6.80          ← pH sensor (analog)
EC:          1.90 dS/m     ← EC sensor (analog)
Action:      0 (monitor)   ← AI decision
  pump=0  fert=1           ← Relays: 0=OFF, 1=ON

Telemetry: HTTP 200        ← Backend upload success
```

---

### **Action Codes:**

| Code | Name | Pump | Fertilizer | When |
|------|------|------|------------|------|
| **0** | monitor | OFF | ON (if safe) | Everything optimal |
| **1** | irrigate | ON | OFF | Low moisture |
| **2** | amend | OFF | OFF | Wrong pH |
| **3** | leach | ON | OFF | High salinity |
| **4** | reclamation | ON | OFF | Critical salinity |

---

## 🔧 **ADVANCED: HARDWARE WIRING** (When You Add Real Sensors)

### **Current Status:**
Your firmware is configured but returns **dummy values** (zeros). To get real data:

### **Required Sensors:**

1. **DHT22** - Temperature & Humidity
   - VCC → 3.3V
   - GND → GND
   - DATA → GPIO 4

2. **Soil Moisture Sensor**
   - VCC → 3.3V
   - GND → GND
   - AOUT → GPIO 32

3. **pH Sensor** (Analog)
   - VCC → 3.3V or 5V
   - GND → GND
   - AOUT → GPIO 34

4. **EC Sensor** (Analog)
   - VCC → 3.3V or 5V
   - GND → GND
   - AOUT → GPIO 35

5. **Pump Relay**
   - IN → GPIO 26
   - VCC → 5V
   - GND → GND
   - COM/NO → Pump

6. **Fertilizer Relay**
   - IN → GPIO 27
   - VCC → 5V
   - GND → GND
   - COM/NO → Valve

### **Next Step: Implement readSensors()**

The function `readSensors()` currently returns zeros. Update it to read real sensors:

```cpp
SensorReading readSensors() {
  SensorReading r;
  
  // Read DHT22
  r.temperature = dht.readTemperature();
  float humidity = dht.readHumidity();
  
  // Read moisture sensor (0-4095 → 0-100%)
  int moistureRaw = analogRead(MOISTURE_ADC_PIN);
  r.moisture = map(moistureRaw, 4095, 0, 0, 100);
  
  // Read pH sensor (calibration needed)
  int phRaw = analogRead(PH_ADC_PIN);
  r.ph = map(phRaw, 0, 4095, 0, 14);
  
  // Read EC sensor (calibration needed)
  int ecRaw = analogRead(EC_ADC_PIN);
  r.ec = map(ecRaw, 0, 4095, 0, 10);
  
  return r;
}
```

**📝 See:** `esp32_wiring_reference.html` for detailed wiring diagrams

---

## ✅ **QUICK REFERENCE CHECKLIST**

### **Before First Upload:**
- [ ] ESP32 board package installed
- [ ] DHT library installed
- [ ] WiFi SSID configured
- [ ] WiFi password configured
- [ ] Backend URL configured (your PC's IP)
- [ ] Device registered and token obtained
- [ ] Device token pasted in code
- [ ] ESP32 connected via USB
- [ ] Correct COM port selected
- [ ] Backend server running

### **After Upload:**
- [ ] Serial monitor shows "WiFi connected"
- [ ] Serial monitor shows "HTTP 200"
- [ ] Dashboard shows latest readings
- [ ] Pump status updates based on conditions
- [ ] Fertilizer status updates based on EC/pH

---

## 🚨 **COMMON ISSUES AND SOLUTIONS**

### **1. ESP32 Not Detected**
**Problem:** No COM port appears in Tools → Port

**Solutions:**
- Install CP210x USB drivers
- Try different USB cable (data cable, not charge-only)
- Try different USB port on computer
- Check ESP32 board has power LED lit

---

### **2. Upload Fails: "Timed Out"**
**Problem:** Can't upload, connection timeout

**Solutions:**
- Hold BOOT button while clicking Upload
- Lower upload speed (115200 → 57600)
- Check USB cable quality
- Disable antivirus temporarily

---

### **3. WiFi Won't Connect**
**Problem:** Serial monitor shows "WiFi connection failed"

**Solutions:**
- Double-check SSID and password (case-sensitive!)
- Make sure WiFi is 2.4GHz (ESP32 doesn't support 5GHz)
- Move ESP32 closer to router
- Restart router if needed

---

### **4. Backend Communication Failed**
**Problem:** Serial shows "Telemetry failed: connection refused"

**Solutions:**
- Make sure backend server is running:
  ```powershell
  cd C:\Users\VINIT\Desktop\Smile_Clinc\New_Agri\backend
  python -m uvicorn app.main:app --reload --port 8000
  ```
- Check PC firewall isn't blocking port 8000
- Verify IP address is correct (run `ipconfig`)
- Both ESP32 and PC must be on same WiFi network

---

### **5. HTTP 401 Unauthorized**
**Problem:** Serial shows "HTTP 401"

**Solutions:**
- Device token is wrong or expired
- Re-register device via API or dashboard
- Copy-paste new token into firmware
- Re-upload firmware

---

## 📞 **NEXT STEPS**

After successful upload:

1. **Test Automation:**
   - Watch serial monitor for 10-minute cycles
   - See action codes change based on readings
   - Check dashboard updates in real-time

2. **Add Real Sensors:**
   - Wire up DHT22, moisture, pH, EC sensors
   - Update `readSensors()` function
   - Calibrate sensors with known values

3. **Deploy to Field:**
   - Mount in weatherproof enclosure
   - Connect to field WiFi or mobile hotspot
   - Add battery backup if needed
   - Monitor from anywhere via web dashboard

---

## 📚 **HELPFUL RESOURCES**

- **ESP32 Pinout:** https://randomnerdtutorials.com/esp32-pinout-reference-gpios/
- **DHT22 Tutorial:** https://randomnerdtutorials.com/esp32-dht11-dht22-temperature-humidity-sensor-arduino-ide/
- **Arduino IDE Docs:** https://docs.arduino.cc/software/ide-v2
- **Your Wiring Diagram:** `esp32_wiring_reference.html` (in project root)

---

**Setup Date:** September 2, 2026  
**Firmware Version:** SoilEdge v1.0  
**Status:** Ready for deployment  

**Need Help?** Check the serial monitor output first - it tells you exactly what's happening!

🎉 **You're all set! Your ESP32 is now a smart field node with Edge AI automation!**
