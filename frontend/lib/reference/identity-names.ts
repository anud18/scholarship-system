/**
 * English display names for the `identities` reference table.
 *
 * The table only stores Chinese `name`s, so English UIs translate by that
 * name. Unlisted names fall back to the Chinese name.
 */
export const IDENTITY_NAME_EN: Record<string, string> = {
  一般生: "Regular Student",
  原住民: "Indigenous Student",
  "僑生(目前有中華民國國籍生)":
    "Overseas Chinese Student (Currently holds R.O.C. nationality)",
  "外籍生(目前有中華民國國籍生)":
    "Foreign Student (Currently holds R.O.C. nationality)",
  外交子女: "Diplomat's Child",
  身心障礙生: "Student with Disability",
  運動成績優良甄試學生: "Outstanding Athletic Performance Admission Student",
  離島: "Outlying Islands Student",
  退伍軍人: "Veteran",
  一般公費生: "Regular Government-Funded Student",
  原住民公費生: "Indigenous Government-Funded Student",
  離島公費生: "Outlying Islands Government-Funded Student",
  退伍軍人公費生: "Veteran Government-Funded Student",
  願景計畫生: "Vision Project Student",
  陸生: "Mainland Chinese Student",
  其他: "Other",
};
