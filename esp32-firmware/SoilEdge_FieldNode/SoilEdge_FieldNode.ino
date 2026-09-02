/* =============================================================================
 * SoilEdge Field Node — ESP32 firmware scaffold
 * =============================================================================
 * This is the starting point for the field-node agent. It includes:
 *   1. The trained decision tree from backend/ml/artifacts/model_tree.c
 *   2. Pin map matching the wiring plan in the project spec
 *   3. A simple sensor read + classify + act loop
 *   4. WiFi + HTTP POST telemetry to the backend
 *
 * What's left for the firmware agent:
 *   - Fill in the sensor calibration (ADC -> physical units)
 *   - Decide on the polling cadence (spec says 5-15 min)
 *   - Add the DHT22 / capacitive moisture / pH / EC driver code
 *   - Implement OTA / deep-sleep battery behaviour
 *
 * Wiring: see docs/01-Smart-Farming-System-Project-Plan.md § 4
 * Trained model: copy ml/artifacts/model_tree.c + .h into this sketch folder.
 * =============================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include "model_tree.h"   // from ml/artifacts/model_tree.h

// ---- Configuration ----
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Backend URL (set this in backend/.env or change here for local dev)
const char* API_BASE      = "http://your-backend:8000";
const char* DEVICE_TOKEN  = "paste-token-here";   // from /api/devices/register
const char* DEVICE_ID     = "esp32-01";

// ---- GPIO map (from project spec § 4.2) ----
#define DHT_PIN            4
#define MOISTURE_ADC_PIN   32   // 12-bit ADC
#define PH_ADC_PIN         34   // input-only
#define EC_ADC_PIN         35   // input-only
#define PUMP_RELAY_PIN     26
#define FERT_RELAY_PIN     27

// ---- Polling ----
const unsigned long POLL_INTERVAL_MS = 10UL * 60UL * 1000UL;   // 10 minutes
unsigned long last_poll = 0;

// ---- Sensor read placeholders ----
struct SensorReading {
  float ph;
  float temperature;
  float moisture;
  float ec;
};

SensorReading readSensors() {
  SensorReading r = {0, 0, 0, 0};
  // TODO: implement actual ADC reads + calibration.
  //       See project plan § 5.5 for the calibration procedure.
  //
  // Expected sequence:
  //   1. Capacitive moisture  -> % (calibrate: dry-air = 0%, submerged = 100%)
  //   2. pH probe + module    -> pH 0-14 (calibrate with pH 4.0 / 7.0 buffers)
  //   3. EC probe + module    -> dS/m (calibrate with 1.413 mS/cm standard)
  //   4. DHT22 / soil temp    -> °C
  return r;
}

// ---- Safety-wrapped classifier (see backend/ml/README.md) ----
int safe_classify(float ph, float temperature, float moisture, float ec) {
  if (ec >= 8.0f) return 4;                       // critical salinity -> reclamation
  if (!isfinite(ph) || ph < 0.0f || ph > 14.0f) return 0;
  if (!isfinite(ec) || ec < 0.0f || ec > 20.0f) return 0;
  if (!isfinite(moisture) || moisture < 0.0f || moisture > 100.0f) return 0;
  if (!isfinite(temperature) || temperature < -40.0f || temperature > 80.0f) return 0;
  return classify(ph, temperature, moisture, ec);
}

const char* action_name(int code) {
  switch (code) {
    case 0: return "Maintain regular soil monitoring";
    case 1: return "Improve irrigation scheduling";
    case 2: return "Use salt-tolerant crops / soil amendment";
    case 3: return "Apply leaching and drainage control";
    case 4: return "Immediate reclamation / salinity control";
    default: return "unknown";
  }
}

void apply_action(int code, SensorReading& r) {
  bool pump_on = false, fert_on = false;
  switch (code) {
    case 0: // monitor — fert only when conditions are safe
      fert_on = (r.ec < 2.2f && r.ph >= 6.0f && r.ph <= 7.5f
                 && r.moisture >= 18.0f && r.moisture <= 40.0f);
      break;
    case 1: case 3: case 4: pump_on = true; break;  // irrigate / leach / reclamation
    case 2: default:       break;                  // amend — pump off
  }
  digitalWrite(PUMP_RELAY_PIN, pump_on   ? HIGH : LOW);
  digitalWrite(FERT_RELAY_PIN, fert_on   ? HIGH : LOW);
  Serial.printf("  action=%d (%s)  pump=%d  fert=%d\n",
                code, action_name(code), pump_on, fert_on);
}

void post_telemetry(SensorReading& r, int code) {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  String url = String(API_BASE) + "/api/telemetry";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);

  // Map action -> (pump, fert) booleans for the backend (mirrors apply_action)
  bool pump = (code == 1 || code == 3 || code == 4);
  bool fert = (code == 0 && r.ec < 2.2f && r.ph >= 6.0f && r.ph <= 7.5f
               && r.moisture >= 18.0f && r.moisture <= 40.0f);

  char body[512];
  snprintf(body, sizeof(body),
    "{\"device_id\":\"%s\","
     "\"moisture\":%.2f,\"temperature\":%.2f,\"ph\":%.2f,\"ec\":%.2f,"
     "\"action\":%d,\"action_name\":\"%s\","
     "\"pump\":%s,\"fertilizer\":%s,"
     "\"timestamp\":\"%s\"}",
    DEVICE_ID,
    r.moisture, r.temperature, r.ph, r.ec,
    code, action_name(code),
    pump  ? "true" : "false",
    fert  ? "true" : "false",
    "");  // server fills in if empty
  int code_resp = http.POST(body);
  if (code_resp > 0) Serial.printf("  telemetry: HTTP %d\n", code_resp);
  else               Serial.printf("  telemetry: failed: %s\n",
                                  http.errorToString(code_resp).c_str());
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(PUMP_RELAY_PIN, OUTPUT);
  pinMode(FERT_RELAY_PIN, OUTPUT);
  digitalWrite(PUMP_RELAY_PIN, LOW);
  digitalWrite(FERT_RELAY_PIN, LOW);

  Serial.println("SoilEdge field node booting...");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println(" connected");
}

void loop() {
  unsigned long now = millis();
  if (now - last_poll < POLL_INTERVAL_MS) return;
  last_poll = now;

  SensorReading r = readSensors();
  int action = safe_classify(r.ph, r.temperature, r.moisture, r.ec);

  // ALWAYS apply locally — never wait for the backend
  apply_action(action, r);

  // Best-effort upload — offline-safe
  post_telemetry(r, action);
}
