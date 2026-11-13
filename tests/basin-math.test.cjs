const {test}=require('node:test');
const assert=require('node:assert/strict');
const {mean}=require('../basin-math.js');
test('partial cells contribute in proportion to covered area',()=>{assert.equal(mean([1,3],[[0,.75],[1,.25]]),1.5);});
test('a uniform field remains uniform for any basin',()=>{assert.equal(mean([2,2,2],[[0,.02],[1,.11],[2,.87]]),2);});
test('an incomplete or invalid grid never becomes a zero-rain basin',()=>{assert.equal(mean([1],[[9,1]]),null);assert.equal(mean([NaN],[[0,1]]),null);assert.equal(mean([],[]),null);});
