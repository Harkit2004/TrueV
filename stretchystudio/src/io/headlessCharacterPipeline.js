/**
 * Headless PSD → Stretchy project → Live2D (.cmo3) for GPU/server pipelines.
 * Requires `canvas` (node-canvas) and ag-psd initialized via initializeCanvas.
 */

import { createCanvas, Image } from 'canvas';
import { initializeCanvas } from 'ag-psd';

import { importPsd } from './psd.js';
import { detectCharacterFormat, organizeCharacterLayers } from './psdOrganizer.js';
import { generateMesh } from '../mesh/generate.js';
import { exportLive2DProject } from './live2d/exporter.js';

let _canvasInitialized = false;

function ensureAgPsdCanvas() {
  if (_canvasInitialized) return;
  initializeCanvas(
    (w, h) => createCanvas(w, h),
    (w, h) => createCanvas(Math.max(1, w), Math.max(1, h)).getContext('2d').createImageData(w, h),
  );
  _canvasInitialized = true;
}

function uid() {
  return `p${Math.random().toString(36).slice(2, 11)}`;
}

/** @param {ImageData} imageData */
function computeImageBounds(imageData, alphaThreshold = 10) {
  let minX = imageData.width;
  let minY = imageData.height;
  let maxX = -1;
  let maxY = -1;
  const data = imageData.data;
  const w = imageData.width;
  for (let y = 0; y < imageData.height; y++) {
    for (let x = 0; x < w; x++) {
      const alpha = data[(y * w + x) * 4 + 3];
      if (alpha > alphaThreshold) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }
  return minX <= maxX ? { minX, minY, maxX, maxY } : null;
}

function computeSmartMeshOpts(imageBounds) {
  if (!imageBounds) {
    return { alphaThreshold: 5, smoothPasses: 0, gridSpacing: 30, edgePadding: 8, numEdgePoints: 80 };
  }
  const w = imageBounds.maxX - imageBounds.minX;
  const h = imageBounds.maxY - imageBounds.minY;
  const sqrtArea = Math.sqrt(w * h);
  return {
    alphaThreshold: 5,
    smoothPasses: 0,
    gridSpacing: Math.max(6, Math.min(80, Math.round(sqrtArea * 0.08))),
    edgePadding: 8,
    numEdgePoints: Math.max(12, Math.min(300, Math.round(sqrtArea * 0.4))),
  };
}

/**
 * @param {ArrayBuffer} psdBuffer
 * @returns {{ project: object, images: Map<string, import('canvas').Image> }}
 */
export async function buildProjectAndImagesFromPsdBuffer(psdBuffer) {
  ensureAgPsdCanvas();

  const { width: psdW, height: psdH, layers } = importPsd(psdBuffer);
  if (!layers.length) {
    throw new Error('No raster layers in PSD');
  }

  const useGroups = detectCharacterFormat(layers);
  const partIds = layers.map(() => uid());

  let groupDefs = [];
  /** @type {Map<number, { parentGroupId: string | null, drawOrder: number }> | null} */
  let assignments = null;
  if (useGroups) {
    const org = organizeCharacterLayers(layers, uid);
    groupDefs = org.groupDefs;
    assignments = org.assignments;
  }

  const project = {
    version: '0.1',
    canvas: { width: psdW, height: psdH, x: 0, y: 0, bgEnabled: false, bgColor: '#ffffff' },
    textures: [],
    nodes: [],
    parameters: [],
    physics_groups: [],
    physicsRules: [],
    animations: [],
  };

  const images = new Map();
  const numLayers = layers.length;

  for (const g of groupDefs) {
    project.nodes.push({
      id: g.id,
      type: 'group',
      name: g.name,
      parent: g.parentId,
      opacity: 1,
      visible: true,
      boneRole: g.boneRole ?? null,
      transform: { x: 0, y: 0, rotation: 0, scaleX: 1, scaleY: 1, pivotX: 0, pivotY: 0 },
    });
  }

  layers.forEach((layer, i) => {
    const partId = partIds[i];
    const off = createCanvas(psdW, psdH);
    const ctx = off.getContext('2d');
    const tmp = createCanvas(layer.width, layer.height);
    tmp.getContext('2d').putImageData(layer.imageData, 0, 0);
    ctx.drawImage(tmp, layer.x, layer.y);
    const fullImageData = ctx.getImageData(0, 0, psdW, psdH);

    const imageBounds = computeImageBounds(fullImageData);

    const pngBuf = off.toBuffer('image/png');
    const img = new Image();
    img.src = pngBuf;

    project.textures.push({ id: partId, source: '' });
    const assignment = assignments?.get(i);
    project.nodes.push({
      id: partId,
      type: 'part',
      name: layer.name,
      parent: assignment?.parentGroupId ?? null,
      draw_order: assignment?.drawOrder ?? (numLayers - 1 - i),
      opacity: layer.opacity,
      visible: layer.visible,
      clip_mask: null,
      transform: {
        x: 0,
        y: 0,
        rotation: 0,
        scaleX: 1,
        scaleY: 1,
        pivotX: psdW / 2,
        pivotY: psdH / 2,
      },
      meshOpts: null,
      mesh: null,
      imageWidth: psdW,
      imageHeight: psdH,
      imageBounds: imageBounds || { minX: 0, minY: 0, maxX: psdW, maxY: psdH },
    });
    images.set(partId, img);
  });

  for (const node of project.nodes) {
    if (node.type !== 'part') continue;
    const img = images.get(node.id);
    if (!img) continue;
    const off = createCanvas(psdW, psdH);
    const meshCtx = off.getContext('2d');
    meshCtx.drawImage(img, 0, 0);
    const imageData = meshCtx.getImageData(0, 0, psdW, psdH);
    const opts = computeSmartMeshOpts(node.imageBounds);
    const { vertices, uvs, triangles, edgeIndices } = generateMesh(
      imageData.data,
      psdW,
      psdH,
      opts,
    );
    node.mesh = {
      vertices,
      uvs: Array.from(uvs),
      triangles,
      edgeIndices,
    };
  }

  return { project, images };
}

/**
 * Full PSD buffer → Live2D project blob (.cmo3 or zip).
 * @param {ArrayBuffer} psdBuffer
 * @param {{ modelName?: string, onProgress?: (s: string) => void }} [opts]
 */
export async function exportLive2dBlobFromPsdBuffer(psdBuffer, opts = {}) {
  const { project, images } = await buildProjectAndImagesFromPsdBuffer(psdBuffer);
  const modelName = opts.modelName ?? 'character';
  return exportLive2DProject(project, images, {
    modelName,
    generateRig: true,
    generatePhysics: true,
    headlessCreateCanvas: (w, h) => createCanvas(w, h),
    onProgress: opts.onProgress ?? (() => {}),
  });
}
