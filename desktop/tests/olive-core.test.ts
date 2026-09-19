import { describe, it, expect } from "vitest";
import {
  geometry,
  rotate,
  project,
  MotionState,
  REST,
  TURN,
  activeState,
} from "../src/components/olive-core/geometry";
describe("3D dot olive", () => {
  it("precomputes deterministic bounded geometry for a stuffed olive", () => {
    const large = geometry(false),
      compact = geometry(true);
    expect(large).toEqual(geometry(false));
    expect(large.body.length).toBeGreaterThan(compact.body.length * 4);
    expect(
      large.body.length + large.pimento.length + large.rim.length,
    ).toBeLessThan(2600);
    for (const mesh of [large, compact]) {
      // The body is closed at the far end and truncated by one flat cut.
      const bottom = Math.min(...mesh.body.map((p) => p.y));
      expect(bottom).toBeLessThan(-1.1);
      const base = mesh.body.filter((p) => p.y < bottom + 0.02);
      expect(Math.max(...base.map((p) => Math.hypot(p.x, p.z)))).toBeLessThan(0.2);
      // The pimento fills that cut: one flat plane, level with the rim, and it
      // reaches the rim rather than leaving a gap around its edge.
      const plane = mesh.rim[0].y;
      expect(Math.max(...mesh.body.map((p) => p.y))).toBeCloseTo(plane, 6);
      for (const p of mesh.pimento) expect(p.y).toBeCloseTo(plane, 6);
      const edge = Math.max(...mesh.rim.map((p) => Math.hypot(p.x, p.z)));
      const filled = Math.max(...mesh.pimento.map((p) => Math.hypot(p.x, p.z)));
      expect(filled).toBeGreaterThan(edge * 0.9);
      expect(filled).toBeLessThanOrEqual(edge + 1e-9);
      // Nothing is recessed: there is no dot below the cut plane inside it.
      expect(Math.min(...mesh.pimento.map((p) => p.y))).toBeCloseTo(plane, 6);
    }
    for (let a = 0; a < TURN; a += 0.2)
      for (const p of [...large.body, ...large.rim]) {
        const q = project(rotate(p, a), 270);
        expect(q.x).toBeGreaterThan(5);
        expect(q.x).toBeLessThan(265);
        expect(q.y).toBeGreaterThan(5);
        expect(q.y).toBeLessThan(265);
      }
  });
  it("keeps the tilted pole axis fixed while surface points spin around it", () => {
    const front = rotate({ x: 0, y: 1, z: 0 }, REST),
      back = rotate({ x: 0, y: 1, z: 0 }, REST + Math.PI);
    expect(front.z).toBeGreaterThan(0);
    expect(back).toEqual(front);
    for (let angle = 0; angle < TURN; angle += 0.2)
      expect(rotate({ x: 0, y: 1, z: 0 }, angle)).toEqual(front);
    // A pole dot sits on the axis and cannot move; take one off the equator.
    const body = geometry(false).body;
    const p = body.reduce((best, item) =>
      Math.hypot(item.x, item.z) > Math.hypot(best.x, best.z) ? item : best,
    );
    expect(project(rotate(p, REST), 270)).not.toEqual(
      project(rotate(p, REST + 1), 270),
    );
  });
  it("welcomes decoratively at a twelve-second turn, but idle compact schedules no motion", () => {
    const welcome = new MotionState(true),
      idle = new MotionState(false);
    for (let i = 0; i < 900; i++) welcome.step(1 / 60);
    const before = welcome.angle;
    for (let i = 0; i < 720; i++) welcome.step(1 / 60);
    expect(welcome.angle - before).toBeCloseTo(TURN, 3);
    expect(idle.step(0.03)).toBe(false);
    expect(idle.angle).toBe(REST);
  });
  it("eases active work to rest and holds approval, pause and failure states without invented work", () => {
    const m = new MotionState(false);
    m.setState("Thinking");
    for (let i = 0; i < 180; i++) m.step(1 / 60);
    expect(m.speed).toBeGreaterThan(0.9);
    const angle = m.angle;
    m.setState("Ready");
    expect(m.angle).toBe(angle);
    m.step(1 / 60);
    expect(Math.abs(m.angle - angle)).toBeLessThan(0.03);
    for (let i = 0; i < 600; i++) m.step(1 / 60);
    expect(m.step(0.03)).toBe(false);
    expect(Math.abs(Math.sin((m.angle - REST) / 2))).toBeLessThan(0.002);
    for (const state of [
      "Approval required",
      "Paused",
      "Pausing",
      "Error",
      "Degraded",
      "Cancelled",
    ]) {
      m.setState(state);
      const before = m.angle;
      expect(m.step(0.03)).toBe(false);
      expect(m.angle).toBe(before);
      expect(activeState(state)).toBe(false);
    }
    m.setState("Researching");
    expect(m.step(0.03)).toBe(true);
    expect(m.step(0.03, true)).toBe(false);
    expect(m.angle).toBe(REST);
  });
  it("caps resume deltas instead of jumping over an entire hidden interval", () => {
    const m = new MotionState(true);
    m.step(600);
    expect(m.angle - REST).toBeLessThan(0.03);
  });
});
