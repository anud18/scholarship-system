import { render, screen, fireEvent, act } from "@testing-library/react";
import { FileUpload } from "../file-upload";

// Mock the FilePreviewDialog component (real one uses portals/iframes).
// Matches the actual prop contract: { isOpen, onClose, file, locale } where
// file is { url, filename, type } | null.
jest.mock("../file-preview-dialog", () => ({
  FilePreviewDialog: ({
    isOpen,
    onClose,
    file,
  }: {
    isOpen: boolean;
    onClose: () => void;
    file: { url: string; filename: string; type: string } | null;
  }) =>
    isOpen && file ? (
      <div data-testid="file-preview-dialog">
        <span>Preview: {file.filename}</span>
        <span>Type: {file.type}</span>
        <span>URL: {file.url}</span>
        <button onClick={onClose}>Close Preview</button>
      </div>
    ) : null,
}));

// jsdom has no URL.createObjectURL
global.URL.createObjectURL = jest.fn(() => "blob:mock-object-url");
global.URL.revokeObjectURL = jest.fn();

function getFileInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector('input[type="file"]');
  expect(input).not.toBeNull();
  return input as HTMLInputElement;
}

function selectFiles(input: HTMLInputElement, files: File[]) {
  Object.defineProperty(input, "files", {
    value: files,
    configurable: true,
  });
  fireEvent.change(input);
}

/** In a rendered file row, buttons are [preview(Eye), remove(X)] — the
 *  "choose file" control is a <label>, not a button role. */
function getRowButtons() {
  const buttons = screen.getAllByRole("button");
  return { previewButton: buttons[0], removeButton: buttons[1] };
}

// NOTE: every real caller passes `initialFiles` (controlled usage, echoing
// onFilesChange back into the prop). When the prop is OMITTED, the default
// `initialFiles = []` parameter creates a fresh array per render, so the
// sync-useEffect re-runs after an internal setFiles and WIPES the freshly
// selected files from the list (component bug for uncontrolled usage —
// see final report). Tests that assert the rendered list after selection
// therefore pass a stable empty array, mirroring real usage.
const STABLE_EMPTY_FILES: File[] = [];

