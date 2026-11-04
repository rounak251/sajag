"""Paths and the fixed geography of the system: gauge sites and upstream rain points."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
ARTIFACTS = ROOT / "artifacts"
WEB = ROOT / "web"

HISTORY_START = "1985-01-01"
MONSOON_MONTHS = (6, 7, 8, 9, 10)

# Central Water Commission flood-forecast sites in and just outside Bihar.
# Coordinates are approximate. GloFAS cells are 0.05 degrees, so each site is snapped to the
# nearest cell whose August flow fits the river (see sajag/sources/glofas.py). `flow` is the
# plausible range of mean monsoon discharge in m3/s, used only for that snap.
SITES = [
    # id, river, site, lat, lon, flow_low, flow_high
    ("kosi_birpur", "Kosi", "Birpur", 26.52, 86.93, 1500, 9000),
    ("kosi_basua", "Kosi", "Basua", 26.12, 86.60, 1000, 9000),
    ("kosi_baltara", "Kosi", "Baltara", 25.58, 86.63, 1000, 9000),
    ("kosi_kursela", "Kosi", "Kursela", 25.42, 87.25, 1000, 9000),
    ("gandak_valmiki", "Gandak", "Valmikinagar", 27.43, 83.91, 1200, 8000),
    ("gandak_dumaria", "Gandak", "Dumariaghat", 26.55, 84.62, 1000, 8000),
    ("gandak_rewa", "Gandak", "Rewaghat", 26.13, 85.12, 1000, 8000),
    ("gandak_hajipur", "Gandak", "Hajipur", 25.72, 85.20, 1000, 8000),
    ("bgandak_lalbegia", "Burhi Gandak", "Lalbegiaghat", 26.58, 85.05, 40, 900),
    ("bgandak_sikandarpur", "Burhi Gandak", "Sikandarpur", 26.13, 85.40, 60, 1200),
    ("bgandak_samastipur", "Burhi Gandak", "Samastipur", 25.86, 85.78, 80, 1500),
    ("bgandak_rosera", "Burhi Gandak", "Rosera", 25.75, 86.03, 80, 1500),
    ("bagmati_dheng", "Bagmati", "Dheng", 26.72, 85.47, 200, 1500),
    ("bagmati_runni", "Bagmati", "Runnisaidpur", 26.38, 85.47, 40, 1500),
    ("bagmati_benibad", "Bagmati", "Benibad", 26.03, 85.63, 50, 1800),
    ("bagmati_hayaghat", "Bagmati", "Hayaghat", 25.98, 85.98, 50, 2000),
    ("kamla_jainagar", "Kamla", "Jainagar", 26.60, 86.13, 20, 700),
    ("kamla_jhanjharpur", "Kamla", "Jhanjharpur", 26.27, 86.28, 30, 900),
    ("mahananda_taibpur", "Mahananda", "Taibpur", 26.20, 87.96, 100, 2500),
    ("mahananda_dhengra", "Mahananda", "Dhengraghat", 25.70, 87.55, 150, 3500),
    ("ganga_buxar", "Ganga", "Buxar", 25.58, 83.98, 3000, 30000),
    ("ganga_patna", "Ganga", "Gandhighat", 25.62, 85.13, 6000, 45000),
    ("ganga_hathidah", "Ganga", "Hathidah", 25.37, 85.99, 7000, 50000),
    ("ganga_munger", "Ganga", "Munger", 25.38, 86.47, 7000, 55000),
    ("ganga_bhagalpur", "Ganga", "Bhagalpur", 25.27, 87.00, 8000, 60000),
    ("ghaghara_darauli", "Ghaghara", "Darauli", 26.08, 84.13, 2000, 20000),
    ("sone_koelwar", "Sone", "Koelwar", 25.57, 84.80, 200, 8000),
    ("punpun_sripalpur", "Punpun", "Sripalpur", 25.50, 85.22, 5, 500),
]

# Bihar's worst floods start with rain that falls outside Bihar, so the model sees these points
# as well as the rain over each district. Each one sits in the headwaters of a named basin.
UPSTREAM = [
    # id, basin, lat, lon
    ("kosi_tamur", "Kosi", 27.4, 87.4),
    ("kosi_sun", "Kosi", 27.6, 86.0),
    ("kosi_dudh", "Kosi", 27.2, 86.7),
    ("kosi_chatara", "Kosi", 26.9, 87.2),
    ("gandak_narayani", "Gandak", 27.7, 84.4),
    ("gandak_kali", "Gandak", 28.2, 83.7),
    ("gandak_trishuli", "Gandak", 27.9, 85.1),
    ("bagmati_kathmandu", "Bagmati", 27.7, 85.3),
    ("bagmati_sindhuli", "Bagmati", 27.2, 85.7),
    ("kamla_dhanusha", "Kamla", 27.0, 86.1),
    ("bgandak_terai", "Burhi Gandak", 27.1, 84.6),
    ("mahananda_darjeeling", "Mahananda", 26.9, 88.3),
    ("ghaghara_karnali", "Ghaghara", 28.7, 81.6),
    ("ghaghara_rapti", "Ghaghara", 28.0, 82.4),
    ("sone_rihand", "Sone", 24.2, 82.9),
    ("ganga_prayagraj", "Ganga", 25.4, 81.9),
    ("ganga_varanasi", "Ganga", 25.3, 83.0),
]
