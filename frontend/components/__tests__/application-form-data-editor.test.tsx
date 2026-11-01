import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import api from "@/lib/api";
import type { Application, ApplicationField } from "@/lib/api";
import { ApplicationFormDataEditor } from "../application-form-data-editor";

const field = (overrides: Partial<ApplicationField>): ApplicationField =>
  ({
    id: 1,
    scholarship_type: "phd",
    field_name: "field",
    field_label: "欄位",
    field_type: "text",
    is_required: false,
    display_order: 0,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  }) as ApplicationField;

const FIELDS = [
  field({ field_name: "contact_phone", field_label: "聯絡電話", is_required: true }),
  field({ field_name: "remark", field_label: "備註", field_type: "textarea" }),
  field({ field_name: "household_size", field_label: "家庭人數", field_type: "number" }),
];

const INITIAL = { contact_phone: "0912345678", remark: "舊備註", household_size: 3 };

const renderEditor = (onSaved = jest.fn()) =>
  render(
    <ApplicationFormDataEditor
      applicationId={42}
      fields={FIELDS}
      initialValues={INITIAL}
      locale="zh"
      onSaved={onSaved}
      onCancel={jest.fn()}
    />
  );

describe("ApplicationFormDataEditor", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("keeps 儲存 disabled until a value changes", async () => {
    const user = userEvent.setup();
    renderEditor();

    const save = screen.getByRole("button", { name: "儲存" });
    expect(save).toBeDisabled();

    const remark = screen.getByLabelText("備註");
    await user.type(remark, "!");
    expect(save).toBeEnabled();

    await user.type(remark, "{backspace}");
    expect(save).toBeDisabled();
  });

  it("sends only the changed field and hands back the updated application", async () => {
    const updated = { id: 42, app_id: "APP-114-1-00042" } as unknown as Application;
    const updateFormFields = jest
      .spyOn(api.applications, "updateFormFields")
      .mockResolvedValue({ success: true, message: "表單內容已更新", data: updated });
    const onSaved = jest.fn();
    const user = userEvent.setup();
    renderEditor(onSaved);

    const householdSize = screen.getByLabelText("家庭人數");
    await user.clear(householdSize);
    await user.type(householdSize, "5");
    await user.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(updated));
    expect(updateFormFields).toHaveBeenCalledTimes(1);
    expect(updateFormFields).toHaveBeenCalledWith(42, { household_size: 5 });
  });

  it("shows the backend's message when the save is rejected", async () => {
    jest.spyOn(api.applications, "updateFormFields").mockResolvedValue({
      success: false,
      message: "「備註」不可超過 10 字",
      data: undefined,
    });
    const onSaved = jest.fn();
    const user = userEvent.setup();
    renderEditor(onSaved);

    await user.type(screen.getByLabelText("備註"), "很長的補充");
    await user.click(screen.getByRole("button", { name: "儲存" }));

    expect(await screen.findByText("「備註」不可超過 10 字")).toBeInTheDocument();
    expect(onSaved).not.toHaveBeenCalled();
  });

  it("blocks an invalid contact phone before it reaches the backend", async () => {
    const updateFormFields = jest.spyOn(api.applications, "updateFormFields");
    const user = userEvent.setup();
    renderEditor();

    const phone = screen.getByLabelText(/聯絡電話/);
    await user.clear(phone);
    await user.type(phone, "12345");

    expect(screen.getByText("請輸入本人有效的台灣手機 (09xxxxxx)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "儲存" })).toBeDisabled();
    expect(updateFormFields).not.toHaveBeenCalled();
  });
});
