/**
 * Draws one frame of a flight onto a canvas. The vertical axis is proportional to the altitude;
 * the horizontal axis shares its scale whenever the track fits, so a bottle flight keeps its real
 * shape. The rocket glyph has a fixed size in pixels and is not to scale.
 */

import {
  niceStep,
  PHASE_COLOR,
  phaseAt,
  sampleIndexAt,
  thrustOf,
  type FlightTimeline,
} from "./flightPlayback";

const COLOR = {
  background: "#ffffff",
  grid: "#e1e6ec",
  axis: "#3d4752",
  ground: "#3d4752",
  future: "#8e99a6",
  body: "#26323d",
  fin: "#1a4db0",
  flame: "#d9480f",
  canopy: "#b42828",
};
const FONT = '14px "Hiragino Sans", "Noto Sans JP", "Yu Gothic UI", Meiryo, system-ui, sans-serif';
const MARGIN = { left: 66, right: 18, top: 28, bottom: 50 };
const ALTITUDE_HEADROOM = 1.12;
const WIDTH_FILL = 0.86;
const KM_THRESHOLD_M = 10_000;
const ROCKET_LENGTH_PX = 30;
const ROCKET_RADIUS_PX = 5;
const LANDED_LABEL_GAP_PX = 16;

interface Plot {
  width: number;
  height: number;
  top: number;
  bottom: number;
  left: number;
  right: number;
  altitudeMaxM: number;
  horizontalMinM: number;
  horizontalMaxM: number;
  sameScale: boolean;
  x: (horizontalM: number) => number;
  y: (altitudeM: number) => number;
}

export function plotFor(timeline: FlightTimeline, width: number, height: number): Plot {
  const left = MARGIN.left;
  const right = width - MARGIN.right;
  const top = MARGIN.top;
  const bottom = height - MARGIN.bottom;
  const apogee = timeline.points[timeline.apogeeIndex].altitude_m;
  const altitudeMaxM = Math.max(apogee * ALTITUDE_HEADROOM, 1);
  const metresToPixels = (bottom - top) / altitudeMaxM;
  const low = Math.min(0, ...timeline.horizontal);
  const high = Math.max(0, ...timeline.horizontal);
  const fits = (high - low) * metresToPixels <= (right - left) * WIDTH_FILL;
  const horizontalScale = fits ? metresToPixels : ((right - left) * WIDTH_FILL) / (high - low);
  const centre = (low + high) / 2;
  const halfSpan = (right - left) / 2 / horizontalScale;
  return {
    width,
    height,
    top,
    bottom,
    left,
    right,
    altitudeMaxM,
    horizontalMinM: centre - halfSpan,
    horizontalMaxM: centre + halfSpan,
    sameScale: fits,
    x: (h) => (left + right) / 2 + (h - centre) * horizontalScale,
    y: (a) => bottom - a * metresToPixels,
  };
}

function axisLabel(valueM: number, km: boolean): string {
  const value = km ? valueM / 1000 : valueM;
  return String(Number(value.toPrecision(6)));
}

function drawAxes(ctx: CanvasRenderingContext2D, plot: Plot): void {
  const km = plot.altitudeMaxM >= KM_THRESHOLD_M;
  const unit = km ? "km" : "m";
  ctx.font = FONT;
  ctx.lineWidth = 1;
  ctx.fillStyle = COLOR.axis;
  ctx.textBaseline = "middle";

  ctx.textAlign = "right";
  const altitudeStep = niceStep(plot.altitudeMaxM, 5);
  for (let a = 0; a <= plot.altitudeMaxM; a += altitudeStep) {
    const y = plot.y(a);
    ctx.strokeStyle = COLOR.grid;
    ctx.beginPath();
    ctx.moveTo(plot.left, y);
    ctx.lineTo(plot.right, y);
    ctx.stroke();
    ctx.fillText(axisLabel(a, km), plot.left - 8, y);
  }
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.fillText(`高度 [${unit}]`, 8, 16);

  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  const span = plot.horizontalMaxM - plot.horizontalMinM;
  const horizontalStep = niceStep(span, Math.max(3, Math.floor((plot.right - plot.left) / 110)));
  const first = Math.ceil(plot.horizontalMinM / horizontalStep) * horizontalStep;
  for (let h = first; h <= plot.horizontalMaxM; h += horizontalStep) {
    ctx.fillText(axisLabel(h, km), plot.x(h), plot.bottom + 6);
  }
  ctx.textAlign = "right";
  ctx.textBaseline = "alphabetic";
  const scale = plot.sameScale ? "縦と同じ縮尺" : "縦と別の縮尺";
  ctx.fillText(`水平距離 [${unit}]（${scale}）`, plot.right, plot.height - 6);

  ctx.strokeStyle = COLOR.ground;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(plot.left, plot.y(0));
  ctx.lineTo(plot.right, plot.y(0));
  ctx.stroke();
}

