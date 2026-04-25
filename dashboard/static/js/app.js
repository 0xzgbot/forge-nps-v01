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

const TABS = ['home','characters','script','products','renders','memory','settings'];
const TAB_LABELS = {
  home: 'Home', characters: 'Characters', script: 'Script',
  products: 'Products', renders: 'Renders', memory: 'Memory', settings: 'Settings'
};

let activeTab = 'home';
let activeCharId = 'elara';
let expandedShot = null;

/* ---------- Boot ---------- */
function boot() {
  initSparkSocket();
  // Brand
  $('#brand-mark').innerHTML = logoSVG();
  // Tabs
  const tabsEl = $('#tabs');
  TABS.forEach(t => {
    tabsEl.append(h('button', {
      class: 'tab' + (t === activeTab ? ' active' : ''),
      'data-tab': t,
      onclick: () => switchTab(t)
    }, TAB_LABELS[t]));
  });
  // Intensity pill
  $$('.intensity-pill button').forEach(b => {
    b.addEventListener('click', () => setIntensity(b.dataset.intensity));
  });
  // Hash routing
  const hash = (location.hash || '').replace(/^#\/?/, '');
  if (TABS.includes(hash)) activeTab = hash;
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

function switchTab(name, updateHash = true) {
  activeTab = name;
  if (updateHash) location.hash = '#/' + name;
  $$('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  const view = $('#view');
  view.innerHTML = '';
  const render = VIEWS[name] || VIEWS.home;
  view.append(render());
  view.style.animation = 'none';
  // force reflow for re-anim
  void view.offsetWidth;
  view.style.animation = '';
  animateStatCounts();
  if (name === 'memory') setTimeout(initMemoryGraph, 30);
}

function animateStatCounts() {
  $$('[data-countup]').forEach(el => {
    const target = parseFloat(el.dataset.countup);
    const isPct = el.dataset.suffix === '%';
    const decimals = el.dataset.decimals ? +el.dataset.decimals : 0;
    const dur = 700;
    const start = performance.now();
    const ease = t => 1 - Math.pow(1-t, 3);
    function tick(now) {
      const p = Math.min(1, (now - start) / dur);
      const v = target * ease(p);
      el.textContent = v.toFixed(decimals) + (isPct ? '%' : '');
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

/* ======================================================================
   VIEWS
   ====================================================================== */


const VIEWS = {};


VIEWS.home = async () => {
  const root = h('div');

  // 3.1 Fetch Stats
  let stats = { total: 0, insights: 0, success: 0, queue: 0, sessions: 0, window: 0 };
  try {
    const r = await fetch('/api/memory/stats');
    if (r.ok) stats = await r.json();
  } catch(e) { console.error("Stats fetch failed", e); }

  // Hero Stats
  const hero = h('div', { class: 'hero-grid' },
    statCard({ label: 'Total Events',   value: stats.total, accent: 'cyan' }),
    statCard({ label: 'Insights',       value: stats.insights, accent: 'purple' }),
    statCard({ label: 'Success Rate',   value: stats.success, accent: 'green', suffix: '%' }),
    statCard({ label: 'Queue Depth',    value: stats.queue, accent: 'amber', sub: h('span', {}, 'staged') }),
    statCard({ label: 'Active Sessions',value: stats.sessions, accent: 'magenta' }),
    statCard({ label: 'Time Window',    value: stats.window, accent: 'cyan', suffix: 'h' })
  );
  root.append(hero);

  const body = h('div', { class: 'home-body' });
  const left = h('div', { class: 'col gap-3' });

  // 3.2 Recent Renders (Real Images)
  const recent = h('div', { class: 'card card-pad', 'data-accent': 'cyan' });
  recent.append(h('div', { class: 'row between', style: 'margin-bottom: 14px;' },
    h('div', { class: 'col gap-1' }, h('div', { class: 'display', style: 'font-size: 13px;' }, 'Recent Renders')),
    h('div', { class: 'row gap-2' }, h('button', { class: 'chip active' }, 'All'))
  ));

  const strip = h('div', { class: 'recent-strip' });
  try {
      const r = await fetch('/api/renders');
      if (r.ok) {
          const renders = await r.json();
          renders.slice(0, 8).forEach((rd, i) => {
              strip.append(h('div', { class: 'thumb' }, 
                  h('img', { 
                      src: rd.url, 
                      style: 'width:100%; height:100%; object-fit:cover; border-radius:4px;',
                      onerror: (e) => e.target.src = '/static/img/placeholder.png'
                  }),
                  h('div', { class: 'meta-overlay' },
                      h('div', { style: 'color: var(--cyan); font-size: 10px;' }, rd.name),
                      h('div', { class: 'muted', style: 'font-size: 8px;' }, `seed ${rd.seed || 0}`)
                  )
              ));
          });
      } else { strip.textContent = "No renders found."; }
  } catch(e) { strip.textContent = "Failed to load renders."; }
  recent.append(strip);
  left.append(recent);

  // 3.3 Campaign Queue (WebSocket wired in initSparkSocket)
  const queue = h('div', { class: 'card card-pad queue-panel', 'data-accent': 'amber' },
    h('div', { class: 'row between' },
      h('div', { class: 'col gap-1' },
        h('div', { class: 'display', style: 'font-size: 13px;' }, 'Live Queue'),
        h('div', { class: 'label' }, 'Spark · node-02')
      ),
      h('div', { class: 'heartbeat' }, ...Array.from({ length: 8 }, () => h('div', { class: 'bar' })))
    ),
    h('div', { class: 'current' },
      h('div', { class: 'col gap-1', style: 'min-width: 0; flex: 1;' },
        h('div', { class: 'job-name', style: 'font-size: 14px; color: var(--amber); letter-spacing: 0.1em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;' }, 'Waiting...'),
        h('div', { class: 'eta' }, '--')
      ),
      h('div', { class: 'row gap-2', style: 'flex-shrink: 0;' }, h('button', { class: 'icon-btn' }, '⏸'), h('button', { class: 'icon-btn' }, '⏭'))
    ),
    h('div', { class: 'progress' }, h('div', { class: 'fill', style: 'width: 0%;' }))
  );
  left.append(queue);

  const right = h('div', { class: 'col gap-3' });
  // Quick Actions (unchanged but re-added to ensure context)
  const actionsCard = h('div', { class: 'card card-pad', 'data-accent': 'cyan' },
    h('div', { class: 'display', style: 'font-size: 13px; margin-bottom: 14px;' }, 'Quick Actions'),
    h('div', { class: 'quick-actions' },
      h('button', { class: 'quick-action', onclick: () => window.startBatch() }, h('div', { class: 'title', style: 'color: var(--green);' }, '▶ Start Batch'), h('div', { class: 'desc' }, 'Dispatch 24 renders to Spark')),
      h('button', { class: 'quick-action', onclick: () => switchTab('characters') }, h('div', { class: 'title', style: 'color: var(--magenta);' }, '◉ Review Anchors'), h('div', { class: 'desc' }, 'Check character DNA integrity')),
      h('button', { class: 'quick-action', onclick: () => switchTab('memory') }, h('div', { class: 'title', style: 'color: var(--purple);' }, '⎈ Run Memory Audit'), h('div', { class: 'desc' }, 'Consolidate episodic → semantic'))
    )
  );
  right.append(actionsCard);

  body.append(left, right);
  root.append(body);
  return root;
};



VIEWS.characters = async () => {
  const root = h('div');
  const char = CHARACTERS.find(c => c.id === activeCharId) || CHARACTERS[0];

  // Selector (unchanged logic but using h for clean code)
  const selector = h('div', { class: 'char-selector' });
  CHARACTERS.forEach(c => {
    selector.append(h('div', {
      class: 'card char-pick interactive' + (c.id === char.id ? ' active' : ''),
      'data-accent': c.accent,
      onclick: () => { activeCharId = c.id; switchTab('characters', false); }
    },
      h('div', { class: 'portrait', html: portraitSVG(c, 56) }),
      h('div', { class: 'col gap-1' }, h('div', { class: 'name' }, c.name), h('div', { class: 'role' }, c.role)),
      h('div', { style: 'margin-left: auto;' }, h('span', { class: `dot d-${c.score >= 90 ? 'green' : 'amber'}` }))
    ));
  });
  selector.append(h('div', { class: 'card char-pick interactive', style: 'border-style: dashed; justify-content: center;' },
    h('div', { class: 'col gap-1', style: 'align-items: center; text-align: center;' }, h('div', { style: 'color: var(--text-secondary); font-size: 20px;' }, '+'), h('div', { class: 'label' }, 'Add Character'))
  ));
  root.append(selector);

  // Hero (3.4 Anchor image with real GET)
  const hero = h('div', { class: 'char-hero' });
  const anchor = h('div', { class: 'card anchor-card', 'data-accent': char.accent });
  
  const imgEl = h('img', { 
    id: `anchor-img-${char.id}`,
    class: 'anchor-img-real',
    style: 'width:100%; height:100%; object-fit:cover; border-radius:4px;',
    src: `/static/img/placeholder-char.png` // fallback
  });

  // Attempt to load real image immediately
  fetch(`/api/characters/anchor/${char.id}`)
    .then(r => r.ok ? r.blob().then(blob => URL.createObjectURL(blob)) : Promise.reject())
    .then(url => imgEl.src = url)
    .catch(() => { imgEl.src = `/static/img/placeholder-char.png`; });

  anchor.append(
    imgEl,
    h('div', { class: 'anchor-footer' },
      h('div', { class: 'consistency' }, 
        h('div', { class: 'row between' }, h('span', { class: 'label' }, 'Consistency Score'), h('span', { class: 'score' }, char.score + '%')),
        h('div', { class: 'progress mono green' }, h('div', { class: 'fill', style: `width: ${char.score}%;` }))
      ),
      h('button', { class: 'btn btn-primary', onclick: () => window.renderCharacterAnchor(char) }, '↻ Regenerate Anchor')
    )
  );
  hero.append(anchor);

  // DNA Editor (kept from original)
  const dna = h('div', { class: 'card dna-editor', 'data-accent': 'magenta' });
  const dnaBody = h('div', { class: 'dna-body' });
  const edit = h('div', { class: 'dna-pane' });
  edit.append(h('h3', {}, 'Character DNA · markdown source'), h('div', { class: 'dna-md', html: `
<span class="h"># ${char.name}</span>
<span class="c"># ${char.role}</span>
<span class="h">## HAIR</span><span class="k">description:</span> <span class="v">"${char.dna.hair}"</span>
<span class="h">## EYES</span><span class="k">description:</span> <span class="v">"${char.dna.eyes}"</span>
<span class="h">## BUILD</span><span class="k">description:</span> <span class="v">"${char.dna.build}"</span>
<span class="h">## CLOTHING</span><span class="k">description:</span> <span class="v">"${char.dna.clothing}"</span>
<span class="h">## SIGNATURE</span><span class="k">description:</span> <span class="v">"${char.dna.signature}"</span>
<span class="h">## PALETTE</span><span class="k">hex:</span> <span class="v">${char.dna.palette.map(p=>`"${p}"`).join(', ')}</span>` }));

  const preview = h('div', { class: 'dna-pane dna-preview' },
    h('h3', {}, 'Rendered preview'),
    h('h4', {}, 'Hair'), h('p', {}, char.dna.hair),
    h('h4', {}, 'Eyes'), h('p', {}, char.dna.eyes),
    h('h4', {}, 'Build'), h('p', {}, char.dna.build),
    h('h4', {}, 'Clothing'), h('p', {}, char.dna.clothing),
    h('h4', {}, 'Signature'), h('p', {}, char.dna.signature),
    h('h4', {}, 'Palette'),
    h('div', { class: 'row gap-2', style: 'margin-top: 4px;' }, ...char.dna.palette.map(c => h('div', { style: `width: 32px; height: 32px; border-radius: 4px; border: 1px solid var(--border); background: ${c};`, title: c })))
  );
  dnaBody.append(edit, preview);
  dna.append(dnaBody, h('div', { class: 'row between', style: 'padding: 12px 18px; border-top: 1px solid var(--border);' }, h('div', { class: 'label' }, 'last saved 2m ago · 14 revisions'), h('div', { class: 'row gap-2' }, h('button', { class: 'btn btn-ghost' }, 'Export'), h('button', { class: 'btn btn-primary' }, '✓ Save DNA'))));
  hero.append(dna);

  root.append(hero, sectionHead('Variation Gallery', `${char.name} · 24 frames`), h('div', { class: 'filter-chips', style: 'margin-bottom: 12px;' }, h('button', { class: 'chip active' }, 'All · 24'), h('button', { class: 'chip' }, 'Pose · 8'), h('button', { class: 'chip' }, 'Lighting · 6'), h('button', { class: 'chip' }, 'Background · 4'), h('button', { class: 'chip' }, 'Best Only · 11')), h('div', { class: 'var-gallery' }));
  // Gallery logic simplified for brevity in this reconstruction script
  for (let i = 0; i < 12; i++) {
    root.querySelector('.var-gallery').append(h('div', { class: 'thumb', html: frameSVG(`${char.name}_V${String(i+1).padStart(2,'0')}`, i, char.accent) + `<div class="meta-overlay"><div style="color: var(--${char.accent}); font-size: 10px;">V${String(i+1).padStart(2,'0')}</div><div class="muted">seed ${849271+i}</div></div>` }));
  }

  return root;
};



VIEWS.memory = async () => {
  const root = h('div');
  let stats = { events: 0, nodes: 0, density: 0 };
  try {
    const r = await fetch('/api/memory/stats');
    if (r.ok) stats = await r.json();
  } catch(e) { console.error("Memory stats failed", e); }

  root.append(sectionHead('Cognitive Memory Audit', 'Semantic Density: High'));
  root.append(h('div', { class: 'hero-grid' },
    statCard({ label: 'Total Events', value: stats.events || 0, accent: 'cyan' }),
    statCard({ label: 'Knowledge Nodes', value: stats.nodes || 0, accent: 'purple' }),
    statCard({ label: 'Semantic Density', value: stats.density || 0, accent: 'magenta', suffix: '%' })
  ));

  // Graph Placeholder
  root.append(h('div', { class: 'card card-pad', style: 'margin-top: 24px; height: 300px;' }, h('div', { class: 'label' }, 'Semantic Knowledge Graph (Loading...)')));
  setTimeout(initMemoryGraph, 100);

  return root;
};





VIEWS.home = () => {
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


VIEWS.characters = () => {
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


VIEWS.script = () => {
  const root = h('div');

  const toolbar = h('div', { class: 'script-toolbar' },
    h('div', { class: 'col gap-1' },
      h('div', { class: 'label' }, 'Active script'),
      h('select', { class: 'select', style: 'min-width: 260px;' },
        h('option', {}, 'pilot_script.md'),
        h('option', {}, 'emberfall_bible.md'),
        h('option', {}, 'act2_draft.md')
      )
    ),
    h('div', { class: 'col gap-1' },
      h('div', { class: 'label' }, 'Detected characters'),
      h('div', { class: 'row gap-2' },
        ...CHARACTERS.map(c => h('span', { class: `badge b-${c.accent === 'cyan' ? 'cyan' : c.accent === 'magenta' ? 'magenta' : 'amber'}` }, c.name))
      )
    ),
    h('div', { style: 'margin-left: auto;' },
      h('button', { class: 'btn btn-primary' }, '↻ Reparse Script')
    )
  );
  root.append(toolbar);

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
  SHOTS.forEach(s => {
    const row = h('tr', { class: expandedShot === s.id ? 'expanded' : '' },
      h('td', {}, String(s.n).padStart(2, '0')),
      h('td', {}, h('span', { style: 'color: var(--cyan); letter-spacing: 0.08em;' }, s.id)),
      h('td', {}, h('div', { class: 'row gap-2 wrap' },
        ...s.chars.map(c => h('span', { class: 'badge b-magenta' }, c))
      )),
      h('td', {}, h('span', { class: 'badge ' + STATUS_BADGE[s.status].cls }, STATUS_BADGE[s.status].label)),
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
              h('button', { class: 'btn btn-sm btn-ghost' }, 'Copy seed')
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
                ...s.chars.map(c => h('span', { class: 'badge b-magenta' }, c)),
                h('span', { class: 'badge b-amber' }, 'HOLLOW')
              )
            ),
            h('div', { class: 'col gap-1' },
              h('span', { class: 'label' }, 'Audit history'),
              h('div', { class: 'audit-row' },
                h('span', { class: 'muted' }, '14:02  pass'),
                h('span', { style: 'color: var(--green)' }, '0.96')
              ),
              h('div', { class: 'audit-row' },
                h('span', { class: 'muted' }, '13:51  pass'),
                h('span', { style: 'color: var(--green)' }, '0.92')
              ),
              h('div', { class: 'audit-row' },
                h('span', { class: 'muted' }, '13:48  fail'),
                h('span', { style: 'color: var(--red)' }, '0.61')
              )
            )
          )
        )
      )));
    }
  });
  table.append(tbody);
  card.append(table);
  root.append(card);
  return root;
};


VIEWS.products = () => {
  const root = h('div');
  root.append(sectionHead('Product Anchor · Emberdrive MKII', 'variant pipeline · 0 drift'));

  const hero = h('div', { class: 'char-hero' });
  const prod = { id: 'mk2', accent: 'amber', name: 'EMBERDRIVE', score: 87 };

  const anchor = h('div', { class: 'card anchor-card', 'data-accent': 'amber' });
  anchor.append(
    h('div', { class: 'anchor-img', html: frameSVG('EMBERDRIVE · MK-II', 3, 'amber', '1 / 1') }),
    h('div', { class: 'anchor-footer' },
      h('div', { class: 'consistency' },
        h('div', { class: 'row between' },
          h('span', { class: 'label' }, 'Consistency Score'),
          h('span', { class: 'score', style: 'color: var(--amber);' }, '87%')
        ),
        h('div', { class: 'progress mono' }, h('div', { class: 'fill', style: 'width: 87%;' }))
      ),
      h('button', { class: 'btn btn-primary' }, '↻ Regenerate')
    )
  );
  hero.append(anchor);

  const dna = h('div', { class: 'card dna-editor', 'data-accent': 'amber' },
    h('div', { class: 'dna-body' },
      h('div', { class: 'dna-pane' },
        h('h3', {}, 'Product description'),
        h('div', { class: 'dna-md', html: `
<span class="h"># EMBERDRIVE · MK-II</span>

<span class="h">## FORM</span>
<span class="k">silhouette:</span> <span class="v">"angular crescent, 220mm wingspan"</span>
<span class="k">material:</span>   <span class="v">"brushed titanium, matte black accents"</span>
<span class="k">intake:</span>     <span class="v">"triangular cyan glow slit"</span>

<span class="h">## DETAIL</span>
<span class="k">panel_lines:</span> <span class="v">"precise, hexagonal tiling"</span>
<span class="k">etching:</span>     <span class="v">"maker's mark on left dorsal fin"</span>

<span class="h">## LORE</span>
<span class="k">origin:</span>      <span class="v">"Hollow-forged, Orin workshop, year 0041"</span>
<span class="k">weight:</span>      <span class="v">"410g sealed"</span>` })
      ),
      h('div', { class: 'dna-pane dna-preview' },
        h('h4', {}, 'Form'),
        h('p', {}, 'Angular crescent silhouette, 220mm wingspan. Brushed titanium with matte black accents. Triangular cyan glow slit runs the length of the intake.'),
        h('h4', {}, 'Detail'),
        h('p', {}, 'Precise hexagonal panel tiling. Maker\'s mark etched on the left dorsal fin.'),
        h('h4', {}, 'Lore'),
        h('p', {}, 'Hollow-forged in the Orin workshop, year 0041. 410g sealed weight.')
      )
    )
  );
  hero.append(dna);
  root.append(hero);

  root.append(h('div', { style: 'height: 16px;' }));
  root.append(sectionHead('Generation Banks', 'tune each axis independently'));

  const banks = h('div', { class: 'bank-grid' },
    h('div', { class: 'card bank', 'data-accent': 'cyan' },
      h('div', { class: 'bank-title' }, 'Angle'),
      h('ul', {},
        h('li', {}, 'top-down · flat lay'),
        h('li', {}, '45° hero'),
        h('li', {}, 'profile · side'),
        h('li', {}, 'macro detail'),
        h('li', {}, '3/4 studio')
      )
    ),
    h('div', { class: 'card bank', 'data-accent': 'magenta' },
      h('div', { class: 'bank-title' }, 'Material'),
      h('ul', {},
        h('li', {}, 'brushed titanium'),
        h('li', {}, 'carbon fiber'),
        h('li', {}, 'matte ceramic'),
        h('li', {}, 'polished alloy'),
        h('li', {}, 'sooted steel')
      )
    ),
    h('div', { class: 'card bank', 'data-accent': 'amber' },
      h('div', { class: 'bank-title' }, 'Context'),
      h('ul', {},
        h('li', {}, 'white seamless'),
        h('li', {}, 'workshop bench'),
        h('li', {}, 'lifestyle · flight'),
        h('li', {}, 'scale · gloved hand'),
        h('li', {}, 'in motion · trail')
      )
    ),
    h('div', { class: 'card bank', 'data-accent': 'green' },
      h('div', { class: 'bank-title' }, 'Lighting'),
      h('ul', {},
        h('li', {}, 'softbox · 5600K'),
        h('li', {}, 'rim cyan · key amber'),
        h('li', {}, 'ember forge glow'),
        h('li', {}, 'moonlit · single source'),
        h('li', {}, 'hard dawn')
      )
    )
  );
  root.append(banks);

  root.append(h('div', { style: 'height: 20px;' }));
  root.append(sectionHead('Recent Variations'));
  const gal = h('div', { class: 'var-gallery' });
  for (let i = 0; i < 12; i++) {
    gal.append(h('div', { class: 'thumb', html: frameSVG(`MK2_V${String(i+1).padStart(2,'0')}`, i+5, i%2 ? 'amber' : 'cyan') + `
      <div class="meta-overlay">
        <div style="color: var(--amber); letter-spacing: 0.14em;">MK2_V${String(i+1).padStart(2,'0')}</div>
        <div class="muted" style="font-size: 9px;">angle ${(i%5)+1} · score 0.${85+i%12}</div>
      </div>` }));
  }
  root.append(gal);

  return root;
};

/* ---------- RENDERS ---------- */
VIEWS.renders = () => {
  const root = h('div');

  const bar = h('div', { class: 'card batch-bar', 'data-accent': 'green' },
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
      h('input', { class: 'input', type: 'number', value: 24, min: 1, max: 50 })
    ),
    h('div', { class: 'field' },
      h('span', { class: 'label' }, 'Seed'),
      h('div', { class: 'row gap-2' },
        h('input', { class: 'input', value: '849271', style: 'flex: 1;' }),
        h('button', { class: 'icon-btn', title: 'Lock seed' }, '🔒')
      )
    ),
    h('div', { class: 'field' },
      h('span', { class: 'label' }, 'Anchor'),
      h('div', { class: 'row gap-2', style: 'align-items: center;' },
        h('div', { style: 'width: 36px; height: 36px; border-radius: 4px; overflow: hidden; border: 1px solid var(--border);', html: portraitSVG(CHARACTERS[0], 36) }),
        h('select', { class: 'select', style: 'flex: 1;' },
          h('option', {}, 'ELARA · pilot anchor'),
          h('option', {}, 'ORIN · mechanist'),
          h('option', {}, 'VEX-09 · drone')
        )
      )
    ),
    h('div', { class: 'field', style: 'align-self: end;' },
      h('button', { class: 'btn btn-success btn-lg' }, '▶  Start Batch')
    ),
    h('div', { class: 'field', style: 'align-self: end;' },
      h('button', { class: 'btn btn-danger' }, '⏹  Clear Queue')
    )
  );
  root.append(bar);

  const layout = h('div', { class: 'render-layout' });

  // Queue monitor sidebar
  const monitor = h('div', { class: 'card card-pad queue-monitor', 'data-accent': 'amber' },
    h('div', { class: 'row between' },
      h('div', { class: 'display', style: 'font-size: 12px;' }, 'Queue Monitor'),
      h('span', { class: 'spark-status' }, h('span', { class: 'dot d-green' }), 'SPARK ONLINE')
    ),
    h('div', { class: 'row-stats' },
      h('div', { class: 'stat-mini' },
        h('div', { class: 'lbl' }, 'Queued'), h('div', { class: 'val' }, '22')),
      h('div', { class: 'stat-mini' },
        h('div', { class: 'lbl' }, 'Running'), h('div', { class: 'val', style: 'color: var(--amber);' }, '2')),
      h('div', { class: 'stat-mini' },
        h('div', { class: 'lbl' }, 'Done'), h('div', { class: 'val', style: 'color: var(--green);' }, '8')),
      h('div', { class: 'stat-mini' },
        h('div', { class: 'lbl' }, 'VRAM'), h('div', { class: 'val' }, '45GB'))
    ),
    h('div', { style: 'margin-top: 14px;' },
      h('div', { class: 'row between', style: 'margin-bottom: 6px;' },
        h('span', { class: 'label' }, 'Progress'),
        h('span', { class: 'label' }, '8 / 24')
      ),
      h('div', { class: 'progress' }, h('div', { class: 'fill', style: 'width: 33%;' })),
      h('div', { style: 'margin-top: 8px; font-size: 11px; color: var(--text-secondary);' }, 'ETA  ~12m 04s remaining'),
      h('div', { style: 'margin-top: 16px;' },
        h('span', { class: 'label' }, 'Current'),
        h('div', { style: 'margin-top: 6px; font-size: 13px; color: var(--amber);' }, 'VAR_014 · cockpit-cu · Elara')
      )
    ),
    h('div', { class: 'divider' }),
    h('div', { class: 'col gap-2' },
      h('span', { class: 'label' }, 'Cluster nodes'),
      h('div', { class: 'row between', style: 'font-size: 11px;' },
        h('span', {}, h('span', { class: 'dot d-green', style: 'margin-right: 8px;' }), 'node-02 · primary'),
        h('span', { class: 'muted' }, '45GB')
      ),
      h('div', { class: 'row between', style: 'font-size: 11px;' },
        h('span', {}, h('span', { class: 'dot d-dim', style: 'margin-right: 8px;' }), 'node-03 · standby'),
        h('span', { class: 'muted' }, 'offline')
      )
    )
  );
  layout.append(monitor);

  // render grid
  const grid = h('div', { class: 'render-grid' });
  const accents = ['cyan','magenta','amber','green'];
  // 8 complete
  for (let i = 0; i < 8; i++) {
    grid.append(h('div', { class: 'thumb', html: frameSVG(`VAR_${String(i+1).padStart(3,'0')}`, i, accents[i%4], '3/4') + `
      <div class="meta-overlay">
        <div style="color: var(--cyan); letter-spacing: 0.14em;">VAR_${String(i+1).padStart(3,'0')} · 0.9${2 + i%6}</div>
        <div class="muted" style="font-size: 9px;">seed ${849271+i} · ${['elara','orin','vex'][i%3]}</div>
      </div>` }));
  }
  // 2 running (active glow)
  for (let i = 8; i < 10; i++) {
    grid.append(h('div', { class: 'thumb active', html: `
      <div style="position: absolute; inset: 0; background: radial-gradient(circle at 50% 50%, rgba(255,191,0,0.15), #0D1420 70%);"></div>
      <div class="skeleton" style="position: absolute; inset: 0; background: linear-gradient(110deg, transparent 30%, rgba(255,191,0,0.18) 50%, transparent 70%); background-size: 200% 100%; animation: skeleton 2s linear infinite;"></div>
      <div style="position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-family: 'JetBrains Mono'; font-size: 10px; color: var(--amber); letter-spacing: 0.2em;">
        VAR_${String(i+1).padStart(3,'0')} · rendering…
      </div>` }));
  }
  // 12 pending skeletons
  for (let i = 10; i < 22; i++) {
    grid.append(h('div', { class: 'thumb pending', html: `
      <div class="skeleton"></div>
      <div style="position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--text-dim); font-size: 10px; letter-spacing: 0.2em;">
        QUEUED · ${String(i+1).padStart(3,'0')}
      </div>` }));
  }
  layout.append(grid);
  root.append(layout);
  return root;
};

/* ---------- MEMORY ---------- */
VIEWS.memory = () => {
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
VIEWS.settings = async () => {
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
    ...GRAPH.edges.map((e, i) => ({ data: { id: 'e'+i, source: e.source, target: e.target } }))
  ];

  const cy = cytoscape({
    container,
    elements,
    style: [
      {
        selector: 'node',
        style: {
          'background-color': 'data(color)',
          'label': 'data(label)',
          'color': '#E6EDF3',
          'font-family': 'JetBrains Mono, monospace',
          'font-size': 9,
          'text-margin-y': -8,
          'text-valign': 'top',
          'text-halign': 'center',
          'text-outline-color': '#0A0E14',
          'text-outline-width': 2,
          'width': 28, 'height': 28,
          'border-width': 2,
          'border-color': 'data(color)',
          'border-opacity': 0.6,
          'overlay-padding': 8,
          'transition-property': 'opacity, border-width',
          'transition-duration': 200
        }
      },
      { selector: 'node[type="session"]', style: { 'width': 40, 'height': 40, 'shape': 'round-hexagon' } },
      { selector: 'node[type="insight"]', style: { 'shape': 'round-diamond', 'width': 32, 'height': 32 } },
      { selector: 'node[type="concept"]', style: { 'shape': 'round-rectangle' } },
      { selector: 'node[type="outcome"]', style: { 'shape': 'ellipse' } },
      {
        selector: 'edge',
        style: {
          'width': 1,
          'line-color': '#2A3A4F',
          'target-arrow-color': '#2A3A4F',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          'opacity': 0.7
        }
      },
      { selector: '.dim',   style: { 'opacity': 0.12 } },
      { selector: '.highlight', style: {
        'border-width': 4, 'border-opacity': 1,
        'box-shadow': '0 0 30px currentColor'
      }}
    ],
    layout: { name: 'cose', padding: 80, animate: true, animationDuration: 600, idealEdgeLength: 110, nodeRepulsion: 8000 }
  });

  cy.on('mouseover', 'node', (evt) => {
    const n = evt.target;
    n.style({ 'border-width': 4, 'border-opacity': 1 });
  });
  cy.on('mouseout', 'node', (evt) => {
    evt.target.style({ 'border-width': 2, 'border-opacity': 0.6 });
  });
  cy.on('tap', 'node', (evt) => {
    const n = evt.target;
    const connected = n.neighborhood().union(n);
    cy.elements().not(connected).addClass('dim');
    connected.removeClass('dim');
  });
  cy.on('tap', (evt) => {
    if (evt.target === cy) cy.elements().removeClass('dim');
  });

  // Layout buttons
  $$('.graph-toolbar [data-layout]').forEach(btn => {
    btn.addEventListener('click', () => {
      const name = btn.dataset.layout;
      cy.layout({
        name,
        padding: 60,
        animate: true,
        animationDuration: 600,
        fit: true
      }).run();
    });
  });

  // Search
  const search = document.getElementById('graph-search');
  if (search) {
    let to = null;
    search.addEventListener('input', () => {
      clearTimeout(to);
      to = setTimeout(() => {
        const q = search.value.trim().toLowerCase();
        if (!q) { cy.elements().removeClass('dim'); return; }
        const matching = cy.nodes().filter(n => (n.data('label') || '').toLowerCase().includes(q));
        const all = matching.union(matching.neighborhood());
        cy.elements().addClass('dim');
        all.removeClass('dim');
      }, 250);
    });
  }

  window.__cy = cy;
}

document.addEventListener('DOMContentLoaded', boot);


// --- Character Management ---

window.openAddCharacterModal = function() {
    const modal = h('div', { id: 'modal-overlay', class: 'modal-overlay' }, [
        h('div', { class: 'modal-content' }, [
            h('h3', {}, 'Add New Character'),
            h('div', { class: 'form-group' }, [
                h('label', {}, 'Name'),
                h('input', { id: 'new-char-name', type: 'text', placeholder: 'e.g. Elara Vance' })
            ]),
            h('div', { class: 'form-group' }, [
                h('label', {}, 'Description/Bio'),
                h('textarea', { id: 'new-char-desc', placeholder: 'Brief backstory...' })
            ]),
            h('div', { class: 'modal-actions' }, [
                h('button', { class: 'btn-secondary', onclick: () => document.getElementById('modal-overlay').remove() }, 'Cancel'),
                h('button', { class: 'btn-primary', onclick: window.generateAndRenderCharacter() }, 'Generate + Render')
            ])
        ])
    ]);
    document.body.appendChild(modal);
};

window.renderCharacterAnchor = async function(char) {
    console.log(`Rendering anchor for: ${char.id}`);
    const container = document.querySelector(`#char-anchor-${char.id}`);
    if (container) container.innerHTML = '<div class="loading-spinner"></div>';

    try {
        const res = await fetch('/api/characters/render', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: char.id, prompt: char.anchor_prompt })
        });
        if (!res.ok) throw new Error('Render request failed');
        const data = await res.json();
        
        // Polling or direct update depending on API behavior
        if (data.anchor_url) {
            container.innerHTML = `<img src="${data.anchor_url}" class="character-anchor-img" alt="${char.id}">`;
        }
    } catch (err) {
        console.error('Render error:', err);
        if (container) container.innerHTML = '<div class="error">Failed to render</div>';
    }
};

window.generateAndRenderCharacter = async function() {
    const name = document.getElementById('new-char-name').value;
    const desc = document.getElementById('new-char-desc').value;

    if (!name || !desc) {
        alert('Name and Description are required.');
        return;
    }

    try {
        // 1. Generate via Hermes
        const genRes = await fetch('/api/hermes/generate-character', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description: desc })
        });
        if (!genRes.ok) throw new Error('Character generation failed');
        const charData = await genRes.json();

        // 2. Render via Spark (using the returned character info)
        // Assuming charData contains { id, anchor_prompt }
        await window.renderCharacterAnchor(charData);
        
        document.getElementById('modal-overlay').remove();
    } catch (err) {
        console.error('Sequence error:', err);
        alert('Process failed: ' + err.message);
    }
};