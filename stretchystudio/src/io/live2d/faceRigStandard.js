/**
 * Shared face-rig conventions for Live2D export (.cmo3 + .moc3 runtime parity).
 * Standard parameter IDs match Cubism / VTube Studio expectations.
 *
 * Product choice: ship **both** (1) runtime atlas `.moc3` with synthetic face warps
 * when tagged meshes exist, and (2) **Cubism Editor** workflow via `.cmo3` for
 * full-quality closure and published SDK models.
 *
 * @module io/live2d/faceRigStandard
 */

/** Tags that participate in per-eye closure in cmo3writer (keep in sync). */
export const EYE_CLOSURE_TAGS = new Set([
  'eyelash-l', 'eyewhite-l', 'irides-l',
  'eyelash-r', 'eyewhite-r', 'irides-r',
  'irides', 'eyes',
]);

const LEFT_EYE_TAG_ORDER = ['eyelash-l', 'eyewhite-l', 'irides-l', 'irides', 'eyes'];
const RIGHT_EYE_TAG_ORDER = ['eyelash-r', 'eyewhite-r', 'irides-r'];

/** Minimal standard params for blink / mouth open on runtime .moc3 */
export const FACE_STANDARD_PARAM_DEFS = [
  { id: 'ParamEyeLOpen', min: 0, max: 1, default: 1 },
  { id: 'ParamEyeROpen', min: 0, max: 1, default: 1 },
  { id: 'ParamMouthOpenY', min: 0, max: 1, default: 0 },
];

/**
 * @param {object} project
 * @param {Map<string, unknown>|null} regions - if set, only meshes present in atlas export
 * @returns {{ mouth: object|null, eyeL: object|null, eyeR: object|null }}
 */
export function resolveFaceRigMeshes(project, regions = null) {
  const nodes = project.nodes ?? [];
  const meshParts = nodes.filter(
    n => n.type === 'part' && n.mesh && n.visible !== false,
  );
  const inExport = (id) => !regions || regions.has(id);

  let eyeL = null;
  for (const tag of LEFT_EYE_TAG_ORDER) {
    const m = meshParts.find(p => p.tag === tag && inExport(p.id));
    if (m) {
      eyeL = m;
      break;
    }
  }
  let eyeR = null;
  for (const tag of RIGHT_EYE_TAG_ORDER) {
    const m = meshParts.find(p => p.tag === tag && inExport(p.id));
    if (m) {
      eyeR = m;
      break;
    }
  }
  const mouth = meshParts.find(p => p.tag === 'mouth' && inExport(p.id)) ?? null;

  return { mouth, eyeL, eyeR };
}

/**
 * @param {{ mouth: object|null, eyeL: object|null, eyeR: object|null }} face
 * @returns {boolean}
 */
export function faceRigHasAnyTarget(face) {
  return !!(face.mouth || face.eyeL || face.eyeR);
}

/**
 * Merge face standard params into an existing param list (no duplicate ids).
 *
 * @param {Array<{id:string,min?:number,max?:number,default?:number}>} paramList
 */
export function mergeFaceStandardParams(paramList) {
  const ids = new Set(paramList.map(p => p.id));
  for (const d of FACE_STANDARD_PARAM_DEFS) {
    if (!ids.has(d.id)) {
      paramList.push({
        id: d.id,
        min: d.min,
        max: d.max,
        default: d.default,
      });
      ids.add(d.id);
    }
  }
}

/**
 * model3.json Groups for SDK lip sync / eye blink (when meshes exist).
 *
 * @param {{ mouth: object|null, eyeL: object|null, eyeR: object|null }} face
 * @returns {Record<string, string[]>}
 */
export function model3GroupsForFaceRig(face) {
  const groups = {};
  if (face.mouth) {
    groups.LipSync = ['ParamMouthOpenY'];
  }
  if (face.eyeL || face.eyeR) {
    groups.EyeBlink = ['ParamEyeLOpen', 'ParamEyeROpen'];
  }
  return groups;
}

/**
 * Nearest ancestor group id for hierarchy / warp parent.
 *
 * @param {object} project
 * @param {string} nodeId
 * @returns {string|null}
 */
export function nearestAncestorGroupId(project, nodeId) {
  const nodes = project.nodes ?? [];
  const byId = new Map(nodes.map(n => [n.id, n]));
  let cur = byId.get(nodeId);
  while (cur) {
    if (cur.type === 'group') return cur.id;
    cur = cur.parent ? byId.get(cur.parent) : null;
  }
  return null;
}

/**
 * Axis-aligned bbox of mesh vertices (canvas px).
 *
 * @param {object} part - part with .mesh.vertices [{x,y},...]
 * @returns {{ minX:number,maxX:number,minY:number,maxY:number,cx:number,cy:number,w:number,h:number }|null}
 */
export function meshCanvasBBox(part) {
  const verts = part?.mesh?.vertices;
  if (!verts?.length) return null;
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const v of verts) {
    if (v.x < minX) minX = v.x;
    if (v.x > maxX) maxX = v.x;
    if (v.y < minY) minY = v.y;
    if (v.y > maxY) maxY = v.y;
  }
  if (!Number.isFinite(minX)) return null;
  return {
    minX, maxX, minY, maxY,
    cx: (minX + maxX) / 2,
    cy: (minY + maxY) / 2,
    w: maxX - minX,
    h: maxY - minY,
  };
}

/**
 * Build 2×2 warp grid control points (row-major: (row,col) with row outer).
 *
 * @param {number} gx
 * @param {number} gy
 * @param {number} gw
 * @param {number} gh
 * @param {number} col
 * @param {number} row
 * @returns {{ x: number, y: number }[]}
 */
export function makeWarpGridPoints(gx, gy, gw, gh, col, row) {
  const pts = [];
  for (let r = 0; r <= row; r++) {
    for (let c = 0; c <= col; c++) {
      const tx = col > 0 ? c / col : 0;
      const ty = row > 0 ? r / row : 0;
      pts.push({ x: gx + tx * gw, y: gy + ty * gh });
    }
  }
  return pts;
}

/**
 * Eye blink: outer rows move toward middle row in Y (param 0 = open, 1 = closed).
 *
 * @param {{ x: number, y: number }[]} restPts
 * @param {number} col
 * @param {number} row
 * @param {number} amount - 0 open .. 1 closed
 */
export function blendEyeWarpSquash(restPts, col, row, amount) {
  const out = restPts.map(p => ({ ...p }));
  if (amount <= 0 || row < 1) return out;
  const midR = Math.max(0, Math.min(row, Math.floor(row / 2)));
  for (let r = 0; r <= row; r++) {
    const edge = r <= midR
      ? (midR > 0 ? r / midR : 0)
      : (row - midR > 0 ? (row - r) / (row - midR) : 0);
    const pull = amount * 0.5 * edge;
    for (let c = 0; c <= col; c++) {
      const i = r * (col + 1) + c;
      const centerY = restPts[midR * (col + 1) + c].y;
      out[i].y += (centerY - out[i].y) * pull;
    }
  }
  return out;
}

/**
 * Mouth open: shift bottom grid row downward in canvas space.
 *
 * @param {{ x: number, y: number }[]} restPts
 * @param {number} col
 * @param {number} row
 * @param {number} amount
 * @param {number} jawPx
 */
export function blendMouthWarpOpen(restPts, col, row, amount, jawPx) {
  const out = restPts.map(p => ({ ...p }));
  if (amount <= 0 || row < 1) return out;
  const shift = jawPx * amount;
  for (let c = 0; c <= col; c++) {
    const i = row * (col + 1) + c;
    out[i].y += shift;
  }
  return out;
}
