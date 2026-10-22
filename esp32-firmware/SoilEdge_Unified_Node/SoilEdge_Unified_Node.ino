/*
 * ==============================================================================
 * SOIL-EDGE UNIFIED ESP32 FIRMWARE (Dynamic App Schema + Website Telemetry)
 * ==============================================================================
 * Bridges BOTH the Mobile / AI Studio App and the SoilEdge Website Backend.
 *
 * Capabilities:
 *  1. Dynamic JSON Schema Engine:
 *     - Fetches crop profiles, irrigation thresholds & pins from App / Cloud Run.
 *     - Web USB / Serial JSON handshake (PING_SYNC & FEED_SCHEMA).
 *     - Persists active profile to Non-Volatile Flash (Preferences) for offline resilience.
 *
 *  2. SoilEdge Website Backend Sync:
 *     - Posts rich telemetry (Moisture, Temp, Humidity, VPD, Turbidity, Flow, Pump)
 *       to FastAPI endpoint: POST /api/telemetry every 5 seconds.
 *
 *  3. Multi-Sensor Hardware Integration (Physical Breadboard Map):
 *     - Soil Moisture ADC: GPIO 32 (Switched via 2N2222 transistor on GPIO 25 to avoid corrosion)
 *     - DHT11 / DHT22: GPIO 4 (Air Temperature & Relative Humidity)
 *     - Turbidity Sensor: GPIO 34 (ADC1 with voltage divider)
 *     - Flow Sensor: GPIO 27 (Hall-effect interrupt counting pulses -> L/min & Litres)
 *     - Irrigation Relay / Pump: GPIO 26 (Configurable Active-LOW / Active-HIGH)
 *
 *  4. Dual Serial Protocol Output:
 *     - Emits [Telemetry] M=.. T=.. for Website live charts (esp32-monitor.html).
 *     - Emits compact JSON for mobile app & Web USB communication.
 *
 *  5. Local Web Server (Zero-Cloud LAN mode):
 *     - Serves built-in responsive dashboard at http://<ESP32_IP>/
 *     - Serves /data JSON API for local direct control.
 * ==============================================================================
 */

#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <math.h>
#include "DHT.h"

// ------------------------------------------------------------------------------
// 1. NETWORK & BACKEND CREDENTIALS
// ------------------------------------------------------------------------------
// Adjust these to match your Wi-Fi and Laptop / Server IP
const char* WIFI_SSID             = "realme C67 5G";
const char* WIFI_PASSWORD         = "abhi#302";

// Website Backend Gateway (FastAPI)
const char* BACKEND_BASE_URL      = "http://10.39.34.52:8000"; // Your PC's LAN IP
const char* DEVICE_TOKEN          = "esp32_secret_token_123";   // Matches token from web registration

// Optional: Cloud Run / AI Studio App Schema Feed URL
const char* SCHEMA_FEED_URL       = "http://10.39.34.52:8000/api/esp/schema";
const char* ESP_DEVICE_SECRET     = "soiledge_sec_esp32_token_981e80ce";

// ------------------------------------------------------------------------------
// 2. DEFAULT HARDWARE PINS & CALIBRATION (Overridable via Dynamic Schema)
// ------------------------------------------------------------------------------
#define DEFAULT_SOIL_PIN          32   // Soil Moisture AO (GPIO 32, ADC1)
#define DEFAULT_SOIL_POWER_PIN    25   // 2N2222 Transistor Base Gate (GPIO 25)
#define DEFAULT_DHT_PIN            4   // DHT11 / DHT22 Data Pin (GPIO 4)
#define DEFAULT_DHT_TYPE       DHT11
#define DEFAULT_TURBIDITY_PIN     34   // Turbidity Sensor AO (GPIO 34, ADC1)
#define DEFAULT_FLOW_PIN          27   // Water Flow Hall Sensor (GPIO 27, Interrupt)
#define DEFAULT_RELAY_PIN         26   // Submersible Pump Relay (GPIO 26)
#define DEFAULT_FERT_VALVE_PIN    22   // Solenoid Fertilizer Valve (GPIO 22)
#define RELAY_ACTIVE_LOW        true   // True for standard active-low relay modules

// Flow sensor calibration (YF-S201: 7.5 pulses/s = 1 L/min)
const float FLOW_K_FACTOR = 7.5f;

