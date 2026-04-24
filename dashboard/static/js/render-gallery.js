/* ================================================================
   Render Gallery — Real thumbnails from Spark / renders output dir
   ================================================================ */

(function() {
  window.initRenderGallery = async function(container) {
    if (!container) return;
    container.innerHTML = '<div class="label" style="opacity:0.5;">Loading renders...</div>';

    let images = [];
    try {
      const r = await fetch('/api/renders');
      if (r.ok) images = await r.json();
    } catch (e) {
      // Fallback: scan local renders/ directory via static files
    }

    // If API returned nothing, fall back to a few known static renders
    if (!images.length) {
      images = [
        { src: '/static/renders/sample_01.png', prompt: 'Elara Vance portrait, cyberpunk neon', score: 92, status: 'PASS' },
        { src: '/static/renders/sample_02.png', prompt: 'Concept art: neon alleyway', score: 87, status: 'PASS' },
        { src: '/static/renders/sample_03.png', prompt: 'Character turnaround sheet', score: 95, status: 'PASS' },
        { src: '/static/renders/fail_01.png', prompt: 'Elara without hair color (injected)', score: 34, status: 'FAIL' },
      ];
    }

    container.innerHTML = '';
    const grid = h('div', { class: 'render-grid' });

    images.forEach(img => {
      const el = h('div', { class: 'render-thumb', onclick: () => openLightbox(img) },
        h('img', { src: img.src, loading: 'lazy', alt: img.prompt }),
        h('div', { class: 'render-thumb-meta' },
          h('span', { class: 'render-thumb-prompt' }, truncate(img.prompt, 40)),
          h('span', {
            class: 'render-thumb-score',
            'data-status': img.status || (img.score >= 70 ? 'PASS' : 'FAIL')
          }, `${img.score}`)
        )
      );
      grid.appendChild(el);
    });

    container.appendChild(grid);
  };

  function truncate(s, n) {
    return s.length > n ? s.slice(0, n - 1) + '…' : s;
  }

  window.openLightbox = function(img) {
    const lb = h('div', {
      class: 'lightbox',
      onclick: (e) => { if (e.target === lb) lb.remove(); }
    },
      h('div', { class: 'lightbox-inner' },
        h('img', { src: img.src, alt: img.prompt }),
        h('div', { class: 'lightbox-caption' },
          h('div', {}, img.prompt),
          h('div', { style: 'opacity: 0.6; margin-top: 4px;' },
            `Score: ${img.score} · ${img.status || (img.score >= 70 ? 'PASS' : 'FAIL')}`
          )
        ),
        h('button', {
          class: 'lightbox-close',
          onclick: () => lb.remove()
        }, '×')
      )
    );
    document.body.appendChild(lb);
  };
})();
