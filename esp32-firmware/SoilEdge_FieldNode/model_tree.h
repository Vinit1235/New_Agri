// Auto-generated header for the ESP32 soil-AI model
// Trained on 10000 real samples on 2026-08-31
// Returns the 5-class spec action code:
//   0 = monitor, 1 = irrigate, 2 = amend, 3 = leach, 4 = reclamation
int classify(float ph, float temperature, float moisture, float ec);