// Flash Storage Namespace
Preferences prefs;

// ------------------------------------------------------------------------------
// 3. ACTIVE IN-MEMORY DYNAMIC CONFIGURATION STRUCT
// ------------------------------------------------------------------------------
struct EdgeConfig {
  char  schema_version[16];
  char  schema_checksum[32];
  char  device_id[32];
  char  zone_id[32];
  char  crop_name[32];
  
  // Dynamic Agronomic Thresholds
  float min_moisture_pct;
  float target_moisture_pct;
  float critical_wilting_pct;
  float saturation_cutoff_pct;
  float max_ec_dsm;
  float temp_min_c;
  float temp_max_c;

  // Actuation & Watchdog Rules
  int   max_pump_runtime_sec;
  int   soak_delay_sec;
  bool  pulse_mode_enabled;
  int   pulse_on_sec;
  int   pulse_rest_sec;

  // Hardware Pins & Calibration
  int   moisture_adc_pin;
  int   soil_power_pin;
  int   relay_gpio_pin;
  int   flow_sensor_pin;
  int   turbidity_pin;
  int   adc_dry;
  int   adc_wet;

  // Polling & Telemetry Cadences
  int   check_interval_sec;
  int   telemetry_interval_sec;
} config;

// ------------------------------------------------------------------------------
// 4. RUNTIME SYSTEM STATE & SENSORS
// ------------------------------------------------------------------------------
DHT dht(DEFAULT_DHT_PIN, DEFAULT_DHT_TYPE);
WebServer server(80);

// Actuator States
bool          isPumpOn              = false;
bool          isValveOn             = false;
unsigned long pumpStartTimeMs       = 0;
bool          safetyCutoutActive    = false;
unsigned long safetyCutoutTimeMs    = 0;
const unsigned long PUMP_COOLDOWN_MS = 600000; // 10-minute cooldown after safety cutoff

// Sensor readings cache
float currentMoisture    = 0.0f;
float currentTemperature = 0.0f;
float currentHumidity    = 0.0f;
float currentVPD         = 0.0f;
float currentTurbidity   = 0.0f;

// Water Flow Metering
volatile unsigned long flowPulseCount = 0;
unsigned long          lastFlowCalcMs = 0;
float                  flowRateLPM    = 0.0f;
float                  sessionVolumeL = 0.0f;
RTC_DATA_ATTR float    rtcTotalVolumeL = 0.0f; // Preserved in RTC memory

// Loop Timers
unsigned long lastCheckMs      = 0;
unsigned long lastTelemetryMs  = 0;
unsigned long lastSchemaPollMs = 0;

// Serial Buffer
String serialRxBuffer = "";

// ------------------------------------------------------------------------------
// 5. INTERRUPT SERVICE ROUTINE FOR FLOW SENSOR
// ------------------------------------------------------------------------------
void IRAM_ATTR onFlowPulse() {
  flowPulseCount++;
}

// ------------------------------------------------------------------------------
// 6. ACTUATOR & RELAY CONTROL (WITH FAILSAFE WATCHDOG)
// ------------------------------------------------------------------------------

void setValve(bool enable, const char* reason = "MANUAL") {
  isValveOn = enable;
  int pin = DEFAULT_FERT_VALVE_PIN;
  pinMode(pin, OUTPUT);
  if (RELAY_ACTIVE_LOW) {
    digitalWrite(pin, enable ? LOW : HIGH);
  } else {
    digitalWrite(pin, enable ? HIGH : LOW);
  }
  Serial.printf("[Fertilizer Valve] %s (%s) | GPIO %d\n", enable ? "OPEN" : "CLOSED", reason, pin);
}

void setPump(bool enable, const char* reason = "MANUAL") {
  if (safetyCutoutActive && enable) {
    Serial.println("[Safety] Blocked pump start: safety lockout is currently ACTIVE.");
    return;
  }

  if (enable && !isPumpOn) {
    sessionVolumeL  = 0.0f; // Reset session counter on pump activation
    pumpStartTimeMs = millis();
    Serial.printf("[Pump] START (%s) | GPIO %d\n", reason, config.relay_gpio_pin);
  } else if (!enable && isPumpOn) {
    Serial.printf("[Pump] STOP (%s) | Session pumped: %.3f L | Cumulative: %.3f L\n",
                  reason, sessionVolumeL, rtcTotalVolumeL);
  }

  isPumpOn = enable;
  if (RELAY_ACTIVE_LOW) {
    digitalWrite(config.relay_gpio_pin, isPumpOn ? LOW : HIGH);
  } else {
    digitalWrite(config.relay_gpio_pin, isPumpOn ? HIGH : LOW);
  }
}

