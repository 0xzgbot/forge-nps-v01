/* ================================================================
   Hermes Live Panel — Real-time decision event stream
   ================================================================ */

(function() {
  const PANEL_ID = 'hermes-panel';
  const TOGGLE_ID = 'hermes-toggle';
  const MAX_EVENTS = 50;
  let ws = null;
  let events = [];
  let connected = false;

  const EVENT_META = {
    DISPATCH_START:     { icon: '🚀', color: 'cyan',  label: 'Dispatch' },
    MEMORY_QUERY:       { icon: '🔍', color: 'cyan',  label: 'Query' },
    MEMORY_RECALL:      { icon: '🧠', color: 'amber', label: 'Recall' },
    PROMPT_AUGMENT:     { icon: '✨', color: 'magenta', label: 'Augment' },
    DISPATCH_SHOT:      { icon: '⚡', color: 'green', label: 'Shot' },
    OUTCOME_RECORD:     { icon: '✅', color: 'green', label: 'Outcome' },
    CONSOLIDATION_START:{ icon: '💤', color: 'purple', label: 'Dream' },
    INSIGHT_BORN:       { icon: '💡', color: 'purple', label: 'Insight' },
  };

  function ensurePanel() {
    if ($( '#' + PANEL_ID)) return;

    const panel = h('div', { id: PANEL_ID, class: 'hermes-panel' },
      h('div', { class: 'hermes-panel-head' },
        h('span', { class: 'hermes-panel-title' }, 'HERMES LIVE'),
        h('span', { class: 'hermes-panel-status' + (connected ? ' connected' : '') }, connected ? '● LIVE' : '○ OFF'),
        h('button', { class: 'hermes-panel-close', onclick: togglePanel }, '×')
      ),
      h('div', { id: 'hermes-events', class: 'hermes-events' })
    );
    document.body.appendChild(panel);
  }

  function ensureToggle() {
    if ($( '#' + TOGGLE_ID)) return;
    const btn = h('button', {
      id: TOGGLE_ID,
      class: 'hermes-toggle-btn',
      title: 'Hermes Live Panel',
      onclick: togglePanel
    }, '🧠');
    document.body.appendChild(btn);
  }

  function togglePanel() {
    const p = $('#' + PANEL_ID);
    if (p) p.classList.toggle('open');
  }

  function addEvent(type, payload, ts) {
    const meta = EVENT_META[type] || { icon: '◆', color: 'text-secondary', label: type };
    const time = new Date(ts * 1000).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });

    let detail = '';
    if (type === 'MEMORY_RECALL') detail = payload.fix ? `Fix: "${payload.fix.slice(0, 60)}"` : '';
    if (type === 'PROMPT_AUGMENT') detail = payload.rule ? `Rule: "${payload.rule.slice(0, 60)}"` : `Recalled ${payload.recall_count} memories`;
    if (type === 'DISPATCH_SHOT') detail = payload.shot_id;
    if (type === 'OUTCOME_RECORD') detail = `${payload.success ? 'PASS' : 'FAIL'} · Score ${payload.score}`;
    if (type === 'INSIGHT_BORN') detail = `"${payload.rule.slice(0, 60)}" (conf ${Math.round((payload.confidence||0)*100)}%)`;

    const ev = { type, time, meta, detail };
    events.unshift(ev);
    if (events.length > MAX_EVENTS) events.pop();
    renderEvents();
  }

  function renderEvents() {
    const container = $('#hermes-events');
    if (!container) return;
    container.innerHTML = '';
    events.forEach(ev => {
      container.append(h('div', { class: 'hermes-event' },
        h('span', { class: 'hermes-event-time' }, ev.time),
        h('span', { class: 'hermes-event-icon', style: `color: var(--${ev.meta.color})` }, ev.meta.icon),
        h('span', { class: 'hermes-event-label', style: `color: var(--${ev.meta.color})` }, ev.meta.label),
        ev.detail ? h('span', { class: 'hermes-event-detail' }, ev.detail) : null
      ));
    });
  }

  function connect() {
    if (ws) return;
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${proto}//${location.host}/ws/hermes`);
    ws.onopen = () => {
      connected = true;
      updateStatus();
    };
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type && msg.payload) {
          addEvent(msg.type, msg.payload, msg.timestamp || Date.now()/1000);
        }
      } catch (_) {}
    };
    ws.onclose = () => {
      connected = false;
      updateStatus();
      ws = null;
      setTimeout(connect, 3000);
    };
    ws.onerror = () => {
      connected = false;
      updateStatus();
    };
  }

  function updateStatus() {
    const st = $('.hermes-panel-status');
    if (st) {
      st.textContent = connected ? '● LIVE' : '○ OFF';
      st.classList.toggle('connected', connected);
    }
  }

  window.initHermesPanel = function() {
    ensureToggle();
    ensurePanel();
    connect();
  };
})();
