import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Markdown } from "../src/components/Markdown";
import { Core } from "../src/components/Core";
describe("untrusted presentation", () => {
  it("renders Markdown without active HTML or remote image requests", () => {
    const html = renderToStaticMarkup(
      createElement(Markdown, {
        text: '<script>window.olive.call("agent.tool", {})</script>\n\n![tracking](https://example.invalid/pixel)\n\n[unsafe](javascript:alert(1))',
      }),
    );
    expect(html).not.toContain("<script>");
    expect(html).not.toContain("<img");
    expect(html).not.toContain('href="javascript:');
    expect(html).toContain("Image blocked");
  });
  it("labels Core state and does not animate invented work", () => {
    const ready = renderToStaticMarkup(createElement(Core, { state: "Ready" }));
    expect(ready).toContain("OLIVE: Ready");
    expect(ready).not.toContain("core-active");
    const working = renderToStaticMarkup(
      createElement(Core, { state: "Working" }),
    );
    expect(working).toContain("core-active");
    expect(working).toContain("OLIVE: Working");
  });
});
