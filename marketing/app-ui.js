const canvas = document.getElementById("signalCanvas");
const ctx = canvas.getContext("2d");

let width = 0;
let height = 0;
let nodes = [];
let reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function resizeCanvas() {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  width = window.innerWidth;
  height = window.innerHeight;
  canvas.width = Math.floor(width * dpr);
  canvas.height = Math.floor(height * dpr);
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  nodes = Array.from({ length: Math.min(90, Math.max(42, Math.floor(width / 16))) }, (_, index) => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * 0.14,
    vy: (Math.random() - 0.5) * 0.14,
    kind: index % 7 === 0 ? "memory" : index % 5 === 0 ? "skill" : "signal",
    pulse: Math.random() * Math.PI * 2,
  }));
}

function draw(time) {
  if (reduceMotion) return;

  ctx.clearRect(0, 0, width, height);

  for (const node of nodes) {
    node.x += node.vx;
    node.y += node.vy;
    node.pulse += 0.018;

    if (node.x < -30) node.x = width + 30;
    if (node.x > width + 30) node.x = -30;
    if (node.y < -30) node.y = height + 30;
    if (node.y > height + 30) node.y = -30;
  }

  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const a = nodes[i];
      const b = nodes[j];
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      if (distance > 142) continue;

      const alpha = (1 - distance / 142) * 0.22;
      ctx.strokeStyle = a.kind === "memory" || b.kind === "memory"
        ? `rgba(144,255,181,${alpha})`
        : a.kind === "skill" || b.kind === "skill"
          ? `rgba(255,180,95,${alpha})`
          : `rgba(53,240,208,${alpha})`;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
  }

  for (const node of nodes) {
    const alpha = 0.45 + Math.sin(node.pulse + time * 0.0012) * 0.2;
    const radius = node.kind === "memory" ? 2.8 : node.kind === "skill" ? 2.3 : 1.5;
    ctx.fillStyle = node.kind === "memory"
      ? `rgba(144,255,181,${alpha})`
      : node.kind === "skill"
        ? `rgba(255,180,95,${alpha})`
        : `rgba(53,240,208,${alpha})`;
    ctx.beginPath();
    ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
    ctx.fill();
  }

  requestAnimationFrame(draw);
}

document.querySelectorAll(".skill-matrix button, .chip").forEach((control) => {
  control.addEventListener("click", () => {
    control.classList.toggle("loaded");
    control.classList.toggle("active");
  });
});

resizeCanvas();
window.addEventListener("resize", resizeCanvas);
requestAnimationFrame(draw);