function drawTrack(
  ctx: CanvasRenderingContext2D,
  plot: Plot,
  timeline: FlightTimeline,
  timeS: number,
  position: { x: number; y: number },
): void {
  const { points, horizontal } = timeline;
  ctx.lineWidth = 1.5;
  ctx.strokeStyle = COLOR.future;
  ctx.setLineDash([4, 5]);
  ctx.beginPath();
  points.forEach((p, i) => {
    if (i === 0) ctx.moveTo(plot.x(horizontal[i]), plot.y(p.altitude_m));
    else ctx.lineTo(plot.x(horizontal[i]), plot.y(p.altitude_m));
  });
  ctx.stroke();
  ctx.setLineDash([]);

  ctx.lineWidth = 3;
  const index = sampleIndexAt(timeline, timeS);
  for (let i = 1; i <= index + 1 && i < points.length; i += 1) {
    const end = i <= index ? { x: plot.x(horizontal[i]), y: plot.y(points[i].altitude_m) } : position;
    ctx.strokeStyle = PHASE_COLOR[phaseAt(timeline, points[i - 1].t_s)];
    ctx.beginPath();
    ctx.moveTo(plot.x(horizontal[i - 1]), plot.y(points[i - 1].altitude_m));
    ctx.lineTo(end.x, end.y);
    ctx.stroke();
  }
}

function drawDot(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  ctx.fillStyle = COLOR.body;
  ctx.beginPath();
  ctx.arc(x, y, 4, 0, Math.PI * 2);
  ctx.fill();
}

function drawLabel(ctx: CanvasRenderingContext2D, x: number, y: number, text: string, width: number): void {
  ctx.fillStyle = "rgba(255, 255, 255, 0.9)";
  ctx.fillRect(x - 3, y - 11, width + 6, 21);
  ctx.fillStyle = COLOR.body;
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillText(text, x, y);
}

/** A dot with its label beside it, on the left when the right side has no room. */
function drawMarker(ctx: CanvasRenderingContext2D, plot: Plot, x: number, y: number, text: string): void {
  drawDot(ctx, x, y);
  ctx.font = FONT;
  const width = ctx.measureText(text).width;
  const fitsRight = x + 10 + width + 4 <= plot.right;
  drawLabel(ctx, fitsRight ? x + 10 : x - 10 - width, y, text, width);
}

/** A dot with its label above the parked glyph, clear of the ground line and the launch marker. */
function drawLandingMarker(ctx: CanvasRenderingContext2D, plot: Plot, x: number, y: number, text: string): void {
  drawDot(ctx, x, y);
  ctx.font = FONT;
  const width = ctx.measureText(text).width;
  const left = Math.min(Math.max(x - width / 2, plot.left + 4), plot.right - width - 4);
  drawLabel(ctx, left, y - ROCKET_LENGTH_PX - LANDED_LABEL_GAP_PX, text, width);
}

function drawMarkers(ctx: CanvasRenderingContext2D, plot: Plot, timeline: FlightTimeline, timeS: number): void {
  const { points, horizontal, thrustEndS, apogeeIndex, reachesGround } = timeline;
  if (thrustEndS !== null && timeS >= thrustEndS) {
    const i = sampleIndexAt(timeline, thrustEndS);
    drawMarker(ctx, plot, plot.x(horizontal[i]), plot.y(points[i].altitude_m), `推力終了 ${thrustEndS.toFixed(2)} s`);
  }
  const apogee = points[apogeeIndex];
  if (timeS >= apogee.t_s) {
    const height = plot.altitudeMaxM >= KM_THRESHOLD_M
      ? `${(apogee.altitude_m / 1000).toFixed(1)} km`
      : `${apogee.altitude_m.toFixed(1)} m`;
    const text = `頂点 ${height} · ${apogee.t_s.toFixed(2)} s`;
    drawMarker(ctx, plot, plot.x(horizontal[apogeeIndex]), plot.y(apogee.altitude_m), text);
  }
  if (timeS >= timeline.endS) {
    const i = points.length - 1;
    const label = reachesGround ? "着地" : "記録の終わり";
    const text = `${label} ${timeline.endS.toFixed(2)} s`;
    drawLandingMarker(ctx, plot, plot.x(horizontal[i]), plot.y(points[i].altitude_m), text);
  }
}

