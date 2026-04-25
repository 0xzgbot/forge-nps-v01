/* Forge NPS — mock data + helpers */

const CHARACTERS = [
  {
    id: 'elara',
    name: 'ELARA',
    role: 'Pilot · Protagonist',
    accent: 'cyan',
    score: 94,
    anchor_prompt: 'Portrait of ELARA, female pilot protagonist, platinum crop hair with undercut left side and singed tips, pale amber reflective eyes, lean athletic build, charcoal flight jacket over graphite undersuit with copper piping along seams, ember-glow tattoo on left forearm, softbox studio lighting, neutral dark background, highly detailed, cinematic, 8k',
    dna: {
      hair: 'Platinum crop, undercut left side, singed tips from the Hollow',
      eyes: 'Pale amber, reflective — pupils dilate in low-light',
      build: 'Lean, 5\'8", defined shoulders from high-g maneuvers',
      clothing: 'Charcoal flight jacket over graphite undersuit, copper piping along seams',
      signature: 'Left forearm: ember-glow tattoo — a spiralling sigil, always visible',
      palette: ['#C4A57A', '#2A2E35', '#E9A74B']
    }
  },
  {
    id: 'orin',
    name: 'ORIN',
    role: 'Mechanist · Ally',
    accent: 'magenta',
    score: 88,
    anchor_prompt: 'Portrait of ORIN, male mechanist, jet black shoulder-length hair pulled into utilitarian knot, deep indigo eyes with surgical steadiness, tall broad-framed build, heat-resistant apron soot-scored, copper tools at belt, right hand three-fingered prosthetic with exposed servos, softbox studio lighting, neutral dark background, highly detailed, cinematic, 8k',
    dna: {
      hair: 'Jet black, shoulder length, pulled into a utilitarian knot',
      eyes: 'Deep indigo, surgical steadiness',
      build: 'Tall, broad-framed, calloused hands',
      clothing: 'Heat-resistant apron, soot-scored; copper tools at the belt',
      signature: 'Right hand: three-fingered prosthetic with exposed servos',
      palette: ['#0E0F12', '#4A3A2A', '#B76E3A']
    }
  },
  {
    id: 'vex',
    name: 'VEX-09',
    role: 'Drone · Companion',
    accent: 'amber',
    score: 91,
    anchor_prompt: 'VEX-09 compact quadrotor drone, palm-sized, brushed alloy chassis, single large cyan aperture eye with iris shutter, polished gunmetal shell with faint cyan trace lines, amber underglow lighting effect, four-fold manipulator arms, studio product photography, neutral dark background, highly detailed, 8k',
    dna: {
      hair: '—',
      eyes: 'Single cyan aperture, 120° pan, iris shutter animated',
      build: 'Palm-sized drone, brushed alloy chassis, four-fold manipulators',
      clothing: 'Polished gunmetal shell, faint cyan trace lines',
      signature: 'Amber underglow when processing, hums at 440 Hz',
      palette: ['#30343C', '#00FFFF', '#FFBF00']
    }
  }
];

