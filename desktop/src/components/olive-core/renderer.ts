import { geometry, MotionState, rotate, activeState, corePaletteMode } from "./geometry";
export interface CoreMetrics {
  frames: number;
  drawMs: number;
  maxDrawMs: number;
  angle: number;
  running: boolean;
  points: number;
  reduced: boolean;
  visible: boolean;
}
export class OliveRenderer {
  private ctx: CanvasRenderingContext2D;
  private mesh;
  private motion;
  private frame = 0;
  private last = 0;
  private painted = 0;
  private size = 48;
  private visible = true;
  private disposed = false;
  private failed = false;
  private reduced = false;
  private light = false;
  private state = "Ready";
  private appearance = new MutationObserver(() => this.refresh());
  private intersection: IntersectionObserver;
  private resize: ResizeObserver;
  private density = matchMedia(`(resolution: ${devicePixelRatio}dppx)`);
  private lastRatio = devicePixelRatio;
  private system = matchMedia("(prefers-reduced-motion: reduce)");
  // The olive's own colours, from the desktop icon: a green body and a red
  // pimento. Each ramp runs from the shaded side to the lit side.
  private darkPalette = Array.from(
    { length: 32 },
    (_, i) => `hsl(${82 - i * 0.4} ${56 - i * 0.25}% ${23 + i * 1.05}%)`,
  );
  private lightPalette = Array.from(
    { length: 32 },
    (_, i) => `hsl(${82 - i * 0.3} 60% ${16 + i * 0.6}%)`,
  );
  private pimentoDark = Array.from(
    { length: 32 },
    (_, i) => `hsl(${357 + i * 0.35} 70% ${36 + i * 1.05}%)`,
  );
  private pimentoLight = Array.from(
    { length: 32 },
    (_, i) => `hsl(${356 + i * 0.3} 72% ${32 + i * 0.6}%)`,
  );
  // V2 compact Core: cyan compute lighting only while real work runs, amber
  // while OLIVE waits for an approval. The Welcome Core keeps the olive.
  private computeDark = Array.from(
    { length: 32 },
    (_, i) => `hsl(${188 - i * 0.2} ${58 - i * 0.2}% ${24 + i * 1.3}%)`,
  );
  private computeLight = Array.from(
    { length: 32 },
    (_, i) => `hsl(${190 - i * 0.2} 70% ${18 + i * 0.6}%)`,
  );
  private attentionDark = Array.from(
    { length: 32 },
    (_, i) => `hsl(${38 + i * 0.2} ${70 - i * 0.2}% ${26 + i * 1.3}%)`,
  );
  private attentionLight = Array.from(
    { length: 32 },
    (_, i) => `hsl(${36 + i * 0.2} 80% ${18 + i * 0.6}%)`,
  );
  readonly metrics: CoreMetrics = {
    frames: 0,
    drawMs: 0,
    maxDrawMs: 0,
    angle: 0,
    running: false,
    points: 0,
    reduced: false,
    visible: true,
  };
  constructor(
    private canvas: HTMLCanvasElement,
    private welcome: boolean,
  ) {
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) throw new Error("Canvas unavailable");
    this.size = Math.max(
      1,
      Math.min(300, canvas.clientWidth || (welcome ? 270 : 48)),
    );
    this.ctx = ctx;
    this.mesh = geometry(!welcome);
    this.motion = new MotionState(welcome);
    this.metrics.points =
      this.mesh.body.length + this.mesh.pimento.length + this.mesh.rim.length;
    Object.defineProperty(canvas, "oliveCoreMetrics", {
      value: this.metrics,
      configurable: true,
    });
    this.resize = new ResizeObserver((entries) => {
      this.size = Math.max(1, Math.min(300, entries[0].contentRect.width));
      this.refresh();
    });
    this.intersection = new IntersectionObserver((entries) => {
      this.visible = entries[0].isIntersecting;
      this.refresh();
    });
    this.resize.observe(canvas);
    this.intersection.observe(canvas);
    this.appearance.observe(document.documentElement, {
      attributes: true,
      attributeFilter: [
        "data-reduced",
        "data-theme",
        "data-window-visible",
        "data-core-motion",
      ],
    });
    document.addEventListener("visibilitychange", this.refresh);
    this.system.addEventListener("change", this.refresh);
    this.density.addEventListener("change", this.refresh);
    window.addEventListener("resize", this.refresh);
    this.refresh();
  }
  setState(state: string) {
    this.state = state;
    this.motion.setState(state);
    this.refresh();
  }
  private stop() {
    cancelAnimationFrame(this.frame);
    this.frame = 0;
    this.last = 0;
    this.painted = 0;
    this.metrics.running = false;
  }
  private refresh = () => {
    if (this.disposed || this.failed) return;
    this.stop();
    const preference = document.documentElement.dataset.coreMotion;
    this.reduced =
      !this.welcome &&
      (document.documentElement.dataset.reduced === "true" ||
        preference === "pause" ||
        (this.system.matches && preference !== "play"));
    this.light = document.documentElement.dataset.theme === "light";
    this.metrics.reduced = this.reduced;
    this.metrics.visible =
      this.visible &&
      !document.hidden &&
      document.documentElement.dataset.windowVisible !== "false";
    if (!this.metrics.visible) return;
    if (this.lastRatio !== devicePixelRatio) {
      this.density.removeEventListener("change", this.refresh);
      this.lastRatio = devicePixelRatio;
      this.density = matchMedia(`(resolution: ${devicePixelRatio}dppx)`);
      this.density.addEventListener("change", this.refresh);
    }
    const ratio = Math.min(2, Math.max(1, devicePixelRatio));
    const pixels = Math.round(this.size * ratio);
    if (this.canvas.width !== pixels || this.canvas.height !== pixels) {
      this.canvas.width = this.canvas.height = pixels;
      this.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    }
    this.motion.step(0, this.reduced);
    this.draw();
    if (
      !this.reduced &&
      (this.welcome ||
        activeState(this.state) ||
        Math.abs(this.motion.target - this.motion.angle) > 0.002)
    )
      this.schedule();
  };
  private schedule() {
    if (!this.frame && !this.failed && !this.disposed) {
      this.metrics.running = true;
      this.frame = requestAnimationFrame(this.tick);
    }
  }
  private tick = (now: number) => {
    this.frame = 0;
    if (
      this.disposed ||
      this.failed ||
      document.hidden ||
      document.documentElement.dataset.windowVisible === "false" ||
      !this.visible
    ) {
      this.stop();
      return;
    }
    const dt = this.last ? Math.min(0.05, (now - this.last) / 1000) : 0;
    this.last = now;
    const moving = this.motion.step(dt, this.reduced);
    // Render at most 30 frames/sec; the time-based motion remains refresh independent.
    if (!this.painted || now - this.painted >= 1000 / 30 || !moving) {
      this.draw();
      this.painted = now;
    }
    if (moving) this.schedule();
    else this.stop();
  };
  private draw() {
    const start = performance.now();
    try {
      const c = this.ctx,
        s = this.size,
        angle = this.motion.angle;
      c.clearRect(0, 0, s, s);
      const x = rotate({ x: 1, y: 0, z: 0 }, angle),
        y = rotate({ x: 0, y: 1, z: 0 }, angle),
        z = rotate({ x: 0, y: 0, z: 1 }, angle);
      const mode = this.welcome ? "rest" : corePaletteMode(this.state);
      const palette =
        mode === "compute"
          ? this.light ? this.computeLight : this.computeDark
          : mode === "attention"
            ? this.light ? this.attentionLight : this.attentionDark
            : this.light ? this.lightPalette : this.darkPalette;
      const brightness = activeState(this.state) ? 1 : 0.83;
      const pointSize = this.welcome ? s / 225 : Math.max(0.62, s / 62);
      const project = (px: number, py: number, pz: number) => {
        const zz = px * x.z + py * y.z + pz * z.z,
          scale = (s * 0.355 * 4.8) / (4.8 - zz);
        c.lineTo(
          s / 2 + (px * x.x + py * y.x + pz * z.x) * scale,
          s / 2 - (px * x.y + py * y.y + pz * z.y) * scale,
        );
      };
      const pimentoPalette = this.light ? this.pimentoLight : this.pimentoDark;
      const dots = (
        points: typeof this.mesh.body,
        inside = false,
        warm = false,
      ) => {
        for (const p of points) {
          const nz = p.normal.x * x.z + p.normal.y * y.z + p.normal.z * z.z;
          if (!inside && nz <= 0) continue;
          const zz = p.x * x.z + p.y * y.z + p.z * z.z,
            scale = (s * 0.355 * 4.8) / (4.8 - zz);
          const px = s / 2 + (p.x * x.x + p.y * y.x + p.z * z.x) * scale,
            py = s / 2 - (p.x * x.y + p.y * y.y + p.z * z.y) * scale;
          const nx = p.normal.x * x.x + p.normal.y * y.x + p.normal.z * z.x;
          const ny = p.normal.x * x.y + p.normal.y * y.y + p.normal.z * z.y;
          // The cut plane faces one way, so its dots share a light value; the
          // rim stays bright to draw the pimento's edge against the body.
          const lit = inside
            ? p.rim
              ? 0.9
              : 0.42 + 0.5 * Math.max(0, nz)
            : 0.28 + 0.72 * Math.max(0, -nx * 0.4 + ny * 0.35 + nz * 0.8);
          c.globalAlpha = inside ? 1 : Math.min(1, nz * 8) * brightness;
          c.fillStyle = (warm ? pimentoPalette : palette)[
            Math.min(31, Math.max(0, Math.round(lit * 31)))
          ];
          c.beginPath();
          c.arc(
            px,
            py,
            pointSize *
              (p.rim ? 1.12 : inside ? 0.8 : 0.75 + (0.25 * (zz + 1)) / 2),
            0,
            Math.PI * 2,
          );
          c.fill();
        }
      };
      dots(this.mesh.body);
      // The pimento only shows while its face is turned towards the camera.
      // Clipping to the projected rim keeps it inside the cut at every angle.
      if (this.mesh.rim.length && y.z > 0.02) {
        c.save();
        c.beginPath();
        for (const p of this.mesh.rim) project(p.x, p.y, p.z);
        c.closePath();
        c.clip();
        c.globalAlpha = 1;
        dots(this.mesh.pimento, true, true);
        c.restore();
        dots(this.mesh.rim, true);
      }
      c.globalAlpha = 1;
      this.canvas.dataset.rendered = "true";
      this.metrics.frames++;
      this.metrics.angle = angle;
      const elapsed = performance.now() - start;
      this.metrics.drawMs +=
        (elapsed - this.metrics.drawMs) / Math.min(this.metrics.frames, 90);
      this.metrics.maxDrawMs = Math.max(this.metrics.maxDrawMs, elapsed);
    } catch {
      this.failed = true;
      this.stop();
      delete this.canvas.dataset.rendered;
    }
  }
  dispose() {
    this.disposed = true;
    this.stop();
    this.resize.disconnect();
    this.intersection.disconnect();
    this.appearance.disconnect();
    document.removeEventListener("visibilitychange", this.refresh);
    this.system.removeEventListener("change", this.refresh);
    window.removeEventListener("resize", this.refresh);
    this.density.removeEventListener("change", this.refresh);
    delete this.canvas.dataset.rendered;
  }
}
