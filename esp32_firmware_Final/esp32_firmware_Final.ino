/*
 * =============================================================================
 *  SoilEdge Field Node -- v3.0  (Multi-Sensor + Flow Metering Edition)
 *
 *  Hardware wiring (per breadboard map):
 *    GPIO32 -> Soil Moisture AO       (ADC1, switched via 2N2222 on GPIO25)
 *    GPIO4  -> DHT11 Data pin         (10k pull-up to 3V3)
 *    GPIO34 -> Turbidity AO           (ADC1, 5V through 5.6k/10k divider)
 *    GPIO27 -> Water Flow Sensor sig  (hall-effect FALLING-edge, 10k pull-up 3V3)
 *    GPIO25 -> Soil-power transistor base (1k resistor -> 2N2222 base)
 *    GPIO26 -> Relay / pump
 *
 *  New in v3.0:
 *    - Flow rate (L/min) via ISR pulse counting on GPIO27
 *    - Per-session water volume (L) -- reset on each pump-ON event
 *    - Cumulative total volume (L)  -- RTC_DATA_ATTR, survives deep sleep
 *    - Turbidity (NTU) via voltage-divider corrected ADC
 *    - All values in web dashboard, /data JSON, and backend POST
 *
 *  Retained from v2:
 *    - VPD, Dew-point, Fungal risk, Depletion rate, Hours-to-wilting
 *    - Hysteresis irrigation (ON < 25%, OFF >= 60%)
 *    - 3-min fail-safe cutout + 10-min cooldown
 *    - Deep-sleep low-power mode (toggle ENABLE_DEEP_SLEEP)
 *    - Built-in dark-mode web dashboard + /data JSON API
 *    - FastAPI backend telemetry upload
 * =============================================================================
 */

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <math.h>
#include "esp_sleep.h"
#include "DHT.h"

// ---------------------------------------------------------------------------
// WiFi
// ---------------------------------------------------------------------------
const char* ssid     = "realme C67 5G";
const char* password = "abhi#302";

// ---------------------------------------------------------------------------
// Backend
// ---------------------------------------------------------------------------
const char* API_BASE        = "http://10.39.34.52:8000";
const char* DEVICE_TOKEN    = "esp32_secret_token_123";
const char* DEVICE_ID       = "esp32-01";
const bool  SEND_TO_BACKEND = true;

// ---------------------------------------------------------------------------
// Pin Definitions  (must match breadboard map)
// ---------------------------------------------------------------------------
#define SOIL_PIN        32   // Soil moisture AO   GPIO32  ADC1_CH4
#define DHTPIN           4   // DHT11 data         GPIO4
#define DHTTYPE      DHT11
#define TURBIDITY_PIN   34   // Turbidity AO       GPIO34  ADC1_CH6
#define FLOW_PIN        27   // Flow sensor signal GPIO27
#define SOIL_POWER_PIN  25   // 2N2222 base        GPIO25

// Active-Low Hardware Relays (GPIO 23 for Pump, GPIO 22 for Solenoid Valve)
#define PIN_PUMP_RELAY       23   // Main Pump Relay (GPIO 23)
#define PIN_FERTILIZER_VALVE 22   // Solenoid Fertilizer Valve (GPIO 22)
#define RELAY_PIN            23   // Alias for backwards compatibility
#define ONBOARD_LED_PIN       2   // Onboard Blue LED (GPIO 2) mirrors Pump state
#define WEBSERVER_PORT       80   // Standard HTTP Port 80 for direct browser access without typing :8000

// Set to true if using a standard Relay Module (active-LOW)
// Set to false if using an NPN Transistor (2N2222 / TIP120) / MOSFET / Motor Driver (active-HIGH)
#define RELAY_ACTIVE_LOW true

// ---------------------------------------------------------------------------
// Soil Moisture Calibration
// ---------------------------------------------------------------------------
const int DRY_VALUE = 3300;  // ADC raw in dry air
const int WET_VALUE = 1400;  // ADC raw fully submerged

// ---------------------------------------------------------------------------
// Flow Sensor Calibration
// YF-S201 default:  K = 7.5 pulses/s = 1 L/min
// Adjust if sensor body shows a different model number.
// ---------------------------------------------------------------------------
const float FLOW_K_FACTOR = 7.5f;

// ---------------------------------------------------------------------------
// Turbidity Calibration
// Divider ratio: 10k / (5.6k + 10k) = 0.641  -> attenuates 5V to <3.3V
// Typical sensor output: ~4.2V @ clear (0 NTU),  ~2.5V @ muddy (~3000 NTU)
// ---------------------------------------------------------------------------
const float DIVIDER_RATIO = 10000.0f / (5600.0f + 10000.0f);  // 0.6410
const float TURB_V_CLEAR  = 4.20f;
const float TURB_V_MUDDY  = 2.50f;
const float TURB_NTU_MAX  = 3000.0f;

// ---------------------------------------------------------------------------
// Irrigation Thresholds
// ---------------------------------------------------------------------------
const float MOISTURE_LOW_THRESHOLD  = 25.0f;
const float MOISTURE_HIGH_THRESHOLD = 60.0f;
const float WILTING_POINT_MOISTURE  = 15.0f;

// ---------------------------------------------------------------------------
// Safety Timers
// ---------------------------------------------------------------------------
const unsigned long MAX_PUMP_RUN_MS    = 180000;  // 3 min fail-safe cutout
const unsigned long PUMP_COOLDOWN_MS   = 600000;  // 10 min post-cutout cooldown
const unsigned long UPLOAD_INTERVAL_MS =   5000;  // telemetry cadence (ms)
const unsigned long FLOW_CALC_INTERVAL =   1000;  // flow rate update period (ms)

