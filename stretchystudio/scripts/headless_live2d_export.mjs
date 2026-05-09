/**
 * CLI: PSD → Live2D CAFF (.cmo3) via headless Stretchy pipeline (same project export as the app).
 * Writes a single Cubism-openable .cmo3 (no animations in the PSD path). If the exporter ever
 * returns a ZIP (e.g. rig debug bundle), the inner `${modelName}.cmo3` is extracted automatically.
 *
 * Usage:
 *   node scripts/headless_live2d_export.mjs --psd-in path/to.psd --out out.cmo3 [--model-name name]
 *   (--zip-out is an alias for --out)
 */

import fs from 'node:fs/promises';
import path from 'node:path';

import { exportLive2dBlobFromPsdBuffer } from '../src/io/headlessCharacterPipeline.js';

/** @param {Uint8Array} u8 */
function looksLikeZip(u8) {
  return u8.length >= 4 && u8[0] === 0x50 && u8[1] === 0x4b;
}

/**
 * If bytes are a ZIP containing `${modelName}.cmo3`, return those inner bytes; else return as-is.
 * @param {Uint8Array} u8
 * @param {string} modelName
 */
async function ensureBareCmo3Bytes(u8, modelName) {
  if (!looksLikeZip(u8)) return u8;
  const { default: JSZip } = await import('jszip');
  const zip = await JSZip.loadAsync(u8);
  const innerName = `${modelName}.cmo3`;
  const entry = zip.file(innerName);
  if (!entry) {
    const names = Object.keys(zip.files).filter((k) => !zip.files[k].dir);
    throw new Error(
      `Export returned ZIP but "${innerName}" not found. Entries: ${names.join(', ') || '(none)'}`,
    );
  }
  return /** @type {Uint8Array} */ (await entry.async('uint8array'));
}

function parseArgs(argv) {
  const out = { psdIn: null, outPath: null, modelName: 'character' };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--psd-in') out.psdIn = argv[++i];
    else if (a === '--out' || a === '--zip-out') out.outPath = argv[++i];
    else if (a === '--model-name') out.modelName = argv[++i];
  }
  return out;
}

async function main() {
  const { psdIn, outPath, modelName } = parseArgs(process.argv);
  if (!psdIn || !outPath) {
    console.error(
      'Usage: node scripts/headless_live2d_export.mjs --psd-in <.psd> --out <file.cmo3> [--model-name name]\n'
      + '  (--zip-out is accepted as an alias for --out)',
    );
    process.exit(1);
  }
  const absPsd = path.isAbsolute(psdIn) ? psdIn : path.resolve(process.cwd(), psdIn);
  const absOut = path.isAbsolute(outPath) ? outPath : path.resolve(process.cwd(), outPath);

  const buf = await fs.readFile(absPsd);
  const blob = await exportLive2dBlobFromPsdBuffer(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength), {
    modelName,
    onProgress: (m) => console.error(m),
  });
  let u8 = new Uint8Array(await blob.arrayBuffer());
  u8 = await ensureBareCmo3Bytes(u8, modelName);
  await fs.writeFile(absOut, Buffer.from(u8.buffer, u8.byteOffset, u8.byteLength));

  console.error(`Wrote ${absOut} (${u8.byteLength} bytes)`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
