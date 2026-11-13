/* Area fractions are computed from polygon intersections in equal-area EPSG:5070. */
(function(root){
  'use strict';
  function mean(values,samples){
    if(!Array.isArray(values)||!samples.length)return null;
    let sum=0,weight=0;
    for(const [i,w] of samples){if(!Number.isInteger(i)||i<0||i>=values.length||!Number.isFinite(values[i])||!Number.isFinite(w)||w<0)return null;sum+=values[i]*w;weight+=w;}
    return weight>0?sum/weight:null;
  }
  function cellValue(values,grid,lon,lat){
    if(!Array.isArray(values)||!Number.isFinite(lon)||!Number.isFinite(lat)||Math.abs(lat)>=85.051129)return null;
    const {width,height,extent3857:[xmin,ymin,xmax,ymax]}=grid;
    const x=6378137*lon*Math.PI/180,y=6378137*Math.log(Math.tan(Math.PI/4+lat*Math.PI/360));
    const col=Math.floor((x-xmin)/(xmax-xmin)*width),row=Math.floor((ymax-y)/(ymax-ymin)*height);
    if(col<0||col>=width||row<0||row>=height||values.length!==width*height)return null;
    const value=values[row*width+col];return Number.isFinite(value)?value:null;
  }
  const api={mean,cellValue};if(typeof module==='object'&&module.exports)module.exports=api;else root.BasinMath=api;
})(typeof window==='object'?window:this);
