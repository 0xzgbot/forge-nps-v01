/* Forge NPS — App shell, tabs, view rendering — FULL REMEDIATION */

const $ = (s, p = document) => p?.querySelector(s);
const $$ = (s, p = document) => p ? [...p.querySelectorAll(s)] : [];
const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
};

const TABS = ['home','characters','script','renders','memory','settings'];
const TAB_LABELS = {
  home: 'Home', characters: 'Characters', script: 'Script',
  renders: 'Renders', memory: 'Memory', settings: 'Settings'
};

let activeTab = 'home';
let activeCharId = 'elara';
let expandedShot = null;
window.SHOTS = window.SHOTS || [];

/* Cached data (populated from API) */
const APP_DATA = {
  stats: null,
  renders: [],
  insights: [],
  timeline: [],
  graph: null,
  memoryStats: null,
  config: null
};

/* Toast notification system */
window.showToast = function(message, type = 'info') {
  const existing = $('.toast-container');
  if (!existing) {
    const container = h('div', { class: 'toast-container', style: 'position:fixed;top:16px;right:16px;z-index:10000;display:flex;flex-direction:column;gap:8px;' });
    document.body.appendChild(container);
  }
  const toast = h('div', {
    class: `toast toast-${type}`,
    style: `padding:10px 16px;border-radius:6px;font-size:12px;font-family:"JetBrains Mono",monospace;animation:slideIn .2s ease;max-width:360px;box-shadow:0 4px 12px rgba(0,0,0,0.5);border:1px solid var(--border, #2A3A4F);background:var(--bg-secondary, #0D1420);color:var(--text, #E6EDF3);`
  }, message);
  const container = $('.toast-container');
  container.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; setTimeout(() => toast.remove(), 300); }, 3500);
};

/* Loading overlay */
window.showLoading = function(container, message = 'Loading...') {
  if (!container) return;
  const loader = h('div', { class: 'loading-overlay', style: 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:rgba(10,14,20,0.8);z-index:100;border-radius:4px;' },
    h('div', { class: 'loading-spinner', style: 'width:32px;height:32px;border:3px solid var(--border);border-top-color:var(--cyan);border-radius:50%;animation:spin .8s linear infinite;' }),
    h('span', { style: 'color:var(--text-secondary);margin-left:12px;font-size:12px;font-family:"JetBrains Mono",monospace;' }, message)
  );
  container.style.position = 'relative';
  container.appendChild(loader);
  return loader;
};

window.hideLoading = function(loader) {
  if (loader) loader.remove();
};

/* ---------- TAB ICONS ---------- */
const TAB_ICONS = {
  home:       `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 9l7-6 7 6v8a1 1 0 0 1-1 1h-3v-5H7v5H4a1 1 0 0 1-1-1z"/></svg>`,
  characters: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="7" cy="7" r="3"/><path d="M2 17a5 5 0 0 1 10 0"/><circle cx="14" cy="7" r="2.5"/><path d="M13 13a4 4 0 0 1 5 4"/></svg>`,
  script:     `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="3" width="12" height="14" rx="1"/><path d="M7 7h6M7 10h6M7 13h4"/></svg>`,
  renders:    `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="6" height="6" rx="1"/><rect x="11" y="3" width="6" height="6" rx="1"/><rect x="3" y="11" width="6" height="6" rx="1"/><rect x="11" y="11" width="6" height="6" rx="1"/></svg>`,
  memory:     `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M7 4a3 3 0 0 0-3 3v6a3 3 0 0 0 3 3h6a3 3 0 0 0 3-3V7a3 3 0 0 0-3-3H7z"/><path d="M10 4v12M7 8h6M7 12h6"/></svg>`,
  settings:   `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="10" cy="10" r="3"/><path d="M10 2v2m0 12v2M2 10h2m12 0h2M4.5 4.5l1.4 1.4m8.2 8.2 1.4 1.4M4.5 15.5l1.4-1.4m8.2-8.2 1.4-1.4"/></svg>`,
};

/* ---------- API HELPERS ---------- */
async function apiGet(url, fallback = null) {
  try {
    const r = await fetch(url);
    if (r.ok) return await r.json();
  } catch (e) { /* silent */ }
  return fallback;
}

async function apiPost(url, body) {
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (r.ok) return await r.json();
    const err = await r.text().catch(() => 'Unknown error');
    throw new Error(err);
  } catch (e) {
    throw e;
  }
}

/* ---------- Boot ---------- */
function boot() {
  if (typeof initSparkWidget === 'function') initSparkWidget();
  if (typeof initHermesPanel === 'function') initHermesPanel();
  window.navigate = switchTab;

  const brandMark = $('#brand-mark');
  if (brandMark && typeof logoSVG === 'function') brandMark.innerHTML = logoSVG();

  // Build sidebar rail nav
  const railNavEl = document.getElementById('railNav');
  if (railNavEl) {
    railNavEl.innerHTML = '';
    TABS.forEach(id => {
      railNavEl.appendChild(h('div', {
        class: 'rail-item',
        'data-view': id,
        onclick: () => switchTab(id)
      },
        h('span', { class: 'ico', html: TAB_ICONS[id] || '' }),
        h('span', { class: 'label' }, TAB_LABELS[id])
      ));
    });
  }

  const tabsEl = $('#tabs');
  if (tabsEl) {
    tabsEl.innerHTML = '';
    TABS.forEach(t => {
      tabsEl.append(h('button', {
        class: 'tab' + (t === activeTab ? ' active' : ''),
        'data-tab': t,
        onclick: () => switchTab(t)
      }, TAB_LABELS[t]));
    });
  }

  $$('.intensity-pill button').forEach(b => {
    b.addEventListener('click', () => setIntensity(b.dataset.intensity));
  });

  // Wire topbar buttons
  wireTopbar();

  // Connect Hermes WebSocket for live events
  connectHermesWS();

  const hash = (location.hash || '').replace(/^#\/?/, '');
  if (TABS.includes(hash)) activeTab = hash;
  else location.hash = '';
  window.addEventListener('hashchange', () => {
    const nh = (location.hash || '').replace(/^#\/?/, '');
    if (TABS.includes(nh) && nh !== activeTab) switchTab(nh, false);
  });
  switchTab(activeTab, false);
}

/* ---------- Hermes WebSocket ---------- */
function connectHermesWS() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${proto}//${location.host}/ws/hermes`;
  let ws = null;
  let reconnectDelay = 3000;

  function connect() {
    try {
      ws = new WebSocket(wsUrl);
      ws.onopen = () => {
        reconnectDelay = 3000; // reset backoff on successful connect
      };
      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);
          handleHermesEvent(data);
        } catch (e) { /* ignore parse errors */ }
      };
      ws.onclose = () => {
        // Reconnect with exponential backoff
        setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 1.5, 30000);
      };
      ws.onerror = () => { ws.close(); };
    } catch (e) { /* ignore */ }
  }

  connect();
}

function handleHermesEvent(data) {
  const type = data.type;
  const payload = data.payload || {};

  // Map event types to emoji labels
  const EVENT_LABELS = {
    'lmstudio_detected': '[SPARK \u26A1]',
    'lmstudio_empty': '[SPARK \u26A1]',
    'lmstudio_offline': '[SPARK \u26A1]',
    'render_complete': '[HERMES \ud83e\udde0]',
    'render_failed': '[HERMES \ud83e\udde0]',
    'kimi_vl_audit': '[KIMI-VL \ud83d\udc41]',
    'memory_written': '[MEM \ud83d\udcbe]',
    'spark_job_update': '[SPARK \u26A1]',
    'remediation_retry': '[HERMES \ud83e\udde0]',
    'remediation_complete': '[HERMES \ud83e\udde0]',
    'prompt_written': '[KIMI K2 \u270d]',
    'dispatch_start': '[HERMES \ud83e\udde0]',
    'dispatch_shot': '[HERMES \ud83e\udde0]',
    'dispatch_complete': '[HERMES \ud83e\udde0]',
    'memory_query': '[MEM \ud83d\udcbe]',
  };
  const label = EVENT_LABELS[type] || '[SYS]';

  // Append to event log if it exists
  if (typeof appendEventLog === 'function') {
    appendEventLog(type, payload, label);
  }

  // LM Studio detection events
  if (type === 'lmstudio_detected') {
    updateLMStudioPill('live', `LM Studio \u00B7 ${payload.model || 'model loaded'}`);
    window.showToast(`${label} LM Studio detected: ${payload.model}`, 'success');
  } else if (type === 'lmstudio_empty') {
    updateLMStudioPill('amber', 'LM Studio \u00B7 no models loaded');
  } else if (type === 'lmstudio_offline') {
    updateLMStudioPill('dim', 'LM Studio \u00B7 offline');
  }

  // Render complete events (populates filmstrip live)
  if (type === 'render_complete') {
    const retryTag = payload.retry ? ` (retry ${payload.retry})` : '';
    window.showToast(`${label} Render complete: ${payload.filename || 'image'}${retryTag}`, 'success');
    // Inject new render into filmstrip live
    if (payload.relative_files && payload.relative_files.length > 0) {
      const newRenders = payload.relative_files.map((f, i) => {
        const campaign = payload.campaign || 'default';
        return {
          id: payload.prompt_id || `R_${Date.now()}`,
          src: `/campaigns/${campaign}/${payload.filename}`,
          prompt: payload.prompt_preview || '',
          seed: Date.now(),
          score: '—',
          campaign: campaign,
        };
      });
      // Add to global renders store if it exists
      if (window._rendersCache) {
        window._rendersCache.unshift(...newRenders);
      }
      // Update filmstrip directly if on home view
      const strip = document.getElementById('recent-strip');
      if (strip) {
        const accents = ['cyan', 'magenta', 'amber', 'green'];
        const existing = strip.children.length;
        newRenders.forEach((r, i) => {
          const c = accents[(existing + i) % accents.length];
          const thumb = h('div', { class: 'thumb' });
          if (r.src) {
            thumb.append(h('img', {
              src: r.src, alt: r.prompt || '',
              style: 'width:100%;height:100%;object-fit:cover;'
            }));
          }
          const overlay = h('div', { class: 'meta-overlay' },
            h('div', { style: 'color: var(--' + c + '); letter-spacing: 0.14em;' }, String(r.id)),
            h('div', { class: 'muted' }, 'seed ' + String(r.seed || '—') + ' \u00B7 score ' + String(r.score || '—'))
          );
          thumb.append(overlay);
          strip.prepend(thumb);
        });
      }
    }
    // Also refresh renders view if active
    if (activeTab === 'renders') switchTab('renders', false);
  }

  // Kimi-VL audit events
  if (type === 'kimi_vl_audit') {
    const retryTag = payload.retry ? ` (retry ${payload.retry})` : '';
    window.showToast(`${label} Audit: ${payload.score || ''} ${payload.passed ? '\u2705' : '\u26a0\ufe0f'}${retryTag}`, payload.passed !== false ? 'success' : 'warning');
  }

  // Memory events — append new rules to the rulebook live
  if (type === 'memory_written') {
    const container = document.getElementById('rulebook-container');
    const countBadge = document.getElementById('insights-rule-count');
    let insightCount = parseInt(countBadge?.textContent || '0', 10);

    // Build a synthetic rule entry from the audit event payload
    const passed = payload.passed !== false;
    const score = payload.score != null ? Math.round(payload.score * 100) : 0;
    const concept = payload.concept || 'concept';
    const isNewRule = !passed && (payload.feedback || '').trim().length > 0;

    if (container) {
      // Only show non-trivial entries — skip "none" / passing audits without issues
      if (!isNewRule && passed && score >= 75) {
        // Don't clutter rulebook with every pass, just update count
      } else {
        const confPct = score;
        const ruleText = isNewRule ? (payload.feedback || concept) : `Audit ${passed ? 'PASS' : 'FAIL'}: ${concept}`;
        const entry = h('div', { class: 'rule-entry' },
          h('div', { class: 'rule-header' },
            h('span', { class: 'rule-label' }, ruleText),
            passed
              ? h('span', { class: 'rule-kernel rule-pass-tag' }, '✅ PASS')
              : h('span', { class: 'rule-kernel rule-fail-tag' }, '⚠️ FAIL')
          ),
          h('div', { class: 'rule-body' },
            h('div', { class: 'rule-confidence-row' },
              h('div', { class: 'rule-conf-bar' }, h('div', { class: 'fill', style: `width: ${confPct}%;` })),
              h('span', { class: 'rule-conf-text' }, confPct + '%')
            ),
            h('div', { class: 'rule-meta-row' },
              passed ? h('span', { class: 'rule-age' }, 'just now') : null,
              !passed && payload.feedback ? h('span', { class: 'rule-error-tag' }, (payload.feedback || '').slice(0, 60)) : null
            )
          )
        );
        container.append(entry);
        insightCount++;
      }
    }

    if (countBadge) countBadge.textContent = insightCount + ' RULES';
    window.showToast(`${label} ${payload.concept || 'concept'} saved`, 'info');
  }

  // Spark job events
  if (type === 'spark_job_update') {
    // Update queue display
    if (payload.status === 'complete') {
      window.showToast(`${label} Job ${payload.job_id || ''} complete`, 'success');
    }
  }

  // Remediation retry events
  if (type === 'remediation_retry') {
    window.showToast(`${label} RETRY ${payload.retry_number}/${payload.max_retries}: ${payload.rewrite_reason || 'Rewriting prompt'}...`, 'warning');
  }

  // Remediation complete events
  if (type === 'remediation_complete') {
    const status = payload.resolved ? 'RESOLVED' : 'UNRESOLVED';
    window.showToast(`${label} Remediation ${status} (score: ${payload.final_score}, retries: ${payload.retries_used})`, payload.resolved ? 'success' : 'error');
  }
}

