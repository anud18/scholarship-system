/**
 * Unit tests for resolveFilePreviewUrl — the preview-URL preference logic
 * extracted from FileUpload (PR #885 / #892).
 *
 * Pins:
 * - url > same-origin file_path > object URL > undefined.
 * - a cross-origin absolute file_path (e.g. http://localhost:8000 on staging)
 *   or a bare filename is NOT used as an iframe src.
 * - a restored non-Blob entry with no usable URL returns undefined and does NOT
 *   call URL.createObjectURL (the #892 crash guard).
 */
import { resolveFilePreviewUrl, isUploadedFileLike } from "@/lib/file-preview";

const ORIGIN = "https://ss.test.nycu.edu.tw";

describe("resolveFilePreviewUrl", () => {
  beforeEach(() => {
    (global.URL.createObjectURL as unknown) = jest.fn(() => "blob:mock");
  });

  it("prefers a caller-set url over file_path", () => {
    const f = {
      id: 1,
      url: "/api/v1/preview?fileId=1",
      file_path: "http://localhost:8000/api/v1/files/1",
    } as unknown as File;
    expect(resolveFilePreviewUrl(f, ORIGIN)).toBe("/api/v1/preview?fileId=1");
    expect(global.URL.createObjectURL).not.toHaveBeenCalled();
  });

  it("uses a relative file_path", () => {
    const f = { id: 1, file_path: "/api/v1/files/applications/1/files/2" } as unknown as File;
    expect(resolveFilePreviewUrl(f, ORIGIN)).toBe("/api/v1/files/applications/1/files/2");
  });

  it("uses a same-origin absolute file_path", () => {
    const f = { id: 1, file_path: `${ORIGIN}/api/v1/files/x` } as unknown as File;
    expect(resolveFilePreviewUrl(f, ORIGIN)).toBe(`${ORIGIN}/api/v1/files/x`);
  });

  it("returns undefined for a cross-origin file_path on a non-Blob restored entry (no crash)", () => {
    const f = { id: 1, file_path: "http://localhost:8000/api/v1/files/x" } as unknown as File;
    expect(resolveFilePreviewUrl(f, ORIGIN)).toBeUndefined();
    expect(global.URL.createObjectURL).not.toHaveBeenCalled();
  });

  it("returns undefined for a bare-filename file_path on a non-Blob restored entry", () => {
    const f = { id: 1, file_path: "Screenshot.png" } as unknown as File;
    expect(resolveFilePreviewUrl(f, ORIGIN)).toBeUndefined();
    expect(global.URL.createObjectURL).not.toHaveBeenCalled();
  });

  it("creates an object URL for a real local File", () => {
    const f = new File(["x"], "a.pdf", { type: "application/pdf" });
    expect(resolveFilePreviewUrl(f, ORIGIN)).toBe("blob:mock");
    expect(global.URL.createObjectURL).toHaveBeenCalledTimes(1);
  });
});

describe("isUploadedFileLike", () => {
  it("detects id / url / file_path", () => {
    expect(isUploadedFileLike({ id: 1 })).toBe(true);
    expect(isUploadedFileLike({ url: "/x" })).toBe(true);
    expect(isUploadedFileLike({ file_path: "/x" })).toBe(true);
  });

  it("is false for a plain local File and nullish input", () => {
    expect(isUploadedFileLike(new File(["x"], "a.pdf"))).toBe(false);
    expect(isUploadedFileLike(null)).toBe(false);
    expect(isUploadedFileLike(undefined)).toBe(false);
  });
});
