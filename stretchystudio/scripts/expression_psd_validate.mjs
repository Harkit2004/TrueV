/**
 * CLI: compare two PSDs' layer names and raster dimensions (expression vs base).
 *
 * Usage:
 *   node scripts/expression_psd_validate.mjs --base path/to/base.psd --expr path/to/expr.psd
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { initializeCanvas } from 'ag-psd';
import { createCanvas } from 'canvas';

import { importPsd } from '../src/io/psd.js';
import { validateExpressionPsdStructure } from '../src/io/expressionPsdPipeline.js';

function ensureCanvas() {
  initializeCanvas(
    (w, h) => createCanvas(w, h),
    (w, h) => createCanvas(Math.max(1, w), Math.max(1, h)).getContext('2d').createImageData(w, h),
  );
}

function parseArgs(argv) {
  const out = { base: null, expr: null };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--base') out.base = argv[++i];
    else if (a === '--expr') out.expr = argv[++i];
  }
  return out;
}

function layerMeta(layers) {
  return layers.map((l) => ({
    name: l.name ?? '',
    width: l.width ?? 0,
    height: l.height ?? 0,
    x: l.x ?? 0,
    y: l.y ?? 0,
  }));
}

async function main() {
  const { base, expr } = parseArgs(process.argv);
  if (!base || !expr) {
    console.error('Usage: node scripts/expression_psd_validate.mjs --base <.psd> --expr <.psd>');
    process.exit(1);
  }
  ensureCanvas();
  const absB = path.isAbsolute(base) ? base : path.resolve(process.cwd(), base);
  const absE = path.isAbsolute(expr) ? expr : path.resolve(process.cwd(), expr);
  const bufB = await fs.readFile(absB);
  const bufE = await fs.readFile(absE);
  const pb = importPsd(bufB.buffer.slice(bufB.byteOffset, bufB.byteOffset + bufB.byteLength));
  const pe = importPsd(bufE.buffer.slice(bufE.byteOffset, bufE.byteOffset + bufE.byteLength));
  if (pb.width !== pe.width || pb.height !== pe.height) {
    console.error(`Canvas mismatch: base ${pb.width}×${pb.height} vs expr ${pe.width}×${pe.height}`);
    process.exit(2);
  }
  const metaB = layerMeta(pb.layers);
  const metaE = layerMeta(pe.layers);
  const { ok, mismatches } = validateExpressionPsdStructure(metaB, metaE);
  if (ok) {
    console.error('OK: layer names and sizes match.');
    process.exit(0);
  }
  console.error('Mismatches:');
  for (const m of mismatches) console.error(`  - ${m}`);
  process.exit(3);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