// Global event log function - appends events to the Live Event Log
window.appendEventLog = function(type, payload, label) {
  const log = document.getElementById('event-log');
  if (!log) return;
  const now = new Date();
  const time = now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const entry = document.createElement('div');
  entry.style.cssText = 'padding:2px 4px;border-left:2px solid var(--border,#2A3A4F);';
  // Color code by label
  const colors = {
    '[SPARK \u26A1]': '#00D4FF',
    '[HERMES \ud83e\udde0]': '#9600FF',
    '[KIMI-VL \ud83d\udc41]': '#FF6B35',
    '[MEM \ud83d\udcbe]': '#00FF88',
    '[KIMI K2 \u270d]': '#FFD700',
  };
  entry.style.borderLeftColor = colors[label] || '#2A3A4F';
  entry.innerHTML = `<span style="color:var(--text-secondary)">${time}</span> <span style="color:${colors[label] || '#E6EDF3'}">${label}</span> <span style="color:var(--text-secondary)">${type}</span>`;
  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
  // Keep only last 200 entries
  while (log.children.length > 200) log.removeChild(log.firstChild);
};

function updateLMStudioPill(status, text) {
  const pills = document.querySelectorAll('.status-pill');
  if (pills.length >= 2) {
    const pill = pills[1]; // second pill is Spark/LM Studio
    pill.innerHTML = '';
    pill.append(
      h('span', { class: `dot ${status}` }),
      ' ',
      text
    );
  }
}

function setIntensity(level) {
  document.body.classList.remove('intensity-tasteful','intensity-full');
  if (level === 'tasteful') document.body.classList.add('intensity-tasteful');
  if (level === 'full') document.body.classList.add('intensity-full');
  $$('.intensity-pill button').forEach(b => b.classList.toggle('active', b.dataset.intensity === level));
}

