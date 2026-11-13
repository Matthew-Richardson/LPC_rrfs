# La Plata County RRFS forecast map

A responsive topo map with the **La Plata County outline** and NOAA's public operational **RRFS 3 km** forecasts. County branding comes from `Matthew-Richardson/readyplatav2`; there are no incident, evacuation zone, road closure, or POI overlays and no ArcGIS JavaScript dependency.

## Map features

- Total precipitation, three-hour precipitation, model accumulated new snowfall, and 2 m air temperature.
- Three-hour timeline through 84 hours, animation, previous/next controls, and click-to-read forecast cell values.
- Initialization, valid time, and accumulation periods in Mountain Time (`America/Denver`, including daylight saving).
- Esri topographic basemap, county outline, County/Region views, opacity, scale bar, and **Save map** PNG export with title, times, and legend.
- Model guidance is clearly distinguished from official warnings. A run older than 12 hours is flagged.

## Automatic updates and hosting

The expected GitHub Pages address is **https://matthew-richardson.github.io/LPC_rrfs/**. This address is a deployment target; check the workflow for confirmation of deployment.

The `Update RRFS and publish map` workflow runs on pushes to `main`, manually, and hourly at :35 UTC. It selects the newest **00/06/12/18Z extended run** with an f084 index, validates all fields through hour 84, and publishes a static website to GitHub Pages. This viewer uses the four extended runs, not the shorter hourly cycles. The browser checks the forecast manifest every five minutes; **Refresh** checks immediately. GitHub schedules may run late.

The workflow attempts to enable Pages. If GitHub denies that step, choose **Settings → Pages → Build and deployment → Source → GitHub Actions**, then rerun the workflow. Ensure Actions are allowed. GitHub may disable schedules after 60 days of repository inactivity; check Actions if updates stop.

Download the **LPC-RRFS-static-site** artifact from a successful workflow to host on another server. Upload the ZIP's entire contents, preserving `assets/` and `data/`. GitHub Pages updates automatically; another server needs each new artifact copied or a separate deployment process. Set `Cache-Control: no-cache` for `data/manifest.json` on your own server. Other forecast files use cycle-specific paths and may be cached.

Generated forecast data are saved in the workflow cache and deployment artifacts, not committed to source. A failed forecast build never publishes partial data or replaces the last complete website. Its original run timestamps and stale indicator remain visible. Published site artifacts are retained for seven days. Repeated checks of the same complete cycle reuse the cache.

## Data interpretation

| Product | NOAA field | Treatment |
| --- | --- | --- |
| Total precipitation | APCP, surface, initialization-to-valid accumulation | kg/m² ÷ 25.4 → inches |
| Three-hour precipitation | Difference between successive cumulative APCP fields | Previous three-hour interval; first frame covers initialization through F003 |
| Accumulated snowfall | ASNOW, surface, initialization-to-valid accumulation | meters × 39.37007874 → inches; native model snowfall, not a fixed 10:1 ratio |
| Air temperature | TMP, 2 m above ground | kelvin → °F |

**Precipitation includes the water equivalent of snow, ice, and rain. It is not rainfall only.** ASNOW is new snowfall accumulation, not existing snow depth. No snowline or drainage averages are inferred.

The decoder verifies initialization, valid step, accumulation start, units, and complete HTTP byte-range responses. RRFS encodes ASNOW using an older GRIB master table, so ecCodes can label its units `unknown`. The decoder explicitly recognizes NCEP's discipline 0/category 1/parameter 29 as ASNOW in meters and rejects other unknown fields. Reference: https://www.nco.ncep.noaa.gov/pmb/docs/grib2/grib2_doc/grib2_table4-2-0-1.shtml

The displayed grid covers longitude -108.65 to -106.80 and latitude 36.70 to 38.30. Native Lambert model cells are sampled with nearest-neighbor selection onto a regular Web Mercator display grid. PNGs and click values use identical sample indices. Smaller display pixels do not add resolution beyond the approximately 3 km native grid. Local terrain elevations can differ from the model.

## County outline and basemap

`assets/county.geojson` is a static outline downloaded November 12, 2026 from the public county GIS boundary service:

https://gis.lpcgov.org/arcgis/rest/services/JS_website/Map_Pro/MapServer/83

The outline is bundled with the site and requires no live county layer requests. The logo and favicon were copied from `Matthew-Richardson/readyplatav2`. The topo basemap is Esri World Topographic Map, with credits shown on screen and in exported graphics. The alternative light gray basemap can be selected by unchecking **Topographic basemap**. No API key or account is embedded.

## Local development

Python 3.12 is recommended:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/update_rrfs.py
python -m http.server 8000
```

Open http://localhost:8000. Leaflet 1.9.4, Esri raster basemap tiles, and Google Fonts (with system fallbacks) are external dependencies. The map uses Canvas and ordinary images; WebGL is not required. No backend is needed to serve the finished site.

For a small real-data test: `python scripts/update_rrfs.py --hours 3,6 --output /tmp/rrfs-smoke`. To choose an extended cycle, add `--cycle YYYYMMDDHH`. Only consecutive three-hour steps starting at F003 are supported. The same complete cycle is skipped unless `--force` is supplied.

## NOAA sources

- Operational bucket: https://noaa-rrfs-ops-pds.s3.amazonaws.com/index.html
- Public data and license: https://registry.opendata.aws/noaa-rrfs-ops/
- Product inventory: https://www.nco.ncep.noaa.gov/pmb/products/rrfs/

Only selected GRIB messages are fetched with HTTP byte ranges. Python/ecCodes processes the data; the browser loads small PNG and JSON subsets. No WeatherBELL data, images, or subscriptions are used. NOAA requests attribution; this project does not imply NOAA endorsement.
