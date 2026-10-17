// The company brain in 3D: a real MRI-derived brain (CC BY-SA 3.0, Nevit Dilmen, NIH 3D) drawn as a hologram,
// with Premise's live decision network threaded through it as nerves. Facts sit deep, assumptions in the middle,
// guarantees out toward the cortex. Firing a change (fire.js) lights the broken path; signals travel along it.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const stage = document.getElementById('brain');
const source = document.getElementById('plate-data');
const reduce = navigator.webdriver || matchMedia('(prefers-reduced-motion: reduce)').matches;
const COLORS = {ice: new THREE.Color(0xdfe4ff), indigo: new THREE.Color(0x5b63ff), indigo2: new THREE.Color(0x8b92ff),
  holds: new THREE.Color(0x7cf0c8), unknown: new THREE.Color(0xffd27a), broken: new THREE.Color(0xff6b8b)};
const stateColor = s => ['holds', 'holding'].includes(s) ? COLORS.holds : ['broken', 'violated'].includes(s) ? COLORS.broken
  : ['unknown', 'unverified', 'unevaluable'].includes(s) ? COLORS.unknown : COLORS.ice;
const hash = text => [...text].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) / 4294967295;

async function main() {
  if (!stage || !source) return;
  const data = JSON.parse(source.textContent);
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({antialias: true, alpha: true, powerPreference: 'high-performance'});
  } catch {
    stage.querySelector('.brain-fallback').textContent = 'WebGL is unavailable here; the network below shows the same graph.';
    return;
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
  renderer.setClearColor(0x000000, 0);
  stage.prepend(renderer.domElement);
  renderer.domElement.setAttribute('aria-label', `A 3D brain carrying the decision network: ${data.facts.length} facts, ${data.assumptions.length} assumptions, ${data.guarantees.length} guarantees.`);
  renderer.domElement.setAttribute('role', 'img');

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
  camera.position.set(0, 0.6, reduce ? 9.6 : 13);
  const controls = new OrbitControls(camera, renderer.domElement);
  Object.assign(controls, {enableZoom: false, enablePan: false, enableDamping: true, dampingFactor: 0.06, rotateSpeed: 0.55,
    autoRotate: !reduce, autoRotateSpeed: 0.7, minPolarAngle: Math.PI * 0.28, maxPolarAngle: Math.PI * 0.72});
  controls.addEventListener('start', () => stage.classList.add('touched'));

  // Brain mesh: compact indexed binary ('PBRN', counts, half-extent, int16 xyz, u16 indices)
  const buffer = await (await fetch(new URL('./models/brain.bin', import.meta.url))).arrayBuffer();
  const view = new DataView(buffer);
  const nv = view.getUint32(4, true), nt = view.getUint32(8, true);
  const packed = new Int16Array(buffer, 16, nv * 3);
  const indexStart = 16 + nv * 6 + (nv % 2 ? 2 : 0);
  const indices = nv > 65535 ? new Uint32Array(buffer, indexStart, nt * 3) : new Uint16Array(buffer, indexStart, nt * 3);
  const R = 3.1;
  const positions = new Float32Array(nv * 3);
  for (let i = 0; i < packed.length; i++) positions[i] = packed[i] / 32767 * R;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(new THREE.BufferAttribute(indices, 1));
  geometry.rotateX(-Math.PI / 2);
  geometry.rotateY(Math.PI / 2);
  geometry.computeBoundingBox();
  const box = geometry.boundingBox, centre = new THREE.Vector3(), size = new THREE.Vector3();
  box.getCenter(centre); box.getSize(size);
  geometry.translate(-centre.x, -centre.y - size.y * 0.12, -centre.z);
  geometry.computeVertexNormals();
  geometry.computeBoundingBox();
  const bb = geometry.boundingBox;

  const brain = new THREE.Group();
  scene.add(brain);
  const uniforms = {uTime: {value: 0}, uScan: {value: -10}, uReveal: {value: reduce ? 1 : 0}};
  const shell = new THREE.Mesh(geometry, new THREE.ShaderMaterial({
    uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `varying vec3 vN; varying vec3 vV; varying vec3 vP;
      void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); vP = position; gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform float uScan; uniform float uReveal; varying vec3 vN; varying vec3 vV; varying vec3 vP;
      void main() {
        float f = pow(1.0 - abs(dot(vN, vV)), 2.4);
        float scan = smoothstep(0.16, 0.0, abs(vP.y - uScan));
        vec3 col = mix(vec3(0.36, 0.39, 1.0), vec3(0.87, 0.89, 1.0), f) * (0.12 + f * 1.25) + vec3(0.55, 0.6, 1.0) * scan * 0.55;
        gl_FragColor = vec4(col, (0.04 + f * 0.7 + scan * 0.3) * uReveal);
      }`,
  }));
  brain.add(shell);
  const seeds = new Float32Array(nv);
  for (let i = 0; i < nv; i++) seeds[i] = Math.random();
  const cloudGeometry = new THREE.BufferGeometry();
  cloudGeometry.setAttribute('position', geometry.getAttribute('position'));
  cloudGeometry.setAttribute('seed', new THREE.BufferAttribute(seeds, 1));
  const cloud = new THREE.Points(cloudGeometry, new THREE.ShaderMaterial({
    uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `uniform float uTime; attribute float seed; varying float vA;
      void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); vA = 0.25 + 0.75 * pow(0.5 + 0.5 * sin(uTime * 1.6 + seed * 40.0), 6.0);
        gl_PointSize = (1.4 + seed * 1.6) * (9.0 / -mv.z); gl_Position = projectionMatrix * mv; }`,
    fragmentShader: `uniform float uReveal; varying float vA;
      void main() { float d = length(gl_PointCoord - 0.5); if (d > 0.5) discard; gl_FragColor = vec4(0.84, 0.87, 1.0, (1.0 - d * 2.0) * vA * 0.6 * uReveal); }`,
  }));
  brain.add(cloud);

  // The decision network, laid inside the brain in three strata
  const glowTexture = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const g = c.getContext('2d'), grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grad.addColorStop(0, 'rgba(255,255,255,1)'); grad.addColorStop(0.25, 'rgba(255,255,255,0.45)'); grad.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
  })();
  const factIds = new Set(data.facts.map(f => f.id));
  for (const a of data.assumptions) for (const f of [a.lhs_fact, a.rhs_fact]) if (f) factIds.add(f);
  const facts = [...factIds], assumptions = data.assumptions.map(a => a.id), guarantees = data.guarantees.map(g => g.id);
  const byId = new Map([...data.assumptions.map(a => [a.id, {kind: 'assumption', state: a.state, text: a.text}]),
    ...data.guarantees.map(g => [g.id, {kind: 'guarantee', state: g.status, text: g.statement, prerequisites: g.prerequisites}]),
    ...facts.map(id => [id, {kind: 'fact', state: 'fact', value: data.facts.find(f => f.id === id)?.value, control: data.facts.find(f => f.id === id)?.controlled_by}])]);
  const half = new THREE.Vector3(); bb.getSize(half).multiplyScalar(0.5);
  const lift = (bb.max.y + bb.min.y) / 2;
  const nodes = new Map();
  const place = (ids, y, spread, kind) => ids.forEach((id, i) => {
    const angle = i * 2.39996 + hash(id) * 0.6, r = Math.sqrt((i + 0.5) / ids.length) * spread;
    nodes.set(id, {id, kind, pos: new THREE.Vector3(Math.cos(angle) * r * half.x * 0.62, lift + y * half.y + (hash(id + 'y') - 0.5) * 0.35, Math.sin(angle) * r * half.z * 0.66)});
  });
  place(facts, -0.12, 0.55, 'fact');
  place(assumptions, 0.18, 0.75, 'assumption');
  place(guarantees, 0.48, 0.9, 'guarantee');

  const network = new THREE.Group();
  brain.add(network);

  // A soft dark lens behind the network: it always faces the camera and quiets the brain's own fibres
  // there, so the decision network reads as a separate layer instead of more brain.
  const lensTexture = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const g = c.getContext('2d'), grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    grad.addColorStop(0, 'rgba(4,5,14,0.82)'); grad.addColorStop(0.55, 'rgba(4,5,14,0.6)'); grad.addColorStop(1, 'rgba(4,5,14,0)');
    g.fillStyle = grad; g.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(c);
  })();
  const lens = new THREE.Sprite(new THREE.SpriteMaterial({map: lensTexture, transparent: true, depthWrite: false, depthTest: false}));
  lens.renderOrder = 1;
  network.add(lens);

  const edges = [];
  const edgeVertex = `varying float vU; void main() { vU = uv.x; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;
  const edgeFragment = `uniform vec3 uColor; uniform float uOpacity; uniform float uTime; uniform float uFlow; varying float vU;
    void main() {
      float band = fract(vU * 2.0 - uTime * 0.45);
      float pulse = smoothstep(0.0, 0.18, band) * (1.0 - smoothstep(0.18, 0.5, band));
      vec3 col = mix(uColor * 0.8, vec3(1.0), pulse * 0.55 * uFlow);
      gl_FragColor = vec4(col, uOpacity * (0.6 + 0.9 * pulse * uFlow));
    }`;
  const link = (from, to, kind) => {
    const a = nodes.get(from).pos, b = nodes.get(to).pos;
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const out = new THREE.Vector3(mid.x, 0, mid.z).normalize().multiplyScalar(0.28 + hash(from + to) * 0.25);
    const curve = new THREE.QuadraticBezierCurve3(a.clone(), mid.add(out).add(new THREE.Vector3(0, 0.12, 0)), b.clone());
    const material = new THREE.ShaderMaterial({
      uniforms: {uColor: {value: new THREE.Color()}, uOpacity: {value: 0.8}, uTime: uniforms.uTime, uFlow: {value: reduce ? 0 : 1}},
      vertexShader: edgeVertex, fragmentShader: edgeFragment, transparent: true, depthWrite: false, depthTest: false,
    });
    const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, 48, 0.013, 8), material);
    mesh.renderOrder = 2;
    network.add(mesh);
    edges.push({from, to, kind, curve, mesh, material});
  };
  for (const a of data.assumptions) for (const f of new Set([a.lhs_fact, a.rhs_fact])) if (f && nodes.has(f)) link(f, a.id, 'fa');
  for (const g of data.guarantees) for (const a of g.prerequisites) if (nodes.has(a)) link(a, g.id, 'ag');

  {
    const box = new THREE.Box3().setFromPoints([...nodes.values()].map(n => n.pos));
    const centre = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
    lens.position.copy(centre);
    lens.scale.setScalar(Math.max(size.x, size.y, size.z) * 1.7);
  }
  const hits = [];
  for (const node of nodes.values()) {
    const info = byId.get(node.id);
    const radius = node.kind === 'guarantee' ? 0.085 : node.kind === 'assumption' ? 0.06 : 0.04;
    node.color = node.kind === 'fact' ? COLORS.ice.clone() : stateColor(info.state).clone();
    node.base = node.color.clone();
    node.core = new THREE.Mesh(new THREE.SphereGeometry(radius, 20, 20), new THREE.MeshBasicMaterial({color: node.color, transparent: true, depthTest: false}));
    node.core.renderOrder = 4;
    node.halo = new THREE.Sprite(new THREE.SpriteMaterial({map: glowTexture, color: node.color, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false}));
    node.halo.renderOrder = 3;
    node.halo.scale.setScalar(radius * 5);
    node.group = new THREE.Group();
    node.group.position.copy(node.pos);
    node.group.add(node.core, node.halo);
    node.radius = radius;
    const hit = new THREE.Mesh(new THREE.SphereGeometry(radius * 3, 8, 8), new THREE.MeshBasicMaterial({visible: false}));
    hit.userData.id = node.id;
    node.group.add(hit);
    hits.push(hit);
    node.phase = hash(node.id) * 6.28;
    network.add(node.group);
  }

  // Signals travelling along real paths
  const pulses = Array.from({length: 7}, () => {
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({map: glowTexture, color: COLORS.ice, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false}));
    sprite.scale.setScalar(0.22);
    sprite.material.depthTest = false;
    sprite.renderOrder = 5;
    network.add(sprite);
    return {sprite, route: null, t: 0, speed: 0};
  });
  const routes = () => {
    const firedEdges = edges.filter(e => e.state === 'fired');
    if (firedEdges.length) return firedEdges.map(e => [e]);
    return edges.filter(e => e.kind === 'fa').flatMap(fa => edges.filter(ag => ag.kind === 'ag' && ag.from === fa.to).map(ag => [fa, ag]));
  };
  function launch(pulse) {
    const options = routes();
    pulse.route = options[Math.floor(Math.random() * options.length)];
    pulse.t = 0;
    pulse.speed = pulse.route[0].state === 'fired' ? 0.9 : 0.35 + Math.random() * 0.2;
    pulse.sprite.material.color.copy(pulse.route[0].state === 'fired' ? COLORS.broken : COLORS.ice);
  }
  pulses.forEach((p, i) => { p.delay = i * 0.6; });

  // State: hover tracing and fired scenarios
  let firedCheck = null, hovered = null;
  function connected(id) {
    const set = new Set([id]);
    const feeds = f => edges.filter(e => e.kind === 'fa' && e.from === f).map(e => e.to);
    const holds = a => edges.filter(e => e.kind === 'ag' && e.from === a).map(e => e.to);
    const fedBy = a => edges.filter(e => e.kind === 'fa' && e.to === a).map(e => e.from);
    const kind = nodes.get(id).kind;
    if (kind === 'fact') feeds(id).forEach(a => { set.add(a); holds(a).forEach(g => set.add(g)); });
    if (kind === 'assumption') { fedBy(id).forEach(f => set.add(f)); holds(id).forEach(g => set.add(g)); }
    if (kind === 'guarantee') edges.filter(e => e.kind === 'ag' && e.to === id).forEach(e => { set.add(e.from); fedBy(e.from).forEach(f => set.add(f)); });
    return set;
  }
  function paint() {
    const trace = hovered ? connected(hovered) : null;
    const touched = new Set(firedCheck ? firedCheck.changed.map(c => c.fact) : []);
    const fired = new Set();
    if (firedCheck) for (const g of firedCheck.not_holding) for (const id of [g.id, ...g.chain]) fired.add(id);
    const statusOf = new Map(firedCheck ? firedCheck.not_holding.map(g => [g.id, g.status]) : []);
    const reached = new Set(edges.filter(e => e.kind === 'fa' && touched.has(e.from)).map(e => e.to));
    for (const edge of edges) {
      edge.state = null;
      if (firedCheck) {
        if ((edge.kind === 'fa' && touched.has(edge.from) && fired.has(edge.to)) || (edge.kind === 'ag' && fired.has(edge.from) && fired.has(edge.to))) edge.state = 'fired';
        else if ((edge.kind === 'fa' && touched.has(edge.from)) || (edge.kind === 'ag' && reached.has(edge.from))) edge.state = 'checked';
      }
      const lit = trace ? trace.has(edge.from) && trace.has(edge.to) : null;
      const target = byId.get(edge.to);
      const resting = target ? stateColor(target.state) : COLORS.ice;
      edge.material.uniforms.uColor.value.copy(edge.state === 'fired' ? COLORS.broken : edge.state === 'checked' ? COLORS.holds : lit ? COLORS.ice : resting);
      edge.material.uniforms.uOpacity.value = edge.state ? 0.95 : lit ? 0.9 : (trace || firedCheck) ? 0.06 : 0.34;
    }
    for (const node of nodes.values()) {
      const info = byId.get(node.id);
      let color = node.base;
      if (touched.has(node.id)) color = COLORS.unknown;
      else if (statusOf.has(node.id)) color = stateColor(statusOf.get(node.id));
      else if (fired.has(node.id)) color = COLORS.broken;
      node.color.copy(color);
      const active = trace ? trace.has(node.id) : firedCheck ? (touched.has(node.id) || fired.has(node.id) || reached.has(node.id)) : true;
      node.core.material.opacity = active ? 1 : 0.18;
      node.halo.material.opacity = active ? 0.95 : 0.12;
      node.hot = fired.has(node.id) || touched.has(node.id);
      void info;
    }
  }
  document.addEventListener('premise:fire', event => {
    firedCheck = event.detail ? event.detail.check : null;
    paint();
    pulses.forEach(launch);
  });

  // Pointer: hover tooltip, click to open the entity
  const tip = document.createElement('div');
  tip.className = 'tip';
  tip.setAttribute('role', 'tooltip');
  stage.append(tip);
  const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2();
  let down = null;
  function describe(id) {
    const info = byId.get(id);
    if (info.kind === 'guarantee') return [info.text, info.state];
    if (info.kind === 'assumption') return [info.text, info.state];
    return [info.value === undefined ? 'Fact referenced by an assumption.' : `Main value ${JSON.stringify(info.value)}, controlled ${info.control || 'internally'}.`, null];
  }
  function pick(event) {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    return raycaster.intersectObjects(hits, false)[0]?.object.userData.id || null;
  }
  renderer.domElement.addEventListener('pointermove', event => {
    const id = pick(event);
    if (id !== hovered) { hovered = id; paint(); controls.autoRotate = !reduce && !id; }
    renderer.domElement.style.cursor = id ? 'pointer' : '';
    if (!id) { tip.classList.remove('show'); return; }
    const [text, state] = describe(id);
    tip.replaceChildren(Object.assign(document.createElement('strong'), {textContent: id}), document.createTextNode(text));
    if (state) tip.append(document.createElement('br'), window.premiseBadge(state));
    const rect = stage.getBoundingClientRect();
    tip.style.left = `${Math.min(Math.max(8, event.clientX - rect.left + 16), rect.width - 310)}px`;
    tip.style.top = `${Math.min(event.clientY - rect.top + 16, rect.height - 120)}px`;
    tip.classList.add('show');
  });
  renderer.domElement.addEventListener('pointerleave', () => { hovered = null; paint(); tip.classList.remove('show'); controls.autoRotate = !reduce; });
  renderer.domElement.addEventListener('pointerdown', event => { down = [event.clientX, event.clientY]; });
  renderer.domElement.addEventListener('pointerup', event => {
    if (!down || Math.hypot(event.clientX - down[0], event.clientY - down[1]) > 5) return;
    const id = pick(event);
    if (id) location.href = window.premiseEntity(id);
  });

  // Size, visibility and the frame loop
  const resize = () => {
    const {clientWidth: w, clientHeight: h} = stage;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(stage);
  resize();
  brain.rotation.y = -0.6;
  paint();
  stage.classList.add('ready');
  const clock = new THREE.Clock();
  let visible = true;
  new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; }).observe(stage);
  const loop = () => {
    if (!visible || document.hidden) return;
    const dt = Math.min(clock.getDelta(), 0.05), t = clock.elapsedTime;
    uniforms.uTime.value = t;
    if (!reduce) {
      uniforms.uReveal.value = Math.min(1, uniforms.uReveal.value + dt * 0.7);
      camera.position.lerp(camera.position.clone().setLength(9.6), 0.03);
      const cycle = (t % 7) / 7;
      uniforms.uScan.value = bb.max.y + 0.4 - cycle * (bb.max.y - bb.min.y + 0.8) * 1.4;
      for (const node of nodes.values()) {
        const beat = node.hot ? 0.35 * (0.5 + 0.5 * Math.sin(t * 6 + node.phase)) : 0.08 * Math.sin(t * 1.4 + node.phase);
        node.halo.scale.setScalar(node.radius * 5 * (1 + beat));
      }
      for (const p of pulses) {
        if (p.delay > 0) { p.delay -= dt; continue; }
        if (!p.route) launch(p);
        p.t += dt * p.speed;
        const leg = Math.min(Math.floor(p.t), p.route.length - 1), local = Math.min(p.t - leg, 1);
        p.sprite.position.copy(p.route[leg].curve.getPoint(local));
        p.sprite.material.opacity = Math.sin(Math.PI * Math.min(p.t / p.route.length, 1)) * 0.95;
        if (p.t >= p.route.length) { p.delay = Math.random() * 0.8; launch(p); }
      }
    }
    controls.update();
    renderer.render(scene, camera);
  };
  renderer.setAnimationLoop(loop);
}

main().catch(error => {
  const fallback = stage?.querySelector('.brain-fallback');
  if (fallback) fallback.textContent = 'The 3D brain could not load; the network below shows the same graph.';
  console.warn('brain3d', error);
});
