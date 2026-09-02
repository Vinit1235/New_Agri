# Krishinayan — Pitch Deck (12 Slides)
**Build the PPT from this file only.**  
Style of top decks: **one idea per slide · minimal text · numbers on problem · product as behavior change · clear ask.**

**Product:** Krishinayan  
**One-liner:** Offline AI that irrigates and blocks unsafe fertilizer — with satellite crop health every 5 days.

---

## Slide 1 — Title

**Krishinayan**  
Offline AI for irrigation & fertilizer. Satellite health every 5 days.

**Optional subline:** Smart farming · salinity-aware · edge + Sentinel  

**Visual:** logo + hero  

**Say:** We don’t only show farm data. We act in the field when the soil needs water — and we stop fertilizer when salt makes it useless.

---

## Slide 2 — Problem

**Title:** Farms waste water and fertilizer — and salt is spreading  

**Three facts only:**

1. Agriculture uses **~71%** of global freshwater withdrawals  
2. **~1.38 billion hectares** of land are salt-affected (**10.7%** of land) — yield losses up to **~70%** in severe cases  
3. Only about **1/3** of applied nitrogen is used by crops; the rest is waste and pollution  

**The trap:** Weak crop → more fertilizer → higher soil salt (EC) → weaker crop  

**Footer (tiny):** FAO AQUASTAT · FAO Salt-Affected Soils 2024 · nutrient budget research  

**Say:** Calendar watering and blind fertilizing burn money and damage soil. Salinity turns the next fertilizer bag into a liability.

---

## Slide 3 — Solution

**Title:** Krishinayan acts in the soil — and watches the crop from space  

**Behavior change (not feature dump):**

| Today | With Krishinayan |
|-------|----------------|
| Water by schedule | Water when **moisture** says dry |
| Fertilize by habit | Fertilize only if **EC + pH** allow |
| Notice stress late | **EC** drives leach / block feed in real time |
| Need constant internet | **ESP32 decides offline** |
| Guess crop recovery | **NDVI / NDWI every ~5 days** |

**One line:** Edge AI runs the pump and fertilizer valve; software tracks canopy health via Copernicus/Sentinel.

**Visual:** sensor in soil + small satellite cue  

---

## Slide 4 — Product

**Title:** Two layers. One system.

```text
FIELD                         SOFTWARE
ESP32 + sensors               Dashboard (HTML/JS)
moisture · temp · pH · EC     live soil + action log
local AI → pump / fertilizer  crop settings
OFFLINE first                 Sentinel NDVI/NDWI ~5 days
                              health: Healthy / Moderate / High
```

**Hardware (simple):** ESP32 · moisture · temp · pH · EC · relays · battery  

**Software:** Python backend · web dashboard · European satellite API  

**Say:** Minutes for soil actions. Days for health trends. Cloud is optional — automation is not.

---

## Slide 5 — How the AI decides

**Title:** Salinity-aware automation  

| Condition | Action |
|-----------|--------|
| Moisture low, EC normal | **Irrigate** |
| EC high | **Leach / manage water** · fertilizer **OFF** |
| pH unsafe | Fertilizer **OFF** |
| Soil OK | Monitor · optional light dose only if safe |

**Tech (one line):** Lightweight model trained on PC → runs on ESP32 (no PC in the field).  

**Say:** High electrical conductivity is a hard stop on dosing. That breaks the salinity–fertilizer loop.

---

## Slide 6 — Why this wins (value)

**Title:** Benefits that matter on a real farm  

- **Save water** — irrigate from soil truth, not the calendar  
- **Protect soil** — don’t add fertilizer salt when EC is already high  
- **Cut input waste** — dose only when the plant can use it  
- **Stay online when the network isn’t** — decisions on-device  
- **See recovery** — 5-day satellite health, multi-crop aware  
- **Clear language** — irrigate / leach / monitor / block fertilizer  

**Direction from research (honest):** Sensor-driven irrigation and precision practices often show **~15–25%** productivity gains and **~20–40%** water savings in published cases — why soil-led control is the right bet.

---

## Slide 7 — Market

**Title:** Who pays for this problem to go away  

**Primary:** Farms with pumps + fertilizer cost + salinity or water stress  
**Secondary:** Agri projects, cooperatives, demos that need **action**, not only apps  

**Job to be done:**  
“Keep yield up with less water and less wasted fertilizer — without killing the soil.”

**Why now:**  
Cheap ESP32-class hardware · free Sentinel data via API · pressure on water and fertilizer prices · salinity mapped as a global food-security risk  

*(Keep TAM/SAM light unless you have a bottom-up number for your region.)*

---

## Slide 8 — Competition

**Title:** Not another monitoring app  

| | Apps / dashboards | Satellite-only | Krishinayan |
|--|-------------------|----------------|----------|
| Offline pump control | Rare | No | **Yes** |
| EC-aware fertilizer block | Rare | No | **Yes** |
| 5-day canopy health | Sometimes | Yes | **Yes** |
| Works without cloud | Rare | N/A | **Yes** |

**Unfair angle:** **Act locally on salt + moisture; verify health from European satellites.**

---

## Slide 9 — Business model

**Title:** How we make money *(adjust to your real plan)*  

**Options (pick one story):**  
- Hardware kit + software subscription per field  
- Software SaaS; farmer brings compatible sensors  
- Pilot / institutional license (co-ops, agri programs)  

**Unit idea:** Per device / per hectare / per season — simple pricing, not complex tiers at pitch stage  

**Say only what you will actually offer in the pilot.**

---

## Slide 10 — Traction & roadmap

**Title:** Where we are · where we go  

**Now**  
- System design: edge AI + dashboard + Sentinel health  
- Offline decision logic (moisture, pH, EC)  
- Pitch-ready product architecture  

**Next 90 days**  
- Field pilot: calibrate sensors · prove offline irrigate / block fertilizer  
- Live dashboard + 5-day NDVI/NDWI on real polygon  

**Then**  
- Multi-crop profiles · water & fertilizer savings metrics · scale kits  

**Pilot success =** decisions without PC · fertilizer blocked when EC high · health trend visible in software  

---

## Slide 11 — Team

**Title:** Team  

**Layout:** Name · role · one relevant strength (hardware / AI / agri / software)  

*Replace with real names.*  

**Why this team:** Can ship embedded control + simple software + domain logic (soil EC, irrigation).  

---

## Slide 12 — The ask

**Title:** The ask  

**We are looking for:**  
- Pilot fields / partners for calibration  
- Funding or support for kits + software polish  
- Agronomy input for crop thresholds  

**Use of support (example):**  
Hardware kits · field calibration · Sentinel pipeline · 1 pilot season metrics  

**Close line:**  
*Krishinayan stops the loop where salinity triggers more fertilizer — with AI that acts in the field and satellites that watch the crop every five days.*

**Contact:** [email / phone / QR]  

---

## Design rules (top-deck style)

1. **≤12 slides** in the main room deck  
2. **Large type**; few bullets; one chart or diagram max per slide  
3. Problem slide = **facts**, not emotion paragraphs  
4. Solution slide = **before/after behavior**, not a feature list  
5. Never claim a % yield for *your* product until pilot data exists  
6. Appendix (optional, not presented unless asked): full FAO numbers, architecture, API list  

---

## 3-minute cut (if time is short)

Speak only: **1 → 2 → 3 → 5 → 6 → 12**

---

## Optional appendix (extra PPT section, not core 12)

- Full architecture diagram  
- UI screen list  
- Sensor pin / hardware sketch  
- Research citation list  
- Image asset map for product screenshots  

---

**End of 12-slide pitch-deck.md**
