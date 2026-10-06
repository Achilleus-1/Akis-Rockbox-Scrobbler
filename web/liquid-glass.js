'use strict';

// Two local WebGL passes: an Aero environment texture, then rounded glass lenses.
// The DOM stays above the canvas: text, focus, input and hit testing remain native.
(() => {
  const toggle = document.getElementById('live-glass');
  const status = document.getElementById('glass-status');
  const canvas = document.createElement('canvas');
  canvas.className = 'liquid-glass-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const preference = 'akis-scrobbler-live-glass';
  let enabled = true;
  try { enabled = localStorage.getItem(preference) !== 'off'; } catch { /* Storage is optional. */ }
  toggle.checked = enabled;
  const gl = canvas.getContext('webgl', {
    alpha: false, antialias: false, depth: false, stencil: false,
    powerPreference: 'low-power', preserveDrawingBuffer: false
  });
  if (!gl) {
    toggle.checked = false;
    toggle.disabled = true;
    status.textContent = 'Static glass is active on this device.';
    canvas.remove();
    return;
  }

  const vertex = `
    attribute vec2 aPosition;
    varying vec2 vUV;
    void main() {
      vUV = aPosition * 0.5 + 0.5;
      gl_Position = vec4(aPosition, 0.0, 1.0);
    }
  `;
  const environment = `
    precision mediump float;
    varying vec2 vUV;
    uniform vec2 uResolution;
    uniform vec2 uPointer;
    uniform float uTime;
    float cloud(vec2 p, vec2 center, vec2 stretch) {
      vec2 d = (p - center) / stretch;
      return exp(-dot(d, d) * 2.0);
    }
    void main() {
      vec2 p = vec2(vUV.x, 1.0 - vUV.y);
      float t = uTime * 0.045;
      vec3 color = vec3(0.85, 0.94, 0.97);
      color = mix(color, vec3(0.32, 0.78, 0.89), cloud(p, vec2(0.13 + sin(t)*0.04, 0.20), vec2(0.60, 0.65))*0.78);
      color = mix(color, vec3(0.76, 0.73, 0.93), cloud(p, vec2(0.90, 0.25 + cos(t)*0.05), vec2(0.46, 0.58))*0.65);
      color = mix(color, vec3(0.46, 0.87, 0.69), cloud(p, vec2(0.78, 0.88), vec2(0.65, 0.53))*0.70);
      // Broad, flowing ribbons give the lenses an actual texture to bend.
      float ribbon = p.y - (0.28 + 0.25*sin(p.x*4.1 + t) + 0.045*sin(p.x*10.0-t*0.8));
      color = mix(color, vec3(0.94, 0.99, 1.0), exp(-ribbon*ribbon*200.0)*0.68);
      float seam = abs(ribbon - 0.038);
      color += vec3(0.17, 0.20, 0.22) * exp(-seam*seam*14000.0);
      float second = p.y - (0.74 + 0.17*cos(p.x*5.2 - t*0.7));
      color = mix(color, vec3(0.46, 0.80, 0.88), exp(-second*second*550.0)*0.24);
      color += vec3(0.15) * exp(-pow(second - 0.019, 2.0)*14000.0);
      // Soft light tracks the pointer, without painting over interface text.
      vec2 light = (p*uResolution - uPointer) / 260.0;
      color += vec3(0.07, 0.08, 0.085)*exp(-dot(light, light));
      gl_FragColor = vec4(color, 1.0);
    }
  `;
  const glass = `
    precision mediump float;
    varying vec2 vUV;
    uniform sampler2D uScene;
    uniform vec2 uResolution;
    uniform vec4 uRect;
    uniform float uRadius;
    uniform float uMaterial;
    uniform vec3 uPointer;
    uniform vec4 uRipples[4];
    float roundedBox(vec2 p) {
      vec2 q = abs(p) - (uRect.zw*0.5 - uRadius);
      return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - uRadius;
    }
    vec2 sceneUV(vec2 p) {
      return clamp(vec2(p.x/uResolution.x, 1.0-p.y/uResolution.y), 0.002, 0.998);
    }
    void main() {
      vec2 screen = vec2(vUV.x, 1.0-vUV.y)*uResolution;
      vec2 local = screen - uRect.xy - uRect.zw*0.5;
      float d = roundedBox(local);
      if (d > 1.5) discard;
      vec2 normal = normalize(vec2(roundedBox(local+vec2(0.7,0.0))-roundedBox(local-vec2(0.7,0.0)),
                                  roundedBox(local+vec2(0.0,0.7))-roundedBox(local-vec2(0.0,0.7))) + vec2(0.0001));
      float rim = exp(min(d, 0.0)/11.0);
      vec2 bend = normal * rim * (17.0 + min(uRadius, 28.0)*0.4);
      vec2 delta = screen - uPointer.xy;
      float distanceToPointer = length(delta);
      float hover = exp(-distanceToPointer*distanceToPointer/22000.0)*uPointer.z;
      bend += delta * hover * 0.18;
      for (int i=0; i<4; i++) {
        vec2 wave = screen - uRipples[i].xy;
        float distanceToWave = length(wave);
        float age = uRipples[i].z;
        float ring = distanceToWave - age*220.0;
        float amplitude = exp(-age*2.0)*exp(-ring*ring/1200.0)*uRipples[i].w;
        bend += wave/max(distanceToWave,1.0)*sin(ring*0.085)*amplitude*13.0;
      }
      vec2 samplePoint = screen - bend;
      vec2 dispersion = normal*rim*1.35;
      vec3 color = vec3(texture2D(uScene,sceneUV(samplePoint+dispersion)).r,
                        texture2D(uScene,sceneUV(samplePoint)).g,
                        texture2D(uScene,sceneUV(samplePoint-dispersion)).b);
      // Frosted center keeps contrast; the edge retains the strongest refraction.
      vec3 soft = texture2D(uScene,sceneUV(samplePoint+vec2(3.0,2.0))).rgb;
      soft += texture2D(uScene,sceneUV(samplePoint-vec2(3.0,2.0))).rgb;
      color = mix(color, soft*0.5, (1.0-rim)*0.32);
      if (uMaterial > 0.5) {
        vec3 tint = uMaterial > 1.5 ? vec3(0.02,0.38,0.59) : vec3(0.045,0.29,0.43);
        color = mix(color, tint, 0.77);
      } else {
        color = mix(color, vec3(0.98,0.995,1.0), 0.35 + (1.0-rim)*0.13);
      }
      vec2 lightDirection = normalize(uPointer.xy - (uRect.xy+uRect.zw*0.5) + vec2(-180.0,-230.0));
      float reflection = pow(max(dot(normal,lightDirection),0.0),5.0);
      color += vec3(0.18,0.21,0.23)*rim*reflection;
      color += vec3(0.11,0.14,0.16)*hover;
      float edge = exp(-abs(d+1.5)*1.0);
      color += vec3(0.35)*edge*(0.25+reflection*0.75);
      gl_FragColor = vec4(color, 1.0-smoothstep(-0.75,1.0,d));
    }
  `;
  const copy = `
    precision mediump float;
    varying vec2 vUV;
    uniform sampler2D uScene;
    void main() { gl_FragColor = texture2D(uScene,vUV); }
  `;

  let resources, frame = 0, dirty = true, lastDraw = -Infinity, lastLayout = -Infinity;
  let surfaces = [], width = 0, height = 0, lost = false;
  let elapsed = 0, lastTick = 0, rippleIndex = 0;
  const pointer = {x:-1000, y:-1000, targetX:-1000, targetY:-1000, active:0};
  const ripples = Array.from({length:4}, () => ({x:0,y:0,start:-100}));
  const rectSelector = '.sidebar, .topbar, .page-heading, .upload-card, .connection-card, .queue-card, .reading-view article, .nav-item.active, .account-chip, .button';

  function program(fragment) {
    const shaders = [[gl.VERTEX_SHADER,vertex],[gl.FRAGMENT_SHADER,fragment]].map(([type,source]) => {
      const shader = gl.createShader(type);
      gl.shaderSource(shader,source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader,gl.COMPILE_STATUS)) {
        const reason = gl.getShaderInfoLog(shader);
        gl.deleteShader(shader);
        throw new Error(reason);
      }
      return shader;
    });
    const result = gl.createProgram();
    shaders.forEach(shader => gl.attachShader(result,shader));
    gl.linkProgram(result);
    shaders.forEach(shader => gl.deleteShader(shader));
    if (!gl.getProgramParameter(result,gl.LINK_STATUS)) {
      const reason = gl.getProgramInfoLog(result);
      gl.deleteProgram(result);
      throw new Error(reason);
    }
    const uniforms = {};
    for (const name of ['uResolution','uPointer','uTime','uScene','uRect','uRadius','uMaterial','uRipples[0]']) {
      uniforms[name] = gl.getUniformLocation(result,name);
    }
    return {program:result,position:gl.getAttribLocation(result,'aPosition'),uniforms};
  }

  function initialize() {
    resources = {environment:program(environment),glass:program(glass),copy:program(copy)};
    resources.quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER,resources.quad);
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
    resources.texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D,resources.texture);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
    resources.scene = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER,resources.scene);
    gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,resources.texture,0);
    width = height = 0;
    resize();
    if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) throw new Error('Glass framebuffer unavailable');
    gl.bindFramebuffer(gl.FRAMEBUFFER,null);
    lost = false;
    dirty = true;
    canvas.dataset.renderer = 'webgl';
    sync();
  }

  function resize() {
    const nextWidth = document.documentElement.clientWidth;
    const nextHeight = window.innerHeight;
    if (width === nextWidth && height === nextHeight) return;
    width = Math.max(1,nextWidth);
    height = Math.max(1,nextHeight);
    // Cap resolution and frame rate, including on high-DPI displays.
    const scale = Math.min(devicePixelRatio || 1,1.25,Math.sqrt(1400000/(width*height)));
    canvas.width = Math.max(1,Math.round(width*scale));
    canvas.height = Math.max(1,Math.round(height*scale));
    gl.bindTexture(gl.TEXTURE_2D,resources.texture);
    gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,canvas.width,canvas.height,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
    dirty = true;
  }

  function measure() {
    surfaces = [];
    // Read geometry only after layout changes, never per fragment or per pointer event.
    for (const node of document.querySelectorAll(rectSelector)) {
      if (node.closest('dialog') || !node.getClientRects().length) continue;
      if (node.matches('.button') && node.closest('.queue-card,.reading-view')) continue;
      const rect = node.getBoundingClientRect();
      if (rect.bottom < 0 || rect.top > height || rect.right < 0 || rect.left > width) continue;
      const radius = Math.min(parseFloat(getComputedStyle(node).borderTopLeftRadius) || 0,rect.width/2,rect.height/2);
      const material = node.matches('.sidebar,.button.dark,.nav-item.active') ? 1 : node.matches('.button.primary') ? 2 : 0;
      surfaces.push({node,x:rect.x,y:rect.y,width:rect.width,height:rect.height,radius,material});
    }
    dirty = false;
  }

  function use(pass) {
    gl.useProgram(pass.program);
    gl.bindBuffer(gl.ARRAY_BUFFER,resources.quad);
    gl.enableVertexAttribArray(pass.position);
    gl.vertexAttribPointer(pass.position,2,gl.FLOAT,false,0,0);
    gl.uniform2f(pass.uniforms.uResolution,width,height);
    gl.uniform1i(pass.uniforms.uScene,0);
  }

  function draw() {
    gl.viewport(0,0,canvas.width,canvas.height);
    gl.disable(gl.SCISSOR_TEST);
    gl.disable(gl.BLEND);
    gl.bindFramebuffer(gl.FRAMEBUFFER,resources.scene);
    use(resources.environment);
    gl.uniform1f(resources.environment.uniforms.uTime,motion.matches ? 0 : elapsed);
    gl.uniform2f(resources.environment.uniforms.uPointer,pointer.x,pointer.y);
    // Unbind the scene texture while drawing into it: no texture feedback loop.
    gl.bindTexture(gl.TEXTURE_2D,null);
    gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
    gl.bindFramebuffer(gl.FRAMEBUFFER,null);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D,resources.texture);
    use(resources.copy);
    gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
    use(resources.glass);
    const uniforms = resources.glass.uniforms;
    gl.uniform3f(uniforms.uPointer,pointer.x,pointer.y,pointer.active);
    gl.uniform4fv(uniforms['uRipples[0]'],new Float32Array(ripples.flatMap(ripple => {
      const age = elapsed-ripple.start;
      return [ripple.x,ripple.y,Math.min(age,10),!motion.matches && age < 3 ? 1 : 0];
    })));
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);
    gl.enable(gl.SCISSOR_TEST);
    const scaleX = canvas.width/width, scaleY = canvas.height/height;
    for (const surface of surfaces) {
      const left = Math.max(0,Math.floor((surface.x-2)*scaleX));
      const bottom = Math.max(0,Math.floor((height-surface.y-surface.height-2)*scaleY));
      const right = Math.min(canvas.width,Math.ceil((surface.x+surface.width+2)*scaleX));
      const top = Math.min(canvas.height,Math.ceil((height-surface.y+2)*scaleY));
      gl.scissor(left,bottom,Math.max(0,right-left),Math.max(0,top-bottom));
      gl.uniform4f(uniforms.uRect,surface.x,surface.y,surface.width,surface.height);
      gl.uniform1f(uniforms.uRadius,surface.radius);
      gl.uniform1f(uniforms.uMaterial,surface.material);
      gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
    }
    gl.disable(gl.SCISSOR_TEST);
    canvas.dataset.state = motion.matches ? 'still' : 'live';
  }

  function tick(now) {
    frame = 0;
    if (!enabled || lost || document.hidden) return;
    if (now-lastDraw >= 1000/30 || motion.matches) {
      elapsed += lastTick ? Math.min((now-lastTick)/1000,0.1) : 0;
      lastTick = now;
      lastDraw = now;
      const smoothing = motion.matches ? 1 : 0.24;
      pointer.x += (pointer.targetX-pointer.x)*smoothing;
      pointer.y += (pointer.targetY-pointer.y)*smoothing;
      resize();
      if (dirty || now-lastLayout > 500) { measure(); lastLayout = now; }
      draw();
      document.body.classList.add('shader-glass');
    }
    if (!motion.matches) frame = requestAnimationFrame(tick);
  }

  function requestDraw() {
    if (!frame && enabled && !lost && !document.hidden) frame = requestAnimationFrame(tick);
  }

  function sync() {
    cancelAnimationFrame(frame);
    frame = 0;
    lastTick = 0;
    document.body.classList.remove('shader-glass');
    canvas.hidden = !enabled || lost;
    canvas.dataset.state = lost ? 'fallback' : enabled ? 'ready' : 'off';
    status.textContent = enabled && !lost ? 'Move your pointer across the glass. Click for a ripple.' : 'Static glass is active.';
    requestDraw();
  }

  function fallback() {
    lost = true;
    sync();
    toggle.disabled = true;
    toggle.checked = false;
    status.textContent = 'Static glass is active on this device.';
  }

  toggle.addEventListener('change', () => {
    enabled = toggle.checked;
    try { localStorage.setItem(preference,enabled ? 'on' : 'off'); } catch { /* Optional preference. */ }
    sync();
  });
  window.addEventListener('storage', event => {
    if (event.key !== preference && event.key !== null) return;
    enabled = event.newValue !== 'off';
    toggle.checked = enabled;
    sync();
  });
  window.addEventListener('pointermove', event => {
    pointer.targetX = event.clientX;
    pointer.targetY = event.clientY;
    pointer.active = 1;
    requestDraw();
  }, {passive:true});
  document.addEventListener('pointerleave', () => { pointer.active = 0; requestDraw(); });
  window.addEventListener('pointerdown', event => {
    pointer.targetX = event.clientX;
    pointer.targetY = event.clientY;
    pointer.active = 1;
    ripples[rippleIndex++ % 4] = {x:event.clientX,y:event.clientY,start:elapsed};
    requestDraw();
  }, {passive:true});
  window.addEventListener('resize', () => { dirty = true; requestDraw(); }, {passive:true});
  window.addEventListener('scroll', () => { dirty = true; requestDraw(); }, {passive:true,capture:true});
  document.addEventListener('visibilitychange', () => {
    cancelAnimationFrame(frame);
    frame = 0;
    lastTick = 0;
    canvas.dataset.state = document.hidden ? 'paused' : 'ready';
    requestDraw();
  });
  motion.addEventListener('change',sync);
  const observer = new MutationObserver(() => { dirty = true; requestDraw(); });
  // Observe app layout, not the canvas diagnostics or the shader's own body class.
  for (const node of document.querySelectorAll('.main-shell,.sidebar')) {
    observer.observe(node,{subtree:true,childList:true,attributes:true,attributeFilter:['hidden','class','disabled']});
  }
  canvas.addEventListener('webglcontextlost', event => {
    event.preventDefault();
    fallback();
  });
  canvas.addEventListener('webglcontextrestored', () => {
    try { toggle.disabled = false; toggle.checked = enabled; initialize(); } catch { fallback(); }
  });
  window.addEventListener('pagehide', () => {
    cancelAnimationFrame(frame);
    frame = 0;
  });
  window.addEventListener('pageshow',requestDraw);
  try { initialize(); } catch (error) {
    console.warn('Liquid glass unavailable; using the static theme.',error.message);
    fallback();
  }
})();
