/**
 * Mesh generation Web Worker entry point.
 *
 * Receives:  { imageData: {data, width, height}, opts }
 * Responds:  { vertices, uvs, triangles, edgeIndices }
 *
 * Note: Sets (edgeIndices) can't be transferred — send as plain Array.
 */
import { generateMesh } from './generate.js';

self.onmessage = function (e) {
  const { imageData, opts } = e.data;

  try {
    const result = generateMesh(
      imageData.data,
      imageData.width,
      imageData.height,
      opts
    );

    // Serialise the Set → Array for postMessage
    self.postMessage({
      ok: true,
      vertices: result.vertices,
      uvs: result.uvs,
      triangles: result.triangles,
      edgeIndices: Array.from(result.edgeIndices),
    }, [result.uvs.buffer]); // Transfer the Float32Array buffer

  } catch (err) {
    self.postMessage({ ok: false, error: err.message });
  }
};
