#!/usr/bin/env python3
"""Write contract-valid MOCK files into web/data/ so the dashboard can be built and tested.

Real inputs used, read only: district polygons, gauge sites, the blind test event list, declared
droughts and place names. Every model output in here (risk, levels, flows, skill scores) is
invented. `meta.mock` is true, and the page shows a banner while that field is present. The real
pipeline does not write that field, so the banner goes away when Python overwrites web/data/.

Run:  python3 web/dev/make_mock.py
Standard library only. Audio needs macOS `say` and `afconvert`; without them `audio` is left empty,
which is also a state the page has to survive.
"""
import csv
import json
import math
import random
import shutil
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "data"
PROCESSED = ROOT / "data" / "processed"
REFERENCE = ROOT / "data" / "reference"
ISSUED = date(2026, 11, 5)
LEADS = (1, 3, 5, 7)
SEED = 20261105

NAME_HI = {
    "araria": "अररिया", "arwal": "अरवल", "aurangabad": "औरंगाबाद", "banka": "बाँका",
    "begusarai": "बेगूसराय", "bhagalpur": "भागलपुर", "bhojpur": "भोजपुर", "buxar": "बक्सर",
    "darbhanga": "दरभंगा", "east_champaran": "पूर्वी चंपारण", "gaya": "गया",
    "gopalganj": "गोपालगंज", "jamui": "जमुई", "jehanabad": "जहानाबाद", "kaimur": "कैमूर",
    "katihar": "कटिहार", "khagaria": "खगड़िया", "kishanganj": "किशनगंज",
    "lakhisarai": "लखीसराय", "madhepura": "मधेपुरा", "madhubani": "मधुबनी", "munger": "मुंगेर",
    "muzaffarpur": "मुजफ्फरपुर", "nalanda": "नालंदा", "nawada": "नवादा", "patna": "पटना",
    "purnia": "पूर्णिया", "rohtas": "रोहतास", "saharsa": "सहरसा", "samastipur": "समस्तीपुर",
    "saran": "सारण", "sheikhpura": "शेखपुरा", "sheohar": "शिवहर", "sitamarhi": "सीतामढ़ी",
    "siwan": "सीवान", "supaul": "सुपौल", "vaishali": "वैशाली",
    "west_champaran": "पश्चिमी चंपारण",
}
RIVER_HI = {
    "Ganga": "गंगा", "Kosi": "कोसी", "Gandak": "गंडक", "Burhi Gandak": "बूढ़ी गंडक",
    "Bagmati": "बागमती", "Kamla": "कमला", "Mahananda": "महानंदा", "Ghaghara": "घाघरा",
    "Sone": "सोन", "Punpun": "पुनपुन",
}
# Rough courses in lon, lat. Good enough to lay out the map until the pipeline writes real ones.
RIVERS = {
    "Ganga": [(83.62, 25.62), (83.98, 25.58), (84.45, 25.70), (84.85, 25.72), (85.13, 25.64),
              (85.60, 25.48), (85.99, 25.38), (86.47, 25.39), (87.00, 25.27), (87.30, 25.28),
              (87.62, 25.34), (87.90, 24.85)],
    "Kosi": [(87.16, 26.90), (86.93, 26.52), (86.72, 26.30), (86.60, 26.12), (86.58, 25.85),
             (86.63, 25.58), (86.95, 25.46), (87.25, 25.36)],
    "Gandak": [(83.91, 27.45), (84.20, 27.02), (84.62, 26.55), (84.90, 26.32), (85.12, 26.13),
               (85.20, 25.70)],
    "Burhi Gandak": [(84.60, 27.02), (85.05, 26.58), (85.40, 26.13), (85.78, 25.86),
                     (86.03, 25.75), (86.48, 25.46)],
    "Bagmati": [(85.47, 26.95), (85.47, 26.72), (85.47, 26.38), (85.63, 26.03), (85.98, 25.98),
                (86.40, 25.62)],
    "Kamla": [(86.13, 26.78), (86.13, 26.60), (86.28, 26.27), (86.32, 25.92)],
    "Mahananda": [(88.15, 26.55), (87.96, 26.20), (87.75, 25.95), (87.55, 25.70), (87.78, 25.30)],
    "Ghaghara": [(83.45, 26.30), (84.13, 26.08), (84.65, 25.74)],
    "Sone": [(83.45, 24.55), (84.10, 24.83), (84.50, 25.20), (84.80, 25.57), (84.98, 25.68)],
    "Punpun": [(84.70, 24.62), (85.00, 25.05), (85.22, 25.50), (85.34, 25.56)],
}


