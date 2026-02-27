#!/usr/bin/env node
/**
 * Google Play Top Charts Scraper
 * Uses Node.js google-play-scraper which has working batchexecute API
 *
 * Usage: node gp_scraper.js <chart_type> [country] [num] [category]
 * chart_type: free | paid | grossing
 * category: GAME (default) | GAME_CASUAL | GAME_PUZZLE | etc.
 * Output: JSON array to stdout
 */

const gplay = require('google-play-scraper').default;

const chartMap = {
  'free': gplay.collection.TOP_FREE,
  'paid': gplay.collection.TOP_PAID,
  'grossing': gplay.collection.GROSSING,
};

async function main() {
  const chartType = process.argv[2] || 'free';
  const country = process.argv[3] || 'us';
  const num = parseInt(process.argv[4]) || 100;
  const categoryArg = process.argv[5] || 'GAME';

  const collection = chartMap[chartType];
  if (!collection) {
    process.stderr.write(`Unknown chart type: ${chartType}. Use: free, paid, grossing\n`);
    process.exit(1);
  }

  // Resolve category
  const category = gplay.category[categoryArg];
  if (!category) {
    process.stderr.write(`Unknown category: ${categoryArg}\n`);
    process.stderr.write(`Available: ${Object.keys(gplay.category).filter(k => k.startsWith('GAME')).join(', ')}\n`);
    process.exit(1);
  }

  try {
    const apps = await gplay.list({
      collection: collection,
      category: category,
      num: num,
      country: country,
      lang: 'en',
      fullDetail: false,
    });

    const results = apps.map((app, index) => ({
      rank: index + 1,
      app_id: app.appId,
      app_name: app.title,
      developer: app.developer || '',
      category: app.genre || app.genreId || '',
      rating: app.scoreText ? parseFloat(app.scoreText) : (app.score || null),
      rating_count: app.ratings || null,
      price: app.priceText === 'Free' ? 0 : (app.price || 0),
      icon_url: app.icon || '',
      extra: {
        installs: app.installs || '',
        free: app.free !== false,
        genreId: app.genreId || '',
        url: app.url || '',
        description_short: (app.summary || '').slice(0, 200),
      },
    }));

    // Output ONLY JSON to stdout, everything else to stderr
    process.stdout.write(JSON.stringify(results));
  } catch (err) {
    process.stderr.write(`Error scraping ${chartType} (${categoryArg}): ${err.message}\n`);
    process.exit(1);
  }
}

main();
