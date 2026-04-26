/* Forge NPS — App shell, tabs, view rendering */

const $ = (s, p = document) => p.querySelector(s);
const $$ = (s, p = document) => [...p.querySelectorAll(s)];
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
    el.append(kid.nodeType ? kid : document.createTextNode(kid));
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

const TAB_ICONS = {
  home:       `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M3 9l7-6 7 6v8a1 1 0 0 1-1 1h-3v-5H7v5H4a1 1 0 0 1-1-1z"/></svg>`,
  characters: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="7" cy="7" r="3"/><path d="M2 17a5 5 0 0 1 10 0"/><circle cx="14" cy="7" r="2.5"/><path d="M13 13a4 4 0 0 1 5 4"/></svg>`,
  script:     `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="3" width="12" height="14" rx="1"/><path d="M7 7h6M7 10h6M7 13h4"/></svg>`,
  renders:    `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="6" height="6" rx="1"/><rect x="11" y="3" width="6" height="6" rx="1"/><rect x="3" y="11" width="6" height="6" rx="1"/><rect x="11" y="11" width="6" height="6" rx="1"/></svg>`,
  memory:     `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M7 4a3 3 0 0 0-3 3v6a3 3 0 0 0 3 3h6a3 3 0 0 0 3-3V7a3 3 0 0 0-3-3H7z"/><path d="M10 4v12M7 8h6M7 12h6"/></svg>`,
  settings:   `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="10" cy="10" r="3"/><path d="M10 2v2m0 12v2M2 10h2m12 0h2M4.5 4.5l1.4 1.4m8.2 8.2 1.4 1.4M4.5 15.5l1.4-1.4m8.2-8.2 1.4-1.4"/></svg>`,
};

