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
  products: 'Products', renders: 'Renders', memory: 'Memory', models: 'Models', settings: 'Settings'
};

let activeTab = 'home';
let activeCharId = 'elara';
let expandedShot = null;

/* ---------- Boot ---------- */
function boot() {
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
  // Light/dark toggle
  const themeBtn = $('#theme-toggle');
  const isLight = localStorage.getItem('forge-theme') === 'light';
  if (isLight) document.body.classList.add('light-mode');
  themeBtn && themeBtn.addEventListener('click', () => {
    const light = document.body.classList.toggle('light-mode');
    localStorage.setItem('forge-theme', light ? 'light' : 'dark');
    themeBtn.title = light ? 'Switch to dark mode' : 'Switch to light mode';
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
  if (name === 'home') { setTimeout(() => initHermesPanel($('#hermes-panel')), 30); setTimeout(() => initTeachMode($('#teach-mode-container')), 30); }
  if (name === 'renders') { setTimeout(() => initSparkWidget($('#spark-widget')), 30); setTimeout(() => initRenderGallery($('#render-gallery')), 30); }
  if (name === 'memory') { setTimeout(initMemoryGraph, 30); setTimeout(loadMemoryLiveData, 50); }
  if (name === 'models') setTimeout(initModelsPage, 30);
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

function openVideoLightbox(renderData) {
    const lightbox = document.createElement('div');
    lightbox.className = 'lightbox-overlay';
    lightbox.innerHTML = `
        <div class="lightbox-content video-lightbox">
            <div class="lightbox-header">
                <h3>${renderData.shot_id}</h3>
                <button class="btn-ghost" onclick="closeLightbox()">Close</button>
            </div>
            <div id="video-player-container"></div>
            <div class="lightbox-meta">
                <p><strong style="color: var(--cyan)">Prompt:</strong> ${renderData.prompt}</p>
                <p><strong style="color: var(--amber)">Seed:</strong> ${renderData.seed || 'N/A'}</p>
                <p><strong style="color: var(--magenta)">Score:</strong> ${renderData.score || 'N/A'}</p>
            </div>
        </div>
    `;
    document.body.appendChild(lightbox);

    // Global close function for the button
    window.closeLightbox = () => {
        lightbox.remove();
    };
    
    new ForgeVideoPlayer(
        "video-player-container",
        renderData.asset_path,
        {
            shot_id: renderData.shot_id,
            description: renderData.prompt,
            lore_excerpt: window.currentLoreExcerpt || "No lore loaded."
        }
    );
}

function openImageLightbox(renderData) {
    const lightbox = document.createElement('div');
    lightbox.className = 'lightbox-overlay';
    lightbox.innerHTML = `
        <div class="lightbox-content image-lightbox">
            <div class="lightbox-header">
                <h3>${renderData.shot_id}</h3>
                <button class="btn-ghost" onclick="closeLightbox()">Close</button>
            </div>
            <img src="${renderData.asset_path}" style="max-width:100%;max-height:70vh;object-fit:contain;border-radius:4px;" />
            <div class="lightbox-meta">
                <p><strong style="color: var(--cyan)">Prompt:</strong> ${renderData.prompt || 'N/A'}</p>
                <p><strong style="color: var(--amber)">Seed:</strong> ${renderData.seed || 'N/A'}</p>
                <p><strong style="color: var(--magenta)">Score:</strong> ${renderData.score || 'N/A'}</p>
            </div>
        </div>
    `;
    document.body.appendChild(lightbox);
    window.closeLightbox = () => lightbox.remove();
    lightbox.addEventListener('click', e => { if (e.target === lightbox) lightbox.remove(); });
}

function createRenderCard(renderData) {
    const isVideo = renderData.asset_path.match(/\.(mp4|webm|mov)$/i);
    
    const card = h('div', { class: 'render-card' });
    card.innerHTML = `
        ${isVideo
            ? `<div class="video-thumbnail">
                <video src="${renderData.asset_path}" muted preload="metadata"></video>
                <div class="play-overlay">Play</div>
               </div>`
            : `<img src="${renderData.asset_path}" loading="lazy">`
        }
        <div class="render-meta">
            <span class="badge-${renderData.status || 'ready'}">${renderData.status || 'ready'}</span>
            <span class="shot-id">${renderData.shot_id}</span>
        </div>
    `;
    
    card.addEventListener('click', () => {
        if (isVideo) { openVideoLightbox(renderData); }
        else if (typeof openImageLightbox === 'function') { openImageLightbox(renderData); }
    });
    
    return card;
}

/* ======================================================================
   VIEWS
   ====================================================================== */
const VIEWS = {};

/* ---------- HOME ---------- */
VIEWS.home = () => {
  const root = h('div');

  // ── Campaign Queue — full-width top bar ──
  const queue = h('div', { class: 'card card-pad queue-panel queue-topbar', 'data-accent': 'amber' },
    h('div', { class: 'row between' },
      h('div', { class: 'col gap-1' },
        h('div', { class: 'display', style: 'font-size: 13px;' }, 'Campaign Queue'),
        h('div', { class: 'label' }, 'Spark · FLUX2 + LTX + WAN')
      ),
      h('div', { class: 'col gap-1', style: 'flex: 1; margin: 0 24px; min-width: 0;' },
        h('div', { class: 'row between' },
          h('div', { style: 'font-size: 14px; color: var(--amber); letter-spacing: 0.1em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;' }, 'VAR_014 · cockpit-cu · Elara'),
          h('div', { class: 'eta' }, 'ETA 3m 12s · 8 of 24 complete')
        ),
        h('div', { class: 'progress', style: 'width: 100%; margin-top: 6px;' }, h('div', { class: 'fill', style: 'width: 33%;' }))
      ),
      h('div', { class: 'row gap-2', style: 'align-items: center;' },
        h('div', { class: 'heartbeat' }, ...Array.from({ length: 8 }, () => h('div', { class: 'bar' }))),
        h('button', { class: 'icon-btn', title: 'Pause' }, '⏸'),
        h('button', { class: 'icon-btn', title: 'Skip' }, '⏭')
      )
    )
  );
  root.append(queue);

  // ── Stat pills row ──
  const hero = h('div', { class: 'hero-grid', style: 'margin-top: 12px;' },
    statCard({ label: 'Total Events',   value: 176, accent: 'cyan'    }),
    statCard({ label: 'Insights',       value: 12,  accent: 'purple'  }),
    statCard({ label: 'Success Rate',   value: 94,  accent: 'green',   suffix: '%' }),
    statCard({ label: 'Queue Depth',    value: 22,  accent: 'amber',   sub: h('span', {}, 'of 24 staged') }),
    statCard({ label: 'Active Models',  value: 4,   accent: 'magenta', sub: h('span', {}, 'FLUX2 · LTX · WAN · Z-Image') }),
    statCard({ label: 'Styles',         value: 8,   accent: 'cyan',    suffix: '+' })
  );
  root.append(hero);

  // ── Main body: Hermes large left | sidebar right ──
  const body = h('div', { class: 'home-body' });
  const left  = h('div', { class: 'col gap-3' });
  const right = h('div', { class: 'col gap-3' });

  // Hermes Live — tall main panel
  const hermesCard = h('div', { class: 'card card-pad hermes-main', 'data-accent': 'purple' },
    h('div', { class: 'row between', style: 'margin-bottom: 12px;' },
      h('div', { class: 'display', style: 'font-size: 13px;' }, 'Hermes Live'),
      h('span', { class: 'ticker' }, 'STREAMING · /ws/hermes')
    ),
    h('div', { id: 'hermes-panel', class: 'hermes-panel hermes-panel-tall' },
      h('div', { class: 'label', style: 'opacity:0.5;' }, 'Waiting for events...')
    )
  );
  left.append(hermesCard);

  // Teach Mode
  left.append(h('div', { id: 'teach-mode-container' }));

  // Recent renders strip
  const recent = h('div', { class: 'card card-pad', 'data-accent': 'cyan' });
  recent.append(
    h('div', { class: 'row between', style: 'margin-bottom: 14px;' },
      h('div', { class: 'col gap-1' },
        h('div', { class: 'display', style: 'font-size: 13px;' }, 'Recent Campaign Assets'),
        h('div', { class: 'label' }, 'Last 8 · FLUX2 Dev + Z-Image Turbo')
      ),
      h('div', { class: 'row gap-2' },
        h('button', { class: 'chip active' }, 'All'),
        h('button', { class: 'chip' }, 'Social'),
        h('button', { class: 'chip' }, 'Products'),
        h('button', { class: 'chip' }, 'Video')
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

  // Quick Actions
  right.append(h('div', { class: 'card card-pad', 'data-accent': 'cyan' },
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
  ));

  // Live Feed
  right.append(h('div', { class: 'card card-pad', 'data-accent': 'purple' },
    h('div', { class: 'row between', style: 'margin-bottom: 10px;' },
      h('div', { class: 'display', style: 'font-size: 13px;' }, 'Live Feed'),
      h('div', { class: 'ticker' }, 'STREAMING · 24ms')
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
  ));

  body.append(left, right);
  root.append(body);
  return root;
};

/* ---------- CHARACTERS ---------- */
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

/* ---------- SCRIPT ---------- */
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

/* ---------- PRODUCTS ---------- */
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
        h('option', {}, 'FLUX2 Dev NVFP4 — Quality'),
        h('option', {}, 'Z-Image Turbo — Speed'),
        h('option', {}, 'LTX 2.3 NVFP4 — Video'),
        h('option', {}, 'WAN 2.2 NVFP4 — Animation')
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
          h('option', {}, 'VEX-09 · companion')
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

  // Spark Monitor Widget sidebar (live)
  const monitor = h('div', { id: 'spark-widget', class: 'card card-pad', 'data-accent': 'amber' });
  layout.append(monitor);

  // render gallery (real thumbnails)
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

  // side: insights + timeline + actions
  const side = h('div', { class: 'mem-side' });

  // Actions card
  const actionsCard = h('div', { class: 'card card-pad', 'data-accent': 'cyan' },
    h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 10px;' }, 'Actions'),
    h('button', {
      class: 'btn btn-primary consolidate-btn',
      id: 'consolidate-btn',
      onclick: async () => {
        const btn = $('#consolidate-btn');
        btn.textContent = 'Consolidating...';
        btn.disabled = true;
        try {
          const r = await fetch('/api/memory/consolidate', { method: 'POST' });
          const data = await r.json();
          btn.textContent = `${data.new_insights} insights born ✓`;
          setTimeout(() => { btn.textContent = 'Consolidate Now'; btn.disabled = false; }, 3000);
          // Refresh insights if on memory tab
          if (activeTab === 'memory') switchTab('memory', false);
        } catch (e) {
          btn.textContent = 'Failed';
          setTimeout(() => { btn.textContent = 'Consolidate Now'; btn.disabled = false; }, 3000);
        }
      }
    }, 'Consolidate Now'),
    h('div', { class: 'label', style: 'margin-top: 8px; opacity: 0.5;' }, 'Trigger episodic → semantic dream')
  );
  side.append(actionsCard);

  // Insights card (live)
  const insightsCard = h('div', { class: 'card card-pad', 'data-accent': 'purple' },
    h('div', { class: 'row between', style: 'margin-bottom: 12px;' },
      h('div', { class: 'display', style: 'font-size: 12px;' }, 'What Hermes Has Learned'),
      h('span', { class: 'badge b-purple', id: 'insight-count' }, '—')
    ),
    h('div', { class: 'insights', id: 'insights-list' },
      h('div', { class: 'label', style: 'opacity:0.5;' }, 'Loading...')
    )
  );
  side.append(insightsCard);

  // Timeline card (live)
  const tlCard = h('div', { class: 'card card-pad', 'data-accent': 'cyan' },
    h('div', { class: 'row between', style: 'margin-bottom: 10px;' },
      h('div', { class: 'display', style: 'font-size: 12px;' }, 'Timeline'),
      h('span', { class: 'label' }, 'last 8')
    ),
    h('div', { class: 'timeline', id: 'timeline-list' },
      ...TIMELINE.slice(0, 8).map(e => h('div', { class: 'tl-event' },
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

/* ---------- MODELS ---------- */
VIEWS.models = () => {
  const root = h('div');
  root.append(sectionHead('Models', 'Local vs API Backend', { style: 'margin-top: 0;' }));

  const grid = h('div', { class: 'settings-grid' });

  // --- Toggle Switch ---
  const toggleCard = h('div', { class: 'card', 'data-accent': 'cyan', style: 'grid-column: 1 / -1;' });
  const toggleRow = h('div', { class: 'model-toggle-row' });

  const localLabel = h('span', { class: 'model-toggle-label' }, 'LOCAL');
  const apiLabel = h('span', { class: 'model-toggle-label' }, 'API');

  const switchTrack = h('div', { class: 'model-toggle-track' });
  const switchThumb = h('div', { class: 'model-toggle-thumb' });
  switchTrack.append(switchThumb);

  let currentMode = 'api'; // default until fetch

  async function fetchStatus() {
    try {
      const r = await fetch('/api/models/status');
      const data = await r.json();
      currentMode = data.mode;
      updateToggle(data.mode);
      updateLocalCard(data.local);
      updateApiCard(data.api);
    } catch (e) {
      console.warn('Models status fetch failed', e);
    }
  }

  function updateToggle(mode) {
    switchThumb.style.left = mode === 'local' ? '4px' : 'calc(100% - 28px)';
    localLabel.classList.toggle('active', mode === 'local');
    apiLabel.classList.toggle('active', mode === 'api');
  }

  switchTrack.addEventListener('click', async () => {
    const newMode = currentMode === 'api' ? 'local' : 'api';
    try {
      const r = await fetch('/api/models/mode', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: newMode })
      });
      if (r.ok) {
        currentMode = newMode;
        updateToggle(newMode);
        fetchStatus();
      }
    } catch (e) {
      alert('Failed to switch mode: ' + e.message);
    }
  });

  toggleRow.append(localLabel, switchTrack, apiLabel);
  toggleCard.append(
    h('div', { class: 'display', style: 'font-size: 11px; margin-bottom: 12px; opacity: 0.7;' }, 'BACKEND MODE'),
    toggleRow,
    h('div', { class: 'label', style: 'margin-top: 12px; opacity: 0.5;' },
      'Toggle between LM Studio (local GPU) and Kimi/NIM (cloud API). Hermes will route all inference through the selected backend.'
    )
  );
  grid.append(toggleCard);

  // --- Local Card ---
  function updateLocalCard(info) { /* stub — LM Studio config is in the settings grid below */ }
  async function testLocal() { await fetch('/api/models/test-local'); }

  const apiStatus = h('div', { class: 'model-status' });
  function updateApiCard(info) {
    apiStatus.innerHTML = '';
    apiStatus.append(
      h('span', { class: 'dot d-' + (info.available ? 'green' : 'red') }),
      h('span', { class: 'label' }, info.available ? 'Ready' : 'Not configured'),
      h('span', { class: 'label', style: 'opacity: 0.5; margin-left: auto;' }, info.endpoint || '')
    );
  }
  async function testApi() { await fetch('/api/models/test-api'); }

  root.append(grid);

  // Fetch status on mount
  setTimeout(fetchStatus, 50);

  return root;
};

/* ---------- SETTINGS (merged with Models) ---------- */
VIEWS.settings = () => {
  const root = h('div');
  root.append(sectionHead('Settings', 'Models, Configuration & System'));

  // ── Models section (merged from Models tab) ──
  const modelsWrap = h('div', { style: 'margin-bottom: 16px;' });
  modelsWrap.append(VIEWS.models());
  root.append(modelsWrap);
  const grid = h('div', { class: 'settings-grid' });

  const statusBar = h('div', { class: 'label', style: 'margin-bottom: 12px; opacity: 0.6; font-size: 11px;' }, 'Loading configuration...');
  root.append(statusBar);

  // Helper to create a saveable input row
  function makeRow(label, key, opts = {}) {
    const input = h('input', {
      class: 'input',
      type: opts.type || 'text',
      value: opts.value || '',
      'data-key': key,
      onblur: () => saveKey(key, input.value),
    });
    const row = h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, label),
      input,
      h('button', {
        class: 'btn btn-sm',
        onclick: () => { saveKey(key, input.value); }
      }, 'Save')
    );
    row._input = input;
    return row;
  }

  async function saveKey(key, value) {
    statusBar.textContent = 'Saving ' + key + '...';
    try {
      const r = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates: { [key]: value } })
      });
      if (r.ok) {
        statusBar.textContent = key + ' saved ✓';
        setTimeout(() => { statusBar.textContent = 'Configuration auto-saved to data/config.json'; }, 2000);
      } else {
        statusBar.textContent = 'Save failed for ' + key;
      }
    } catch (e) {
      statusBar.textContent = 'Network error: ' + e.message;
    }
  }

  // --- API Keys Section ---
  const apiCard = h('div', { class: 'card setting-group', 'data-accent': 'cyan' });
  const nimStatus = h('div', { class: 'model-status' });
  const apiTestBtn = h('button', { class: 'btn btn-sm', style: 'color: var(--green); border-color: var(--green); margin-top: 4px;', onclick: async () => {
    apiTestBtn.textContent = 'Testing...';
    try {
      const r = await fetch('/api/models/test-api');
      const d = await r.json();
      nimStatus.innerHTML = '';
      nimStatus.append(
        h('span', { class: 'dot d-' + (d.healthy ? 'green' : 'red') }),
        h('span', { class: 'label' }, d.healthy ? 'Ready' : 'Unreachable'),
        h('span', { class: 'label', style: 'opacity:0.5; margin-left:auto;' }, d.api_key_configured ? 'Key ✓' : 'No key')
      );
    } catch(e) { nimStatus.textContent = '✗ error'; }
    apiTestBtn.textContent = 'Test Connection';
  }}, 'Test Connection');
  apiCard.append(
    h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 4px;' }, 'Kimi / NVIDIA NIM'),
    nimStatus,
    makeRow('API Key', 'KIMI_API_KEY', { type: 'password' }),
    makeRow('NIM Endpoint', 'NIM_ENDPOINT'),
    apiTestBtn
  );
  grid.append(apiCard);

  function makeTestBtn(label, onClick) {
    const btn = h('button', { class: 'btn btn-sm', style: 'color: var(--green); border-color: var(--green);', onclick: onClick }, label);
    return btn;
  }

  function addComfyTestBtn(row) {
    const input = row._input;
    const status = h('span', { class: 'label', style: 'margin-left: 8px; min-width: 80px;' }, '');
    const btn = makeTestBtn('Test', async () => {
      const url = input.value.trim();
      if (!url) return;
      status.textContent = 'testing…';
      try {
        const r = await fetch('/api/spark/test?url=' + encodeURIComponent(url));
        if (r.ok) {
          status.style.color = 'var(--green)';
          status.textContent = '✓ online';
        } else {
          status.style.color = 'var(--red, #ff4444)';
          status.textContent = '✗ offline';
        }
      } catch { status.style.color = 'var(--red, #ff4444)'; status.textContent = '✗ error'; }
    });
    row.append(btn, status);
  }

  // --- ComfyUI Hosts Section ---
  const comfyCard = h('div', { class: 'card setting-group', 'data-accent': 'green' });
  comfyCard.append(h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 4px;' }, 'ComfyUI Hosts'));
  const primaryRow = makeRow('Primary Host', 'COMFYUI_PRIMARY');
  const secondaryRow = makeRow('Secondary Host', 'COMFYUI_SECONDARY');
  addComfyTestBtn(primaryRow);
  addComfyTestBtn(secondaryRow);
  comfyCard.append(primaryRow, secondaryRow);

  // Extra servers added dynamically
  const extraServers = h('div', { id: 'extra-comfy-servers' });
  comfyCard.append(extraServers);

  let extraCount = 3;
  const addServerBtn = h('button', {
    class: 'btn btn-ghost',
    style: 'margin-top: 10px; color: var(--green); border-color: var(--green);',
    onclick: () => {
      const key = `COMFYUI_EXTRA_${extraCount}`;
      const row = makeRow(`Server ${extraCount}`, key);
      addComfyTestBtn(row);
      // Add remove button
      const removeBtn = h('button', {
        class: 'icon-btn',
        title: 'Remove',
        style: 'color: var(--red, #ff4444); margin-left: 6px;',
        onclick: () => { row.remove(); }
      }, '✕');
      row.append(removeBtn);
      extraServers.append(row);
      extraCount++;
    }
  }, '+ Add Server');
  comfyCard.append(addServerBtn);
  grid.append(comfyCard);

  // --- LM Studio Section ---
  const lmCard = h('div', { class: 'card setting-group', 'data-accent': 'purple' });
  lmCard.append(h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 4px;' }, 'LM Studio (Local Inference)'));
  const lmHostRow = makeRow('LM Studio Host', 'LMSTUDIO_HOST');
  const lmEmbedRow = makeRow('Embedding Model', 'LMSTUDIO_EMBED_MODEL');
  const lmChatRow = makeRow('Chat Model', 'LMSTUDIO_CHAT_MODEL');

  // LM Studio test btn — also auto-fills loaded models
  const lmStatus = h('span', { class: 'label', style: 'margin-left: 8px; min-width: 120px;' }, '');
  const lmTestBtn = makeTestBtn('Test & Detect Models', async () => {
    lmStatus.textContent = 'testing…';
    lmStatus.style.color = '';
    try {
      const r = await fetch('/api/models/test-local');
      if (r.ok) {
        const d = await r.json();
        lmStatus.style.color = 'var(--green)';
        lmStatus.textContent = `✓ ${(d.models || []).length} model(s) loaded`;
        // Auto-fill chat and embed fields from detected models
        const models = d.models || [];
        const chatModel = models.find(m => !m.toLowerCase().includes('embed') && !m.toLowerCase().includes('nomic')) || models[0];
        const embedModel = models.find(m => m.toLowerCase().includes('embed') || m.toLowerCase().includes('nomic'));
        if (chatModel && !lmChatRow._input.value) {
          lmChatRow._input.value = chatModel;
          saveKey('LMSTUDIO_CHAT_MODEL', chatModel);
        }
        if (embedModel && !lmEmbedRow._input.value) {
          lmEmbedRow._input.value = embedModel;
          saveKey('LMSTUDIO_EMBED_MODEL', embedModel);
        }
      } else {
        lmStatus.style.color = 'var(--red, #ff4444)';
        lmStatus.textContent = '✗ not reachable';
      }
    } catch { lmStatus.style.color = 'var(--red, #ff4444)'; lmStatus.textContent = '✗ error'; }
  });
  lmHostRow.append(lmTestBtn, lmStatus);

  lmCard.append(
    lmHostRow,
    lmEmbedRow,
    lmChatRow,
    h('div', { class: 'label', style: 'margin-top: 8px; opacity: 0.5;' },
      'Point at any machine running LM Studio. Examples: http://localhost:1234 | http://192.168.1.50:1234 | http://localhost:1234'
    )
  );
  grid.append(lmCard);

  // --- Model Config Section ---
  const modelCard = h('div', { class: 'card setting-group', 'data-accent': 'magenta' });
  modelCard.append(h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 4px;' }, 'NIM Model Names'));
  const instructRow = makeRow('Instruct Model', 'KIMI_INSTRUCT_MODEL');
  const thinkingRow = makeRow('Thinking Model', 'KIMI_THINKING_MODEL');
  const visualRow = makeRow('Visual Model', 'KIMI_VISUAL_MODEL');
  modelCard.append(instructRow, thinkingRow, visualRow);
  grid.append(modelCard);

  // --- GPU Farm Section ---
  const gpuCard = h('div', { class: 'card setting-group', 'data-accent': 'amber', style: 'grid-column: 1 / -1;' });
  const gpuGridEl = h('div', { style: 'display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-top: 10px;' });
  const gpuList = [
    { name: 'RTX 3090 #1', vram: '24 GB', model: 'FLUX2 Dev NVFP4', temp: 68, load: 94 },
    { name: 'RTX 3090 #2', vram: '24 GB', model: 'FLUX2 Dev NVFP4', temp: 71, load: 91 },
    { name: 'GTX 1080 Ti #1', vram: '11 GB', model: 'Z-Image Turbo', temp: 74, load: 88 },
    { name: 'GTX 1080 Ti #2', vram: '11 GB', model: 'Z-Image Turbo', temp: 72, load: 85 },
  ];
  gpuList.forEach(gpu => gpuGridEl.appendChild(h('div', { class: 'card', style: 'padding: 12px; border: 1px solid var(--border);' },
    h('div', { class: 'row between', style: 'margin-bottom: 8px;' },
      h('span', { class: 'display', style: 'font-size: 11px; color: var(--amber);' }, gpu.name),
      h('span', { class: 'label', style: 'opacity: 0.6;' }, gpu.vram)
    ),
    h('div', { class: 'label', style: 'margin-bottom: 8px;' }, gpu.model),
    h('div', { class: 'row between', style: 'font-size: 11px; opacity: 0.7;' },
      h('span', {}, `Load: ${gpu.load}%`), h('span', {}, `Temp: ${gpu.temp}°C`)
    ),
    h('div', { class: 'progress mono', style: 'margin-top: 6px; height: 4px;' },
      h('div', { class: 'fill', style: `width: ${gpu.load}%; background: var(--amber);` })
    )
  )));
  gpuCard.append(
    h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 4px;' }, 'GPU Farm'),
    h('div', { class: 'label', style: 'opacity: 0.5; margin-bottom: 8px;' }, '4 GPUs · 70 GB TOTAL VRAM · rendering only'),
    gpuGridEl
  );
  grid.append(gpuCard);

  // --- Export Brain Section ---
  const exportCard = h('div', { class: 'card setting-group', 'data-accent': 'purple' });
  exportCard.append(
    h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 8px;' }, 'Hermes Brain'),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'Export'),
      h('button', {
        class: 'btn',
        onclick: async () => {
          try {
            const r = await fetch('/api/hermes/export');
            const data = await r.json();
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `hermes_brain_${data.exported_at.replace(/[:T]/g, '-')}.json`;
            a.click();
            URL.revokeObjectURL(url);
            statusBar.textContent = 'Brain exported ✓';
          } catch (e) {
            statusBar.textContent = 'Export failed: ' + e.message;
          }
        }
      }, '⎘ Export Brain')
    ),
    h('div', { class: 'label', style: 'margin-top: 8px; opacity: 0.5;' },
      'Downloads semantic insights + skill registry + episodic summary as JSON.'
    )
  );
  grid.append(exportCard);

  // --- Restart Section ---
  const restartCard = h('div', { class: 'card setting-group', 'data-accent': 'red' });
  restartCard.append(
    h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 8px;' }, 'System'),
    h('div', { class: 'setting-row' },
      h('span', { class: 'lbl' }, 'Dashboard'),
      h('button', {
        class: 'btn btn-danger',
        onclick: async () => {
          if (!confirm('Restart the dashboard server? You will need to refresh the page after.')) return;
          try {
            const r = await fetch('/api/restart', { method: 'POST' });
            const data = await r.json();
            statusBar.textContent = data.message;
          } catch (e) {
            statusBar.textContent = 'Restart triggered. Refresh page in 3 seconds.';
          }
        }
      }, 'Restart Server')
    ),
    h('div', { class: 'label', style: 'margin-top: 8px; opacity: 0.5;' },
      'Config is saved to data/config.json and overrides .env. Restart applies changes.'
    )
  );
  grid.append(restartCard);

  root.append(grid);

  // Load real config on mount
  setTimeout(async () => {
    try {
      const r = await fetch('/api/config');
      const cfg = await r.json();
      // Populate all inputs by data-key
      $$('[data-key]').forEach(el => {
        const key = el.dataset.key;
        if (cfg[key] !== undefined) el.value = cfg[key];
      });
      statusBar.textContent = 'Configuration loaded from .env + data/config.json';
    } catch (e) {
      statusBar.textContent = 'Failed to load configuration';
    }
  }, 50);

  return root;
};

/* ---------- Models page init ---------- */
function initModelsPage() {
  // Status is fetched inside VIEWS.models render
}

/* ---------- Memory live data loader ---------- */
async function loadMemoryLiveData() {
  try {
    const [insightsR, timelineR, statsR] = await Promise.all([
      fetch('/api/memory/insights').catch(() => null),
      fetch('/api/memory/timeline?limit=8').catch(() => null),
      fetch('/api/memory/stats').catch(() => null),
    ]);

    if (insightsR && insightsR.ok) {
      const insights = await insightsR.json();
      const list = $('#insights-list');
      const count = $('#insight-count');
      if (list) {
        list.innerHTML = '';
        (insights || []).slice(0, 8).forEach(i => {
          list.appendChild(h('div', { class: 'insight' },
            h('div', { class: 'rule' }, i.rule || i.text || 'Insight'),
            h('div', { class: 'confidence-bar' }, h('div', { class: 'fill', style: `width: ${(i.confidence || 0) * 100}%;` })),
            h('div', { class: 'meta' },
              h('span', {}, `conf ${Math.round((i.confidence || 0) * 100)}%  ·  ${i.confirms || 0} confirms`),
              h('span', {}, i.age || 'recent')
            )
          ));
        });
      }
      if (count) count.textContent = (insights || []).length + ' INSIGHTS';
    }

    if (timelineR && timelineR.ok) {
      const timeline = await timelineR.json();
      const list = $('#timeline-list');
      if (list) {
        list.innerHTML = '';
        (timeline || []).slice(0, 8).forEach(e => {
          list.appendChild(h('div', { class: 'tl-event' },
            h('div', { class: 'tl-time' }, e.t || e.timestamp?.split('T')[1]?.slice(0,5) || '--:--'),
            h('div', { class: 'tl-body' },
              h('div', { class: 'tl-type' }, e.type || 'event'),
              h('div', { class: 'tl-desc' }, e.desc || e.concept || '')
            )
          ));
        });
      }
    }

    if (statsR && statsR.ok) {
      const stats = await statsR.json();
      // Update stat cards if they have data-countup
      $$('[data-countup]').forEach(el => {
        const key = el.closest('.card')?.querySelector('.stat-label')?.textContent?.toLowerCase();
        if (key && stats[key] !== undefined) {
          el.dataset.countup = stats[key];
          el.textContent = stats[key];
        }
      });
    }
  } catch (e) {
    console.warn('Memory live data load failed', e);
  }
}

/* ---------- Memory graph init ---------- */
function initMemoryGraph() {
  if (!window.cytoscape) return;
  const container = document.getElementById('graph-canvas');
  if (!container) return;

  const elements = [
    ...GRAPH.nodes.map(n => ({ data: { id: n.id, label: n.label, type: n.type, color: NODE_COLORS[n.type] } })),
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
