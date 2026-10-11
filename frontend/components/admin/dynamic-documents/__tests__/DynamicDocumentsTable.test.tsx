import { render, screen } from "@testing-library/react";
import type { DragEndEvent } from "@dnd-kit/core";

import type { ApplicationDocument } from "@/lib/api";
import { DynamicDocumentsTable } from "../DynamicDocumentsTable";

// Pointer-driven dragging can't run in jsdom, so capture the onDragEnd the
// table hands to DndContext and fire drops through it directly.
let capturedDragEnd: ((event: DragEndEvent) => void) | undefined;

jest.mock("@dnd-kit/core", () => {
  const actual = jest.requireActual("@dnd-kit/core");
  return {
    ...actual,
    DndContext: ({
      children,
      onDragEnd,
    }: {
      children: React.ReactNode;
      onDragEnd: (event: DragEndEvent) => void;
    }) => {
      capturedDragEnd = onDragEnd;
      return <>{children}</>;
    },
  };
});

const makeDoc = (id: number, name: string): ApplicationDocument =>
  ({
    id,
    scholarship_type: "phd",
    document_name: name,
    is_required: true,
    accepted_file_types: ["PDF"],
    max_file_size: "5MB",
    max_file_count: 1,
    display_order: id,
    is_active: true,
  }) as ApplicationDocument;

const drop = (activeId: number, overId: number | null) =>
  capturedDragEnd?.({
    active: { id: activeId },
    over: overId === null ? null : { id: overId },
  } as unknown as DragEndEvent);

const renderTable = (
  overrides: Partial<React.ComponentProps<typeof DynamicDocumentsTable>> = {}
) => {
  const props: React.ComponentProps<typeof DynamicDocumentsTable> = {
    documents: [makeDoc(1, "推薦信"), makeDoc(2, "研究計畫"), makeDoc(3, "成績單")],
    isReordering: false,
    onReorder: jest.fn(),
    uploadingExampleDocId: null,
    onToggleActive: jest.fn(),
    onUploadExample: jest.fn(),
    onPreviewExample: jest.fn(),
    onDeleteExample: jest.fn(),
    onEdit: jest.fn(),
    onDelete: jest.fn(),
    ...overrides,
  };
  render(<DynamicDocumentsTable {...props} />);
  return props;
};

describe("DynamicDocumentsTable", () => {
  beforeEach(() => {
    capturedDragEnd = undefined;
  });

  it("renders one drag handle per document, in the given order", () => {
    renderTable();
    expect(screen.getAllByRole("button", { name: "拖曳排序" })).toHaveLength(3);
    const rows = screen.getAllByTestId(/^dynamic-document-row-/);
    expect(rows.map(r => r.getAttribute("data-testid"))).toEqual([
      "dynamic-document-row-1",
      "dynamic-document-row-2",
      "dynamic-document-row-3",
    ]);
  });

  it("reports the moved order on drop", () => {
    const { onReorder } = renderTable();
    drop(3, 1);
    expect(onReorder).toHaveBeenCalledTimes(1);
    const next = (onReorder as jest.Mock).mock.calls[0][0] as ApplicationDocument[];
    expect(next.map(d => d.id)).toEqual([3, 1, 2]);
  });

  it("ignores drops outside the list or onto the same row", () => {
    const { onReorder } = renderTable();
    drop(2, null);
    drop(2, 2);
    expect(onReorder).not.toHaveBeenCalled();
  });

  it("locks the drag handles while a reorder is saving", () => {
    renderTable({ isReordering: true });
    for (const handle of screen.getAllByRole("button", { name: "拖曳排序" })) {
      expect(handle).toBeDisabled();
    }
  });
});
