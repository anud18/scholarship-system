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

  it("renders without a nonce outside the provider (dev CSP path)", () => {
    render(
      <ScrollArea>
        <div>content</div>
      </ScrollArea>
    );
    // No provider -> undefined nonce -> no crash, no nonce attribute.
    expect(styleNonces().filter((n) => n === NONCE)).toHaveLength(0);
  });
});
