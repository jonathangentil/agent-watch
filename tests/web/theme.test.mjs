import test from 'node:test';
import assert from 'node:assert/strict';
import {loadTheme,saveTheme,themeId} from '../../src/alethe_tui/web/theme.mjs';
test('three supported choices, safe fallback and persistent preference',()=>{
 const values=new Map(),store={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)};
 assert.equal(loadTheme(store),'current');
 for(const value of ['current','aura','light']){saveTheme(value,store);assert.equal(loadTheme(store),value)}
 assert.equal(themeId('invalid'),'current');
 assert.equal(loadTheme({getItem(){throw Error('blocked')}}),'current');
 assert.doesNotThrow(()=>saveTheme('aura',{setItem(){throw Error('blocked')}}));
});