// ---------------------------------------------------------------------------
// Deep Sleep (optional)
// ---------------------------------------------------------------------------
const bool     ENABLE_DEEP_SLEEP      = false;
const uint64_t SLEEP_DURATION_SECONDS = 60;

// ---------------------------------------------------------------------------
// RTC Slow Memory -- preserved across deep sleep cycles
// ---------------------------------------------------------------------------
RTC_DATA_ATTR unsigned long rtc_boot_count          = 0;
RTC_DATA_ATTR float         rtc_last_moisture       = -1.0f;
RTC_DATA_ATTR unsigned long rtc_last_sample_time_ms = 0;
RTC_DATA_ATTR float         rtc_depletion_rate      = 0.0f;
RTC_DATA_ATTR bool          rtc_safety_lockout      = false;
RTC_DATA_ATTR unsigned long rtc_lockout_start_time  = 0;
RTC_DATA_ATTR float         rtc_total_volume_L      = 0.0f;  // *** cumulative litres pumped ***

// ---------------------------------------------------------------------------
// Global Runtime State
// ---------------------------------------------------------------------------
DHT       dht(DHTPIN, DHTTYPE);
WebServer server(WEBSERVER_PORT);

// Dynamic Crop Profiles & Runtime Overrides
String activeCropName         = "Tomato";
float  cropMinMoist           = 25.0f;
float  cropTargetMoist        = 60.0f;
int    cropMaxPumpRunSec      = 180;

bool          pumpActive             = false;
unsigned long pumpStartTime          = 0;
bool          safetyCutoutActive     = false;
unsigned long safetyCutoutTime       = 0;
unsigned long lastUploadTime         = 0;
unsigned long lastDepletionCheckTime = 0;
float         lastSampleMoisture     = -1.0f;
float         currentDepletionRate   = 0.0f;  // %/hr

// Flow sensor
volatile unsigned long pulseCount   = 0;      // ISR accumulator
unsigned long          lastFlowCalc = 0;
float                  flowRateLPM  = 0.0f;   // current flow rate (L/min)
float                  sessionVolL  = 0.0f;   // litres pumped this irrigation session

// ---------------------------------------------------------------------------
// ISR  -- count hall-effect pulses (kept in IRAM for speed)
// ---------------------------------------------------------------------------
void IRAM_ATTR onFlowPulse() {
  pulseCount++;
}

// ===========================================================================
//  setPump()  -- manages relay AND session volume counter
// ===========================================================================
void setPump(bool enable) {
  if (enable && !pumpActive) {
    // New irrigation session begins -- reset the session volume counter
    sessionVolL   = 0.0f;
    pumpStartTime = millis();
    Serial.println("[Flow] Irrigation session started -- session volume reset to 0 L.");
  }
  pumpActive = enable;
  digitalWrite(ONBOARD_LED_PIN, enable ? HIGH : LOW); // Built-in blue LED mirrors pump state
  if (RELAY_ACTIVE_LOW)
    digitalWrite(PIN_PUMP_RELAY, enable ? LOW : HIGH);
  else
    digitalWrite(PIN_PUMP_RELAY, enable ? HIGH : LOW);
  Serial.printf("[Actuator] Pump Motor (GPIO %d): %s\n", PIN_PUMP_RELAY, enable ? "ON" : "OFF");
}

bool isFertilizerOn = false;
unsigned long fertStartTime = 0;

void setFertilizerValve(bool enable) {
  isFertilizerOn = enable;
  if (enable) fertStartTime = millis();
  if (RELAY_ACTIVE_LOW)
    digitalWrite(PIN_FERTILIZER_VALVE, enable ? LOW : HIGH);
  else
    digitalWrite(PIN_FERTILIZER_VALVE, enable ? HIGH : LOW);
  Serial.printf("[Actuator] Fertilizer Valve (GPIO %d): %s\n", PIN_FERTILIZER_VALVE, enable ? "OPEN" : "CLOSED");
}

// ===========================================================================
//  updateFlowMeasurements()
//  Call every loop(). Refreshes flowRateLPM every 1 s and accumulates
//  session/total volume while the pump is active.
// ===========================================================================
void updateFlowMeasurements() {
  unsigned long now = millis();
  if (now - lastFlowCalc < FLOW_CALC_INTERVAL) return;

  // Atomic snapshot of ISR counter
  noInterrupts();
  unsigned long pulses = pulseCount;
  pulseCount = 0;
  interrupts();

  float elapsedSec = (now - lastFlowCalc) / 1000.0f;
  lastFlowCalc = now;

  // Flow rate:  (pulses/s) / K_factor  =  L/min
  float pps   = pulses / elapsedSec;
  flowRateLPM = pps / FLOW_K_FACTOR;
  if (flowRateLPM < 0.0f) flowRateLPM = 0.0f;

  // Accumulate volume ONLY while relay is ON
  //   Volume (L)  =  rate (L/min)  x  time (min)
  if (pumpActive && flowRateLPM > 0.0f) {
    float addedL        = flowRateLPM * (elapsedSec / 60.0f);
    sessionVolL        += addedL;
    rtc_total_volume_L += addedL;   // persistent across deep-sleep boots
  }
}

// ===========================================================================
//  Turbidity: ADC raw -> NTU
// ===========================================================================
float readTurbidityNTU() {
  int   raw     = analogRead(TURBIDITY_PIN);
  float adcV    = raw * (3.3f / 4095.0f);
  float sensorV = adcV / DIVIDER_RATIO;    // undo voltage divider

  // Linear interpolation:
  //   sensorV == TURB_V_CLEAR  ->  0 NTU
  //   sensorV == TURB_V_MUDDY  ->  TURB_NTU_MAX
  float ntu = ((TURB_V_CLEAR - sensorV) / (TURB_V_CLEAR - TURB_V_MUDDY)) * TURB_NTU_MAX;
  return constrain(ntu, 0.0f, TURB_NTU_MAX);
}

