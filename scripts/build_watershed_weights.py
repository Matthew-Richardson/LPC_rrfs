#!/usr/bin/env python3
"""Rebuild area weights against the displayed RRFS grid. Offline optional tool.
Requires shapely and pyproj; neither is needed by the browser or model updater.
Input: assets/watersheds.geojson. Output: assets/watershed-weights.json.
"""
import json
from pathlib import Path
import math
from shapely.geometry import shape, Polygon
from shapely.ops import transform
from pyproj import Transformer

ROOT=Path(__file__).resolve().parents[1]
WIDTH,HEIGHT=144,156
BOUNDS=[-108.65,36.70,-106.80,38.30]
R=6378137.0

def build():
    source=json.loads((ROOT/'assets/watersheds.geojson').read_text())
    to_equal=Transformer.from_crs(4326,5070,always_xy=True).transform
    to_geo=Transformer.from_crs(3857,4326,always_xy=True).transform
    to_xy=Transformer.from_crs(4326,3857,always_xy=True).transform
    west,south,east,north=BOUNDS
    x0,y0=to_xy(west,south);x1,y1=to_xy(east,north)
    dx,dy=(x1-x0)/WIDTH,(y1-y0)/HEIGHT
    records=[]
    for f in source['features']:
        original=shape(f['geometry'])
        assert original.is_valid and not original.is_empty
        geom=transform(to_equal,original)
        minlon,minlat,maxlon,maxlat=original.bounds
        assert west<minlon<maxlon<east and south<minlat<maxlat<north,'Basin extends beyond forecast coverage'
        minx,miny=to_xy(minlon,minlat);maxx,maxy=to_xy(maxlon,maxlat)
        cols=range(max(0,int((minx-x0)/dx)),min(WIDTH,int((maxx-x0)/dx)+1))
        rows=range(max(0,int((y1-maxy)/dy)),min(HEIGHT,int((y1-miny)/dy)+1))
        samples=[]
        for row in rows:
            for col in cols:
                a=x0+col*dx;b=y1-row*dy
                corners=[to_geo(a,b),to_geo(a+dx,b),to_geo(a+dx,b-dy),to_geo(a,b-dy)]
                cell=transform(to_equal,Polygon(corners))
                area=geom.intersection(cell).area
                if area>0:samples.append([row*WIDTH+col,area])
        covered=sum(w for i,w in samples)
        assert abs(covered/geom.area-1)<.002, 'Incomplete watershed coverage'
        samples=[[i,round(w/covered,12)] for i,w in samples]
        center=original.representative_point()
        records.append({'id':f['properties']['id'],'areaKm2':round(geom.area/1e6,2),'anchor':[center.y,center.x],'samples':samples,'coverage':covered/geom.area})
        print(f['properties']['name'],records[-1]['areaKm2'],'km2;',len(samples),'display samples')
    out={'schema':1,'grid':{'width':WIDTH,'height':HEIGHT,'bounds':BOUNDS},'method':'Area-weighted intersections in equal-area EPSG:5070 against the nearest-neighbor mapped RRFS grid; display samples do not add native model resolution.','basins':records}
    (ROOT/'assets/watershed-weights.json').write_text(json.dumps(out,separators=(',',':'))+'\n')
if __name__=='__main__':build()
