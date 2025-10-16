import { useState, useEffect, useRef } from "react";
import type { GridMetrics } from "./useGridMetrics";
import { ALLOCATION_MATRIX_LAYOUT } from "@/lib/constants/allocation-matrix-layout";

export interface PillGeometry {
  left: number;
  top: number;
  width: number;
  height: number;
  visible: boolean;
}

/**
 * Hook to calculate pill geometry based on card bounding boxes within a run
 * Uses ResizeObserver with debouncing and requestAnimationFrame for performance
 *
 * @param rowKey Unique identifier for the row
 * @param runStart Starting column index of the run
 * @param runEnd Ending column index of the run
 * @param gridMetrics Grid measurements (colWidth, gridGap, baseOffset)
 * @returns Pill geometry for absolute positioning
 */
export function usePillMetrics(
  rowKey: string | number,
  runStart: number,
  runEnd: number,
  gridMetrics: GridMetrics
): PillGeometry {
  const [geometry, setGeometry] = useState<PillGeometry>({
    left: 0,
    top: 0,
    width: 0,
    height: 0,
    visible: false,
  });

  const rafRef = useRef<number | undefined>(undefined);
  const debounceRef = useRef<NodeJS.Timeout | undefined>(undefined);

  useEffect(() => {
    const updateGeometry = () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
      }

      rafRef.current = requestAnimationFrame(() => {
        // Find all cards in this run
        const cards: HTMLElement[] = [];

        for (let idx = runStart; idx <= runEnd; idx++) {
          const cell = document.querySelector(
            `[data-row-key="${rowKey}"][data-subtype-index="${idx}"]`
          );
          if (cell) {
            const cardElements = Array.from(
              cell.querySelectorAll("[data-student-card]")
            ) as HTMLElement[];
            cards.push(...cardElements);
          }
        }

        if (cards.length === 0) {
          setGeometry((prev) => ({ ...prev, visible: false }));
          return;
        }

        // Calculate bounding box union of all cards
        const rects = cards.map((card) => card.getBoundingClientRect());
        const minLeft = Math.min(...rects.map((r) => r.left));
        const maxRight = Math.max(...rects.map((r) => r.right));
        const minTop = Math.min(...rects.map((r) => r.top));
        const maxBottom = Math.max(...rects.map((r) => r.bottom));

        // Find row container for relative positioning
        const rowContainer = document.querySelector(
          `[data-row-container="${rowKey}"]`
        ) as HTMLElement;
        if (!rowContainer) {
          setGeometry((prev) => ({ ...prev, visible: false }));
          return;
        }

        const rowRect = rowContainer.getBoundingClientRect();

        const { colWidth, gridGap, baseOffset } = gridMetrics;
        const { PILL_INSET_X, PILL_INSET_Y } = ALLOCATION_MATRIX_LAYOUT;

        // Calculate geometry using grid-aware formulas
        const cols = runEnd - runStart + 1;
        const width = cols * colWidth + (cols - 1) * gridGap - 2 * PILL_INSET_X;
        const left = baseOffset + runStart * (colWidth + gridGap) + PILL_INSET_X;
        const top = minTop - rowRect.top - PILL_INSET_Y;
        const height = maxBottom - minTop + 2 * PILL_INSET_Y;

        setGeometry({ left, top, width, height, visible: true });
      });
    };

    const debouncedUpdate = () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      debounceRef.current = setTimeout(updateGeometry, 50);
    };

    // Initial update
    updateGeometry();

    // Set up ResizeObserver to watch all cells and cards in this run
    const observer = new ResizeObserver(debouncedUpdate);
    const observedElements: Element[] = [];

    for (let idx = runStart; idx <= runEnd; idx++) {
      const cell = document.querySelector(
        `[data-row-key="${rowKey}"][data-subtype-index="${idx}"]`
      );
      if (cell) {
        observer.observe(cell);
        observedElements.push(cell);

        const cards = cell.querySelectorAll("[data-student-card]");
        cards.forEach((card) => {
          observer.observe(card);
          observedElements.push(card);
        });
      }
    }

    // Cleanup
    return () => {
      observer.disconnect();
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current);
      }
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [rowKey, runStart, runEnd, gridMetrics]);

  return geometry;
}