/* ---------- Topbar wiring ---------- */
function wireTopbar() {
  // Search button
  const searchBtn = document.querySelector('[title="Search"]');
  if (searchBtn) {
    searchBtn.addEventListener('click', () => {
      const existing = $('.search-overlay');
      if (existing) { existing.remove(); return; }
      const overlay = h('div', { class: 'search-overlay', style: 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9998;display:flex;align-items:flex-start;justify-content:center;padding-top:15vh;' },
        h('div', { style: 'width:90%;max-width:600px;background:var(--bg-secondary,#0D1420);border:1px solid var(--border,#2A3A4F);border-radius:8px;padding:16px;' },
          h('input', { id: 'global-search-input', class: 'input', placeholder: 'Search renders, characters, shots...', style: 'width:100%;background:var(--bg,#0A0E14);border:1px solid var(--border,#2A3A4F);color:var(--text,#E6EDF3);padding:10px 14px;border-radius:4px;font-size:14px;font-family:"JetBrains Mono",monospace;' }),
          h('div', { id: 'global-search-results', style: 'margin-top:12px;max-height:400px;overflow-y:auto;' })
        )
      );
      document.body.appendChild(overlay);
      const input = $('#global-search-input');
      const results = $('#global-search-results');
      input.focus();
      input.addEventListener('input', async () => {
        const q = input.value.trim();
        if (q.length < 2) { results.innerHTML = ''; return; }
        results.innerHTML = '<div style="color:var(--text-secondary);font-size:12px;padding:8px;">Searching...</div>';
        try {
          const data = await apiGet(`/api/search?q=${encodeURIComponent(q)}`, []);
          if (!data.length) {
            results.innerHTML = '<div style="color:var(--text-secondary);font-size:12px;padding:8px;">No results found</div>';
            return;
          }
          results.innerHTML = '';
          data.forEach(item => {
            results.append(h('div', {
              class: 'search-result',
              style: 'padding:8px 12px;border-radius:4px;cursor:pointer;font-size:12px;border-bottom:1px solid var(--border,#2A3A4F);',
              onclick: () => { overlay.remove(); if (item.tab) switchTab(item.tab); }
            }, `${item.type || 'Result'}: ${item.label || item.title || ''}`));
          });
        } catch (e) {
          results.innerHTML = '<div style="color:var(--error);font-size:12px;padding:8px;">Search unavailable</div>';
        }
      });
      overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
      input.addEventListener('keydown', (e) => { if (e.key === 'Escape') overlay.remove(); });
    });
  }

  // Notifications button
  const notifBtn = document.querySelector('[title="Notifications"]');
  if (notifBtn) {
    notifBtn.addEventListener('click', async () => {
      switchTab('memory', false);
      window.showToast('Notifications merged into Memory timeline', 'info');
    });
  }

  // Status pills - update from API
  updateStatusPills();
}

async function updateStatusPills() {
  try {
    const stats = await apiGet('/api/stats', null);
    if (stats) {
      const hermesPill = document.querySelectorAll('.status-pill')[0];
      if (hermesPill) {
        hermesPill.textContent = '';
        hermesPill.append(h('span', { class: 'dot live' }), ' ', 'Hermes — ' + (stats.insights || 12) + ' insights');
      }
      const sparkPill = document.querySelectorAll('.status-pill')[1];
      if (sparkPill) {
        const status = stats.spark_status || 'ready';
        sparkPill.textContent = '';
        sparkPill.append(h('span', { class: 'dot' + (status === 'ready' ? ' live' : '') }), ' ', 'Spark ' + status);
      }
    }
  } catch (e) { /* keep defaults */ }
}

/* ---------- Tab switching ---------- */
const CRUMB_SECTION = { home: 'Home', characters: 'Characters', script: 'Script', renders: 'Renders', memory: 'Memory', settings: 'Settings' };
const CRUMB_CURRENT = { home: 'Overview', characters: 'Elara', script: 'pilot_script.md', renders: 'Batch · 849271', memory: 'Knowledge graph', settings: 'Models' };

function switchTab(name, updateHash = true) {
  activeTab = name;
  if (updateHash) location.hash = '#/' + name;
  $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  $$('.rail-item[data-view]').forEach(el => el.classList.toggle('active', el.dataset.view === name));
  const cs = document.getElementById('crumbSection');
  const cc = document.getElementById('crumbCurrent');
  if (cs) cs.textContent = CRUMB_SECTION[name] || name;
  if (cc) cc.textContent = CRUMB_CURRENT[name] || '';
  const view = $('#view');
  if (!view) return;
  view.innerHTML = '';
  const render = window.VIEWS[name] || window.VIEWS.home;
  const result = render();
  const finish = (el) => {
    view.innerHTML = '';
    view.append(el);
    view.style.animation = 'none';
    void view.offsetWidth;
    view.style.animation = '';
    animateStatCounts();
    if (name === 'memory') setTimeout(initMemoryGraph, 30);
  };
  if (result && typeof result.then === 'function') {
    result.then(finish).catch(e => {
      console.error('View error:', e);
      view.innerHTML = '<div style="padding:24px;color:var(--error)">View failed to load</div>';
    });
  } else {
    finish(result);
  }
}

function animateStatCounts() {
  $$('[data-countup]').forEach(el => {
    const target = parseFloat(el.dataset.countup);
    const decimals = el.dataset.decimals ? +el.dataset.decimals : 0;
    const suffix = el.dataset.suffix || '';
    const dur = 700;
    const start = performance.now();
    const ease = t => 1 - Math.pow(1 - t, 3);
    function tick(now) {
      const p = Math.min(1, (now - start) / dur);
      el.textContent = (target * ease(p)).toFixed(decimals) + suffix;
    }
    requestAnimationFrame(tick);
  });
}

/* ---------- Shared bits ---------- */
function statCard({ label, value, accent, sub, decimals=0, suffix='' }) {
  return h('div', { class: 'card stat', 'data-accent': accent },
    h('div', { class: 'stat-label' }, h('span', { class: `dot d-${accent}` }), label),
    h('div', { class: 'stat-value', 'data-countup': value, 'data-decimals': decimals, 'data-suffix': suffix }, '0'),
    sub ? h('div', { class: 'stat-sub' }, sub) : null
  );
}

function sectionHead(title, meta) {
  return h('div', { class: 'section-head' },
    h('h2', {}, title),
    h('div', { class: 'bar' }),
    meta ? h('div', { class: 'meta' }, meta) : null
  );
}

/* ======================================================================
   VIEWS
   ====================================================================== */
window.VIEWS = {};

/* ---------- HOME VIEW ---------- */
window.VIEWS.home = async () => {
  const root = h('div');

  // Fetch stats from API
  const stats = await apiGet('/api/stats', {
    total_events: 176, insights: 12, success_rate: 94,
    queue_depth: 22, active_sessions: 1, time_window: 24
  });

  // hero stats
  const hero = h('div', { class: 'hero-grid' },
    statCard({ label: 'Total Events',   value: stats.total_events ?? 176, accent: 'cyan' }),
    statCard({ label: 'Insights',       value: stats.insights ?? 12, accent: 'purple' }),
    statCard({ label: 'Success Rate',   value: stats.success_rate ?? 94, accent: 'green', suffix: '%' }),
    statCard({ label: 'Queue Depth',    value: stats.queue_depth ?? 22, accent: 'amber', sub: h('span', {}, `${stats.queue_total ?? 24} staged`) }),
    statCard({ label: 'Active Sessions', value: stats.active_sessions ?? 1, accent: 'magenta', sub: h('span', {}, stats.session_info ?? 'node-02 · 45GB VRAM') }),
    statCard({ label: 'Time Window',    value: stats.time_window ?? 24, accent: 'cyan', suffix: 'h' })
  );
  root.append(hero);

  const body = h('div', { class: 'home-body' });
  const left = h('div', { class: 'col gap-3' });

  // recent renders card - fetch real renders
  const renders = await apiGet('/api/renders', []);
  const recent = h('div', { class: 'card card-pad', 'data-accent': 'cyan' });
  recent.append(
    h('div', { class: 'row between', style: 'margin-bottom: 14px;' },
      h('div', { class: 'col gap-1' },
        h('div', { class: 'display', style: 'font-size: 13px;' }, 'Recent Renders'),
        h('div', { class: 'label' }, `Last ${Math.min(renders.length, 8)} · session node-02`)
      ),
      h('div', { class: 'row gap-2' },
        ...['All','Elara','Orin','Vex'].map((name, i) =>
          h('button', {
            class: 'chip' + (i === 0 ? ' active' : ''),
            onclick: (e) => {
              $$('.chip', recent).forEach(c => c.classList.remove('active'));
              e.currentTarget.classList.add('active');
              filterRecentRenders(name);
            }
          }, name)
        )
      )
    )
  );

  const strip = h('div', { class: 'recent-strip', id: 'recent-strip' });
  const accents = ['cyan','magenta','amber','green'];
  const renderThumbs = (list) => {
    strip.innerHTML = '';
    const shown = list.slice(0, 8);
    if (!shown.length) {
      strip.append(h('div', { style: 'padding:20px;text-align:center;color:var(--text-3);font-size:12px;' }, 'No renders yet'));
      return;
    }
    shown.forEach((r, i) => {
      const c = accents[i % accents.length];
      const thumb = h('div', { class: 'thumb' });
      if (r.src) {
        thumb.append(h('img', { src: r.src, alt: r.prompt || '', style: 'width:100%;height:100%;object-fit:cover;' }));
      } else {
        thumb.innerHTML = frameSVG(`VAR_${String(i+1).padStart(3,'0')}`, i, c);
      }
      const overlay = h('div', { class: 'meta-overlay' },
        h('div', { style: 'color: var(--' + c + '); letter-spacing: 0.14em;' }, String(r.id || 'VAR_' + String(i+1).padStart(3,'0'))),
        h('div', { class: 'muted' }, 'seed ' + String(r.seed || '—') + ' · score ' + String(r.score || '—'))
      );
      thumb.append(overlay);
      strip.append(thumb);
    });
  };

  renderThumbs(renders);
  window.filterRecentRenders = (charName) => {
    if (charName === 'All') renderThumbs(renders);
    else renderThumbs(renders.filter(r => (r.prompt || '').toLowerCase().includes(charName.toLowerCase())));
  };

  recent.append(strip);
  left.append(recent);

  // queue panel
  const queue = h('div', { class: 'card card-pad queue-panel', 'data-accent': 'amber' },
    h('div', { class: 'row between' },
      h('div', { class: 'col gap-1' },
        h('div', { class: 'display', style: 'font-size: 13px;' }, 'Live Queue'),
        h('div', { class: 'label' }, 'Spark · node-02 · FLUX2 NVFP4 Turbo')
      ),
      h('div', { class: 'heartbeat' },
        ...Array.from({ length: 8 }, () => h('div', { class: 'bar' }))
      )
    ),
    h('div', { class: 'current' },
      h('div', { class: 'col gap-1', style: 'min-width: 0; flex: 1;' },
        h('div', { style: 'font-size: 14px; color: var(--amber); letter-spacing: 0.1em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;' }, stats.current_job || 'VAR_014 · cockpit-cu · Elara'),
        h('div', { class: 'eta' }, stats.queue_eta || 'ETA 3m 12s · 8 of 24 complete')
      ),
      h('div', { class: 'row gap-2', style: 'flex-shrink: 0;' },
        h('button', { class: 'icon-btn', title: 'Pause', onclick: () => toggleQueue('pause') }, '⏸'),
        h('button', { class: 'icon-btn', title: 'Skip', onclick: () => toggleQueue('skip') }, '⏭')
      )
    ),
    h('div', { class: 'progress' }, h('div', { class: 'fill', style: `width: ${stats.queue_progress ?? 33}%;` }))
  );
  left.append(queue);

  // right column
  const right = h('div', { class: 'col gap-3' });

  const actionsCard = h('div', { class: 'card card-pad', 'data-accent': 'cyan' },
    h('div', { class: 'display', style: 'font-size: 13px; margin-bottom: 14px;' }, 'Quick Actions'),
    h('div', { class: 'quick-actions' },
      h('button', { class: 'quick-action', onclick: () => switchTab('renders') },
        h('div', { class: 'title', style: 'color: var(--green);' }, '▶ Start Batch'),
        h('div', { class: 'desc' }, 'Dispatch 24 renders to Spark')
      ),
      h('button', { class: 'quick-action', onclick: () => switchTab('characters') },
        h('div', { class: 'title', style: 'color: var(--magenta);' }, '◉ Review Anchors'),
        h('div', { class: 'desc' }, 'Check character DNA integrity')
      ),
      h('button', { class: 'quick-action', onclick: () => openSparkOutput() },
        h('div', { class: 'title', style: 'color: var(--amber);' }, '⇱ Open Spark Output'),
        h('div', { class: 'desc' }, 'node-02 · /output/2026-04-23')
      ),
      h('button', { class: 'quick-action', onclick: () => switchTab('memory') },
        h('div', { class: 'title', style: 'color: var(--purple);' }, '⎈ Run Memory Audit'),
        h('div', { class: 'desc' }, 'Consolidate episodic → semantic')
      )
    )
  );
  right.append(actionsCard);

  // mini-timeline preview - fetch from API
  const timeline = await apiGet('/api/memory/timeline', TIMELINE);
  const feed = h('div', { class: 'card card-pad', 'data-accent': 'purple' },
    h('div', { class: 'row between', style: 'margin-bottom: 10px;' },
      h('div', { class: 'display', style: 'font-size: 13px;' }, 'Live Feed'),
      h('div', { class: 'ticker' }, 'STREAMING · 24.ms')
    ),
    h('div', { class: 'timeline' },
      ...(timeline || []).slice(0, 5).map(e => h('div', { class: 'tl-event' },
        h('div', { class: 'tl-time' }, e.t),
        h('div', { class: 'tl-body' },
          h('div', { class: 'tl-type' }, e.type),
          h('div', { class: 'tl-desc' }, e.desc)
        )
      ))
    )
  );
  right.append(feed);

  body.append(left, right);
  root.append(body);
  return root;
};

/* ---------- Queue controls ---------- */
async function toggleQueue(action) {
  try {
    const result = await apiPost('/api/queue/toggle', { action });
    window.showToast(`Queue ${action}: ${result.message || 'OK'}`, action === 'pause' ? 'warning' : 'info');
  } catch (e) {
    window.showToast(`Queue ${action} failed: ${e.message}`, 'error');
  }
}

function openSparkOutput() {
  apiGet('/api/spark/output-path', null).then(path => {
    if (path) {
      window.open(path, '_blank');
    } else {
      window.showToast('Spark output path not available', 'warning');
    }
  }).catch(() => {
    window.showToast('Could not reach Spark server', 'error');
  });
}

/* ---------- CHARACTERS VIEW ---------- */
window.VIEWS.characters = async () => {
  const root = h('div');

  // Fetch characters from API
  const apiChars = await apiGet('/api/characters', null);
  const chars = apiChars || CHARACTERS;

  const char = chars.find(c => c.id === activeCharId) || chars[0];

  // selector
  const selector = h('div', { class: 'char-selector' });
  chars.forEach(c => {
    selector.append(h('div', {
      class: 'card char-pick interactive' + (c.id === char.id ? ' active' : ''),
      'data-accent': c.accent,
      onclick: () => { activeCharId = c.id; switchTab('characters', false); }
    },
      h('div', { class: 'portrait', html: c.anchor_url ? '' : portraitSVG(c, 56) }),
      c.anchor_url ? h('img', { src: c.anchor_url, alt: c.name, style: 'width:56px;height:56px;border-radius:4px;object-fit:cover;' }) : null,
      h('div', { class: 'col gap-1' },
        h('div', { class: 'name' }, c.name),
        h('div', { class: 'role' }, c.role)
      ),
      h('div', { style: 'margin-left: auto;' },
        h('span', { class: `dot d-${c.score >= 90 ? 'green' : 'amber'}` })
      )
    ));
  });
  // add new
  selector.append(h('div', { class: 'card char-pick interactive', style: 'border-style: dashed; justify-content: center;', onclick: () => window.openAddCharacterModal() },
    h('div', { class: 'col gap-1', style: 'align-items: center; text-align: center;' },
      h('div', { style: 'color: var(--text-secondary); font-size: 20px;' }, '+'),
      h('div', { class: 'label' }, 'Add Character')
    )
  ));
  root.append(selector);

  // hero: anchor + DNA editor
  const hero = h('div', { class: 'char-hero' });

  const anchor = h('div', { class: 'card anchor-card', 'data-accent': char.accent, id: `char-anchor-${char.id}` });
  if (char.anchor_url) {
    anchor.append(h('img', { src: char.anchor_url, alt: char.name, style: 'width:100%;max-height:520px;object-fit:contain;' }));
  } else {
    anchor.append(h('div', { class: 'anchor-img', html: portraitSVG(char, 520) }));
  }
  anchor.append(
    h('div', { class: 'anchor-footer' },
      h('div', { class: 'consistency' },
        h('div', { class: 'row between' },
          h('span', { class: 'label' }, 'Consistency Score'),
          h('span', { class: 'score' }, (char.score || 0) + '%')
        ),
        h('div', { class: 'progress mono green' }, h('div', { class: 'fill', style: `width: ${char.score || 0}%;` }))
      ),
      h('button', { class: 'btn btn-primary', onclick: () => regenerateAnchor(char) }, '↻ Regenerate Anchor')
    )
  );
  hero.append(anchor);

  // DNA editor
  const dna = h('div', { class: 'card dna-editor', 'data-accent': 'magenta' });
  const dnaBody = h('div', { class: 'dna-body' });
  const edit = h('div', { class: 'dna-pane' });
  edit.append(
    h('h3', {}, 'Character DNA · markdown source'),
    h('div', { class: 'dna-md', html: `
<span class="h"># ${char.name}</span>
<span class="c"># ${char.role}</span>

<span class="h">## HAIR</span>
<span class="k">description:</span> <span class="v">"${char.dna?.hair || '—'}"</span>

<span class="h">## EYES</span>
<span class="k">description:</span> <span class="v">"${char.dna?.eyes || '—'}"</span>

<span class="h">## BUILD</span>
<span class="k">description:</span> <span class="v">"${char.dna?.build || '—'}"</span>

<span class="h">## CLOTHING</span>
<span class="k">description:</span> <span class="v">"${char.dna?.clothing || '—'}"</span>

<span class="h">## SIGNATURE</span>
<span class="k">description:</span> <span class="v">"${char.dna?.signature || '—'}"</span>

<span class="h">## PALETTE</span>
<span class="k">hex:</span> <span class="v">${(char.dna?.palette || []).map(p=>`"${p}"`).join(', ')}</span>` })
  );
  const preview = h('div', { class: 'dna-pane dna-preview' },
    h('h3', {}, 'Rendered preview'),
    h('h4', {}, 'Hair'),       h('p', {}, char.dna?.hair || '—'),
    h('h4', {}, 'Eyes'),       h('p', {}, char.dna?.eyes || '—'),
    h('h4', {}, 'Build'),      h('p', {}, char.dna?.build || '—'),
    h('h4', {}, 'Clothing'),   h('p', {}, char.dna?.clothing || '—'),
    h('h4', {}, 'Signature'),  h('p', {}, char.dna?.signature || '—'),
    h('h4', {}, 'Palette'),
    h('div', { class: 'row gap-2', style: 'margin-top: 4px;' },
      ...(char.dna?.palette || []).map(c => h('div', { style: `width: 32px; height: 32px; border-radius: 4px; border: 1px solid var(--border); background: ${c};`, title: c }))
    )
  );
  dnaBody.append(edit, preview);
  dna.append(dnaBody,
    h('div', { class: 'row between', style: 'padding: 12px 18px; border-top: 1px solid var(--border);' },
      h('div', { class: 'label' }, char.last_saved ? `last saved ${char.last_saved}` : 'last saved 2m ago · 14 revisions'),
      h('div', { class: 'row gap-2' },
        h('button', { class: 'btn btn-ghost', onclick: () => exportCharacter(char) }, 'Export'),
        h('button', { class: 'btn btn-primary', onclick: () => saveCharacterDNA(char) }, '✓ Save DNA')
      )
    )
  );
  hero.append(dna);
  root.append(hero);

  // variation gallery - fetch from API
  root.append(h('div', { style: 'height: 16px;' }));
  root.append(sectionHead('Variation Gallery', `${char.name} · variations`));

  const chips = h('div', { class: 'filter-chips', style: 'margin-bottom: 12px;' });
  const varFilters = ['All','Pose','Lighting','Background','Best Only'];
  varFilters.forEach((name, i) => {
    chips.append(h('button', {
      class: 'chip' + (i === 0 ? ' active' : ''),
      onclick: (e) => {
        $$('.chip', chips).forEach(c => c.classList.remove('active'));
        e.currentTarget.classList.add('active');
        filterVariations(char.id, name);
      }
    }, name));
  });
  root.append(chips);

  const gal = h('div', { class: 'var-gallery', id: 'var-gallery' });
  // Fetch variations from API
  const vars = await apiGet(`/api/characters/${char.id}/variations`, []);
  const renderVars = (list) => {
    gal.innerHTML = '';
    if (!list.length) {
      gal.append(h('div', { style: 'grid-column:1/-1;padding:40px;text-align:center;color:var(--text-3);font-size:12px;' }, 'No variations yet. Run a batch to generate.'));
      return;
    }
    list.forEach((v, i) => {
      const accent = char.accent;
      const tile = h('div', { class: 'thumb' });
      if (v.src) {
        tile.append(h('img', { src: v.src, alt: v.prompt || '', style: 'width:100%;height:100%;object-fit:cover;' }));
      } else {
        tile.innerHTML = frameSVG(char.name + '_V' + String(i+1).padStart(2,'0'), i, accent);
      }
      const overlay = h('div', { class: 'meta-overlay' },
        h('div', { style: 'color: var(--' + accent + '); letter-spacing: 0.14em;' }, String(v.id || 'V' + String(i+1).padStart(2,'0')) + ' · score ' + String(v.score || '—')),
        h('div', { class: 'muted', style: 'font-size: 9px;' }, String(v.type || 'pose') + ' · seed ' + String(v.seed || '—'))
      );
      tile.append(overlay);
      gal.append(tile);
    });
  };
  renderVars(vars);
  window.filterVariations = (charId, filter) => {
    if (filter === 'All') renderVars(vars);
    else renderVars(vars.filter(v => (v.type || '').toLowerCase() === filter.toLowerCase() || (v.prompt || '').toLowerCase().includes(filter.toLowerCase())));
  };
  root.append(gal);

  return root;
};

/* ---------- Character actions ---------- */
async function regenerateAnchor(char) {
  window.showToast(`Regenerating anchor for ${char.name}...`, 'info');
  try {
    const result = await apiPost('/api/characters/render', { name: char.id, prompt: char.anchor_prompt });
    window.showToast(`Anchor regenerated: ${result.message || 'OK'}`, 'success');
    switchTab('characters', false);
  } catch (e) {
    window.showToast(`Anchor regen failed: ${e.message}`, 'error');
  }
}

async function exportCharacter(char) {
  try {
    const data = await apiGet(`/api/characters/${char.id}/export`, null);
    if (data) {
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `${char.id}_dna.json`; a.click();
      URL.revokeObjectURL(url);
      window.showToast(`Exported ${char.name} DNA`, 'success');
    }
  } catch (e) {
    // Fallback: export from local data
    const blob = new Blob([JSON.stringify(char, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${char.id}_dna.json`; a.click();
    URL.revokeObjectURL(url);
    window.showToast(`Exported ${char.name} DNA (local)`, 'success');
  }
}

async function saveCharacterDNA(char) {
  window.showToast(`Saving DNA for ${char.name}...`, 'info');
  try {
    const result = await apiPost('/api/characters/save-dna', { id: char.id, dna: char.dna });
    window.showToast(`DNA saved: ${result.message || 'OK'}`, 'success');
  } catch (e) {
    window.showToast(`Save failed: ${e.message}`, 'error');
  }
}

/* ---------- SCRIPT VIEW ---------- */
window.VIEWS.script = async () => {
  const root = h('div');

  let scriptFiles = [];
  try {
    const sr = await fetch('/api/scripts');
    if (sr.ok) scriptFiles = await sr.json();
  } catch (e) { /* ignore */ }

  const select = h('select', { class: 'select', style: 'min-width: 320px;' },
    h('option', { value: '' }, '— demo shots —'),
    ...scriptFiles.map(s => h('option', { value: s.path }, s.label))
  );

  const reparseBtn = h('button', { class: 'btn btn-primary' }, '↻ Load Script');

  const toolbar = h('div', { class: 'script-toolbar' },
    h('div', { class: 'col gap-1' },
      h('div', { class: 'label' }, 'Active script'),
      select
    ),
    h('div', { class: 'col gap-1' },
      h('div', { class: 'label' }, 'Detected characters'),
      h('div', { class: 'row gap-2' },
        ...CHARACTERS.map(c => h('span', { class: `badge b-${c.accent === 'cyan' ? 'cyan' : c.accent === 'magenta' ? 'magenta' : 'amber'}` }, c.name))
      )
    ),
    h('div', { style: 'margin-left: auto;' }, reparseBtn)
  );
  root.append(toolbar);

  let shots = [];
  try {
    const sr = await fetch('/api/shots');
    if (sr.ok) shots = await sr.json();
  } catch (e) { /* fallback to empty */ }

  const statusLabel = h('span', { class: 'muted', style: 'font-size: 11px; margin-left: 8px;' },
    `${shots.length} shots`
  );
  toolbar.append(statusLabel);

  const card = h('div', { class: 'card', 'data-accent': 'cyan' });
  const table = h('table', { class: 'script-table' });
  table.append(h('thead', {}, h('tr', {},
    h('th', { style: 'width: 44px;' }, '#'),
    h('th', { style: 'width: 130px;' }, 'Shot ID'),
    h('th', { style: 'width: 180px;' }, 'Characters'),
    h('th', { style: 'width: 130px;' }, 'Status'),
    h('th', {}, 'Prompt Preview')
  )));
  const tbody = h('tbody');

  const renderShots = (list) => {
    tbody.innerHTML = '';
    if (list.length === 0) {
      const empty = h('tr', {}, h('td', { colspan: 5, style: 'padding: 40px; text-align: center; color: var(--text-3);' },
        'No SHOT markers found in this script. Select a different file or add ## SHOT lines.'
      ));
      tbody.append(empty);
      return;
    }
    list.forEach(s => {
      const row = h('tr', { class: expandedShot === s.id ? 'expanded' : '' },
        h('td', {}, String(s.n).padStart(2, '0')),
        h('td', {}, h('span', { style: 'color: var(--cyan); letter-spacing: 0.08em;' }, s.id)),
        h('td', {}, h('div', { class: 'row gap-2 wrap' },
          ...s.chars.map(c => h('span', { class: 'badge b-magenta' }, c))
        )),
        h('td', {}, h('span', { class: 'badge ' + (STATUS_BADGE[s.status] || { cls: 'b-cyan', label: s.status || 'READY' }).cls },
          (STATUS_BADGE[s.status] || { cls: 'b-cyan', label: s.status || 'READY' }).label)),
        h('td', {}, h('span', { class: 'prompt-preview' }, s.prompt))
      );
      row.addEventListener('click', () => {
        expandedShot = expandedShot === s.id ? null : s.id;
        switchTab('script', false);
      });
      tbody.append(row);
      if (expandedShot === s.id) {
        tbody.append(h('tr', {}, h('td', { colspan: 5, style: 'padding: 0;' },
          h('div', { class: 'shot-detail' },
            h('div', { class: 'col gap-3' },
              h('div', { class: 'label' }, 'Full prompt'),
              h('pre', {}, s.prompt),
              h('div', { class: 'row gap-2' },
                h('button', { class: 'btn btn-sm', onclick: (e) => { e.stopPropagation(); editPrompt(s); } }, 'Edit prompt'),
                h('button', { class: 'btn btn-sm btn-primary', onclick: (e) => { e.stopPropagation(); dispatchShot(s); } }, 'Dispatch to Spark'),
                h('button', {
                  class: 'btn btn-sm btn-ghost',
                  onclick: (e) => { e.stopPropagation(); navigator.clipboard.writeText(String(s.seed)); window.showToast('Seed copied', 'success'); }
                }, 'Copy seed')
              )
            ),
            h('div', { class: 'meta-block' },
              h('div', { class: 'col gap-1' },
                h('span', { class: 'label' }, 'Locked seed'),
                h('div', { style: 'font-size: 18px; color: var(--amber); letter-spacing: 0.1em;' }, s.seed + ' 🔒')
              ),
              h('div', { class: 'col gap-1' },
                h('span', { class: 'label' }, 'Detected anchors'),
                h('div', { class: 'row gap-2 wrap' },
                  ...s.chars.map(c => h('span', { class: 'badge b-magenta' }, c))
                )
              )
            )
          )
        )));
      }
    });
  };

  renderShots(shots);
  table.append(tbody);
  card.append(table);
  root.append(card);

  const loadScript = async (path) => {
    reparseBtn.disabled = true;
    reparseBtn.textContent = '⌛ Loading…';
    try {
      const res = await fetch('/api/script/reparse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path })
      });
      const data = await res.json();
      const fresh = await fetch('/api/shots');
      const newShots = fresh.ok ? await fresh.json() : [];
      renderShots(newShots);
      statusLabel.textContent = `${newShots.length} shots`;
      reparseBtn.textContent = `✓ ${data.count} shots`;
      window.showToast(`Loaded ${data.count} shots`, 'success');
    } catch (e) {
      reparseBtn.textContent = '✗ Error';
      window.showToast(`Load failed: ${e.message}`, 'error');
    } finally {
      setTimeout(() => {
        reparseBtn.disabled = false;
        reparseBtn.textContent = '↻ Load Script';
      }, 2000);
    }
  };

  select.addEventListener('change', () => loadScript(select.value));
  reparseBtn.addEventListener('click', () => loadScript(select.value));

  return root;
};

/* ---------- Script actions ---------- */
function editPrompt(shot) {
  const modal = h('div', { id: 'modal-overlay', class: 'modal-overlay', style: 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9999;display:flex;align-items:center;justify-content:center;' },
    h('div', { class: 'modal-content', style: 'background:var(--bg-secondary,#0D1420);border:1px solid var(--border,#2A3A4F);border-radius:8px;padding:24px;width:90%;max-width:600px;max-height:80vh;overflow-y:auto;' },
      h('h3', { style: 'margin-bottom:12px;' }, `Edit Prompt · ${shot.id}`),
      h('textarea', { id: 'edit-prompt-text', class: 'textarea', style: 'width:100%;min-height:200px;background:var(--bg,#0A0E14);border:1px solid var(--border,#2A3A4F);color:var(--text,#E6EDF3);padding:12px;border-radius:4px;font-family:"JetBrains Mono",monospace;font-size:12px;resize:vertical;' }, shot.prompt),
      h('div', { class: 'modal-actions', style: 'display:flex;gap:8px;justify-content:flex-end;margin-top:16px;' },
        h('button', { class: 'btn btn-ghost', onclick: () => document.getElementById('modal-overlay').remove() }, 'Cancel'),
        h('button', { class: 'btn btn-primary', onclick: async () => {
          const newPrompt = document.getElementById('edit-prompt-text').value;
          try {
            await apiPost('/api/shots/update', { id: shot.id, prompt: newPrompt });
            shot.prompt = newPrompt;
            window.showToast('Prompt updated', 'success');
          } catch (e) {
            window.showToast(`Update failed: ${e.message}`, 'error');
          }
          document.getElementById('modal-overlay').remove();
        }}, 'Save')
      )
    )
  );
  document.body.appendChild(modal);
}

async function dispatchShot(shot) {
  window.showToast(`Dispatching ${shot.id} to Spark...`, 'info');
  try {
    const result = await apiPost('/api/shots/dispatch', { id: shot.id });
    window.showToast(`${shot.id} dispatched: ${result.message || 'OK'}`, 'success');
    shot.status = 'queued';
  } catch (e) {
    window.showToast(`Dispatch failed: ${e.message}`, 'error');
  }
}

/* ---------- RENDERS VIEW ---------- */
window.VIEWS.renders = async () => {
  const root = h('div', { class: 'renders-shell' });

  const workflowSelect = h('select', { class: 'select' },
    h('option', {}, 'FLUX2 NVFP4 Turbo'),
    h('option', {}, 'FLUX.1 Dev'),
    h('option', {}, 'Z-Image Turbo')
  );
  const countInput = h('input', { class: 'input', type: 'number', value: 24, min: 1, max: 50, style: 'width: 70px;' });
  const seedInput = h('input', { class: 'input', value: '849271', style: 'width: 100px;' });

  // Length selector [15s][30s][60s][90s] -> shot counts 3/6/12/18
  const LENGTH_MAP = { '15s': 3, '30s': 6, '60s': 12, '90s': 18 };
  let selectedLength = '30s';
  const lengthBtns = ['15s', '30s', '60s', '90s'].map(len =>
    h('button', {
      class: 'chip' + (len === selectedLength ? ' active' : ''),
      id: 'length-' + len,
      onclick: () => {
        selectedLength = len;
        Object.values(LENGTH_MAP).forEach(() => {}); // no-op
        $$('[id^="length-"]').forEach(b => b.classList.remove('active'));
        $('#length-' + len).classList.add('active');
        countInput.value = LENGTH_MAP[len];
      }
    }, len)
  );
  const lengthGroup = h('div', { class: 'field' },
    h('span', { class: 'label' }, 'Length'),
    h('div', { class: 'row gap-1' }, ...lengthBtns)
  );

  const bar = h('div', { class: 'renders-toolbar' },
    h('div', { class: 'field' },
      h('span', { class: 'label' }, 'Workflow'),
      workflowSelect
    ),
    lengthGroup,
    h('div', { class: 'field' },
      h('span', { class: 'label' }, 'Count'),
      countInput
    ),
    h('div', { class: 'field' },
      h('span', { class: 'label' }, 'Seed'),
      seedInput
    ),
    h('button', { class: 'btn btn-primary', id: 'start-batch-btn' }, '▶  Start Batch'),
    h('button', { class: 'btn btn-danger', id: 'clear-queue-btn' }, 'Clear Queue'),
    h('button', {
      class: 'btn btn-secondary',
      id: 'audit-all-btn',
      onclick: () => window.runVisionAuditBatch && window.runVisionAuditBatch()
    }, '👁 Audit All'),
    h('button', {
      class: 'btn btn-secondary',
      id: 'sort-order-btn',
      title: 'Toggle sort order'
    }, '↓ Newest'),
    h('span', { class: 'muted', style: 'margin-left: auto; font-size: 11px;' }, 'loading…')
  );
  root.append(bar);

  // Start Batch button
  const startBtn = $('#start-batch-btn', root);
  if (startBtn) {
    startBtn.addEventListener('click', async () => {
      const workflow = workflowSelect.value;
      const count = parseInt(countInput.value) || 24;
      const seed = seedInput.value || '849271';
      startBtn.disabled = true;
      startBtn.textContent = '⌛ Starting...';
      try {
        const result = await apiPost('/api/batch/start', { workflow, count, seed });
        window.showToast(`Batch started: ${result.message || `${count} renders queued`}`, 'success');
        // Refresh renders
        const res = await fetch('/api/renders');
        if (res.ok) {
          renders = await res.json();
          buildGrid();
        }
      } catch (e) {
        window.showToast(`Batch failed: ${e.message}`, 'error');
      } finally {
        setTimeout(() => { startBtn.disabled = false; startBtn.textContent = '▶  Start Batch'; }, 2000);
      }
    });
  }

  // Clear Queue button
  const clearBtn = $('#clear-queue-btn', root);
  if (clearBtn) {
    clearBtn.addEventListener('click', async () => {
      if (!confirm('Clear the entire render queue?')) return;
      clearBtn.disabled = true;
      clearBtn.textContent = '⌛ Clearing...';
      try {
        const result = await apiPost('/api/queue/clear', {});
        window.showToast(`Queue cleared: ${result.message || 'OK'}`, 'success');
      } catch (e) {
        window.showToast(`Clear failed: ${e.message}`, 'error');
      } finally {
        setTimeout(() => { clearBtn.disabled = false; clearBtn.textContent = 'Clear Queue'; }, 2000);
      }
    });
  }

  // Vision Audit Batch
  window.runVisionAuditBatch = async () => {
    const btn = $('#audit-all-btn');
    if (!btn || btn.disabled) return;

    if (!confirm("Start batch vision audit for all Sienna renders? This will call the local Gemma 4 model via LM Studio.")) return;

    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⌛ Auditing...';

    try {
      const response = await fetch('/api/renders/audit-batch', { method: 'POST' });
      if (!response.ok) throw new Error('Audit request failed');

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n').filter(line => line.trim());

        for (const line of lines) {
          try {
            const result = JSON.parse(line);
            if (result.error || !result.filename) continue;

            const tiles = $$('.renders-tile');
            let targetTile = null;
            for (const t of tiles) {
              const img = t.querySelector('img');
              if (img && img.src.includes(result.filename)) {
                targetTile = t;
                break;
              }
            }

            if (targetTile) {
              const chip = targetTile.querySelector('.audit-chip');
              if (chip) {
                const isPass = result.status === 'PASS';
                const isFail = result.status === 'FAIL';
                const label = isPass ? 'PASS' : isFail ? 'FAIL' : result.status;
                chip.className = `audit-chip ${isPass ? 'pass' : isFail ? 'fail' : 'unaudited'}`;
                chip.innerHTML = `<span>${label}</span><span class="audit-score">${String(result.score).padStart(2, '0')}</span>`;
              }
            }
          } catch (e) {
            console.error('Error parsing stream line:', e, line);
          }
        }
      }
      window.showToast('Audit complete', 'success');
    } catch (err) {
      console.error('Vision Audit Batch Error:', err);
      window.showToast(`Audit failed: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  };

  // Fetch real renders
  let renders = [];
  try {
    const res = await fetch('/api/renders');
    if (res.ok) renders = await res.json();
  } catch (e) {
    console.warn('Could not load renders:', e);
  }

  const countLabel = bar.querySelector('.muted');
  if (countLabel) countLabel.textContent = `${renders.length} renders`;

  let reversed = true;
  const grid = h('div', { class: 'renders-grid' });

  const buildGrid = () => {
    grid.innerHTML = '';
    const ordered = reversed ? [...renders].reverse() : renders;
    if (ordered.length === 0) {
      grid.append(h('div', { style: 'grid-column: 1/-1; padding: 80px; text-align: center; color: var(--text-3);' },
        'No renders found. Run a batch to see images here.'
      ));
    } else {
      ordered.forEach(r => {
        const isPass = r.status === 'PASS';
        const isFail = r.status === 'FAIL';
        const tile = h('div', { class: 'renders-tile', title: r.prompt });
        const img = h('img', { src: r.src, loading: 'lazy', alt: r.prompt });
        let chip;
        if (isPass || isFail) {
          const label = isPass ? 'PASS' : 'FAIL';
          const cls = isPass ? 'pass' : 'fail';
          chip = h('div', { class: `audit-chip ${cls}` },
            h('span', {}, label),
            r.score ? h('span', { class: 'audit-score' }, String(r.score).padStart(2, '0')) : ''
          );
        } else if (r.status === 'unaudited') {
          chip = h('div', { class: 'audit-chip unaudited' }, 'UNAUDITED');
        } else {
          chip = h('div', { class: 'audit-chip unaudited' }, r.score ? String(r.score).padStart(2, '0') : '—');
        }
        tile.append(img, chip);
        tile.addEventListener('click', () => openLightbox(r.src, r.prompt));
        grid.append(tile);
      });
    }
  };

  buildGrid();

  const sortBtn = document.getElementById('sort-order-btn');
  if (sortBtn) {
    sortBtn.addEventListener('click', () => {
      reversed = !reversed;
      sortBtn.textContent = reversed ? '↓ Newest' : '↑ Oldest';
      buildGrid();
    });
  }

  root.append(grid);
  return root;
};

function openLightbox(src, caption) {
  const existing = document.getElementById('forge-lightbox');
  if (existing) existing.remove();
  const lb = h('div', { id: 'forge-lightbox', style: 'position:fixed;inset:0;background:rgba(0,0,0,0.92);z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;cursor:zoom-out;' },
    h('img', { src, style: 'max-width:95vw;max-height:88vh;object-fit:contain;border-radius:4px;' }),
    h('div', { style: 'font-size:11px;color:var(--text-3);max-width:800px;text-align:center;' }, caption)
  );
  lb.addEventListener('click', () => lb.remove());
  document.body.appendChild(lb);
}

/* ---------- MEMORY VIEW ---------- */
window.VIEWS.memory = async () => {
  const root = h('div');

  // Fetch memory stats from API
  const memStats = await apiGet('/api/memory/stats', {
    events: 176, insights: 12, concepts: 18, confidence: 89, audits: 42, sessions: 3
  });

  const hero = h('div', { class: 'hero-grid' },
    statCard({ label: 'Events',      value: memStats.events ?? 176, accent: 'cyan' }),
    statCard({ label: 'Insights',    value: memStats.insights ?? 12, accent: 'purple' }),
    statCard({ label: 'Concepts',    value: memStats.concepts ?? 18, accent: 'magenta' }),
    statCard({ label: 'Confidence',  value: memStats.confidence ?? 89, accent: 'green', suffix: '%' }),
    statCard({ label: 'Audits',      value: memStats.audits ?? 42, accent: 'amber' }),
    statCard({ label: 'Sessions',    value: memStats.sessions ?? 3, accent: 'amber' })
  );
  root.append(hero);

  const layout = h('div', { class: 'memory-layout' });

  // graph
  const graph = h('div', { class: 'card graph-wrap', 'data-accent': 'purple' },
    h('div', { class: 'graph-toolbar' },
      h('input', { class: 'search', id: 'graph-search', placeholder: '⌕  Search nodes, rules, concepts…' }),
      h('button', { class: 'btn btn-sm', 'data-layout': 'cose' }, 'Force'),
      h('button', { class: 'btn btn-sm', 'data-layout': 'circle' }, 'Circle'),
      h('button', { class: 'btn btn-sm', 'data-layout': 'grid' }, 'Grid'),
      h('button', { class: 'btn btn-sm', 'data-layout': 'concentric' }, 'Radial')
    ),
    h('div', { class: 'graph-canvas', id: 'graph-canvas' }),
    h('div', { class: 'graph-legend' },
      h('div', { class: 'legend-row' }, h('span', { class: 'legend-sw', style: 'background: #FFBF00;' }), 'Session'),
      h('div', { class: 'legend-row' }, h('span', { class: 'legend-sw', style: 'background: #00FFFF;' }), 'Attempt'),
      h('div', { class: 'legend-row' }, h('span', { class: 'legend-sw', style: 'background: #00FF41;' }), 'Outcome'),
      h('div', { class: 'legend-row' }, h('span', { class: 'legend-sw', style: 'background: #BD00FF;' }), 'Insight'),
      h('div', { class: 'legend-row' }, h('span', { class: 'legend-sw', style: 'background: #FF00FF;' }), 'Concept')
    )
  );
  layout.append(graph);

  // Fetch insights + timeline from API
  const [apiInsights, apiTimeline] = await Promise.all([
    apiGet('/api/memory/insights', INSIGHTS),
    apiGet('/api/memory/timeline', [
      { t: '10:00', type: 'SESSION', desc: 'New session started' },
      { t: '10:05', type: 'ATTEMPT', desc: 'Workflow executed' },
      { t: '10:10', type: 'OUTCOME', desc: 'Generation complete' },
      { t: '10:15', type: 'INSIGHT', desc: 'New pattern detected' },
      { t: '10:20', type: 'SESSION', desc: 'Session checkpoint' },
      { t: '10:25', type: 'ATTEMPT', desc: 'Retry attempt' },
      { t: '10:30', type: 'OUTCOME', desc: 'Quality threshold met' },
      { t: '10:35', type: 'INSIGHT', desc: 'Confidence updated' }
    ])
  ]);

  // side: insights + timeline
  const side = h('div', { class: 'mem-side' });
  let insightCount = (apiInsights || []).length;
  const insightsCard = h('div', { class: 'card card-pad', 'data-accent': 'purple' },
    h('div', { class: 'row between', style: 'margin-bottom: 12px;' },
      h('div', { class: 'display', style: 'font-size: 12px;' }, 'Rulebook'),
      h('span', { id: 'insights-rule-count', class: 'badge b-purple' }, insightCount + ' RULES')
    ),
    h('div', { class: 'rulebook', id: 'rulebook-container' })
  );

  // Render formatted rule entries from insights data
  function renderRuleEntry(i) {
    const confirms = i.confirmations || i.confirms || 0;
    const confPct = Math.round((i.confidence ?? 0) * 100);
    const kernel = (i.applies_to && i.applies_to.kernel_id) ? `[${i.applies_to.kernel_id}]` : '';
    const errorCat = (i.applies_to && i.applies_to.error_category && i.applies_to.error_category !== 'None') ? ` — ${i.applies_to.error_category}` : '';

    // Parse created_at to relative time
    let ageStr = '';
    if (i.created_at) {
      const then = new Date(i.created_at);
      const diffMs = Date.now() - then.getTime();
      const mins = Math.floor(diffMs / 60000);
      if (mins < 1) ageStr = 'just now';
      else if (mins < 60) ageStr = `${mins}m ago`;
      else {
        const hrs = Math.floor(mins / 60);
        if (hrs < 24) ageStr = `${hrs}h ago`;
        else ageStr = `${Math.floor(hrs / 24)}d ago`;
      }
    }

    // Extract the meaningful part of the rule text
    const ruleText = i.rule || '';
    let displayRule = ruleText;
    if (ruleText.startsWith('When generating with ') && ruleText.endsWith(': none')) {
      // Skip trivial "none" adjustments — show kernel info instead
      displayRule = `Verified stable under ${i.applies_to?.error_category || 'general'} conditions`;
    }

    const entry = h('div', { class: 'rule-entry' },
      h('div', { class: 'rule-header' },
        h('span', { class: 'rule-label' }, displayRule),
        kernel ? h('span', { class: 'rule-kernel' }, kernel) : null
      ),
      h('div', { class: 'rule-body' },
        h('div', { class: 'rule-confidence-row' },
          h('div', { class: 'rule-conf-bar' }, h('div', { class: 'fill', style: `width: ${confPct}%;` })),
          h('span', { class: 'rule-conf-text' }, `${confPct}%`)
        ),
        h('div', { class: 'rule-meta-row' },
          h('span', { class: 'rule-confirm-badge' }, confirms + 'x'),
          ageStr ? h('span', { class: 'rule-age' }, ageStr) : null,
          errorCat ? h('span', { class: 'rule-error-tag' }, errorCat) : null
        )
      )
    );
    return entry;
  }

  // Render all insights into the rulebook container
  const rulebookContainer = document.getElementById('rulebook-container');
  if (rulebookContainer && apiInsights && apiInsights.length > 0) {
    apiInsights.forEach(i => rulebookContainer.append(renderRuleEntry(i)));
  } else if (rulebookContainer) {
    rulebookContainer.append(h('div', { class: 'empty-rulebook', style: 'text-align:center;padding:32px;color:var(--text-secondary);font-size:12px;' },
      h('div', { style: 'margin-bottom:4px;font-size:18px;' }, '📖'),
      'Run audits or consolidate memory to build rules.'
    ));
  }

  side.append(insightsCard);

  const tlCard = h('div', { class: 'card card-pad', 'data-accent': 'cyan' },
    h('div', { class: 'row between', style: 'margin-bottom: 10px;' },
      h('div', { class: 'display', style: 'font-size: 12px;' }, 'Timeline'),
      h('span', { class: 'label' }, (apiTimeline || []).length + ' events')
    ),
    h('div', { class: 'timeline' },
      ...(apiTimeline || []).slice(0, 8).map(e => h('div', { class: 'tl-event' },
        h('div', { class: 'tl-time' }, e.t),
        h('div', { class: 'tl-body' },
          h('div', { class: 'tl-type' }, e.type),
          h('div', { class: 'tl-desc' }, e.desc)
        )
      ))
    )
  );
  side.append(tlCard);

  layout.append(side);
  root.append(layout);
  return root;
};

/* ---------- SETTINGS VIEW ---------- */
window.VIEWS.settings = async () => {
  const root = h('div', { class: 'col gap-3' });

  // Fetch config from API
  const config = await apiGet('/api/config', {
    kimi_api: 'sk_k25_••••••••••••••••••••',
    nim_url: 'https://integrate.api.nvidia.com/v1',
    anthropic_api: 'sk_ant_••••••••••••',
    comfy_primary: 'localhost:8188',
    comfy_secondary: 'localhost:8189',
    flux_model: 'flux2-dev-nvfp4.safetensors',
    clip_model: 'mistral_3_small_flux2_bf16.safetensors',
    turbo_lora: 'Flux_2-Turbo-LoRA_comfyui.safetensors',
    prompt_banks: { Pose: 'hero wide\nextreme close-up\nover-the-shoulder\nlow-angle\ntracking shot\nportrait\nmacro detail\nprofile · side\nthree-quarter\noverhead' }
  });

  // Hermes Chat Panel
  const hermesPanel = h('div', { class: 'card card-pad', 'data-accent': 'purple' },
    h('div', { class: 'row between', style: 'margin-bottom: 14px;' },
      h('div', { class: 'col gap-1' },
        h('div', { class: 'display', style: 'font-size: 13px;' }, 'Hermes Command Center'),
        h('div', { class: 'label' }, 'Direct Neural Link · Profile: <span id="active-hermes-profile">live</span>')
      ),
      h('div', { class: 'row gap-2' },
          h('select', { id: 'hermes-profile-sel', style: 'background: transparent; color: inherit; border: 1px solid var(--border); padding: 2px 4px; font-size: 11px;' },
              ['live', 'character', 'script', 'product'].map(p => h('option', { value: p }, p.charAt(0).toUpperCase() + p.slice(1)))
          )
      )
    ),
    h('div', { class: 'chat-container', style: 'height: 300px; overflow-y: auto; margin-bottom: 12px; display: flex; flex-direction: column; gap: 8px;' },
        h('div', { id: 'hermes-chat-history', class: 'chat-history', style: 'display:flex; flex-direction:column; gap:8px;' }, h('div', { class: 'muted', style: 'font-size: 12px; text-align: center;' }, 'System Ready. Awaiting command...'))
    ),
    h('div', { class: 'row gap-2' },
        h('input', { id: 'hermes-chat-input', type: 'text', placeholder: 'Ask Hermes about configuration...', style: 'flex: 1; background: var(--bg-secondary); border: 1px solid var(--border); color: inherit; padding: 8px 12px; border-radius: 4px;' }),
        h('button', { class: 'btn btn-primary', id: 'hermes-send-btn' }, 'Send')
    )
  );

  // Length selector inside Command Center
  let selectedLength = 30;
  hermesPanel.append(h('div', { class: 'card setting-group length-selector-card' },
    h('div', { style: 'font-size:12px;margin-bottom:8px;' }, 'Render Duration'),
    h('div', { id: 'length-selector', class: 'length-buttons' },
      [
        { label: '15s', value: 15 },
        { label: '30s', value: 30 },
        { label: '60s', value: 60 },
        { label: '90s', value: 90 }
      ].map(l => h('button', {
        class: 'length-btn' + (l.value === selectedLength ? ' active' : ''),
        onclick: function() {
          $$('.length-btn').forEach(b => b.classList.remove('active'));
          this.classList.add('active');
          selectedLength = l.value;
          const disp = document.getElementById('current-length-display');
          if (disp) disp.textContent = 'Selected: ' + l.value + 's';
        }
      }, l.label))
    ),
    h('div', { id: 'current-length-display', style: 'font-size:11px;color:var(--text-secondary);margin-top:8px;font-family:"JetBrains Mono",monospace;' }, 'Selected: 30s')

  ));

  // Event Log section
  hermesPanel.append(h('div', { class: 'card setting-group', style: 'margin-top:12px;' },
    h('div', { class: 'row between', style: 'margin-bottom:8px;' },
      h('div', { style: 'font-size:12px;' }, 'Live Event Log'),
      h('button', { class: 'btn btn-sm', id: 'clear-event-log', style: 'font-size:10px;' }, 'Clear')
    ),
    h('div', { id: 'event-log', style: 'height:180px;overflow-y:auto;background:var(--bg,#0A0E14);border:1px solid var(--border,#2A3A4F);border-radius:4px;padding:8px;font-family:"JetBrains Mono",monospace;font-size:11px;display:flex;flex-direction:column;gap:2px;' })
  ));

  // Wire event log clear button
  setTimeout(() => {
    const clearBtn = document.getElementById('clear-event-log');
    if (clearBtn) clearBtn.onclick = () => {
      const log = document.getElementById('event-log');
      if (log) log.innerHTML = '';
    };
  }, 100);

  setTimeout(() => {
      const input = $('#hermes-chat-input');
      const btn = $('#hermes-send-btn');
      const history = $('#hermes-chat-history');
      const sel = $('#hermes-profile-sel');

      const appendMsg = (role, text) => {
          const msg = h('div', { class: `chat-msg ${role}`, style: 'padding: 6px 10px; border-radius: 4px; max-width: 85%; font-size: 13px;' },
              h('div', { class: 'msg-text' }, text)
          );
          if (role === 'user') msg.style.alignSelf = 'flex-end'; else msg.style.alignSelf = 'flex-start';
          if (role === 'user') msg.style.backgroundColor = 'var(--bg-secondary)';
          else msg.style.backgroundColor = 'rgba(150, 0, 255, 0.1)';
          history.append(msg);
          history.scrollTop = history.scrollHeight;
      };

      const send = async () => {
          const val = input.value.trim();
          if (!val) return;
          const profile = sel.value;
          $('#active-hermes-profile').textContent = profile;
          appendMsg('user', val);
          input.value = '';
          btn.disabled = true;
          btn.textContent = '...';
          try {
              // Create streaming response message
              const streamMsg = h('div', { class: 'chat-msg hermes', style: 'padding: 6px 10px; border-radius: 4px; max-width: 85%; font-size: 13px; background-color: rgba(150, 0, 255, 0.1);', align: 'flex-start' });
              const streamText = h('div', { class: 'msg-text' });
              streamMsg.append(streamText);
              history.append(streamMsg);
              history.scrollTop = history.scrollHeight;

              // Use fetch with streaming reader
              const response = await fetch('/api/hermes/chat', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ message: val, profile })
              });

              if (!response.ok) throw new Error(`HTTP ${response.status}`);

              const reader = response.body.getReader();
              const decoder = new TextDecoder();
              let buffer = '';
              let fullResponse = '';

              while (true) {
                  const { done, value } = await reader.read();
                  if (done) break;
                  buffer += decoder.decode(value, { stream: true });

                  // Parse SSE events from buffer
                  const lines = buffer.split('\n');
                  buffer = lines.pop() || '';

                  for (const line of lines) {
                      if (line.startsWith('data: ')) {
                          try {
                              const data = JSON.parse(line.slice(6));
                              if (data.type === 'chat_chunk') {
                                  fullResponse += data.content;
                                  streamText.textContent = fullResponse;
                                  history.scrollTop = history.scrollHeight;
                              } else if (data.type === 'chat_error') {
                                  streamText.textContent = 'Error: ' + data.error;
                              }
                          } catch (e) { /* ignore parse errors */ }
                      }
                  }
              }

              // If no streaming content, fallback to JSON response
              if (!fullResponse) {
                  try {
                      const data = JSON.parse(buffer);
                      if (data.response) streamText.textContent = data.response;
                  } catch (e) { /* ignore */ }
              }

          } catch (e) {
              appendMsg('error', `Error: ${e.message}`);
          } finally {
              btn.disabled = false;
              btn.textContent = 'Send';
          }
      };

      btn.onclick = send;
      input.onkeydown = (e) => { if (e.key === 'Enter') send(); };
  }, 50);

  const container = h('div', { class: 'settings-container' });

  // 1. API Keys Card
  container.append(h('div', { class: 'card setting-group', 'data-accent': 'cyan' },
    h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 4px;' }, 'API Keys'),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'Kimi API'),
      h('input', { class: 'input', type: 'password', value: config.kimi_api, id: 'kimi-api-key' }),
      h('button', { class: 'btn btn-sm', onclick: function() {
        const inp = $('#kimi-api-key');
        inp.type = inp.type === 'password' ? 'text' : 'password';
        this.textContent = inp.type === 'text' ? 'Hide' : 'Show';
      }}, 'Show')
    ),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'NVIDIA NIM'),
      h('input', { class: 'input', value: config.nim_url, id: 'nim-url' }),
      h('button', { class: 'btn btn-sm', onclick: async function() {
        const url = $('#nim-url').value;
        this.textContent = '...';
        try {
          const r = await fetch('/api/nim/test?url=' + encodeURIComponent(url));
          const d = await r.json();
          window.showToast(d.healthy ? 'NIM connected' : 'NIM unreachable', d.healthy ? 'success' : 'error');
        } catch(e) { window.showToast('NIM test failed', 'error'); }
        this.textContent = 'Test';
      }}, 'Test')
    ),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'Anthropic'),
      h('input', { class: 'input', type: 'password', value: config.anthropic_api, id: 'anthropic-api-key' }),
      h('button', { class: 'btn btn-sm', onclick: function() {
        const inp = $('#anthropic-api-key');
        inp.type = inp.type === 'password' ? 'text' : 'password';
        this.textContent = inp.type === 'text' ? 'Hide' : 'Show';
      }}, 'Show')
    ),
    h('button', { class: 'btn btn-ghost', style: 'margin-top:8px;', onclick: async function() {
      try {
        await apiPost('/api/config/save', {
          kimi_api: $('#kimi-api-key').value,
          nim_url: $('#nim-url').value,
          anthropic_api: $('#anthropic-api-key').value
        });
        window.showToast('API keys saved', 'success');
      } catch(e) { window.showToast('Save failed', 'error'); }
    }}, '✓ Save Keys')
  ));

  // 2. ComfyUI Hosts Card
  const pingHost = async (inputEl, btnEl) => {
    const url = 'http://' + inputEl.value;
    btnEl.textContent = '...';
    try {
      const r = await fetch('/api/spark/test?url=' + encodeURIComponent(url));
      const d = await r.json();
      const status = btnEl.closest('.setting-row').querySelector('.ping-status');
      if (d.healthy) {
        status.textContent = '● Online ' + (d.info?.latency_ms ? d.info.latency_ms + 'ms' : '');
        status.style.color = 'var(--green)';
      } else {
        status.textContent = '● Offline';
        status.style.color = 'var(--red)';
      }
    } catch(e) {
      const status = btnEl.closest('.setting-row').querySelector('.ping-status');
      status.textContent = '● Error';
      status.style.color = 'var(--red)';
    }
    btnEl.textContent = 'Ping';
  };

  container.append(h('div', { class: 'card setting-group', 'data-accent': 'green' },
    h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 4px;' }, 'ComfyUI Hosts'),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, h('span', { class: 'dot d-green', style: 'margin-right: 8px;' }), 'Primary'),
      h('input', { class: 'input', value: config.comfy_primary, id: 'comfy-primary' }),
      h('button', { class: 'btn btn-sm', onclick: function() { pingHost($('#comfy-primary'), this); }}, 'Ping'),
      h('span', { class: 'ping-status', style: 'font-size:11px; margin-left: 8px;' }, '')
    ),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, h('span', { class: 'dot d-dim', style: 'margin-right: 8px;' }), 'Secondary'),
      h('input', { class: 'input', value: config.comfy_secondary, id: 'comfy-secondary' }),
      h('button', { class: 'btn btn-sm', onclick: function() { pingHost($('#comfy-secondary'), this); }}, 'Ping'),
      h('span', { class: 'ping-status', style: 'font-size:11px; margin-left: 8px;' }, '')
    ),
    h('button', { class: 'btn btn-ghost', style: 'align-self: flex-start; margin-top: 4px;', onclick: () => window.showToast('Add host coming soon', 'info') }, '+ Add host'),
    h('button', { class: 'btn btn-ghost', style: 'margin-top:4px;', onclick: async function() {
      try {
        await apiPost('/api/config/save', {
          comfy_primary: $('#comfy-primary').value,
          comfy_secondary: $('#comfy-secondary').value
        });
        window.showToast('Hosts saved', 'success');
      } catch(e) { window.showToast('Save failed', 'error'); }
    }}, '✓ Save Hosts')
  ));

  // 3. Models & Backends Card
  container.append(h('div', { class: 'card setting-group', 'data-accent': 'magenta' },
    h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 4px;' }, 'Model Config'),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'FLUX2 Model'),
      h('input', { class: 'input', value: config.flux_model, id: 'flux-model' }),
      h('button', { class: 'btn btn-sm', onclick: () => window.showToast('Model picker coming soon', 'info') }, 'Pick')
    ),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'CLIP Model'),
      h('input', { class: 'input', value: config.clip_model, id: 'clip-model' }),
      h('button', { class: 'btn btn-sm', onclick: () => window.showToast('Model picker coming soon', 'info') }, 'Pick')
    ),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'Turbo LoRA'),
      h('input', { class: 'input', value: config.turbo_lora, id: 'turbo-lora' }),
      h('button', { class: 'btn btn-sm', onclick: () => window.showToast('Model picker coming soon', 'info') }, 'Pick')
    ),
    h('button', { class: 'btn btn-ghost', style: 'margin-top:8px;', onclick: async function() {
      try {
        await apiPost('/api/config/save', {
          flux_model: $('#flux-model').value,
          clip_model: $('#clip-model').value,
          turbo_lora: $('#turbo-lora').value
        });
        window.showToast('Model config saved', 'success');
      } catch(e) { window.showToast('Save failed', 'error'); }
    }}, '✓ Save Models')
  ));

  // 4. Prompt Banks Card
  container.append(h('div', { class: 'card setting-group', 'data-accent': 'amber' },
    h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 8px;' }, 'Prompt Banks'),
    h('div', { class: 'bank-tabs' },
      ['Pose','View','Lighting','Background','Extras'].map((name, i) => h('button', {
        class: 'bank-tab' + (i === 0 ? ' active' : ''),
        onclick: (e) => { $$('.bank-tab').forEach(t => t.classList.remove('active')); e.currentTarget.classList.add('active'); }
      }, name))
    ),
    h('textarea', { class: 'textarea', id: 'prompt-bank-text', style: 'min-height: 150px; margin-top: 8px;' }, config.prompt_banks?.Pose || 'hero wide\nextreme close-up\nover-the-shoulder\nlow-angle\ntracking shot\nportrait\nmacro detail\nprofile · side\nthree-quarter\noverhead'),
    h('button', { class: 'btn btn-ghost', style: 'margin-top:8px;', onclick: async function() {
      try {
        await apiPost('/api/config/save', {
          prompt_banks: { Pose: $('#prompt-bank-text').value }
        });
        window.showToast('Prompt bank saved', 'success');
      } catch(e) { window.showToast('Save failed', 'error'); }
    }}, '✓ Save Prompt Bank')
  ));

  root.append(hermesPanel, container);
  return root;
};

