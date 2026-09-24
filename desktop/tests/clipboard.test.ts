import { expect, it, vi } from "vitest";
import { writeClipboardText } from "../electron/clipboard";

it("copies exact code and waits for native completion", async () => {
  let finish!: () => void;
  const write = vi.fn(() => new Promise<void>(resolve => { finish = resolve; }));
  const text = '\tconst greeting = "Olá <世界> & café";\n\n';
  let completed = false;
  const operation = writeClipboardText(text, write).then(() => { completed = true; });
  expect(write).toHaveBeenCalledWith(text);
  await Promise.resolve();
  expect(completed).toBe(false);
  finish();
  await operation;
  expect(completed).toBe(true);
});

it("rejects malformed or oversized payloads without writing or truncation", async () => {
  const write = vi.fn(async () => {});
  for (const value of [null, {}, ["text"], 4, "x".repeat(2_000_001)]) {
    await expect(writeClipboardText(value, write)).rejects.toThrow();
  }
  expect(write).not.toHaveBeenCalled();
  await expect(writeClipboardText("", write)).resolves.toBeUndefined();
});

it("propagates the native write failure", async () => {
  await expect(writeClipboardText("code", async () => {throw new Error("Clipboard unavailable");})).rejects.toThrow("Clipboard unavailable");
});
