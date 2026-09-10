#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <math.h>
#include "esp_sleep.h"
#include "DHT.h"

// =============================================================================
// SoilEdge Field Node — Advanced Edge IoT Firmware
// Features:
// 1. Soil Moisture (ADC) + DHT11 (Air Temp & RH)
// 2. Vapor Pressure Deficit (VPD) real-time calculation & crop stress index
// 3. Dew Point (Magnus formula) & Fungal Outbreak / Leaf Mold Risk Alert
// 4. Soil Depletion Rate (ΔMoisture/Δt) & Hours to Wilting Point Forecast
// 5. Smart Irrigation Hysteresis (ON < 25%, OFF >= 60%) to eliminate relay chatter
// 6. Fail-Safe Auto-Cutout Max Run Timer (3-min limit) + cooldown protection
// 7. Configurable Deep Sleep Low-Power Cycling for Battery/Solar Operation
// 8. Built-in Responsive Dark-Mode Web Dashboard + /data JSON API
// =============================================================================

// ---- WiFi Configuration ----
const char* ssid     = "realme C67 5G";
const char* password = "abhi#302";

// ---- Backend API Configuration ----
const char* API_BASE     = "http://10.235.221.52:8000";
const char* DEVICE_TOKEN = "esp32_secret_token_123";
const char* DEVICE_ID    = "esp32-01";
const bool  SEND_TO_BACKEND = true; // Auto-syncs telemetry with SoilEdge FastAPI backend

// ---- Pin Definitions ----
#define SOIL_PIN   34   // Capacitive/Resistive Soil Moisture Analog Pin (ADC1)
#define DHTPIN     4    // DHT11 Data Pin
#define DHTTYPE    DHT11
#define RELAY_PIN  26   // Submersible Pump / Solenoid Valve Relay Pin
#define RELAY_ACTIVE_LOW true // Standard 5V/3.3V relay boards trigger ON when pulled LOW

// ---- Sensor Calibration Constants ----
const int DRY_VALUE = 3300; // Sensor in dry air
const int WET_VALUE = 1400; // Sensor submerged in water

// ---- Smart Irrigation & Hysteresis Thresholds ----
const float MOISTURE_LOW_THRESHOLD  = 25.0f; // Turn ON pump when moisture drops below 25%
const float MOISTURE_HIGH_THRESHOLD = 60.0f; // Turn OFF pump when moisture reaches or exceeds 60%
const float WILTING_POINT_MOISTURE  = 15.0f; // Permanent wilting point for typical crops

// ---- Safety Protection Timers ----
const unsigned long MAX_PUMP_RUN_MS  = 180000; // Fail-safe auto-cutout limit: 3 minutes max continuous
const unsigned long PUMP_COOLDOWN_MS = 600000; // 10 minutes cooldown lockout after safety cutout
const unsigned long UPLOAD_INTERVAL_MS = 5000; // Telemetry upload cadence in continuous mode

// ---- Power Management (Deep Sleep) ----
// Set to false for live local web server (debugging / continuous power)
// Set to true for ultra-low-power battery/solar cycling (wakes, samples, acts, uploads, sleeps)
const bool     ENABLE_DEEP_SLEEP      = false;
const uint64_t SLEEP_DURATION_SECONDS = 60; // Sleep duration in seconds

// ---- RTC Slow Memory (Preserved across Deep Sleep cycles) ----
RTC_DATA_ATTR unsigned long rtc_boot_count = 0;
RTC_DATA_ATTR float         rtc_last_moisture = -1.0f;
RTC_DATA_ATTR unsigned long rtc_last_sample_time_ms = 0;
RTC_DATA_ATTR float         rtc_depletion_rate_pct_hr = 0.0f;
RTC_DATA_ATTR bool          rtc_safety_lockout = false;
RTC_DATA_ATTR unsigned long rtc_lockout_start_time = 0;

// ---- Global Runtime State ----
DHT dht(DHTPIN, DHTTYPE);
WebServer server(80);

bool          pumpActive = false;
unsigned long pumpStartTime = 0;
bool          safetyCutoutActive = false;
unsigned long safetyCutoutTime = 0;
unsigned long lastUploadTime = 0;
unsigned long lastDepletionCheckTime = 0;
float         lastSampleMoisture = -1.0f;
float         currentDepletionRate = 0.0f; // %/hr

