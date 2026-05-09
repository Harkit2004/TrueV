/**
 * Helpers for validating expression PSDs against a base (same layer names / canvas size).
 * Use with img2img-generated expression stacks before Stretchy Live2D export.
 *
 * @module io/expressionPsdPipeline
 */

/**
 * @param {{ name: string, width: number, height: number, x: number, y: number }[]} baseLayers
 * @param {{ name: string, width: number, height: number, x: number, y: number }[]} exprLayers
 * @returns {{ ok: boolean, mismatches: string[] }}
 */
export function validateExpressionPsdStructure(baseLayers, exprLayers) {
  const mismatches = [];
  const baseByName = new Map(baseLayers.map((l) => [l.name.trim().toLowerCase(), l]));
  const exprByName = new Map(exprLayers.map((l) => [l.name.trim().toLowerCase(), l]));
  if (baseLayers.length !== exprLayers.length) {
    mismatches.push(`layer count differs: base ${baseLayers.length} vs expression ${exprLayers.length}`);
  }
  for (const bl of baseLayers) {
    const key = bl.name.trim().toLowerCase();
    const el = exprByName.get(key);
    if (!el) mismatches.push(`missing layer in expression PSD: "${bl.name}"`);
    else if (bl.width !== el.width || bl.height !== el.height) {
      mismatches.push(`size mismatch for "${bl.name}": base ${bl.width}×${bl.height} vs expr ${el.width}×${el.height}`);
    }
  }
  for (const el of exprLayers) {
    const key = el.name.trim().toLowerCase();
    if (!baseByName.has(key)) mismatches.push(`extra layer in expression PSD: "${el.name}"`);
  }
  return { ok: mismatches.length === 0, mismatches };
}
