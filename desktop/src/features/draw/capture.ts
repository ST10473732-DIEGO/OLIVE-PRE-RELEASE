// Pointer input → canonical stroke points. Pure logic (no DOM), so every edge
// case is unit-tested: one drawing pointer at a time, cancellation, lost
// capture, pressure only when the hardware reports it, bounded point counts.
import { LIMITS, quantize, quantizePressure } from "./model";

export type CaptureTool = "pen" | "erase";
export interface Sample { x: number; y: number; pressure: number }
export interface CaptureStart extends Sample {
  pointerId: number;
  pointerType: string;
  tool: CaptureTool;
  /** Skip samples closer than this (document px) to the last kept point. */
  minDistance: number;
}
export interface Captured {
  tool: CaptureTool;
  /** Flat x, y (and pressure when `pressure`) values, already quantized. */
  points: number[];
  pressure: boolean;
  pointerType: string;
}

/** Real pressure is only trusted from a pen, and only once it varies: the
 *  Pointer Events spec reports a constant 0.5 for hardware without pressure,
 *  and that must draw at the selected width, not at a faked one. */
const penPressure = (pointerType: string, value: number) => pointerType === "pen" && value > 0 && value <= 1;

export class StrokeCapture {
  private current: {
    pointerId: number;
    pointerType: string;
    tool: CaptureTool;
    minDistance: number;
    xs: number[];
    ys: number[];
    ps: number[];
    pressureSeen: boolean;
    tail: Sample | null;
  } | null = null;
  /** True once a stroke hit the per-stroke point limit (the UI says so). */
  limited = false;

  get active() { return this.current !== null; }
  get pointerId() { return this.current?.pointerId ?? null; }
  get tool() { return this.current?.tool ?? null; }

  begin(start: CaptureStart): boolean {
    if (this.current) return false;   // A second finger or pen never starts a second stroke.
    this.limited = false;
    this.current = {
      pointerId: start.pointerId, pointerType: start.pointerType, tool: start.tool, minDistance: Math.max(0, start.minDistance),
      xs: [], ys: [], ps: [], pressureSeen: false, tail: null,
    };
    this.keep(start);
    return true;
  }

  private keep(sample: Sample) {
    const c = this.current!;
    if (c.xs.length >= LIMITS.max_points) {
      this.limited = true;
      return;
    }
    const x = quantize(sample.x), y = quantize(sample.y);
    const p = penPressure(c.pointerType, sample.pressure) ? quantizePressure(sample.pressure) : c.ps.length ? c.ps[c.ps.length - 1] : 0.5;
    if (c.ps.length && p !== c.ps[0]) c.pressureSeen = true;
    c.xs.push(x);
    c.ys.push(y);
    c.ps.push(p);
    c.tail = null;
  }

  /** Coalesced samples for the drawing pointer; other pointers are ignored. */
  move(pointerId: number, samples: Sample[]): boolean {
    const c = this.current;
    if (!c || pointerId !== c.pointerId) return false;
    let changed = false;
    for (const sample of samples) {
      if (!Number.isFinite(sample.x) || !Number.isFinite(sample.y)) continue;
      const lx = c.xs[c.xs.length - 1], ly = c.ys[c.ys.length - 1];
      if (Math.hypot(sample.x - lx, sample.y - ly) < c.minDistance) {
        c.tail = sample;   // Kept for the final point if the pointer stops here.
        continue;
      }
      const before = c.xs.length;
      this.keep(sample);
      changed = changed || c.xs.length !== before;
    }
    return changed;
  }

  /** Pointer up, or lost capture: finish the stroke with what was drawn. */
  end(pointerId: number, last?: Sample): Captured | null {
    const c = this.current;
    if (!c || pointerId !== c.pointerId) return null;
    const final = last && Number.isFinite(last.x) && Number.isFinite(last.y) ? last : c.tail;
    if (final && (quantize(final.x) !== c.xs[c.xs.length - 1] || quantize(final.y) !== c.ys[c.ys.length - 1])) this.keep(final);
    const result = this.snapshot();
    this.current = null;
    return result;
  }

  /** pointercancel (the system took the pointer): the partial stroke is discarded. */
  cancel(pointerId?: number): boolean {
    if (!this.current || (pointerId !== undefined && pointerId !== this.current.pointerId)) return false;
    this.current = null;
    return true;
  }

  /** The in-progress stroke as it will be stored (for live rendering). */
  snapshot(): Captured | null {
    const c = this.current;
    if (!c) return null;
    const pressure = c.tool === "pen" && c.pressureSeen;
    const points: number[] = [];
    for (let i = 0; i < c.xs.length; i++) {
      points.push(c.xs[i], c.ys[i]);
      if (pressure) points.push(c.ps[i]);
    }
    return { tool: c.tool, points, pressure, pointerType: c.pointerType };
  }
}