def write(name, obj):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def catmull(points, steps=8):
    """Smooth a coarse course so rivers do not read as straight segments."""
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for s in range(steps):
            t = s / steps
            out.append(tuple(
                round(0.5 * (2 * p1[a] + (p2[a] - p0[a]) * t
                             + (2 * p0[a] - 5 * p1[a] + 4 * p2[a] - p3[a]) * t * t
                             + (3 * p1[a] - p0[a] - 3 * p2[a] + p3[a]) * t ** 3), 4)
                for a in (0, 1)))
    out.append(points[-1])
    return out


def centroid(feature):
    geom = feature["geometry"]
    rings = [geom["coordinates"][0]] if geom["type"] == "Polygon" else [
        p[0] for p in geom["coordinates"]]
    xs = [c[0] for r in rings for c in r]
    ys = [c[1] for r in rings for c in r]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def season(year):
    d, out = date(year, 6, 1), []
    while d <= date(year, 10, 31):
        out.append(d)
        d += timedelta(days=1)
    return out


def pulse(x, rise=10.0, fall=11.0):
    """0 before the rise, 1 around x = 2, slow decay after. x is days from first report."""
    if x < -rise:
        return 0.0
    if x <= 2:
        return ((x + rise) / (rise + 2)) ** 1.7
    return math.exp(-(x - 2) / fall)


def load_events():
    rows = list(csv.DictReader(open(REFERENCE / "blind_test_events.csv", encoding="utf-8")))
    return [{
        "start": r["first_report"], "end": r["first_report"], "district": r["district"],
        "label": r["event"], "source": "press", "url": r["source"], "rivers": r["rivers"],
    } for r in rows]


def extra_2020():
    """A year the model did see, with multi-day inventory records and no url on some rows."""
    plan = [("east_champaran", "2020-07-21", "2020-08-02"), ("muzaffarpur", "2020-07-24", "2020-08-05"),
            ("darbhanga", "2020-07-22", "2020-08-10"), ("gopalganj", "2020-07-23", "2020-08-01"),
            ("sitamarhi", "2020-07-21", "2020-07-31"), ("samastipur", "2020-07-26", "2020-08-08"),
            ("sheohar", "2020-07-22", "2020-07-30"), ("saran", "2020-07-27", "2020-08-04")]
    return [{"start": a, "end": b, "district": d, "label": "2020 North Bihar flood",
             "source": "inventory", "url": "", "rivers": "Gandak and Bagmati and Burhi Gandak"}
            for d, a, b in plan]


