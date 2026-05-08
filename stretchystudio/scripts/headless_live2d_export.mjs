/**
 * CLI: PSD → Live2D (.cmo3) via headless Stretchy pipeline.
 * Usage: node scripts/headless_live2d_export.mjs --psd-in path/to.psd --zip-out out.cmo3 [--model-name name]
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { exportLive2dBlobFromPsdBuffer } from '../src/io/headlessCharacterPipeline.js';

function parseArgs(argv) {
  const out = { psdIn: null, zipOut: null, modelName: 'character' };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--psd-in') out.psdIn = argv[++i];
    else if (a === '--zip-out') out.zipOut = argv[++i];
    else if (a === '--model-name') out.modelName = argv[++i];
  }
  return out;
}

async function main() {
  const { psdIn, zipOut, modelName } = parseArgs(process.argv);
  if (!psdIn || !zipOut) {
    console.error('Usage: node scripts/headless_live2d_export.mjs --psd-in <.psd> --zip-out <out> [--model-name name]');
    process.exit(1);
  }
  const absPsd = path.isAbsolute(psdIn) ? psdIn : path.resolve(process.cwd(), psdIn);
  const absOut = path.isAbsolute(zipOut) ? zipOut : path.resolve(process.cwd(), zipOut);

  const buf = await fs.readFile(absPsd);
  const blob = await exportLive2dBlobFromPsdBuffer(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength), {
    modelName,
    onProgress: (m) => console.error(m),
  });
  const ab = await blob.arrayBuffer();
  await fs.writeFile(absOut, Buffer.from(ab));

  console.error(`Wrote ${absOut} (${ab.byteLength} bytes)`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
