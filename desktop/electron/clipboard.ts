import { z } from "zod";

// Local user-interface operation only. No read/watch API or agent capability.
export const clipboardText = z.string().max(2_000_000, "Text exceeds the clipboard copy limit");

export async function writeClipboardText(input: unknown, write: (text: string) => Promise<void>) {
  const text = clipboardText.parse(input);
  await write(text);
}
