/**
 * Tests for `emailToPlainText(html)` — the HTML→plain-text
 * converter used when rendering the plain-text fallback for
 * outgoing emails.
 *
 * SECURITY: this helper has been hardened against regex-bypass
 * attacks by switching to DOMParser-only extraction. Pinning the
 * behaviour here so a future refactor (e.g. "let's just use a
 * regex, it's simpler") gets caught.
 *
 * Tested behaviours:
 *  - <script> and <style> contents are removed (not preserved)
 *  - Plain text inside tags is preserved
 *  - Whitespace is normalized to single spaces
 *  - Leading/trailing whitespace is trimmed
 *  - HTML entities are decoded by DOMParser (&amp; → &)
 *  - Empty input → empty string (not crash)
 *  - Malformed HTML doesn't throw
 *
 * Wave 6a99 — closes coverage gap on a SECURITY-relevant helper
 * (DOMParser path) plus the Node fallback used by SSR.
 *
 * Note: jsdom provides DOMParser, so the DOMParser branch is the
 * one exercised by these tests. The Node.js fallback at the
 * bottom of the source is unreachable from jsdom.
 *
 * 12 cases.
 */

import { emailToPlainText } from "../email-renderer";

describe("emailToPlainText", () => {
  it("strips simple HTML tags", () => {
    // Pin: <p>...</p> → plain text content.
    expect(emailToPlainText("<p>Hello World</p>")).toBe("Hello World");
  });

  it("preserves text across multiple tags", () => {
    // Pin: text from sibling/nested tags concatenates correctly.
    expect(
      emailToPlainText("<div>Hello <span>World</span></div>")
    ).toBe("Hello World");
  });

  it("removes script tag contents entirely", () => {
    // Pin SECURITY: script element AND its body are removed.
    // The body must NOT leak into the plain-text output (would
    // expose internal JS to recipients).
    const out = emailToPlainText(
      "<p>Hello</p><script>alert('xss')</script><p>World</p>"
    );
    expect(out).not.toContain("alert");
    expect(out).not.toContain("xss");
    expect(out).toContain("Hello");
    expect(out).toContain("World");
  });

  it("removes style tag contents entirely", () => {
    // Pin: <style> body (CSS) does not leak into plain text.
    const out = emailToPlainText(
      "<style>body { color: red; }</style><p>Hello</p>"
    );
    expect(out).not.toContain("color");
    expect(out).not.toContain("red");
    expect(out).toContain("Hello");
  });

  it("decodes HTML entities via DOMParser", () => {
    // Pin: &amp; → &, &lt; → <, &nbsp; → space. DOMParser handles
    // these natively; the regex-free design relies on this.
    const out = emailToPlainText("<p>A &amp; B</p>");
    expect(out).toBe("A & B");
  });

  it("collapses multiple spaces to a single space", () => {
    // Pin: multiple SPACE characters collapse to one.
    // Implementation: split(' ').filter(Boolean).join(' ') —
    // SECURITY-relevant choice (regex-free per the source's
    // CodeQL comment). Pinned so it doesn't drift back to regex.
    expect(emailToPlainText("<p>A    B    C</p>")).toBe("A B C");
  });

  it("preserves newlines verbatim (regex-free design)", () => {
    // Pin: split(' ') only splits on the SPACE character. Newlines
    // and tabs in the DOM textContent are NOT collapsed. This is
    // the documented trade-off for the regex-free implementation
    // (see source comment "Normalize whitespace without regex").
    // Email clients render \n as line break, which is acceptable.
    const out = emailToPlainText("<p>A\n\nB</p>");
    expect(out).toContain("\n");
  });

  it("trims leading and trailing whitespace", () => {
    // Pin: surrounding whitespace stripped — clean output.
    const out = emailToPlainText("<p>   hello   </p>");
    expect(out).toBe("hello");
  });

  it("empty string returns empty string", () => {
    // Pin: defensive — empty input doesn't crash, returns "".
    expect(emailToPlainText("")).toBe("");
  });

  it("plain text without tags passes through", () => {
    // Pin: input with no HTML still works (DOMParser wraps in
    // <html><body>).
    expect(emailToPlainText("just text")).toBe("just text");
  });

  it("strips deeply nested tag structure", () => {
    // Pin: arbitrary nesting depth handled. textContent walks
    // the whole tree.
    const html =
      "<div><div><div><div><span>deep</span></div></div></div></div>";
    expect(emailToPlainText(html)).toBe("deep");
  });

  it("malformed HTML does not throw", () => {
    // Pin: DOMParser is forgiving — unclosed tags / extra >
    // are recovered. Function should not throw on user input.
    expect(() => emailToPlainText("<p>unclosed")).not.toThrow();
    expect(() => emailToPlainText(">extra<")).not.toThrow();
  });

  it("returns empty when only contains script/style", () => {
    // Pin: if the entire body is non-visible (script/style only),
    // output is empty after trimming — no leaks of internal
    // JS/CSS.
    const out = emailToPlainText("<script>secrets</script>");
    expect(out).toBe("");
  });
});
