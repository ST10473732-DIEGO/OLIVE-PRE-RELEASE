import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { features, launcherFeatures, navigationRows, searchFeatures, chatCompatibleRoute } from "../src/navigation/features";
import { sourceGroup, SourceChips, SourceEvidence } from "../src/features/chat/SourceChips";

describe("Chat research navigation and provenance", () => {
  it("removes standalone Research from all normal launch surfaces", () => {
    for (const list of [features, launcherFeatures, navigationRows(false), navigationRows(true)]) {
      expect(list.some(f => f.id === "research")).toBe(false);
    }
    expect(searchFeatures("research").some(f => f.id === "chat")).toBe(true);
  });
  it("renders inspectable source groups and never interprets source text as HTML", () => {
    const html = renderToStaticMarkup(createElement(SourceChips, {sources: [
      {kind: "document_excerpt", label: "D1 · Report.pdf — page 12"},
      {kind: "page_excerpt", label: "S1 · Publisher", url: "https://example.org", retrieved_at: "2026-09-29T07:00Z"},
    ], inspect: () => undefined}));
    expect(html).toContain('aria-label="Document evidence"');
    expect(html).toContain('aria-label="Public web evidence"');
    expect(html).toContain('Retrieved 2026-09-29T07:00Z');
    const untrusted = renderToStaticMarkup(createElement(SourceEvidence, {source: {url: "javascript:alert(1)", evidence: "<script>unsafe()</script>"}}));
    expect(untrusted).not.toContain("<script>");
    expect(untrusted).toContain("&lt;script&gt;");
    expect(untrusted).not.toContain("Open original source");
  });
  it("redirects legacy routes safely to Chat", () => {
    expect(chatCompatibleRoute("research")).toBe("chat");
    expect(chatCompatibleRoute("studio")).toBe("studio");
  });
  it("keeps document and web provenance distinct", () => {
    expect(sourceGroup({kind: "document_excerpt", label: "D1 · Report.pdf — page 12"})).toBe("Document evidence");
    expect(sourceGroup({url: "https://example.org", retrieved_at: "2026-09-29T07:00Z"})).toBe("Public web evidence");
    expect(sourceGroup({label: "Legacy source"})).toBe("Sources");
  });
  it("shows current snapshots without inventing publication times", () => {
    const source = {kind: "current_snapshot", title: "Leadership", url: "https://example.org/leadership", published_at: null, retrieved_at: "2026-09-29T07:00Z"};
    for (const html of [renderToStaticMarkup(createElement(SourceEvidence, {source})),
      renderToStaticMarkup(createElement(SourceChips, {sources: [source], inspect: () => undefined}))]) {
      expect(html).toContain("Current page snapshot");
      expect(html).toContain("Publication date unavailable");
      expect(html).toContain("Retrieved 2026-09-29T07:00Z");
      expect(html).not.toContain("Published 2026-09-29T07:00Z");
    }
  });
});