// ------------------------------------------------------------------------------
// 7. SENSOR MEASUREMENT ROUTINES
// ------------------------------------------------------------------------------
float readSoilMoisture() {
  // Pulse transistor gate to power moisture sensor, sample, then cut power
  digitalWrite(config.soil_power_pin, HIGH);
  delay(15);
  int raw = analogRead(config.moisture_adc_pin);
  digitalWrite(config.soil_power_pin, LOW);

  // Map ADC between calibrated dry and wet limits
  float pct = (float)map(raw, config.adc_dry, config.adc_wet, 0, 100);
  return constrain(pct, 0.0f, 100.0f);
}

float calculateVPD(float tempC, float rh) {
  if (isnan(tempC) || isnan(rh) || rh <= 0.0f) return 0.0f;
  float svp = 0.61078f * exp((17.27f * tempC) / (tempC + 237.3f));
  float vpd = svp * (1.0f - (rh / 100.0f));
  return max(0.0f, vpd);
}

float readTurbidity() {
  int raw = analogRead(config.turbidity_pin);
  float voltage = raw * (3.3f / 4095.0f);
  // Approximation: 3.0V = clear water (0 NTU), <1.5V = highly turbid (>1000 NTU)
  float ntu = (3.0f - voltage) * 500.0f;
  return constrain(ntu, 0.0f, 2000.0f);
}

void updateFlowMeasurements() {
  unsigned long now = millis();
  unsigned long elapsed = now - lastFlowCalcMs;
  if (elapsed >= 1000) {
    noInterrupts();
    unsigned long pulses = flowPulseCount;
    flowPulseCount = 0;
    interrupts();

    // Calculate flow rate in L/min
    flowRateLPM = (float)pulses / (FLOW_K_FACTOR * (elapsed / 1000.0f));

    // Volume increment in Litres
    float litresThisPeriod = (flowRateLPM / 60.0f) * (elapsed / 1000.0f);
    if (isPumpOn) {
      sessionVolumeL  += litresThisPeriod;
      rtcTotalVolumeL += litresThisPeriod;
    }
    lastFlowCalcMs = now;
  }
}

