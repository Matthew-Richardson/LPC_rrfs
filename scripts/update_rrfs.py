#!/usr/bin/env python3
"""Publish a small, georeferenced RRFS subset from NOAA's public operational feed.

Only selected GRIB messages are downloaded with HTTP byte ranges. All fields use
the CONUS 3 km grid. No WeatherBELL graphics or third-party forecast data are used.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import io
import json
import math
from pathlib import Path
import re
import shutil
import time
import urllib.error
import urllib.request
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
import eccodes as ec

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://noaa-rrfs-ops-pds.s3.amazonaws.com'
BOUNDS = [-108.65, 36.70, -106.80, 38.30]  # W,S,E,N; surrounding San Juan terrain
WIDTH, HEIGHT = 144, 156
HOURS = list(range(3, 85, 3))
RADIUS = 6378137.0
PRODUCTS = {
    'qpf': {'label': 'Total precipitation', 'unit': 'in', 'levels': [0.01,.05,.1,.25,.5,.75,1,1.5,2,3,4],
            'colors': ['#d7e6ee','#98d5b4','#50bc83','#1b9864','#147b95','#1766ac','#4b55b4','#8c46a8','#c33d8e','#eb665a','#f8b84e'],
            'description': 'Water equivalent of all precipitation, including snow, accumulated since model initialization. Not rainfall only.'},
    'qpf3': {'label': 'Three-hour precipitation', 'unit': 'in', 'levels': [.01,.05,.1,.25,.5,.75,1,1.5,2,3,4],
             'colors': ['#d7e6ee','#98d5b4','#50bc83','#1b9864','#147b95','#1766ac','#4b55b4','#8c46a8','#c33d8e','#eb665a','#f8b84e'],
             'description': 'Water equivalent of all precipitation during the three hours ending at the selected valid time. Includes snow.'},
    'snow': {'label': 'Accumulated snowfall', 'unit': 'in', 'levels': [.1,1,2,4,6,8,12,18,24,36,48],
             'colors': ['#dcecf6','#a7d9ec','#75bddf','#4389c6','#375caa','#514797','#8b49aa','#be55b6','#e871bf','#f4a0ce','#fff0fa'],
             'description': 'Model accumulated new snowfall (ASNOW), since initialization; not snow depth and not a fixed 10:1 conversion.'},
    'temp': {'label': 'Air temperature', 'unit': '°F', 'levels': [-30,0,10,20,28,32,36,40,50,60,70,80,90],
             'colors': ['#583790','#6855ae','#657bbd','#6da9d2','#8cd0df','#c5e7e5','#e8edca','#f3df97','#f4b46f','#e88659','#ce5d54','#ad4054','#7c294c'],
             'description': 'Instantaneous model air temperature at 2 meters above the model terrain. Local elevations can differ from the model grid.'},
}


for key, label, desc in [
    ('rain', 'Estimated total rainfall', 'Sum of three-hour precipitation minus three-hour snowfall water equivalent, since initialization. Snow removed; freezing rain or other mixed precipitation may remain.'),
    ('rain3', 'Estimated three-hour rainfall', 'Three-hour precipitation minus three-hour model snowfall water equivalent. Snow removed; freezing rain or other mixed precipitation may remain.'),
]:
    PRODUCTS[key] = {**PRODUCTS['qpf'], 'label': label, 'description': desc}


def fetch(url, headers=None):
    """Retry transient failures, but do not conceal a missing model file."""
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'LPC-RRFS-public-map/1.0', **(headers or {})})
            with urllib.request.urlopen(req, timeout=90) as response:
                if headers and 'Range' in headers and response.status != 206:
                    raise RuntimeError('Server ignored byte range; refusing full-CONUS download')
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                raise
            if attempt == 2:
                raise
        except (TimeoutError, urllib.error.URLError):
            if attempt == 2:
                raise
        time.sleep(attempt + 1)


def model_url(cycle, hour):
    return f'{BASE}/rrfs.{cycle:%Y%m%d}/{cycle:%H}/rrfs.t{cycle:%H}z.2dfld.3km.f{hour:03d}.conus.grib2'


def parse_index(text):
    rows = []
    for line in text.strip().splitlines():
        pieces = line.split(':')
        if len(pieces) >= 6:
            rows.append({'offset': int(pieces[1]), 'variable': pieces[3], 'level': pieces[4], 'description': pieces[5]})
    for i, row in enumerate(rows):
        row['end'] = rows[i + 1]['offset'] - 1 if i + 1 < len(rows) else None
    return rows


def select_record(rows, variable, level, cumulative=False):
    matches = [r for r in rows if r['variable'] == variable and r['level'] == level]
    if cumulative:
        matches = [r for r in matches if re.match(r'0-\d+ (hour|day).*acc fcst', r['description'])]
    if len(matches) != 1:
        raise ValueError(f'Expected one {variable} {level} cumulative={cumulative}; found {len(matches)}')
    return matches[0]


def get_message(url, row):
    ending = '' if row['end'] is None else row['end']
    data = fetch(url, {'Range': f"bytes={row['offset']}-{ending}"})
    if not data.startswith(b'GRIB') or not data.endswith(b'7777'):
        raise ValueError('Incomplete GRIB message')
    return data


def mercator(lon, lat):
    return RADIUS * np.deg2rad(lon), RADIUS * np.log(np.tan(np.pi / 4 + np.deg2rad(lat) / 2))


def build_grid(message):
    g = ec.codes_new_from_message(message)
    try:
        lat = ec.codes_get_array(g, 'latitudes')
        lon = (ec.codes_get_array(g, 'longitudes') + 180) % 360 - 180
    finally:
        ec.codes_release(g)
    w, s, e, n = BOUNDS
    subset = np.flatnonzero((lat >= s-.15) & (lat <= n+.15) & (lon >= w-.15) & (lon <= e+.15))
    if len(subset) == 0:
        raise ValueError('No RRFS grid cells cover map extent')
    x0, y0 = mercator(w, s)
    x1, y1 = mercator(e, n)
    dx, dy = (x1-x0)/WIDTH, (y1-y0)/HEIGHT
    xx, yy = np.meshgrid(x0+(np.arange(WIDTH)+.5)*dx, y1-(np.arange(HEIGHT)+.5)*dy)
    x, y = mercator(lon[subset], lat[subset])
    distance, index = cKDTree(np.column_stack([x,y])).query(np.column_stack([xx.ravel(), yy.ravel()]))
    if np.max(distance) > 7000:
        raise ValueError('Map extent extends outside the model grid')
    return subset[index], {'width': WIDTH, 'height': HEIGHT, 'bounds': BOUNDS,
                            'extent3857': [float(x0),float(y0),float(x1),float(y1)],
                            'sampling': 'Nearest 3 km model grid cell; north-to-south rows in Web Mercator'}


def decode(message, indices, cycle, hour, cumulative, expected_units):
    g = ec.codes_new_from_message(message)
    try:
        units = ec.codes_get(g, 'units')
        # RRFS encodes ASNOW with master table version 2. ecCodes can report
        # 'unknown' even though NCEP identifies 0/1/29 as Total Snowfall [m].
        # Accept that one explicit parameter, never arbitrary unknown fields.
        asnow = tuple(ec.codes_get(g,k) for k in ('discipline','parameterCategory','parameterNumber')) == (0,1,29)
        snow_water = tuple(ec.codes_get(g,k) for k in ('discipline','parameterCategory','parameterNumber')) == (0,1,50)
        if units not in expected_units and not (units == 'unknown' and ((asnow and expected_units == {'m'}) or (snow_water and 'kg m**-2' in expected_units))):
            raise ValueError(f'Unexpected field units: {units}')
        date = int(ec.codes_get(g, 'dataDate'))
        clock = int(ec.codes_get(g, 'dataTime'))
        if date != int(cycle.strftime('%Y%m%d')) or clock != cycle.hour * 100:
            raise ValueError('GRIB initialization differs from selected cycle')
        ec.codes_set(g, 'stepUnits', 1)  # Explicit hours, including day-based index strings
        if int(ec.codes_get(g, 'endStep')) != hour:
            raise ValueError('Unexpected GRIB forecast end step')
        if cumulative and int(ec.codes_get(g, 'startStep')) != 0:
            raise ValueError('Refusing interval accumulation as a run-total field')
        values = ec.codes_get_values(g)[indices]
        if not np.all(np.isfinite(values)) or np.any(np.abs(values) > 1e10):
            raise ValueError('Missing or invalid GRIB grid values')
        return values.reshape(HEIGHT, WIDTH)
    finally:
        ec.codes_release(g)


def colorize(values, product):
    spec = PRODUCTS[product]
    colors = np.array([tuple(bytes.fromhex(c[1:])) + (230,) for c in spec['colors']], dtype=np.uint8)
    bins = np.searchsorted(spec['levels'], values, side='right') - 1
    rgba = colors[np.clip(bins, 0, len(colors)-1)]
    if product != 'temp':
        rgba[bins < 0, 3] = 0
    return rgba


def frame_data(cycle, hour, indices):
    url = model_url(cycle, hour)
    rows = parse_index(fetch(url + '.idx').decode())
    result = {}
    for product, variable, level, units in [
        ('qpf','APCP','surface',{'kg m**-2','kg m-2'}),
        ('snowwater','TSNOWP','surface',{'kg m**-2','kg m-2'}),
        ('snow','ASNOW','surface',{'m'}),
        ('temp','TMP','2 m above ground',{'K'}),
    ]:
        message = get_message(url, select_record(rows, variable, level, product != 'temp'))
        result[product] = decode(message, indices, cycle, hour, product != 'temp', units)
    result['snowwater'] = np.maximum(result['snowwater'], 0)/25.4
    result['qpf'] = np.maximum(result['qpf'], 0)/25.4
    result['snow'] = np.maximum(result['snow'], 0)*39.37007874
    result['temp'] = (result['temp']-273.15)*1.8+32
    return hour, result


def available_cycle(now, required_hour):
    latest = now.replace(minute=0, second=0, microsecond=0)
    latest -= timedelta(hours=latest.hour % 6)
    for back in range(0, 49, 6):
        cycle = latest - timedelta(hours=back)
        try:
            fetch(model_url(cycle, required_hour) + '.idx')
            return cycle
        except urllib.error.HTTPError as exc:
            if exc.code not in (403,404):
                raise
    raise RuntimeError('No complete extended RRFS cycle found in the past 48 hours')


def run(args):
    output = Path(args.output)
    hours = [int(x) for x in args.hours.split(',')] if args.hours else HOURS
    if sorted(set(hours)) != hours or hours != list(range(3, max(hours)+1, 3)) or max(hours)>84:
        raise ValueError('Hours must be consecutive three-hour steps starting at 3, through at most 84')
    cycle = datetime.strptime(args.cycle,'%Y%m%d%H').replace(tzinfo=timezone.utc) if args.cycle else available_cycle(datetime.now(timezone.utc),max(hours))
    if cycle.hour not in (0,6,12,18):
        raise ValueError('Use an extended 00/06/12/18Z cycle')
    cycle_id = cycle.strftime('%Y%m%d%H')
    current = output/'manifest.json'
    if current.exists() and not args.force:
        old = json.loads(current.read_text())
        if old.get('cycle') == cycle_id and [f['hour'] for f in old.get('frames',[])] == hours and 'rain' in old.get('products', {}):
            print(f'Complete cycle {cycle_id} is already published'); return
    print(f'Building RRFS {cycle_id}, {len(hours)} frames', flush=True)
    url = model_url(cycle,hours[0])
    rows = parse_index(fetch(url+'.idx').decode())
    indices, grid = build_grid(get_message(url,select_record(rows,'APCP','surface',True)))
    staging = output / f'.{cycle_id}.staging'
    if staging.exists(): shutil.rmtree(staging)
    staging.mkdir(parents=True)
    frames = []
    previous = np.zeros((HEIGHT,WIDTH))
    previous_rain = np.zeros((HEIGHT,WIDTH))
    previous_snowwater = np.zeros((HEIGHT,WIDTH))
    try:
        # map preserves chronological order; only two CONUS decoders run at once.
        with ThreadPoolExecutor(max_workers=2) as pool:
            for hour, fields in pool.map(lambda h: frame_data(cycle,h,indices),hours):
                delta = fields['qpf']-previous
                if np.min(delta) < -.02:
                    raise ValueError('Cumulative precipitation decreases by >0.02 in; cannot compute intervals')
                fields['qpf3'] = np.maximum(delta,0)
                snowwater = fields.pop('snowwater')
                snow_interval = np.maximum(snowwater - previous_snowwater, 0)
                fields['rain3'] = np.maximum(fields['qpf3'] - snow_interval, 0)
                fields['rain'] = previous_rain + fields['rain3']
                previous_rain = fields['rain']
                previous_snowwater = snowwater
                previous = fields['qpf']
                for product, values in fields.items():
                    Image.fromarray(colorize(values,product)).save(staging/f'{product}-{hour:03d}.png')
                payload = {k: np.round(v, 2 if k!='temp' else 1).ravel().tolist() for k,v in fields.items()}
                (staging/f'grid-{hour:03d}.json').write_text(json.dumps(payload,separators=(',',':'),allow_nan=False))
                frames.append({'hour':hour,'valid':(cycle+timedelta(hours=hour)).isoformat(),
                               'intervalStart':(cycle+timedelta(hours=hour-3)).isoformat(),
                               'source':model_url(cycle,hour)})
                print(f'  f{hour:03d} complete',flush=True)
        manifest = {'schema':1,'model':'NOAA RRFS operational CONUS 3 km','cycle':cycle_id,
                    'initialized':cycle.isoformat(),'generated':datetime.now(timezone.utc).isoformat(),
                    'grid':grid,'products':PRODUCTS,'frames':frames,'directory':cycle_id,
                    'source':BASE,'forecastStepHours':3,'completeThroughHour':max(hours)}
        output.mkdir(parents=True,exist_ok=True)
        destination = output/cycle_id
        if destination.exists(): shutil.rmtree(destination)
        staging.rename(destination)
        temp_manifest = output/'manifest.tmp'
        temp_manifest.write_text(json.dumps(manifest,indent=2)+'\n')
        temp_manifest.replace(current)  # Publish only after every field/frame succeeded.
        for path in output.iterdir():
            if path.is_dir() and re.fullmatch(r'\d{10}',path.name) and path.name != cycle_id:
                shutil.rmtree(path)
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise
    print(f'Published {cycle_id} through f{max(hours):03d}',flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default=str(ROOT/'data'))
    p.add_argument('--cycle',help='Optional UTC initialization YYYYMMDDHH')
    p.add_argument('--hours',help='Consecutive three-hour frames, e.g. 3,6 for a smoke test; default 3..84')
    p.add_argument('--force',action='store_true')
    run(p.parse_args())
