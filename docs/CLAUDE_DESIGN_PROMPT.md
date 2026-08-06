Prompt for Claude Design Agent
Context
You are designing the UI for Cinesmith, an AI-powered creative production pipeline that generates consistent character and product renders at scale. The user is a creative director who drops in a lore bible (character descriptions) and seed images, then batches out 24-30 variations using FLUX2 NVFP4 Turbo on a remote GPU cluster ("the Spark").
The system has a backend in Python (FastAPI) and currently has a functional but bare-bones dashboard on port 7000. The backend is fully working. Your job is to design and build the frontend UI.
Design Vibe: "The Creative Studio of 2035"
Think: DaVinci Resolve's precision meets Spline's playfulness meets a living, breathing creative intelligence. The interface should feel like a tool you want to spend hours in — responsive, luminous, and alive. Dark mode is the canvas; neon accents are the energy. Every panel has depth (glassmorphism + subtle glow), every number updates in real-time, and the system feels like it's working with you, not monitoring you.
Fluid, responsive, alive with information — every pixel earns its keep
Dark mode only (#0A0E14 background) — the canvas
Neon accents: cyan #00FFFF, magenta #FF00FF, amber #FFBF00 — the energy
Monospace font (JetBrains Mono) for labels and data — precision without coldness
Glassmorphism panels with subtle backdrop blur — depth and dimension
Subtle scanline overlay + grid background — texture, not surveillance
Every active element has a colored top-edge glow bar — like a neon sign humming to life
Celebrate progress. The machine has a heartbeat, not a duty roster.
Color System
css
Copy
--bg-primary: #0A0E14;
--bg-panel: #0D1117;
--bg-card: #111820;
--border: #1E2A3A;
--text-primary: #E6EDF3;
--text-secondary: #8B949E;
--cyan: #00FFFF;
--magenta: #FF00FF;
--amber: #FFBF00;
--green: #00FF41;
--red: #FF3333;
--purple: #BD00FF;
Navigation Structure (7 Tabs)
Top bar: Logo left, tab pills center, Spark status + actions right.
1. HOME / OVERVIEW (default)
Hero stats row: 6 cards — Total Events, Insights, Success Rate, Queue Depth, Active Sessions, Time Range. Each card has a colored top gradient bar.
Recent renders strip: Horizontal scroll of thumbnail images with hover zoom.
Queue status panel: Live progress bar, current job name, ETA.
Quick actions: 4 large button tiles — Start Batch, Review Anchors, Open Spark Output, Run Memory Audit.
2. CHARACTERS
Character selector: Horizontal card row with anchor thumbnails.
Anchor hero: Large image left with "Regenerate" button + consistency score bar.
DNA editor: Split-pane markdown editor (edit left, rendered preview right) for Hair, Eyes, Clothing, Signature Item.
Variation gallery: Grid of renders with filter chips (All / Pose / Lighting / Background / Best Only).
3. SCRIPT
Script selector: Dropdown to pick script file.
Shot list table: Columns = #, Shot ID, Characters, Status (badge), Prompt Preview. Sortable.
Expandable rows: Click to reveal full prompt, detected character badges, locked seed, audit history.
4. PRODUCTS
Same layout as Characters but for product shots.
Banks: Angle, Material, Context, Lighting.
Product description editor instead of character DNA.
5. RENDERS — The Studio Floor
Batch controls bar: Workflow dropdown, Count spinner (1-50), Seed lock toggle, Anchor image picker (drag-and-drop), START BATCH (big green), CLEAR QUEUE (red).
Queue monitor sidebar: Spark online indicator, pending count, VRAM free, progress bar, ETA.
Render grid: Masonry or uniform grid. Hover = metadata overlay (prompt, seed, score). Click = lightbox.
6. MEMORY
Stats cards: Same 6 as Home but with memory-specific metrics.
Force-directed graph: Cytoscape.js network graph (nodes = events/insights/sessions, edges = relationships). Color-coded nodes.
Timeline: Vertical chronological feed of last 30 events.
Insights panel: Semantic rules with confidence bars.
Search bar: Filters graph in real-time.
Layout buttons: Force / Circle / Grid / Radial.
7. SETTINGS
API keys (masked input + show toggle)
ComfyUI hosts table (primary/secondary + status dots)
Model config (FLUX2 model, CLIP, LoRA file paths)
Bank editor: tabbed textareas for pose/view/lighting/background/extras banks (one item per line)
Backend API (Already Built)
The following endpoints exist and return JSON. Build the frontend to consume them.
plain
Copy
GET /api/memory/stats       → { total_events, total_insights, success_rate, ... }
GET /api/memory/timeline    → [{ event_id, timestamp, type, concept, ... }]
GET /api/memory/insights    → [{ insight_id, rule, confidence, confirmations, ... }]
GET /api/memory/graph       → { nodes: [...], edges: [...] }
GET /api/memory/search?q=   → { events: [...], insights: [...] }
GET /api/skills             → [{ name, status }]
GET /api/session/{id}       → { status, shots, ... }
GET /api/reasoning/{shot}   → { shot_id, content }
Key Frontend Libraries
Cytoscape.js (CDN: https://unpkg.com/cytoscape@3.26.0/dist/cytoscape.min.js) — for the memory graph. Already proven working.
Vanilla JS — no React/Vue needed. Keep it simple for hackathon speed.
CSS Grid + Flexbox for layout.
File Structure to Build
plain
Copy
dashboard/static/
├── index.html              ← Main shell with tabs
├── css/
│   ├── design-system.css   ← All CSS variables, base styles, scanlines, grid bg
│   ├── components.css      ← Cards, buttons, inputs, badges, progress bars
│   └── animations.css      ← Keyframes, transitions
├── js/
│   ├── app.js              ← Tab router, init, state
│   ├── api.js              ← Fetch wrappers for all endpoints
│   └── memory-graph.js     ← Cytoscape setup (reference existing memory.html)
Assets You Can Generate
Logo SVG: "CINESMITH NPS" wordmark or an abstract anvil/cinesmith icon in cyan
Favicon: 32x32 dark with cyan accent
Empty state illustrations: simple geometric line art in the neon color palette
Critical UI Behaviors
Tab switching: Content crossfades 200ms. URL hash updates (#/renders).
Live queue: Polls /api/memory/stats every 5 seconds when on Renders or Home tab.
Graph hover: Tooltip with full metadata appears near cursor.
Graph click: Dims non-neighbor nodes to 15% opacity.
Render thumbnails: Lazy load. Hover = scale 1.05 + metadata overlay.
Search: Debounced 300ms. Non-matching graph nodes fade to 10%.
Buttons: All buttons have hover glow transition (200ms ease).
Responsive Breakpoints
Desktop ≥1200px: Full layout, sidebar always visible.
Tablet 900-1199px: 2-column, sidebar collapses to icon-only.
Mobile <900px: Single column, tab bar → hamburger menu, cards stack.
What NOT to Do
Don't use Bootstrap, Tailwind, or any CSS framework. Write custom CSS to match the design system exactly.
Don't use React/Vue/Angular. Vanilla JS only.
Don't make it light mode.
Don't use generic Material Design components. Everything should feel custom-built for this tool.
Don't make it feel like a dashboard you're being monitored on. Make it feel like a studio you want to play in.
Success Criteria
[ ] All 7 tabs exist and are navigable
[ ] Home tab shows live stats from /api/memory/stats
[ ] Renders tab has functional batch controls (UI only — wire to backend later)
[ ] Memory tab shows the Cytoscape graph with correct node colors
[ ] Every card has the colored top-edge glow bar
[ ] Scanline + grid background visible on all tabs
[ ] Mobile: tabs collapse to hamburger, content stacks vertically
Reference Material
The existing dashboard/static/memory.html already implements:
Cytoscape.js graph with correct styling
Stats cards with gradient top bars
Timeline + insights panels
Search functionality
Design system (scanlines, grid bg, neon colors)
Use it as your style reference. Extract the CSS and adapt it into the shared design-system.css.
The existing dashboard/static/index.html has:
Basic WebSocket feed
Mock data display
Very simple grid layout