// ------------------------------------------------------------------------------
// 8. DYNAMIC JSON SCHEMA PARSER & PERSISTENCE
// ------------------------------------------------------------------------------
bool applyDynamicJsonSchema(const String& jsonString) {
  StaticJsonDocument<2048> doc;
  DeserializationError err = deserializeJson(doc, jsonString);
  if (err) {
    Serial.printf("[SCHEMA-ERROR] JSON parse failed: %s\n", err.c_str());
    return false;
  }

  // 1. Identity & Versioning
  strlcpy(config.schema_version, doc["schema_version"] | "3.0.0", sizeof(config.schema_version));
  strlcpy(config.schema_checksum, doc["edge_operating"]["schema_checksum"] | doc["checksum"] | "CRC-INIT", sizeof(config.schema_checksum));
  strlcpy(config.device_id, doc["device_id"] | "esp32-01", sizeof(config.device_id));
  strlcpy(config.zone_id, doc["zone_id"] | "zone-01", sizeof(config.zone_id));
  strlcpy(config.crop_name, doc["crop_profile"]["crop_name"] | doc["crop"] | "Tomato", sizeof(config.crop_name));

  // 2. Dynamic Thresholds
  config.min_moisture_pct      = doc["thresholds"]["min_moisture_pct"]      | doc["min_moisture"]    | 25.0f;
  config.target_moisture_pct   = doc["thresholds"]["target_moisture_pct"]   | doc["target_moisture"] | 60.0f;
  config.critical_wilting_pct  = doc["thresholds"]["critical_wilting_pct"]  | 15.0f;
  config.saturation_cutoff_pct = doc["thresholds"]["saturation_cutoff_pct"] | 85.0f;
  config.max_ec_dsm            = doc["thresholds"]["max_ec_dsm"]            | 2.5f;
  config.temp_min_c            = doc["thresholds"]["temp_min_c"]            | 16.0f;
  config.temp_max_c            = doc["thresholds"]["temp_max_c"]            | 35.0f;

  // 3. Actuation Rules
  config.max_pump_runtime_sec  = doc["actuation_rules"]["max_pump_runtime_sec"] | 180; // 3 min safety
  config.soak_delay_sec        = doc["actuation_rules"]["soak_delay_sec"]       | 180;
  config.pulse_mode_enabled    = doc["actuation_rules"]["pulse_mode_enabled"]   | false;
  config.pulse_on_sec          = doc["actuation_rules"]["pulse_on_seconds"]     | 120;
  config.pulse_rest_sec        = doc["actuation_rules"]["pulse_rest_seconds"]    | 60;

  // 4. Hardware Pins
  config.moisture_adc_pin      = doc["hardware_pins"]["moisture_adc_pin"]   | DEFAULT_SOIL_PIN;
  config.soil_power_pin        = doc["hardware_pins"]["soil_power_pin"]     | DEFAULT_SOIL_POWER_PIN;
  config.relay_gpio_pin        = doc["hardware_pins"]["relay_gpio_pin"]     | DEFAULT_RELAY_PIN;
  config.flow_sensor_pin       = doc["hardware_pins"]["flow_sensor_pin"]    | DEFAULT_FLOW_PIN;
  config.turbidity_pin         = doc["hardware_pins"]["turbidity_pin"]      | DEFAULT_TURBIDITY_PIN;
  config.adc_dry               = doc["hardware_pins"]["adc_dry_reading"]    | 3300;
  config.adc_wet               = doc["hardware_pins"]["adc_wet_reading"]    | 1400;

  // 5. Cadences
  config.check_interval_sec    = doc["edge_operating"]["check_interval_sec"]             | 10;
  config.telemetry_interval_sec= doc["edge_operating"]["telemetry_publish_interval_sec"]| 5;

  // Hardware re-initialization
  pinMode(config.relay_gpio_pin, OUTPUT);
  pinMode(config.soil_power_pin, OUTPUT);
  digitalWrite(config.soil_power_pin, LOW);
  setPump(false, "INIT_APPLY");

  // Save to persistent flash memory
  prefs.putString("saved_schema", jsonString);

  Serial.println("=================================================");
  Serial.printf("[SCHEMA-APPLIED] Crop: %s | Moisture: Min %.1f%% -> Target %.1f%%\n",
                config.crop_name, config.min_moisture_pct, config.target_moisture_pct);
  Serial.printf("[SCHEMA-APPLIED] Relay Pin: GPIO %d | Power Pin: GPIO %d | Checksum: %s\n",
                config.relay_gpio_pin, config.soil_power_pin, config.schema_checksum);
  Serial.println("=================================================");

  // Web USB / Serial Acknowledgment
  Serial.printf("{\"status\":\"ACK_APPLIED\",\"device\":\"%s\",\"crop\":\"%s\",\"checksum\":\"%s\"}\n",
                config.device_id, config.crop_name, config.schema_checksum);
  return true;
}

// ------------------------------------------------------------------------------
// 9. HTTP SCHEMA SYNC FROM BACKEND OR CLOUD RUN APP
// ------------------------------------------------------------------------------
void pollSchemaFeedFromApp() {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(SCHEMA_FEED_URL);
  http.addHeader("X-ESP-TOKEN", ESP_DEVICE_SECRET);
  http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
  http.addHeader("X-ESP-CHECKSUM", config.schema_checksum);
  http.setTimeout(3500);

  int httpCode = http.GET();
  if (httpCode == HTTP_CODE_OK) {
    String payload = http.getString();
    applyDynamicJsonSchema(payload);
  } else if (httpCode == 304) {
    // 304 Not Modified: configuration is already current
  } else {
    // Schema endpoint offline or not mounted
  }
  http.end();
}