/* ---------- Memory Graph ---------- */
window.initMemoryGraph = async function() {
  const container = document.getElementById('graph-canvas');
  if (!container || typeof cytoscape === 'undefined') return;

  // Fetch graph data from API
  const apiGraph = await apiGet('/api/memory/graph', null);
  const GRAPH = apiGraph || {
    nodes: [
      { label: 'Session 001', type: 'session', color: '#FFBF00' },
      { label: 'Sienna render', type: 'attempt', color: '#00FFFF' },
      { label: 'Eye color rule', type: 'insight', color: '#BD00FF' },
      { label: 'Iris explicitness', type: 'concept', color: '#FF00FF' },
      { label: 'Pass · score 0.94', type: 'outcome', color: '#00FF41' },
      { label: 'Session 002', type: 'session', color: '#FFBF00' },
      { label: 'Elara render', type: 'attempt', color: '#00FFFF' },
      { label: 'Hair strand rule', type: 'insight', color: '#BD00FF' },
      { label: 'Strand detail', type: 'concept', color: '#FF00FF' },
      { label: 'Pass · score 0.91', type: 'outcome', color: '#00FF41' }
    ],
    edges: [
      { source: 'n0', target: 'n1' }, { source: 'n1', target: 'n2' },
      { source: 'n2', target: 'n3' }, { source: 'n1', target: 'n4' },
      { source: 'n5', target: 'n6' }, { source: 'n6', target: 'n7' },
      { source: 'n7', target: 'n8' }, { source: 'n6', target: 'n9' },
      { source: 'n0', target: 'n5' }
    ]
  };

  const elements = [
    ...GRAPH.nodes.map((n, i) => ({ data: { id: 'n'+i, label: n.label, type: n.type, color: n.color } })),
    ...GRAPH.edges.map((e, i) => ({ data: { id: 'e'+i, source: e.source, target: e.target } }))
  ];

  const cy = cytoscape({
    container, elements,
    style: [
      { selector: 'node', style: {
          'background-color': 'data(color)', 'label': 'data(label)',
          'color': '#E6EDF3', 'font-family': 'JetBrains Mono, monospace', 'font-size': 9,
          'text-margin-y': -8, 'text-valign': 'top', 'text-halign': 'center',
          'text-outline-color': '#0A0E14', 'text-outline-width': 2,
          'width': 28, 'height': 28, 'border-width': 2, 'border-color': 'data(color)',
          'border-opacity': 0.6, 'overlay-padding': 8
      }},
      { selector: 'node[type="session"]', style: { 'width': 40, 'height': 40, 'shape': 'round-hexagon' } },
      { selector: 'node[type="insight"]', style: { 'shape': 'round-diamond', 'width': 32, 'height': 32 } },
      { selector: 'node[type="concept"]', style: { 'shape': 'round-rectangle' } },
      { selector: 'node[type="outcome"]', style: { 'shape': 'ellipse' } },
      { selector: 'edge', style: {
          'width': 1, 'line-color': '#2A3A4F', 'target-arrow-color': '#2A3A4F',
          'target-arrow-shape': 'triangle', 'curve-style': 'bezier', 'opacity': 0.7
      }},
      { selector: '.dim', style: { 'opacity': 0.12 } }
    ],
    layout: { name: 'cose', padding: 80, animate: true, animationDuration: 600, idealEdgeLength: 110, nodeRepulsion: 8000 }
  });

  cy.on('mouseover', 'node', (evt) => evt.target.style({ 'border-width': 4, 'border-opacity': 1 }));
  cy.on('mouseout', 'node', (evt) => evt.target.style({ 'border-width': 2, 'border-opacity': 0.6 }));
  cy.on('tap', 'node', (evt) => {
    const connected = evt.target.neighborhood().union(evt.target);
    cy.elements().not(connected).addClass('dim');
    connected.removeClass('dim');
  });
  cy.on('tap', (evt) => { if (evt.target === cy) cy.elements().removeClass('dim'); });

  $$('.graph-toolbar [data-layout]').forEach(btn => {
    btn.addEventListener('click', () =>
      cy.layout({ name: btn.dataset.layout, padding: 60, animate: true, fit: true }).run()
    );
  });

  const search = document.getElementById('graph-search');
  if (search) {
    let to = null;
    search.addEventListener('input', () => {
      clearTimeout(to);
      to = setTimeout(() => {
        const q = search.value.trim().toLowerCase();
        if (!q) { cy.elements().removeClass('dim'); return; }
        const matching = cy.nodes().filter(n => (n.data('label') || '').toLowerCase().includes(q));
        cy.elements().addClass('dim');
        matching.union(matching.neighborhood()).removeClass('dim');
      }, 250);
    });
  }
  window.__cy = cy;
};

