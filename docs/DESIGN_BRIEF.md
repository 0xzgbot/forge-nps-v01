# Forge NPS — UI/UX Design Brief

> **Goal:** Transform the current functional dashboard into a **professional, cohesive, easy-to-use interface** that looks like a high-end creative production tool.
>
> **Vibe:** Hermes agent — cyberpunk, high-tech, precise, trustworthy. Think: "What if DaVinci Resolve and a military C2 system had a baby for AI image generation?"
>
> **User:** A creative director who needs to generate 24-30 consistent character/product renders in a batch, monitor quality, and iterate quickly.

---

## Design System

### Color Palette (Neo-Veridia)

| Token | Hex | Usage |
|---|---|---|
| `--bg-primary` | `#0A0E14` | Page background |
| `--bg-panel` | `#0D1117` | Card/panel background |
| `--bg-card` | `#111820` | Elevated surfaces |
| `--border` | `#1E2A3A` | Borders, dividers |
| `--text-primary` | `#E6EDF3` | Headings, primary text |
| `--text-secondary` | `#8B949E` | Labels, metadata |
| `--cyan` | `#00FFFF` | Primary accent, active states, links |
| `--magenta` | `#FF00FF` | Secondary accent, characters, alerts |
| `--amber` | `#FFBF00` | Warnings, sessions, highlights |
| `--green` | `#00FF41` | Success, pass, positive |
| `--red` | `#FF3333` | Error, fail, critical |
| `--purple` | `#BD00FF` | Insights, memory, AI-generated |

### Typography

- **Primary:** `JetBrains Mono` or `SF Mono` — monospace for that terminal/command-line precision
- **Secondary:** `Inter` or `SF Pro Display` — for longer readable text (character descriptions, etc.)
- **Scale:** 11px labels → 13px body → 16px headings → 24px hero stats

### Effects

- **Glassmorphism:** `backdrop-filter: blur(12px)` + semi-transparent backgrounds
- **Neon glows:** Text shadows and box shadows with accent colors at 20-40% opacity
- **Scanlines:** Very subtle CSS overlay (`repeating-linear-gradient` at 0.015 opacity)
- **Grid background:** 50px CSS grid at 0.03 opacity cyan
- **Edge highlights:** 2px gradient line at top of active cards (cyan → transparent)
- **Hover states:** Border color transition + subtle glow increase

### Spacing

- Tight, information-dense layout
- 12px gaps between panels
- 16px padding inside cards
- 1px borders with `--border` color

---

## Navigation Structure

```
┌─────────────────────────────────────────────────────────────┐
│  [LOGO]  FORGE NPS        Home  Characters  Script  Products  Renders  Memory  Models  Settings  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [CONTENT AREA — changes per tab]                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Top Bar

- **Left:** Logo + project name "FORGE NPS" in gradient text (cyan → magenta)
- **Center:** Tab navigation (pill-style, active tab has cyan underline glow)
- **Right:** Spark status indicator (green pulsing dot = online), quick actions dropdown

---

## Tab Specifications

### 1. HOME / OVERVIEW (Default Landing)

**Purpose:** System heartbeat. One-glance status of everything.

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [HERO STATS ROW]                                          │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐  │
│  │ Events │ │Insights│ │Success │ │ Queue  │ │ Active │  │
│  │  176   │ │   2    │ │  100%  │ │  22/24 │ │  1 run │  │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘  │
├─────────────────────────────┬───────────────────────────────┤
│  [RECENT RENDERS STRIP]     │  [LIVE QUEUE STATUS]         │
│  Thumbnail row (8 recent)   │  Progress bar + ETA          │
│  with hover zoom            │  Current job name            │
├─────────────────────────────┴───────────────────────────────┤
│  [QUICK ACTIONS]            │  [MEMORY MINI-GRAPH]         │
│  • Start New Batch          │  Last 20 nodes, condensed    │
│  • Review Anchors           │  Click to expand → Memory tab│
│  • Open Spark Output        │                              │
│  • Run Memory Audit         │                              │
└─────────────────────────────────────────────────────────────┘
```

