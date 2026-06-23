(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  /* ------------------------------------------------------------------
     Starfield background (subtle, ambient — not part of the orb)
  ------------------------------------------------------------------ */
  const starCanvas = document.getElementById("stars");
  const sctx = starCanvas.getContext("2d");
  let stars = [], sw = 0, sh = 0;

  function sizeStarCanvas(){
    sw = window.innerWidth;
    sh = window.innerHeight;
    starCanvas.width = sw * dpr;
    starCanvas.height = sh * dpr;
    starCanvas.style.width = sw + "px";
    starCanvas.style.height = sh + "px";
    sctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const count = Math.round((sw * sh) / 11000);
    stars = new Array(count).fill(0).map(() => ({
      x: Math.random() * sw,
      y: Math.random() * sh,
      r: Math.random() * 1.1 + 0.2,
      baseAlpha: Math.random() * 0.45 + 0.15,
      speed: Math.random() * 0.5 + 0.15,
      phase: Math.random() * Math.PI * 2,
      drift: Math.random() * 4 + 1.5
    }));
  }

  function drawStars(t){
    sctx.clearRect(0, 0, sw, sh);
    for (const s of stars){
      const a = s.baseAlpha * (0.55 + 0.45 * Math.sin(t * 0.0009 * s.speed + s.phase));
      sctx.beginPath();
      sctx.fillStyle = `rgba(200,194,224,${a.toFixed(3)})`;
      sctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
      sctx.fill();
      if (!reduceMotion){
        s.y += s.drift * 0.002;
        if (s.y > sh + 2){ s.y = -2; s.x = Math.random() * sw; }
      }
    }
  }

  /* ------------------------------------------------------------------
     Particle sphere — the orb itself
  ------------------------------------------------------------------ */
  const canvas = document.getElementById("orbCanvas");
  const ctx = canvas.getContext("2d");
  let size = 0; // logical (CSS) px, square

  function sizeOrbCanvas(){
    const rect = canvas.getBoundingClientRect();
    size = rect.width;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  const COUNT = 900;
  const particles = [];

  function rand(a, b){ return a + Math.random() * (b - a); }

  for (let i = 0; i < COUNT; i++){
    const onShell = Math.random() < 0.6;
    const r = onShell ? rand(0.8, 1.0) : Math.cbrt(Math.random()) * 0.76;

    // uniform random direction on the unit sphere
    const u = Math.random() * 2 - 1;
    const theta = Math.random() * Math.PI * 2;
    const su = Math.sqrt(1 - u * u);

    particles.push({
      ox: su * Math.cos(theta) * r,
      oy: su * Math.sin(theta) * r,
      oz: u * r,
      size: rand(0.9, 2.3) * (onShell ? 1 : 0.65),
      hue: rand(252, 282),
      sat: rand(28, 52),
      light: onShell ? rand(58, 80) : rand(34, 54),
      dispX: 0,
      dispY: 0
    });
  }

  // interaction state
  let spinAngle = 0;
  let clickBoost = 0;      // extra spin speed, decays after a click
  let pulse = 0;           // outward expansion pulse, decays after a click
  const baseSpinSpeed = 0.00026; // rad / ms
  let aiState = "INITIALISING";

  let mouseNX = 0, mouseNY = 0;       // -1..1 relative to canvas center, for gentle tilt
  let mouseCX = null, mouseCY = null; // mouse position in canvas-local px, for repel

  function onPointer(clientX, clientY){
    const rect = canvas.getBoundingClientRect();
    const relX = clientX - rect.left;
    const relY = clientY - rect.top;
    mouseCX = relX;
    mouseCY = relY;
    mouseNX = Math.max(-1, Math.min(1, (relX - rect.width / 2) / (rect.width / 2)));
    mouseNY = Math.max(-1, Math.min(1, (relY - rect.height / 2) / (rect.height / 2)));
  }

  window.addEventListener("mousemove", (e) => onPointer(e.clientX, e.clientY), { passive: true });
  window.addEventListener("touchmove", (e) => {
    if (e.touches && e.touches[0]) onPointer(e.touches[0].clientX, e.touches[0].clientY);
  }, { passive: true });
  window.addEventListener("mouseleave", () => { mouseCX = null; mouseCY = null; });

  function drawOrb(t, dt){
    if (!size) return;

    spinAngle += (baseSpinSpeed + clickBoost) * dt;
    clickBoost *= 0.965;
    
    // Persistent state modifiers
    let targetPulse = 0;
    if (aiState === "SPEAKING") {
      targetPulse = 0.5 + Math.sin(t * 0.01) * 0.3; // Rapid pulsating
      clickBoost = 0.0015; // Keep it spinning fast
    } else if (aiState === "THINKING") {
      targetPulse = 0.1 + Math.sin(t * 0.002) * 0.1; // Slow deep throb
    } else if (aiState === "LISTENING") {
      // Smooth, gentle undulation to indicate active listening
      targetPulse = 0.2 + Math.sin(t * 0.004) * 0.08; 
    } else if (aiState === "STARTING" || aiState === "INITIALISING") {
      targetPulse = 0.8 + Math.sin(t * 0.008) * 0.4; // Strong, wide pulses for boot up
      clickBoost = 0.002; // Faster spin for boot
    }
    
    // Blend the click burst pulse with the state pulse
    const activePulse = Math.max(pulse, targetPulse);
    pulse *= 0.93;

    const tumble = reduceMotion ? 0 : Math.sin(t * 0.00014) * 0.16 - mouseNY * 0.22;
    const yaw = spinAngle + (reduceMotion ? 0 : mouseNX * 0.22);

    const cY = Math.cos(yaw),    sY = Math.sin(yaw);
    const cX = Math.cos(tumble), sX = Math.sin(tumble);

    const R = size * 0.40;
    const focal = size * 1.55;
    const ccx = size / 2, ccy = size / 2;
    const pulseScale = 1 + activePulse * 0.32;
    const repelRadius = size * 0.16;

    const projected = [];

    for (const p of particles){
      // rotate around Y
      let x1 = p.ox * cY - p.oz * sY;
      let z1 = p.ox * sY + p.oz * cY;
      let y1 = p.oy;
      // rotate around X
      let y2 = y1 * cX - z1 * sX;
      let z2 = y1 * sX + z1 * cX;
      let x2 = x1;

      x2 *= pulseScale; y2 *= pulseScale; z2 *= pulseScale;

      const X = x2 * R, Y = y2 * R, Z = z2 * R;
      const persp = focal / (focal - Z);
      let sx = ccx + X * persp;
      let sy = ccy + Y * persp;

      // pointer repel — push nearby particles outward, spring back smoothly
      let tdx = 0, tdy = 0;
      if (mouseCX !== null && !reduceMotion){
        const dx = sx - mouseCX, dy = sy - mouseCY;
        const dist = Math.hypot(dx, dy);
        if (dist < repelRadius && dist > 0.001){
          const f = (1 - dist / repelRadius);
          const push = f * f * 26;
          tdx = (dx / dist) * push;
          tdy = (dy / dist) * push;
        }
      }
      p.dispX += (tdx - p.dispX) * 0.18;
      p.dispY += (tdy - p.dispY) * 0.18;

      sx += p.dispX;
      sy += p.dispY;

      const depthT = (Z / R + 1) / 2; // 0 back .. 1 front
      const boost = Math.min(1, (Math.abs(p.dispX) + Math.abs(p.dispY)) / 20);
      const alpha = (0.18 + depthT * 0.72) * (1 + boost * 0.6 + activePulse * 0.5);
      const rad = p.size * (0.55 + depthT * 0.85) * (1 + boost * 0.5 + activePulse * 0.35);

      projected.push({
        sx, sy, rad,
        a: Math.min(1, alpha),
        hue: p.hue,
        sat: p.sat,
        light: Math.min(92, p.light + activePulse * 16 + boost * 14),
        z: Z
      });
    }

    projected.sort((a, b) => a.z - b.z);

    ctx.clearRect(0, 0, size, size);
    ctx.globalCompositeOperation = "lighter";
    for (const q of projected){
      ctx.globalAlpha = q.a;
      ctx.fillStyle = `hsl(${q.hue.toFixed(0)} ${q.sat.toFixed(0)}% ${q.light.toFixed(0)}%)`;
      ctx.beginPath();
      ctx.arc(q.sx, q.sy, Math.max(0.4, q.rad), 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }

  /* ------------------------------------------------------------------
     Click / tap — expansion pulse + spin-up + screen-space burst
  ------------------------------------------------------------------ */
  const fxField = document.getElementById("fxField");

  function burst(){
    pulse = 1;
    clickBoost = 0.0016;

    const ripple = document.createElement("div");
    ripple.className = "ripple";
    fxField.appendChild(ripple);
    ripple.addEventListener("animationend", () => ripple.remove());

    const n = 8;
    for (let i = 0; i < n; i++){
      const spark = document.createElement("div");
      spark.className = "spark";
      const angle = (Math.PI * 2 * i) / n + Math.random() * 0.35;
      const dist = 50 + Math.random() * 60;
      const dur = 550 + Math.random() * 350;
      spark.style.setProperty("--tx", `${Math.cos(angle) * dist}px`);
      spark.style.setProperty("--ty", `${Math.sin(angle) * dist}px`);
      spark.style.setProperty("--dur", `${dur}ms`);
      fxField.appendChild(spark);
      spark.addEventListener("animationend", () => spark.remove());
    }
  }

  canvas.addEventListener("click", burst);
  canvas.addEventListener("touchstart", (e) => {
    if (e.touches && e.touches[0]){
      onPointer(e.touches[0].clientX, e.touches[0].clientY);
    }
    burst();
  }, { passive: true });

  /* ------------------------------------------------------------------
     Main loop
  ------------------------------------------------------------------ */
  let lastT = performance.now();

  function frame(t){
    const dt = Math.min(48, t - lastT);
    lastT = t;
    drawStars(t);
    drawOrb(t, dt);
    requestAnimationFrame(frame);
  }

  function handleResize(){
    sizeStarCanvas();
    sizeOrbCanvas();
  }
  window.addEventListener("resize", handleResize);

  requestAnimationFrame(() => {
    sizeStarCanvas();
    sizeOrbCanvas();
    requestAnimationFrame(frame);
  });
  // Expose global API for INDRA to control the orb
  window.INDRAOrb = {
    setState: function(state) {
      aiState = state;
      if (state === "SPEAKING") {
        pulse = 1.0; // Initial burst
      } else if (state === "LISTENING") {
        pulse = 0.5; // Initial burst
      } else if (state === "STARTING") {
        pulse = 1.2; // Massive burst on boot
      }
    },
    triggerBurst: burst
  };

})();