String getTurbidityStatus(float ntu) {
  if (ntu <   1.0f) return "Crystal Clear (< 1 NTU)";
  if (ntu <   5.0f) return "Clear (Drinking Grade)";
  if (ntu <  50.0f) return "Slightly Turbid";
  if (ntu < 200.0f) return "Turbid (Monitor Sediment)";
  return "Very Turbid (High Sediment)";
}

// ===========================================================================
//  Soil Moisture %
// ===========================================================================
float getSoilMoisturePercentage(int rawVal) {
  int pct = map(rawVal, DRY_VALUE, WET_VALUE, 0, 100);
  return (float)constrain(pct, 0, 100);
}

// ===========================================================================
//  VPD (kPa)
// ===========================================================================
float calculateVPD(float tempC, float humidity) {
  if (isnan(tempC) || isnan(humidity) || humidity <= 0.0f) return 0.0f;
  float vpSat = 0.61078f * exp((17.27f * tempC) / (tempC + 237.3f));
  float vpd   = vpSat * (1.0f - humidity / 100.0f);
  return (vpd < 0.0f) ? 0.0f : vpd;
}
String getVPDStatus(float vpd) {
  if (vpd < 0.40f)  return "Low Transpiration (High Humidity)";
  if (vpd <= 1.20f) return "Optimal Vegetative Zone";
  if (vpd <= 1.60f) return "Mild Transpiration Stress";
  return "High Moisture Stress (Stomata Closing)";
}

// ===========================================================================
//  Dew Point & Fungal Risk
// ===========================================================================
float calculateDewPoint(float tempC, float humidity) {
  if (isnan(tempC) || isnan(humidity) || humidity <= 0.0f) return 0.0f;
  float alpha = ((17.27f * tempC) / (237.3f + tempC)) + log(humidity / 100.0f);
  return (237.3f * alpha) / (17.27f - alpha);
}
String getFungalRisk(float tempC, float dp, float humidity) {
  if (isnan(tempC) || isnan(humidity)) return "Unknown";
  float delta = tempC - dp;
  if (delta <= 2.0f || humidity >= 85.0f) return "HIGH (Condensation / Mold Hazard)";
  if (delta <= 4.0f || humidity >= 75.0f) return "MODERATE (Monitor Closely)";
  return "LOW (Healthy Aeration)";
}

// ===========================================================================
//  Soil Depletion Rate & Hours to Wilting
// ===========================================================================
void updateDepletionRate(float moisture) {
  unsigned long now = millis();
  if (lastSampleMoisture < 0.0f) {
    lastSampleMoisture     = moisture;
    lastDepletionCheckTime = now;
    return;
  }
  unsigned long elapsed = now - lastDepletionCheckTime;
  if (elapsed >= 60000) {
    float delta = lastSampleMoisture - moisture;
    float hours = elapsed / 3600000.0f;
    if (hours > 0.0f) {
      float rate = delta / hours;
      currentDepletionRate = currentDepletionRate * 0.7f + rate * 0.3f;
    }
    lastSampleMoisture     = moisture;
    lastDepletionCheckTime = now;
  }
}
float getHoursToWiltingPoint(float moisture) {
  if (currentDepletionRate <= 0.05f)          return -1.0f;
  if (moisture <= WILTING_POINT_MOISTURE)      return  0.0f;
  return (moisture - WILTING_POINT_MOISTURE) / currentDepletionRate;
}

// ===========================================================================
//  Smart Irrigation: Hysteresis + Fail-Safe Cutout
// ===========================================================================
void evaluateIrrigationLogic(float moisture) {
  unsigned long now = millis();

  // Reset lockout after cooldown
  if (safetyCutoutActive && (now - safetyCutoutTime >= PUMP_COOLDOWN_MS)) {
    safetyCutoutActive = false;
    Serial.println("[Safety] 10-min cooldown complete. Pump lock cleared.");
  }

  // Fail-safe 3-min run timer
  if (pumpActive && (now - pumpStartTime >= MAX_PUMP_RUN_MS)) {
    setPump(false);
    safetyCutoutActive = true;
    safetyCutoutTime   = now;
    Serial.printf("[ALERT] 3-min max timer! Session: %.3f L | Total: %.3f L. Cutout engaged.\n",
                  sessionVolL, rtc_total_volume_L);
    return;
  }
  if (safetyCutoutActive) { setPump(false); return; }

  // Hysteresis state machine
  if (moisture < MOISTURE_LOW_THRESHOLD) {
    if (!pumpActive) {
      setPump(true);
      Serial.printf("[Irrigation] Moisture %.1f%% < %.1f%% -- Pump ON\n",
                    moisture, MOISTURE_LOW_THRESHOLD);
    }
  } else if (moisture >= MOISTURE_HIGH_THRESHOLD) {
    if (pumpActive) {
      setPump(false);
      Serial.printf("[Irrigation] %.1f%% target reached -- Pump OFF | Session: %.3f L | Total: %.3f L\n",
                    MOISTURE_HIGH_THRESHOLD, sessionVolL, rtc_total_volume_L);
    }
  }
}