/* ---------- Boot ---------- */
function boot() {
  if (typeof initSparkWidget === 'function') initSparkWidget();
  if (typeof initHermesPanel === 'function') initHermesPanel();
  window.navigate = switchTab;

  const brandMark = $('#brand-mark');
  if (brandMark && typeof logoSVG === 'function') brandMark.innerHTML = logoSVG();

  // Build sidebar rail nav (replaces inline-script version which may have crashed)
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

  const hash = (location.hash || '').replace(/^#\/?/, '');
  if (TABS.includes(hash)) activeTab = hash;
  else location.hash = '';
  window.addEventListener('hashchange', () => {
    const nh = (location.hash || '').replace(/^#\/?/, '');
    if (TABS.includes(nh) && nh !== activeTab) switchTab(nh, false);
  });
  switchTab(activeTab, false);
}

function setIntensity(level) {
  document.body.classList.remove('intensity-tasteful','intensity-full');
  if (level === 'tasteful') document.body.classList.add('intensity-tasteful');
  if (level === 'full') document.body.classList.add('intensity-full');
  $$('.intensity-pill button').forEach(b => b.classList.toggle('active', b.dataset.intensity === level));
}

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
      if (p < 1) requestAnimationFrame(tick);
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

async function apiAction(url, options = {}, onResult) {
  try {
    const r = await fetch(url, options);
    if (r.ok) { if (onResult) await onResult(r); return true; }
    console.error(`API Error: ${url}`, r.statusText);
  } catch (e) { console.error('Network error', e); }
  return false;
}

/* ======================================================================
   VIEWS — reset global (originally declared by inline script in index.html)
   ====================================================================== */
window.VIEWS = {};

window.VIEWS.home = () => {
  const root = h('div');

  // hero stats
  const hero = h('div', { class: 'hero-grid' },
    statCard({ label: 'Total Events',   value: 176, accent: 'cyan'    }),
    statCard({ label: 'Insights',       value: 12,  accent: 'purple'  }),
    statCard({ label: 'Success Rate',   value: 94,  accent: 'green',   suffix: '%' }),
    statCard({ label: 'Queue Depth',    value: 22,  accent: 'amber',   sub: h('span', {}, 'of 24 staged') }),
    statCard({ label: 'Active Sessions',value: 1,   accent: 'magenta', sub: h('span', {}, 'node-02 · 45GB VRAM') }),
    statCard({ label: 'Time Window',    value: 24,  accent: 'cyan',    suffix: 'h' })
  );
  root.append(hero);

  // body: recent renders + queue + actions + heartbeat
  const body = h('div', { class: 'home-body' });

  // left column
  const left = h('div', { class: 'col gap-3' });

  // recent renders card
  const recent = h('div', { class: 'card card-pad', 'data-accent': 'cyan' });
  recent.append(
    h('div', { class: 'row between', style: 'margin-bottom: 14px;' },
      h('div', { class: 'col gap-1' },
        h('div', { class: 'display', style: 'font-size: 13px;' }, 'Recent Renders'),
        h('div', { class: 'label' }, 'Last 8 · session node-02')
      ),
      h('div', { class: 'row gap-2' },
        h('button', { class: 'chip active' }, 'All'),
        h('button', { class: 'chip' }, 'Elara'),
        h('button', { class: 'chip' }, 'Orin'),
        h('button', { class: 'chip' }, 'Vex')
      )
    )
  );
  const strip = h('div', { class: 'recent-strip' });
  const accents = ['cyan','magenta','amber','green'];
  for (let i = 0; i < 8; i++) {
    const c = accents[i % accents.length];
    strip.append(h('div', { class: 'thumb', html: frameSVG(`VAR_${String(14 - i).padStart(3,'0')}`, i, c) + `
      <div class="meta-overlay">
        <div style="color: var(--cyan); letter-spacing: 0.14em;">VAR_${String(14 - i).padStart(3,'0')}</div>
        <div class="muted">seed ${849271 - i*7} · score 0.9${(3 + i % 6)}</div>
      </div>`
    }));
  }
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
        h('div', { style: 'font-size: 14px; color: var(--amber); letter-spacing: 0.1em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;' }, 'VAR_014 · cockpit-cu · Elara'),
        h('div', { class: 'eta' }, 'ETA 3m 12s · 8 of 24 complete')
      ),
      h('div', { class: 'row gap-2', style: 'flex-shrink: 0;' },
        h('button', { class: 'icon-btn', title: 'Pause' }, '⏸'),
        h('button', { class: 'icon-btn', title: 'Skip' }, '⏭')
      )
    ),
    h('div', { class: 'progress' }, h('div', { class: 'fill', style: 'width: 33%;' }))
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
      h('button', { class: 'quick-action' },
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

  // mini-timeline preview
  const feed = h('div', { class: 'card card-pad', 'data-accent': 'purple' },
    h('div', { class: 'row between', style: 'margin-bottom: 10px;' },
      h('div', { class: 'display', style: 'font-size: 13px;' }, 'Live Feed'),
      h('div', { class: 'ticker' }, 'STREAMING · 24.ms')
    ),
    h('div', { class: 'timeline' },
      ...TIMELINE.slice(0, 5).map(e => h('div', { class: 'tl-event' },
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


window.VIEWS.characters = () => {
  const root = h('div');
  const char = CHARACTERS.find(c => c.id === activeCharId) || CHARACTERS[0];

  // selector
  const selector = h('div', { class: 'char-selector' });
  CHARACTERS.forEach(c => {
    selector.append(h('div', {
      class: 'card char-pick interactive' + (c.id === char.id ? ' active' : ''),
      'data-accent': c.accent,
      onclick: () => { activeCharId = c.id; switchTab('characters', false); }
    },
      h('div', { class: 'portrait', html: portraitSVG(c, 56) }),
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
  selector.append(h('div', { class: 'card char-pick interactive', style: 'border-style: dashed; justify-content: center;' },
    h('div', { class: 'col gap-1', style: 'align-items: center; text-align: center;' },
      h('div', { style: 'color: var(--text-secondary); font-size: 20px;' }, '+'),
      h('div', { class: 'label' }, 'Add Character')
    )
  ));
  root.append(selector);

  // hero: anchor + DNA editor
  const hero = h('div', { class: 'char-hero' });

  const anchor = h('div', { class: 'card anchor-card', 'data-accent': char.accent });
  anchor.append(
    h('div', { class: 'anchor-img', html: portraitSVG(char, 520) }),
    h('div', { class: 'anchor-footer' },
      h('div', { class: 'consistency' },
        h('div', { class: 'row between' },
          h('span', { class: 'label' }, 'Consistency Score'),
          h('span', { class: 'score' }, char.score + '%')
        ),
        h('div', { class: 'progress mono green' }, h('div', { class: 'fill', style: `width: ${char.score}%;` }))
      ),
      h('button', { class: 'btn btn-primary' }, '↻ Regenerate Anchor')
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
<span class="k">description:</span> <span class="v">"${char.dna.hair}"</span>

<span class="h">## EYES</span>
<span class="k">description:</span> <span class="v">"${char.dna.eyes}"</span>

<span class="h">## BUILD</span>
<span class="k">description:</span> <span class="v">"${char.dna.build}"</span>

<span class="h">## CLOTHING</span>
<span class="k">description:</span> <span class="v">"${char.dna.clothing}"</span>

<span class="h">## SIGNATURE</span>
<span class="k">description:</span> <span class="v">"${char.dna.signature}"</span>

<span class="h">## PALETTE</span>
<span class="k">hex:</span> <span class="v">${char.dna.palette.map(p=>`"${p}"`).join(', ')}</span>` })
  );
  const preview = h('div', { class: 'dna-pane dna-preview' },
    h('h3', {}, 'Rendered preview'),
    h('h4', {}, 'Hair'),       h('p', {}, char.dna.hair),
    h('h4', {}, 'Eyes'),       h('p', {}, char.dna.eyes),
    h('h4', {}, 'Build'),      h('p', {}, char.dna.build),
    h('h4', {}, 'Clothing'),   h('p', {}, char.dna.clothing),
    h('h4', {}, 'Signature'),  h('p', {}, char.dna.signature),
    h('h4', {}, 'Palette'),
    h('div', { class: 'row gap-2', style: 'margin-top: 4px;' },
      ...char.dna.palette.map(c => h('div', { style: `width: 32px; height: 32px; border-radius: 4px; border: 1px solid var(--border); background: ${c};`, title: c }))
    )
  );
  dnaBody.append(edit, preview);
  dna.append(dnaBody,
    h('div', { class: 'row between', style: 'padding: 12px 18px; border-top: 1px solid var(--border);' },
      h('div', { class: 'label' }, 'last saved 2m ago · 14 revisions'),
      h('div', { class: 'row gap-2' },
        h('button', { class: 'btn btn-ghost' }, 'Export'),
        h('button', { class: 'btn btn-primary' }, '✓ Save DNA')
      )
    )
  );
  hero.append(dna);
  root.append(hero);

  // variation gallery
  root.append(h('div', { style: 'height: 16px;' }));
  root.append(sectionHead('Variation Gallery', `${char.name} · 24 frames`));

  const chips = h('div', { class: 'filter-chips', style: 'margin-bottom: 12px;' },
    h('button', { class: 'chip active' }, 'All · 24'),
    h('button', { class: 'chip' }, 'Pose · 8'),
    h('button', { class: 'chip' }, 'Lighting · 6'),
    h('button', { class: 'chip' }, 'Background · 4'),
    h('button', { class: 'chip' }, 'Best Only · 11')
  );
  root.append(chips);

  const gal = h('div', { class: 'var-gallery' });
  for (let i = 0; i < 12; i++) {
    gal.append(h('div', { class: 'thumb', html: frameSVG(`${char.name}_V${String(i+1).padStart(2,'0')}`, i, char.accent) + `
      <div class="meta-overlay">
        <div style="color: var(--${char.accent}); letter-spacing: 0.14em;">V${String(i+1).padStart(2,'0')} · score 0.9${(i%7)+2}</div>
        <div class="muted" style="font-size: 9px;">pose ${i+1} · amber key · seed ${849271+i*3}</div>
      </div>` }));
  }
  root.append(gal);

  return root;
};


window.VIEWS.script = async () => {
  const root = h('div');

  // Fetch available scripts from disk
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

  // Fetch shots from API
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
                h('button', { class: 'btn btn-sm' }, 'Edit prompt'),
                h('button', { class: 'btn btn-sm btn-primary' }, 'Dispatch to Spark'),
                h('button', {
                  class: 'btn btn-sm btn-ghost',
                  onclick: (e) => { e.stopPropagation(); navigator.clipboard.writeText(String(s.seed)); }
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
    } catch (e) {
      reparseBtn.textContent = '✗ Error';
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


window.VIEWS.renders = async () => {
  const root = h('div', { class: 'renders-shell' });

  const bar = h('div', { class: 'renders-toolbar' },
    h('div', { class: 'field' },
      h('span', { class: 'label' }, 'Workflow'),
      h('select', { class: 'select' },
        h('option', {}, 'FLUX2 NVFP4 Turbo'),
        h('option', {}, 'FLUX.1 Dev'),
        h('option', {}, 'Z-Image Turbo')
      )
    ),
    h('div', { class: 'field' },
      h('span', { class: 'label' }, 'Count'),
      h('input', { class: 'input', type: 'number', value: 24, min: 1, max: 50, style: 'width: 70px;' })
    ),
    h('div', { class: 'field' },
      h('span', { class: 'label' }, 'Seed'),
      h('input', { class: 'input', value: '849271', style: 'width: 100px;' })
    ),
    h('button', { class: 'btn btn-primary' }, '▶  Start Batch'),
    h('button', { class: 'btn btn-danger' }, 'Clear Queue'),
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

  // Logic for Vision Audit Batch Button
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

          // Find matching tile in the grid by finding the img whose src contains the filename
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
            const badge = targetTile.querySelector('.renders-badge');
            if (badge) {
              badge.textContent = `${result.status} · ${result.score}`;
              badge.className = `renders-badge ${result.status === 'FAIL' ? 'fail' : ''}`;
            }
          }
        } catch (e) {
          console.error('Error parsing stream line:', e, line);
        }
      }
    }
  } catch (err) {
    console.error('Vision Audit Batch Error:', err);
    alert('Audit failed: ' + err.message);
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

  // Update count label
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
        const isFail = r.status === 'FAIL';
        const tile = h('div', { class: 'renders-tile', title: r.prompt });
        const img = h('img', { src: r.src, loading: 'lazy', alt: r.prompt });
        const badge = h('div', { class: 'renders-badge' + (isFail ? ' fail' : '') },
          r.status + (r.score ? ` · ${r.score}` : '')
        );
        tile.append(img, badge);
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

/* ---------- MEMORY ---------- */
window.VIEWS.memory = () => {
  const root = h('div');

  // hero stats
  const hero = h('div', { class: 'hero-grid' },
    statCard({ label: 'Events',      value: 176, accent: 'cyan' }),
    statCard({ label: 'Insights',    value: 12,  accent: 'purple' }),
    statCard({ label: 'Concepts',    value: 18,  accent: 'magenta' }),
    statCard({ label: 'Confidence',  value: 89,  accent: 'green',  suffix: '%' }),
    statCard({ label: 'Audits',      value: 42,  accent: 'amber' }),
    statCard({ label: 'Sessions',    value: 3,   accent: 'amber' })
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

  // side: insights + timeline
  const side = h('div', { class: 'mem-side' });
  const insightsCard = h('div', { class: 'card card-pad', 'data-accent': 'purple' },
    h('div', { class: 'row between', style: 'margin-bottom: 12px;' },
      h('div', { class: 'display', style: 'font-size: 12px;' }, 'Semantic Insights'),
      h('span', { class: 'badge b-purple' }, INSIGHTS.length + ' RULES')
    ),
    h('div', { class: 'insights' },
      ...INSIGHTS.map(i => h('div', { class: 'insight' },
        h('div', { class: 'rule' }, i.rule),
        h('div', { class: 'confidence-bar' }, h('div', { class: 'fill', style: `width: ${i.confidence * 100}%;` })),
        h('div', { class: 'meta' },
          h('span', {}, `conf ${Math.round(i.confidence * 100)}%  ·  ${i.confirms} confirms`),
          h('span', {}, i.age + ' ago')
        )
      ))
    )
  );
  side.append(insightsCard);

  const tlCard = h('div', { class: 'card card-pad', 'data-accent': 'cyan' },
    h('div', { class: 'row between', style: 'margin-bottom: 10px;' },
      h('div', { class: 'display', style: 'font-size: 12px;' }, 'Timeline'),
      h('span', { class: 'label' }, 'last 8')
    ),
    h('div', { class: 'timeline' },
      ...TIMELINE.map(e => h('div', { class: 'tl-event' },
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

/* ---------- SETTINGS ---------- */
window.VIEWS.settings = async () => {
  const root = h('div', { class: 'col gap-3' });

  // Hermes Chat Panel
  const hermesPanel = h('div', { class: 'card card-pad', 'data-accent': 'purple' },
    h('div', { class: 'row between', style: 'margin-bottom: 14px;' },
      h('div', { class: 'col gap-1' },
        h('div', { class: 'display', style: 'font-size: 13px;' }, 'Hermes Command Center'),
        h('div', { class: 'label' }, 'Direct Neural Link · Profile: <span id="active-hermes-profile">live</span>')
      ),
      h('div', { class: 'row gap-2' },
          h('select', { id: 'hermes-profile-sel', style: 'background: transparent; color: inherit; border: 1px solid var(--border); padding: 2px 4px; font-size: 11px;' },
              ['live', 'character', 'script', 'product'].map(p => h('option', { value: p, text: p.charAt(0).toUpperCase() + p.slice(1) }))
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

  // Initialize Hermes Chat logic
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

          try {
              const r = await fetch('/api/hermes/profile/chat', {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ message: val, profile })
              });
              if (!r.ok) throw new Error(await r.text());
              const data = await r.json();
              appendMsg('hermes', data.response);
          } catch (e) {
              appendMsg('error', `Error: ${e.message}`);
          }
      };

      btn.onclick = send;
      input.onkeydown = (e) => { if (e.key === 'Enter') send(); };
  }, 50);

  // Single column of cards - no sidebar sub-nav
  const container = h('div', { class: 'settings-container' });
  
  // 1. API Keys Card
  container.append(h('div', { class: 'card setting-group', 'data-accent': 'cyan' },
    h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 4px;' }, 'API Keys'),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'Kimi API'),
      h('input', { class: 'input', type: 'password', value: 'sk_k25_••••••••••••••••••••' }),
      h('button', { class: 'btn btn-sm' }, 'Show')
    ),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'NVIDIA NIM'),
      h('input', { class: 'input', value: 'https://integrate.api.nvidia.com/v1' }),
      h('button', { class: 'btn btn-sm' }, 'Test')
    ),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'Anthropic'),
      h('input', { class: 'input', type: 'password', value: 'sk_ant_••••••••••••' }),
      h('button', { class: 'btn btn-sm' }, 'Show')
    )
  ));

  // 2. ComfyUI Hosts Card
  container.append(h('div', { class: 'card setting-group', 'data-accent': 'green' },
    h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 4px;' }, 'ComfyUI Hosts'),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, h('span', { class: 'dot d-green', style: 'margin-right: 8px;' }), 'Primary'),
      h('input', { class: 'input', value: 'localhost:8188' }),
      h('button', { 
        class: 'btn btn-sm', 
        onclick: async function() {
          const input = this.closest('.setting-row').querySelector('input');
          const status = this.closest('.setting-row').querySelector('.ping-status');
          const url = 'http://' + input.value;
          this.textContent = '...';
          try {
            const r = await fetch('/api/spark/test?url=' + encodeURIComponent(url));
            const d = await r.json();
            if (d.healthy) {
              status.textContent = '● Online ' + (d.info?.latency_ms ? d.info.latency_ms + 'ms' : '');
              status.style.color = 'var(--green)';
            } else {
              status.textContent = '● Offline';
              status.style.color = 'var(--red)';
            }
          } catch(e) { 
            status.textContent = '● Error'; 
            status.style.color = 'var(--red)'; 
          }
          this.textContent = 'Ping';
        }
      }, 'Ping'),
      h('span', { class: 'ping-status', style: 'font-size:11px; margin-left: 8px;' }, '')
    ),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, h('span', { class: 'dot d-dim', style: 'margin-right: 8px;' }), 'Secondary'),
      h('input', { class: 'input', value: 'localhost:8189' }),
      h('button', { 
        class: 'btn btn-sm', 
        onclick: async function() {
          const input = this.closest('.setting-row').querySelector('input');
          const status = this.closest('.setting-row').querySelector('.ping-status');
          const url = 'http://' + input.value;
          this.textContent = '...';
          try {
            const r = await fetch('/api/spark/test?url=' + encodeURIComponent(url));
            const d = await r.json();
            if (d.healthy) {
              status.textContent = '● Online ' + (d.info?.latency_ms ? d.info.latency_ms + 'ms' : '');
              status.style.color = 'var(--green)';
            } else {
              status.textContent = '● Offline';
              status.style.color = 'var(--red)';
            }
          } catch(e) { 
            status.textContent = '● Error'; 
            status.style.color = 'var(--red)'; 
          }
          this.textContent = 'Ping';
        }
      }, 'Ping'),
      h('span', { class: 'ping-status', style: 'font-size:11px; margin-left: 8px;' }, '')
    ),
    h('button', { class: 'btn btn-ghost', style: 'align-self: flex-start; margin-top: 4px;' }, '+ Add host')
  ));

  // 3. Models & Backends Card
  container.append(h('div', { class: 'card setting-group', 'data-accent': 'magenta' },
    h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 4px;' }, 'Model Config'),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'FLUX2 Model'),
      h('input', { class: 'input', value: 'flux2-dev-nvfp4.safetensors' }),
      h('button', { class: 'btn btn-sm' }, 'Pick')
    ),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'CLIP Model'),
      h('input', { class: 'input', value: 'mistral_3_small_flux2_bf16.safetensors' }),
      h('button', { class: 'btn btn-sm' }, 'Pick')
    ),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'Turbo LoRA'),
      h('input', { class: 'input', value: 'Flux_2-Turbo-LoRA_comfyui.safetensors' }),
      h('button', { class: 'btn btn-sm' }, 'Pick')
    )
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
    h('textarea', { class: 'textarea', style: 'min-height: 150px; margin-top: 8px;' }, 'hero wide\nextreme close-up\nover-the-shoulder\nlow-angle\ntracking shot\nportrait\nmacro detail\nprofile · side\nthree-quarter\noverhead')
  ));

  root.append(hermesPanel, container);
  return root;
};

function initMemoryGraph() {
  const container = document.getElementById('graph-canvas');
  if (!container || typeof cytoscape === 'undefined') return;

  const GRAPH = {
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
}

document.addEventListener('DOMContentLoaded', boot);

/* ---------- Character Management ---------- */

window.openAddCharacterModal = function() {
  const modal = h('div', { id: 'modal-overlay', class: 'modal-overlay' },
    h('div', { class: 'modal-content' },
      h('h3', {}, 'Add New Character'),
      h('div', { class: 'form-group' },
        h('label', {}, 'Name'),
        h('input', { id: 'new-char-name', type: 'text', placeholder: 'e.g. Elara Vance' })
      ),
      h('div', { class: 'form-group' },
        h('label', {}, 'Description/Bio'),
        h('textarea', { id: 'new-char-desc', placeholder: 'Brief backstory...' })
      ),
      h('div', { class: 'modal-actions' },
        h('button', { class: 'btn btn-ghost', onclick: () => document.getElementById('modal-overlay').remove() }, 'Cancel'),
        h('button', { class: 'btn btn-primary', onclick: () => window.generateAndRenderCharacter() }, 'Generate + Render')
      )
    )
  );
  document.body.appendChild(modal);
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
      container.innerHTML = `<img src="${data.anchor_url}" class="character-anchor-img" alt="${char.id}">`;
    }
  } catch (err) {
    if (container) container.innerHTML = '<div style="color:var(--error)">Render failed</div>';
  }
};

window.generateAndRenderCharacter = async function() {
  const name = document.getElementById('new-char-name')?.value;
  const desc = document.getElementById('new-char-desc')?.value;
  if (!name || !desc) { alert('Name and Description are required.'); return; }
  try {
    const genRes = await fetch('/api/hermes/generate-character', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description: desc })
    });
    if (!genRes.ok) throw new Error('Character generation failed');
    const charData = await genRes.json();
    await window.renderCharacterAnchor(charData);
    document.getElementById('modal-overlay')?.remove();
  } catch (err) {
    alert('Process failed: ' + err.message);
  }
};
