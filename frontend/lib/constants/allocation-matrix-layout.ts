/**
 * Allocation matrix layout constants
 * Centralizes grid dimensions and spacing for consistent track rendering
 */

export const ALLOCATION_MATRIX_LAYOUT = {
  // Grid column widths
  RANK_COLUMN_WIDTH: 220, // px - First column (ranking)
  SUBTYPE_COLUMN_MIN_WIDTH: 260, // px - Sub-type columns

  // Grid gap (currently 0, but declared for future use)
  GRID_GAP: 0, // px

  // Cell padding
  CELL_PADDING_X: 16, // px-4 = 1rem = 16px
  CELL_PADDING_Y: 16, // py-4 = 1rem = 16px

  // Track styling
  TRACK_HEIGHT_MIN: 16, // px
  TRACK_HEIGHT_MAX: 24, // px
  TRACK_HEIGHT_RATIO: 0.28, // 28% of card height
  TRACK_PADDING_X: 8, // px - Inner padding from cell edges

  // Pill styling (for run-level design)
  PILL_INSET_X: 6, // px - Horizontal inset from cell edges (minimal inset to cover borders)
  PILL_INSET_Y: 10, // px - Vertical inset from card bounding box (increased for consistency)
  PILL_BORDER_WIDTH: 1.5, // px - Border thickness
  PILL_CARD_RADIUS: 16, // px - Card corner radius (rounded-2xl) for radius calculation

  // Pill color palettes (matching NYCU theme)
  PILL_COLORS: {
    // NYCU Blue variant - for allocated students
    blue: {
      bgStart: "rgb(239, 246, 255)", // blue-50
      bgEnd: "rgb(219, 234, 254)", // blue-100
      border: "rgb(147, 197, 253)", // blue-300
      insetShadow: "rgba(30, 64, 175, 0.08)", // blue-800 with transparency
      hoverBgStart: "rgb(219, 234, 254)", // blue-100
      hoverBgEnd: "rgb(191, 219, 254)", // blue-200
    },
    // Orange variant - for backup students
    warm: {
      bgStart: "rgb(255, 247, 237)", // orange-50
      bgEnd: "rgb(255, 237, 213)", // orange-100
      border: "rgb(253, 186, 116)", // orange-300
      insetShadow: "rgba(194, 65, 12, 0.08)", // orange-700 with transparency
      hoverBgStart: "rgb(255, 237, 213)", // orange-100
      hoverBgEnd: "rgb(254, 215, 170)", // orange-200
    },
    // Muted slate variant - for unallocated students
    muted: {
      bgStart: "rgb(248, 250, 252)", // slate-50
      bgEnd: "rgb(241, 245, 249)", // slate-100
      border: "rgb(226, 232, 240)", // slate-200
      insetShadow: "rgba(0, 0, 0, 0.04)",
      hoverBgStart: "rgb(241, 245, 249)", // slate-100
      hoverBgEnd: "rgb(226, 232, 240)", // slate-200
    },
  },

  // Z-index layers
  Z_INDEX: {
    ROW_CONTAINER: 0,
    CELL_BACKGROUND: 5,
    PILL: 10, // Run-level pills
    CARD: 20,
  },
} as const;

/**
 * Split an array of column indexes into contiguous runs
 * @param indexes - Sorted array of column indexes (e.g., [0, 1, 2, 5, 6])
 * @returns Array of [start, end] pairs (e.g., [[0, 2], [5, 6]])
 *
 * @example
 * contiguousRuns([0, 2, 4]) => [[0, 0], [2, 2], [4, 4]]
 * contiguousRuns([0, 1, 2, 5, 6]) => [[0, 2], [5, 6]]
 */
export function contiguousRuns(indexes: number[]): Array<[number, number]> {
  if (!indexes.length) return [];

  const sorted = [...new Set(indexes)].sort((a, b) => a - b);
  const runs: Array<[number, number]> = [];
  let start = sorted[0];
  let prev = start;

  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] === prev + 1) {
      prev = sorted[i];
    } else {
      runs.push([start, prev]);
      start = sorted[i];
      prev = start;
    }
  }

  runs.push([start, prev]);
  return runs;
}