const SHOTS = [
  { n: 1,  id: 'SHOT_001', chars: ['ELARA'],           status: 'done',    seed: 849271, prompt: 'Wes Anderson style — Elara centered in a pastel coral room, symmetrical framing, soft key light, playful props, 35mm film grain' },
  { n: 2,  id: 'SHOT_002', chars: ['ELARA'],           status: 'retry',   seed: 849272, prompt: 'photoreal advertising — Elara holding a chrome water bottle, studio lighting, white seamless background, product sharp, shallow depth of field' },
  { n: 3,  id: 'SHOT_003', chars: ['ELARA','ORIN'],    status: 'done',    seed: 849273, prompt: 'animated cel-shade — Elara and Orin in a sunlit meadow, soft outlines, warm palette, Studio Ghibli influence, expressive poses' },
  { n: 4,  id: 'SHOT_004', chars: ['VEX-09'],          status: 'running', seed: 849274, prompt: 'macro product detail — Vex-09 on brushed aluminum surface, studio rim light, shallow DOF, commercial photography style' },
  { n: 5,  id: 'SHOT_005', chars: ['ELARA'],           status: 'queued',  seed: 849275, prompt: 'cinematic noir — Elara in a rain-soaked alley, single streetlamp key light, high contrast, moody color grade, anamorphic lens' },
  { n: 6,  id: 'SHOT_006', chars: ['ORIN'],            status: 'queued',  seed: 849276, prompt: 'pop-art portrait — Orin against a saturated yellow background, bold outlines, flat color blocks, graphic poster style' },
  { n: 7,  id: 'SHOT_007', chars: ['ELARA','VEX-09'],  status: 'failed',  seed: 849277, prompt: 'architectural interior — Elara and Vex-09 in a mid-century modern living room, warm wood tones, geometric light patterns, editorial photography' },
  { n: 8,  id: 'SHOT_008', chars: ['ELARA'],           status: 'queued',  seed: 849278, prompt: 'fantasy watercolor — Elara in an enchanted forest, soft bleeding edges, luminous highlights, storybook illustration style' }
];

const STATUS_BADGE = {
  done:    { label: 'COMPLETE',  cls: 'b-green'   },
  running: { label: 'RUNNING',   cls: 'b-amber'   },
  retry:   { label: 'RETRYING',  cls: 'b-amber'   },
  queued:  { label: 'QUEUED',    cls: 'b-cyan'    },
  failed:  { label: 'FAILED',    cls: 'b-red'     }
};

const INSIGHTS = [
  { rule: 'Wes Anderson style — Elara\'s eye color desaturates under warm pastels. Boost amber saturation +0.15 when palette includes coral or peach.', confidence: 0.91, confirms: 14, age: '2h' },
  { rule: 'Photoreal advertising — Orin renders with 5 fingers when prosthetic is below frame. Always cite "three-fingered prosthetic" in prompt tail.', confidence: 0.97, confirms: 22, age: '4h' },
  { rule: 'Cel-shaded animation — Vex-09 iris drifts to blue under soft outlines. Lock to Z-Image anime checkpoint for animated sequences.', confidence: 0.84, confirms: 9, age: '9h' },
  { rule: 'Noir lighting — backgrounds below 0.35 exposure flatten the subject. Maintain rim-light ≥ 0.6 when key is single-source.', confidence: 0.79, confirms: 6, age: '1d' },
  { rule: 'Product photography — chrome surfaces reflect environment color. Include neutral gray surround for consistent bottle renders.', confidence: 0.88, confirms: 11, age: '3h' }
];

const TIMELINE = [
  { t: '14:02:11', type: 'RENDER_PASS',  desc: 'VAR_014 · Elara · Wes Anderson portrait · consistency 0.96' },
  { t: '14:01:42', type: 'AUDIT_PASS',   desc: 'SHOT_003 — animated style · 4 anchors matched, 0 drift flags' },
  { t: '14:01:19', type: 'DISPATCH',     desc: 'Batch queued · 18 variations · FLUX2 Dev + Z-Image Turbo' },
  { t: '14:00:03', type: 'INSIGHT',      desc: 'New rule promoted · "Pastel eye saturation boost" · confidence 0.91' },
  { t: '13:58:47', type: 'REMEDIATION',  desc: 'SHOT_007 auto-repaired after 2 iterations · architectural lighting fix' },
  { t: '13:56:22', type: 'AUDIT_FAIL',   desc: 'SHOT_007 — interior wood tones shifted warm · retry scheduled' },
  { t: '13:54:08', type: 'RENDER_PASS',  desc: 'VAR_009 · Orin · pop-art portrait · consistency 0.89' },
  { t: '13:51:55', type: 'SESSION_OPEN', desc: 'Session 2026-04-23-A · style bible: multiverse.md · operator: creative_director' }
];

