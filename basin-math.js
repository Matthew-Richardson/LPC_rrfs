/* Area fractions are computed from polygon intersections in equal-area EPSG:5070. */
(function(root){
  'use strict';
  function mean(values,samples){
    if(!Array.isArray(values)||!samples.length)return null;
    let sum=0,weight=0;
    for(const [i,w] of samples){if(!Number.isInteger(i)||i<0||i>=values.length||!Number.isFinite(values[i])||!Number.isFinite(w)||w<0)return null;sum+=values[i]*w;weight+=w;}
    return weight>0?sum/weight:null;
  }
  const api={mean};if(typeof module==='object'&&module.exports)module.exports=api;else root.BasinMath=api;
})(typeof window==='object'?window:this);