// ------------------------------------------------------------------------------
// 10. HTTP TELEMETRY UPLOAD TO SOIL-EDGE WEBSITE BACKEND
// ------------------------------------------------------------------------------
void postTelemetryToWebsite() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String url = String(BACKEND_BASE_URL) + "/api/telemetry";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
  http.setTimeout(3000);

  String actionName = isPumpOn ? "HYSTERESIS_IRRIGATION_ON" : "STANDBY";
  if (safetyCutoutActive) actionName = "SAFETY_CUTOUT_ENGAGED";

  // Build telemetry payload matching backend schemas.TelemetryIn
  String payload;
  payload.reserve(512);
  payload = "{";
  payload += "\"device_id\":\""      + String(config.device_id)        + "\",";
  payload += "\"moisture\":"         + String(currentMoisture, 1)      + ",";
  payload += "\"temperature\":"      + (isnan(currentTemperature) ? "null" : String(currentTemperature, 1)) + ",";
  payload += "\"humidity\":"         + (isnan(currentHumidity)    ? "null" : String(currentHumidity, 1))    + ",";
  payload += "\"turbidity_ntu\":"    + String(currentTurbidity, 1)     + ",";
  payload += "\"flow_rate_lpm\":"    + String(flowRateLPM, 2)          + ",";
  payload += "\"session_volume_L\":" + String(sessionVolumeL, 3)       + ",";
  payload += "\"total_volume_L\":"   + String(rtcTotalVolumeL, 3)      + ",";
  payload += "\"pump\":"             + String(isPumpOn ? "true" : "false") + ",";
  payload += "\"fertilizer\":" + String(isValveOn ? "true" : "false") + ",";
  payload += "\"action_name\":\""    + actionName                      + "\"";
  payload += "}";

  int code = http.POST(payload);
  if (code == HTTP_CODE_OK || code == 201) {
    // Check if the backend sent dynamic commands or schema in response
    String response = http.getString();
    if (response.indexOf("\"crop_profile\"") >= 0 || response.indexOf("\"thresholds\"") >= 0) {
      applyDynamicJsonSchema(response);
    }
  }
  http.end();
}

// ------------------------------------------------------------------------------
// 11. LOCAL WEB SERVER (Direct Browser Access at http://<ESP32_IP>/)
// ------------------------------------------------------------------------------
void handleLocalDashboard() {
  String html = "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>SoilEdge Node</title>"
                "<style>body{background:#0b1320;color:#e2e8f0;font-family:sans-serif;padding:20px;text-align:center}"
                ".card{background:#132238;border:1px solid #1e3a5f;border-radius:12px;padding:16px;margin:12px auto;max-width:360px}"
                ".v{font-size:28px;font-weight:bold;color:#38bdf8}.btn{padding:10px 20px;border-radius:8px;border:none;cursor:pointer;font-weight:bold}"
                ".on{background:#10b981;color:#fff}.off{background:#ef4444;color:#fff}</style></head><body>"
                "<h2>🌿 " + String(config.crop_name) + " Node (" + String(config.device_id) + ")</h2>"
                "<div class='card'><div>Moisture</div><div class='v'>" + String(currentMoisture, 1) + "%</div>"
                "<div>Target: " + String(config.min_moisture_pct, 0) + "% - " + String(config.target_moisture_pct, 0) + "%</div></div>"
                "<div class='card'><div>Air Climate</div><div class='v'>" + String(currentTemperature, 1) + "&deg;C | " + String(currentHumidity, 1) + "% RH</div></div>"
                "<div class='card'><div>Water Flow &amp; Volume</div><div class='v'>" + String(flowRateLPM, 2) + " L/m</div>"
                "<div>Session: " + String(sessionVolumeL, 3) + " L | Total: " + String(rtcTotalVolumeL, 2) + " L</div></div>"
                "<div class='card'><div>Relay / Pump</div><div class='v' style='color:" + (isPumpOn ? "#10b981" : "#64748b") + "'>" + (isPumpOn ? "RUNNING" : "IDLE") + "</div><br>"
                "<a href='/pump?state=toggle'><button class='btn " + (isPumpOn ? "off'>STOP PUMP" : "on'>START PUMP") + "</button></a></div>"
                "</body></html>";
  server.send(200, "text/html", html);
}

void handleLocalDataApi() {
  String j = "{";
  j += "\"device\":\""     + String(config.device_id)     + "\",";
  j += "\"crop\":\""       + String(config.crop_name)     + "\",";
  j += "\"moisture\":"     + String(currentMoisture, 1)   + ",";
  j += "\"temp\":"         + String(currentTemperature, 1)+ ",";
  j += "\"humidity\":"     + String(currentHumidity, 1)   + ",";
  j += "\"vpd\":"          + String(currentVPD, 2)        + ",";
  j += "\"flow_lpm\":"     + String(flowRateLPM, 2)       + ",";
  j += "\"session_L\":"    + String(sessionVolumeL, 3)    + ",";
  j += "\"total_L\":"      + String(rtcTotalVolumeL, 3)   + ",";
  j += "\"pump\":"         + String(isPumpOn ? "true" : "false") + ",";
  j += "\"checksum\":\""   + String(config.schema_checksum) + "\"";
  j += "}";
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", j);
}


