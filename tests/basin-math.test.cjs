const {test}=require('node:test');
const assert=require('node:assert/strict');
const {mean}=require('../basin-math.js');
test('partial cells contribute in proportion to covered area',()=>{assert.equal(mean([1,3],[[0,.75],[1,.25]]),1.5);});
test('a uniform field remains uniform for any basin',()=>{assert.equal(mean([2,2,2],[[0,.02],[1,.11],[2,.87]]),2);});
test('an incomplete or invalid grid never becomes a zero-rain basin',()=>{assert.equal(mean([1],[[9,1]]),null);assert.equal(mean([NaN],[[0,1]]),null);assert.equal(mean([],[]),null);});
const {cellValue}=require('../basin-math.js');
test('town cells use north-to-south rows in the displayed Mercator grid',()=>{
  const grid={width:2,height:2,extent3857:[-1000,-1000,1000,1000]};
  assert.equal(cellValue([1,2,3,4],grid,-.004,.004),1);
  assert.equal(cellValue([1,2,3,4],grid,.004,.004),2);
  assert.equal(cellValue([1,2,3,4],grid,-.004,-.004),3);
  assert.equal(cellValue([1,2,3,4],grid,.004,-.004),4);
  assert.equal(cellValue([1,2,3,4],grid,10,10),null);
  assert.equal(cellValue([NaN,2,3,4],grid,-.004,.004),null);
  assert.equal(cellValue([1,2],grid,-.004,.004),null);
});
test('new upstream basin geometries have matching complete area weights',()=>{
  const fs=require('node:fs'),path=require('node:path');
  const geo=JSON.parse(fs.readFileSync(path.join(__dirname,'../assets/watersheds.geojson')));
  const weights=JSON.parse(fs.readFileSync(path.join(__dirname,'../assets/watershed-weights.json')));
  for(const id of ['animas','laplata']){
    assert.equal(geo.features.filter(f=>f.properties.id===id).length,1);
    const b=weights.basins.find(b=>b.id===id);
    assert.ok(b.coverage>.998&&b.areaKm2>0);
    assert.ok(Math.abs(b.samples.reduce((sum,row)=>sum+row[1],0)-1)<1e-7);
    assert.ok(b.samples.every(([i,w])=>i>=0&&i<weights.grid.width*weights.grid.height&&w>0));
  }
});
