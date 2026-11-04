'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
let settings, options, token, dirty = false, busy = false, analysis = null, resultFilter = 'all';
let searchResults = [];
let loaded = false;

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type':'application/json','X-Monitor-Token':token}, body:JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败，请重试');
  return data;
}
function notice(message, error = false) {
  $('notice').textContent = message;
  $('notice').className = 'notice' + (error ? ' error' : '');
  $('notice').hidden = false;
}
function changed() {
  dirty = true;
  $('save-state').textContent = '有未保存的修改';
  renderCounts();
}
function renderCounts() {
  const charts = settings.chart_list.filter(c => c.enabled).length;
  const companies = settings.companies.filter(c => c.enabled).length;
  $('chart-count').textContent = charts;
  $('company-count').textContent = companies;
  $('selected-count').textContent = `· ${settings.chart_list.length} 个，${charts} 个启用`;
  $('watch-count').textContent = `· ${settings.companies.length} 个账号`;
}
function showTab(name) {
  document.querySelectorAll('.panel').forEach(p => p.hidden = p.id !== name);
  document.querySelectorAll('[data-tab]').forEach(button => {
    button.classList.toggle('active',button.dataset.tab === name);
    button.setAttribute('aria-selected',String(button.dataset.tab === name));
  });
}
function choices(id, values, selected) {
  $(id).innerHTML = Object.entries(values).map(([key,name]) =>
    `<label><input type="checkbox" value="${esc(key)}" ${selected.includes(key) ? 'checked' : ''}>${esc(name)}</label>`).join('');
}
function checked(id) { return [...$(id).querySelectorAll('input:checked')].map(e => e.value); }
function codes(value) {
  const values = [...new Set(value.toLowerCase().split(/[,，\s]+/).filter(Boolean))];
  if (!values.length || values.some(v => !/^[a-z]{2}$/.test(v))) throw new Error('国家请填写两位代码，多个用逗号分隔，例如 us, jp');
  return values;
}
function countryName(code) { return `${(options.countries[code] || code.toUpperCase())} · ${code.toUpperCase()}`; }
function scopeName(scope) {
  return `${options.platforms[scope.platform]?.name_zh || scope.platform} · ${countryName(scope.country)} · ${options.genres[scope.genre]?.name_zh || scope.genre} · ${options.charts[scope.chart_type]?.name_zh || scope.chart_type}`;
}
function timeLabel(value) {
  if (!value) return '尚未运行';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
}
function safeStoreURL(value) {
  try {
    const u = new URL(value);
    return u.protocol === 'https:' && ['apps.apple.com','itunes.apple.com','play.google.com'].includes(u.hostname) ? u.href : '';
  } catch {return '';}
}
function appURL(app) {
  let url = app.url;
  if (!url) {try {url = JSON.parse(app.extra_json || '{}').url;} catch {}}
  return safeStoreURL(url);
}
function appName(app) {
  const url = appURL(app);
  return url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(app.app_name)} ↗</a>` : esc(app.app_name);
}
function renderScopes() {
  renderCounts();
  if (!settings.chart_list.length) {
    $('scope-list').innerHTML = '<div class="status-line"><p>还没有选择版块。在上方勾选组合并添加。</p></div>';
    return;
  }
  $('scope-list').innerHTML = `<table><thead><tr><th>启用</th><th>商店</th><th>国家 / 地区</th><th>榜单</th><th>游戏品类</th><th></th></tr></thead><tbody>${settings.chart_list.map((s,i) => `<tr><td><input type="checkbox" data-scope-toggle="${i}" aria-label="启用 ${esc(scopeName(s))}" ${s.enabled ? 'checked' : ''}></td><td>${esc(options.platforms[s.platform]?.name_zh || s.platform)}</td><td>${esc(countryName(s.country))}</td><td>${esc(options.charts[s.chart_type]?.name_zh || s.chart_type)}</td><td><span class="badge">${esc(options.genres[s.genre]?.name_zh || s.genre)}</span></td><td><button class="text-button danger" data-scope-remove="${i}" aria-label="移除 ${esc(scopeName(s))}">移除</button></td></tr>`).join('')}</tbody></table>`;
}
function renderCompanies() {
  renderCounts();
  $('watch-list').innerHTML = settings.companies.map((c,i) => `<div class="card watch"><input type="checkbox" data-company-toggle="${i}" ${c.enabled ? 'checked' : ''} aria-label="启用 ${esc(c.name)}"><div><input class="company-name" data-company-name="${i}" value="${esc(c.name)}" aria-label="公司关注名称" maxlength="200"><small>${esc(options.platforms[c.platform].name_zh)} · ID ${esc(c.developer_id)}</small></div><label>关注国家 / 地区<input data-company-countries="${i}" value="${esc(c.countries.join(', '))}" placeholder="us, jp" aria-label="${esc(c.name)} 的关注地区"></label><button class="text-button danger" data-company-remove="${i}">取消关注</button></div>`).join('') || '<div class="empty"><div class="symbol">◎</div><h3>建立你的公司观察名单</h3><p>搜索公司或旗下游戏，确认开发者账号后添加关注。</p></div>';
}
function addCompany(platform, id, name, countries) {
  const existing = settings.companies.find(c => c.platform === platform && c.developer_id === id);
  if (existing) {
    existing.countries = [...new Set([...existing.countries,...countries])];
    existing.enabled = true;
    notice('已在关注名单中，为你合并了地区选择。');
  } else {
    settings.companies.push({id:crypto.randomUUID(),platform,developer_id:id,name,countries,enabled:true});
    notice(`已添加 ${name}，保存后生效。`);
  }
  changed(); renderCompanies();
}
function setupForm() {
  choices('platform-options',Object.fromEntries(Object.entries(options.platforms).map(([k,v]) => [k,v.name_zh])),['ios','gp']);
  choices('country-options',Object.fromEntries(Object.entries(options.countries).map(([k,v]) => [k,`${v} ${k.toUpperCase()}`])),['us']);
  choices('chart-options',Object.fromEntries(Object.entries(options.charts).map(([k,v]) => [k,v.name_zh])),['free']);
  choices('genre-options',Object.fromEntries(Object.entries(options.genres).map(([k,v]) => [k,v.name_zh])),['puzzle']);
  $('search-country').innerHTML = Object.entries(options.countries).map(([k,v]) => `<option value="${k}">${esc(v)} ${k.toUpperCase()}</option>`).join('');
  $('ranking-enabled').checked = settings.ranking_enabled;
  $('company-enabled').checked = settings.company_enabled;
  $('threshold').value = settings.rank_surge_threshold;
  $('window').value = settings.comparison_hours;
  if (![50,100,200].includes(settings.top_n)) $('top-n').add(new Option(`Top ${settings.top_n}`,settings.top_n));
  $('top-n').value = settings.top_n;
  $('new-days').value = settings.new_entry_days;
  for (const [id,key] of Object.entries({'ranking-enabled':'ranking_enabled','company-enabled':'company_enabled','threshold':'rank_surge_threshold','window':'comparison_hours','top-n':'top_n','new-days':'new_entry_days'})) {
    $(id).addEventListener($(id).type === 'number' ? 'input' : 'change',() => {
      settings[key] = $(id).type === 'checkbox' ? $(id).checked : Number($(id).value); changed();
    });
  }
  renderScopes(); renderCompanies();
}
async function save() {
  const result = await api('/api/settings',settings);
  settings = result.settings;
  dirty = false;
  $('save-state').textContent = '配置已保存';
  renderScopes(); renderCompanies();
  notice('本地设置已保存。每天推送的范围请点击“同步每天推送”更新。');
}
function emptyFindings(title,description) {
  return `<div class="empty"><div class="symbol">◎</div><h3>${esc(title)}</h3><p>${esc(description)}</p></div>`;
}
function renderFindings() {
  if (!analysis) {
    $('findings').innerHTML = emptyFindings('你的第一份监测，准备就绪','先在“榜单版块”和“关注公司”中选择范围，保存后点击“立即监测”。第一次会建立基线。');
    return;
  }
  const charts = Object.values(analysis.charts);
  const companies = analysis.companies || [];
  const surges = charts.reduce((n,c) => n + (c.changes.surges || []).length,0);
  const events = companies.flatMap(c => c.events);
  const snapshots = companies.flatMap(c => c.snapshots);
  $('metric-surges').textContent = surges;
  $('metric-new').textContent = events.length;
  $('metric-scopes').textContent = charts.filter(c => c.status === 'ok').length + snapshots.filter(s => ['ok','partial'].includes(s.status)).length;
  $('metric-time').textContent = timeLabel(analysis.crawl_time);
  const errors = charts.filter(c => c.status === 'error').length + snapshots.filter(c => c.status === 'error').length;
  $('result-description').textContent = errors ? `有 ${errors} 个来源采集失败，请查看下方状态。成功的来源仍可查看结果。` : '同一游戏在不同榜单的爬升分别记录；公司发现按开发者账号和游戏去重。';
  let html = '';
  if (['all','surges'].includes(resultFilter)) {
    for (const c of charts.filter(c => c.changes.surges?.length)) {
      html += `<article class="card finding-card"><div class="finding-head"><div><h3>${esc(scopeName(c.scope))}</h3><p>对比 ${esc(timeLabel(c.previous_time))} · 实际 ${c.elapsed_hours} 小时</p></div><span class="badge teal">上升 ≥ ${c.threshold} 名</span></div><div class="table-wrap"><table><thead><tr><th>游戏</th><th>公司</th><th>排名变化</th><th>爬升</th></tr></thead><tbody>${c.changes.surges.map(a => `<tr><td><strong>${appName(a)}</strong><small>${esc(a.app_id)}</small></td><td>${esc(a.developer)}</td><td>#${a.prev_rank} → #${a.rank}</td><td class="surge">↑ ${a.rank_change}</td></tr>`).join('')}</tbody></table></div></article>`;
    }
    if (resultFilter === 'surges' && !surges) html += emptyFindings('本轮没有达到阈值的爬升','若刚开始监测，请等待积累符合对比窗口的历史快照。采集状态中可以查看每个版块的情况。');
  }
  if (['all','companies'].includes(resultFilter)) {
    html += '<div class="release-grid">' + companies.flatMap(c => c.events.map(e => {
      const recent = e.kind === 'new_release';
      const url = appURL(e);
      return `<article class="card"><span class="badge ${recent ? 'teal' : 'amber'}">${recent ? '近期发布' : '首次发现 · 不确定为新游'}</span><h3>${esc(e.app_name)}</h3><p>${esc(c.company.name)} · ${esc(options.platforms[c.company.platform].name_zh)} · ${esc(e.country.toUpperCase())}</p><p>商店首发：${esc(e.release_date || '未知')}</p><p>首次监测：${esc(timeLabel(e.first_seen))}</p>${url ? `<a class="text-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">前往商店查看 ↗</a>` : ''}</article>`;
    })).join('') + '</div>';
    if (resultFilter === 'companies' && !events.length) html += emptyFindings('本轮没有公司新增发现','首次关注会记录已有产品。后续从开发者目录发现的新游戏会出现在这里。');
  }
  if (resultFilter === 'all' && !events.length && !surges) {
    html += errors && !charts.some(c => c.status === 'ok') && !snapshots.some(s => s.status !== 'error') ? emptyFindings('本轮未取得可分析的数据','请查看下方来源错误，修复后重新监测；本轮不判断新增或排名变化。') : emptyFindings('本轮暂无新增信号','已采集的产品保留在历史中。首次快照用于建立基线，不会把已有游戏全部当作新游戏。');
  }
  if (['all','status'].includes(resultFilter)) {
    html += '<article class="card finding-card"><div class="finding-head"><h3>采集状态与历史基线</h3><span class="badge">'+esc(timeLabel(analysis.crawl_time))+'</span></div>';
    for (const c of charts) {
      let label = '已采集', desc = `取得 ${c.current.length} 款 · `;
      if (c.status === 'error') {label = '采集失败'; desc = c.message || '来源无数据';}
      else if (c.status === 'not_run') {label = '待采集';desc = '配置已添加，本轮没有该版块快照';}
      else desc += c.previous_time ? `对比 ${timeLabel(c.previous_time)}，间隔 ${c.elapsed_hours} 小时` : '缺少符合窗口的历史；本轮仅记录快照';
      html += `<div class="status-line"><span class="badge ${c.status === 'error' ? 'red' : ''}">${label}</span><div><b>${esc(scopeName(c.scope))}</b><p>${esc(desc)}</p>${c.current.length ? `<details><summary>查看本轮榜单（${c.current.length} 款）</summary><table><tbody>${c.current.map(a => `<tr><td>#${a.rank}</td><td>${appName(a)}</td><td>${esc(a.developer)}</td></tr>`).join('')}</tbody></table></details>` : ''}</div></div>`;
    }
    for (const c of companies) {
      for (const country of c.company.countries) {
        const snap = c.snapshots.find(s => s.country === country);
        const label = !snap ? '待采集' : snap.status === 'error' ? '采集失败' : snap.baseline ? '首次基线' : snap.status === 'partial' ? '目录不完整' : '已采集';
        const desc = !snap ? '本轮未取得这个地区的目录' : snap.status === 'error' ? snap.message : `取得 ${snap.count} 款游戏` + (snap.message ? ' · '+snap.message : '');
        html += `<div class="status-line"><span class="badge ${snap?.status === 'error' ? 'red' : snap?.status === 'partial' ? 'amber' : ''}">${label}</span><div><b>${esc(c.company.name)} · ${esc(options.platforms[c.company.platform].name_zh)} · ${esc(country.toUpperCase())}</b><p>${esc(desc)}</p></div></div>`;
      }
    }
    if (!charts.length && !companies.length) html += '<div class="status-line"><p>当前没有启用的版块或公司。请在设置中选择。</p></div>';
    html += '</article>';
  }
  $('findings').innerHTML = html;
}
async function refresh() {
  const state = await api('/api/state');
  const updated = !loaded || JSON.stringify(state.analysis) !== JSON.stringify(analysis);
  loaded = true;
  analysis = state.analysis;
  const wasBusy = busy;
  busy = state.job.running;
  if (wasBusy && !busy && !state.job.error) notice(state.job.result?.errors?.length ? '监测完成，部分来源失败。可在采集状态中查看原因。' : '本轮监测已完成，结果已更新。');
  $('run').disabled = busy;
  $('save').disabled = busy;
  $('run').textContent = busy ? '正在采集…' : '▶ 立即监测';
  const runStatus = analysis?.run?.status;
  const statusLabel = {ok:'监测完成',partial:'部分来源失败，详见采集状态',error:'本轮采集失败，详见采集状态',running:'有监测正在运行',interrupted:'上次监测中断，请重新运行'}[runStatus];
  $('job-state').textContent = busy ? '采集中，页面会自动更新' : state.job.error ? '运行未完成' : statusLabel || (analysis ? '已载入最近一轮结果' : '选择监测范围后即可开始');
  if (state.job.error) notice(state.job.error,true);
  if (updated) renderFindings();
}