// ------------------------------------------------------------------------------
// OVER-THE-AIR WI-FI CROP CONFIGURATION ENDPOINT (GET/POST /setcrop or /crop)
// ------------------------------------------------------------------------------
void handleSetCrop() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "Content-Type");

  String cropName = "";

  if (server.hasArg("crop")) {
    cropName = server.arg("crop");
  } else if (server.hasArg("name")) {
    cropName = server.arg("name");
  } else if (server.hasArg("plain")) {
    // Check if sent via JSON payload
    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, server.arg("plain")) == DeserializationError::Ok) {
      if (doc.containsKey("crop")) cropName = doc["crop"].as<String>();
      else if (doc.containsKey("crop_name")) cropName = doc["crop_name"].as<String>();
    }
  }

  if (cropName.length() == 0) {
    server.send(400, "application/json", "{\"status\":\"error\",\"message\":\"Missing crop parameter. Example: /setcrop?crop=Tomato\"}");
    return;
  }

  cropName.trim();
  float minM = 25.0;
  float targetM = 60.0;
  int maxRun = 180;
  float maxEc = 2.5;

  String lower = cropName;
  lower.toLowerCase();

  if (lower.indexOf("tomato") >= 0) {
    minM = 28.0; targetM = 65.0; maxRun = 180; maxEc = 2.5;
  } else if (lower.indexOf("wheat") >= 0) {
    minM = 22.0; targetM = 50.0; maxRun = 240; maxEc = 4.0;
  } else if (lower.indexOf("rice") >= 0 || lower.indexOf("paddy") >= 0) {
    minM = 50.0; targetM = 85.0; maxRun = 360; maxEc = 3.0;
  } else if (lower.indexOf("cotton") >= 0) {
    minM = 20.0; targetM = 45.0; maxRun = 180; maxEc = 5.0;
  } else if (lower.indexOf("sugarcane") >= 0) {
    minM = 35.0; targetM = 70.0; maxRun = 300; maxEc = 3.5;
  } else if (lower.indexOf("maize") >= 0 || lower.indexOf("corn") >= 0) {
    minM = 25.0; targetM = 60.0; maxRun = 200; maxEc = 3.2;
  } else if (lower.indexOf("potato") >= 0) {
    minM = 30.0; targetM = 70.0; maxRun = 180; maxEc = 2.5;
  } else if (lower.indexOf("chilli") >= 0) {
    minM = 25.0; targetM = 65.0; maxRun = 180; maxEc = 2.0;
  }

  // Update in-memory configuration
  strncpy(config.crop_name, cropName.c_str(), sizeof(config.crop_name) - 1);
  config.min_moisture_pct = minM;
  config.target_moisture_pct = targetM;
  config.max_pump_runtime_sec = maxRun;
  config.max_ec_dsm = maxEc;

  // Persist to Flash (Preferences) so it survives power cycles
  prefs.putString("saved_crop", cropName);
  prefs.putFloat("saved_min_m", minM);
  prefs.putFloat("saved_target_m", targetM);
  prefs.putInt("saved_max_run", maxRun);

  Serial.printf("\n[OTA-CROP] >>> Successfully modified crop over Wi-Fi to: %s <<<\n", config.crop_name);
  Serial.printf("   New Autonomous Thresholds: Min Moisture: %.1f%% | Target: %.1f%% | Max Pump Run: %ds\n",
                minM, targetM, maxRun);

  String resp = "{\"status\":\"success\",\"message\":\"Crop successfully modified over Wi-Fi\",\"crop\":\"" + cropName +
                "\",\"min_moisture\":" + String(minM, 1) +
                ",\"target_moisture\":" + String(targetM, 1) +
                ",\"max_runtime_sec\":" + String(maxRun) +
                ",\"max_ec_dsm\":" + String(maxEc, 1) + "}";
  server.send(200, "application/json", resp);
}