// ===========================================================================
//  Web Dashboard (auto-refreshes every 4 s)
// ===========================================================================
void handleRoot() {
  // Read all sensors
  digitalWrite(SOIL_POWER_PIN, HIGH);
  delay(10);
  int   rawADC   = analogRead(SOIL_PIN);
  float soilV    = rawADC * (3.3f / 4095.0f);
  float moisture = getSoilMoisturePercentage(rawADC);
  digitalWrite(SOIL_POWER_PIN, LOW);

  float tempC    = dht.readTemperature();
  float humidity = dht.readHumidity();
  float vpd      = calculateVPD(tempC, humidity);
  float dp       = calculateDewPoint(tempC, humidity);
  float wiltHrs  = getHoursToWiltingPoint(moisture);
  float turbNTU  = readTurbidityNTU();

  // ---- Build HTML ----
  String h;
  h.reserve(6000);
  h = "<!DOCTYPE html><html lang='en'><head>"
      "<meta charset='utf-8'>"
      "<meta name='viewport' content='width=device-width,initial-scale=1'>"
      "<meta http-equiv='refresh' content='4'>"
      "<title>SoilEdge v3 Field Gateway</title>"
      "<style>"
      "*{box-sizing:border-box}"
      "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;"
        "background:#090d16;color:#f1f5f9;margin:0;padding:20px}"
      ".hdr{max-width:1080px;margin:0 auto 20px;display:flex;justify-content:space-between;"
        "align-items:center;border-bottom:1px solid #1e293b;padding-bottom:14px}"
      "h1{font-size:22px;color:#10b981;margin:0}"
      ".chip{background:#1e293b;border:1px solid #334155;padding:4px 12px;"
        "border-radius:999px;font-size:12px;color:#94a3b8}"
      ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));"
        "gap:16px;max-width:1080px;margin:0 auto}"
      ".card{background:#131b2e;border:1px solid #1e293b;border-radius:14px;"
        "padding:18px;box-shadow:0 4px 16px rgba(0,0,0,.25)}"
      ".ct{font-size:11px;text-transform:uppercase;letter-spacing:1.2px;"
        "color:#64748b;font-weight:700;margin-bottom:8px}"
      ".val{font-size:34px;font-weight:800;color:#38bdf8;line-height:1.1}"
      ".unit{font-size:18px;font-weight:500;color:#94a3b8}"
      ".desc{font-size:13px;color:#94a3b8;margin-top:6px}"
      ".bdg{display:inline-block;padding:3px 10px;border-radius:9999px;"
        "font-size:11px;font-weight:600;margin-top:8px}"
      ".g{background:rgba(16,185,129,.15);color:#34d399;border:1px solid rgba(16,185,129,.3)}"
      ".a{background:rgba(245,158,11,.15);color:#fbbf24;border:1px solid rgba(245,158,11,.3)}"
      ".r{background:rgba(239,68,68,.15);color:#f87171;border:1px solid rgba(239,68,68,.3)}"
      ".b{background:rgba(56,189,248,.15);color:#38bdf8;border:1px solid rgba(56,189,248,.3)}"
      ".c{background:rgba(34,211,238,.15);color:#22d3ee;border:1px solid rgba(34,211,238,.3)}"
      ".bar{background:#1e293b;height:6px;border-radius:999px;overflow:hidden;margin-top:10px}"
      ".bf{height:100%;border-radius:999px}"
      ".vr{display:flex;justify-content:space-between;align-items:baseline;"
        "margin-top:10px;border-top:1px solid #1e293b;padding-top:10px}"
      ".vl{font-size:12px;color:#64748b}"
      ".vv{font-size:20px;font-weight:700;color:#22d3ee}"
      ".ft{max-width:1080px;margin:24px auto 0;text-align:center;font-size:12px;color:#475569}"
      "</style></head><body>";

  h += "<div class='hdr'><div><h1>&#127807; SoilEdge Field Gateway</h1>"
       "<div style='color:#64748b;font-size:13px;margin-top:3px'>Node: <b>"
       + String(DEVICE_ID) + "</b> &bull; Boot #" + String(rtc_boot_count) + "</div></div>"
       "<div class='chip'>RSSI: <b>" + String(WiFi.RSSI()) + " dBm</b></div></div>";
  h += "<div class='grid'>";

  // --- Card 1: Soil Moisture ---
  h += "<div class='card'><div class='ct'>Soil Moisture &amp; Hysteresis</div>"
       "<div class='val'>" + String((int)moisture) + "<span class='unit'>%</span></div>"
       "<div class='bar'><div class='bf' style='width:" + String((int)moisture)
       + "%;background:linear-gradient(90deg,#f59e0b,#10b981)'></div></div>"
       "<div class='desc'>ADC: <b>" + String(rawADC) + "</b> &bull; <b>" + String(soilV,2) + " V</b></div>"
       "<div class='desc'>Bands: ON &lt; <b>" + String((int)MOISTURE_LOW_THRESHOLD)
       + "%</b> &bull; OFF &ge; <b>" + String((int)MOISTURE_HIGH_THRESHOLD) + "%</b></div></div>";

  // --- Card 2: Pump Actuator ---
  h += "<div class='card'><div class='ct'>Pump Actuator (Relay GPIO" + String(RELAY_PIN) + ")</div>";
  if (safetyCutoutActive) {
    h += "<div class='val' style='color:#ef4444'>LOCKOUT</div>"
         "<span class='bdg r'>Fail-Safe Cutout (3-min limit)</span>"
         "<div class='desc' style='margin-top:8px'>Flood protection active</div>";
  } else if (pumpActive) {
    unsigned long runSec = (millis() - pumpStartTime) / 1000;
    h += "<div class='val' style='color:#10b981'>ACTIVE</div>"
         "<span class='bdg g'>Pumping (" + String(runSec) + " s / 180 s max)</span>";
  } else {
    h += "<div class='val' style='color:#94a3b8'>IDLE</div>"
         "<span class='bdg b'>Triggers below " + String((int)MOISTURE_LOW_THRESHOLD) + "%</span>";
  }
  h += "</div>";

  // --- Card 3: WATER FLOW & VOLUME (new) ---
  h += "<div class='card'><div class='ct'>&#128167; Water Flow &amp; Volume Pumped</div>"
       "<div class='val'>" + String(flowRateLPM, 2) + "<span class='unit'> L/min</span></div>";
  if (pumpActive)
    h += "<span class='bdg c'>Actively flowing</span>";
  else if (sessionVolL > 0.001f)
    h += "<span class='bdg b'>Last session complete</span>";
  else
    h += "<span class='bdg b'>No flow detected</span>";
  h += "<div class='vr'>"
         "<div><div class='vl'>This Session</div>"
         "<div class='vv'>" + String(sessionVolL, 3) + " L</div></div>"
         "<div style='text-align:right'><div class='vl'>Cumulative Total</div>"
         "<div class='vv'>" + String(rtc_total_volume_L, 2) + " L</div></div>"
       "</div>"
       "<div class='desc'>GPIO27 &bull; K=" + String(FLOW_K_FACTOR, 1) + " pulses/s per L/min</div></div>";

  // --- Card 4: Turbidity ---
  String tSt  = getTurbidityStatus(turbNTU);
  String tBdg = (turbNTU < 5.0f) ? "g" : (turbNTU < 200.0f ? "a" : "r");
  h += "<div class='card'><div class='ct'>Water Turbidity</div>"
       "<div class='val'>" + String((int)turbNTU) + "<span class='unit'> NTU</span></div>"
       "<span class='bdg " + tBdg + "'>" + tSt + "</span>"
       "<div class='bar'><div class='bf' style='width:"
       + String(constrain((int)(turbNTU / 30.0f), 0, 100))
       + "%;background:linear-gradient(90deg,#22d3ee,#ef4444)'></div></div>"
       "<div class='desc'>GPIO34 via 5.6k/10k divider</div></div>";

  // --- Card 5: VPD ---
  String vSt  = getVPDStatus(vpd);
  String vBdg = (vpd >= 0.40f && vpd <= 1.20f) ? "g" : (vpd <= 1.60f ? "a" : "r");
  h += "<div class='card'><div class='ct'>Vapor Pressure Deficit</div>"
       "<div class='val'>" + String(vpd, 2) + "<span class='unit'> kPa</span></div>"
       "<span class='bdg " + vBdg + "'>" + vSt + "</span>"
       "<div class='desc' style='margin-top:8px'>On-chip calculation from T &amp; RH</div></div>";

  // --- Card 6: Dew Point / Fungal Risk ---
  String fRisk = getFungalRisk(tempC, dp, humidity);
  String fBdg  = fRisk.startsWith("HIGH") ? "r" : (fRisk.startsWith("MOD") ? "a" : "g");
  h += "<div class='card'><div class='ct'>Dew Point &amp; Fungal Risk</div>"
       "<div class='val'>" + String(dp, 1) + "<span class='unit'> &deg;C</span></div>"
       "<span class='bdg " + fBdg + "'>" + fRisk + "</span>"
       "<div class='desc' style='margin-top:8px'>Margin: <b>" + String(tempC - dp, 1) + " &deg;C</b></div></div>";

  // --- Card 7: Ambient Climate ---
  h += "<div class='card'><div class='ct'>Ambient Microclimate (DHT11)</div>"
       "<div class='val'>" + String(tempC, 1) + "<span class='unit'> &deg;C</span></div>"
       "<div class='desc' style='margin-top:4px'>Humidity: <b style='color:#38bdf8;font-size:16px'>"
       + String(humidity, 1) + "%</b></div>"
       "<div class='bar'><div class='bf' style='width:" + String((int)humidity)
       + "%;background:#38bdf8'></div></div></div>";

  // --- Card 8: Depletion Forecast ---
  h += "<div class='card'><div class='ct'>Soil Depletion &amp; Wilting Forecast</div>";
  if (currentDepletionRate > 0.05f) {
    h += "<div class='val' style='color:#f59e0b'>-" + String(currentDepletionRate, 2)
         + "<span class='unit'> %/hr</span></div>";
    h += (wiltHrs >= 0.0f)
         ? "<span class='bdg a'>Wilting in ~" + String(wiltHrs, 1) + " hrs</span>"
         : "<span class='bdg r'>Critically Dry</span>";
  } else {
    h += "<div class='val' style='color:#34d399'>Stable</div>"
         "<span class='bdg g'>Moisture Equilibrium</span>";
  }
  h += "<div class='desc' style='margin-top:8px'>Wilting threshold: <b>"
       + String((int)WILTING_POINT_MOISTURE) + "%</b></div></div>";

  h += "</div>";  // end grid
  h += "<div class='ft'>Auto-refresh 4 s &bull; " + WiFi.localIP().toString()
       + " &bull; SoilEdge v3.0</div></body></html>";

  server.send(200, "text/html", h);
}

