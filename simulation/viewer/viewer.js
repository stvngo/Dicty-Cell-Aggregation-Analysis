// Dicty 3D lift viewer.
//
// Serve the repo root (python -m http.server 8000) and open
// http://localhost:8000/simulation/viewer/
//
// Data: simulation/output/web/<model>/{meta.json, chunk_NNN.bin} from
// `python -m simulation.build`. Each Gaussian row is 9 float32:
// x y sxx sxy syy area mass peak track (pixels, image coords: x right, y down).
//
// World frame: image x -> world X, image y -> world Z, height -> world Y.
// The 512x512 frame spans X, Z in [-256, 256]; the floor sits at Y = 0.

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import GUI from 'lil-gui';

const WEB_ROOT = '../output/web/';
const REPO_ROOT = '../../';
const NF = 9;
const SIZE = 512;
const HALF = SIZE / 2;
const Z_TARGET = 90;           // world height of the tallest object at zScale = 1
const CUTOFF = 3.5;            // Gaussian support, in standard deviations
const ISO = Math.exp(-1);      // metaball level: lone dome height == its amplitude

const params = {
  model: '',
  mode: 'surface',
  height: 'mound',
  color: 'height',
  colormap: 'inferno',
  zScale: 1.0,
  sigmaScale: 1.0,
  metaSigma: 1.25,
  imageGain: 1.0,
  gridRes: 256,
  volRes: 160,
  splatOpacity: 0.9,
  fps: 24,
  autoRotate: false,
  snapshot: () => snapshot(),
};

// ---------------------------------------------------------------- colormaps

