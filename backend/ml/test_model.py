import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
MODEL_PATH = ARTIFACTS / "model_tree.json"

def predict(node, features):
    """Recursively predicts the action based on the model tree."""
    if isinstance(node, int):
        return node
    
    feature_val = features.get(node["f"], 0.0)
    if feature_val <= node["t"]:
        return predict(node["l"], features)
    else:
        return predict(node["r"], features)


class TestESP32Model(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Load the model tree once for all tests."""
        if not MODEL_PATH.exists():
            raise FileNotFoundError(f"Model file not found: {MODEL_PATH}")
        with open(MODEL_PATH) as f:
            cls.model = json.load(f)
            
    def test_low_ec_high_moisture(self):
        # EC < 3.9, Temp > 27.8, EC <= 2.1, Moisture > 70 => 0
        features = {"ec": 1.5, "temperature": 30.0, "moisture": 75.0, "ph": 7.0}
        self.assertEqual(predict(self.model, features), 0)
        
    def test_high_ec_low_moisture(self):
        # EC > 3.9, Moisture < 67.6 => 3 (leach)
        features = {"ec": 4.5, "temperature": 25.0, "moisture": 50.0, "ph": 6.0}
        self.assertEqual(predict(self.model, features), 3)

    def test_mid_ec_low_temp(self):
        # EC <= 3.9, Temp <= 27.8, EC <= 3.5 => 0 (monitor)
        features = {"ec": 2.5, "temperature": 25.0, "moisture": 60.0, "ph": 6.5}
        self.assertEqual(predict(self.model, features), 0)
        
    def test_moderate_ec_moderate_moisture(self):
        # EC <= 3.9, Temp > 27.8, EC > 2.1, Moisture <= 69.6 => 2 (amend)
        features = {"ec": 2.5, "temperature": 30.0, "moisture": 65.0, "ph": 6.5}
        self.assertEqual(predict(self.model, features), 2)


if __name__ == "__main__":
    unittest.main()
