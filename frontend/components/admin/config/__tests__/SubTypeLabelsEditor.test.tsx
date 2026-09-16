import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { SubTypeLabelsEditor } from "../SubTypeLabelsEditor";
import type { SubTypeLabels } from "@/lib/api/types";

function renderEditor(value: SubTypeLabels | undefined, onChange = jest.fn()) {
  render(<SubTypeLabelsEditor subTypes={["nstc", "moe_1w"]} value={value} onChange={onChange} />);
  return onChange;
}

describe("SubTypeLabelsEditor", () => {
  it("renders one 中文 / English row per sub-type with current overrides", () => {
    renderEditor({ moe_1w: { name: "115學年度教育部", name_en: "AY115 MOE" } });

    expect(screen.getByTestId("sub_type_label-row-nstc")).toBeInTheDocument();
    expect(screen.getByTestId("sub_type_label-row-moe_1w")).toBeInTheDocument();
    expect(screen.getByLabelText("中文名稱", { selector: "#sub_type_label_moe_1w_name" })).toHaveValue(
      "115學年度教育部"
    );
    expect(screen.getByLabelText("英文名稱", { selector: "#sub_type_label_moe_1w_name_en" })).toHaveValue(
      "AY115 MOE"
    );
    expect(screen.getByLabelText("中文名稱", { selector: "#sub_type_label_nstc_name" })).toHaveValue("");
  });

  it("emits a new object with the edited sub-type and keeps the others untouched", () => {
    const initial: SubTypeLabels = { moe_1w: { name: "115學年度教育部" } };
    const onChange = renderEditor(initial);

    fireEvent.change(screen.getByLabelText("中文名稱", { selector: "#sub_type_label_nstc_name" }), {
      target: { value: "115學年度國科會" },
    });

    expect(onChange).toHaveBeenCalledWith({
      moe_1w: { name: "115學年度教育部" },
      nstc: { name: "115學年度國科會" },
    });
    // Immutability: the prop object is not mutated in place.
    expect(initial).toEqual({ moe_1w: { name: "115學年度教育部" } });
  });

  it("removes the override when both inputs of a row are cleared", () => {
    const onChange = renderEditor({ nstc: { name: "115學年度國科會" }, moe_1w: { name: "115學年度教育部" } });

    fireEvent.change(screen.getByLabelText("中文名稱", { selector: "#sub_type_label_nstc_name" }), {
      target: { value: "   " },
    });

    expect(onChange).toHaveBeenCalledWith({ moe_1w: { name: "115學年度教育部" } });
  });

  it("keeps a row whose English name is still filled in", () => {
    const onChange = renderEditor({ nstc: { name: "115學年度國科會", name_en: "AY115 NSTC" } });

    fireEvent.change(screen.getByLabelText("中文名稱", { selector: "#sub_type_label_nstc_name" }), {
      target: { value: "" },
    });

    expect(onChange).toHaveBeenCalledWith({ nstc: { name: "", name_en: "AY115 NSTC" } });
  });

  it("renders nothing when the scholarship defines no sub-types", () => {
    const { container } = render(<SubTypeLabelsEditor subTypes={[]} value={{}} onChange={jest.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});