**Key Elements:**
- Stats cards with top gradient bar (color per metric)
- Render strip: horizontal scroll of recent PNGs, hover = 1.2x zoom + metadata overlay
- Queue status: progress bar, "VAR_014 running… 3 min remaining" style text
- Quick actions: large button tiles with icons

---

### 2. CHARACTERS

**Purpose:** Manage character DNA, anchors, and consistency.

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [CHARACTER SELECTOR — horizontal cards]                   │
│  ┌────────┐ ┌────────┐ ┌────────┐                         │
│  │ ELARA  │ │ [+]    │                                      │
│  │ [img]  │ │ Add    │                                      │
│  │ ✓ Live │ │ Char   │                                      │
│  └────────┘ └────────┘                                      │
├─────────────────────────────────────────────────────────────┤
│  [ANCHOR IMAGE — large left]  │  [DNA EDITOR — right]      │
│  512x512 hero image           │  Markdown editor with      │
│  with "Regenerate" button     │  live preview              │
│                               │  Sections: Hair, Eyes,     │
│  Consistency Score: 94%       │  Clothing, Signature Item  │
│  ━━━━━━━━━━━━○────            │                              │
│                               │  [Save DNA] [Export]        │
├───────────────────────────────┴──────────────────────────────┤
│  [VARIATION GALLERY — grid]                                 │
│  Filter: [All] [Pose] [Lighting] [Background] [Best Only]  │
│  ┌────┐┌────┐┌────┐┌────┐┌────┐┌────┐...                   │
│  │img ││img ││img ││img ││img ││img │                       │
│  └────┘└────┘└────┘└────┘└────┘└────┘                       │
│  Hover: full prompt + seed + score                         │
└─────────────────────────────────────────────────────────────┘
```

**Key Elements:**
- Character selector: card with anchor thumbnail, name, status dot
- DNA editor: split-pane markdown editor (left: edit, right: rendered preview)
- Consistency score: horizontal bar, color-coded (green ≥80%, amber 60-80%, red <60%)
- Gallery: CSS grid, 6 columns, infinite scroll or pagination
- Filter chips: toggle buttons, multiple select

---

### 3. SCRIPT

**Purpose:** Upload, parse, and manage production scripts.

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [UPLOAD / SELECT SCRIPT]  world_bible.md  pilot_script.md │
├─────────────────────────────────────────────────────────────┤
│  [SHOT LIST — table view]                                   │
│  # │ Shot ID    │ Characters │ Status    │ Prompt Preview │
│  ──┼────────────┼────────────┼───────────┼────────────────│
│  1 │ SHOT_001   │ Elara      │ ✅ Done   │ "extreme..."   │
│  2 │ SHOT_002   │ Elara      │ 🔄 Retry  │ "close up..."  │
│  3 │ SHOT_003   │ —          │ ⏳ Queue  │ —              │
├─────────────────────────────────────────────────────────────┤
│  [SHOT DETAIL — expands on row click]                      │
│  Left: Full prompt text (editable)                         │
│  Right: Character detection badges + locked seed value     │
│  Bottom: Audit history (pass/fail + score)                 │
└─────────────────────────────────────────────────────────────┘
```

**Key Elements:**
- Shot table: sortable columns, status badges (✅ 🔄 ⏳ ❌)
- Expandable rows: click to reveal full details
- Character badges: colored pills showing detected characters
- Seed display: locked value with copy button

---

### 4. PRODUCTS

**Purpose:** Product-specific variation pipeline (future expansion of character system).

**Layout:** Mirror of Characters tab but with product-specific banks:
- Angle bank (top-down, 45°, flat lay, macro)
- Material bank (aluminum, carbon fiber, matte black)
- Context bank (white background, lifestyle, scale reference)

---

### 5. RENDERS