// ===========================================================================
//  JSON /data API endpoint
// ===========================================================================
void handleDataJson() {
  digitalWrite(SOIL_POWER_PIN, HIGH);
  delay(10);
  int   rawADC   = analogRead(SOIL_PIN);
  float soilV    = rawADC * (3.3f / 4095.0f);
  float moisture = getSoilMoisturePercentage(rawADC);
  digitalWrite(SOIL_POWER_PIN, LOW);

  float tempC    = dht.readTemperature();
  float humidity = dht.readHumidity();
  float vpd      = calculateVPD(tempC, humidity);
  float dp       = calculateDewPoint(tempC, humidity);
  float wiltHrs  = getHoursToWiltingPoint(moisture);
  float turbNTU  = readTurbidityNTU();

  String j;
  j.reserve(1024);
  j = "{";
  j += "\"device_id\":\""           + String(DEVICE_ID)               + "\",";
  j += "\"boot_count\":"            + String(rtc_boot_count)          + ",";
  j += "\"moisture\":"              + String(moisture, 2)             + ",";
  j += "\"soil_raw\":"              + String(rawADC)                  + ",";
  j += "\"soil_voltage\":"          + String(soilV, 2)                + ",";
  j += "\"temperature\":"           + (isnan(tempC)    ? "null" : String(tempC, 2))    + ",";
  j += "\"humidity\":"              + (isnan(humidity) ? "null" : String(humidity, 2)) + ",";
  j += "\"vpd_kpa\":"               + String(vpd, 2)                  + ",";
  j += "\"vpd_status\":\""          + getVPDStatus(vpd)               + "\",";
  j += "\"dew_point_c\":"           + String(dp, 2)                   + ",";
  j += "\"fungal_risk\":\""         + getFungalRisk(tempC, dp, humidity) + "\",";
  j += "\"turbidity_ntu\":"         + String(turbNTU, 1)              + ",";
  j += "\"turbidity_status\":\""    + getTurbidityStatus(turbNTU)     + "\",";
  j += "\"flow_rate_lpm\":"         + String(flowRateLPM, 3)          + ",";
  j += "\"session_volume_L\":"      + String(sessionVolL, 4)          + ",";
  j += "\"total_volume_L\":"        + String(rtc_total_volume_L, 4)   + ",";
  j += "\"depletion_rate_pct_hr\":" + String(currentDepletionRate, 3) + ",";
  j += "\"hours_to_wilting\":"      + String(wiltHrs, 1)              + ",";
  j += "\"pump_active\":"           + String(pumpActive         ? "true" : "false") + ",";
  j += "\"safety_lockout\":"        + String(safetyCutoutActive ? "true" : "false") + ",";
  j += "\"wifi_rssi\":"             + String(WiFi.RSSI());
  j += "}";

  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.send(200, "application/json", j);
}