def simulate(year, records, keys, centres, sites, rng):
    dates = season(year)
    n, blind = len(dates), year >= 2024
    t_of = {d.isoformat(): i for i, d in enumerate(dates)}
    hazard = {k: [0.0] * n for k in keys}
    groups = {}
    for r in records:
        groups.setdefault((r["label"], r["start"]), []).append(r)
    for (_, start), rows in groups.items():
        t0 = t_of[start]
        hit = {r["district"] for r in rows}
        for k in hit:
            # A share of real floods get almost no signal: the mock has to show misses.
            amp = rng.uniform(0.22, 0.34) if rng.random() < 0.16 else rng.uniform(0.74, 1.0)
            skew = rng.uniform(-2.0, 2.0)
            for t in range(n):
                hazard[k][t] = max(hazard[k][t], amp * pulse(t - t0 + skew))
        cx = sum(centres[k][0] for k in hit) / len(hit)
        cy = sum(centres[k][1] for k in hit) / len(hit)
        for k in keys:
            if k in hit:
                continue
            dist = math.hypot(centres[k][0] - cx, centres[k][1] - cy)
            if dist < 1.3:  # neighbours rise too, so some alerts are false alarms
                amp = rng.uniform(0.12, 0.58) * (1.3 - dist) / 1.3 + 0.08
                for t in range(n):
                    hazard[k][t] = max(hazard[k][t], amp * pulse(t - t0 - 1))

    noise = {}
    for k in keys:
        v, row = 0.0, []
        for _ in range(n):
            v = 0.86 * v + rng.gauss(0, 0.9)
            row.append(v)
        noise[k] = row
    seasonal = [max(0.0, math.sin(math.pi * t / n)) ** 1.4 for t in range(n)]

    def hz(k, x):
        lo = min(n - 1, max(0, int(x)))
        hi = min(n - 1, lo + 1)
        return hazard[k][lo] + (hazard[k][hi] - hazard[k][lo]) * (x - int(x))

    risk = {str(L): [[0] * len(keys) for _ in range(n)] for L in LEADS}
    level = [[0] * len(keys) for _ in range(n)]
    reasons = {}
    for t in range(n):
        for j, k in enumerate(keys):
            base = 2 + 4 * seasonal[t] + noise[k][t]
            prev = 0
            for L in LEADS:
                v = base + 100 * hz(k, t + 0.75 * L) * (0.60 + 0.05 * L) + 0.5 * L
                v = int(round(min(97, max(prev, v, 0))))
                risk[str(L)][t][j] = v
                prev = v
            r3 = risk["3"][t][j]
            lv = 3 if r3 >= 62 else 2 if r3 >= 40 else 1 if r3 >= 20 else 0
            level[t][j] = lv
            if lv:
                rising = hazard[k][min(n - 1, t + 3)] > hazard[k][t]
                codes = ["river_forecast", "upstream_rain"] if rising else ["river_now", "soil"]
                if lv >= 2:
                    codes.append("statewide" if rng.random() < 0.5 else "local_rain")
                if lv == 1 and rng.random() < 0.4:
                    codes.append("season")
                reasons[f"{t}:{j}"] = codes

    statewide = [round(sum(1 for v in row if v >= 2) / len(keys), 4) for row in level]

    q, peak7 = [[0.0] * len(sites) for _ in range(n)], [[0.0] * len(sites) for _ in range(n)]
    for s, site in enumerate(sites):
        typical = site["typical"]
        wig, series = 0.0, []
        for t in range(n):
            wig = 0.8 * wig + rng.gauss(0, 0.03)
            flow = typical * (0.16 + 0.62 * seasonal[t] + wig)
            series.append(max(typical * 0.05, flow))
        for (_, start), rows in groups.items():
            names = " ".join(r["rivers"] for r in rows)
            if site["river"] in names and (site["river"] != "Gandak" or "Burhi" not in names
                                           or names.count("Gandak") > names.count("Burhi")):
                t0 = t_of[start]
                size = rng.uniform(0.75, 1.15) * typical
                for t in range(n):
                    series[t] += size * pulse(t - t0 + 1, rise=7, fall=7)
        for t in range(n):
            q[t][s] = round(series[t], 1)
            ahead = series[t + 1:t + 8] or [series[t]]
            peak7[t][s] = round(max(ahead) * rng.uniform(0.9, 1.1), 1)

    return {
        "year": year, "blind": blind, "dates": [d.isoformat() for d in dates], "districts": keys,
        "risk": risk, "level": level, "reasons": reasons, "statewide": statewide,
        "sites": [s["id"] for s in sites], "q": q, "peak7": peak7,
        "records": [{k: r[k] for k in ("start", "end", "district", "label", "source", "url")}
                    for r in records],
    }


def make_drought(keys, centres, rng):
    bad = {2009: 1.5, 2010: 1.7, 2013: 1.8, 2018: 1.3, 2019: 0.9, 2022: 1.5, 2015: 0.8, 2005: 1.0}
    wet = {2007: 1.2, 2016: 0.8, 2017: 0.9, 2020: 1.3, 2021: 1.0}
    months, spi3, chance, share = [], [], [], []
    state = {k: 0.0 for k in keys}
    y, m = 1997, 1
    while (y, m) <= (2026, 10):
        months.append(f"{y}-{m:02d}")
        shift = -bad.get(y, 0) + wet.get(y, 0) if 6 <= m <= 10 else 0
        row, ch = [], []
        for k in keys:
            west = (85.5 - centres[k][0]) * 0.18   # drier in the south and west, for shape
            south = (25.6 - centres[k][1]) * 0.22
            state[k] = 0.55 * state[k] + rng.gauss(0, 0.62)
            v = state[k] + shift - (west + south) * (0.6 if shift < 0 else 0.1)
            if (y, m) >= (2026, 8):
                v -= 0.55 + west + south
            v = round(max(-3.0, min(3.0, v)), 2)
            row.append(v)
            ch.append(int(round(100 / (1 + math.exp(1.5 * (v + 0.9))))))
        spi3.append(row)
        chance.append(ch)
        share.append(round(sum(1 for v in row if v <= -1) / len(keys), 4))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    declared = []
    for r in csv.DictReader(open(REFERENCE / "declared_droughts.csv", encoding="utf-8")):
        declared.append({"year": int(r["year"]), "scope": r["scope"], "url": r["source"]})
    return {"months": months, "districts": keys, "spi3": spi3, "chance": chance,
            "state_share": share, "declared": declared}


