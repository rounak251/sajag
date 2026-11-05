# Sajag (सजग): flood and drought early warning for Bihar

**Neural Storm 2026, Green Planet track, problem GP-03: Flood & Drought Early Warning System**

**Team:** Rounak Choudhary (solo), NIT Patna

**Live demo:** https://rounak251.github.io/sajag/

![Replay of the September 2024 flood on the Sajag map](docs/screenshots/map.png)

Sajag forecasts flood risk for Bihar's 38 districts, rates 37,007 villages and towns by exposure, tracks drought, and writes each warning as a one-part SMS and a voice message in Hindi, Maithili, Bhojpuri and English. A Python job on GitHub Actions refreshes the forecast every morning, so it runs with no server, no API keys and no hosting bill.

The main result is a negative one, and it is the most useful thing here. A machine-learning model that looked good in cross-validation failed a blind test. Rain forecasts, not the model, are what made the fixed version work.

## The test that failed

Before running the first model on 2024 to 2026, I wrote down 46 district floods from 5 events, using press reports, and [committed the list](data/reference/blind_test_events.csv) to git. Cross-validation had said the model would catch 60% of floods at least 3 days ahead. On the blind test it caught **3 of 46**.

| Rule | Warned 3+ days ahead, of 46 |
|---|---|
| Version 1, cross-validation promised 60% | **3** |
| 3-day rain threshold | 10 |
| River level threshold | 6 |

It lost to both simple rules, for three reasons:

1. **It had learned the calendar.** Only 1 of its 24 training floods began on or after 15 September, so it treated late September as safe. On 28 September 2024 it scored Darbhanga 0.003, about 1% after calibration, with 161 mm of rain in the previous 3 days. A label bug, found later, had hidden two more late floods from it.
2. **It barely knew the Ganga.** My data cleaning had dropped the 2016 Ganga flood, and the label bug dropped the 2021 one.
3. **It could not see rain coming.** Rain fell in Nepal on 26 to 28 September 2024 and the flood was reported on the 28th. A model that only reads rain already fallen cannot warn on the 25th.

Cross-validation hid the first problem and even favoured the calendar feature, because the training years share the same gap.

## What changed, and what that is worth