const GRAPH = {
  nodes: [
    { id: 's1',   type: 'session',  label: 'Session 2026-04-23-A' },
    { id: 'a1',   type: 'attempt',  label: 'Attempt · Elara pose' },
    { id: 'a2',   type: 'attempt',  label: 'Attempt · Orin portrait' },
    { id: 'a3',   type: 'attempt',  label: 'Attempt · Vex macro' },
    { id: 'a4',   type: 'attempt',  label: 'Attempt · Hollow wide' },
    { id: 'a5',   type: 'attempt',  label: 'Attempt · holoprojector' },
    { id: 'o1',   type: 'outcome',  label: 'Pass · 0.94' },
    { id: 'o2',   type: 'outcome',  label: 'Pass · 0.89' },
    { id: 'o3',   type: 'outcome',  label: 'Pass · 0.96' },
    { id: 'o4',   type: 'outcome',  label: 'Fail · drift' },
    { id: 'o5',   type: 'outcome',  label: 'Fail · iris color' },
    { id: 'i1',   type: 'insight',  label: 'Amber/cyan cap' },
    { id: 'i2',   type: 'insight',  label: 'Prosthetic phrasing' },
    { id: 'i3',   type: 'insight',  label: 'CLIP lock for Vex' },
    { id: 'i4',   type: 'insight',  label: 'Hollow volumetric range' },
    { id: 'c1',   type: 'concept',  label: 'ELARA' },
    { id: 'c2',   type: 'concept',  label: 'ORIN' },
    { id: 'c3',   type: 'concept',  label: 'VEX-09' },
    { id: 'c4',   type: 'concept',  label: 'HOLLOW' }
  ],
  edges: [
    { source: 's1', target: 'a1' },
    { source: 's1', target: 'a2' },
    { source: 's1', target: 'a3' },
    { source: 's1', target: 'a4' },
    { source: 's1', target: 'a5' },
    { source: 'a1', target: 'o1' },
    { source: 'a2', target: 'o2' },
    { source: 'a3', target: 'o3' },
    { source: 'a4', target: 'o4' },
    { source: 'a5', target: 'o5' },
    { source: 'o4', target: 'i1' },
    { source: 'o4', target: 'i4' },
    { source: 'o5', target: 'i3' },
    { source: 'o2', target: 'i2' },
    { source: 'a1', target: 'c1' },
    { source: 'a2', target: 'c2' },
    { source: 'a3', target: 'c3' },
    { source: 'a4', target: 'c4' },
    { source: 'a5', target: 'c3' },
    { source: 'i1', target: 'c1' },
    { source: 'i2', target: 'c2' },
    { source: 'i3', target: 'c3' },
    { source: 'i4', target: 'c4' }
  ]
};

const NODE_COLORS = {
  session: '#FFBF00',
  attempt: '#00FFFF',
  outcome: '#00FF41',
  insight: '#BD00FF',
  concept: '#FF00FF'
};

