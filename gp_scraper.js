#!/usr/bin/env node
// Store adapters. JSON only on stdout; argv is passed without a shell.
const fs = require('node:fs');

async function mapLimited(items, fn) {
  const results = new Array(items.length);
  let cursor = 0;
  await Promise.all(Array.from({length: Math.min(4, items.length)}, async () => {
    while (cursor < items.length) {
      const index = cursor++;
      results[index] = await fn(items[index]);
    }
  }));
  return results;
}

async function main() {
  const {default: gplay} = await import('google-play-scraper');
  const [mode = 'free', country = 'us', count = '100', value = 'GAME'] = process.argv.slice(2);
  const num = Number(count);
  if (!/^[a-z]{2}$/.test(country) || !Number.isInteger(num) || num < 1 || num > 200) {
    throw new Error('Invalid country or limit');
  }
  const opts = {country, lang: 'en', requestOptions: {timeout: 25000}, num};
  const detail = app => gplay.app({...opts, appId: app.appId});
  let result;
  if (mode === 'search') {
    // Full details resolve actual account IDs, not the search result's display name.
    const apps = await gplay.search({...opts, term: value, fullDetail: false});
    const detailed = await mapLimited(apps, detail);
    result = detailed.filter(a => (a.genreId || '').startsWith('GAME'))
      .map(a => ({developer_id: a.developerId, name: a.developer, example: a.title}));
  } else if (mode === 'developer') {
    const known = JSON.parse(fs.readFileSync(0, 'utf8') || '{}');
    const apps = await gplay.developer({...opts, devId: value, fullDetail: false});
    if (!apps.length) throw new Error('No products returned; check developer ID and country');
    const catalog = await mapLimited(apps, async app => {
      if (Object.hasOwn(known, app.appId)) return {...known[app.appId], app_name: app.title};
      const a = await detail(app);
      if (!a.genreId || !a.appId || !a.title) throw new Error('Incomplete app details');
      return {app_id: a.appId, app_name: a.title, developer: a.developer,
        is_game: a.genreId.startsWith('GAME'), category: a.genre,
        // 'updated' is not an original release date.
        release_date: a.released || null, url: a.url, icon_url: a.icon};
    });
    result = {apps: catalog, partial: apps.length >= num,
      message: apps.length >= num ? 'Google Play 已达到 200 款抓取上限，目录可能不完整' : ''};
  } else {
    const collection = {free: gplay.collection.TOP_FREE, paid: gplay.collection.TOP_PAID,
                        grossing: gplay.collection.GROSSING}[mode];
    const category = gplay.category[value];
    if (!collection || !category || !value.startsWith('GAME')) throw new Error('Invalid game chart');
    const apps = await gplay.list({...opts, collection, category, fullDetail: false});
    result = apps.map((a, i) => ({rank: i + 1, app_id: a.appId, app_name: a.title,
      developer: a.developer || '', category: a.genre || value, rating: a.score || null,
      rating_count: a.ratings || null, price: a.price || 0, icon_url: a.icon || '',
      extra_json: JSON.stringify({url: a.url || '', genreId: a.genreId || value})}));
  }
  process.stdout.write(JSON.stringify(result));
}
main().catch(error => {process.stderr.write(error.message + '\n'); process.exitCode = 1;});
