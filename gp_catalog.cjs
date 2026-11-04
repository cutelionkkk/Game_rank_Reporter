// Developer landing pages may feature only ten games. The named account page
// contains the full catalog, so merge both before deciding what is newly seen.
function decodeDeveloperId(id) {
  return decodeURIComponent(String(id).replace(/\+/g, ' '));
}

async function developerApps(gplay, opts, devId) {
  let initial;
  try {
    initial = await gplay.developer({...opts, devId, fullDetail: false});
  } catch (error) {
    if (error.status === 404) throw new Error('Developer unavailable (404)');
    throw error;
  }
  if (!initial.length) throw new Error('No products returned; check developer ID and country');
  let apps = initial;
  let warning = '';
  const first = await gplay.app({...opts, appId: initial[0].appId});
  if (/^\d+$/.test(devId)) {
    if (!first.developer) throw new Error('Missing developer name');
    try {
      const full = await gplay.developer({...opts, devId: first.developer, fullDetail: false});
      if (!full.length) throw new Error('Empty named catalog');
      apps = [...new Map([...initial, ...full].map(a => [a.appId, a])).values()];
    } catch (error) {
      warning = 'Google Play 完整开发者目录暂不可用，仅取得展示页产品';
    }
  }
  return {apps, first, warning};
}
module.exports = {decodeDeveloperId, developerApps};