// =============================================================================
// Helper Functions: Relay & Actuator Control
// =============================================================================
void setPump(bool enable) {
  pumpActive = enable;
  if (RELAY_ACTIVE_LOW) {
    digitalWrite(RELAY_PIN, enable ? LOW : HIGH);
  } else {
    digitalWrite(RELAY_PIN, enable ? HIGH : LOW);
  }
}

// =============================================================================
// Edge Math 1: Soil Moisture Percentage
// =============================================================================
float getSoilMoisturePercentage(int rawVal) {
  int moisturePercent = map(rawVal, DRY_VALUE, WET_VALUE, 0, 100);
  return (float)constrain(moisturePercent, 0, 100);
}

// =============================================================================
// Edge Math 2: Vapor Pressure Deficit (VPD in kPa)
// VPD = VPsat * (1 - RH/100)
// VPsat = 0.61078 * exp((17.27 * T) / (T + 237.3))
// =============================================================================
float calculateVPD(float tempC, float humidity) {
  if (isnan(tempC) || isnan(humidity) || humidity <= 0.0f) return 0.0f;
  float vpSat = 0.61078f * exp((17.27f * tempC) / (tempC + 237.3f));
  float vpAct = vpSat * (humidity / 100.0f);
  float vpd = vpSat - vpAct;
  return (vpd < 0.0f) ? 0.0f : vpd;
}

String getVPDStatus(float vpd) {
  if (vpd < 0.40f) return "Low Transpiration (High Humidity)";
  if (vpd <= 1.20f) return "Optimal Vegetative Zone";
  if (vpd <= 1.60f) return "Mild Transpiration Stress";
  return "High Moisture Stress (Stomata Closing)";
}

// =============================================================================
// Edge Math 3: Dew Point (Magnus Formula) & Fungal / Mold Risk
// =============================================================================
float calculateDewPoint(float tempC, float humidity) {
  if (isnan(tempC) || isnan(humidity) || humidity <= 0.0f) return 0.0f;
  float alpha = ((17.27f * tempC) / (237.3f + tempC)) + log(humidity / 100.0f);
  return (237.3f * alpha) / (17.27f - alpha);
}

String getFungalRisk(float tempC, float dewPointC, float humidity) {
  if (isnan(tempC) || isnan(humidity)) return "Unknown";
  float delta = tempC - dewPointC;
  // If ambient temperature is within 2°C of dew point or humidity > 85%, condensation occurs
  if (delta <= 2.0f || humidity >= 85.0f) {
    return "HIGH (Condensation / Mold Hazard)";
  }
  if (delta <= 4.0f || humidity >= 75.0f) {
    return "MODERATE (Monitor Closely)";
  }
  return "LOW (Healthy Aeration)";
}

// =============================================================================
// Edge Math 4: Soil Depletion Rate (ΔMoisture/Δt) & Hours to Wilting Point
// =============================================================================
void updateDepletionRate(float currentMoisture) {
  unsigned long now = millis();
  if (lastSampleMoisture < 0.0f) {
    lastSampleMoisture = currentMoisture;
    lastDepletionCheckTime = now;
    return;
  }

  unsigned long elapsedMs = now - lastDepletionCheckTime;
  // Recalculate rate every 60 seconds (or on significant readings)
  if (elapsedMs >= 60000) {
    float deltaMoisture = lastSampleMoisture - currentMoisture; // positive means drying out
    float hours = elapsedMs / 3600000.0f;
    if (hours > 0.0f) {
      // Exponential moving average for smooth rate
      float instantRate = deltaMoisture / hours;
      currentDepletionRate = (currentDepletionRate * 0.7f) + (instantRate * 0.3f);
    }
    lastSampleMoisture = currentMoisture;
    lastDepletionCheckTime = now;
  }
}

float getHoursToWiltingPoint(float currentMoisture) {
  if (currentDepletionRate <= 0.05f) {
    return -1.0f; // Stable or currently replenishing
  }
  if (currentMoisture <= WILTING_POINT_MOISTURE) {
    return 0.0f; // Already at or below wilting threshold
  }
  return (currentMoisture - WILTING_POINT_MOISTURE) / currentDepletionRate;
}

