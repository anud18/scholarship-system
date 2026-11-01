import React from "react";
import { act, render, screen } from "@testing-library/react";
import { ScholarshipApplicationStep } from "../ScholarshipApplicationStep";
import api from "@/lib/api";
import type { Application, ScholarshipType } from "@/lib/api";

jest.mock("@/hooks/use-applications", () => ({
  useApplications: () => ({
    createApplication: jest.fn(),
    uploadDocument: jest.fn(),
    submitApplication: jest.fn(),
    updateApplication: jest.fn(),
    fetchApplications: jest.fn(),
  }),
}));

jest.mock("@/hooks/use-student-profile", () => ({
  useStudentProfile: () => ({
    profile: null,
    userInfo: null,
    studentInfo: null,
    refresh: jest.fn(),
  }),
}));

afterEach(() => {
  jest.restoreAllMocks();
});

const phdScholarship = (
  overrides: Partial<ScholarshipType> = {}
): ScholarshipType =>
  ({
    id: 1,
    configuration_id: 10,
    code: "phd",
    name: "博士生獎學金",
    name_en: "PhD Scholarship",
    sub_type_selection_mode: "multiple",
    is_application_period: true,
    already_submitted: false,
    all_sub_type_list: ["nstc", "moe_1w"],
    eligible_sub_types: [
      { value: "moe_1w", label: "教育部", label_en: "MOE", is_default: false },
    ],
    closed_sub_types: [{ value: "nstc", label: "國科會", label_en: "NSTC" }],
    passed: [],
    warnings: [],
    errors: [],
    ...overrides,
  }) as unknown as ScholarshipType;

const returnedApplication = {
  id: 7,
  scholarship_type: "phd",
  status: "returned",
  scholarship_subtype_list: ["nstc", "moe_1w"],
  submitted_form_data: { fields: {}, documents: [] },
} as unknown as Application;

async function renderEditing(scholarship: ScholarshipType) {
  jest.spyOn(api.scholarships, "getEligible").mockResolvedValue({
    success: true,
    message: "ok",
    data: [scholarship],
  });
  jest.spyOn(api.applicationFields, "getFormConfig").mockResolvedValue({
    success: true,
    message: "ok",
    data: { scholarship_type: "phd", fields: [], documents: [] },
  } as never);
  await act(async () => {
    render(
      <ScholarshipApplicationStep
        onBack={jest.fn()}
        onComplete={jest.fn()}
        locale="zh"
        userId={1}
        editingApplication={returnedApplication}
      />
    );
  });
}

describe("ScholarshipApplicationStep with sub-types closed this round", () => {
  it("unticks a saved sub-type that is now closed and says why", async () => {
    await renderEditing(phdScholarship());

    expect(
      await screen.findByText("國科會 本次未開放申請，已取消勾選")
    ).toBeInTheDocument();
    expect(screen.getByText("教育部")).toBeInTheDocument();
    expect(screen.queryByText("國科會")).not.toBeInTheDocument();
  });

  it("explains why a returned application can no longer be resubmitted when every qualifying sub-type is closed", async () => {
    await renderEditing(
      phdScholarship({
        eligible_sub_types: [
          {
            value: "general",
            label: "通用",
            label_en: "General",
            is_default: true,
          },
        ],
        closed_sub_types: [
          { value: "nstc", label: "國科會", label_en: "NSTC" },
          { value: "moe_1w", label: "教育部", label_en: "MOE" },
        ],
        errors: [
          {
            rule_id: "sub_types_not_open",
            rule_name: "申請類別未開放",
            rule_type: "open_sub_types",
            tag: "本次未開放申請類別",
            message: "本次未開放您符合資格的申請類別",
            sub_type: null,
          },
        ],
      } as unknown as Partial<ScholarshipType>)
    );

    expect(
      await screen.findByText("本次未開放您符合資格的申請類別")
    ).toBeInTheDocument();
  });
});
