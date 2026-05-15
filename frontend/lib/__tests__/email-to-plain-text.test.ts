/**
 * Tests for `frontend/lib/email-renderer.tsx` — `emailToPlainText`.
 *
 * Function had ZERO test references. SECURITY-CRITICAL —
 * extracts plain text from rendered HTML emails for the in-app
 * notification preview and email-test-mode UI. The docstring
 * explicitly notes the regex-free DOMParser design ("no regex
 * patterns that could be bypassed") to satisfy CodeQL.
 *
 * Wave 6a154 pins:
 * - script/style elements REMOVED before extraction (XSS-relevant
 *   — don't leak content of script tags into preview)
 * - HTML entity decoding (DOMParser handles &amp; / &lt; / 中文)
 * - Whitespace normalization without regex (.split(' '))
 * - Newline preservation (regex-free design choice)
 * - Empty / malformed HTML → empty string (not throw)
 * - CJK text round-trip
 *
 * jsdom provides DOMParser in the jest env so this exercises
 * the primary code path (not the Node.js fallback).
 */

import { emailToPlainText } from "../email-renderer";

describe("emailToPlainText (SECURITY: DOMParser-based extraction)", () => {
  describe("script and style elements removed (XSS prevention)", () => {
    it("removes <script> element content entirely", () => {
      // Pin SECURITY: <script> body must NOT leak into the
      // plain-text output. If admin previewed a malicious
      // email, refactor accidentally including script body
      // could surface credentials/payloads.
      const html = `<p>Hello</p><script>alert('XSS')</script><p>World</p>`;
      const result = emailToPlainText(html);
      expect(result).not.toContain("alert");
      expect(result).not.toContain("XSS");
      expect(result).toContain("Hello");
      expect(result).toContain("World");
    });

    it("removes <style> element content", () => {
      // Pin: CSS in <style> isn't user-relevant in plain-text
      // preview. Pin so refactor doesn't accidentally inline
      // it into notification body.
      const html = `<style>body { color: red; }</style><p>Hello</p>`;
      const result = emailToPlainText(html);
      expect(result).not.toContain("color:");
      expect(result).not.toContain("red");
      expect(result).toContain("Hello");
    });

    it("removes nested <script> inside larger HTML", () => {
      const html = `
        <div>
          <h1>Title</h1>
          <script>document.cookie='stolen'</script>
          <p>Body text</p>
        </div>
      `;
      const result = emailToPlainText(html);
      expect(result).not.toContain("cookie");
      expect(result).not.toContain("stolen");
      expect(result).toContain("Title");
      expect(result).toContain("Body text");
    });

    it("removes multiple <script> blocks", () => {
      const html = `<script>a()</script>Hello<script>b()</script>World`;
      const result = emailToPlainText(html);
      expect(result).not.toContain("a()");
      expect(result).not.toContain("b()");
      expect(result).toContain("Hello");
      expect(result).toContain("World");
    });
  });

  describe("HTML entity decoding (DOMParser handles via textContent)", () => {
    it("decodes &amp; to &", () => {
      // Pin: DOMParser handles entity decoding. Pin so refactor
      // to a manual regex-based parser doesn't drop entities.
      const result = emailToPlainText("<p>One &amp; Two</p>");
      expect(result).toContain("&");
      expect(result).not.toContain("&amp;");
    });

    it("decodes &lt; / &gt; to < / >", () => {
      const result = emailToPlainText("<p>5 &lt; 10 &gt; 1</p>");
      expect(result).toContain("<");
      expect(result).toContain(">");
    });

    it("decodes numeric entity (&#39; → ')", () => {
      const result = emailToPlainText("<p>It&#39;s working</p>");
      expect(result).toContain("'");
      expect(result).toContain("It");
    });

    it("decodes CJK numeric entity (&#29579; → 王)", () => {
      // Pin: zh-TW Chinese entity numeric form decodes correctly.
      // Pin so refactor to ASCII-only-aware parser doesn't drop
      // CJK characters from student names.
      const result = emailToPlainText("<p>&#29579;&#23567;&#26126;</p>");
      expect(result).toContain("王小明");
    });
  });

  describe("plain text round-trip", () => {
    it("CJK text preserved verbatim", () => {
      // Pin: zh-TW Chinese characters in regular text nodes
      // round-trip unchanged.
      const result = emailToPlainText(
        "<p>親愛的王小明同學您好</p>"
      );
      expect(result).toBe("親愛的王小明同學您好");
    });

    it("strips HTML tags but keeps text content", () => {
      const result = emailToPlainText(
        "<div><h1>Title</h1><p>Body</p></div>"
      );
      expect(result).toContain("Title");
      expect(result).toContain("Body");
      expect(result).not.toContain("<h1");
      expect(result).not.toContain("</p>");
    });

    it("multiple consecutive spaces collapsed via split(' ').filter(Boolean)", () => {
      // Pin: whitespace normalization without regex (per
      // docstring SECURITY constraint). split(' ').filter(
      // Boolean).join(' ') collapses runs of plain-space.
      const result = emailToPlainText("<p>A    B    C</p>");
      expect(result).toBe("A B C");
    });

    it("output is trimmed (no leading/trailing whitespace)", () => {
      const result = emailToPlainText("<p>  Hello  </p>");
      expect(result).toBe("Hello");
    });
  });

  describe("defensive paths", () => {
    it("empty string input → empty string", () => {
      expect(emailToPlainText("")).toBe("");
    });

    it("text-only input (no tags) preserved", () => {
      // Pin: DOMParser still parses; text becomes body.textContent.
      const result = emailToPlainText("plain text only");
      expect(result).toBe("plain text only");
    });

    it("malformed HTML does not throw", () => {
      // Pin: DOMParser is permissive for text/html. Pin so
      // refactor to strict XML parser doesn't crash on real-
      // world emails with malformed markup.
      expect(() => emailToPlainText("<p>unclosed")).not.toThrow();
      expect(() => emailToPlainText("</p><p>")).not.toThrow();
      expect(() => emailToPlainText("<<<>>>")).not.toThrow();
    });

    it("nested HTML preserves text order", () => {
      const result = emailToPlainText(
        "<div><span>A</span><span>B</span><span>C</span></div>"
      );
      // Tokens appear in order
      const aIdx = result.indexOf("A");
      const bIdx = result.indexOf("B");
      const cIdx = result.indexOf("C");
      expect(aIdx).toBeLessThan(bIdx);
      expect(bIdx).toBeLessThan(cIdx);
    });
  });

  describe("attribute values NOT extracted (only text nodes)", () => {
    it("href attribute value does NOT leak into output", () => {
      // Pin SECURITY: textContent doesn't include attribute
      // values. Pin so refactor doesn't accidentally surface
      // tracking URLs / secret-laden hrefs in plain-text preview.
      const html = `<a href="https://evil.com/secret?token=abc123">Click here</a>`;
      const result = emailToPlainText(html);
      expect(result).not.toContain("evil.com");
      expect(result).not.toContain("token=abc123");
      expect(result).toContain("Click here");
    });

    it("alt attribute on <img> does NOT leak", () => {
      const html = `<img src="https://x/y.png" alt="alt text"><p>Body</p>`;
      const result = emailToPlainText(html);
      expect(result).not.toContain("https://x");
      expect(result).not.toContain("alt text");
      expect(result).toContain("Body");
    });

    it("data-* attributes do NOT leak", () => {
      const html = `<div data-secret="oops">Visible</div>`;
      const result = emailToPlainText(html);
      expect(result).not.toContain("oops");
      expect(result).toContain("Visible");
    });
  });
});
