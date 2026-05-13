/**
 * Tests for `contiguousRuns` in `lib/constants/allocation-matrix-layout.ts`.
 *
 * This helper groups student-allocation column indexes into contiguous
 * runs for rendering the run-level pill UI in the AllocationMatrix.
 * Each run becomes a single styled pill spanning multiple cells; a bug
 * here would either:
 * - Render separate pills for adjacent columns → broken visual unity
 * - Merge non-adjacent columns into one pill → wrong students appear
 *   grouped together (allocation misrepresentation in the UI)
 *
 * 10 cases. Pure function, no DOM / no React.
 */

import { contiguousRuns } from "../allocation-matrix-layout";

describe("contiguousRuns", () => {
  it("returns empty array for empty input", () => {
    expect(contiguousRuns([])).toEqual([]);
  });

  it("returns single run for single index", () => {
    expect(contiguousRuns([3])).toEqual([[3, 3]]);
  });

  it("groups a fully-contiguous range as one run", () => {
    expect(contiguousRuns([0, 1, 2, 3])).toEqual([[0, 3]]);
  });

  it("splits non-contiguous indexes into separate runs", () => {
    // From the JSDoc example
    expect(contiguousRuns([0, 1, 2, 5, 6])).toEqual([
      [0, 2],
      [5, 6],
    ]);
  });

  it("treats every isolated index as its own run", () => {
    // From the JSDoc example
    expect(contiguousRuns([0, 2, 4])).toEqual([
      [0, 0],
      [2, 2],
      [4, 4],
    ]);
  });

  it("handles unsorted input by sorting first", () => {
    /* Pin: input is sorted internally — caller doesn't need to pre-sort.
     * Without this, a user-clicked-out-of-order selection would render
     * incorrectly. */
    expect(contiguousRuns([3, 1, 2, 5])).toEqual([
      [1, 3],
      [5, 5],
    ]);
  });

  it("deduplicates input via Set", () => {
    /* Pin: duplicate indexes collapsed. Defensive against double-add
     * bugs in the caller. */
    expect(contiguousRuns([1, 1, 2, 2, 3])).toEqual([[1, 3]]);
  });

  it("handles multiple separated runs", () => {
    expect(contiguousRuns([0, 1, 3, 4, 7])).toEqual([
      [0, 1],
      [3, 4],
      [7, 7],
    ]);
  });

  it("does not mutate the input array", () => {
    /* Pin: function uses spread + sort, so the caller's array is
     * untouched. Otherwise UI state held in React would silently
     * mutate during a render. */
    const input = [5, 2, 1];
    contiguousRuns(input);
    expect(input).toEqual([5, 2, 1]);
  });

  it("handles negative indexes and zero correctly", () => {
    /* Pin: not strictly used in production but defensive. Contiguity
     * still works around zero. */
    expect(contiguousRuns([-2, -1, 0, 1])).toEqual([[-2, 1]]);
  });
});
