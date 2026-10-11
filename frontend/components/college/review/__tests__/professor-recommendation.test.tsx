import { render, screen } from "@testing-library/react";

import { ProfessorRecommendation } from "../application-summary-fields";

const names: Record<string, string> = {
  moe_1w: "115學年度教育部博士生獎學金 (指導教授配合款每月 $5000 元)",
  nstc: "國科會博士生獎學金",
};
const getSubTypeName = (code: string | undefined) =>
  (code && names[code]) || code || "-";

describe("ProfessorRecommendation", () => {
  it("puts a bracketed note and the verdict on a second line", () => {
    render(
      <ProfessorRecommendation
        app={{
          professor_review_items: [
            { sub_type_code: "moe_1w", recommendation: "approve" },
          ],
        }}
        locale="zh"
        getSubTypeName={getSubTypeName}
      />
    );

    expect(screen.getByText("115學年度教育部博士生獎學金")).toBeInTheDocument();
    expect(
      screen.getByText("(指導教授配合款每月 $5000 元): 推薦")
    ).toBeInTheDocument();
  });

  it("keeps a label without a note on one line", () => {
    render(
      <ProfessorRecommendation
        app={{
          professor_review_items: [
            { sub_type_code: "nstc", recommendation: "reject" },
          ],
        }}
        locale="zh"
        getSubTypeName={getSubTypeName}
      />
    );

    expect(screen.getByText("國科會博士生獎學金: 不推薦")).toBeInTheDocument();
  });

  it("shows 教授審核中 when a required professor review is missing", () => {
    render(
      <ProfessorRecommendation
        app={{
          professor_review_items: [],
          requires_professor_recommendation: true,
        }}
        locale="zh"
        getSubTypeName={getSubTypeName}
      />
    );

    expect(screen.getByText("教授審核中")).toBeInTheDocument();
  });
});
