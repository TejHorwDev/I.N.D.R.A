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
  let cw = 0, ch = 0;

  function sizeOrbCanvas(){
    cw = window.innerWidth;
    ch = window.innerHeight;
    canvas.width = cw * dpr;
    canvas.height = ch * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  const COUNT = 900;
  const particles = [];

  function rand(a, b){ return a + Math.random() * (b - a); }

  for (let i = 0; i < COUNT; i++){
    const onShell = Math.random() < 0.6;
    const r = onShell ? rand(0.8, 1.0) : Math.cbrt(Math.random()) * 0.76;

    const u = Math.random() * 2 - 1;
    const theta = Math.random() * Math.PI * 2;
    const su = Math.sqrt(1 - u * u);

    // Agni "V" Shape Logic
    let isRight = Math.random() > 0.5;
    let t_edge = Math.random();
    
    // Top points of the V (y is negative, pointing up)
    let v_top_x = 1.0;
    let v_top_y = -1.0;
    
    // Bottom point of the V (y is positive, pointing down)
    let v_bottom_x = 0;
    let v_bottom_y = 1.0;
    
    let ax, ay;
    if (isRight) {
        ax = v_bottom_x + t_edge * (v_top_x - v_bottom_x);
        ay = v_bottom_y + t_edge * (v_top_y - v_bottom_y);
    } else {
        ax = v_bottom_x + t_edge * (-v_top_x - v_bottom_x);
        ay = v_bottom_y + t_edge * (v_top_y - v_bottom_y);
    }
    
    // Add particle thickness and noise
    ax += (Math.random() - 0.5) * 0.12;
    ay += (Math.random() - 0.5) * 0.12;
    
    // Scale slightly to fit nicely
    ax *= 0.65;
    ay *= 0.65;

    particles.push({
      ox: su * Math.cos(theta) * r,
      oy: su * Math.sin(theta) * r,
      oz: u * r,
      size: rand(0.9, 2.3) * (onShell ? 1 : 0.65),
      hue: rand(252, 282),
      sat: rand(28, 52),
      light: onShell ? rand(58, 80) : rand(34, 54),
      dispX: 0,
      dispY: 0,
      home_ox: su * Math.cos(theta) * r,
      home_oy: su * Math.sin(theta) * r,
      home_oz: u * r,
      target_ox: Math.cos(theta) * 1.0, // tighter ring
      target_oy: Math.sin(theta) * 1.0,
      target_oz: (Math.random() - 0.5) * 0.05,
      agni_ox: ax,
      agni_oy: ay,
      agni_oz: (Math.random() - 0.5) * 0.05,
      vx: 0,
      vy: 0,
      vz: 0
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

  
  let isVayu = false;
  let isAgni = false;
  let morphProgress = 0;
  
  window.activeWidgets = [];
window.updateWidgetBounds = function(bounds) {
    window.activeWidgets = bounds;
};
window.setTheme = function(theme) {
    isVayu = (theme === 'vayu');
    isAgni = (theme === 'agni');
    const root = document.documentElement;
    // EXPLOSION trigger
    for (let p of particles) {
      let explodeForce = 0.8 + Math.random() * 1.2;
      p.vx += (Math.random() - 0.5) * explodeForce;
      p.vy += (Math.random() - 0.5) * explodeForce;
      p.vz += (Math.random() - 0.5) * explodeForce;
    }
    pulse = 1.6; // blinding flash

    if (isVayu) {
      root.style.setProperty('--void', '#010c14');
      root.style.setProperty('--deep', '#031626');
      root.style.setProperty('--deep-2', '#05223a');
      root.style.setProperty('--halo-a', 'rgba(56,189,248,0.30)');
      root.style.setProperty('--halo-b', 'rgba(14,165,233,0.16)');
      root.style.setProperty('--ripple', 'rgba(125,211,252,0.55)');
      root.style.setProperty('--spark', 'rgba(186,230,253,0.9)');
      document.getElementById('aiStateText').style.color = 'rgba(56, 189, 248, 0.9)';
      document.getElementById('aiStateText').style.textShadow = '0 0 10px rgba(56, 189, 248, 0.6)';
    } else if (isAgni) {
      root.style.setProperty('--void', '#140103');
      root.style.setProperty('--deep', '#290209');
      root.style.setProperty('--deep-2', '#3a030c');
      root.style.setProperty('--halo-a', 'rgba(244, 63, 94, 0.25)');
      root.style.setProperty('--halo-b', 'rgba(225, 29, 72, 0.15)');
      root.style.setProperty('--ripple', 'rgba(251, 113, 133, 0.5)');
      root.style.setProperty('--spark', 'rgba(253, 164, 175, 0.9)');
      document.getElementById('aiStateText').style.color = 'rgba(244, 63, 94, 0.9)';
      document.getElementById('aiStateText').style.textShadow = '0 0 10px rgba(244, 63, 94, 0.6)';
    } else {
      root.style.removeProperty('--void');
      root.style.removeProperty('--deep');
      root.style.removeProperty('--deep-2');
      root.style.removeProperty('--halo-a');
      root.style.removeProperty('--halo-b');
      root.style.removeProperty('--ripple');
      root.style.removeProperty('--spark');
      document.getElementById('aiStateText').style.color = 'rgba(214,205,235,0.9)';
      document.getElementById('aiStateText').style.textShadow = '0 0 10px rgba(196,186,224,0.55)';
    }
  };

  function drawOrb(t, dt){
    if (!cw || !ch) return;

    spinAngle += (baseSpinSpeed + clickBoost) * dt;
    // Update morph progress smoothly
    if (isVayu) {
      morphProgress += (1 - morphProgress) * 0.05;
    } else if (isAgni) {
      morphProgress += (2 - morphProgress) * 0.05; // 2 for Agni
    } else {
      morphProgress += (0 - morphProgress) * 0.05; // 0 for Indra
    }

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

    // Calculate original responsive size to decouple from fullscreen canvas
    const vw22 = cw * 0.22;
    const clampedSize = Math.max(160, Math.min(300, vw22));
    
    const R = clampedSize * 0.40;
    const focal = clampedSize * 1.55;
    const ccx = cw / 2, ccy = ch / 2;
    const pulseScale = 1 + activePulse * 0.32;
    const repelRadius = clampedSize * 0.16;

    const projected = [];

    for (const p of particles){

      // Hooke's Law Spring Physics
      let gx = isAgni ? p.agni_ox : (isVayu ? p.target_ox : p.home_ox);
      let gy = isAgni ? p.agni_oy : (isVayu ? p.target_oy : p.home_oy);
      let gz = isAgni ? p.agni_oz : (isVayu ? p.target_oz : p.home_oz);
      
      let spring = 0.04;
      let friction = 0.82;
      
      p.vx += (gx - p.ox) * spring;
      p.vy += (gy - p.oy) * spring;
      p.vz += (gz - p.oz) * spring;
      
      p.vx *= friction;
      p.vy *= friction;
      p.vz *= friction;
      
      p.ox += p.vx;
      p.oy += p.vy;
      p.oz += p.vz;

      let cur_ox = p.ox;
      let cur_oy = p.oy;
      let cur_oz = p.oz;

      // Z-axis rotation for Vayu ring (wheel spin)
      let vx = cur_ox * cY - cur_oy * sY;
      let vy = cur_ox * sY + cur_oy * cY;
      let vz = cur_oz;

      // Y-axis rotation for Indra orb
      let ix = cur_ox * cY - cur_oz * sY;
      let iy = cur_oy;
      let iz = cur_ox * sY + cur_oz * cY;

      // Fixed position for Agni (no spin)
      let ax = cur_ox;
      let ay = cur_oy;
      let az = cur_oz;

      // Blend rotation axis based on morphProgress
      // 0 = Indra, 1 = Vayu, 2 = Agni
      let x1 = ix; let y1 = iy; let z1 = iz;
      if (morphProgress < 1) {
          x1 = ix + (vx - ix) * morphProgress;
          y1 = iy + (vy - iy) * morphProgress;
          z1 = iz + (vz - iz) * morphProgress;
      } else {
          x1 = vx + (ax - vx) * (morphProgress - 1);
          y1 = vy + (ay - vy) * (morphProgress - 1);
          z1 = vz + (az - vz) * (morphProgress - 1);
      }

      // rotate around X (tumble based on mouse)
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


      let finalHue = p.hue;
      let finalSat = p.sat;
      
      if (morphProgress > 0.01 && morphProgress < 1.01) {
         // Blending Indra to Vayu (Light Blue 195)
         let targetHue = 195 + (p.hue % 15); 
         let targetSat = Math.min(100, p.sat + 40);
         finalHue = p.hue + (targetHue - p.hue) * morphProgress;
         finalSat = p.sat + (targetSat - p.sat) * morphProgress;
      } else if (morphProgress >= 1.01) {
         // Blending Vayu to Agni (Cyberpunk Red 355)
         let vayuHue = 195 + (p.hue % 15);
         let vayuSat = Math.min(100, p.sat + 40);
         let agniHue = 355 + (p.hue % 10);
         let agniSat = Math.min(100, p.sat + 50);
         let t = morphProgress - 1;
         finalHue = vayuHue + (agniHue - vayuHue) * t;
         finalSat = vayuSat + (agniSat - vayuSat) * t;
      }

      projected.push({
        sx, sy, rad,
        a: Math.min(1, alpha),
        hue: finalHue,
        sat: finalSat,

        light: Math.min(92, p.light + activePulse * 16 + boost * 14),
        z: Z
      });
    }

    projected.sort((a, b) => a.z - b.z);

    ctx.clearRect(0, 0, cw, ch);
    
    // DRAW NEURAL LINKS
    if (window.activeWidgets && window.activeWidgets.length > 0) {
      ctx.save();
      ctx.lineWidth = (isVayu || isAgni) ? 1.5 : 2.0;
      for (let w of window.activeWidgets) {
        let alpha = w.op * ((isVayu || isAgni) ? 0.8 : 0.7);
        ctx.strokeStyle = isAgni ? `rgba(244, 63, 94, ${alpha})` : (isVayu ? `rgba(56, 189, 248, ${alpha})` : `rgba(147, 51, 234, ${alpha})`);
        ctx.setLineDash([8, 12]);
        ctx.lineDashOffset = -t * 0.08;
        
        ctx.beginPath();
        let isLeft = (w.x + w.w/2) < cw/2;
        let vw22 = cw * 0.22;
        let currentClampedSize = Math.max(160, Math.min(300, vw22));
        let orbEdgeOffset = currentClampedSize * 0.42; // Precisely matches the 0.40 particle radius
        let startX = isLeft ? cw/2 - orbEdgeOffset : cw/2 + orbEdgeOffset;
        let startY = ch/2;
        
        ctx.moveTo(startX, startY);
        
        let edgeX = isLeft ? w.x + w.w : w.x;
        let edgeY = w.y + w.h / 2;
        
        // Draw a smooth futuristic bezier curve
        let dist = Math.abs(edgeX - startX);
        let cp1x = isLeft ? startX - dist * 0.4 : startX + dist * 0.4;
        let cp1y = startY;
        let cp2x = isLeft ? edgeX + dist * 0.4 : edgeX - dist * 0.4;
        let cp2y = edgeY;
        
        ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, edgeX, edgeY);
        ctx.stroke();
        
        ctx.beginPath();
        ctx.arc(edgeX, edgeY, 4, 0, Math.PI*2);
        ctx.fillStyle = isAgni ? `rgba(244, 63, 94, ${w.op})` : (isVayu ? `rgba(56, 189, 248, ${w.op})` : `rgba(147, 51, 234, ${w.op})`);
        ctx.fill();
        ctx.shadowColor = ctx.fillStyle;
        ctx.shadowBlur = 12;
        ctx.stroke();
      }
      ctx.restore();
    }

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
    // Center the ripple inside the fullscreen field
    ripple.style.left = (cw / 2) + "px";
    ripple.style.top = (ch / 2) + "px";
    ripple.className = "ripple";
    fxField.appendChild(ripple);
    ripple.addEventListener("animationend", () => ripple.remove());

    const n = 8;
    for (let i = 0; i < n; i++){
      const spark = document.createElement("div");
      spark.className = "spark";
      spark.style.left = (cw / 2) + "px";
      spark.style.top = (ch / 2) + "px";
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
