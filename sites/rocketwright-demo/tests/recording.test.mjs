import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const root=new URL('../integrated-src/public/',import.meta.url);
const data=JSON.parse(readFileSync(new URL('demo-data.json',root),'utf8'));
test('recorded stages follow the original eight-step history',()=>{
  assert.equal(data.replay,true);assert.equal(data.snapshots.length,9);
  data.snapshots.forEach((snapshot,index)=>{
    assert.equal(snapshot.history.length,index);
    assert.equal(snapshot.active,null);
    if(index<8){assert.equal(snapshot.options.length,1);assert.equal(snapshot.options[0].id,data.snapshots[8].history[index].chosen);}
  });
  assert.equal(data.snapshots[8].confirmed,true);
});
test('all downloadable artifacts match their recorded hashes',()=>{
  assert.ok(data.assets.length>=47);
  for(const asset of data.assets){const bytes=readFileSync(new URL(asset.path,root));assert.equal(createHash('sha256').update(bytes).digest('hex'),asset.sha256,asset.path);assert.equal(bytes.length,asset.bytes);}
  for(const file of data.files){assert.ok(file.url.startsWith('/functional/assets/'));const bytes=readFileSync(new URL(file.url.slice('/functional/'.length),root));assert.equal(createHash('sha256').update(bytes).digest('hex'),file.sha256,file.name);}
  assert.equal(data.files.filter(file=>file.name.endsWith('.mp4')).length,2);
  assert.equal(data.files.filter(file=>file.kind==='manual').length,1);
});
test('reference CAD and films remain a distinct 2 L case',()=>{
  assert.equal(data.library.case_id,'pet-coke-2l-v2');
  assert.equal(data.library.geometry.diameter_mm,110);
  for(const asset of data.library.assets){assert.equal(asset.status,'available');assert.ok(asset.url.startsWith('/functional/assets/library/'));readFileSync(new URL(asset.url.slice('/functional/'.length),root));}
  assert.ok(data.references.records.length>50);
});
test('public recording contains no local absolute paths or replacement characters',()=>{
  const text=JSON.stringify(data);
  assert.ok(!/[A-Z]:[\\/]/.test(text));assert.ok(!text.includes('\ufffd'));
});
