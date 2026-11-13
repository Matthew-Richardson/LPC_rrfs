/* global L */
'use strict';
const $ = id => document.getElementById(id);
const escapeHTML = text => String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const formatTime = (date, short=false) => new Intl.DateTimeFormat('en-US', {
  timeZone:'America/Denver', weekday:'short', month:'short', day:'numeric',
  hour:'numeric', minute:short?undefined:'2-digit', timeZoneName:short?undefined:'short'
}).format(new Date(date));
const state = {manifest:null, product:'qpf', index:27, busy:false, playing:false, timer:null, grids:new Map(), renderId:0, displayed:null};
let map, forecastLayer, boundary, topo, gray;
const countyBounds = [[36.96,-108.4],[37.92,-107.30]];
async function readJSON(url) {
  const response = await fetch(url,{cache:'no-store'});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}
function stopPlayback() {
  clearTimeout(state.timer);state.timer=null;state.playing=false;
  $('play').textContent='▶';$('play').setAttribute('aria-label','Play forecast animation');
}
function updateLegend() {
  const spec=state.manifest.products[state.product];
  $('legendTitle').textContent=spec.label;$('legendUnit').textContent=spec.unit;$('productDescription').textContent=spec.description;
  $('legendRamp').replaceChildren(...spec.colors.map(color=>{const s=document.createElement('span');s.style.background=color;return s;}));
  // Equal-width color bins: each threshold sits directly under its color.
  $('legendTicks').replaceChildren(...spec.levels.map((value,i)=>{const s=document.createElement('span');s.textContent=value+(i===spec.levels.length-1?'+':'');return s;}));
  $('legendNote').textContent=state.product==='temp'?'2 m air temperature · model terrain':`Transparent areas: less than ${spec.levels[0]} ${spec.unit}`;
}
function refreshAge() {
  if(!state.manifest)return;
  const age=(Date.now()-Date.parse(state.manifest.initialized))/3600000;
  $('freshness').classList.toggle('stale',age>12);
  $('freshness').textContent=age>12?`Older run · ${Math.floor(age)}h`:'Latest complete run';
  $('freshness').title='Latest complete extended cycle found by the updater; shorter hourly cycles are not displayed.';
  $('generated').textContent=`Processed ${formatTime(state.manifest.generated)}`;
}
async function loadForecast() {
  $('refresh').disabled=true;
  try {
    const manifest=await readJSON(`data/manifest.json?t=${Date.now()}`);
    if(manifest.schema!==1||!manifest.frames?.length||!manifest.products?.qpf)throw new Error('Invalid forecast manifest');
    const changed=state.manifest?.cycle!==manifest.cycle;
    stopPlayback();state.manifest=manifest;
    if(changed){state.grids.clear();state.index=Math.min(state.index,manifest.frames.length-1);}
    $('runTime').textContent=`${formatTime(manifest.initialized)} · ${manifest.initialized.slice(11,13)}Z`;
    $('hour').max=manifest.frames.length-1;$('rangeEnd').textContent=`Through ${manifest.completeThroughHour} hours`;
    const ticks=[0,Math.floor((manifest.frames.length-1)/2),manifest.frames.length-1];
    $('timeTicks').replaceChildren(...ticks.map(i=>{const s=document.createElement('span');s.textContent=formatTime(manifest.frames[i].valid,true);return s;}));
    refreshAge();updateLegend();await showFrame();
    for(const id of ['hour','play','previous','next','download'])$(id).disabled=false;
    notice('');
  }catch(error){
    console.error('Forecast unavailable:',error);
    if(state.manifest)notice('Update check failed. Showing the previously loaded run.');
    else{$('runTime').textContent='Forecast data unavailable';$('freshness').textContent='No forecast loaded';$('freshness').classList.add('stale');notice('Forecast could not load. Try Refresh. The topo map remains available.');}
  }finally{$('refresh').disabled=false;}
}
let boundaryError='';
function notice(message){$('mapNotice').textContent=message||boundaryError;}
function assetPath(file,manifest=state.manifest){return `data/${manifest.directory}/${file}`;}
async function showFrame(){
  if(!state.manifest)return;
  const requestId=++state.renderId, manifest=state.manifest, product=state.product;
  const frame=manifest.frames[state.index], hour=String(frame.hour).padStart(3,'0');
  const path=assetPath(`${product}-${hour}.png`,manifest);state.busy=true;
  try{
    const image=new Image();image.src=path;await image.decode();if(requestId!==state.renderId)return;
    const [w,s,e,n]=manifest.grid.bounds;
    const nextLayer=L.imageOverlay(path,[[s,w],[n,e]],{pane:'forecast',opacity:Number($('opacity').value)/100,interactive:false});
    nextLayer.addTo(map);if(forecastLayer)forecastLayer.remove();forecastLayer=nextLayer;
    state.displayed={manifest,product,frame};map.closePopup();
    $('hour').value=state.index;$('validTime').textContent=formatTime(frame.valid);
    $('period').textContent=['qpf3','rain3'].includes(product)?`3 hours: ${formatTime(frame.intervalStart,true)} → ${formatTime(frame.valid,true)}`:product==='temp'?'Instantaneous model forecast':`Accumulation since ${formatTime(manifest.initialized,true)}`;
    $('forecastHour').textContent=`F${hour} · ${manifest.products[product].label}`;updateLegend();notice('');
    const next=manifest.frames[(state.index+1)%manifest.frames.length], preload=new Image();preload.src=assetPath(`${product}-${String(next.hour).padStart(3,'0')}.png`,manifest);
  }catch(error){if(requestId===state.renderId)notice('This forecast frame could not load. Try Refresh.');console.error(error);throw error;}
  finally{if(requestId===state.renderId)state.busy=false;}
}
async function move(delta){
  if(!state.manifest)return;
  state.index=(state.index+delta+state.manifest.frames.length)%state.manifest.frames.length;
  try{await showFrame();}catch{stopPlayback();}
}
async function animate(){await move(1);if(state.playing)state.timer=setTimeout(animate,1100);}
async function pointForecast(latlng){
  const shown=state.displayed;if(!shown)return;
  const {manifest,product,frame}=shown,{width,height,extent3857}=manifest.grid;
  const p=L.CRS.EPSG3857.project(latlng),[xmin,ymin,xmax,ymax]=extent3857;
  const col=Math.floor((p.x-xmin)/(xmax-xmin)*width), row=Math.floor((ymax-p.y)/(ymax-ymin)*height);
  if(col<0||col>=width||row<0||row>=height)return;
  try{
    const key=`${manifest.cycle}-${frame.hour}`;let grid=state.grids.get(key);
    if(!grid){grid=await readJSON(assetPath(`grid-${String(frame.hour).padStart(3,'0')}.json`,manifest));state.grids.set(key,grid);if(state.grids.size>6)state.grids.delete(state.grids.keys().next().value);}
    if(state.displayed!==shown)return;
    const value=grid[product][row*width+col],spec=manifest.products[product];
    L.popup().setLatLng(latlng).setContent(`<strong>${escapeHTML(spec.label)}</strong><div class="point-value">${Number(value).toFixed(product==='temp'?1:2)} ${escapeHTML(spec.unit)}</div><p>${escapeHTML(formatTime(frame.valid))}</p><p class="forecast-popup-note">${escapeHTML(spec.description)}</p><p class="forecast-popup-note">Nearest approximately 3 km model cell. Initialized ${escapeHTML(formatTime(manifest.initialized))}.</p>`).openOn(map);
  }catch(error){notice('Point values could not load. The forecast image is still available.');console.error(error);}
}
async function saveMap(){
  if(!state.displayed||state.busy)return;
  stopPlayback();const shown=state.displayed;$('download').disabled=true;
  try{
    // All map layers use same-origin or CORS-enabled images. Recreate the
    // visible topo tiles, forecast image, and county canvas in pane order.
    const box=$('map').getBoundingClientRect(),ratio=2;
    const canvas=document.createElement('canvas');canvas.width=Math.round(box.width*ratio);canvas.height=Math.round(box.height*ratio)+172;
    const ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle='#173f40';ctx.font='bold 23px Arial';ctx.fillText('LA PLATA COUNTY · '+shown.manifest.products[shown.product].label,20,33);
    ctx.font='14px Arial';ctx.fillText(`RRFS 3 km | Init ${formatTime(shown.manifest.initialized)} | Valid ${formatTime(shown.frame.valid)}`,20,60);
    ctx.save();ctx.beginPath();ctx.rect(0,82,canvas.width,box.height*ratio);ctx.clip();ctx.fillStyle='#e4e9dd';ctx.fillRect(0,82,canvas.width,box.height*ratio);
    for(const paneName of ['tilePane','forecast','outline']){
      const pane=map.getPane(paneName);
      for(const el of pane.querySelectorAll('img,canvas')){
        if(el.tagName==='IMG'&&(!el.complete||!el.naturalWidth))continue;
        const r=el.getBoundingClientRect();if(!r.width||!r.height)continue;
        ctx.globalAlpha=Number(getComputedStyle(el).opacity)||1;
        ctx.drawImage(el,(r.left-box.left)*ratio,82+(r.top-box.top)*ratio,r.width*ratio,r.height*ratio);
      }
    }
    ctx.restore();ctx.globalAlpha=1;
    const y=82+box.height*ratio,spec=shown.manifest.products[shown.product], binWidth=Math.min(55,(canvas.width-40)/spec.colors.length);
    spec.colors.forEach((color,i)=>{ctx.fillStyle=color;ctx.fillRect(20+i*binWidth,y+9,binWidth,12);ctx.fillStyle='#173f40';ctx.font='12px Arial';ctx.fillText(String(spec.levels[i]),20+i*binWidth,y+36);});
    ctx.font='13px Arial';ctx.fillText(spec.unit+' · '+(shown.product==='temp'?'2 m temperature':['qpf3','rain3'].includes(shown.product)?'Previous 3 hours':'Since model initialization'),20,y+57);
    ctx.font='11px Arial';ctx.fillText('NOAA public model guidance, not a warning. Basemap: Esri, USGS and contributors. County boundary: La Plata County GIS.',20,y+77);
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw new Error('PNG export failed');
    const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=`LPC_RRFS_${shown.manifest.cycle}_${shown.product}_f${String(shown.frame.hour).padStart(3,'0')}.png`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000);
  }catch(error){notice('Map export failed. You can still capture the displayed map.');console.error(error);}
  finally{$('download').disabled=false;}
}
async function startMap(){
  if(typeof L==='undefined'){notice('Map library could not load. Check your connection and reload.');return;}
  map=L.map('map',{preferCanvas:true,scrollWheelZoom:false,minZoom:7,maxZoom:15,zoomSnap:0.25,zoomControl:true}).fitBounds(countyBounds,{padding:[15,15]});
  map.createPane('forecast');map.getPane('forecast').style.zIndex=350;map.getPane('forecast').style.pointerEvents='none';
  map.createPane('outline');map.getPane('outline').style.zIndex=420;map.getPane('outline').style.pointerEvents='none';
  topo=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',{crossOrigin:'anonymous',attribution:'Tiles © Esri — Esri, USGS, NOAA and contributors',maxZoom:17}).addTo(map);
  gray=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',{crossOrigin:'anonymous',attribution:'Tiles © Esri and contributors',maxZoom:16});
  L.control.scale({imperial:true,metric:false,position:'bottomright'}).addTo(map);
  try{const geo=await readJSON('assets/county.geojson');boundary=L.geoJSON(geo,{pane:'outline',interactive:false,style:{color:'#173f40',weight:2.5,opacity:1,fill:false,dashArray:'7 4'}}).addTo(map);}
  catch(error){boundaryError='County outline could not load. Try reloading the page.';notice('');console.error(error);}
  $('countyOutline').onchange=()=>{if(boundary)$('countyOutline').checked?boundary.addTo(map):boundary.remove();};
  $('terrain').onchange=()=>{if($('terrain').checked){gray.remove();topo.addTo(map);}else{topo.remove();gray.addTo(map);}};
  $('home').onclick=()=>map.fitBounds(countyBounds,{padding:[15,15]});
  $('region').onclick=()=>map.fitBounds([[36.70,-108.65],[38.30,-106.80]],{padding:[10,10]});
  map.on('click',event=>pointForecast(event.latlng));
  new ResizeObserver(()=>map.invalidateSize()).observe($('map'));
  await loadForecast();
  setInterval(()=>{if(!document.hidden&&!state.playing)loadForecast();},300000);setInterval(refreshAge,60000);
}

document.querySelectorAll('[data-product]').forEach(el=>el.addEventListener('click',()=>{
  stopPlayback();state.product=el.dataset.product;
  document.querySelectorAll('[data-product]').forEach(b=>{b.classList.toggle('active',b===el);b.setAttribute('aria-pressed',String(b===el));});showFrame().catch(()=>{});
}));
$('opacity').oninput=()=>{$('opacityValue').textContent=$('opacity').value+'%';if(forecastLayer)forecastLayer.setOpacity(Number($('opacity').value)/100);};
$('hour').oninput=()=>{stopPlayback();state.index=Number($('hour').value);showFrame().catch(()=>{});};
$('previous').onclick=()=>{stopPlayback();move(-1);};$('next').onclick=()=>{stopPlayback();move(1);};
$('play').onclick=()=>{if(state.playing){stopPlayback();return;}state.playing=true;$('play').textContent='Ⅱ';$('play').setAttribute('aria-label','Pause forecast animation');state.timer=setTimeout(animate,0);};
$('refresh').onclick=()=>{stopPlayback();loadForecast();};$('download').onclick=saveMap;
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopPlayback();});
startMap().catch(error=>{notice('Map initialization failed. Please reload.');console.error(error);});