describe("FileUpload Component", () => {
  let mockOnFilesChange: jest.Mock;

  beforeEach(() => {
    mockOnFilesChange = jest.fn();
    jest.clearAllMocks();
  });

  it("should render the upload area (zh locale by default)", () => {
    render(<FileUpload onFilesChange={mockOnFilesChange} />);

    expect(screen.getByText("拖放檔案到此處或點擊上傳")).toBeInTheDocument();
    expect(screen.getByText("選擇檔案")).toBeInTheDocument();
    // Accepted types and max size surfaced to the user
    expect(screen.getByText(/\.pdf, \.jpg, \.jpeg, \.png/)).toBeInTheDocument();
    expect(screen.getByText(/10 MB/)).toBeInTheDocument();
  });

  it("should render in English locale", () => {
    render(<FileUpload onFilesChange={mockOnFilesChange} locale="en" />);

    expect(
      screen.getByText("Drag and drop files here or click to upload")
    ).toBeInTheDocument();
    expect(screen.getByText("Choose File")).toBeInTheDocument();
  });

  it("should handle file selection via input", () => {
    const { container } = render(
      <FileUpload
        onFilesChange={mockOnFilesChange}
        initialFiles={STABLE_EMPTY_FILES}
      />
    );

    const file = new File(["content"], "test.pdf", {
      type: "application/pdf",
    });
    selectFiles(getFileInput(container), [file]);

    expect(mockOnFilesChange).toHaveBeenCalledWith([file]);
    expect(screen.getByText("test.pdf")).toBeInTheDocument();
  });

  it("should handle drag and drop", () => {
    render(<FileUpload onFilesChange={mockOnFilesChange} />);

    const dropZone = screen
      .getByText("拖放檔案到此處或點擊上傳")
      .closest("div");
    const file = new File(["content"], "test.pdf", {
      type: "application/pdf",
    });

    fireEvent.dragEnter(dropZone!, { dataTransfer: { files: [file] } });
    fireEvent.drop(dropZone!, { dataTransfer: { files: [file] } });

    expect(mockOnFilesChange).toHaveBeenCalledWith([file]);
  });

  it("should filter out files with unaccepted extensions", () => {
    const { container } = render(
      <FileUpload onFilesChange={mockOnFilesChange} acceptedTypes={[".pdf"]} />
    );

    const validFile = new File(["content"], "test.pdf", {
      type: "application/pdf",
    });
    const invalidFile = new File(["content"], "test.txt", {
      type: "text/plain",
    });
    selectFiles(getFileInput(container), [validFile, invalidFile]);

    expect(mockOnFilesChange).toHaveBeenCalledWith([validFile]);
  });

  it("should filter out files exceeding the size limit", () => {
    const maxSize = 1024; // 1KB
    const { container } = render(
      <FileUpload onFilesChange={mockOnFilesChange} maxSize={maxSize} />
    );

    const smallFile = new File(["a"], "small.pdf", {
      type: "application/pdf",
    });
    const largeFile = new File(["a".repeat(2000)], "large.pdf", {
      type: "application/pdf",
    });
    selectFiles(getFileInput(container), [smallFile, largeFile]);

    expect(mockOnFilesChange).toHaveBeenCalledWith([smallFile]);
  });

  it("should enforce the max files limit", () => {
    const { container } = render(
      <FileUpload
        onFilesChange={mockOnFilesChange}
        maxFiles={2}
        initialFiles={STABLE_EMPTY_FILES}
      />
    );

    const files = [
      new File(["1"], "file1.pdf", { type: "application/pdf" }),
      new File(["2"], "file2.pdf", { type: "application/pdf" }),
      new File(["3"], "file3.pdf", { type: "application/pdf" }),
    ];
    selectFiles(getFileInput(container), files);

    expect(mockOnFilesChange).toHaveBeenCalledWith([files[0], files[1]]);
    expect(screen.getByText(/\(2\/2\)/)).toBeInTheDocument();
  });

  it("should reject files without an extension in the accepted list", () => {
    const { container } = render(
      <FileUpload onFilesChange={mockOnFilesChange} />
    );

    const fileWithoutExtension = new File(["content"], "noextension", {
      type: "application/pdf",
    });
    selectFiles(getFileInput(container), [fileWithoutExtension]);

    expect(mockOnFilesChange).toHaveBeenCalledWith([]);
  });

  it("should display initial files with the file-count heading", () => {
    const initialFiles = [
      new File(["content"], "test.pdf", { type: "application/pdf" }),
    ];

    render(
      <FileUpload
        onFilesChange={mockOnFilesChange}
        initialFiles={initialFiles}
        fileType="transcript"
      />
    );

    expect(screen.getByText("test.pdf")).toBeInTheDocument();
    expect(screen.getByText(/已上傳檔案 \(1\/5\) - transcript/)).toBeInTheDocument();
  });

  it("should show file sizes in appropriate units", () => {
    const files = [
      new File(["a".repeat(500)], "small.pdf", { type: "application/pdf" }),
      new File(["a".repeat(1024 * 1024)], "large.pdf", {
        type: "application/pdf",
      }),
    ];

    render(
      <FileUpload onFilesChange={mockOnFilesChange} initialFiles={files} />
    );

    expect(screen.getByText("500 Bytes")).toBeInTheDocument();
    expect(screen.getByText("1 MB")).toBeInTheDocument();
  });

  it("should allow file removal", () => {
    const initialFiles = [
      new File(["content"], "test.pdf", { type: "application/pdf" }),
    ];

    render(
      <FileUpload
        onFilesChange={mockOnFilesChange}
        initialFiles={initialFiles}
      />
    );

    const { removeButton } = getRowButtons();
    fireEvent.click(removeButton);

    expect(mockOnFilesChange).toHaveBeenCalledWith([]);
    expect(screen.queryByText("test.pdf")).not.toBeInTheDocument();
  });

  it("should simulate upload progress to completion for new files", () => {
    jest.useFakeTimers();
    // Deterministic progress increments (memory: no flaky randomness)
    const randomSpy = jest.spyOn(Math, "random").mockReturnValue(0.5);

    try {
      const { container } = render(
        <FileUpload
          onFilesChange={mockOnFilesChange}
          initialFiles={STABLE_EMPTY_FILES}
        />
      );

      const file = new File(["content"], "test.pdf", {
        type: "application/pdf",
      });
      selectFiles(getFileInput(container), [file]);

      // Progress ticks every 200ms (+15 with mocked random); finish it
      act(() => {
        jest.advanceTimersByTime(2000);
      });

      expect(screen.getByText("完成")).toBeInTheDocument();
    } finally {
      randomSpy.mockRestore();
      jest.useRealTimers();
    }
  });

  it("should mark previously-uploaded files instead of re-uploading", () => {
    const uploadedFile = new File(["content"], "uploaded.pdf", {
      type: "application/pdf",
    });
    // Server metadata attached by the caller for restored uploads
    Object.assign(uploadedFile, {
      id: "file123",
      file_path: "/uploads/file.pdf",
      originalSize: 2048,
    });

    render(
      <FileUpload
        onFilesChange={mockOnFilesChange}
        initialFiles={[uploadedFile]}
      />
    );

    expect(screen.getByText("uploaded.pdf")).toBeInTheDocument();
    // Uploaded marker + "exists" badge
    expect(screen.getByText("已上傳")).toBeInTheDocument();
    expect(screen.getByText("已存在")).toBeInTheDocument();
    // Shows the server-side original size, not the local blob size
    expect(screen.getByText(/2 KB/)).toBeInTheDocument();
  });

  it("should open the preview dialog with an object URL for a local file", () => {
    const initialFiles = [
      new File(["content"], "test.pdf", { type: "application/pdf" }),
    ];

    render(
      <FileUpload
        onFilesChange={mockOnFilesChange}
        initialFiles={initialFiles}
      />
    );

    const { previewButton } = getRowButtons();
    fireEvent.click(previewButton);

    expect(screen.getByTestId("file-preview-dialog")).toBeInTheDocument();
    expect(screen.getByText("Preview: test.pdf")).toBeInTheDocument();
    expect(screen.getByText("Type: application/pdf")).toBeInTheDocument();
    expect(screen.getByText("URL: blob:mock-object-url")).toBeInTheDocument();
  });

  it("should prefer the server url for previously-uploaded files in preview", () => {
    const uploadedFile = new File(["content"], "photo.png", {
      type: "image/png",
    });
    Object.assign(uploadedFile, {
      id: "file456",
      url: "/api/v1/preview/documents/456",
    });

    render(
      <FileUpload
        onFilesChange={mockOnFilesChange}
        initialFiles={[uploadedFile]}
      />
    );

    const { previewButton } = getRowButtons();
    fireEvent.click(previewButton);

    expect(screen.getByText("Type: image")).toBeInTheDocument();
    expect(
      screen.getByText("URL: /api/v1/preview/documents/456")
    ).toBeInTheDocument();
    expect(global.URL.createObjectURL).not.toHaveBeenCalled();
  });

  it("should not open preview for a restored entry with no previewable source", () => {
    // A restored uploaded entry is a plain object, not a real Blob, and has
    // neither a same-origin url nor file_path — preview must be a no-op
    // (PR #885/#892 contract in lib/file-preview).
    const restoredEntry = {
      id: "file789",
      name: "ghost.pdf",
      size: 100,
    } as unknown as File;

    render(
      <FileUpload
        onFilesChange={mockOnFilesChange}
        initialFiles={[restoredEntry]}
      />
    );

    const { previewButton } = getRowButtons();
    fireEvent.click(previewButton);

    expect(
      screen.queryByTestId("file-preview-dialog")
    ).not.toBeInTheDocument();
  });

  it("should close the preview dialog", () => {
    const initialFiles = [
      new File(["content"], "test.pdf", { type: "application/pdf" }),
    ];

    render(
      <FileUpload
        onFilesChange={mockOnFilesChange}
        initialFiles={initialFiles}
      />
    );

    const { previewButton } = getRowButtons();
    fireEvent.click(previewButton);
    expect(screen.getByTestId("file-preview-dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Close Preview"));
    expect(
      screen.queryByTestId("file-preview-dialog")
    ).not.toBeInTheDocument();
  });

  it("should append newly selected files to existing ones", () => {
    const first = new File(["1"], "first.pdf", { type: "application/pdf" });
    const second = new File(["2"], "second.pdf", { type: "application/pdf" });

    const { container } = render(
      <FileUpload onFilesChange={mockOnFilesChange} initialFiles={[first]} />
    );

    selectFiles(getFileInput(container), [second]);

    expect(mockOnFilesChange).toHaveBeenCalledWith([first, second]);
    expect(screen.getByText("first.pdf")).toBeInTheDocument();
    expect(screen.getByText("second.pdf")).toBeInTheDocument();
  });

  it("should generate distinct input ids for concurrent instances", () => {
    const { container } = render(
      <div>
        <FileUpload onFilesChange={mockOnFilesChange} fileType="a" />
        <FileUpload onFilesChange={mockOnFilesChange} fileType="a" />
      </div>
    );

    const inputs = container.querySelectorAll('input[type="file"]');
    expect(inputs).toHaveLength(2);
    expect(inputs[0].id).toBeTruthy();
    expect(inputs[1].id).toBeTruthy();
    expect(inputs[0].id).not.toBe(inputs[1].id);
  });
});