function drawRocket(
  ctx: CanvasRenderingContext2D,
  position: { x: number; y: number },
  headingRad: number,
  flame: boolean,
  canopy: boolean,
): void {
  const length = ROCKET_LENGTH_PX;
  const radius = ROCKET_RADIUS_PX;
  ctx.save();
  ctx.translate(position.x, position.y);
  ctx.rotate(headingRad);
  if (canopy) {
    ctx.strokeStyle = COLOR.body;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (const side of [-1, 1]) {
      ctx.moveTo(0, -length);
      ctx.lineTo(side * 21, -length - 20);
    }
    ctx.stroke();
    ctx.fillStyle = COLOR.canopy;
    ctx.beginPath();
    ctx.arc(0, -length - 20, 21, Math.PI, 0);
    ctx.closePath();
    ctx.fill();
  }
  if (flame) {
    ctx.fillStyle = COLOR.flame;
    ctx.beginPath();
    ctx.moveTo(-radius + 1, 0);
    ctx.lineTo(0, 22);
    ctx.lineTo(radius - 1, 0);
    ctx.closePath();
    ctx.fill();
  }
  ctx.fillStyle = COLOR.fin;
  ctx.beginPath();
  ctx.moveTo(-radius, -9);
  ctx.lineTo(-radius - 6, 0);
  ctx.lineTo(radius + 6, 0);
  ctx.lineTo(radius, -9);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = COLOR.body;
  ctx.beginPath();
  ctx.moveTo(-radius, 0);
  ctx.lineTo(-radius, -length + 9);
  ctx.lineTo(0, -length);
  ctx.lineTo(radius, -length + 9);
  ctx.lineTo(radius, 0);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

function heading(plot: Plot, timeline: FlightTimeline, index: number): number {
  const { points, horizontal } = timeline;
  const next = Math.min(index + 1, points.length - 1);
  const previous = next === index ? Math.max(index - 1, 0) : index;
  const dx = plot.x(horizontal[next]) - plot.x(horizontal[previous]);
  const dy = plot.y(points[next].altitude_m) - plot.y(points[previous].altitude_m);
  return dx === 0 && dy === 0 ? 0 : Math.atan2(dx, -dy);
}

export function drawFlight(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  timeline: FlightTimeline,
  timeS: number,
  parachute: boolean,
): void {
  const plot = plotFor(timeline, width, height);
  ctx.fillStyle = COLOR.background;
  ctx.fillRect(0, 0, width, height);
  drawAxes(ctx, plot);

  const { points, horizontal } = timeline;
  const index = sampleIndexAt(timeline, timeS);
  const next = Math.min(index + 1, points.length - 1);
  const gap = points[next].t_s - points[index].t_s;
  const fraction = gap > 0 ? Math.min((timeS - points[index].t_s) / gap, 1) : 0;
  // Only the glyph moves between samples, for smooth motion; every number shown is a sample.
  const position = {
    x: plot.x(horizontal[index] + (horizontal[next] - horizontal[index]) * fraction),
    y: plot.y(points[index].altitude_m + (points[next].altitude_m - points[index].altitude_m) * fraction),
  };
  drawTrack(ctx, plot, timeline, timeS, position);
  drawMarkers(ctx, plot, timeline, timeS);

  const descending = phaseAt(timeline, timeS) === "descent";
  const landed = timeS >= timeline.endS && timeline.reachesGround;
  const upright = (descending && parachute) || landed || timeS <= timeline.startS;
  const flame = (thrustOf(points[index]) ?? 0) > 0;
  drawRocket(ctx, position, upright ? 0 : heading(plot, timeline, index), flame, descending && parachute && !landed);
}