// =============================================================================
// Smart Irrigation: Hysteresis Control & Fail-Safe Cutout Timer
// =============================================================================
void evaluateIrrigationLogic(float moisture) {
  unsigned long now = millis();

  // 1. Check if safety lockout cooldown has expired
  if (safetyCutoutActive && (now - safetyCutoutTime >= PUMP_COOLDOWN_MS)) {
    safetyCutoutActive = false;
    Serial.println("[Safety] 10-minute cooldown elapsed. Pump safety lock reset.");
  }

  // 2. Continuous Run Fail-Safe Cutout
  if (pumpActive && (now - pumpStartTime >= MAX_PUMP_RUN_MS)) {
    setPump(false);
    safetyCutoutActive = true;
    safetyCutoutTime = now;
    Serial.println("[ALERT] Max continuous run timer exceeded (3 mins)! Cutout engaged to prevent flooding.");
    return;
  }

  // 3. Do not run if locked out
  if (safetyCutoutActive) {
    setPump(false);
    return;
  }

  // 4. Hysteresis State Machine
  // Moisture < 25%: Start pump
  if (moisture < MOISTURE_LOW_THRESHOLD) {
    if (!pumpActive) {
      setPump(true);
      pumpStartTime = now;
      Serial.printf("[Irrigation] Moisture %.1f%% < %.1f%%. Pump Started!\n", moisture, MOISTURE_LOW_THRESHOLD);
    }
  }
  // Moisture >= 60%: Stop pump
  else if (moisture >= MOISTURE_HIGH_THRESHOLD) {
    if (pumpActive) {
      setPump(false);
      Serial.printf("[Irrigation] Target moisture %.1f%% reached. Pump Stopped!\n", MOISTURE_HIGH_THRESHOLD);
    }
  }
  // Between 25% and 60%: Maintain previous state (HYSTERESIS - eliminates rapid relay chatter)
}

