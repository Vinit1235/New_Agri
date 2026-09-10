#!/usr/bin/env python3
"""
ESP32 Field Node Simulator
Simulates the ESP32 SoilEdge device posting telemetry data to backend:
- Soil Moisture + DHT11 (Temperature & Humidity)
- Real-time Edge Math: Vapor Pressure Deficit (VPD) and Dew Point (Magnus formula)
- Smart Irrigation Hysteresis (ON < 25%, OFF >= 60%)
- Fail-Safe Max Run Timer Cutout
"""

import requests
import time
import math
import random
from datetime import datetime

# Configuration
BACKEND_URL = "http://localhost:8000"
DEVICE_ID = "TEST_ESP32_SIMULATOR"

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header():
    print(f"\n{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}   SOIL-EDGE ESP32 FIELD NODE SIMULATOR (VPD & HYSTERESIS){Colors.RESET}")
    print(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n")

def print_status(status, message):
    if status == "success":
        print(f"{Colors.GREEN}✓{Colors.RESET} {message}")
    elif status == "error":
        print(f"{Colors.RED}✗{Colors.RESET} {message}")
    elif status == "info":
        print(f"{Colors.BLUE}ℹ{Colors.RESET} {message}")
    elif status == "warning":
        print(f"{Colors.YELLOW}⚠{Colors.RESET} {message}")

def calculate_vpd(temp_c, humidity):
    """Calculate Vapor Pressure Deficit in kPa"""
    if temp_c is None or humidity is None or humidity <= 0:
        return 0.0
    vp_sat = 0.61078 * math.exp((17.27 * temp_c) / (temp_c + 237.3))
    vp_act = vp_sat * (humidity / 100.0)
    return max(0.0, vp_sat - vp_act)

def calculate_dew_point(temp_c, humidity):
    """Calculate Dew Point in Celsius via Magnus formula"""
    if temp_c is None or humidity is None or humidity <= 0:
        return 0.0
    alpha = ((17.27 * temp_c) / (237.3 + temp_c)) + math.log(humidity / 100.0)
    return (237.3 * alpha) / (17.27 - alpha)

def get_fungal_risk(temp_c, dew_c, humidity):
    delta = temp_c - dew_c
    if delta <= 2.0 or humidity >= 85.0:
        return "HIGH (Condensation Alert)"
    if delta <= 4.0 or humidity >= 75.0:
        return "MODERATE"
    return "LOW"

class HysteresisController:
    """Simulates the ESP32 state machine with hysteresis and fail-safe cutout"""
    def __init__(self, low_thresh=25.0, high_thresh=60.0, max_run_sec=180):
        self.low_thresh = low_thresh
        self.high_thresh = high_thresh
        self.max_run_sec = max_run_sec
        self.pump_active = False
        self.pump_start_time = None
        self.safety_lockout = False

    def evaluate(self, moisture):
        now = time.time()
        if self.safety_lockout:
            return False, "SAFETY_CUTOUT_LOCKED"

        if self.pump_active and self.pump_start_time:
            if (now - self.pump_start_time) > self.max_run_sec:
                self.pump_active = False
                self.safety_lockout = True
                return False, "SAFETY_CUTOUT_ENGAGED"

        if moisture < self.low_thresh:
            if not self.pump_active:
                self.pump_active = True
                self.pump_start_time = now
            return True, "HYSTERESIS_IRRIGATION_ON"
        elif moisture >= self.high_thresh:
            if self.pump_active:
                self.pump_active = False
                self.pump_start_time = None
            return False, "TARGET_REACHED_STANDBY"
        else:
            # Retain current pump state
            action = "HYSTERESIS_HOLD_ON" if self.pump_active else "HYSTERESIS_HOLD_OFF"
            return self.pump_active, action

controller = HysteresisController()

def generate_sensor_reading(scenario="optimal"):
    """Generate realistic moisture & DHT11 readings for different field conditions"""
    scenarios = {
        "optimal": {
            "moisture": random.uniform(40.0, 55.0),
            "temperature": random.uniform(22.0, 26.0),
            "humidity": random.uniform(55.0, 70.0)
        },
        "dry_trigger": {
            "moisture": random.uniform(12.0, 22.0),
            "temperature": random.uniform(29.0, 34.0),
            "humidity": random.uniform(30.0, 45.0)
        },
        "hysteresis_mid": {
            "moisture": random.uniform(35.0, 45.0),
            "temperature": random.uniform(24.0, 28.0),
            "humidity": random.uniform(60.0, 75.0)
        },
        "wet_target": {
            "moisture": random.uniform(62.0, 75.0),
            "temperature": random.uniform(21.0, 25.0),
            "humidity": random.uniform(70.0, 80.0)
        },
        "high_humidity_mold_risk": {
            "moisture": random.uniform(45.0, 55.0),
            "temperature": random.uniform(19.0, 23.0),
            "humidity": random.uniform(88.0, 96.0)
        }
    }
    return scenarios.get(scenario, scenarios["optimal"])

def post_telemetry(device_id, device_token, reading, pump_state, action_name):
    """Post telemetry data to FastAPI backend"""
    payload = {
        "device_id": device_id,
        "moisture": round(reading["moisture"], 2),
        "temperature": round(reading["temperature"], 2),
        "humidity": round(reading["humidity"], 2),
        "pump": pump_state,
        "fertilizer": False,
        "action_name": action_name,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    headers = {
        "Authorization": f"Bearer {device_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/telemetry",
            json=payload,
            headers=headers,
            timeout=10
        )
        return response.status_code, response.text, payload
    except requests.exceptions.ConnectionError:
        return None, "Connection refused - is backend running?", payload
    except Exception as e:
        return None, str(e), payload

def register_test_device(user_token, field_id):
    """Register test device and get token"""
    print_status("info", f"Registering test device: {DEVICE_ID}")
    payload = {
        "device_id": DEVICE_ID,
        "field_id": field_id,
        "device_type": "esp32"
    }
    headers = {
        "Authorization": f"Bearer {user_token}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(
            f"{BACKEND_URL}/api/devices/register",
            json=payload,
            headers=headers,
            timeout=10
        )
        if response.status_code in (200, 201):
            data = response.json()
            device_token = data.get("token") or data.get("device_token")
            print_status("success", "Device registered successfully")
            print_status("info", f"Device Token: {device_token[:25]}...")
            return device_token
        else:
            print_status("error", f"Failed to register device: {response.status_code} {response.text}")
            return None
    except Exception as e:
        print_status("error", f"Failed to register device: {e}")
        return None

def run_simulation_cycle(device_id, device_token, scenario, cycle_num):
    print(f"\n{Colors.YELLOW}{'─'*70}{Colors.RESET}")
    print(f"{Colors.BOLD}CYCLE #{cycle_num} - Scenario: {scenario.upper()}{Colors.RESET}")
    print(f"{Colors.YELLOW}{'─'*70}{Colors.RESET}\n")

    reading = generate_sensor_reading(scenario)
    vpd = calculate_vpd(reading['temperature'], reading['humidity'])
    dew = calculate_dew_point(reading['temperature'], reading['humidity'])
    fungal_risk = get_fungal_risk(reading['temperature'], dew, reading['humidity'])
    pump_state, action_name = controller.evaluate(reading['moisture'])

    print(f"{Colors.CYAN}📊 SENSORS (Soil Moisture + DHT11):{Colors.RESET}")
    print(f"  Soil Moisture: {reading['moisture']:.1f}%")
    print(f"  Air Temp:      {reading['temperature']:.1f}°C")
    print(f"  Humidity:      {reading['humidity']:.1f}%")

    print(f"\n{Colors.MAGENTA}🔬 EDGE MATH DERIVATIVES:{Colors.RESET}")
    print(f"  VPD:           {vpd:.2f} kPa")
    print(f"  Dew Point:     {dew:.1f}°C")
    print(f"  Fungal Risk:   {fungal_risk}")

    print(f"\n{Colors.BLUE}⚡ HYSTERESIS IRRIGATION DECISION:{Colors.RESET}")
    print(f"  Pump State:    {'ON' if pump_state else 'OFF'} "
          f"({Colors.GREEN + '●' if pump_state else Colors.RED + '●'}{Colors.RESET})")
    print(f"  Action Name:   {action_name}")

    if device_token:
        print(f"\n{Colors.BLUE}📡 POSTING TO /api/telemetry...{Colors.RESET}")
        status_code, response_text, payload = post_telemetry(
            device_id, device_token, reading, pump_state, action_name
        )
        if status_code in (200, 201):
            print_status("success", f"Telemetry acknowledged by server (HTTP {status_code})")
            return True
        else:
            print_status("error", f"Telemetry failed ({status_code}): {response_text}")
            return False
    return True

def main():
    print_header()

    print_status("info", "Checking backend health...")
    try:
        response = requests.get(f"{BACKEND_URL}/api/health", timeout=5)
        if response.status_code == 200:
            print_status("success", "Backend is running and healthy")
        else:
            print_status("error", f"Backend health check failed: {response.status_code}")
            return
    except Exception as e:
        print_status("error", f"Cannot connect to backend: {e}")
        print_status("info", "Make sure backend is running: uvicorn app.main:app --port 8000")
        return

    user_token = input(f"\n{Colors.CYAN}Enter user token (or press Enter to run offline preview): {Colors.RESET}").strip()
    device_token = None

    if user_token:
        field_id = input(f"{Colors.CYAN}Enter field ID (default: 1): {Colors.RESET}").strip()
        field_id = int(field_id) if field_id else 1
        device_token = register_test_device(user_token, field_id)

    scenarios = ["dry_trigger", "hysteresis_mid", "wet_target", "hysteresis_mid", "high_humidity_mold_risk"]
    print(f"\n{Colors.BOLD}Running 5 Edge IoT Scenarios...{Colors.RESET}\n")

    for i, scenario in enumerate(scenarios, 1):
        run_simulation_cycle(DEVICE_ID, device_token, scenario, i)
        if i < len(scenarios):
            time.sleep(1.5)

    print(f"\n{Colors.GREEN}✓ Simulation sequence complete!{Colors.RESET}\n")

if __name__ == "__main__":
    main()
