import {
  buildExampleDocumentPreview,
  exampleDocumentFilename,
} from "../example-document-preview";

describe("exampleDocumentFilename", () => {
  it("mirrors the backend Content-Disposition name <document_name>_example.<ext>", () => {
    expect(
      exampleDocumentFilename({
        id: 1,
        document_name: "成績單",
        example_file_url: "examples/document_1_20260902.PDF",
      })
    ).toBe("成績單_example.pdf");
  });

  it("does not treat a dotless object name's path as an extension", () => {
    expect(
      exampleDocumentFilename({
        id: 1,
        document_name: "成績單",
        example_file_url: "examples/document_12",
      })
    ).toBe("成績單_example");
  });

  it("ignores dots in directory segments", () => {
    expect(
      exampleDocumentFilename({
        id: 1,
        document_name: "成績單",
        example_file_url: "v1.2/examples/document_12",
      })
    ).toBe("成績單_example");
  });
});

describe("buildExampleDocumentPreview", () => {
  beforeEach(() => localStorage.setItem("auth_token", "tok"));
  afterEach(() => localStorage.clear());

  it("returns null when the document has no example", () => {
    expect(
      buildExampleDocumentPreview({ id: 4, document_name: "成績單" })
    ).toBeNull();
  });

  it("builds the secure preview URL and a matching mime type", () => {
    const preview = buildExampleDocumentPreview({
      id: 4,
      document_name: "成績單",
      example_file_url: "examples/document_4.png",
    });
    expect(preview).toEqual({
      url: expect.stringContaining("/api/v1/preview/examples?"),
      filename: "成績單_example.png",
      type: "image/png",
    });
    const url = new URL(preview!.url, "http://localhost");
    expect(url.searchParams.get("documentId")).toBe("4");
    expect(url.searchParams.get("token")).toBe("tok");
  });
});
