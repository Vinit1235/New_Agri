import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
NDVI_MODEL_PATH = ARTIFACTS / "ndvi_bands.json"


def evaluate_ndvi(profiles, crop, doy, current_ndvi):
    """
    Evaluates whether a given NDVI value is healthy (within range) for the 
    specified crop and day-of-year (doy).
    Returns (stage_name, status) where status is 'healthy', 'low', or 'high'.
    """
    if crop not in profiles:
        raise ValueError(f"Crop '{crop}' not found in profiles.")
        
    stages = profiles[crop]["stages"]
    
    # Find the matching stage for the day of year
    for stage in stages:
        windows = stage["doy_window"]
        is_in_stage = False
        
        if len(windows) == 2:
            is_in_stage = windows[0] <= doy <= windows[1]
        elif len(windows) == 4:
            is_in_stage = (windows[0] <= doy <= windows[1]) or (windows[2] <= doy <= windows[3])
            
        if is_in_stage:
            low = stage["ndvi_low"]
            high = stage["ndvi_high"]
            
            if current_ndvi < low:
                return stage["stage"], "low"
            elif current_ndvi > high:
                return stage["stage"], "high"
            else:
                return stage["stage"], "healthy"
                
    return "unknown", "out of range"


class TestNDVIModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NDVI_MODEL_PATH.exists():
            raise FileNotFoundError(f"Model file not found: {NDVI_MODEL_PATH}")
        with open(NDVI_MODEL_PATH) as f:
            data = json.load(f)
            cls.profiles = data["profiles"]
            
    def test_wheat_seedling_healthy(self):
        # Wheat seedling window is [1, 60] with NDVI 0.25 - 0.54
        stage, status = evaluate_ndvi(self.profiles, "wheat", doy=30, current_ndvi=0.40)
        self.assertEqual(stage, "seedling")
        self.assertEqual(status, "healthy")
        
    def test_wheat_seedling_low(self):
        # Wheat seedling window is [1, 60] with NDVI 0.25 - 0.54
        stage, status = evaluate_ndvi(self.profiles, "wheat", doy=30, current_ndvi=0.15)
        self.assertEqual(stage, "seedling")
        self.assertEqual(status, "low")

    def test_maize_vegetative_high(self):
        # Maize vegetative window is [141, 195] with NDVI 0.64 - 0.78
        stage, status = evaluate_ndvi(self.profiles, "maize", doy=160, current_ndvi=0.90)
        self.assertEqual(stage, "vegetative")
        self.assertEqual(status, "high")
        
    def test_maize_fallow_split_window(self):
        # Maize fallow window is [276, 365, 1, 89] with NDVI 0.35 - 0.63
        # Testing late year
        stage, status = evaluate_ndvi(self.profiles, "maize", doy=300, current_ndvi=0.50)
        self.assertEqual(stage, "fallow")
        self.assertEqual(status, "healthy")
        
        # Testing early year
        stage, status = evaluate_ndvi(self.profiles, "maize", doy=45, current_ndvi=0.70)
        self.assertEqual(stage, "fallow")
        self.assertEqual(status, "high")


if __name__ == "__main__":
    unittest.main()
