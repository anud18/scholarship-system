/**
 * Tests for `ALLOCATION_MATRIX_LAYOUT` constant in
 * `frontend/lib/constants/allocation-matrix-layout.ts`.
 *
 * The existing test file (`allocation-matrix-layout.test.ts`) covers
 * the `contiguousRuns` function. This wave fills the gap by pinning
 * the **constant object itself** — the actual layout values + color
 * palettes + Z-index ordering that the AllocationMatrix component
 * renders from.
 *
 * Drift in these values silently shifts UI:
 *  - Grid column widths → table layout breaks at boundary widths
 *  - Track height ratio → student-card pill bands look wrong
 *  - Pill insets → border/shadow alignment off
 *  - Color palette → wrong visual treatment per allocation state
 *  - Z-index ordering → cards stack wrong (pill above card, etc.)
 *
 * 16 cases.
 */

import { ALLOCATION_MATRIX_LAYOUT } from "../allocation-matrix-layout";

describe("ALLOCATION_MATRIX_LAYOUT constant", () => {
  // ─── Grid dimensions ────────────────────────────────────────────────

  it("rank column is 220px wide", () => {
    // Pin: the sticky first column width. Pill geometry math
    // in useGridMetrics depends on this.
    expect(ALLOCATION_MATRIX_LAYOUT.RANK_COLUMN_WIDTH).toBe(220);
  });

  it("sub-type column min width is 260px", () => {
    // Pin: matches CSS grid-template-columns minmax(260px, ...)
    // Refactoring requires CSS update too.
    expect(ALLOCATION_MATRIX_LAYOUT.SUBTYPE_COLUMN_MIN_WIDTH).toBe(260);
  });

  it("grid gap is 0 (no inter-cell spacing)", () => {
    // Pin: zero. Pill geometry formula relies on gap=0.
    expect(ALLOCATION_MATRIX_LAYOUT.GRID_GAP).toBe(0);
  });

  it("cell padding is 16px horizontal and vertical", () => {
    // Pin: matches Tailwind p-4 (16px). Pin both axes.
    expect(ALLOCATION_MATRIX_LAYOUT.CELL_PADDING_X).toBe(16);
    expect(ALLOCATION_MATRIX_LAYOUT.CELL_PADDING_Y).toBe(16);
  });

  // ─── Track styling ──────────────────────────────────────────────────

  it("track height range is 16-24px", () => {
    // Pin: min/max for track band. Pin range so a refactor
    // squishing it to 0-10 would be obvious.
    expect(ALLOCATION_MATRIX_LAYOUT.TRACK_HEIGHT_MIN).toBe(16);
    expect(ALLOCATION_MATRIX_LAYOUT.TRACK_HEIGHT_MAX).toBe(24);
  });

  it("track height ratio is 28% of card height", () => {
    // Pin: 0.28. The track is sized as 28% of the parent card
    // — too low looks anemic, too high covers card content.
    expect(ALLOCATION_MATRIX_LAYOUT.TRACK_HEIGHT_RATIO).toBe(0.28);
  });

  // ─── Pill styling ───────────────────────────────────────────────────

  it("pill horizontal inset is 6px (minimal, for border coverage)", () => {
    // Pin: PILL_INSET_X=6 is documented as "minimal inset to
    // cover borders". Pin so a refactor enlarging it doesn't
    // leave gaps at run boundaries.
    expect(ALLOCATION_MATRIX_LAYOUT.PILL_INSET_X).toBe(6);
  });

  it("pill vertical inset is 10px", () => {
    expect(ALLOCATION_MATRIX_LAYOUT.PILL_INSET_Y).toBe(10);
  });

  it("pill border is 1.5px (matches Tailwind border-[1.5px])", () => {
    expect(ALLOCATION_MATRIX_LAYOUT.PILL_BORDER_WIDTH).toBe(1.5);
  });

  it("pill card radius is 16px (rounded-2xl)", () => {
    expect(ALLOCATION_MATRIX_LAYOUT.PILL_CARD_RADIUS).toBe(16);
  });

  // ─── Color palette — 3 variants ─────────────────────────────────────

  it("PILL_COLORS has exactly three documented variants", () => {
    // Pin: blue (allocated), warm (backup), muted (unallocated).
    // Adding a variant requires updating the AllocationMatrix
    // switch-case AND this test.
    expect(Object.keys(ALLOCATION_MATRIX_LAYOUT.PILL_COLORS).sort()).toEqual([
      "blue",
      "muted",
      "warm",
    ]);
  });

  it("each variant exposes 6 styled keys", () => {
    // Pin: bgStart/bgEnd/border/insetShadow/hoverBgStart/hoverBgEnd.
    // The renderer reads these — dropping one would crash.
    const expectedKeys = [
      "bgStart",
      "bgEnd",
      "border",
      "insetShadow",
      "hoverBgStart",
      "hoverBgEnd",
    ].sort();
    for (const variant of ["blue", "warm", "muted"] as const) {
      expect(Object.keys(ALLOCATION_MATRIX_LAYOUT.PILL_COLORS[variant]).sort()).toEqual(
        expectedKeys
      );
    }
  });

  it("blue variant uses Tailwind blue-50/100 gradient", () => {
    // Pin: the documented NYCU blue palette for allocated state.
    // Pin so a refactor to a different blue shade is caught.
    expect(ALLOCATION_MATRIX_LAYOUT.PILL_COLORS.blue.bgStart).toBe(
      "rgb(239, 246, 255)"
    ); // blue-50
    expect(ALLOCATION_MATRIX_LAYOUT.PILL_COLORS.blue.bgEnd).toBe(
      "rgb(219, 234, 254)"
    ); // blue-100
  });

  it("warm variant uses orange palette for backup students", () => {
    expect(ALLOCATION_MATRIX_LAYOUT.PILL_COLORS.warm.bgStart).toBe(
      "rgb(255, 247, 237)"
    ); // orange-50
  });

  it("muted variant uses slate palette for unallocated", () => {
    expect(ALLOCATION_MATRIX_LAYOUT.PILL_COLORS.muted.bgStart).toBe(
      "rgb(248, 250, 252)"
    ); // slate-50
  });

  // ─── Z-index stacking order ─────────────────────────────────────────

  it("z-index order is row<cell<pill<card", () => {
    // Pin: the stacking order is critical — pill sits BELOW card
    // so card content (avatar, name) is on top. If pill rises
    // above card, you can't see the student.
    const z = ALLOCATION_MATRIX_LAYOUT.Z_INDEX;
    expect(z.ROW_CONTAINER).toBeLessThan(z.CELL_BACKGROUND);
    expect(z.CELL_BACKGROUND).toBeLessThan(z.PILL);
    expect(z.PILL).toBeLessThan(z.CARD);
  });

  it("z-index values are specific pinned numbers (0/5/10/20)", () => {
    // Pin: exact values so a refactor doesn't accidentally use
    // larger numbers (which can leak above unrelated Tailwind
    // z-{10,20,30,40,50} utilities).
    expect(ALLOCATION_MATRIX_LAYOUT.Z_INDEX.ROW_CONTAINER).toBe(0);
    expect(ALLOCATION_MATRIX_LAYOUT.Z_INDEX.CELL_BACKGROUND).toBe(5);
    expect(ALLOCATION_MATRIX_LAYOUT.Z_INDEX.PILL).toBe(10);
    expect(ALLOCATION_MATRIX_LAYOUT.Z_INDEX.CARD).toBe(20);
  });

  // ─── const assertion guards ──────────────────────────────────────────

  it("constant is frozen-like (as const) — type-level immutability", () => {
    // Pin: typed as `as const`. We can't directly check the
    // type-level readonly, but we can verify nested objects
    // exist and have the right shape — pin via structural check.
    expect(ALLOCATION_MATRIX_LAYOUT).toMatchObject({
      RANK_COLUMN_WIDTH: expect.any(Number),
      PILL_COLORS: expect.objectContaining({
        blue: expect.any(Object),
        warm: expect.any(Object),
        muted: expect.any(Object),
      }),
      Z_INDEX: expect.objectContaining({
        ROW_CONTAINER: expect.any(Number),
        PILL: expect.any(Number),
      }),
    });
  });
});
