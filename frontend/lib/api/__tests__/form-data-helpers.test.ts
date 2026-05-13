/**
 * Tests for `lib/api/form-data-helpers.ts`.
 *
 * These helpers construct FormData for file-upload endpoints. The
 * type system tries to model multipart/form-data via OpenAPI's
 * `format: "binary"`, but at runtime we still need a real FormData.
 *
 * Regression risks:
 * - Skipped File entries → silently lose attachments on upload
 * - String coercion bug → "[object Object]" sent instead of value
 * - undefined/null appended as literal "undefined" → server gets
 *   malformed value
 *
 * 13 cases covering 4 helpers.
 */
import {
  createFileUploadFormData,
  isFormData,
  TypedFormData,
  typedFormData,
} from "../form-data-helpers";

// jsdom provides FormData + File globals — use them directly.

describe("createFileUploadFormData", () => {
  it("returns a FormData instance", () => {
    const file = new File(["content"], "x.pdf", { type: "application/pdf" });
    const fd = createFileUploadFormData({ file });
    expect(fd).toBeInstanceOf(FormData);
  });

  it("appends the file with the 'file' key", () => {
    const file = new File(["x"], "test.pdf");
    const fd = createFileUploadFormData({ file });
    const got = fd.get("file");
    expect(got).toBeInstanceOf(File);
    expect((got as File).name).toBe("test.pdf");
  });

  it("appends additional string fields", () => {
    const file = new File(["x"], "test.pdf");
    const fd = createFileUploadFormData({ file, file_type: "document", category: "transcript" });
    expect(fd.get("file_type")).toBe("document");
    expect(fd.get("category")).toBe("transcript");
  });

  it("appends another File via dynamic key", () => {
    /** A second File under a different key works because the loop
     * handles `value instanceof File` for any iteration. */
    const file1 = new File(["a"], "a.pdf");
    const file2 = new File(["b"], "b.pdf");
    const fd = createFileUploadFormData({ file: file1, attachment: file2 });
    expect((fd.get("attachment") as File).name).toBe("b.pdf");
  });
});

// ─── isFormData ──────────────────────────────────────────────────────

describe("isFormData", () => {
  it("returns true for a FormData instance", () => {
    expect(isFormData(new FormData())).toBe(true);
  });

  it("returns false for plain objects, arrays, primitives", () => {
    expect(isFormData({})).toBe(false);
    expect(isFormData([])).toBe(false);
    expect(isFormData("string")).toBe(false);
    expect(isFormData(42)).toBe(false);
    expect(isFormData(null)).toBe(false);
    expect(isFormData(undefined)).toBe(false);
  });
});

// ─── TypedFormData class ─────────────────────────────────────────────

describe("TypedFormData", () => {
  it("constructs an empty FormData with no initial data", () => {
    const tfd = new TypedFormData();
    expect(tfd.get()).toBeInstanceOf(FormData);
    // Empty.
    const entries = Array.from(tfd.get().entries());
    expect(entries).toHaveLength(0);
  });

  it("constructs from an initial data object", () => {
    const tfd = new TypedFormData({ name: "Alice", age: 30 });
    expect(tfd.get().get("name")).toBe("Alice");
    expect(tfd.get().get("age")).toBe("30"); // coerced to string
  });

  it("append() coerces non-File values to string", () => {
    const tfd = new TypedFormData<{ count: number; name: string }>();
    tfd.append("count", 42);
    tfd.append("name", "Bob");
    expect(tfd.get().get("count")).toBe("42");
    expect(tfd.get().get("name")).toBe("Bob");
  });

  it("append() preserves File and Blob without string coercion", () => {
    /** Critical: File/Blob must NOT be coerced to '[object File]' —
     * the multipart encoding requires the raw binary. */
    const file = new File(["x"], "x.pdf");
    const tfd = new TypedFormData();
    tfd.append("doc" as any, file);
    expect(tfd.get().get("doc")).toBeInstanceOf(File);
  });

  it("append() skips undefined and null (NOT 'undefined'/'null' strings)", () => {
    /** Pin so a refactor doesn't accidentally append literal 'undefined'
     * — server would receive a string 'undefined' and misinterpret. */
    const tfd = new TypedFormData<Record<string, any>>();
    tfd.append("maybe_set", undefined);
    tfd.append("possibly_null", null);
    tfd.append("real", "value");
    expect(tfd.get().get("maybe_set")).toBeNull(); // FormData.get returns null for absent keys
    expect(tfd.get().get("possibly_null")).toBeNull();
    expect(tfd.get().get("real")).toBe("value");
  });

  it("append() chains (returns this)", () => {
    /** Fluent API: chain calls. Pin the return type contract. */
    const tfd = new TypedFormData<{ a: string; b: string }>();
    const result = tfd.append("a", "1").append("b", "2");
    expect(result).toBe(tfd);
  });

  it("asBody() returns the internal FormData (typed)", () => {
    /** asBody is a type assertion — runtime just returns the FormData.
     * Pin so a future refactor doesn't accidentally wrap it. */
    const tfd = new TypedFormData({ k: "v" });
    const body = tfd.asBody();
    expect(body).toBe(tfd.get());
  });
});

// ─── typedFormData (factory) ─────────────────────────────────────────

describe("typedFormData factory", () => {
  it("returns a TypedFormData instance with provided data", () => {
    const tfd = typedFormData({ x: "y" });
    expect(tfd).toBeInstanceOf(TypedFormData);
    expect(tfd.get().get("x")).toBe("y");
  });

  it("returns an empty TypedFormData when called without args", () => {
    const tfd = typedFormData();
    expect(tfd).toBeInstanceOf(TypedFormData);
    expect(Array.from(tfd.get().entries())).toHaveLength(0);
  });
});
