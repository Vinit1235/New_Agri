/*
 * ============================================================================
 * JanSeva DryTech - Smart Vegetable Dryer Firmware (DHT11 & USB Real-Time Edition)
 * Target Board: ESP32 Dev Module
 * Version: 2.5.0
 * 
 * Hardware Wiring:
 * 1. DHT11 Sensor (Temperature & Relative Humidity):
 *    - VCC  -> ESP32 3.3V (or 5V for 3-pin breakout board)
 *    - GND  -> ESP32 GND
 *    - DATA -> ESP32 GPIO 4 (Note: If using bare 4-pin DHT11, place a 10K pull-up resistor between VCC and DATA)
 * 
 * 2. Cooling / Circulation Fan Actuator:
 *    - Relay / MOSFET Signal (IN) -> ESP32 GPIO 25 (HIGH = ON, LOW = OFF)
 *    - Relay VCC                  -> 5V or External 12V
 *    - Relay GND                  -> ESP32 GND (Common Ground)
 * 
 * 3. Status Indicator LED:
 *    - Onboard Blue LED           -> ESP32 GPIO 2 (aaLights up when Fan is ON)
 * 
 * 4. USB Cable Connection:
 *    - Direct USB cable from ESP32 to Laptop USB port at 115200 Baud
 * 
 * Library Requirement:
 * In Arduino IDE, go to: Sketch -> Include Library -> Manage Libraries...
 * Search for "DHT sensor library" by Adafruit and click Install.
 * (Also allow it to install "Adafruit Unified Sensor" dependency if prompted).
 * 
 * Real-Time Telemetry Stream (Sent every 1 second via USB Serial):
 * {"temp":28.5,"humidity":62.0,"fan":1,"target":55.0,"auto":0,"sensor":"DHT11","status":"OK"}
 * 
 * Serial Commands (Sent from Web Dashboard via USB):
 * - "FAN:ON"       -> Turns Fan ON
 * - "FAN:OFF"      -> Turns Fan OFF
 * - "FAN:TOGGLE"   -> Toggles Fan state
 * - "AUTO:ON"      -> Enables automatic temperature-driven fan exhaust
 * - "AUTO:OFF"     -> Disables auto mode (manual control)
 * - "SET:TEMP:xx"  -> Updates target setpoint (e.g., SET:TEMP:55.0)
 * - "STATUS"       -> Requests immediate telemetry JSON packet
 * ============================================================================
 */

#include <Arduino.h>
#include <DHT.h>

// ==================== PIN DEFINITIONS ====================
#define DHTPIN              4     // ESP32 GPIO 4 connected to DHT11 DATA pin
#define DHTTYPE             DHT11 // Sensor model DHT11
#define FAN_PIN             25    // Digital Output for Fan Relay / MOSFET / Driver
#define STATUS_LED_PIN      2     // Built-in ESP32 Blue LED (GPIO 2)

// ==================== SENSOR INITIALIZATION ====================
DHT dht(DHTPIN, DHTTYPE);

// ==================== STATE VARIABLES ====================
float currentTemperature      = 28.5;     // Live DHT11 temperature in Celsius
float currentHumidity         = 60.0;     // Live DHT11 relative humidity in %
float targetTemperature       = 55.0;     // Target drying temperature setpoint
float hysteresisTemp          = 2.0;      // Buffer (+/- °C) for auto-thermostat mode
bool  fanState                = false;    // false = OFF, true = ON
bool  autoControlMode         = false;    // Automatic overheat protection mode

unsigned long lastDhtReadTime = 0;
const unsigned long DHT_READ_INTERVAL_MS = 1500;  // DHT11 minimum sample interval (1.5s)

unsigned long lastTelemetryTime = 0;
const unsigned long TELEMETRY_INTERVAL_MS = 1000; // Send USB telemetry every 1.0 second

// Serial receive buffer
String serialRxBuffer = "";

// ==================== DHT11 SENSOR READING ====================
void readDht11Sensor() {
  float newTemp = dht.readTemperature();
  float newHum  = dht.readHumidity();

  // Validate temperature reading
  if (!isnan(newTemp) && newTemp >= 0.0 && newTemp <= 85.0) {
    // Apply gentle smoothing filter
    currentTemperature = (currentTemperature * 0.7) + (newTemp * 0.3);
  }

  // Validate humidity reading
  if (!isnan(newHum) && newHum >= 5.0 && newHum <= 100.0) {
    currentHumidity = (currentHumidity * 0.7) + (newHum * 0.3);
  }
}

// ==================== FAN ACTUATOR CONTROL ====================
void setFan(bool state, const char* reason = "MANUAL") {
  fanState = state;
  digitalWrite(FAN_PIN, fanState ? HIGH : LOW);
  digitalWrite(STATUS_LED_PIN, fanState ? HIGH : LOW);

  // Immediately send JSON confirmation feedback over USB Serial
  Serial.print("{\"event\":\"fan_change\",\"fan\":");
  Serial.print(fanState ? 1 : 0);
  Serial.print(",\"temp\":");
  Serial.print(currentTemperature, 1);
  Serial.print(",\"humidity\":");
  Serial.print(currentHumidity, 1);
  Serial.print(",\"reason\":\"");
  Serial.print(reason);
  Serial.println("\"}");
}

