import { calculateFormProgress } from "../application-progress";

const field = (field_name: string, overrides = {}) => ({
  field_name,
  is_active: true,
  is_required: true,
  is_fixed: false,
  ...overrides,
});

const doc = (document_name: string, overrides = {}) => ({
  document_name,
  is_active: true,
  is_required: true,
  ...overrides,
});

const base = {
  fields: [],
  documents: [],
  formData: {},
  fileData: {},
  hasSubTypeChoice: false,
  selectedSubTypeCount: 0,
  isPersonalInfoSaved: true,
};

describe("calculateFormProgress", () => {
  it("is 100% when personal info is saved and nothing else is required", () => {
    expect(calculateFormProgress(base)).toBe(100);
  });

  it("stays below 100% until personal info is saved", () => {
    expect(calculateFormProgress({ ...base, isPersonalInfoSaved: false })).toBe(
      0
    );

    const filled = {
      ...base,
      fields: [field("contact_phone")],
      documents: [doc("transcript")],
      formData: { contact_phone: "0912345678" },
      fileData: { transcript: [{}] },
      hasSubTypeChoice: true,
      selectedSubTypeCount: 1,
    };
    expect(
      calculateFormProgress({ ...filled, isPersonalInfoSaved: false })
    ).toBe(75);
    expect(calculateFormProgress(filled)).toBe(100);
  });

  it("counts only active, required, non-fixed fields", () => {
    const progress = calculateFormProgress({
      ...base,
      fields: [
        field("filled"),
        field("empty"),
        field("optional", { is_required: false }),
        field("inactive", { is_active: false }),
        field("fixed", { is_fixed: true }),
      ],
      formData: { filled: "x", empty: "" },
    });
    // personal info + "filled" of 3 required items
    expect(progress).toBe(67);
  });

  it("treats 0 and false as filled values", () => {
    expect(
      calculateFormProgress({
        ...base,
        fields: [field("count"), field("flag")],
        formData: { count: 0, flag: false },
      })
    ).toBe(100);
  });

  it("counts only documents that require an upload", () => {
    const progress = calculateFormProgress({
      ...base,
      documents: [
        doc("uploaded"),
        doc("missing"),
        doc("no_upload", { requires_upload: false }),
        doc("fixed", { is_fixed: true }),
      ],
      fileData: { uploaded: [{}], missing: [] },
    });
    expect(progress).toBe(67);
  });

  it("requires a sub-type only when the scholarship offers a choice", () => {
    expect(calculateFormProgress({ ...base, hasSubTypeChoice: true })).toBe(50);
    expect(
      calculateFormProgress({
        ...base,
        hasSubTypeChoice: true,
        selectedSubTypeCount: 2,
      })
    ).toBe(100);
  });
});