// ===========================================================================
//  Backend POST (extended with turbidity + flow fields)
// ===========================================================================
void postTelemetryToBackend(float moisture, float temp, float humid,
                             bool pumpState, float turbNTU) {
  if (!SEND_TO_BACKEND || WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  String targetUrl = String(API_BASE) + "/api/esp/telemetry";

  if (targetUrl.startsWith("https://")) {
    WiFiClientSecure secureClient;
    secureClient.setInsecure();
    http.begin(secureClient, targetUrl);
  } else {
    http.begin(targetUrl);
  }

  http.addHeader("Content-Type", "application/json");
  if (strlen(DEVICE_TOKEN) > 0)
    http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);

  String action = pumpState ? "HYSTERESIS_IRRIGATION_ON" : "STANDBY";
  if (safetyCutoutActive) action = "SAFETY_CUTOUT_ENGAGED";

  String body;
  body.reserve(512);
  body = "{";
  body += "\"device_id\":\""       + String(DEVICE_ID)               + "\",";
  body += "\"moisture\":"          + String(moisture, 2)             + ",";
  body += "\"temperature\":"       + (isnan(temp)  ? "null" : String(temp, 2))       + ",";
  body += "\"humidity\":"          + (isnan(humid) ? "null" : String(humid, 2))     + ",";
  body += "\"turbidity_ntu\":"     + String(turbNTU, 1)              + ",";
  body += "\"flow_rate_lpm\":"     + String(flowRateLPM, 3)          + ",";
  body += "\"session_volume_L\":"  + String(sessionVolL, 4)          + ",";
  body += "\"total_volume_L\":"    + String(rtc_total_volume_L, 4)   + ",";
  body += "\"pump\":"              + String(pumpState ? "true" : "false") + ",";
  body += "\"fertilizer\":"        + String(isFertilizerOn ? "true" : "false") + ",";
  body += "\"action_name\":\""     + action                          + "\"";
  body += "}";

  int code = http.POST(body);
  if (code > 0)
    Serial.printf("[Backend] POST HTTP %d\n", code);
  else
    Serial.printf("[Backend] Error: %s\n", http.errorToString(code).c_str());
  http.end();
}

// ===========================================================================
//  setup()
// ===========================================================================

void setCorsHeaders() {
  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  server.sendHeader("Access-Control-Allow-Headers", "*");
}

void handleTelemetryApi() {
  setCorsHeaders();
  
  // Power soil sensor, read, cut power
  digitalWrite(SOIL_POWER_PIN, HIGH);
  delay(10);
  int rawADC = analogRead(SOIL_PIN);
  float moisture = getSoilMoisturePercentage(rawADC);
  digitalWrite(SOIL_POWER_PIN, LOW);

  float tempC = dht.readTemperature();
  float humidity = dht.readHumidity();
  float vpd = calculateVPD(tempC, humidity);
  float turbNTU = readTurbidityNTU();

  String json = "{";
  json += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  json += "\"moisture_pct\":" + String(moisture, 1) + ",";
  json += "\"raw_adc\":" + String(rawADC) + ",";
  json += "\"temperature\":" + (isnan(tempC) ? "null" : String(tempC, 1)) + ",";
  json += "\"humidity\":" + (isnan(humidity) ? "null" : String(humidity, 1)) + ",";
  json += "\"vpd\":" + (isnan(vpd) ? "null" : String(vpd, 2)) + ",";
  json += "\"turbidity_ntu\":" + String(turbNTU, 1) + ",";
  json += "\"flow_rate_lpm\":" + String(flowRateLPM, 2) + ",";
  json += "\"session_volume_L\":" + String(sessionVolL, 3) + ",";
  json += "\"total_volume_L\":" + String(rtc_total_volume_L, 3) + ",";
  json += "\"pump_active\":" + String(pumpActive ? "true" : "false") + ",";
  json += "\"fertilizer_active\":" + String(isFertilizerOn ? "true" : "false") + ",";
  json += "\"relay_pin\":23,";
  json += "\"valve_pin\":22,";
  json += "\"port\":8000,";
  json += "\"crop\":\"" + activeCropName + "\",";
  json += "\"mode\":\"ACTIVE_LOW\"";
  json += "}";

  server.send(200, "application/json", json);
}

