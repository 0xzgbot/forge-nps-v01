/* ================================================================
   Spark Monitor Widget — Live queue progress in top bar
   ================================================================ */

(function() {
  let ws = null;
  let state = { spark_alive: false, summary: { total:0, queued:0, running:0, completed:0, failed:0 }, jobs: [] };

  function ensureWidget() {
    if ($('#spark-widget')) return;
    const widget = h('div', { id: 'spark-widget', class: 'spark-widget' },
      h('span', { class: 'spark-dot' }),
      h('span', { class: 'spark-label' }, 'SPARK'),
      h('span', { class: 'spark-queue' }, '—')
    );
    const target = $('.topbar-right');
    if (target) target.insertBefore(widget, target.firstChild);
  }

  function updateWidget() {
    const dot = $('.spark-dot');
    const label = $('.spark-queue');
    if (!dot || !label) return;

    const alive = state.spark_alive;
    const s = state.summary;
    dot.className = 'spark-dot ' + (alive ? 'online' : 'offline');
    label.textContent = alive
      ? `${s.running}R · ${s.queued}Q · ${s.completed}D`
      : 'OFFLINE';
  }

  function connect() {
    if (ws) return;
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${proto}//${location.host}/ws/spark`);
    ws.onopen = () => {};
    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.spark_alive !== undefined) {
          state.spark_alive = msg.spark_alive;
          state.summary = msg.summary || state.summary;
          state.jobs = msg.jobs || state.jobs;
          updateWidget();
        }
      } catch (_) {}
    };
    ws.onclose = () => { ws = null; setTimeout(connect, 5000); };
    ws.onerror = () => { state.spark_alive = false; updateWidget(); };
  }

  // Also poll REST as fallback
  async function poll() {
    try {
      const r = await fetch('/api/spark/state');
      if (r.ok) {
        state = await r.json();
        updateWidget();
      }
    } catch (_) {
      state.spark_alive = false;
      updateWidget();
    }
  }

  window.initSparkWidget = function() {
    ensureWidget();
    connect();
    poll();
    setInterval(poll, 5000);
  };
})();
