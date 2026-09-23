export type Vec = { x: number; y: number; z: number };
export type Dot = Vec & { normal: Vec; rim?: boolean };
export const REST = 0.24;
export const TURN = Math.PI * 2;
export const activeState = (state: string) =>
  ["Thinking", "Working", "Researching"].includes(state);

// A stuffed olive: a closed body truncated by one flat cut, and a pimento that
// fills that cut. Both are real object-space geometry, transformed with the
// olive, never a pasted image. Bands are spaced by equal arc so the stipple
// stays even over the closed end instead of ringing around the pole.
export function geometry(compact: boolean) {
  const body: Dot[] = [],
    pimento: Dot[] = [],
    rim: Dot[] = [];
  const cut = 0.84,
    radius = Math.sqrt(1 - cut * cut);
  const bands = compact ? 15 : 38;
  // Walk the sphere by equal arc from the closed pole (y = -1) to the cut plane
  // (y = cut). Equal *height* instead would bunch the dots at the equator and
  // leave visible rings around the closed end.
  const limit = Math.PI - Math.acos(cut);
  for (let row = 0; row < bands; row++) {
    const t = (limit * row) / (bands - 1);
    const y = -Math.cos(t);
    const r = Math.sin(t),
      count = Math.max(1, Math.round(r * (compact ? 28 : 82)));
    for (let col = 0; col < count; col++) {
      const a = (TURN * (col + (row % 2) * 0.5)) / count;
      const x = 0.79 * r * Math.cos(a) * (1 + 0.06 * y),
        z = 0.73 * r * Math.sin(a);
      const normal = {
        x: x / (0.79 * 0.79),
        y: y / 1.14,
        z: z / (0.73 * 0.73),
      };
      const length = Math.hypot(normal.x, normal.y, normal.z);
      body.push({
        x,
        y: y * 1.14,
        z,
        normal: {
          x: normal.x / length,
          y: normal.y / length,
          z: normal.z / length,
        },
      });
    }
  }
  // The pimento is a flat disc filling the cut, not a recess: rings of dots on
  // the cut plane itself, spaced like the body so the two read as one object.
  const rings = compact ? 3 : 8;
  for (let ring = 0; ring < rings; ring++) {
    const r = ring / (rings - 1),
      count = Math.max(1, Math.round(r * (compact ? 17 : 50)));
    for (let col = 0; col < count; col++) {
      const a = (TURN * (col + 0.4 * (ring % 2))) / count;
      pimento.push({
        x: 0.79 * radius * r * Math.cos(a) * (1 + 0.06 * cut),
        y: cut * 1.14,
        z: 0.73 * radius * r * Math.sin(a),
        normal: { x: 0, y: 1, z: 0 },
      });
    }
  }
  const count = compact ? 20 : 48;
  for (let i = 0; i < count; i++) {
    const a = (TURN * i) / count;
    rim.push({
      x: 0.79 * radius * Math.cos(a) * (1 + 0.06 * cut),
      y: cut * 1.14,
      z: 0.73 * radius * Math.sin(a),
      normal: { x: 0, y: 1, z: 0 },
      rim: true,
    });
  }
  return { body, pimento, rim };
}
export function rotate(p: Vec, angle: number): Vec {
  // Spin around the olive's own pole-to-pole axis, then apply a fixed tilt.
  // Reversing this order makes the tilted axis precess instead of staying put.
  const tx = 0.57,
    tz = -0.28,
    camera = 0.12;
  const sx = p.x * Math.cos(angle) + p.z * Math.sin(angle),
    sz = -p.x * Math.sin(angle) + p.z * Math.cos(angle);
  const y = p.y * Math.cos(tx) - sz * Math.sin(tx),
    z = p.y * Math.sin(tx) + sz * Math.cos(tx);
  const x = sx * Math.cos(tz) - y * Math.sin(tz),
    yy = sx * Math.sin(tz) + y * Math.cos(tz);
  return {
    x,
    y: yy * Math.cos(camera) - z * Math.sin(camera),
    z: yy * Math.sin(camera) + z * Math.cos(camera),
  };
}
export function project(p: Vec, size: number) {
  const perspective = 4.8 / (4.8 - p.z),
    scale = size * 0.355;
  return {
    x: size / 2 + p.x * scale * perspective,
    y: size / 2 - p.y * scale * perspective,
    z: p.z,
  };
}
export class MotionState {
  angle = REST;
  speed = 0;
  target = REST;
  state = "Ready";
  constructor(public welcome: boolean) {}
  setState(state: string) {
    if (state === this.state) return;
    this.state = state;
    this.target = REST + Math.round((this.angle - REST) / TURN) * TURN;
  }
  step(delta: number, reduced = false) {
    if (reduced) {
      this.angle = REST;
      this.speed = 0;
      return false;
    }
    const dt = Math.min(0.05, Math.max(0, delta));
    if (this.welcome || activeState(this.state)) {
      const speed = this.welcome ? TURN / 12 : 0.95;
      this.speed += (speed - this.speed) * (1 - Math.exp(-dt * 3.5));
      this.angle += this.speed * dt;
      return true;
    }
    if (this.state !== "Ready") {
      this.speed = 0;
      return false;
    }
    this.speed += ((this.target - this.angle) * 9 - this.speed * 6) * dt;
    this.angle += this.speed * dt;
    if (
      Math.abs(this.target - this.angle) < 0.002 &&
      Math.abs(this.speed) < 0.003
    ) {
      this.angle = this.target;
      this.speed = 0;
      return false;
    }
    return true;
  }
}

/** Which V2 palette the compact Core uses for a runtime state: the olive at
 *  rest, cyan only while real work runs, amber while waiting on the person. */
export function corePaletteMode(state: string): "rest" | "compute" | "attention" {
  if (["Approval required", "Paused", "Pausing"].includes(state)) return "attention";
  return activeState(state) ? "compute" : "rest";
}
