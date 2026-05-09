/**
 * Live2D Cubism .exp3.json (expression) generator.
 *
 * @see https://docs.live2d.com/en/cubism-sdk-manual/expression/
 * @module io/live2d/exp3json
 */

/**
 * @typedef {Object} Exp3Parameter
 * @property {string} id   - Live2D parameter id (e.g. ParamMouthForm)
 * @property {number} value
 * @property {'Add'|'Multiply'|'Overwrite'} [blend='Add']
 */

/**
 * Build one expression JSON object (file body only).
 *
 * @param {Object} opts
 * @param {Exp3Parameter[]} opts.parameters
 * @param {number} [opts.fadeInTime]
 * @param {number} [opts.fadeOutTime]
 * @returns {object}
 */
export function generateExp3Json(opts) {
  const { parameters, fadeInTime, fadeOutTime } = opts;
  const out = {
    Type: 'Live2D Expression',
    Parameters: (parameters ?? []).map((p) => ({
      Id: p.id,
      Value: p.value,
      Blend: p.blend ?? 'Add',
    })),
  };
  if (fadeInTime != null) out.FadeInTime = fadeInTime;
  if (fadeOutTime != null) out.FadeOutTime = fadeOutTime;
  return out;
}