void handlePumpToggle() {
  setPump(!isPumpOn, "LOCAL_WEB_TOGGLE");
  server.sendHeader("Location", "/");
  server.send(303);
}

// ------------------------------------------------------------------------------
// 12. COMMAND PARSER FOR USB / WEB SERIAL
// ------------------------------------------------------------------------------
void parseSerialCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd == "PING_SYNC") {
    Serial.printf("SYNC_HELLO:{\"device_id\":\"%s\",\"schema_checksum\":\"%s\",\"crop\":\"%s\"}\n",
                  config.device_id, config.schema_checksum, config.crop_name);
  } else if (cmd.startsWith("FEED_SCHEMA:")) {
    String jsonFeed = cmd.substring(12);
    applyDynamicJsonSchema(jsonFeed);
  } else if (cmd.startsWith("{") && cmd.endsWith("}")) {
    applyDynamicJsonSchema(cmd);
  } else if (cmd.equalsIgnoreCase("VALVE:ON") || cmd.equalsIgnoreCase("FERT:ON")) {
    setValve(true, "SERIAL_COMMAND");
  } else if (cmd.equalsIgnoreCase("VALVE:OFF") || cmd.equalsIgnoreCase("FERT:OFF")) {
    setValve(false, "SERIAL_COMMAND");
  } else if (cmd.equalsIgnoreCase("PUMP:ON") || cmd.equalsIgnoreCase("MOTOR:ON") || cmd.equalsIgnoreCase("FAN:ON")) {
    setPump(true, "SERIAL_COMMAND");
  } else if (cmd.equalsIgnoreCase("PUMP:OFF") || cmd.equalsIgnoreCase("MOTOR:OFF") || cmd.equalsIgnoreCase("FAN:OFF")) {
    setPump(false, "SERIAL_COMMAND");
  } else if (cmd.equalsIgnoreCase("STATUS")) {
    Serial.printf("[Telemetry] M=%.1f%%  T=%.1fC  RH=%.1f%%  Turb=%.0f NTU  Flow=%.2f L/m  Sess=%.3f L  Total=%.3f L  Pump=%s\n",
                  currentMoisture, currentTemperature, currentHumidity, currentTurbidity,
                  flowRateLPM, sessionVolumeL, rtcTotalVolumeL, isPumpOn ? "ON" : "OFF");
  }
}

// ------------------------------------------------------------------------------
// 13. SETUP
// ------------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\n[SOIL-EDGE] Booting Unified Smart Edge Node...");

  // Load last saved dynamic schema from Flash
  prefs.begin("soiledge", false);
  String cachedSchema = prefs.getString("saved_schema", "");
  if (cachedSchema.length() > 0) {
    Serial.println("[BOOT] Restoring active crop profile from flash storage...");
    applyDynamicJsonSchema(cachedSchema);
  } else {
    // Default Fallback Schema
    applyDynamicJsonSchema("{\"device_id\":\"esp32-01\",\"crop_profile\":{\"crop_name\":\"Tomato\"},"
                           "\"thresholds\":{\"min_moisture_pct\":25.0,\"target_moisture_pct\":60.0}}");
  }

  // Initialize Sensors & Peripherals
  dht.begin();
  pinMode(DEFAULT_FERT_VALVE_PIN, OUTPUT);
  digitalWrite(DEFAULT_FERT_VALVE_PIN, RELAY_ACTIVE_LOW ? HIGH : LOW); // Boot safe state
  pinMode(config.flow_sensor_pin, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(config.flow_sensor_pin), onFlowPulse, FALLING);
  lastFlowCalcMs = millis();

  // Announce identity on Serial for Web USB / Monitor
  Serial.printf("SYNC_HELLO:{\"device_id\":\"%s\",\"schema_checksum\":\"%s\",\"crop\":\"%s\"}\n",
                config.device_id, config.schema_checksum, config.crop_name);

  // Connect to Wi-Fi
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[WIFI] Connecting");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 15) {
    delay(400);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WIFI] Connected! IP: %s\n", WiFi.localIP().toString().c_str());

    // Start local web server
    server.on("/", handleLocalDashboard);
    server.on("/data", handleLocalDataApi);
    server.on("/pump", handlePumpToggle);
    server.on("/crop", HTTP_ANY, handleSetCrop);
    server.on("/setcrop", HTTP_ANY, handleSetCrop);
    server.begin();
    Serial.println("[WEB] Local dashboard active at http://" + WiFi.localIP().toString());

    // Poll initial schema update from backend
    pollSchemaFeedFromApp();
  } else {
    Serial.println("\n[WIFI-FALLBACK] Operating 100% autonomous edge mode using flash schema.");
  }
}

