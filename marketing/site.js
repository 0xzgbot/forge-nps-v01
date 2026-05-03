const header = document.querySelector("[data-elevate]");
const riverTrack = document.querySelector("[data-scroll-track]");
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

  const count = Math.max(34, Math.min(82, Math.floor(width / 18)));
  nodes = Array.from({ length: count }, (_, index) => ({
    x: Math.random() * width,
    y: Math.random() * height,
    vx: (Math.random() - 0.5) * 0.18,
    vy: (Math.random() - 0.5) * 0.18,
    pulse: Math.random() * Math.PI * 2,
    role: index % 9 === 0 ? "memory" : index % 5 === 0 ? "skill" : "signal",
  }));
}

function drawSignals(time) {
  if (reduceMotion) return;

  ctx.clearRect(0, 0, width, height);
  ctx.lineWidth = 1;

  for (const node of nodes) {
    node.x += node.vx;
    node.y += node.vy;
    node.pulse += 0.015;

    if (node.x < -40) node.x = width + 40;
    if (node.x > width + 40) node.x = -40;
    if (node.y < -40) node.y = height + 40;
    if (node.y > height + 40) node.y = -40;
  }

  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const a = nodes[i];
      const b = nodes[j];
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const distance = Math.hypot(dx, dy);
      if (distance > 154) continue;

      const alpha = (1 - distance / 154) * 0.22;
      const isMemoryPath = a.role === "memory" || b.role === "memory";
      ctx.strokeStyle = isMemoryPath
        ? `rgba(144, 255, 181, ${alpha})`
        : `rgba(53, 240, 208, ${alpha})`;
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
  }

  for (const node of nodes) {
    const radius = node.role === "memory" ? 2.8 : node.role === "skill" ? 2.2 : 1.5;
    const glow = 0.45 + Math.sin(node.pulse + time * 0.001) * 0.25;
    ctx.fillStyle = node.role === "memory"
      ? `rgba(144, 255, 181, ${glow})`
      : node.role === "skill"
        ? `rgba(255, 180, 95, ${glow})`
        : `rgba(53, 240, 208, ${glow})`;
    ctx.beginPath();
    ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
    ctx.fill();
  }

  requestAnimationFrame(drawSignals);
}

function updateScrollEffects() {
  const scrollY = window.scrollY;
  if (header) header.classList.toggle("is-elevated", scrollY > 24);

  if (riverTrack && window.innerWidth > 980) {
    const section = riverTrack.closest(".feature-river");
    const rect = section.getBoundingClientRect();
    const maxTravel = riverTrack.scrollWidth - riverTrack.clientWidth;
    const progress = Math.min(1, Math.max(0, -rect.top / (section.offsetHeight - window.innerHeight)));
    riverTrack.style.transform = `translateX(${-maxTravel * progress}px)`;
  } else if (riverTrack) {
    riverTrack.style.transform = "";
  }

  document.querySelectorAll("[data-parallax]").forEach((element) => {
    const rect = element.getBoundingClientRect();
    const progress = (rect.top - window.innerHeight * 0.5) / window.innerHeight;
    element.style.setProperty("--parallax", `${progress}`);
    const image = element.querySelector("img");
    if (image && window.innerWidth > 980) {
      image.style.transform = `translateY(${progress * -26}px) scale(1.01)`;
    } else if (image) {
      image.style.transform = "";
    }
  });
}

window.addEventListener("resize", () => {
  resizeCanvas();
  updateScrollEffects();
});

window.addEventListener("scroll", updateScrollEffects, { passive: true });

resizeCanvas();
updateScrollEffects();
requestAnimationFrame(drawSignals);