/* ---------- SVG placeholder portraits (geometric wireframe) ---------- */
function portraitSVG(char, size = 220) {
  const a = char.accent;
  const col = { cyan: '#00FFFF', magenta: '#FF00FF', amber: '#FFBF00' }[a] || '#00FFFF';
  const col2 = { cyan: '#7FFFFF', magenta: '#FF7FFF', amber: '#FFDD66' }[a] || '#7FFFFF';
  const bg = `#0D1420`;

  // Distinctive silhouettes per character id
  let silhouette = '';
  if (char.id === 'elara') {
    silhouette = `
      <path d="M110 60 C 130 60, 148 78, 148 100 C 148 120, 135 140, 110 138 C 85 140, 72 120, 72 100 C 72 78, 90 60, 110 60 Z" fill="none" stroke="${col}" stroke-width="1.2"/>
      <path d="M72 90 L 72 72 L 110 52 L 148 72 L 148 90" fill="none" stroke="${col}" stroke-width="1.2"/>
      <path d="M90 100 L 100 100 M 120 100 L 130 100" stroke="${col2}" stroke-width="1.4"/>
      <path d="M60 160 L 90 150 L 130 150 L 160 160 L 170 220 L 50 220 Z" fill="none" stroke="${col}" stroke-width="1.2"/>
      <path d="M90 180 L 130 180 M 90 195 L 130 195" stroke="${col}" stroke-width="0.7" opacity="0.6"/>
      <circle cx="110" cy="100" r="2" fill="${col2}"/>
    `;
  } else if (char.id === 'orin') {
    silhouette = `
      <path d="M110 55 C 135 55, 155 78, 155 108 C 155 128, 140 145, 110 143 C 80 145, 65 128, 65 108 C 65 78, 85 55, 110 55 Z" fill="none" stroke="${col}" stroke-width="1.2"/>
      <path d="M65 88 Q 110 70, 155 88" fill="none" stroke="${col}" stroke-width="1.2"/>
      <path d="M90 105 L 100 105 M 120 105 L 130 105" stroke="${col2}" stroke-width="1.4"/>
      <path d="M55 160 L 95 150 L 125 150 L 165 160 L 175 220 L 45 220 Z" fill="none" stroke="${col}" stroke-width="1.2"/>
      <path d="M110 150 L 110 220" stroke="${col2}" stroke-width="1" opacity="0.5"/>
      <circle cx="155" cy="175" r="7" fill="none" stroke="${col2}" stroke-width="1"/>
      <path d="M148 175 L 162 175 M 155 168 L 155 182" stroke="${col2}" stroke-width="0.8"/>
    `;
  } else { // vex
    silhouette = `
      <circle cx="110" cy="120" r="50" fill="none" stroke="${col}" stroke-width="1.3"/>
      <circle cx="110" cy="120" r="36" fill="none" stroke="${col}" stroke-width="0.8" opacity="0.6"/>
      <circle cx="110" cy="120" r="16" fill="${col}" opacity="0.15"/>
      <circle cx="110" cy="120" r="10" fill="none" stroke="${col2}" stroke-width="1"/>
      <circle cx="110" cy="120" r="3" fill="${col2}"/>
      <path d="M60 120 L 40 120 M 160 120 L 180 120 M 110 70 L 110 50 M 110 170 L 110 190" stroke="${col}" stroke-width="1"/>
      <path d="M75 85 L 60 70 M 145 85 L 160 70 M 75 155 L 60 170 M 145 155 L 160 170" stroke="${col2}" stroke-width="0.9" opacity="0.7"/>
    `;
  }

  return `
<svg viewBox="0 0 220 220" xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" style="display:block;">
  <defs>
    <radialGradient id="bgrad-${char.id}" cx="50%" cy="50%" r="60%">
      <stop offset="0%" stop-color="${col}" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="${bg}" stop-opacity="1"/>
    </radialGradient>
    <pattern id="grid-${char.id}" width="20" height="20" patternUnits="userSpaceOnUse">
      <path d="M20 0 L 0 0 0 20" fill="none" stroke="${col}" stroke-opacity="0.08" stroke-width="0.5"/>
    </pattern>
  </defs>
  <rect width="220" height="220" fill="url(#bgrad-${char.id})"/>
  <rect width="220" height="220" fill="url(#grid-${char.id})"/>
  ${silhouette}
  <g stroke="${col2}" stroke-width="0.6" opacity="0.5">
    <path d="M12 12 L 32 12 M 12 12 L 12 32"/>
    <path d="M208 12 L 188 12 M 208 12 L 208 32"/>
    <path d="M12 208 L 32 208 M 12 208 L 12 188"/>
    <path d="M208 208 L 188 208 M 208 208 L 208 188"/>
  </g>
</svg>`;
}