def river_distance(lon, lat, course):
    return min(math.hypot(lon - x, lat - y) for x, y in course)


def make_villages(keys, centres, rng):
    by_key = {}
    path = PROCESSED / "_places_raw.csv"
    if path.exists():
        for r in csv.DictReader(open(path, encoding="utf-8")):
            if r.get("key"):
                by_key.setdefault(r["key"], []).append((r["name"], float(r["lat"]), float(r["lon"])))
    courses = [catmull(c, 3) for c in RIVERS.values()]
    for k in keys:
        rows = by_key.get(k) or [(f"Village {i + 1}", centres[k][1] + rng.uniform(-.2, .2),
                                  centres[k][0] + rng.uniform(-.2, .2)) for i in range(60)]
        rng.shuffle(rows)
        out = []
        for name, lat, lon in rows[:140]:
            d = min(river_distance(lon, lat, c) for c in courses)
            exposure = int(max(0, min(100, 100 * math.exp(-d / 0.16) + rng.gauss(4, 9))))
            out.append([name, round(lat, 4), round(lon, 4), exposure,
                        2 if exposure >= 66 else 1 if exposure >= 33 else 0])
        out.sort(key=lambda r: -r[3])
        write(f"villages/{k}.json", {"district": k, "villages": out})


TEMPLATES = {
    "hi": {
        "1": {"sms": "सजग: {district} में {days} दिन में बाढ़ संभव। {river} से दूर रहें।",
              "voice": "यह सजग का संदेश है। {district} में अगले {days} दिनों में बाढ़ आ सकती है। "
                       "{river} नदी के पास न जाएँ। सरकारी निर्देश सुनते रहें।"},
        "2": {"sms": "सजग चेतावनी: {district} में {days} दिन में बाढ़। सामान ऊँचे रखें।",
              "voice": "यह सजग की चेतावनी है। {district} में {days} दिन के भीतर बाढ़ की आशंका है। "
                       "ज़रूरी सामान और पशु ऊँची जगह पर ले जाएँ।"},
        "3": {"sms": "सजग गंभीर: {district} में बाढ़ का खतरा। अभी ऊँची जगह जाएँ।",
              "voice": "यह गंभीर चेतावनी है। {district} में बाढ़ का बड़ा खतरा है। "
                       "अभी ऊँची जगह पर जाएँ और प्रशासन के निर्देश मानें।"},
    },
    "mai": {
        "1": {"sms": "सजग: {district} मे {days} दिन मे बाढ़ि संभव। {river} सँ दूर रहू।",
              "voice": "ई सजगक संदेश अछि। {district} मे अगिला {days} दिन मे बाढ़ि आबि सकैत अछि। "
                       "{river} नदीक लग नहि जाउ।"},
        "2": {"sms": "सजग चेतावनी: {district} मे {days} दिन मे बाढ़ि। सामान ऊँच राखू।",
              "voice": "ई सजगक चेतावनी अछि। {district} मे {days} दिनक भीतर बाढ़िक आशंका अछि। "
                       "जरूरी सामान आ माल-जाल ऊँच ठाम ल' जाउ।"},
        "3": {"sms": "सजग गंभीर: {district} मे बाढ़िक खतरा। एखने ऊँच ठाम जाउ।",
              "voice": "ई गंभीर चेतावनी अछि। {district} मे बाढ़िक पैघ खतरा अछि। "
                       "एखने ऊँच ठाम जाउ।"},
    },
    "bho": {
        "1": {"sms": "सजग: {district} में {days} दिन में बाढ़ संभव। {river} से दूर रहीं।",
              "voice": "ई सजग के संदेश बा। {district} में अगिला {days} दिन में बाढ़ आ सकेला। "
                       "{river} नदी के लगे मत जाईं।"},
        "2": {"sms": "सजग चेतावनी: {district} में {days} दिन में बाढ़। सामान ऊँचा राखीं।",
              "voice": "ई सजग के चेतावनी बा। {district} में {days} दिन के भीतर बाढ़ के डर बा। "
                       "जरूरी सामान आ मवेशी ऊँचा जगह ले जाईं।"},
        "3": {"sms": "सजग गंभीर: {district} में बाढ़ के खतरा। अबहीं ऊँचा जगह जाईं।",
              "voice": "ई गंभीर चेतावनी बा। {district} में बाढ़ के बड़ खतरा बा। "
                       "अबहीं ऊँचा जगह पर जाईं।"},
    },
    "en": {
        "1": {"sms": "Sajag: Flood possible in {district} within {days} days. Stay away from the {river}.",
              "voice": "This is a Sajag message. A flood is possible in {district} in the next "
                       "{days} days. Stay away from the {river} river."},
        "2": {"sms": "Sajag warning: Flood likely in {district} within {days} days. Move goods to high ground.",
              "voice": "This is a Sajag warning. A flood is likely in {district} within {days} "
                       "days. Move goods and animals to high ground."},
        "3": {"sms": "Sajag severe: Flood danger in {district}. Go to high ground now.",
              "voice": "This is a severe warning. There is serious flood danger in {district}. "
                       "Go to high ground now and follow official instructions."},
    },
}