**Purpose:** The command center for batch generation.

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [BATCH CONTROLS — top bar]                                │
│  Workflow: [FLUX2 Turbo ▼]  Count: [24 ▼]  Seed: [🔒]     │
│  [Select Anchor Image(s)]  [▶ START BATCH]  [⏹ CLEAR]     │
├─────────────────────────────────────────────────────────────┤
│  [QUEUE MONITOR — left sidebar]  │  [RENDER GRID — main]   │
│  ┌────────────────────────────┐  │  ┌────┐┌────┐┌────┐    │
│  │ Spark: 🟢 Online           │  │  │img ││img ││img │    │
│  │ Queue: 22 pending          │  │  └────┘└────┘└────┘    │
│  │ VRAM: 45GB free            │  │  ┌────┐┌────┐┌────┐    │
│  │                            │  │  │img ││img ││img │    │
│  │ Progress:                  │  │  └────┘└────┘└────┘    │
│  │ ████████░░░░░░░░░░ 8/24   │  │                          │
│  │ ETA: ~12 min remaining     │  │  [Load More]            │
│  │                            │  │                          │
│  │ Current: VAR_008_running   │  │                          │
│  └────────────────────────────┘  │                          │
└─────────────────────────────────────────────────────────────┘
```

**Key Elements:**
- Workflow dropdown: select from `/workflows/` folder
- Count spinner: 1-50
- Seed lock toggle: random vs deterministic
- Anchor image picker: drag-and-drop zone + gallery
- Start/Clear buttons: large, color-coded (green = start, red = clear)
- Queue monitor: live-updating sidebar with Spark health
- Render grid: masonry or uniform grid, hover = metadata + download

---

### 6. MEMORY

**Purpose:** Hermes memory visualization (ALREADY BUILT — needs integration into this design system).

**Current State:** `dashboard/static/memory.html` has:
- Cytoscape.js force-directed graph
- Event timeline
- Semantic insights panel
- Stats cards
- Search

**Needed:**
- Move into the tabbed layout (currently standalone page)
- Match the glassmorphism + neon design system
- Add auto-refresh toggle
- Add filter buttons by node type (Attempts, Outcomes, Insights, Sessions)

---

### 7. MODELS

**Purpose:** Backend model selection and connection management.

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [BACKEND TOGGLE — centered, large]                        │
│        LOCAL ◄────────────────────────► API                 │
│   (LM Studio)                          (Kimi / NIM)         │
│  Toggle animates: cyan ↔ green                              │
├─────────────────────────────────────────────────────────────┤
│  [LM STUDIO CARD]              │  [KIMI / NIM CARD]        │
│  Green accent                  │  Magenta accent             │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
│  ● Status dot (online/offline) │  ● Status dot              │
│  Model: [dropdown ▼]           │  Model: [dropdown ▼]       │
│  [Test Connection]             │  [Test Connection]         │
│                                │  Endpoint: [...]           │
└─────────────────────────────────────────────────────────────┘
```

**Key Elements:**
- Backend toggle: large animated switch, color transition from cyan (API) to green (LOCAL)
- LM Studio card: green accent (`--green`), status indicator, model dropdown populated from local server
- Kimi/NIM card: magenta accent (`--magenta`), status indicator, model dropdown, endpoint field
- Test Connection button per card: validates reachability and shows pass/fail
- Only the active backend's card is fully enabled; inactive card is dimmed

---

### 8. SETTINGS

**Purpose:** System configuration and management. Backend model and API settings are managed in the **Models** tab.

**Layout:**
```
┌─────────────────────────────────────────────────────────────┐
│  [COMFYUI HOSTS]                                            │
│  Primary:   [100.112.87.8:8188]  🟢 Online                │
│  Secondary: [100.112.87.8:8189]  ⚫ Offline               │
│  [+ Add Host]                                               │
│                                                             │
│  [BANK EDITOR]                                              │
│  Tabbed editor for pose/view/lighting/background banks     │
│  ┌────────┐┌────────┐┌────────┐┌────────┐                │
│  │ Pose   ││ View   ││ Light  ││ Bg     │                │
│  └────────┘└────────┘└────────┘└────────┘                │
│  [textarea with one item per line]                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Library

### Buttons

```
Primary:    bg-transparent, border-cyan, text-cyan, hover:bg-cyan/10, hover:shadow-cyan
Danger:     border-red, text-red, hover:bg-red/10
Success:    border-green, text-green, hover:bg-green/10
Ghost:      no border, text-secondary, hover:text-primary
IconBtn:    32x32 square, centered icon, border, hover:glow
```

### Cards

```
Base:       bg-bg-card, border-1px border, rounded-4px, padding-16px
Active:     + top gradient bar (2px, accent color)
Hover:      border-color → accent, subtle shadow
```

### Badges / Pills

```
Status:     4px radius, padding 2px 8px, font-size 11px
  - success: bg-green/10, border-green/30, text-green
  - warning: bg-amber/10, border-amber/30, text-amber
  - error:   bg-red/10, border-red/30, text-red
  - info:    bg-cyan/10, border-cyan/30, text-cyan
