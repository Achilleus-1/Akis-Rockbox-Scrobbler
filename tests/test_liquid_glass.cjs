'use strict';
// Lifecycle tests use a minimal host; actual GLSL compilation is checked in-browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname,'../web/liquid-glass.js'),'utf8');

function host({available=true,compile=true,reduced=false,saved=null} = {}) {
  function target() {
    const events = new Map();
    return {
      addEventListener(name,callback) { events.set(name,callback); },
      emit(name,event={}) { events.get(name)?.(event); }
    };
  }
  const toggle = {...target(),checked:false,disabled:false};
  const status = {textContent:''};
  const classes = new Set();
  const body = {prepend() {},classList:{add:name=>classes.add(name),remove:name=>classes.delete(name)}};
  const queue = new Map();
  let frameId = 0, draws = 0, preference = saved;
  const gl = new Proxy({
    createShader:()=>({}),createProgram:()=>({}),createBuffer:()=>({}),
    createTexture:()=>({}),createFramebuffer:()=>({}),
    getShaderParameter:()=>compile,getProgramParameter:()=>true,
    getShaderInfoLog:()=> 'Simulated unsupported shader',
    getUniformLocation:()=>({}),getAttribLocation:()=>0,
    FRAMEBUFFER_COMPLETE:1,checkFramebufferStatus:()=>1,
    drawArrays:()=>{ draws++; }
  }, {get:(object,key)=>key in object ? object[key] : ()=>{}});
  const canvas = {...target(),dataset:{},hidden:false,setAttribute() {},remove() {this.removed=true;},getContext:()=>available ? gl : null};
  const doc = {...target(),hidden:false,body,documentElement:{clientWidth:1200},
    createElement:()=>canvas,getElementById:id=>id==='live-glass' ? toggle : status,querySelectorAll:()=>[]};
  const window = {...target(),innerHeight:800};
  const media = {...target(),matches:reduced};
  const context = {
    document:doc,window,matchMedia:()=>media,devicePixelRatio:3,
    localStorage:{getItem:()=>preference,setItem:(_,value)=>{ preference=value; }},
    requestAnimationFrame:callback=>{ queue.set(++frameId,callback); return frameId; },
    cancelAnimationFrame:id=>queue.delete(id),MutationObserver:class { observe() {} },
    getComputedStyle:()=>({borderTopLeftRadius:'24px'}),console:{warn() {}},
    Float32Array,Math
  };
  vm.runInNewContext(source,context);
  return {
    toggle,canvas,doc,window,media,classes,
    frames:()=>queue.size,draws:()=>draws,preference:()=>preference,
    step(now=100) {
      const entries=[...queue]; queue.clear();
      entries.forEach(([,callback])=>callback(now));
    }
  };
}

test('off preference schedules no animation or rendering',()=>{
  const app=host({saved:'off'});
  assert.equal(app.frames(),0);
  assert.equal(app.draws(),0);
  assert.equal(app.canvas.hidden,true);
  assert.equal(app.toggle.checked,false);
});

test('off switch cancels animation and restores the static theme; on resumes',()=>{
  const app=host();
  app.step();
  assert.equal(app.classes.has('shader-glass'),true);
  app.toggle.checked=false; app.toggle.emit('change');
  assert.equal(app.frames(),0);
  assert.equal(app.classes.has('shader-glass'),false);
  assert.equal(app.preference(),'off');
  app.toggle.checked=true; app.toggle.emit('change'); app.step(200);
  assert.equal(app.classes.has('shader-glass'),true);
  assert.equal(app.preference(),'on');
});

test('hidden app cancels animation and visible app resumes',()=>{
  const app=host(); app.step();
  const before=app.draws();
  app.doc.hidden=true; app.doc.emit('visibilitychange');
  app.step(200);
  assert.equal(app.frames(),0);
  assert.equal(app.draws(),before);
  app.doc.hidden=false; app.doc.emit('visibilitychange'); app.step(300);
  assert.ok(app.draws()>before);
});

test('appearance changes in another app tab update this tab',()=>{
  const app=host(); app.step();
  app.window.emit('storage',{key:'akis-scrobbler-live-glass',newValue:'off'});
  assert.equal(app.toggle.checked,false);
  assert.equal(app.frames(),0);
  assert.equal(app.classes.has('shader-glass'),false);
  app.window.emit('storage',{key:'akis-scrobbler-live-glass',newValue:'on'}); app.step(200);
  assert.equal(app.toggle.checked,true);
  assert.equal(app.classes.has('shader-glass'),true);
});

test('reduced motion draws on demand without a continuous animation loop',()=>{
  const app=host({reduced:true}); app.step();
  assert.equal(app.frames(),0);
  assert.equal(app.canvas.dataset.state,'still');
  app.window.emit('pointermove',{clientX:400,clientY:250}); app.step(200);
  assert.equal(app.frames(),0);
  assert.equal(app.classes.has('shader-glass'),true);
  app.media.matches=false; app.media.emit('change'); app.step(300);
  assert.equal(app.frames(),1);
});

test('WebGL absence and compilation failure keep a usable static theme',()=>{
  for (const options of [{available:false},{compile:false}]) {
    const app=host(options);
    assert.equal(app.classes.has('shader-glass'),false);
    assert.equal(app.frames(),0);
    assert.equal(app.toggle.disabled,true);
    assert.equal(app.toggle.checked,false);
    assert.match(app.doc.getElementById('glass-status').textContent,/Static glass/);
  }
});

test('context loss restores CSS and stops rendering; context restoration recovers',()=>{
  const app=host(); app.step();
  let prevented=false;
  app.canvas.emit('webglcontextlost',{preventDefault:()=>{ prevented=true; }});
  assert.equal(prevented,true);
  assert.equal(app.frames(),0);
  assert.equal(app.classes.has('shader-glass'),false);
  app.canvas.emit('webglcontextrestored'); app.step(200);
  assert.equal(app.toggle.disabled,false);
  assert.equal(app.classes.has('shader-glass'),true);
});
