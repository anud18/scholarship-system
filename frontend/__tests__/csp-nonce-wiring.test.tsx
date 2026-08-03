/**
 * Wiring guard for the CSP nonce (issue #1273).
 *
 * Under the nonce-gated production `style-src`, any Radix primitive that renders
 * its own `<style>` must receive the nonce or the browser drops the stylesheet —
 * a silent visual break (hidden scrollbars stop being hidden) that no type check
 * or lint catches, and that dev never reproduces because the dev CSP still
 * carries 'unsafe-inline'.
 *
 * `@radix-ui/react-select` and `@radix-ui/react-scroll-area` are the only two
 * packages in the tree that render a `<style>` in JSX (verified by grepping
 * `dangerouslySetInnerHTML` across @radix-ui/*), and both accept a `nonce` prop.
 * These tests pin that our ui/ wrappers actually pass it through.
 */
import { render, screen } from "@testing-library/react";
import { CspNonceProvider } from "@/components/providers/csp-nonce";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const NONCE = "test-nonce-abc123";

// Radix Select drives real layout APIs jsdom does not implement.
beforeAll(() => {
  Element.prototype.scrollIntoView = jest.fn();
  Element.prototype.hasPointerCapture = jest.fn(() => false);
  Element.prototype.releasePointerCapture = jest.fn();
  global.ResizeObserver =
    global.ResizeObserver ||
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
});

function styleNonces(): (string | null)[] {
  return [...document.querySelectorAll("style")].map((s) => s.getAttribute("nonce"));
}

describe("CSP nonce wiring", () => {
  it("ScrollArea forwards the nonce to the Radix viewport <style>", () => {
    render(
      <CspNonceProvider nonce={NONCE}>
        <ScrollArea>
          <div>content</div>
        </ScrollArea>
      </CspNonceProvider>
    );
    const nonces = styleNonces();
    expect(nonces.length).toBeGreaterThan(0);
    expect(nonces).toContain(NONCE);
  });

  it("Select forwards the nonce to the Radix viewport <style> when open", async () => {
    render(
      <CspNonceProvider nonce={NONCE}>
        <Select open>
          <SelectTrigger>
            <SelectValue placeholder="pick" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="a">A</SelectItem>
          </SelectContent>
        </Select>
      </CspNonceProvider>
    );
    // The content renders in a portal; wait for the item to confirm it mounted.
    expect(await screen.findByText("A")).toBeInTheDocument();
    expect(styleNonces()).toContain(NONCE);
  });

  it("JsonDiffViewer nonces the stylesheets @emotion/css injects", async () => {
    // react-diff-viewer-continued styles itself with @emotion/css, whose default
    // cache carries no nonce — the audit-trail diff would render unstyled in
    // production. Assert on emotion's own tags (data-emotion), not just any
    // <style>, so the test cannot pass on some other component's element.
    const { JsonDiffViewer } = await import("@/components/audit-trail/JsonDiffViewer");
    render(
      <CspNonceProvider nonce={NONCE}>
        <JsonDiffViewer oldValue={{ a: 1 }} newValue={{ a: 2 }} />
      </CspNonceProvider>
    );
    const emotionTags = [...document.querySelectorAll("style[data-emotion]")];
    expect(emotionTags.length).toBeGreaterThan(0);
    expect(emotionTags.every((t) => t.getAttribute("nonce") === NONCE)).toBe(true);
  });

  it("renders without a nonce outside the provider (dev CSP path)", () => {
    // Scope to the styles THIS render adds: emotion leaves its <head> tags
    // behind after the earlier test (testing-library only unmounts containers).
    const before = new Set(document.querySelectorAll("style"));
    render(
      <ScrollArea>
        <div>content</div>
      </ScrollArea>
    );
    const added = [...document.querySelectorAll("style")].filter((s) => !before.has(s));
    // No provider -> undefined nonce -> no crash, no nonce attribute.
    expect(added.length).toBeGreaterThan(0);
    expect(added.filter((s) => s.getAttribute("nonce") === NONCE)).toHaveLength(0);
  });
});