def fill(text, lang):
    hindi = lang != "en"
    return (text.replace("{district}", "पटना" if hindi else "Patna")
            .replace("{river}", "गंगा" if hindi else "Ganga").replace("{days}", "3"))


def make_audio():
    say, conv = shutil.which("say"), shutil.which("afconvert")
    audio = {}
    if not (say and conv):
        return audio
    (OUT / "audio").mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        for lang, levels in TEMPLATES.items():
            voice = "Rishi" if lang == "en" else "Lekha"
            for lv, t in levels.items():
                raw = Path(tmp) / f"{lang}_{lv}.aiff"
                dest = OUT / "audio" / f"{lang}_{lv}.m4a"
                done = subprocess.run([say, "-v", voice, "-o", str(raw), fill(t["voice"], lang)],
                                      capture_output=True)
                if done.returncode:
                    continue
                done = subprocess.run([conv, "-f", "m4af", "-d", "aac", str(raw), str(dest)],
                                      capture_output=True)
                if done.returncode == 0:
                    audio.setdefault(lang, {})[lv] = f"audio/{lang}_{lv}.m4a"
    return audio


def check_sms(keys):
    """The contract's 70 character limit, for the worst district and river name."""
    longest_d = max((NAME_HI[k] for k in keys), key=len)
    longest_r = max(RIVER_HI.values(), key=len)
    for lang in ("hi", "mai", "bho"):
        for lv, t in TEMPLATES[lang].items():
            text = (t["sms"].replace("{district}", longest_d).replace("{river}", longest_r)
                    .replace("{days}", "7"))
            assert len(text) <= 70, f"{lang} level {lv}: {len(text)} characters: {text}"