$('add-scopes').addEventListener('click',() => {
  try {
    const platforms = checked('platform-options'), charts = checked('chart-options'), genres = checked('genre-options');
    const countries = [...new Set([...checked('country-options'),...($('custom-country').value.trim() ? codes($('custom-country').value) : [])])];
    if (![platforms,charts,genres,countries].every(a => a.length)) throw new Error('请至少选择一个商店、国家、榜单和品类');
    const additions = [], existing = new Set(settings.chart_list.map(s => [s.platform,s.country,s.chart_type,s.genre].join('|')));
    let skipped = 0;
    for (const platform of platforms) for (const country of countries) for (const chart_type of charts) for (const genre of genres) {
      if (!options.genres[genre][platform === 'ios' ? 'ios_genre_id' : 'gp_category']) {skipped++;continue;}
      const key = [platform,country,chart_type,genre].join('|');
      if (!existing.has(key)) {additions.push({platform,country,chart_type,genre,enabled:true});existing.add(key);}
    }
    if (settings.chart_list.length+additions.length > 100) throw new Error('最多保存 100 个版块，请减少所选组合');
    settings.chart_list.push(...additions); changed(); renderScopes();
    notice(`已添加 ${additions.length} 个版块。${skipped ? `跳过 ${skipped} 个商店不支持的品类组合。` : ''}保存后生效。`);
  } catch(e) {notice(e.message,true);}
});
$('clear-scopes').addEventListener('click',() => {settings.chart_list = [];changed();renderScopes();});
$('scope-list').addEventListener('change',e => {
  if (e.target.dataset.scopeToggle !== undefined) {settings.chart_list[Number(e.target.dataset.scopeToggle)].enabled = e.target.checked;changed();}
});
$('scope-list').addEventListener('click',e => {
  if (e.target.dataset.scopeRemove !== undefined) {settings.chart_list.splice(Number(e.target.dataset.scopeRemove),1);changed();renderScopes();}
});
$('watch-list').addEventListener('change',e => {
  const d = e.target.dataset;
  if (d.companyToggle !== undefined) settings.companies[Number(d.companyToggle)].enabled = e.target.checked;
  if (d.companyName !== undefined) settings.companies[Number(d.companyName)].name = e.target.value.trim();
  if (d.companyCountries !== undefined) {
    try {settings.companies[Number(d.companyCountries)].countries = codes(e.target.value);}
    catch(error) {notice(error.message,true);e.target.value = settings.companies[Number(d.companyCountries)].countries.join(', ');return;}
  }
  changed();
});
$('watch-list').addEventListener('click',e => {
  if (e.target.dataset.companyRemove !== undefined) {settings.companies.splice(Number(e.target.dataset.companyRemove),1);changed();renderCompanies();}
});
$('search-form').addEventListener('submit',async e => {
  e.preventDefault(); $('search-button').disabled = true; $('search-button').textContent = '搜索中…';
  $('search-results').textContent = '正在查询商店，Google Play 首次搜索可能需要几十秒…';
  try {
    const data = await api('/api/search',{platform:$('search-platform').value,country:$('search-country').value,term:$('search-term').value});
    searchResults = data.results;
    $('search-results').innerHTML = searchResults.map((r,i) => `<div class="search-result"><div><strong>${esc(r.name)}</strong> <a class="text-link" href="${esc(safeStoreURL(r.url))}" target="_blank" rel="noopener noreferrer">核对商店账号 ↗</a><small>ID ${esc(r.developer_id)} · ${esc(r.examples.join(' / '))}</small></div><button data-follow="${i}" class="secondary">＋ 关注</button></div>`).join('') || '<p class="hint">没有匹配的候选账号。可换成旗下游戏名搜索，或手动填写开发者 ID。</p>';
  } catch(error) {$('search-results').textContent = error.message;notice(error.message,true);}
  finally {$('search-button').disabled = false;$('search-button').textContent = '搜索公司';}
});
$('search-results').addEventListener('click',e => {
  if (e.target.dataset.follow !== undefined) {const r = searchResults[Number(e.target.dataset.follow)];addCompany(r.platform,r.developer_id,r.name,[r.country]);}
});
$('manual-form').addEventListener('submit',e => {
  e.preventDefault();
  try {addCompany($('manual-platform').value,$('manual-id').value.trim(),$('manual-name').value.trim(),codes($('manual-countries').value));}
  catch(error) {notice(error.message,true);}
});
$('save').addEventListener('click',async () => {try {await save();await refresh();} catch(e) {notice(e.message,true);}});
$('cloud-sync').addEventListener('click',async () => {
  $('cloud-sync').disabled = true;
  try {
    const result = await api('/api/cloud-sync',settings);
    settings = result.settings; dirty = false;
    $('save-state').textContent = '本地与云端配置已保存';
    renderScopes(); renderCompanies();
    notice('已同步到 '+result.repository+'，下一次每天推送将使用当前选择。');
  } catch(e) {notice(e.message,true);}
  finally {$('cloud-sync').disabled = false;}
});
$('run').addEventListener('click',async () => {
  $('run').disabled = true;
  try {
    if (dirty) await save();
    await api('/api/run',{}); showTab('results');
    notice('监测已开始，正在获取所选榜单和公司目录。结果会自动更新。');
    await refresh();
  } catch(e) {notice(e.message,true);$('run').disabled = false;}
});
document.querySelectorAll('[data-tab]').forEach(b => b.addEventListener('click',() => showTab(b.dataset.tab)));
document.querySelectorAll('[data-result]').forEach(b => b.addEventListener('click',() => {
  resultFilter = b.dataset.result;
  document.querySelectorAll('[data-result]').forEach(x => x.classList.toggle('active',x === b));renderFindings();
}));
window.addEventListener('beforeunload',e => {if (dirty) {e.preventDefault();e.returnValue = '';}});
async function poll() {
  try {await refresh();} catch(e) {notice('无法连接本地服务：'+e.message,true);}
  setTimeout(poll,busy ? 3000 : 12000);
}
(async () => {
  try {
    const data = await api('/api/bootstrap');settings = data.settings;options = data.options;token = data.token;
    $('cloud-destination').textContent = data.cloud_repository ? '同步到 '+data.cloud_repository+' · 每天北京时间 9:00 运行' : '完成 GitHub 云端配置后可同步每天推送范围';
    $('cloud-sync').disabled = !data.cloud_repository;
    setupForm();await poll();
  }
  catch(e) {notice('页面初始化失败：'+e.message,true);}
})();