const COLORMAPS = {
  inferno: ['#000004', '#280b54', '#65156e', '#9f2a63', '#d44842', '#f57d15', '#fac127', '#fcffa4'],
  magma: ['#000004', '#221150', '#5f187f', '#982d80', '#d3436e', '#f8765c', '#febb81', '#fcfdbf'],
  viridis: ['#440154', '#472878', '#3e4a89', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6dcd59', '#b4de2c', '#fde725'],
  ice: ['#04060f', '#14284f', '#1f5a8c', '#2d96b4', '#6ecdd2', '#c8f0f0', '#ffffff'],
};

function buildLut(name) {
  // 256 linear-space RGB entries.
  const stops = COLORMAPS[name].map((h) => new THREE.Color(h)); // THREE.Color stores linear
  const lut = new Float32Array(256 * 3);
  for (let i = 0; i < 256; i++) {
    const t = (i / 255) * (stops.length - 1);
    const k = Math.min(stops.length - 2, Math.floor(t));
    const f = t - k;
    lut[i * 3] = stops[k].r + (stops[k + 1].r - stops[k].r) * f;
    lut[i * 3 + 1] = stops[k].g + (stops[k + 1].g - stops[k].g) * f;
    lut[i * 3 + 2] = stops[k].b + (stops[k + 1].b - stops[k].b) * f;
  }
  return lut;
}

let LUT = buildLut(params.colormap);
const lutTexture = new THREE.DataTexture(new Float32Array(256 * 4), 256, 1, THREE.RGBAFormat, THREE.FloatType);
function refreshLutTexture() {
  for (let i = 0; i < 256; i++) {
    lutTexture.image.data.set([LUT[i * 3], LUT[i * 3 + 1], LUT[i * 3 + 2], 1], i * 4);
  }
  lutTexture.needsUpdate = true;
}
refreshLutTexture();

// Height t in [0, 1] -> LUT index. The gamma lifts single cells off the floor color.
const lutIndex = (t) => Math.min(255, Math.max(0, Math.round(Math.pow(Math.min(t, 1), 0.6) * 255)));

const trackColorCache = new Map();
function trackColor(id) {
  // Golden-ratio hue walk: neighbouring track IDs get distinct hues. Linear RGB.
  let c = trackColorCache.get(id);
  if (!c) {
    const col = new THREE.Color().setHSL((id * 0.61803398875) % 1, 0.7, 0.55, THREE.SRGBColorSpace);
    c = [col.r, col.g, col.b];
    trackColorCache.set(id, c);
  }
  return c;
}

// ---------------------------------------------------------------- data

const state = {
  meta: null,
  chunks: new Map(),       // chunk index -> Promise<{counts, offsets, data}>
  frame: 0,
  data: null,              // {count, data: Float32Array view} for state.frame
  playing: false,
  floorImages: new Map(),  // frame -> HTMLImageElement
  floorPixels: null,       // Uint8ClampedArray of the shown floor image (splat image colors)
};

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

function loadChunk(c) {
  if (!state.chunks.has(c)) {
    const model = params.model;
    const p = fetch(`${WEB_ROOT}${model}/chunk_${String(c).padStart(3, '0')}.bin`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} chunk ${c}`);
        return r.arrayBuffer();
      })
      .then((buf) => {
        const chunk = state.meta.chunk;
        const counts = new Uint32Array(buf, 0, chunk);
        const offsets = new Uint32Array(chunk + 1);
        for (let i = 0; i < chunk; i++) offsets[i + 1] = offsets[i] + counts[i];
        return { counts, offsets, data: new Float32Array(buf, chunk * 4) };
      });
    state.chunks.set(c, p);
    // Keep memory bounded: drop the chunks farthest from c.
    if (state.chunks.size > 24) {
      const far = [...state.chunks.keys()].sort((a, b) => Math.abs(b - c) - Math.abs(a - c));
      for (const k of far.slice(0, state.chunks.size - 24)) state.chunks.delete(k);
    }
  }
  return state.chunks.get(c);
}

async function frameData(f) {
  const chunk = state.meta.chunk;
  const ch = await loadChunk(Math.floor(f / chunk));
  const k = f % chunk;
  const a = ch.offsets[k];
  return { count: ch.counts[k], data: ch.data.subarray(a * NF, (a + ch.counts[k]) * NF) };
}

function floorUrl(f) {
  const m = state.meta;
  const name = `${m.floor_prefix}${String(f).padStart(m.floor_pad, '0')}${m.floor_ext}`;
  return `${REPO_ROOT}${m.floor_dir.split('/').map(encodeURIComponent).join('/')}/${encodeURIComponent(name)}`;
}

function loadFloor(f) {
  if (!state.meta.floor_prefix) return Promise.resolve(null);
  if (state.floorImages.has(f)) return state.floorImages.get(f);
  const p = new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = floorUrl(f);
  });
  state.floorImages.set(f, p);
  if (state.floorImages.size > 160) {
    const far = [...state.floorImages.keys()].sort((a, b) => Math.abs(b - f) - Math.abs(a - f));
    for (const k of far.slice(0, state.floorImages.size - 160)) state.floorImages.delete(k);
  }
  return p;
}

// Amplitude (height) model; mirrors simulation/field.py:amplitudes. Returns raw H.
function rawAmplitude(d, o, model) {
  const area = d[o + 5];
  const peak = Math.min(Math.max(d[o + 7], 0), 1.5);
  if (model === 'mound') return Math.sqrt(area / Math.PI) * peak;
  if (model === 'intensity') return peak;
  const det = d[o + 2] * d[o + 4] - d[o + 3] * d[o + 3];
  return d[o + 6] / (2 * Math.PI * Math.sqrt(Math.max(det, 1)));
}

// ---------------------------------------------------------------- scene

const app = document.getElementById('app');
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
app.appendChild(renderer.domElement);
const floatLinear = !!renderer.extensions.get('OES_texture_float_linear');

const scene = new THREE.Scene();
scene.background = new THREE.Color('#06070b');

const camera = new THREE.PerspectiveCamera(38, window.innerWidth / window.innerHeight, 1, 6000);
camera.position.set(-40, 470, 610);
const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 10, 30);
controls.enableDamping = true;
controls.maxPolarAngle = Math.PI * 0.495;
controls.autoRotateSpeed = 0.6;

scene.add(new THREE.HemisphereLight(0xc4d6ff, 0x1c140a, 0.85));
// Key light from the top-right of the frame, where the cAMP source / food is.
const key = new THREE.DirectionalLight(0xfff0dc, 2.4);
key.position.set(330, 430, -300);
key.castShadow = true;
key.shadow.mapSize.set(2048, 2048);
Object.assign(key.shadow.camera, { left: -380, right: 380, top: 380, bottom: -380, near: 10, far: 1600 });
key.shadow.bias = -0.0004;
key.shadow.normalBias = 0.6;
scene.add(key);
const fill = new THREE.DirectionalLight(0x8fb2ff, 0.55);
fill.position.set(-320, 220, 340);
scene.add(fill);

const floorTex = new THREE.Texture();
floorTex.colorSpace = THREE.SRGBColorSpace;
floorTex.anisotropy = renderer.capabilities.getMaxAnisotropy();
// Same size as the frames: WebGL2 texture storage is allocated once, at the first upload.
const blankCanvas = document.createElement('canvas');
blankCanvas.width = blankCanvas.height = SIZE;
floorTex.image = blankCanvas;
floorTex.needsUpdate = true;

// Specimen slab under everything, so the frame reads as a physical plate.
const slab = new THREE.Mesh(
  new THREE.BoxGeometry(SIZE + 12, 10, SIZE + 12),
  new THREE.MeshStandardMaterial({ color: 0x12141b, roughness: 0.8, metalness: 0.1 }),
);
slab.position.y = -5.2;
slab.receiveShadow = true;
scene.add(slab);

const floorMat = new THREE.MeshStandardMaterial({ map: floorTex, roughness: 0.92, metalness: 0 });
const floor = new THREE.Mesh(new THREE.PlaneGeometry(SIZE, SIZE).rotateX(-Math.PI / 2), floorMat);
floor.receiveShadow = true;
scene.add(floor);

// ---------------------------------------------------------------- surface mode

const surface = {
  mesh: null,
  n: 0,
  heights: null,
  cr: null, cg: null, cb: null, cw: null,
};

const surfaceUniforms = { uImageGain: { value: 1 } };
// Low specular intensity: at grazing angles a glossy dark floor washes out to grey.
const surfaceMat = new THREE.MeshPhysicalMaterial({
  vertexColors: true, map: floorTex, roughness: 0.55, metalness: 0, specularIntensity: 0.25,
});
surfaceMat.onBeforeCompile = (shader) => {
  shader.uniforms.uImageGain = surfaceUniforms.uImageGain;
  shader.vertexShader = shader.vertexShader
    .replace('#include <common>', '#include <common>\nattribute float blend;\nvarying float vBlend;')
    .replace('#include <begin_vertex>', '#include <begin_vertex>\nvBlend = blend;');
  // Low ground shows the microscopy frame; raised Gaussians take the colormap.
  shader.fragmentShader = shader.fragmentShader
    .replace('#include <common>', '#include <common>\nvarying float vBlend;\nuniform float uImageGain;')
    .replace('#include <map_fragment>', '')
    .replace(
      '#include <color_fragment>',
      'vec3 imgC = texture2D(map, vMapUv).rgb * uImageGain;\n' +
      'diffuseColor.rgb = mix(imgC, vColor, clamp(vBlend, 0.0, 1.0));',
    );
};

function ensureSurface(n) {
  if (surface.mesh && surface.n === n) return;
  if (surface.mesh) {
    scene.remove(surface.mesh);
    surface.mesh.geometry.dispose();
  }
  const geo = new THREE.PlaneGeometry(SIZE, SIZE, n - 1, n - 1).rotateX(-Math.PI / 2);
  geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(n * n * 3), 3));
  geo.setAttribute('blend', new THREE.BufferAttribute(new Float32Array(n * n), 1));
  const mesh = new THREE.Mesh(geo, surfaceMat);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.frustumCulled = false;
  scene.add(mesh);
  Object.assign(surface, {
    mesh, n,
    heights: new Float32Array(n * n),
    cr: new Float32Array(n * n), cg: new Float32Array(n * n),
    cb: new Float32Array(n * n), cw: new Float32Array(n * n),
  });
}

// Sum of anisotropic Gaussians sampled at grid vertices (cell = SIZE / (n - 1)).
// Heights are normalized (1 = tallest object of the movie); optional per-vertex
// track-color accumulation weighted by each Gaussian's contribution.
function splat2D(frame, n, withColor) {
  const { heights: H, cr, cg, cb, cw } = surface;
  H.fill(0);
  if (withColor) { cr.fill(0); cg.fill(0); cb.fill(0); cw.fill(0); }
  const d = frame.data;
  const cell = SIZE / (n - 1);
  const s2 = params.sigmaScale ** 2;
  const ref = state.meta.amp_ref[params.height];
  const cut2 = CUTOFF * CUTOFF;
  for (let i = 0; i < frame.count; i++) {
    const o = i * NF;
    const amp = rawAmplitude(d, o, params.height) / ref;
    if (!(amp > 0)) continue;
    const sxx = d[o + 2] * s2, sxy = d[o + 3] * s2, syy = d[o + 4] * s2;
    const det = sxx * syy - sxy * sxy;
    if (det <= 1e-9) continue;
    const ia = syy / det, ib = -sxy / det, ic = sxx / det;
    const gx = d[o], gy = d[o + 1];
    const rx = (CUTOFF * Math.sqrt(sxx)) / cell, ry = (CUTOFF * Math.sqrt(syy)) / cell;
    const c0 = Math.max(0, Math.ceil(gx / cell - rx)), c1 = Math.min(n - 1, Math.floor(gx / cell + rx));
    const r0 = Math.max(0, Math.ceil(gy / cell - ry)), r1 = Math.min(n - 1, Math.floor(gy / cell + ry));
    const tc = withColor ? trackColor(d[o + 8]) : null;
    for (let r = r0; r <= r1; r++) {
      const dy = r * cell - gy;
      const row = r * n;
      for (let c = c0; c <= c1; c++) {
        const dx = c * cell - gx;
        const q = ia * dx * dx + 2 * ib * dx * dy + ic * dy * dy;
        if (q < cut2) {
          const w = amp * Math.exp(-0.5 * q);
          H[row + c] += w;
          if (withColor) {
            cr[row + c] += w * tc[0]; cg[row + c] += w * tc[1]; cb[row + c] += w * tc[2]; cw[row + c] += w;
          }
        }
      }
    }
  }
}

function updateSurface() {
  const n = params.gridRes;
  ensureSurface(n);
  const byTrack = params.color === 'track' && state.meta.kind === 'spots';
  splat2D(state.data, n, byTrack);
  const { heights: H } = surface;
  const geo = surface.mesh.geometry;
  const pos = geo.attributes.position.array;
  const nor = geo.attributes.normal.array;
  const col = geo.attributes.color.array;
  const blend = geo.attributes.blend.array;
  const zs = Z_TARGET * params.zScale;
  const cell = SIZE / (n - 1);
  for (let i = 0; i < n * n; i++) {
    const t = H[i];
    pos[i * 3 + 1] = t * zs;
    if (params.color === 'image') {
      blend[i] = 0;
    } else if (byTrack) {
      const w = surface.cw[i] || 1;
      col[i * 3] = surface.cr[i] / w; col[i * 3 + 1] = surface.cg[i] / w; col[i * 3 + 2] = surface.cb[i] / w;
      blend[i] = Math.min(1, t / 0.04);
    } else {
      const k = lutIndex(t) * 3;
      col[i * 3] = LUT[k]; col[i * 3 + 1] = LUT[k + 1]; col[i * 3 + 2] = LUT[k + 2];
      blend[i] = Math.min(1, Math.pow(t / 0.12, 0.8));
    }
  }
  // Normals from central differences of the height grid.
  for (let r = 0; r < n; r++) {
    for (let c = 0; c < n; c++) {
      const i = r * n + c;
      const hl = pos[(r * n + Math.max(c - 1, 0)) * 3 + 1], hr = pos[(r * n + Math.min(c + 1, n - 1)) * 3 + 1];
      const hu = pos[(Math.max(r - 1, 0) * n + c) * 3 + 1], hd = pos[(Math.min(r + 1, n - 1) * n + c) * 3 + 1];
      const nx = -(hr - hl) / (2 * cell), nz = -(hd - hu) / (2 * cell);
      const inv = 1 / Math.hypot(nx, 1, nz);
      nor[i * 3] = nx * inv; nor[i * 3 + 1] = inv; nor[i * 3 + 2] = nz * inv;
    }
  }
  geo.attributes.position.needsUpdate = true;
  geo.attributes.normal.needsUpdate = true;
  geo.attributes.color.needsUpdate = true;
  geo.attributes.blend.needsUpdate = true;
}

// ---------------------------------------------------------------- metaball mode

const volume = { mesh: null, tex: null, colorTex: null, n: 0, nz: 48, zTop: 1, data: null, color: null };

const volumeMat = new THREE.ShaderMaterial({
  uniforms: {
    uVol: { value: null },
    uLut: { value: lutTexture },
    uFloor: { value: floorTex },
    uColor2D: { value: null },
    uBoxMin: { value: new THREE.Vector3() },
    uBoxMax: { value: new THREE.Vector3() },
    uVoxel: { value: new THREE.Vector3() },
    uIso: { value: ISO },
    uZTarget: { value: Z_TARGET },
    uColorMode: { value: 0 },
    uImageGain: { value: 1 },
    uLightDir: { value: key.position.clone().normalize() },
    uViewProj: { value: new THREE.Matrix4() },
  },
  vertexShader: /* glsl */ `
    varying vec3 vWorld;
    void main() {
      vec4 w = modelMatrix * vec4(position, 1.0);
      vWorld = w.xyz;
      gl_Position = projectionMatrix * viewMatrix * w;
    }`,
  fragmentShader: /* glsl */ `
    precision highp sampler3D;
    uniform sampler3D uVol;
    uniform sampler2D uLut, uFloor, uColor2D;
    uniform vec3 uBoxMin, uBoxMax, uVoxel, uLightDir;
    uniform float uIso, uZTarget, uImageGain;
    uniform int uColorMode;
    uniform mat4 uViewProj;
    varying vec3 vWorld;

    float dens(vec3 p) {
      vec3 u = (p - uBoxMin) / (uBoxMax - uBoxMin);
      return texture(uVol, vec3(u.x, u.z, u.y)).r;   // texture axes: image x, image y, height
    }
    vec3 grad(vec3 p) {
      vec3 e = uVoxel;
      return vec3(dens(p + vec3(e.x, 0., 0.)) - dens(p - vec3(e.x, 0., 0.)),
                  dens(p + vec3(0., e.y, 0.)) - dens(p - vec3(0., e.y, 0.)),
                  dens(p + vec3(0., 0., e.z)) - dens(p - vec3(0., 0., e.z))) / (2.0 * e);
    }

    void main() {
      vec3 ro = cameraPosition;
      vec3 rd = normalize(vWorld - ro);
      vec3 inv = 1.0 / rd;
      vec3 t0 = (uBoxMin - ro) * inv, t1 = (uBoxMax - ro) * inv;
      vec3 tn = min(t0, t1), tf = max(t0, t1);
      float tmin = max(max(max(tn.x, tn.y), tn.z), 0.0);
      float tmax = min(min(tf.x, tf.y), tf.z);
      if (tmax <= tmin) discard;

      float dt = 0.5 * min(uVoxel.x, uVoxel.y);
      float t = tmin;
      float prev = dens(ro + rd * t) - uIso;
      bool hit = prev > 0.0;
      for (int i = 0; i < 1024; i++) {
        if (hit || t > tmax) break;
        float tn2 = t + dt;
        float cur = dens(ro + rd * tn2) - uIso;
        if (cur > 0.0) {
          // Bisection between the last outside sample and this inside one.
          float a = t, b = tn2;
          for (int k = 0; k < 6; k++) {
            float m = 0.5 * (a + b);
            if (dens(ro + rd * m) > uIso) b = m; else a = m;
          }
          t = b;
          hit = true;
        } else {
          t = tn2;
        }
      }
      if (!hit) discard;

      vec3 p = ro + rd * t;
      vec3 n = -normalize(grad(p) + vec3(0.0, 1e-6, 0.0));
      vec3 v = -rd;
      vec2 uvImg = vec2((p.x - uBoxMin.x) / (uBoxMax.x - uBoxMin.x), (p.z - uBoxMin.z) / (uBoxMax.z - uBoxMin.z));

      vec3 base;
      if (uColorMode == 1) {
        base = texture(uColor2D, uvImg).rgb;
      } else if (uColorMode == 2) {
        base = texture(uFloor, vec2(uvImg.x, 1.0 - uvImg.y)).rgb * uImageGain;
      } else {
        float h = clamp(p.y / uZTarget, 0.0, 1.0);
        base = texture(uLut, vec2(pow(h, 0.6), 0.5)).rgb;
      }
      vec3 l = normalize(uLightDir);
      float diff = max(dot(n, l), 0.0);
      vec3 hemi = mix(vec3(0.10, 0.08, 0.06), vec3(0.62, 0.70, 0.88), n.y * 0.5 + 0.5);
      float spec = pow(max(dot(n, normalize(l + v)), 0.0), 56.0) * 0.45;
      float ao = clamp(1.0 - 0.55 * dens(p + n * 2.5 * uVoxel.x), 0.35, 1.0);
      float rim = pow(1.0 - max(dot(n, v), 0.0), 3.0) * 0.25;
      vec3 col = base * (hemi * 0.7 + diff * 1.25) * ao + spec + rim * base;

      vec4 clip = uViewProj * vec4(p, 1.0);
      gl_FragDepth = clamp(0.5 * clip.z / clip.w + 0.5, 0.0, 1.0);
      gl_FragColor = vec4(col, 1.0);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }`,
  side: THREE.BackSide,
});

function ensureVolume(n, nz, zTop) {
  if (!volume.mesh || volume.n !== n || volume.nz !== nz) {
    if (volume.tex) volume.tex.dispose();
    if (volume.colorTex) volume.colorTex.dispose();
    volume.data = new Float32Array(n * n * nz);
    volume.tex = new THREE.Data3DTexture(volume.data, n, n, nz);
    volume.tex.format = THREE.RedFormat;
    volume.tex.type = THREE.FloatType;
    volume.tex.minFilter = volume.tex.magFilter = floatLinear ? THREE.LinearFilter : THREE.NearestFilter;
    volume.tex.unpackAlignment = 1;
    volume.color = new Uint8Array(n * n * 4);
    volume.colorTex = new THREE.DataTexture(volume.color, n, n, THREE.RGBAFormat);
    volume.colorTex.colorSpace = THREE.SRGBColorSpace;
    volume.colorTex.minFilter = volume.colorTex.magFilter = THREE.LinearFilter;
    volumeMat.uniforms.uVol.value = volume.tex;
    volumeMat.uniforms.uColor2D.value = volume.colorTex;
    volume.n = n;
    volume.nz = nz;
  }
  if (!volume.mesh) {
    volume.mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), volumeMat);
    volume.mesh.frustumCulled = false;
    scene.add(volume.mesh);
  }
  volume.zTop = zTop;
  volume.mesh.scale.set(SIZE, zTop, SIZE);
  volume.mesh.position.set(0, zTop / 2, 0);
  const u = volumeMat.uniforms;
  u.uBoxMin.value.set(-HALF, 0, -HALF);
  u.uBoxMax.value.set(HALF, zTop, HALF);
  u.uVoxel.value.set(SIZE / n, zTop / (nz - 1), SIZE / n);
}

// rho(x, y, z) = sum_i exp(-1/2 (d^T S_i^-1 d + z^2 / sz_i^2)), sz_i = height_i / sqrt(2):
// the 1/e iso-surface of a lone Gaussian is a dome exactly height_i tall; close
// domes fuse like metaballs. Mirrors simulation/field.py:density_volume.
function splat3D(frame) {
  const n = params.volRes, nz = 48;
  const zs = Z_TARGET * params.zScale;
  const zTop = zs * 1.35 + 4;
  ensureVolume(n, nz, zTop);
  const V = volume.data;
  V.fill(0);
  const C = volume.color;
  const cacc = new Float32Array(n * n * 4);
  const d = frame.data;
  const cell = SIZE / n;
  const dz = zTop / (nz - 1);
  const s2 = params.metaSigma ** 2;
  const ref = state.meta.amp_ref[params.height];
  const cut = 3.0, cut2 = cut * cut;
  const byTrack = params.color === 'track' && state.meta.kind === 'spots';
  for (let i = 0; i < frame.count; i++) {
    const o = i * NF;
    const amp = rawAmplitude(d, o, params.height) / ref;
    if (!(amp > 0)) continue;
    const sz = Math.max(amp * zs, 1.2 * dz) / Math.SQRT2;
    const sxx = d[o + 2] * s2, sxy = d[o + 3] * s2, syy = d[o + 4] * s2;
    const det = sxx * syy - sxy * sxy;
    if (det <= 1e-9) continue;
    const ia = syy / det, ib = -sxy / det, ic = sxx / det;
    const gx = d[o], gy = d[o + 1];
    const tc = byTrack ? trackColor(d[o + 8]) : null;
    const kmax = Math.min(nz - 1, Math.floor((cut * sz) / dz));
    for (let k = 0; k <= kmax; k++) {
      const qz = ((k * dz) / sz) ** 2;
      const lim = cut2 - qz;
      if (lim <= 0) break;
      const sc = Math.sqrt(lim) / cell;
      const rx = sc * Math.sqrt(sxx), ry = sc * Math.sqrt(syy);
      const cx = gx / cell - 0.5, cy = gy / cell - 0.5;
      const c0 = Math.max(0, Math.ceil(cx - rx)), c1 = Math.min(n - 1, Math.floor(cx + rx));
      const r0 = Math.max(0, Math.ceil(cy - ry)), r1 = Math.min(n - 1, Math.floor(cy + ry));
      const ez = Math.exp(-0.5 * qz);
      const base = k * n * n;
      for (let r = r0; r <= r1; r++) {
        const dy = (r + 0.5) * cell - gy;
        for (let c = c0; c <= c1; c++) {
          const dx = (c + 0.5) * cell - gx;
          const q = ia * dx * dx + 2 * ib * dx * dy + ic * dy * dy;
          if (q < lim) {
            const w = Math.exp(-0.5 * q) * ez;
            V[base + r * n + c] += w;
            if (byTrack && k === 0) {
              const j = (r * n + c) * 4;
              cacc[j] += w * tc[0]; cacc[j + 1] += w * tc[1]; cacc[j + 2] += w * tc[2]; cacc[j + 3] += w;
            }
          }
        }
      }
    }
  }
  if (byTrack) {
    // Linear accumulators -> sRGB bytes for the sRGB-decoded color texture.
    const tmp = new THREE.Color();
    for (let j = 0; j < n * n; j++) {
      const w = cacc[j * 4 + 3] || 1;
      tmp.setRGB(cacc[j * 4] / w, cacc[j * 4 + 1] / w, cacc[j * 4 + 2] / w).convertLinearToSRGB();
      C[j * 4] = tmp.r * 255; C[j * 4 + 1] = tmp.g * 255; C[j * 4 + 2] = tmp.b * 255; C[j * 4 + 3] = 255;
    }
    volume.colorTex.needsUpdate = true;
  }
  volume.tex.needsUpdate = true;
  const u = volumeMat.uniforms;
  u.uZTarget.value = zs;
  u.uColorMode.value = params.color === 'image' ? 2 : byTrack ? 1 : 0;
}

// ---------------------------------------------------------------- splat mode

// 3D Gaussian splatting: each Gaussian becomes a 3D Gaussian centred on the
// floor (world cov = [[sxx, 0, sxy], [0, sz^2, 0], [sxy, 0, syy]]), projected
// with the EWA Jacobian to a screen-space ellipse and alpha-blended back to
// front. The floor hides the lower halves, leaving soft domes.
const splats = { mesh: null, capacity: 0, order: null, depth: null, center: null, cov: null, color: null };

const splatMat = new THREE.ShaderMaterial({
  uniforms: { uViewport: { value: new THREE.Vector2(1, 1) }, uCutoff: { value: 3.0 } },
  vertexShader: /* glsl */ `
    uniform vec2 uViewport;
    uniform float uCutoff;
    attribute vec3 iCenter;
    attribute vec4 iCov;     // xx, xz, zz (ground plane) and yy (height)
    attribute vec4 iColor;   // linear rgb + opacity
    varying vec2 vUV;
    varying vec4 vColor;
    void main() {
      vec4 cam = viewMatrix * vec4(iCenter, 1.0);
      if (cam.z > -1.0) { gl_Position = vec4(0.0, 0.0, 2.0, 1.0); return; }
      vec4 clip = projectionMatrix * cam;
      mat3 S = mat3(iCov.x, 0.0, iCov.y,
                    0.0, iCov.w, 0.0,
                    iCov.y, 0.0, iCov.z);
      float fx = projectionMatrix[0][0] * uViewport.x * 0.5;
      float fy = projectionMatrix[1][1] * uViewport.y * 0.5;
      float z = cam.z;
      mat3 J = mat3(fx / -z, 0.0, 0.0,
                    0.0, fy / -z, 0.0,
                    fx * cam.x / (z * z), fy * cam.y / (z * z), 0.0);
      mat3 T = J * mat3(viewMatrix);
      mat3 C = T * S * transpose(T);
      float a = C[0][0] + 0.3, b = C[0][1], c = C[1][1] + 0.3;
      float mid = 0.5 * (a + c);
      float rad = sqrt(max(mid * mid - (a * c - b * b), 1e-8));
      float l1 = mid + rad, l2 = max(mid - rad, 0.1);
      vec2 v1 = abs(b) > 1e-6 ? normalize(vec2(b, l1 - a)) : (a >= c ? vec2(1.0, 0.0) : vec2(0.0, 1.0));
      vec2 v2 = vec2(-v1.y, v1.x);
      vec2 offPx = position.x * uCutoff * sqrt(l1) * v1 + position.y * uCutoff * sqrt(l2) * v2;
      vUV = position.xy * uCutoff;
      vColor = iColor;
      gl_Position = clip + vec4(offPx / (0.5 * uViewport) * clip.w, 0.0, 0.0);
    }`,
  fragmentShader: /* glsl */ `
    varying vec2 vUV;
    varying vec4 vColor;
    void main() {
      float p = -0.5 * dot(vUV, vUV);
      if (p < -4.5) discard;
      float g = exp(p);
      float a = clamp(vColor.a * g, 0.0, 0.995);
      vec4 c = linearToOutputTexel(vec4(vColor.rgb * (0.7 + 0.45 * g), 1.0));
      gl_FragColor = vec4(c.rgb * a, a);
    }`,
  transparent: true,
  depthWrite: false,
  blending: THREE.CustomBlending,
  blendSrc: THREE.OneFactor,
  blendDst: THREE.OneMinusSrcAlphaFactor,
});

function ensureSplats(count) {
  if (splats.mesh && splats.capacity >= count) return;
  const cap = Math.max(1024, 1 << Math.ceil(Math.log2(Math.max(count, 1))));
  if (splats.mesh) {
    scene.remove(splats.mesh);
    splats.mesh.geometry.dispose();
  }
  const geo = new THREE.InstancedBufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0]), 3));
  geo.setIndex([0, 1, 2, 0, 2, 3]);
  splats.center = new Float32Array(cap * 3);
  splats.cov = new Float32Array(cap * 4);
  splats.color = new Float32Array(cap * 4);
  geo.setAttribute('iCenter', new THREE.InstancedBufferAttribute(splats.center, 3).setUsage(THREE.DynamicDrawUsage));
  geo.setAttribute('iCov', new THREE.InstancedBufferAttribute(splats.cov, 4).setUsage(THREE.DynamicDrawUsage));
  geo.setAttribute('iColor', new THREE.InstancedBufferAttribute(splats.color, 4).setUsage(THREE.DynamicDrawUsage));
  splats.mesh = new THREE.Mesh(geo, splatMat);
  splats.mesh.frustumCulled = false;
  splats.mesh.renderOrder = 2;
  scene.add(splats.mesh);
  splats.capacity = cap;
  splats.order = new Uint32Array(cap);
  splats.depth = new Float32Array(cap);
}

// Unsorted per-Gaussian splat parameters; sortSplats() writes them in draw order.
const splatSrc = { n: 0, center: new Float32Array(0), cov: new Float32Array(0), color: new Float32Array(0) };

function updateSplats() {
  const frame = state.data;
  const n = frame.count;
  ensureSplats(n);
  if (splatSrc.center.length < n * 3) {
    splatSrc.center = new Float32Array(splats.capacity * 3);
    splatSrc.cov = new Float32Array(splats.capacity * 4);
    splatSrc.color = new Float32Array(splats.capacity * 4);
  }
  const d = frame.data;
  const s2 = params.sigmaScale ** 2;
  const ref = state.meta.amp_ref[params.height];
  const zs = Z_TARGET * params.zScale;
  const byTrack = params.color === 'track' && state.meta.kind === 'spots';
  const byImage = params.color === 'image' && state.floorPixels;
  const tmp = new THREE.Color();
  for (let i = 0; i < n; i++) {
    const o = i * NF;
    const t = rawAmplitude(d, o, params.height) / ref;
    const sz = Math.max(t * zs, 1.0) / 2;
    splatSrc.center.set([d[o] - HALF, 0, d[o + 1] - HALF], i * 3);
    splatSrc.cov.set([d[o + 2] * s2, d[o + 3] * s2, d[o + 4] * s2, sz * sz], i * 4);
    let rgb;
    if (byTrack) {
      rgb = trackColor(d[o + 8]);
    } else if (byImage) {
      const px = Math.min(SIZE - 1, Math.max(0, Math.round(d[o])));
      const py = Math.min(SIZE - 1, Math.max(0, Math.round(d[o + 1])));
      const j = (py * SIZE + px) * 4;
      const fp = state.floorPixels;
      tmp.setRGB(fp[j] / 255, fp[j + 1] / 255, fp[j + 2] / 255, THREE.SRGBColorSpace).multiplyScalar(params.imageGain);
      rgb = [tmp.r, tmp.g, tmp.b];
    } else {
      const k = lutIndex(t) * 3;
      rgb = [LUT[k], LUT[k + 1], LUT[k + 2]];
    }
    splatSrc.color.set([rgb[0], rgb[1], rgb[2], params.splatOpacity], i * 4);
  }
  splatSrc.n = n;
  sortSplats();
}

const _camDir = new THREE.Vector3();
function sortSplats() {
  if (!splats.mesh) return;
  const n = splatSrc.n;
  camera.getWorldDirection(_camDir);
  const { order, depth } = splats;
  const cp = camera.position;
  for (let i = 0; i < n; i++) {
    const c = splatSrc.center;
    depth[i] = (c[i * 3] - cp.x) * _camDir.x + (c[i * 3 + 1] - cp.y) * _camDir.y + (c[i * 3 + 2] - cp.z) * _camDir.z;
    order[i] = i;
  }
  const ord = order.subarray(0, n).sort((a, b) => depth[b] - depth[a]); // far to near
  for (let j = 0; j < n; j++) {
    const i = ord[j];
    splats.center.set(splatSrc.center.subarray(i * 3, i * 3 + 3), j * 3);
    splats.cov.set(splatSrc.cov.subarray(i * 4, i * 4 + 4), j * 4);
    splats.color.set(splatSrc.color.subarray(i * 4, i * 4 + 4), j * 4);
  }
  const g = splats.mesh.geometry;
  g.instanceCount = n;
  g.attributes.iCenter.needsUpdate = true;
  g.attributes.iCov.needsUpdate = true;
  g.attributes.iColor.needsUpdate = true;
}

// ---------------------------------------------------------------- frame + UI

const slider = document.getElementById('slider');
const playBtn = document.getElementById('play');
const clock = document.getElementById('clock');
const statsEl = document.getElementById('stats');

function fmtTime(f) {
  const s = f * (state.meta?.seconds_per_frame ?? 15);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return `${h}h ${String(m).padStart(2, '0')}m`;
}

function applyMode() {
  const m = params.mode;
  if (surface.mesh) surface.mesh.visible = m === 'surface';
  if (volume.mesh) volume.mesh.visible = m === 'metaballs';
  if (splats.mesh) splats.mesh.visible = m === 'splats';
  floor.visible = m !== 'surface';
}

function rebuild() {
  if (!state.data) return;
  const t0 = performance.now();
  if (params.mode === 'surface') updateSurface();
  else if (params.mode === 'metaballs') splat3D(state.data);
  else updateSplats();
  applyMode();
  const ms = performance.now() - t0;
  const meta = state.meta;
  statsEl.innerHTML = [
    ['model', `${meta.source} · ${meta.kind === 'image' ? 'image fit' : 'TrackMate spots'}`],
    ['frame', `${state.frame} / ${meta.n_frames - 1}`],
    ['time', fmtTime(state.frame)],
    ['Gaussians', state.data.count.toLocaleString()],
    ['build', `${ms.toFixed(0)} ms`],
  ].map(([k, v]) => `<span>${k}</span><span>${v}</span>`).join('');
}

let requested = 0;
async function showFrame(f) {
  f = Math.max(0, Math.min(state.meta.n_frames - 1, f | 0));
  const token = ++requested;
  const [data, img] = await Promise.all([frameData(f), loadFloor(f)]);
  if (token !== requested) return false; // superseded by a newer request
  state.frame = f;
  state.data = data;
  if (img) {
    floorTex.image = img;
    floorTex.needsUpdate = true;
    if (params.mode === 'splats' && params.color === 'image') state.floorPixels = imagePixels(img);
  }
  slider.value = f;
  clock.textContent = `frame ${f} · ${fmtTime(f)}`;
  rebuild();
  // Prefetch ahead for smooth playback.
  const chunk = state.meta.chunk;
  if (f % chunk > chunk - 12) loadChunk(Math.floor(f / chunk) + 1).catch(() => {});
  for (let k = 1; k <= 12; k++) if (f + k < state.meta.n_frames) loadFloor(f + k);
  return true;
}

const pixelCanvas = document.createElement('canvas');
pixelCanvas.width = pixelCanvas.height = SIZE;
const pixelCtx = pixelCanvas.getContext('2d', { willReadFrequently: true });
function imagePixels(img) {
  pixelCtx.drawImage(img, 0, 0, SIZE, SIZE);
  return pixelCtx.getImageData(0, 0, SIZE, SIZE).data;
}

async function selectModel(name) {
  params.model = name;
  state.meta = await fetchJson(`${WEB_ROOT}${name}/meta.json`);
  state.chunks.clear();
  state.floorImages.clear();
  slider.max = state.meta.n_frames - 1;
  if (state.meta.kind !== 'spots' && params.color === 'track') params.color = 'height';
  gui.controllersRecursive().forEach((c) => c.updateDisplay());
  await showFrame(state.frame);
}

function setPlaying(p) {
  state.playing = p;
  playBtn.textContent = p ? '❚❚' : '▶';
}

function snapshot() {
  renderer.render(scene, camera);
  const a = document.createElement('a');
  a.download = `dicty3d_${params.model}_${params.mode}_f${String(state.frame).padStart(4, '0')}.png`;
  a.href = renderer.domElement.toDataURL('image/png');
  a.click();
}

const gui = new GUI({ title: 'Lift controls' });

async function main() {
  let index;
  try {
    index = await fetchJson(`${WEB_ROOT}index.json`);
  } catch (err) {
    const el = document.getElementById('error');
    el.style.display = 'block';
    el.innerHTML = `Could not load <code>simulation/output/web/index.json</code> (${err.message}).<br><br>
      Build the data with <code>python -m simulation.build</code>, then serve the <b>repo root</b>:
      <code>python -m http.server 8000</code> and open <code>http://localhost:8000/simulation/viewer/</code>.`;
    document.getElementById('loading').remove();
    return;
  }
  const models = index.models;
  params.model = models.includes('timeconvol_image') ? 'timeconvol_image' : models[0];

  // Optional URL state, e.g. ?model=c1_inverted_spots&mode=metaballs&frame=2400&color=track
  const q = new URLSearchParams(location.search);
  if (models.includes(q.get('model'))) params.model = q.get('model');
  for (const k of ['mode', 'height', 'color', 'colormap']) if (q.has(k)) params[k] = q.get(k);
  for (const k of ['zScale', 'sigmaScale', 'metaSigma', 'imageGain']) if (q.has(k)) params[k] = +q.get(k);
  if (q.has('frame')) state.frame = +q.get('frame');
  if (params.colormap !== 'inferno') { LUT = buildLut(params.colormap); refreshLutTexture(); }

  gui.add(params, 'model', models).name('model').onChange(selectModel);
  gui.add(params, 'mode', { 'Surface (height field)': 'surface', 'Metaballs (3D iso-surface)': 'metaballs', 'Gaussian splats': 'splats' })
    .name('render').onChange(() => {
      if (params.mode === 'splats' && params.color === 'image' && floorTex.image instanceof HTMLImageElement) {
        state.floorPixels = imagePixels(floorTex.image);
      }
      rebuild();
    });
  gui.add(params, 'height', { 'mound (size → height)': 'mound', 'intensity': 'intensity', 'mass (volume = Σ intensity)': 'mass' })
    .name('height model').onChange(rebuild);
  gui.add(params, 'color', { height: 'height', 'track (spots only)': 'track', image: 'image' }).name('color by')
    .onChange(() => {
      if (params.color === 'image' && floorTex.image instanceof HTMLImageElement) state.floorPixels = imagePixels(floorTex.image);
      rebuild();
    });
  gui.add(params, 'colormap', Object.keys(COLORMAPS)).onChange((v) => { LUT = buildLut(v); refreshLutTexture(); rebuild(); });
  gui.add(params, 'zScale', 0.1, 4, 0.05).name('z exaggeration').onChange(rebuild);
  gui.add(params, 'imageGain', 0, 2.5, 0.05).name('image brightness').onChange((v) => {
    surfaceUniforms.uImageGain.value = v;
    volumeMat.uniforms.uImageGain.value = v;
    floorMat.color.setScalar(v);
    if (params.mode === 'splats') rebuild();
  });
  const fShape = gui.addFolder('Gaussian shape');
  fShape.add(params, 'sigmaScale', 0.4, 3, 0.05).name('σ scale (surface/splat)').onChange(rebuild);
  fShape.add(params, 'metaSigma', 0.5, 3, 0.05).name('σ scale (metaballs)').onChange(rebuild);
  fShape.add(params, 'splatOpacity', 0.05, 1, 0.01).name('splat opacity').onChange(rebuild);
  const fQual = gui.addFolder('Quality');
  fQual.add(params, 'gridRes', [128, 192, 256, 384, 512]).name('surface grid').onChange(rebuild);
  fQual.add(params, 'volRes', [96, 128, 160, 224, 288]).name('volume grid').onChange(rebuild);
  fQual.close();
  const fPlay = gui.addFolder('Playback & view');
  fPlay.add(params, 'fps', 1, 60, 1).name('frames / s');
  fPlay.add(params, 'autoRotate').name('auto-rotate').onChange((v) => { controls.autoRotate = v; });
  fPlay.add(params, 'snapshot').name('save PNG');

  slider.addEventListener('input', () => { setPlaying(false); showFrame(+slider.value); });
  playBtn.addEventListener('click', () => setPlaying(!state.playing));
  window.addEventListener('keydown', (e) => {
    if (e.target instanceof HTMLInputElement && e.target.type !== 'range') return;
    if (e.target === slider && e.code.startsWith('Arrow')) return; // the slider steps itself
    if (e.code === 'Space') { e.preventDefault(); setPlaying(!state.playing); }
    if (e.code === 'ArrowRight') { setPlaying(false); showFrame(state.frame + (e.shiftKey ? 50 : 1)); }
    if (e.code === 'ArrowLeft') { setPlaying(false); showFrame(state.frame - (e.shiftKey ? 50 : 1)); }
  });

  await selectModel(params.model);
  document.getElementById('loading').remove();
  animate();
}

let lastAdvance = 0;
let advancing = false;
const lastCam = new THREE.Matrix4();
function animate(now = 0) {
  requestAnimationFrame(animate);
  controls.update();
  if (state.playing && !advancing && now - lastAdvance >= 1000 / params.fps) {
    advancing = true;
    lastAdvance = now;
    const next = state.frame + 1 >= state.meta.n_frames ? 0 : state.frame + 1;
    showFrame(next).finally(() => { advancing = false; });
  }
  if (params.mode === 'splats' && !camera.matrixWorld.equals(lastCam)) {
    sortSplats();
    lastCam.copy(camera.matrixWorld);
  }
  const size = renderer.getDrawingBufferSize(new THREE.Vector2());
  splatMat.uniforms.uViewport.value.copy(size);
  volumeMat.uniforms.uViewProj.value.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
  renderer.render(scene, camera);
}

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

main();