void handleSetCropApi() {
  setCorsHeaders();
  String crop = "";
  if (server.hasArg("crop")) crop = server.arg("crop");
  else if (server.hasArg("name")) crop = server.arg("name");
  
  if (crop.length() > 0) {
    activeCropName = crop;
    crop.toLowerCase();
    if (crop.indexOf("tomato") >= 0) { cropMinMoist = 28.0; cropTargetMoist = 65.0; cropMaxPumpRunSec = 180; }
    else if (crop.indexOf("wheat") >= 0) { cropMinMoist = 22.0; cropTargetMoist = 50.0; cropMaxPumpRunSec = 240; }
    else if (crop.indexOf("rice") >= 0) { cropMinMoist = 50.0; cropTargetMoist = 85.0; cropMaxPumpRunSec = 360; }
    else if (crop.indexOf("cotton") >= 0) { cropMinMoist = 20.0; cropTargetMoist = 45.0; cropMaxPumpRunSec = 180; }
    else if (crop.indexOf("sugarcane") >= 0) { cropMinMoist = 35.0; cropTargetMoist = 70.0; cropMaxPumpRunSec = 300; }
    else if (crop.indexOf("maize") >= 0) { cropMinMoist = 25.0; cropTargetMoist = 60.0; cropMaxPumpRunSec = 200; }
    else if (crop.indexOf("potato") >= 0) { cropMinMoist = 30.0; cropTargetMoist = 70.0; cropMaxPumpRunSec = 180; }
    else if (crop.indexOf("chilli") >= 0) { cropMinMoist = 25.0; cropTargetMoist = 65.0; cropMaxPumpRunSec = 180; }

    Serial.printf("[WIFI-CROP] Crop set to %s (Min: %.1f%%, Target: %.1f%%)\n", activeCropName.c_str(), cropMinMoist, cropTargetMoist);
    server.send(200, "application/json", "{\"status\":\"success\",\"crop\":\"" + activeCropName + "\",\"min_moisture\":" + String(cropMinMoist,1) + "}");
  } else {
    server.send(400, "application/json", "{\"error\":\"Missing crop parameter\"}");
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  rtc_boot_count++;
  Serial.println("\n================================================");
  Serial.printf("  SoilEdge Smart Node v3.0  (Boot #%lu)\n", rtc_boot_count);
  Serial.println("================================================");
  Serial.printf("  Cumulative water pumped so far: %.3f L\n", rtc_total_volume_L);

  analogSetAttenuation(ADC_11db);         // 0-3.3V range on all ADC pins
  pinMode(SOIL_PIN,       INPUT);
  pinMode(TURBIDITY_PIN,  INPUT);
  pinMode(SOIL_POWER_PIN, OUTPUT);
  digitalWrite(SOIL_POWER_PIN, LOW);      // soil sensor power OFF on boot

  // --- Boot Safe-State (Prevents Relay Clicks at Boot) ---
  digitalWrite(PIN_PUMP_RELAY,       RELAY_ACTIVE_LOW ? HIGH : LOW);
  pinMode(PIN_PUMP_RELAY,            OUTPUT);
  digitalWrite(PIN_FERTILIZER_VALVE, RELAY_ACTIVE_LOW ? HIGH : LOW);
  pinMode(PIN_FERTILIZER_VALVE,      OUTPUT);
  digitalWrite(ONBOARD_LED_PIN,      LOW);
  pinMode(ONBOARD_LED_PIN,           OUTPUT);

  setPump(false);                         // Pump relay OFF on boot
  setFertilizerValve(false);              // Solenoid valve CLOSED on boot

  dht.begin();

  // Attach flow sensor interrupt
  pinMode(FLOW_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(FLOW_PIN), onFlowPulse, FALLING);
  lastFlowCalc = millis();

  // WiFi connect (15 s timeout -> offline mode)
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
    delay(400);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED)
    Serial.println("\n[WiFi] Connected: " + WiFi.localIP().toString());
  else
    Serial.println("\n[WiFi] Timeout -- offline autonomous mode.");

  // Deep-sleep duty cycle (sample -> act -> upload -> sleep)
  if (ENABLE_DEEP_SLEEP) {
    Serial.println("[Power] Ultra-low-power duty cycle ...");
    digitalWrite(SOIL_POWER_PIN, HIGH);
    delay(10);
    int   raw      = analogRead(SOIL_PIN);
    float moisture = getSoilMoisturePercentage(raw);
    float tempC    = dht.readTemperature();
    float humidity = dht.readHumidity();
    float turbNTU  = readTurbidityNTU();
    delay(1000);
    updateFlowMeasurements();   // gather 1 s of pulses
    digitalWrite(SOIL_POWER_PIN, LOW);

    if (!isnan(tempC) && !isnan(humidity)) {
      updateDepletionRate(moisture);
      evaluateIrrigationLogic(moisture);
      postTelemetryToBackend(moisture, tempC, humidity, pumpActive, turbNTU);
    }
    Serial.printf("[Power] Session: %.3f L | Total: %.3f L\n",
                  sessionVolL, rtc_total_volume_L);
    esp_sleep_enable_timer_wakeup(SLEEP_DURATION_SECONDS * 1000000ULL);
    esp_deep_sleep_start();
  }

  // Continuous server mode
  // Continuous server mode - Port 8000 (Supports Direct LAN, App & Website)
  server.on("/",     handleRoot);
  server.on("/data", handleDataJson);
  
  // App & Dashboard Telemetry with CORS
  server.on("/telemetry", HTTP_OPTIONS, []() { setCorsHeaders(); server.send(204); });
  server.on("/telemetry", HTTP_GET,     handleTelemetryApi);

  // App & Dashboard Direct Actuation Controls
  server.on("/pump/on", HTTP_OPTIONS, []() { setCorsHeaders(); server.send(204); });
  server.on("/pump/on", HTTP_GET, []() {
    setPump(true);
    setCorsHeaders();
    server.send(200, "application/json", "{\"status\":\"OK\",\"pump\":true}");
  });
  server.on("/pump/on", HTTP_POST, []() {
    setPump(true);
    setCorsHeaders();
    server.send(200, "application/json", "{\"status\":\"OK\",\"pump\":true}");
  });

  server.on("/pump/off", HTTP_OPTIONS, []() { setCorsHeaders(); server.send(204); });
  server.on("/pump/off", HTTP_GET, []() {
    setPump(false);
    setCorsHeaders();
    server.send(200, "application/json", "{\"status\":\"OK\",\"pump\":false}");
  });
  server.on("/pump/off", HTTP_POST, []() {
    setPump(false);
    setCorsHeaders();
    server.send(200, "application/json", "{\"status\":\"OK\",\"pump\":false}");
  });

  server.on("/valve/on", HTTP_OPTIONS, []() { setCorsHeaders(); server.send(204); });
  server.on("/valve/on", HTTP_GET, []() {
    setFertilizerValve(true);
    setCorsHeaders();
    server.send(200, "application/json", "{\"status\":\"OK\",\"fertilizer\":true}");
  });

  server.on("/valve/off", HTTP_OPTIONS, []() { setCorsHeaders(); server.send(204); });
  server.on("/valve/off", HTTP_GET, []() {
    setFertilizerValve(false);
    setCorsHeaders();
    server.send(200, "application/json", "{\"status\":\"OK\",\"fertilizer\":false}");
  });

  // Fertilizer aliases
  server.on("/fertilizer/on", HTTP_OPTIONS, []() { setCorsHeaders(); server.send(204); });
  server.on("/fertilizer/on", HTTP_GET, []() {
    setFertilizerValve(true);
    setCorsHeaders();
    server.send(200, "application/json", "{\"status\":\"OK\",\"fertilizer\":true}");
  });
  server.on("/fertilizer/off", HTTP_OPTIONS, []() { setCorsHeaders(); server.send(204); });
  server.on("/fertilizer/off", HTTP_GET, []() {
    setFertilizerValve(false);
    setCorsHeaders();
    server.send(200, "application/json", "{\"status\":\"OK\",\"fertilizer\":false}");
  });

  server.on("/setcrop", HTTP_OPTIONS, []() { setCorsHeaders(); server.send(204); });
  server.on("/setcrop", HTTP_GET, handleSetCropApi);
  server.on("/crop",    HTTP_GET, handleSetCropApi);

  server.on("/pump", []() {
    setPump(!pumpActive);
    server.sendHeader("Location", "/");
    server.send(303);
  });
  server.begin();
  Serial.println("[WebServer] Dashboard: http://" + WiFi.localIP().toString());
  Serial.println("[Command] Send 'PUMP:ON', 'PUMP:OFF', 'FERT:ON', or 'FERT:OFF' to test actuators!");
}