function frameSVG(label, idx = 0, accent = 'cyan', aspect = '1 / 1') {
  const col = { cyan: '#00FFFF', magenta: '#FF00FF', amber: '#FFBF00', green: '#00FF41' }[accent] || '#00FFFF';
  const h = aspect === '3 / 4' ? 293 : 220;
  const w = 220;
  // Varied geometric composition per index so thumbs look non-identical
  const phase = idx * 37 % 360;
  const cx = 60 + (idx * 23) % 100;
  const cy = 80 + (idx * 41) % 120;
  const r  = 30 + (idx * 7)  % 40;
  return `
<svg viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" preserveAspectRatio="xMidYMid slice">
  <defs>
    <radialGradient id="fr-${idx}-${accent}" cx="${cx}" cy="${cy}" r="${r*2}" gradientUnits="userSpaceOnUse">
      <stop offset="0%"  stop-color="${col}" stop-opacity="0.35"/>
      <stop offset="60%" stop-color="${col}" stop-opacity="0.05"/>
      <stop offset="100%" stop-color="#0A0E14" stop-opacity="1"/>
    </radialGradient>
    <pattern id="gp-${idx}" width="16" height="16" patternUnits="userSpaceOnUse" patternTransform="rotate(${phase/20})">
      <path d="M16 0 L 0 0 0 16" fill="none" stroke="${col}" stroke-opacity="0.09" stroke-width="0.5"/>
    </pattern>
  </defs>
  <rect width="${w}" height="${h}" fill="#0D1420"/>
  <rect width="${w}" height="${h}" fill="url(#fr-${idx}-${accent})"/>
  <rect width="${w}" height="${h}" fill="url(#gp-${idx})"/>
  <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${col}" stroke-width="1" opacity="0.7"/>
  <circle cx="${cx}" cy="${cy}" r="${r*0.6}" fill="none" stroke="${col}" stroke-width="0.6" opacity="0.5"/>
  <line x1="0" y1="${cy}" x2="${w}" y2="${cy}" stroke="${col}" stroke-width="0.4" opacity="0.3" stroke-dasharray="3,5"/>
  <line x1="${cx}" y1="0" x2="${cx}" y2="${h}" stroke="${col}" stroke-width="0.4" opacity="0.3" stroke-dasharray="3,5"/>
  <g font-family="'JetBrains Mono', monospace" font-size="8" fill="${col}" opacity="0.85" letter-spacing="1">
    <text x="8" y="14">${label}</text>
    <text x="8" y="${h-10}">SEED · ${849000 + idx * 7}</text>
    <text x="${w-54}" y="${h-10}" opacity="0.6">2560×1440</text>
  </g>
  <g stroke="${col}" stroke-width="0.6" opacity="0.5">
    <path d="M4 4 L 14 4 M 4 4 L 4 14"/>
    <path d="M${w-4} 4 L ${w-14} 4 M ${w-4} 4 L ${w-4} 14"/>
    <path d="M4 ${h-4} L 14 ${h-4} M 4 ${h-4} L 4 ${h-14}"/>
    <path d="M${w-4} ${h-4} L ${w-14} ${h-4} M ${w-4} ${h-4} L ${w-4} ${h-14}"/>
  </g>
</svg>`;
}

function logoSVG() {
  return `
<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="logog" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#00FFFF"/>
      <stop offset="100%" stop-color="#FF00FF"/>
    </linearGradient>
  </defs>
  <path d="M24 4 L 42 14 L 42 34 L 24 44 L 6 34 L 6 14 Z" fill="none" stroke="url(#logog)" stroke-width="1.5"/>
  <path d="M24 12 L 34 18 L 34 30 L 24 36 L 14 30 L 14 18 Z" fill="none" stroke="#00FFFF" stroke-width="1" opacity="0.6"/>
  <circle cx="24" cy="24" r="3" fill="#00FFFF"/>
  <circle cx="24" cy="24" r="5" fill="none" stroke="#00FFFF" stroke-width="0.6" opacity="0.5"/>
</svg>`;
}
