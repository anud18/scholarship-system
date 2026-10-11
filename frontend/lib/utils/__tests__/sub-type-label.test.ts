import { splitSubTypeLabel } from "../sub-type-label";

describe("splitSubTypeLabel", () => {
  it("moves a half-width bracketed note to its own part", () => {
    expect(
      splitSubTypeLabel("115學年度教育部博士生獎學金 (指導教授配合款每月 $5000 元)")
    ).toEqual(["115學年度教育部博士生獎學金", "(指導教授配合款每月 $5000 元)"]);
  });

  it("handles a full-width bracket without a leading space", () => {
    expect(splitSubTypeLabel("國科會博士生獎學金（每月 $40000 元）")).toEqual([
      "國科會博士生獎學金",
      "（每月 $40000 元）",
    ]);
  });

  it("splits only at the first bracket", () => {
    expect(splitSubTypeLabel("A (b) (c)")).toEqual(["A", "(b) (c)"]);
  });

  it("returns the label whole when there is no bracket", () => {
    expect(splitSubTypeLabel("nstc")).toEqual(["nstc", null]);
  });

  it("returns the label whole when it starts with a bracket", () => {
    expect(splitSubTypeLabel("(only note)")).toEqual(["(only note)", null]);
    expect(splitSubTypeLabel("  (only note)")).toEqual(["  (only note)", null]);
  });
});
