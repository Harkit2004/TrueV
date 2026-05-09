/**
 * PSD character format auto-organizer.
 *
 * Detects whether imported PSD layers follow the expected character part naming
 * convention, and if so, organizes them into a Head / Body / Extras group hierarchy
 * while PRESERVING the original PSD draw order.
 */

export const KNOWN_TAGS = [
  'back hair', 'front hair',
  'headwear', 'face', 'irides', 'eyebrow', 'eyewhite', 'eyelash', 'eyewear',
  'ears', 'earwear', 'nose', 'mouth',
  'neck', 'neckwear', 'topwear', 'handwear', 'bottomwear', 'legwear', 'footwear',
  'tail', 'wings', 'objects',
];


// tag → group path (outermost → innermost)
const TAG_TO_GROUPS = {
  'back hair':  ['body', 'upperbody', 'head'],
  'front hair': ['body', 'upperbody', 'head'],
  'headwear':   ['body', 'upperbody', 'head'],
  'face':       ['body', 'upperbody', 'head'],
  'irides':     ['body', 'upperbody', 'head', 'eyes'],
  'eyebrow':    ['body', 'upperbody', 'head', 'eyes'],
  'eyewhite':   ['body', 'upperbody', 'head', 'eyes'],
  'eyelash':    ['body', 'upperbody', 'head', 'eyes'],
  'eyewear':    ['body', 'upperbody', 'head', 'eyes'],
  'ears':       ['body', 'upperbody', 'head'],
  'earwear':    ['body', 'upperbody', 'head'],
  'nose':       ['body', 'upperbody', 'head'],
  'mouth':      ['body', 'upperbody', 'head'],
  'neck':       ['body', 'upperbody'],
  'neckwear':   ['body', 'upperbody'],
  'topwear':    ['body', 'upperbody'],
  'handwear':   ['body', 'upperbody'],
  'bottomwear': ['body', 'lowerbody'],
  'legwear':    ['body', 'lowerbody'],
  'footwear':   ['body', 'lowerbody'],
  'tail':       ['body', 'extras'],
  'wings':      ['body', 'extras'],
  'objects':    ['body', 'extras'],
};

// Parent group for each group name (null = root)
const GROUP_PARENT = {
  eyes:      'head',
  head:      'upperbody',
  upperbody: 'body',
  lowerbody: 'body',
  extras:    'body',
  body:      null,
};

// Creation order — parents before children
const GROUP_CREATE_ORDER = ['body', 'upperbody', 'lowerbody', 'head', 'extras', 'eyes'];

/** Lower value = drawn further back; higher = more in front (Cubism drawOrder). */
const TAG_DRAW_PRIORITY = {
  objects: 5,
  'back hair': 12,
  wings: 14,
  tail: 14,
  bottomwear: 22,
  legwear: 24,
  footwear: 26,
  topwear: 36,
  neck: 44,
  neckwear: 45,
  handwear: 46,
  face: 54,
  ears: 55,
  earwear: 56,
  nose: 57,
  eyebrow: 58,
  'eyebrow-l': 58,
  'eyebrow-r': 58,
  eyewear: 59,
  eyewhite: 64,
  'eyewhite-l': 64,
  'eyewhite-r': 64,
  irides: 66,
  'irides-l': 66,
  'irides-r': 66,
  eyes: 66,
  eyel: 66,
  eyer: 66,
  mouth: 67,
  eyelash: 69,
  'eyelash-l': 69,
  'eyelash-r': 69,
  'front hair': 84,
  headwear: 90,
};

/** Returns the matched tag for a layer name, or null. */
export function matchTag(name) {
  const lower = name.toLowerCase().trim();
  // Exact match first — prevents 'handwear' from matching 'handwear-l', etc.
  for (const tag of KNOWN_TAGS) {
    if (lower === tag) return tag;
  }
  for (const tag of KNOWN_TAGS) {
    if (
      lower.startsWith(tag + '-') ||
      lower.startsWith(tag + ' ') ||
      lower.startsWith(tag + '_')
    ) return tag;
  }
  return null;
}

/** Returns true if at least 4 layers match known character part tags. */
export function detectCharacterFormat(layers) {
  const hits = layers.filter(l => matchTag(l.name) !== null).length;
  return hits >= 4;
}

/**
 * Computes group definitions and per-layer assignments for organized import.
 *
 * @param {object[]} layers   - flat array from importPsd
 * @param {()=>string} uidFn  - uid generator (same as used for part nodes)
 * @returns {{
 *   groupDefs: {id:string, name:string, parentId:string|null}[],
 *   assignments: Map<number, {parentGroupId:string|null, drawOrder:number}>
 * }}
 */
export function organizeCharacterLayers(layers, uidFn) {
  const tagged = layers.map((layer, i) => ({ i, tag: matchTag(layer.name) }));

  // Which groups are actually needed?
  const neededGroups = new Set();
  tagged.forEach(({ tag }) => {
    if (tag) TAG_TO_GROUPS[tag]?.forEach(g => neededGroups.add(g));
  });

  // Create group nodes (parents first so IDs exist when children reference them)
  const groupIds = {};
  const groupDefs = [];
  for (const gName of GROUP_CREATE_ORDER) {
    if (!neededGroups.has(gName)) continue;
    const id = uidFn();
    groupIds[gName] = id;
    groupDefs.push({ id, name: gName, parentId: GROUP_PARENT[gName] ? groupIds[GROUP_PARENT[gName]] : null });
  }

  // Build assignments: semantic draw stack for tagged layers (neck vs collar, etc.),
  // stable within same tag by original PSD depth (numLayers - 1 - i).
  const assignments = new Map();
  const numLayers = layers.length;
  const items = tagged.map((item) => {
    const groups = item.tag ? TAG_TO_GROUPS[item.tag] : null;
    const innermost = groups ? groups[groups.length - 1] : null;
    const baseOrder = numLayers - 1 - item.i;
    const pri = item.tag != null ? (TAG_DRAW_PRIORITY[item.tag] ?? 50) : 50;
    return {
      i: item.i,
      tag: item.tag,
      parentGroupId: innermost ? (groupIds[innermost] ?? null) : null,
      baseOrder,
      pri,
    };
  });
  items.sort((a, b) => {
    if (a.pri !== b.pri) return a.pri - b.pri;
    return a.baseOrder - b.baseOrder;
  });
  for (let rank = 0; rank < items.length; rank++) {
    const row = items[rank];
    assignments.set(row.i, {
      parentGroupId: row.parentGroupId,
      drawOrder: rank,
    });
  }

  return { groupDefs, assignments };
}