document.addEventListener('DOMContentLoaded', boot);

/* ---------- Character Management ---------- */
window.openAddCharacterModal = function() {
  let uploadedFile = null;
  let previewUrl = null;

  const modal = h('div', { id: 'modal-overlay', class: 'modal-overlay', style: 'position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9999;display:flex;align-items:center;justify-content:center;', onclick: (e) => { if (e.target === modal) modal.remove(); } },
    h('div', { class: 'modal-content', style: 'background:var(--bg-secondary,#0D1420);border:1px solid var(--border,#2A3A4F);border-radius:8px;padding:24px;width:90%;max-width:500px;', onclick: (e) => e.stopPropagation() },
      h('h3', { style: 'margin-bottom:12px;' }, 'Add New Character'),
      h('div', { class: 'form-group', style: 'margin-bottom:12px;' },
        h('label', { style: 'display:block;font-size:11px;color:var(--text-secondary);margin-bottom:4px;' }, 'Name'),
        h('input', { id: 'new-char-name', type: 'text', placeholder: 'e.g. Elara Vance', style: 'width:100%;background:var(--bg,#0A0E14);border:1px solid var(--border,#2A3A4F);color:var(--text,#E6EDF3);padding:8px 12px;border-radius:4px;font-family:"JetBrains Mono",monospace;box-sizing:border-box;' })
      ),
      h('div', { class: 'form-group', style: 'margin-bottom:12px;' },
        h('label', { style: 'display:block;font-size:11px;color:var(--text-secondary);margin-bottom:4px;' }, 'Description / Bio'),
        h('textarea', { id: 'new-char-desc', placeholder: 'Brief character description, appearance, role...', style: 'width:100%;min-height:80px;background:var(--bg,#0A0E14);border:1px solid var(--border,#2A3A4F);color:var(--text,#E6EDF3);padding:8px 12px;border-radius:4px;font-family:"JetBrains Mono",monospace;resize:vertical;box-sizing:border-box;' })
      ),
      h('div', { class: 'form-group', style: 'margin-bottom:16px;' },
        h('label', { style: 'display:block;font-size:11px;color:var(--text-secondary);margin-bottom:4px;' }, 'Anchor Image (optional)'),
        h('div', { id: 'anchor-drop-zone', style: 'border:2px dashed var(--border,#2A3A4F);border-radius:6px;padding:20px;text-align:center;cursor:pointer;transition:border-color 0.2s,background 0.2s;background:var(--bg,#0A0E14);',
          onclick: () => document.getElementById('anchor-file-input')?.click(),
          ondragover: (e) => { e.preventDefault(); e.currentTarget.style.borderColor = 'var(--cyan,#00D4FF)'; e.currentTarget.style.background = 'rgba(0,212,255,0.05)'; },
          ondragleave: (e) => { e.currentTarget.style.borderColor = 'var(--border,#2A3A4F)'; e.currentTarget.style.background = 'var(--bg,#0A0E14)'; },
          ondrop: (e) => {
            e.preventDefault();
            e.currentTarget.style.borderColor = 'var(--border,#2A3A4F)';
            e.currentTarget.style.background = 'var(--bg,#0A0E14)';
            const file = e.dataTransfer?.files?.[0];
            if (file) handleFile(file, e.currentTarget);
          }
        },
          h('div', { style: 'color:var(--text-secondary);font-size:12px;font-family:"JetBrains Mono",monospace;' }, 'Drag & drop image here, or click to browse'),
          h('div', { id: 'anchor-preview', style: 'margin-top:8px;' })
        ),
        h('input', { id: 'anchor-file-input', type: 'file', accept: 'image/*', style: 'display:none;',
          onchange: (e) => { const file = e.target?.files?.[0]; if (file) handleFile(file, e.target.parentElement.querySelector('#anchor-drop-zone')); }
        })
      ),
      h('div', { class: 'modal-actions', style: 'display:flex;gap:8px;justify-content:flex-end;' },
        h('button', { class: 'btn btn-ghost', onclick: () => { modal.remove(); if (previewUrl) URL.revokeObjectURL(previewUrl); } }, 'Cancel'),
        h('button', { class: 'btn btn-ghost', onclick: () => { submitCharacter(); if (previewUrl) URL.revokeObjectURL(previewUrl); } }, 'Submit'),
        h('button', { class: 'btn btn-primary', onclick: () => { window.generateAndRenderCharacter(); modal.remove(); if (previewUrl) URL.revokeObjectURL(previewUrl); } }, 'Generate + Render')
      )
    )
  );
  document.body.appendChild(modal);

  function handleFile(file, dropZone) {
    if (!file.type.startsWith('image/')) {
      window.showToast('Please upload an image file.', 'warning');
      return;
    }
    uploadedFile = file;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    const preview = document.getElementById('anchor-preview');
    if (preview) {
      preview.innerHTML = '';
      preview.append(h('img', { src: previewUrl, style: 'max-width:100%;max-height:200px;border-radius:4px;object-fit:contain;' }));
      preview.append(h('div', { style: 'color:var(--cyan,#00D4FF);font-size:11px;margin-top:4px;font-family:"JetBrains Mono",monospace;' }, file.name));
    }
    dropZone.style.borderColor = 'var(--cyan,#00D4FF)';
  }

  async function submitCharacter() {
    const name = document.getElementById('new-char-name')?.value;
    if (!name?.trim()) { window.showToast('Name is required.', 'warning'); return; }
    const desc = document.getElementById('new-char-desc')?.value || '';

    const formData = new FormData();
    formData.append('name', name.trim());
    formData.append('description', desc.trim());
    if (uploadedFile) formData.append('anchor_image', uploadedFile);

    try {
      const res = await fetch('/api/characters', {
        method: 'POST',
        body: formData
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(err.detail || 'Request failed');
      }
      const data = await res.json();
      modal.remove();
      window.showToast(`Character ${name} created`, 'success');
      switchTab('characters', false);
    } catch (err) {
      window.showToast('Failed: ' + err.message, 'error');
    }
  }
};

window.renderCharacterAnchor = async function(char) {
  const container = document.querySelector(`#char-anchor-${char.id}`);
  if (container) container.innerHTML = '<div class="loading-spinner"></div>';
  try {
    const res = await fetch('/api/characters/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: char.id, prompt: char.anchor_prompt })
    });
    if (!res.ok) throw new Error('Render failed');
    const data = await res.json();
    if (data.anchor_url && container) {
      container.innerHTML = '';
      container.append(h('img', {
        src: data.anchor_url,
        class: 'character-anchor-img',
        alt: String(char.id),
        style: 'width:100%;max-height:520px;object-fit:contain;'
      }));
    }
  } catch (err) {
    if (container) {
      container.innerHTML = '';
      container.append(h('div', { style: 'color:var(--error)' }, 'Render failed'));
    }
  }
};