// ===========================================================================
//  loop()
// ===========================================================================
void loop() {
  server.handleClient();

  // Process Serial Monitor commands to test actuators directly
  while (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.equalsIgnoreCase("PUMP:ON") || cmd.equalsIgnoreCase("MOTOR:ON") || cmd == "1") {
      setPump(true);
      Serial.println("[Motor/Pump] MANUAL OVERRIDE: ON");
    } else if (cmd.equalsIgnoreCase("PUMP:OFF") || cmd.equalsIgnoreCase("MOTOR:OFF") || cmd == "0") {
      setPump(false);
      Serial.println("[Motor/Pump] MANUAL OVERRIDE: OFF");
    } else if (cmd.equalsIgnoreCase("FERT:ON") || cmd.equalsIgnoreCase("VALVE:ON")) {
      setFertilizerValve(true);
      Serial.println("[Fertilizer] MANUAL OVERRIDE: OPEN");
    } else if (cmd.equalsIgnoreCase("FERT:OFF") || cmd.equalsIgnoreCase("VALVE:OFF")) {
      setFertilizerValve(false);
      Serial.println("[Fertilizer] MANUAL OVERRIDE: CLOSED");
    }
  }

  // Non-blocking flow measurement (every 1 s)
  updateFlowMeasurements();

  unsigned long now = millis();
  if (now - lastUploadTime >= UPLOAD_INTERVAL_MS) {
    lastUploadTime = now;

    // Power soil sensor, read, cut power
    digitalWrite(SOIL_POWER_PIN, HIGH);
    delay(10);
    int   rawADC   = analogRead(SOIL_PIN);
    float moisture = getSoilMoisturePercentage(rawADC);
    digitalWrite(SOIL_POWER_PIN, LOW);

    float tempC    = dht.readTemperature();
    float humidity = dht.readHumidity();
    float turbNTU  = readTurbidityNTU();

    Serial.printf(
      "[Telemetry] M=%.1f%%  T=%.1fC  RH=%.1f%%  Turb=%.0f NTU  "
      "Flow=%.2f L/m  Sess=%.3f L  Total=%.3f L  Pump=%s\n",
      moisture, tempC, humidity, turbNTU,
      flowRateLPM, sessionVolL, rtc_total_volume_L,
      pumpActive ? "ON" : "OFF");

    if (!isnan(tempC) && !isnan(humidity)) {
      updateDepletionRate(moisture);
      evaluateIrrigationLogic(moisture);
      if (SEND_TO_BACKEND)
        postTelemetryToBackend(moisture, tempC, humidity, pumpActive, turbNTU);
    }
  }
}
