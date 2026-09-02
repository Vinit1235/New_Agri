import os
import sys
from datetime import date
from pathlib import Path

# Add backend to python path so we can import app modules
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BACKEND_DIR))

from app.services.sentinel import get_client, _bbox_around_point

class MockField:
    """A dummy field object to pass to the Sentinel client without needing the database."""
    def __init__(self, lat, lon, crop_type, planting_date):
        self.id = 999
        self.lat = lat
        self.lon = lon
        self.polygon = None # let field_geometry handle it
        self.crop_type = crop_type
        self.planting_date = planting_date

NDVI_MAP_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B04", "B08", "dataMask"],
    output: { bands: 4, sampleType: "UINT8" }
  };
}
function evaluatePixel(sample) {
  let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 1e-6);
  // Red (low) to Yellow (med) to Green (high)
  let r=0, g=0, b=0;
  if (ndvi < 0.2) { r = 255; }
  else if (ndvi < 0.5) { r = 255; g = 255; }
  else { g = 255; }
  return [r, g, b, sample.dataMask ? 255 : 0];
}
"""

NDWI_MAP_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: ["B03", "B08", "dataMask"],
    output: { bands: 4, sampleType: "UINT8" }
  };
}
function evaluatePixel(sample) {
  let ndwi = (sample.B03 - sample.B08) / (sample.B03 + sample.B08 + 1e-6);
  // White (dry) to Blue (wet)
  let b = 255;
  let r = ndwi > 0 ? 0 : 255;
  let g = ndwi > 0 ? 0 : 255;
  return [r, g, b, sample.dataMask ? 255 : 0];
}
"""

def fetch_map_image(field, map_type="NDVI"):
    from app.services.sentinel import settings, _get_copernicus_token, _payload
    import httpx
    
    if not settings.copernicus_client_id:
        print(f"  [Mock] Skipping {map_type} map image - please configure Copernicus credentials in .env first.")
        return
        
    print(f"  [Real] Fetching {map_type} map image...")
    try:
        token = _get_copernicus_token()
        body = _payload(field)
        body["evalscript"] = NDVI_MAP_EVALSCRIPT if map_type == "NDVI" else NDWI_MAP_EVALSCRIPT
        body["output"]["responses"][0]["format"]["type"] = "image/png"
        
        resp = httpx.post(
            settings.copernicus_process_url,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60.0,
        )
        resp.raise_for_status()
        
        filename = f"{map_type.lower()}_map_{field.lat}_{field.lon}.png"
        with open(filename, "wb") as f:
            f.write(resp.content)
        print(f"  -> Saved {map_type} map to {filename}")
    except Exception as e:
        print(f"  -> Failed to fetch {map_type} map: {e}")
        if hasattr(e, "response"):
            print(f"  -> API Response: {e.response.text}")

def test_fetch(lat: float, lon: float, crop_type: str):
    print(f"\n--- Fetching satellite data for {crop_type} at {lat}, {lon} ---")
    
    # Create our dummy field
    field = MockField(lat=lat, lon=lon, crop_type=crop_type, planting_date=date(2026, 3, 1))
    
    # Get the configured client (Mock or real Copernicus if .env has keys)
    client = get_client()
    print(f"Using client: {client.__class__.__name__}")
    
    # Attempt to fetch map images
    fetch_map_image(field, "NDVI")
    fetch_map_image(field, "NDWI")
    
    print("-" * 60)

if __name__ == "__main__":
    # The coordinates provided by the user
    test_fetch(lat=19.712879, lon=72.793093, crop_type="wheat")
