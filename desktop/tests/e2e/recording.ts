import type { Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { spawnSync } from "node:child_process";
export async function record(
  page: Page,
  directory: string,
  filename = "m1-interaction.mp4",
) {
  const folder = path.join(directory, "frames");
  await mkdir(folder, { recursive: true });
  const session = await page.context().newCDPSession(page);
  const frames: { file: string; time: number }[] = [];
  const writes: Promise<void>[] = [];
  const acknowledgements: Promise<unknown>[] = [];
  const captureErrors: unknown[] = [];
  const onFrame = (event: { data: string; sessionId: number; metadata: { timestamp?: number } }) => {
    const file = `frame-${String(frames.length).padStart(5, "0")}.jpg`;
    frames.push({ file, time: event.metadata.timestamp || Date.now() / 1000 });
    writes.push(
      writeFile(path.join(folder, file), Buffer.from(event.data, "base64")),
    );
    acknowledgements.push(session.send("Page.screencastFrameAck", {
      sessionId: event.sessionId,
    }).catch(error => { captureErrors.push(error); }));
  };
  session.on("Page.screencastFrame", onFrame);
  await session.send("Page.startScreencast", {
    format: "jpeg",
    quality: 80,
    maxWidth: 1440,
    maxHeight: 900,
    everyNthFrame: 2,
  });
  return async () => {
    await session.send("Page.stopScreencast");
    session.off("Page.screencastFrame", onFrame);
    await Promise.all(writes);
    await Promise.all(acknowledgements);
    await session.detach();
    if (captureErrors.length) throw new AggregateError(captureErrors, "Recording acknowledgement failed");
    if (!frames.length)
      return { recorded: false, reason: "No screencast frames available" };
    const manifest =
      frames
        .map(
          (frame, i) =>
            `file '${frame.file}'\nduration ${Math.max(0.02, Math.min(2, (frames[i + 1]?.time || frame.time + 0.5) - frame.time))}`,
        )
        .join("\n") + `\nfile '${frames.at(-1)!.file}'\n`;
    await writeFile(path.join(folder, "frames.txt"), manifest);
    const result = spawnSync(
      "ffmpeg",
      [
        "-y",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        path.join(folder, "frames.txt"),
        "-vf",
        "pad=ceil(iw/2)*2:ceil(ih/2)*2",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        path.join(directory, filename),
      ],
      { encoding: "utf8", windowsHide: true },
    );
    return {
      recorded: result.status === 0,
      frames: frames.length,
      reason:
        result.status === 0
          ? "Actual Electron CDP frames"
          : "FFmpeg unavailable or failed; original frames retained",
    };
  };
}