// ==================== TELEMETRY PACKET SENDER ====================
void sendTelemetry() {
  Serial.print("{\"temp\":");
  Serial.print(currentTemperature, 1);
  Serial.print(",\"humidity\":");
  Serial.print(currentHumidity, 1);
  Serial.print(",\"fan\":");
  Serial.print(fanState ? 1 : 0);
  Serial.print(",\"target\":");
  Serial.print(targetTemperature, 1);
  Serial.print(",\"auto\":");
  Serial.print(autoControlMode ? 1 : 0);
  Serial.print(",\"sensor\":\"DHT11\"");
  Serial.print(",\"status\":\"OK\"");
  Serial.println("}");
}

// ==================== COMMAND PARSER ====================
void parseCommand(String cmd) {
  cmd.trim();
  if (cmd.length() == 0) return;

  String upperCmd = cmd;
  upperCmd.toUpperCase();

  if (upperCmd == "FAN:ON" || upperCmd == "1" || upperCmd == "ON") {
    autoControlMode = false;
    setFan(true, "USB_COMMAND_ON");
  } 
  else if (upperCmd == "FAN:OFF" || upperCmd == "0" || upperCmd == "OFF") {
    autoControlMode = false;
    setFan(false, "USB_COMMAND_OFF");
  } 
  else if (upperCmd == "FAN:TOGGLE") {
    autoControlMode = false;
    setFan(!fanState, "USB_TOGGLE");
  } 
  else if (upperCmd == "AUTO:ON") {
    autoControlMode = true;
    Serial.println("{\"event\":\"mode\",\"mode\":\"AUTO\"}");
  } 
  else if (upperCmd == "AUTO:OFF") {
    autoControlMode = false;
    Serial.println("{\"event\":\"mode\",\"mode\":\"MANUAL\"}");
  } 
  else if (upperCmd.startsWith("SET:TEMP:")) {
    float newTarget = upperCmd.substring(9).toFloat();
    if (newTarget >= 30.0 && newTarget <= 80.0) {
      targetTemperature = newTarget;
      Serial.print("{\"event\":\"target_temp\",\"target\":");
      Serial.print(targetTemperature, 1);
      Serial.println("}");
    }
  } 
  else if (upperCmd == "STATUS") {
    sendTelemetry();
  } 
  else if (cmd.startsWith("{") && cmd.endsWith("}")) {
    // JSON command support
    if (cmd.indexOf("\"fan\":1") >= 0 || cmd.indexOf("\"fan\":\"on\"") >= 0) {
      setFan(true, "JSON_COMMAND");
    } else if (cmd.indexOf("\"fan\":0") >= 0 || cmd.indexOf("\"fan\":\"off\"") >= 0) {
      setFan(false, "JSON_COMMAND");
    }
  } 
  else {
    Serial.print("{\"error\":\"UNKNOWN_COMMAND\",\"cmd\":\"");
    Serial.print(cmd);
    Serial.println("\"}");
  }
}

// ==================== SETUP ====================
void setup() {
  // Initialize USB Serial at high-speed 115200 baud
  Serial.begin(115200);
  delay(500);

  // Configure Actuator & Indicator Pins
  pinMode(FAN_PIN, OUTPUT);
  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(FAN_PIN, LOW);
  digitalWrite(STATUS_LED_PIN, LOW);

  // Initialize DHT11 sensor
  dht.begin();
  delay(1000); // Allow DHT11 to stabilize

  // Initial read
  readDht11Sensor();

  Serial.println("\n==============================================");
  Serial.println("🌿 JanSeva DryTech - ESP32 DHT11 & Fan Controller");
  Serial.println("📡 Connected via USB Serial (115200 Baud)");
  Serial.println("DHT11 Pin: GPIO 4 | Fan Pin: GPIO 25 | LED: GPIO 2");
  Serial.println("Commands: FAN:ON | FAN:OFF | SET:TEMP:<val> | STATUS");
  Serial.println("==============================================");

  // Send initial telemetry packet
  sendTelemetry();
}

// ==================== MAIN LOOP ====================
void loop() {
  unsigned long currentMillis = millis();

  // 1. Process incoming USB Serial commands from Laptop
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialRxBuffer.length() > 0) {
        parseCommand(serialRxBuffer);
        serialRxBuffer = "";
      }
    } else {
      if (serialRxBuffer.length() < 120) {
        serialRxBuffer += c;
      }
    }
  }

  // 2. Read DHT11 sensor every 1.5 seconds (DHT11 refresh constraint)
  if (currentMillis - lastDhtReadTime >= DHT_READ_INTERVAL_MS) {
    lastDhtReadTime = currentMillis;
    readDht11Sensor();
  }

  // 3. Automatic Overheat Protection Logic (Thermostat mode)
  if (autoControlMode) {
    if (currentTemperature >= targetTemperature && !fanState) {
      setFan(true, "AUTO_OVERHEAT_TRIGGER");
    } else if (currentTemperature <= (targetTemperature - hysteresisTemp) && fanState) {
      setFan(false, "AUTO_TEMP_NORMALIZED");
    }
  }

  // 4. Stream real-time telemetry over USB Serial every 1 second
  if (currentMillis - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = currentMillis;
    sendTelemetry();
  }

  // Yield to ESP32 RTOS core
  delay(10);
}