def make_metrics():
    methods = [("Sajag", 1.0), ("Logistic regression", 0.74), ("River level only", 0.62),
               ("3-day rain only", 0.41), ("Climatology", 0.26)]
    budget = []
    for b, scale in ((0.02, 0.72), (0.05, 1.0), (0.10, 1.2)):
        for name, skill in methods:
            budget.append({
                "budget": b, "method": name, "caught_1d": round(min(.97, .66 * scale * skill), 3),
                "caught_3d": round(min(.97, .64 * scale * skill), 3),
                "caught_5d": round(min(.97, .45 * scale * skill), 3),
                "precision": round(.16 * skill / scale, 3)})
    return {
        "headline": {"caught_3d": 0.64, "caught_3d_ci": [0.5, 0.75], "budget": 0.05,
                     "events": 24, "onsets": 130},
        "river": [
            {"lead": 1, "ap_new_model": .62, "ap_new_persistence": .31, "nse_model": .98,
             "nse_persistence": .97, "csi_model": .78, "csi_persistence": .72},
            {"lead": 3, "ap_new_model": .47, "ap_new_persistence": .17, "nse_model": .96,
             "nse_persistence": .93, "csi_model": .66, "csi_persistence": .57},
            {"lead": 5, "ap_new_model": .36, "ap_new_persistence": .11, "nse_model": .92,
             "nse_persistence": .87, "csi_model": .57, "csi_persistence": .46},
            {"lead": 7, "ap_new_model": .29, "ap_new_persistence": .08, "nse_model": .88,
             "nse_persistence": .80, "csi_model": .50, "csi_persistence": .38},
        ],
        "impact": [{"lead": L, "model": m, "pr_auc": round((.21 - .008 * L) * s, 3)}
                   for L in LEADS for m, s in methods],
        "budget": budget,
        "reliability": [{"predicted": p, "observed": o, "n": n} for p, o, n in (
            (.03, .02, 5200), (.06, .05, 2600), (.1, .08, 1200), (.15, .13, 760), (.22, .2, 430),
            (.32, .27, 210), (.45, .39, 96), (.62, .51, 34))],
        "ablation": [{"variant": v, "pr_auc": p} for v, p in (
            ("Full model", .15), ("No river forecast", .13), ("No river stage", .12),
            ("No upstream rain", .11), ("No soil moisture", .14))],
        "blind": {
            "events": [
                {"event": "2024 Ganga flood", "first_report": "2024-09-22", "districts": 7,
                 "warned_1d": 6, "warned_3d": 5, "median_lead": 4},
                {"event": "2024 Nepal rivers flood", "first_report": "2024-09-28", "districts": 14,
                 "warned_1d": 12, "warned_3d": 9, "median_lead": 4},
                {"event": "2025 August Ganga flood", "first_report": "2025-08-03", "districts": 7,
                 "warned_1d": 5, "warned_3d": 3, "median_lead": 2},
                {"event": "2026 September Ganga flood", "first_report": "2026-09-05", "districts": 12,
                 "warned_1d": 10, "warned_3d": 9, "median_lead": 5},
                {"event": "2026 late September flood", "first_report": "2026-09-30", "districts": 6,
                 "warned_1d": 5, "warned_3d": 4, "median_lead": 3},
            ],
            "total": {"district_events": 46, "warned_3d": 30}},
        "drought": {"auc": .9, "rows": [
            {"year": y, "declared": y in (2009, 2010, 2013, 2018, 2019, 2022),
             "share": s} for y, s in zip(range(2006, 2027), (
                .21, .03, .08, .68, .74, .11, .19, .82, .1, .29, .05, .03, .55, .37, 0, .08, .6,
                .16, .21, .13, .26))]},
        "exposure": {"high_flooded": .3, "low_flooded": .05, "ratio": 6.0, "villages": 800},
        "data_story": [
            "Mock text. The flood inventory stops in 2023, so later years are checked against press reports instead.",
            "Mock text. Some records gave a state but no district. These were dropped and not guessed.",
            "Mock text. Gauge positions were snapped to the river cell whose flow matches the real river.",
        ],
        "limits": [
            "Mock text. Flash floods from embankment breaches can arrive with no signal in river flow.",
            "Mock text. Flood records are incomplete, so some false alarms may be real floods nobody logged.",
            "Mock text. Risk is given per district. It cannot say which village floods first.",
            "Mock text. The blind test has few events, so its interval is wide.",
        ],
    }