// =============================================================================
// HTTP Handlers: Built-in Live Dashboard & JSON Endpoint
// =============================================================================
void handleRoot() {
  int rawADC = analogRead(SOIL_PIN);
  float soilVolts = rawADC * (3.3f / 4095.0f);
  float moisture = getSoilMoisturePercentage(rawADC);
  float tempC = dht.readTemperature();
  float humidity = dht.readHumidity();

  float vpd = calculateVPD(tempC, humidity);
  String vpdStatus = getVPDStatus(vpd);

  float dewPoint = calculateDewPoint(tempC, humidity);
  String fungalRisk = getFungalRisk(tempC, dewPoint, humidity);

  float wiltingHours = getHoursToWiltingPoint(moisture);

  String html = "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>";
  html += "<meta name='viewport' content='width=device-width, initial-scale=1.0'>";
  html += "<meta http-equiv='refresh' content='4'>";
  html += "<title>SoilEdge IoT Field Gateway</title>";
  html += "<style>";
  html += "* { box-sizing: border-box; }";
  html += "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #090d16; color: #f1f5f9; margin: 0; padding: 20px; }";
  html += ".header { max-width: 960px; margin: 0 auto 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 14px; }";
  html += "h1 { font-size: 22px; color: #10b981; margin: 0; display: flex; align-items: center; gap: 8px; }";
  html += ".chip { background: #1e293b; border: 1px solid #334155; padding: 4px 12px; border-radius: 999px; font-size: 12px; color: #94a3b8; }";
  html += ".grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; max-width: 960px; margin: 0 auto; }";
  html += ".card { background: #131b2e; border: 1px solid #1e293b; border-radius: 14px; padding: 18px; box-shadow: 0 4px 16px rgba(0,0,0,0.25); }";
  html += ".card-title { font-size: 11px; text-transform: uppercase; letter-spacing: 1.2px; color: #64748b; font-weight: 700; margin-bottom: 8px; }";
  html += ".val { font-size: 34px; font-weight: 800; color: #38bdf8; line-height: 1.1; }";
  html += ".unit { font-size: 18px; font-weight: 500; color: #94a3b8; }";
  html += ".desc { font-size: 13px; color: #94a3b8; margin-top: 6px; }";
  html += ".badge { display: inline-block; padding: 3px 10px; border-radius: 9999px; font-size: 11px; font-weight: 600; margin-top: 8px; }";
  html += ".b-green { background: rgba(16,185,129,0.15); color: #34d399; border: 1px solid rgba(16,185,129,0.3); }";
  html += ".b-amber { background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.3); }";
  html += ".b-red { background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.3); }";
  html += ".b-blue { background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.3); }";
  html += ".bar-bg { background: #1e293b; height: 6px; border-radius: 999px; overflow: hidden; margin-top: 10px; }";
  html += ".bar-fill { height: 100%; border-radius: 999px; }";
  html += ".footer { max-width: 960px; margin: 24px auto 0; text-align: center; font-size: 12px; color: #475569; }";
  html += "</style></head><body>";

  html += "<div class='header'>";
  html += "<div><h1>🌱 SoilEdge Field Gateway</h1><div style='color:#64748b; font-size:13px; margin-top:3px;'>Node: <b>" + String(DEVICE_ID) + "</b> &bull; Boot Cycle #" + String(rtc_boot_count) + "</div></div>";
  html += "<div class='chip'>RSSI: <b>" + String(WiFi.RSSI()) + " dBm</b></div>";
  html += "</div>";

  html += "<div class='grid'>";

  // Card 1: Soil Moisture & Hysteresis Status
  html += "<div class='card'>";
  html += "<div class='card-title'>Soil Moisture & Hysteresis</div>";
  html += "<div class='val'>" + String((int)moisture) + "<span class='unit'>%</span></div>";
  html += "<div class='bar-bg'><div class='bar-fill' style='width:" + String((int)moisture) + "%; background:linear-gradient(90deg, #f59e0b, #10b981);'></div></div>";
  html += "<div class='desc'>ADC: <b>" + String(rawADC) + "</b> | <b>" + String(soilVolts, 2) + "V</b></div>";
  html += "<div class='desc'>Hysteresis Bands: ON < <b>" + String((int)MOISTURE_LOW_THRESHOLD) + "%</b> &bull; OFF &ge; <b>" + String((int)MOISTURE_HIGH_THRESHOLD) + "%</b></div>";
  html += "</div>";

  // Card 2: Smart Irrigation Actuator & Safety Cutout
  html += "<div class='card'>";
  html += "<div class='card-title'>Pump Actuator (Relay Pin " + String(RELAY_PIN) + ")</div>";
  if (safetyCutoutActive) {
    html += "<div class='val' style='color:#ef4444;'>LOCKOUT</div>";
    html += "<span class='badge b-red'>Fail-Safe Cutout (3-min limit exceeded)</span>";
    html += "<div class='desc' style='margin-top:8px;'>Cooling down to prevent flooding/overheating</div>";
  } else if (pumpActive) {
    unsigned long runSec = (millis() - pumpStartTime) / 1000;
    html += "<div class='val' style='color:#10b981;'>ACTIVE (ON)</div>";
    html += "<span class='badge b-green'>Pumping Water (" + String(runSec) + "s / 180s max)</span>";
    html += "<div class='desc' style='margin-top:8px;'>Soil target: " + String((int)MOISTURE_HIGH_THRESHOLD) + "%</div>";
  } else {
    html += "<div class='val' style='color:#94a3b8;'>IDLE (OFF)</div>";
    html += "<span class='badge b-blue'>Normal Standby</span>";
    html += "<div class='desc' style='margin-top:8px;'>Triggers ON when moisture drops below " + String((int)MOISTURE_LOW_THRESHOLD) + "%</div>";
  }
  html += "</div>";

  // Card 3: VPD (Vapor Pressure Deficit)
  html += "<div class='card'>";
  html += "<div class='card-title'>Vapor Pressure Deficit (VPD)</div>";
  html += "<div class='val'>" + String(vpd, 2) + "<span class='unit'> kPa</span></div>";
  String vpdBadgeClass = (vpd >= 0.40f && vpd <= 1.20f) ? "b-green" : ((vpd > 1.20f && vpd <= 1.60f) ? "b-amber" : "b-red");
  html += "<span class='badge " + vpdBadgeClass + "'>" + vpdStatus + "</span>";
  html += "<div class='desc' style='margin-top:8px;'>Calculated on-chip from live T & RH readings</div>";
  html += "</div>";

  // Card 4: Dew Point & Fungal Mold Hazard
  html += "<div class='card'>";
  html += "<div class='card-title'>Dew Point & Fungal Disease Risk</div>";
  html += "<div class='val'>" + String(dewPoint, 1) + "<span class='unit'> &deg;C</span></div>";
  String fungalBadgeClass = fungalRisk.startsWith("HIGH") ? "b-red" : (fungalRisk.startsWith("MODERATE") ? "b-amber" : "b-green");
  html += "<span class='badge " + fungalBadgeClass + "'>" + fungalRisk + "</span>";
  html += "<div class='desc' style='margin-top:8px;'>Condensation margin: <b>" + String(tempC - dewPoint, 1) + " &deg;C</b></div>";
  html += "</div>";

  // Card 5: Ambient Climate (DHT11)
  html += "<div class='card'>";
  html += "<div class='card-title'>Ambient Microclimate</div>";
  html += "<div class='val'>" + String(tempC, 1) + "<span class='unit'> &deg;C</span></div>";
  html += "<div class='desc' style='margin-top:4px;'>Relative Humidity: <b style='color:#38bdf8; font-size:16px;'>" + String(humidity, 1) + "%</b></div>";
  html += "<div class='bar-bg'><div class='bar-fill' style='width:" + String((int)humidity) + "%; background:#38bdf8;'></div></div>";
  html += "</div>";

  // Card 6: Soil Depletion Forecast
  html += "<div class='card'>";
  html += "<div class='card-title'>Soil Moisture Depletion Rate</div>";
  if (currentDepletionRate > 0.05f) {
    html += "<div class='val' style='color:#f59e0b;'>-" + String(currentDepletionRate, 2) + "<span class='unit'> %/hr</span></div>";
    if (wiltingHours >= 0.0f) {
      html += "<span class='badge b-amber'>Wilting Point in ~" + String(wiltingHours, 1) + " hours</span>";
    } else {
      html += "<span class='badge b-red'>Critically Dry</span>";
    }
  } else {
    html += "<div class='val' style='color:#34d399;'>Stable</div>";
    html += "<span class='badge b-green'>Moisture Equilibrium / Saturated</span>";
  }
  html += "<div class='desc' style='margin-top:8px;'>Permanent wilting threshold: <b>" + String((int)WILTING_POINT_MOISTURE) + "%</b></div>";
  html += "</div>";

  html += "</div>"; // end grid

  html += "<div class='footer'>";
  html += "Auto-refreshing live telemetry &bull; IP: " + WiFi.localIP().toString() + " &bull; SoilEdge Embedded OS";
  html += "</div>";

  html += "</body></html>";
  server.send(200, "text/html", html);
}