window.generateAndRenderCharacter = async function() {
  const name = document.getElementById('new-char-name')?.value;
  const desc = document.getElementById('new-char-desc')?.value;
  if (!name || !desc) { window.showToast('Name and Description are required.', 'warning'); return; }
  try {
    const genRes = await fetch('/api/hermes/generate-character', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description: desc })
    });
    if (!genRes.ok) throw new Error('Character generation failed');
    const charData = await genRes.json();
    await window.renderCharacterAnchor(charData);
    document.getElementById('modal-overlay')?.remove();
    window.showToast(`Character ${name} generated`, 'success');
    switchTab('characters', false);
  } catch (err) {
    window.showToast('Process failed: ' + err.message, 'error');
  }
};

/* ---------- CSS animations (injected) ---------- */
(function injectStyles() {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes slideIn { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
    .row { display: flex; align-items: center; }
    .col { display: flex; flex-direction: column; }
    .gap-1 { gap: 4px; }
    .gap-2 { gap: 8px; }
    .gap-3 { gap: 12px; }
    .between { justify-content: space-between; }
    .wrap { flex-wrap: wrap; }
    .muted { color: var(--text-secondary, #8B949E); }
    .label { font-size: 11px; color: var(--text-secondary, #8B949E); }
    .display { font-size: 13px; font-weight: 600; color: var(--text, #E6EDF3); }
    .interactive { cursor: pointer; }
    .interactive:hover { opacity: 0.85; }
  `;
  document.head.appendChild(style);
})();