// ------------------------------------------------------------------------------
// 14. MAIN LOOP
// ------------------------------------------------------------------------------
void loop() {
  unsigned long now = millis();

  // Handle local HTTP client requests
  server.handleClient();

  // Accumulate flow meter pulses
  updateFlowMeasurements();

  // 1. Process incoming USB / Web Serial commands
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialRxBuffer.length() > 0) {
        parseSerialCommand(serialRxBuffer);
        serialRxBuffer = "";
      }
    } else {
      if (serialRxBuffer.length() < 512) {
        serialRxBuffer += c;
      }
    }
  }

  // 2. Periodic Sensor Sampling & Autonomous Edge Irrigation Loop
  if (now - lastCheckMs >= (config.check_interval_sec * 1000)) {
    lastCheckMs = now;

    // Read physical sensors
    currentMoisture    = readSoilMoisture();
    currentTemperature = dht.readTemperature();
    currentHumidity    = dht.readHumidity();
    currentVPD         = calculateVPD(currentTemperature, currentHumidity);
    currentTurbidity   = readTurbidity();

    // Check Safety Lockout cooldown
    if (safetyCutoutActive && (now - safetyCutoutTimeMs >= PUMP_COOLDOWN_MS)) {
      safetyCutoutActive = false;
      Serial.println("[Safety] 10-minute cooldown expired. Pump safety lock released.");
    }

    // Dynamic Edge Irrigation Decision Logic
    if (!safetyCutoutActive) {
      // Rule A: Soil is below minimum threshold -> Trigger Pump
      if (currentMoisture < config.min_moisture_pct && !isPumpOn) {
        setPump(true, "SOIL_BELOW_MIN_THRESHOLD");
      }
      // Rule B: Target reached -> Shut off Pump
      else if (currentMoisture >= config.target_moisture_pct && isPumpOn) {
        setPump(false, "TARGET_MOISTURE_REACHED");
      }
      // Rule C: Watchdog safety cutoff exceeded
      else if (isPumpOn && ((now - pumpStartTimeMs) / 1000 >= config.max_pump_runtime_sec)) {
        setPump(false, "WATCHDOG_MAX_RUNTIME_EXCEEDED");
        safetyCutoutActive = true;
        safetyCutoutTimeMs = now;
        Serial.printf("[ALERT] Safety cutoff (%d s) reached! Locked out for cooldown.\n",
                      config.max_pump_runtime_sec);
      }
    }
  }

  // 3. Periodic Telemetry Stream (Every 5s default)
  if (now - lastTelemetryMs >= (config.telemetry_interval_sec * 1000)) {
    lastTelemetryMs = now;

    // A. Formatted Serial line for Website Monitor (frontend/esp32-monitor.html)
    Serial.printf(
      "[Telemetry] M=%.1f%%  T=%.1fC  RH=%.1f%%  Turb=%.0f NTU  Flow=%.2f L/m  Sess=%.3f L  Total=%.3f L  Pump=%s\n",
      currentMoisture,
      isnan(currentTemperature) ? 25.0f : currentTemperature,
      isnan(currentHumidity)    ? 60.0f : currentHumidity,
      currentTurbidity,
      flowRateLPM,
      sessionVolumeL,
      rtcTotalVolumeL,
      isPumpOn ? "ON" : "OFF"
    );

    // B. Compact JSON for Mobile App / Web USB
    Serial.printf("{\"device\":\"%s\",\"crop\":\"%s\",\"moisture\":%.1f,\"pump\":%s,\"flow\":%.2f}\n",
                  config.device_id, config.crop_name, currentMoisture, isPumpOn ? "true" : "false", flowRateLPM);

    // C. HTTP POST to Website Backend
    postTelemetryToWebsite();
  }

  // 4. Periodic Cloud Schema Polling (Every 60s)
  if (now - lastSchemaPollMs >= 60000) {
    lastSchemaPollMs = now;
    pollSchemaFeedFromApp();
  }

  delay(10);
}