def main():
    rng = random.Random(SEED)
    OUT.mkdir(parents=True, exist_ok=True)

    geo = json.load(open(PROCESSED / "districts.geojson", encoding="utf-8"))
    for f in geo["features"]:
        f["properties"]["name_hi"] = NAME_HI[f["properties"]["key"]]
    geo.pop("crs", None)
    geo.pop("name", None)
    write("districts.geojson", geo)
    keys = sorted(f["properties"]["key"] for f in geo["features"])
    centres = {f["properties"]["key"]: centroid(f) for f in geo["features"]}

    write("rivers.geojson", {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": n},
         "geometry": {"type": "LineString", "coordinates": catmull(c)}}
        for n, c in RIVERS.items()]})

    sites = []
    for r in csv.DictReader(open(PROCESSED / "sites.csv", encoding="utf-8")):
        typical = float(r["aug2020_q"])
        sites.append({"id": r["site_id"], "river": r["river"], "site": r["site"],
                      "lat": round(float(r["lat"]), 2), "lon": round(float(r["lon"]), 2),
                      "typical": typical})
    write("sites.json", [{**{k: s[k] for k in ("id", "river", "site", "lat", "lon")},
                          "p95": round(s["typical"] * 1.1, 1),
                          "p99": round(s["typical"] * 1.42, 1)} for s in sites])

    events = load_events()
    per_year = {2020: extra_2020()}
    for year in (2024, 2026):
        per_year[year] = [e for e in events if e["start"].startswith(str(year))]
    for year, records in per_year.items():
        write(f"hindcast/{year}.json", simulate(year, records, keys, centres, sites, rng))

    write("meta.json", {
        "mock": True, "issued": ISSUED.isoformat(), "season_active": False,
        "levels": [{"id": 0, "en": "Normal", "hi": "सामान्य"}, {"id": 1, "en": "Watch", "hi": "सतर्क"},
                   {"id": 2, "en": "Warning", "hi": "चेतावनी"}, {"id": 3, "en": "Severe", "hi": "गंभीर"}],
        "reasons": {
            "river_now": {"en": "River already high", "hi": "नदी पहले से ऊँची"},
            "river_forecast": {"en": "River forecast to rise", "hi": "नदी बढ़ने का अनुमान"},
            "upstream_rain": {"en": "Heavy rain upstream", "hi": "ऊपरी इलाकों में भारी बारिश"},
            "local_rain": {"en": "Heavy rain here", "hi": "यहाँ भारी बारिश"},
            "soil": {"en": "Ground already wet", "hi": "ज़मीन पहले से गीली"},
            "statewide": {"en": "Many rivers high across Bihar", "hi": "बिहार में कई नदियाँ ऊँची"},
            "season": {"en": "Peak flood season", "hi": "बाढ़ का मुख्य मौसम"},
        },
        "years": sorted(per_year), "blind_years": [2024, 2025, 2026],
        "stories": [
            {"id": "sep2026", "title": "Ganga, September 2026", "year": 2026,
             "start": "2026-08-24", "end": "2026-09-16", "focus": "patna",
             "caption": "Mock caption. The Ganga rose for about ten days before the first reports on 5 September.",
             "blind": True},
            {"id": "sep2024", "title": "Nepal rivers, September 2024", "year": 2024,
             "start": "2024-09-14", "end": "2024-10-06", "focus": "supaul",
             "caption": "Mock caption. Rain in Nepal sent the Kosi and Gandak up within days.",
             "blind": True},
            {"id": "jul2020", "title": "North Bihar, July 2020", "year": 2020,
             "start": "2020-07-08", "end": "2020-08-06", "focus": "darbhanga",
             "caption": "Mock caption. A year the model trained on, shown for comparison.",
             "blind": False},
        ],
    })

    write("drought.json", make_drought(keys, centres, rng))
    make_villages(keys, centres, rng)

    days = [ISSUED + timedelta(days=i) for i in range(15)]
    live_sites = []
    for s in sites:
        now = s["typical"] * rng.uniform(0.1, 0.24)
        mid = [now * (1 - 0.012 * i) for i in range(15)]
        spread = [0.03 + 0.02 * i for i in range(15)]
        live_sites.append({
            "id": s["id"], "q": round(now, 1), "pct": round(rng.uniform(24, 71), 1),
            "status": "normal",
            "forecast": {
                "dates": [d.isoformat() for d in days], "q": [round(v, 1) for v in mid],
                "p25": [round(v * (1 - w), 1) for v, w in zip(mid, spread)],
                "p75": [round(v * (1 + w), 1) for v, w in zip(mid, spread)],
                "min": [round(v * (1 - 2 * w), 1) for v, w in zip(mid, spread)],
                "max": [round(v * (1 + 2.6 * w), 1) for v, w in zip(mid, spread)]}})
    write("live.json", {
        "issued": ISSUED.isoformat(), "season_active": False,
        "note": "Mock note. The monsoon has ended, so the flood model is resting until June.",
        "districts": {k: {"risk": {"1": 1, "3": 1, "5": 2, "7": 2}, "level": 0, "reasons": []}
                      for k in keys},
        "sites": live_sites})

    check_sms(keys)
    write("alerts.json", {
        "languages": [{"id": "hi", "name": "हिन्दी"}, {"id": "mai", "name": "मैथिली"},
                      {"id": "bho", "name": "भोजपुरी"}, {"id": "en", "name": "English"}],
        "templates": TEMPLATES, "audio": make_audio()})
    write("metrics.json", make_metrics())

    total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"wrote mock data to {OUT} ({total / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
