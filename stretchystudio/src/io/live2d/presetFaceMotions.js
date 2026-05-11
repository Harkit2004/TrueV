/**
 * Preset .motion3.json clips for standard face parameters (blink / mouth demo).
 *
 * @module io/live2d/presetFaceMotions
 */

import { encodeKeyframesToSegments } from './motion3json.js';

function motionMeta(durationSec, fps, loop, curveCount, segCount, ptCount) {
  return {
    Duration: durationSec,
    Fps: fps,
    Loop: loop,
    AreBeziersRestricted: false,
    CurveCount: curveCount,
    TotalSegmentCount: segCount,
    TotalPointCount: ptCount,
    UserDataCount: 0,
    TotalUserDataSize: 0,
  };
}

function countSegPts(segments) {
  let segCount = 0;
  let ptCount = 1;
  let i = 2;
  while (i < segments.length) {
    const type = segments[i];
    segCount++;
    i++;
    if (type === 1) {
      ptCount += 3;
      i += 6;
    } else {
      ptCount += 1;
      i += 2;
    }
  }
  return { segments: segCount, points: ptCount };
}

/**
 * Looping blink on ParamEyeLOpen + ParamEyeROpen (same curve).
 *
 * @returns {object}
 */
export function generatePresetBlinkMotion3Json() {
  const durationMs = 4000;
  const durationSec = durationMs / 1000;
  const fps = 30;
  const kf = [
    { time: 0, value: 1, easing: 'linear' },
    { time: 120, value: 0.05, easing: 'linear' },
    { time: 200, value: 1, easing: 'linear' },
    { time: 2800, value: 1, easing: 'linear' },
    { time: 2920, value: 0.05, easing: 'linear' },
    { time: 3000, value: 1, easing: 'linear' },
    { time: durationMs, value: 1, easing: 'linear' },
  ];
  const segL = encodeKeyframesToSegments(kf, durationSec);
  const segR = encodeKeyframesToSegments(kf, durationSec);
  const cL = countSegPts(segL);
  const cR = countSegPts(segR);
  const curves = [
    { Target: 'Parameter', Id: 'ParamEyeLOpen', Segments: segL },
    { Target: 'Parameter', Id: 'ParamEyeROpen', Segments: segR },
  ];
  return {
    Version: 3,
    Meta: {
      ...motionMeta(durationSec, fps, true, curves.length, cL.segments + cR.segments, cL.points + cR.points),
    },
    Curves: curves,
  };
}

/**
 * Short mouth open/close demo on ParamMouthOpenY.
 *
 * @returns {object}
 */
export function generatePresetMouthMotion3Json() {
  const durationMs = 2400;
  const durationSec = durationMs / 1000;
  const fps = 30;
  const kf = [
    { time: 0, value: 0, easing: 'linear' },
    { time: 400, value: 0.75, easing: 'linear' },
    { time: 900, value: 0.1, easing: 'linear' },
    { time: 1400, value: 0.85, easing: 'linear' },
    { time: 2000, value: 0, easing: 'linear' },
    { time: durationMs, value: 0, easing: 'linear' },
  ];
  const seg = encodeKeyframesToSegments(kf, durationSec);
  const c = countSegPts(seg);
  const curves = [{ Target: 'Parameter', Id: 'ParamMouthOpenY', Segments: seg }];
  return {
    Version: 3,
    Meta: {
      ...motionMeta(durationSec, fps, true, 1, c.segments, c.points),
    },
    Curves: curves,
  };
}