Character:  bg-magenta/10, border-magenta/30, text-magenta
```

### Inputs

```
Text:       bg-bg-card, border-1px, rounded-4px, padding-10px
Focus:      border-cyan, shadow-cyan/15
Disabled:   opacity-50, cursor-not-allowed
```

### Progress Bar

```
Track:      bg-border, height-4px, rounded
Fill:       gradient (cyan → magenta), animated shimmer
Label:      text-secondary, 11px, above or inside
```

---

## Responsive Behavior

- **Desktop (≥1200px):** Full 3-column layouts, sidebar always visible
- **Tablet (900-1199px):** 2-column, sidebar collapses to icons
- **Mobile (<900px):** Single column, tab bar becomes hamburger menu, cards stack vertically

---

## Assets Needed

| Asset | Format | Notes |
|---|---|---|
| Logo | SVG | "FORGE NPS" wordmark or abstract forge/anvil icon |
| Favicon | ICO/PNG | 32x32, cyan accent on dark |
| Empty States | SVG | Illustrations for "no renders yet", "no characters" |
| Icons | SVG/IconFont | System, characters, script, products, renders, memory, models, settings, play, stop, refresh, download, copy, search, filter, expand, collapse |

---

## Animation Specs

| Element | Animation | Duration | Easing |
|---|---|---|---|
| Page load | Fade in + translateY(10px) | 300ms | ease-out |
| Card hover | Border glow increase | 200ms | ease |
| Tab switch | Content crossfade | 200ms | ease-in-out |
| Stats count | Number roll-up | 600ms | ease-out |
| Queue progress | Width transition | 300ms | linear |
| Graph layout | Node reposition | 500ms | ease-in-out |
| Render thumbnail | Scale 1.0 → 1.05 on hover | 200ms | ease |
| Toast notification | Slide in from top-right | 300ms | ease-out |

---

## File Structure

```
dashboard/
├── static/
│   ├── index.html          ← Main dashboard (tabs container)
│   ├── memory.html         ← Memory Core (already built)
│   ├── css/
│   │   ├── design-system.css   ← Variables, base, utilities
│   │   ├── components.css      ← Cards, buttons, inputs, badges
│   │   ├── layouts.css         ← Grid systems, responsive
│   │   └── animations.css      ← Keyframes, transitions
│   ├── js/
│   │   ├── app.js              ← Router, state, init
│   │   ├── tabs.js             ← Tab switching logic
│   │   ├── api.js              ← Fetch wrappers
│   │   ├── memory-graph.js     ← Cytoscape setup
│   │   ├── render-grid.js      ← Masonry/infinite scroll
│   │   └── components.js       ← Reusable JS components
│   └── assets/
│       ├── logo.svg
│       ├── icons/
│       └── empty-states/
├── forge_dashboard.py      ← FastAPI app
└── memory_api.py           ← Backend API (already built)
```

---

## Priority Order (MVP → Polish)

| Phase | Scope | Est. Time |
|---|---|---|
| **P0** | Design system CSS + tab shell + Home overview | 3-4 hrs |
| **P1** | Renders tab (batch controls + grid) | 2-3 hrs |
| **P2** | Characters tab (DNA editor + gallery) | 2-3 hrs |
| **P3** | Memory tab (port existing into shell) | 1-2 hrs |
| **P4** | Script tab (shot list table) | 1-2 hrs |
| **P5** | Models tab (backend selector + connection cards) | 1 hr |
| **P6** | Settings tab (config editor) | 1 hr |
| **P7** | Products tab | 1 hr |
| **P8** | Polish: animations, responsive, empty states, iconography | 2-3 hrs |

**Total MVP:** ~12-15 hours of focused frontend work.
