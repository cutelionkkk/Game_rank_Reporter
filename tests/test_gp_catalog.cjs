const test = require('node:test');
const assert = require('node:assert/strict');
const {developerApps, decodeDeveloperId} = require('../gp_catalog.cjs');

test('merge the full named catalog with featured products without duplicates', async () => {
 const g = {
  developer: async ({devId}) => devId === '123' ? [{appId:'a'}, {appId:'b'}] : [{appId:'b'}, {appId:'c'}, {appId:'d'}],
  app: async () => ({appId:'a',developer:'Studio Name'})
 };
 const r = await developerApps(g,{num:200},'123');
 assert.deepEqual(r.apps.map(a=>a.appId),['a','b','c','d']);
 assert.equal(r.warning,'');
});
test('an inaccessible complete catalog is explicitly partial', async () => {
 const g = {
  developer: async ({devId}) => { if(devId!=='123') throw Error('offline'); return [{appId:'a'}]; },
  app: async () => ({appId:'a',developer:'Studio Name'})
 };
 assert.ok((await developerApps(g,{num:200},'123')).warning);
});
test('decode account URL IDs exactly once, including literal plus signs', () => {
 assert.equal(decodeDeveloperId('Studio+Name'), 'Studio Name');
 assert.equal(decodeDeveloperId('A%2BB+Games'), 'A+B Games');
 assert.equal(decodeDeveloperId('123'), '123');
});
test('account 404 is unavailable, a network failure remains a failure', async () => {
 await assert.rejects(developerApps({developer: async()=>{throw Object.assign(Error('missing'),{status:404});}}, {}, 'Old Studio'), /Developer unavailable/);
 await assert.rejects(developerApps({developer: async()=>{throw Error('timeout');}}, {}, 'Old Studio'), /timeout/);
});
