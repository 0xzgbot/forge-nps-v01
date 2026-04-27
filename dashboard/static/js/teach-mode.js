/* ================================================================
   Teach Mode — Controlled learning demo UI
   ================================================================ */

(function() {
  window.initTeachMode = function(container) {
    if (!container) return;
    container.innerHTML = '';

    const card = h('div', { class: 'card', 'data-accent': 'purple', style: 'margin-bottom: 16px;' },
      h('div', { class: 'display', style: 'font-size: 12px; margin-bottom: 12px;' }, 'TEACH MODE'),
      h('div', { class: 'label', style: 'margin-bottom: 12px; opacity: 0.7;' },
        'Deliberately inject an error, watch Hermes learn from the failure, then see it fix the same shot automatically.'
      ),

      // Error type selector
      h('div', { class: 'setting-row', style: 'margin-bottom: 12px;' },
        h('span', { class: 'lbl' }, 'Error Type'),
        h('select', { id: 'teach-error-type', class: 'input' },
          h('option', { value: 'strip_hair_color' }, 'Strip Hair Color'),
          h('option', { value: 'wrong_lighting' }, 'Wrong Lighting'),
          h('option', { value: 'remove_anchor' }, 'Remove Anchor')
        )
      ),

      // Concept input
      h('div', { class: 'setting-row', style: 'margin-bottom: 12px;' },
        h('span', { class: 'lbl' }, 'Concept'),
        h('input', { id: 'teach-concept', class: 'input', value: 'Elara Vance portrait, cyberpunk neon glow' })
      ),

      // Run button
      h('button', {
        id: 'teach-run-btn',
        class: 'btn',
        style: 'align-self: flex-start;',
        onclick: runTeachCycle
      }, '▶ Run Teach Cycle'),

      // Results container
      h('div', { id: 'teach-results', class: 'teach-results', style: 'margin-top: 16px; display: none;' })
    );

    container.appendChild(card);
  };

  async function runTeachCycle() {
    const btn = $('#teach-run-btn');
    const results = $('#teach-results');
    const errorType = $('#teach-error-type').value;
    const concept = $('#teach-concept').value;

    btn.textContent = 'Running...';
    btn.disabled = true;
    results.style.display = 'block';
    results.innerHTML = '<div class="label" style="opacity:0.6;">Teaching Hermes...</div>';

    try {
      const r = await fetch('/api/hermes/teach', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concept, error_type: errorType })
      });
      const data = await r.json();

      results.innerHTML = '';
      results.appendChild(renderBeforeAfter(data));

      if (data.insight) {
        setTimeout(() => {
          results.appendChild(renderInsightBorn(data.insight));
        }, 400);
      }
    } catch (e) {
      results.innerHTML = '';
      results.appendChild(h('div', { class: 'label', style: 'color: var(--red);' }, 'Error: ' + String(e.message)));
    }

    btn.textContent = '▶ Run Teach Cycle';
    btn.disabled = false;
  }

  function renderBeforeAfter(data) {
    return h('div', { class: 'teach-before-after' },
      h('div', { class: 'teach-col teach-fail' },
        h('div', { class: 'teach-col-head' }, 'BEFORE'),
        h('div', { class: 'teach-score' }, `${data.before.score}`),
        h('div', { class: 'teach-status fail' }, data.before.status),
        h('div', { class: 'teach-prompt' }, data.before.prompt)
      ),
      h('div', { class: 'teach-arrow' }, '→'),
      h('div', { class: 'teach-col teach-pass' },
        h('div', { class: 'teach-col-head' }, 'AFTER'),
        h('div', { class: 'teach-score' }, `${data.after.score}`),
        h('div', { class: 'teach-status pass' }, data.after.status),
        h('div', { class: 'teach-prompt' }, data.after.prompt)
      )
    );
  }

  function renderInsightBorn(insight) {
    return h('div', { class: 'teach-insight-born', style: 'animation: insightPulse 600ms ease;' },
      h('span', { style: 'font-size: 20px; margin-right: 8px;' }, '💡'),
      h('span', {}, 'Hermes learned: '),
      h('strong', { style: 'color: var(--purple);' }, insight.rule || 'New rule'),
      h('span', { style: 'opacity: 0.6; margin-left: 8px;' }, `(conf ${Math.round((insight.confidence||0)*100)}%)`)
    );
  }
})();