// JSON API Endpoint for REST clients or frontend polling
void handleDataJson() {
  int rawADC = analogRead(SOIL_PIN);
  float soilVolts = rawADC * (3.3f / 4095.0f);
  float moisture = getSoilMoisturePercentage(rawADC);
  float tempC = dht.readTemperature();
  float humidity = dht.readHumidity();
  float vpd = calculateVPD(tempC, humidity);
  float dewPoint = calculateDewPoint(tempC, humidity);
  float wiltingHours = getHoursToWiltingPoint(moisture);

  String json = "{";
  json += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  json += "\"boot_count\":" + String(rtc_boot_count) + ",";
  json += "\"moisture\":" + String(moisture, 2) + ",";
  json += "\"soil_raw\":" + String(rawADC) + ",";
  json += "\"soil_voltage\":" + String(soilVolts, 2) + ",";
  json += "\"temperature\":" + (isnan(tempC) ? "null" : String(tempC, 2)) + ",";
  json += "\"humidity\":" + (isnan(humidity) ? "null" : String(humidity, 2)) + ",";
  json += "\"vpd_kpa\":" + String(vpd, 2) + ",";
  json += "\"vpd_status\":\"" + getVPDStatus(vpd) + "\",";
  json += "\"dew_point_c\":" + String(dewPoint, 2) + ",";
  json += "\"fungal_risk\":\"" + getFungalRisk(tempC, dewPoint, humidity) + "\",";
  json += "\"depletion_rate_pct_hr\":" + String(currentDepletionRate, 3) + ",";
  json += "\"hours_to_wilting\":" + String(wiltingHours, 1) + ",";
  json += "\"pump_active\":" + String(pumpActive ? "true" : "false") + ",";
  json += "\"safety_lockout\":" + String(safetyCutoutActive ? "true" : "false") + ",";
  json += "\"wifi_rssi\":" + String(WiFi.RSSI());
  json += "}";

  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", json);
}

