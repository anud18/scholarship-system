import { useState, useEffect } from "react";

export interface GridMetrics {
  colWidth: number;
  gridGap: number;
  baseOffset: number;
}

/**
 * Hook to measure grid column width, gap, and base offset for pill positioning
 * @param rankColumnWidth Width of the sticky rank column (default 220px)
 * @returns Grid metrics for calculating pill positions
 */
export function useGridMetrics(rankColumnWidth: number = 220): GridMetrics {
  const [metrics, setMetrics] = useState<GridMetrics>({
    colWidth: 260,
    gridGap: 0,
    baseOffset: rankColumnWidth,
  });

  useEffect(() => {
    const measureGrid = () => {
      // Find first two subtype cells to calculate column width + gap
      const cells = Array.from(
        document.querySelectorAll("[data-subtype-index]")
      ) as HTMLElement[];

      if (cells.length >= 2) {
        const firstRect = cells[0].getBoundingClientRect();
        const secondRect = cells[1].getBoundingClientRect();
        const colWidth = firstRect.width;
        const gridGap = secondRect.left - firstRect.right;

        // Measure actual rank column width from DOM (including borders & shadows)
        let measuredBaseOffset = rankColumnWidth; // fallback
        const rankColumn = document.querySelector(
          "[data-row-container] .sticky.left-0"
        ) as HTMLElement;
        if (rankColumn) {
          measuredBaseOffset = rankColumn.getBoundingClientRect().width;
        }

        setMetrics({
          colWidth,
          gridGap,
          baseOffset: measuredBaseOffset,
        });
      }
    };

    // Initial measurement
    measureGrid();

    // Set up ResizeObserver to watch for grid changes
    const observer = new ResizeObserver(measureGrid);
    const cells = document.querySelectorAll("[data-subtype-index]");
    cells.forEach((cell) => observer.observe(cell));

    // Also observe window resize
    window.addEventListener("resize", measureGrid);

    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measureGrid);
    };
  }, [rankColumnWidth]);

  return metrics;
}