Version 2 removes the calendar input, restores the lost floods, and adds a plain rule: raise the alert when extreme rain is forecast over a district or the basin above it. Forecasts come from the [Open-Meteo Previous Runs archive](https://open-meteo.com/en/docs/previous-runs-api), averaging ECMWF and GFS, using only model runs public by 08:00 IST on the issue date. Rain and soil inputs are rebuilt as a morning run would have had them, with NASA's data about 4 days behind.

**These results are not blind.** Version 2 was built after seeing version 1 fail on the same floods, then corrected after an independent review found a label bug and a forecast timing error.

| Flood | First report | Districts | Sajag | Forecast or river, no ML | Forecast only, no ML | 3-day rain | River level |
|---|---|---|---|---|---|---|---|
| 2024 Ganga flood | 22 Sep 2024 | 7 | **0** | 0 | 0 | 3 | 2 |
| 2024 Nepal rivers flood | 28 Sep 2024 | 14 | **14** | 14 | 14 | 2 | 0 |
| 2025 August Ganga flood | 3 Aug 2025 | 7 | **6** | 6 | 2 | 2 | 3 |
| 2026 September Ganga flood | 5 Sep 2026 | 12 | **6** | 5 | 7 | 4 | 4 |
| 2026 late September flood | 30 Sep 2026 | 6 | **6** | 6 | 6 | 6 | 2 |
| **Total warned 3+ days ahead** | | **46** | **32** | **31** | **29** | **17** | **11** |

Every rule gets the same 9.3% alert rate, with its threshold set in hindsight on these years.

What the table says:

- **Rain forecasts do the work.** A forecast threshold with no machine learning catches 29, and forecast or river level catches 31, against Sajag's 32. The model's own contribution is too small to measure on 46 floods.
- **It only just beats chance.** Moving each flood to random days between July and September, 2,000 times, catches 18.7 on average and 31 at the 95th percentile (p = 0.044).
- **Timing is better than place.** In September 2024, none of the 14 named districts was at Warning from 8 to 22 September, all 14 were by the 24th, and 7 of 24 other districts were warned too. In August 2025 it warned 23 of 31 other districts.
- **Some hits are soft.** 25 of the 39 districts named in a first report were warned. For 19 of the 46, an alert was already running 8 days before.

The real test is the next monsoon. Each daily run writes [`forecast_log/`](forecast_log) and commits it, so every forecast is on record before its outcome is known.

## Results

**River forecast: the part that passed the blind test.** Scored on 2024 to 2026 and unchanged since the blind run. The score is average precision for a river crossing its 99th percentile while it is still below it. The target is GloFAS modelled flow, not gauge readings, and GloFAS changes product on 5 August 2023, so the model was trained on one product and tested on the other.

| Days ahead | Sajag | Persistence | NSE, Sajag | NSE, persistence |
|---|---|---|---|---|
| 1 | 0.677 | 0.217 | 0.988 | 0.981 |
| 3 | 0.531 | 0.267 | 0.957 | 0.924 |
| 5 | 0.420 | 0.275 | 0.921 | 0.854 |
| 7 | 0.372 | 0.287 | 0.882 | 0.777 |

**Cross-validation, 2006 to 2023, observed data only.** All methods alert on the same 5% of district days, and 3-year blocks are held out together. Sajag caught 42% of 166 flood starts from 31 events at least 3 days ahead (95% interval 25% to 59%, resampling whole events), against 34% for 3-day rain, 25% for river level and 16% for climatology. The lead over the rain rule is not statistically clear: the interval on the difference runs from -5 to +21 points.

**Drought.** The share of districts with SPI-3 at or below -1 at the end of August separates the 6 years Bihar declared drought from the rest with AUC 0.94, and the forecast from the end of July reaches 0.88. Six years is few, and a declaration is partly a political decision. Month to month, the forecast only just beats assuming nothing changes (AUC 0.875 against 0.859).

**Village exposure.** The score uses a satellite water record ending in 2021 plus land height, so it knows nothing of 2024. On a Sentinel-1 flood map of the Kosi plain from 9 October 2024, flood water was mapped within 500 m of 34.7% of high-exposure villages, 15.3% of medium and 3.7% of low, across 6,222 villages. That is one flood, on one date, in one area.

Every number is on the [Evidence page](https://rounak251.github.io/sajag/#/evidence), with the ablations and reliability plot.

## How it works

1. **Rain-forecast rule.** Raises the level when the 5-day forecast over a district, or the tributary basin above it, passes the 90th, 95th or 98th percentile of rain that really fell in 2006 to 2023. Districts south of the Ganga use only their own rain and the Sone.
2. **District flood risk.** LightGBM, 5 seeds averaged, trained on recorded floods from 2006 to 2023. Rain and river inputs are constrained so more water can never lower the risk. SHAP values become the plain-language reasons on screen.
3. **River forecast.** LightGBM across 27 sites, predicting peak flow 1 to 7 days out from upstream gauges and rain at 17 headwater points, most of them in Nepal.
4. **Drought.** SPI on NASA POWER rainfall, with a one-month forecast.
5. **Alerts.** Templates are tested so every SMS fits one message for all 38 district names: 70 characters in Devanagari, 160 in English. Audio is generated for IVR.

### Data problems worth knowing about

- IMD's records change format around 2005. Earlier rows cover all 38 districts for weeks, so training starts in 2006.
- Day and month are swapped in some rows: `07-11-2017` with a 3-day duration ending 13 July means 11 July. Durations and record order repaired 10 of 119 events ([`sajag/sources/ifi.py`](sajag/sources/ifi.py)).
- Many rows are heavy-rain deaths with no river flood. Filtering them out once also dropped 9 real floods, because on pandas 3 a single blank cell blanked a row's whole text. A test now covers it.

### Limits

- Five floods is a small test, the results are not blind, and the model adds little over a forecast threshold.
- It missed the 2024 Ganga flood entirely.
- Districts average 14 Warning days a season, from 30 in Katihar to under 1 in Sheikhpura. Many alerts will not be followed by a flood.
- Forecasts run wetter than NASA's rain at the low end: Watch fires on 18% of district days against 11% for the rain that then fell. Warning matches, and Severe fires less often (1.8% against 3.0%).
- River flows are GloFAS model output. A first report is when the press named a district, so water may have arrived earlier.
- Flood records are incomplete, so false alarms cannot be counted exactly. The forecast rule can only be tested from 2024, when the archive starts.
- Village lists are thin for Sheohar (8) and Sitamarhi (73).
- Maithili and Bhojpuri text was drafted by an AI tool and needs review by native speakers. Their audio uses a Hindi voice.

**This is a research prototype, not an official warning.** Follow IMD, CWC and BSDMA instructions.

## Tech stack

Python 3.12, LightGBM, scikit-learn, SciPy, pandas, NumPy, GeoPandas, rasterio, Shapely, pytest and ruff. The dashboard is plain HTML, CSS and JavaScript with Leaflet and IBM Plex fonts, all vendored. GitHub Actions and GitHub Pages run the daily job and hosting.

| Data | Used for | Source |
|---|---|---|
| India Flood Inventory v3 | Flood labels | [IIT Delhi and IMD](https://github.com/hydrosenselab/India-Flood-Inventory) |
| NASA POWER | Rain and soil wetness | [NASA](https://power.larc.nasa.gov/) |
| GloFAS | River flow | [Copernicus, via Open-Meteo](https://open-meteo.com/en/docs/flood-api) |
| ECMWF IFS and GFS | Rain forecasts | [Open-Meteo](https://open-meteo.com/) |
| Global Surface Water | Village exposure | [JRC](https://global-surface-water.appspot.com/) |
| Copernicus GLO-90 | Land height | [ESA, on AWS](https://registry.opendata.aws/copernicus-dem/) |
| GeoNames, OpenStreetMap | Village names and rivers | [GeoNames](https://www.geonames.org/), [OSM](https://www.openstreetmap.org/) |
| geoBoundaries | District outlines | [geoBoundaries](https://www.geoboundaries.org/) |

## Setup

You need Python 3.12 and [uv](https://docs.astral.sh/uv/). No API keys.

```bash
git clone https://github.com/rounak251/sajag.git
cd sajag
make setup
```

## Run it locally

The repo includes the trained models and dashboard data, so this is all you need to see it working:

```bash
make serve          # http://localhost:8000
make test           # unit tests
```

Today's forecast from live data takes a few minutes and needs network access, since it calls NASA POWER and Open-Meteo:

```bash
.venv/bin/python -m sajag.forecast
```

To rebuild everything from raw data, which downloads about 250 MB and takes roughly an hour, mostly waiting on API rate limits:

```bash
make data train score web
```

`make score` includes `scripts/blind_test.py`, which now scores version 2. Version 1's blind result is kept in [`artifacts/metrics_blind.json`](artifacts/metrics_blind.json), and the commit history shows the order: the test list is in `c388381` and the result in `1a78945`.

`scripts/make_audio.py` records the voice messages and needs macOS. `scripts/build_villages.py` runs its flood map check only if the optional Sentinel-1 map is present.

## Screenshots

| Evidence | Alert preview | Phone |
|---|---|---|
| ![Evidence page opening with the failed blind test](docs/screenshots/evidence.png) | ![Hindi SMS and voice alert preview](docs/screenshots/alert.png) | ![Map on a phone](docs/screenshots/phone.png) |

## AI tools used

Built with [Claude Code](https://claude.com/claude-code) (Claude Opus). It wrote the code, the dashboard and this README, ran the experiments, drafted the Maithili and Bhojpuri messages, and ran an independent review whose findings are fixed above. Rounak Choudhary directed the project.

## Built during the hackathon

All code in this repo was written on 4 and 5 November 2026, within the extended submission window. The Sentinel-1 flood map used to test village exposure comes from the author's earlier SARITA project. It is used only for that check, and no earlier code was reused.

## License

MIT. Data sources keep their own licences.