// =============================================================================
// Backend Synchronization: POST Telemetry & Decisions
// =============================================================================
void postTelemetryToBackend(float moisture, float temp, float humid, bool pumpState) {
  if (!SEND_TO_BACKEND || WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(API_BASE) + "/api/telemetry";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  if (strlen(DEVICE_TOKEN) > 0) {
    http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
  }

  String actionName = pumpState ? "HYSTERESIS_IRRIGATION_ON" : "STANDBY";
  if (safetyCutoutActive) {
    actionName = "SAFETY_CUTOUT_ENGAGED";
  }

  String body = "{";
  body += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  body += "\"moisture\":" + String(moisture, 2) + ",";
  body += "\"temperature\":" + String(temp, 2) + ",";
  body += "\"humidity\":" + String(humid, 2) + ",";
  body += "\"pump\":" + String(pumpState ? "true" : "false") + ",";
  body += "\"fertilizer\":false,";
  body += "\"action_name\":\"" + actionName + "\"";
  body += "}";

  int httpCode = http.POST(body);
  if (httpCode > 0) {
    Serial.printf("[Backend Sync] POST /api/telemetry HTTP %d\n", httpCode);
  } else {
    Serial.printf("[Backend Sync] HTTP Error: %s\n", http.errorToString(httpCode).c_str());
  }
  http.end();
}

// =============================================================================
// Setup
// =============================================================================
void setup() {
  Serial.begin(115200);
  delay(500);

  rtc_boot_count++;
  Serial.println("\n================================================");
  Serial.printf("  SoilEdge Smart Node Starting (Boot #%lu)\n", rtc_boot_count);
  Serial.println("================================================");

  // Configure Pins
  analogSetAttenuation(ADC_11db); // 0-3.3V ADC range
  pinMode(SOIL_PIN, INPUT);
  pinMode(RELAY_PIN, OUTPUT);
  setPump(false); // Default relay OFF for safety on boot

  dht.begin();

  // Connect to WiFi
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  unsigned long startWifi = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - startWifi < 15000)) {
    delay(400);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected! IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n[WiFi] Connection timeout. Operating in autonomous offline mode.");
  }

  // If Deep Sleep Mode is enabled:
  // Sample sensors once -> execute edge logic & relay -> POST to backend -> Deep Sleep
  if (ENABLE_DEEP_SLEEP) {
    Serial.println("[Power] Executing ultra-low-power duty cycle...");
    int rawADC = analogRead(SOIL_PIN);
    float moisture = getSoilMoisturePercentage(rawADC);
    float tempC = dht.readTemperature();
    float humidity = dht.readHumidity();

    if (!isnan(tempC) && !isnan(humidity)) {
      updateDepletionRate(moisture);
      evaluateIrrigationLogic(moisture);
      postTelemetryToBackend(moisture, tempC, humidity, pumpActive);
    }

    Serial.printf("[Power] Entering deep sleep for %llu seconds...\n", SLEEP_DURATION_SECONDS);
    esp_sleep_enable_timer_wakeup(SLEEP_DURATION_SECONDS * 1000000ULL);
    esp_deep_sleep_start();
  }

  // Continuous Server Mode:
  server.on("/", handleRoot);
  server.on("/data", handleDataJson);
  server.begin();
  Serial.println("[WebServer] Live dashboard running at http://" + WiFi.localIP().toString());
}

// =============================================================================
// Main Loop (Continuous Server Mode)
// =============================================================================
void loop() {
  server.handleClient();

  unsigned long now = millis();

  // Periodic Telemetry Ingestion & Control Loop
  if (now - lastUploadTime >= UPLOAD_INTERVAL_MS) {
    lastUploadTime = now;

    int rawADC = analogRead(SOIL_PIN);
    float moisture = getSoilMoisturePercentage(rawADC);
    float tempC = dht.readTemperature();
    float humidity = dht.readHumidity();

    if (!isnan(tempC) && !isnan(humidity)) {
      // 1. Update soil depletion tracking
      updateDepletionRate(moisture);

      // 2. Evaluate smart irrigation hysteresis and run timer
      evaluateIrrigationLogic(moisture);

      // 3. Post telemetry to FastAPI backend
      if (SEND_TO_BACKEND) {
        postTelemetryToBackend(moisture, tempC, humidity, pumpActive);
      }
    }
  }
}
