/**
 * Scholarship rule operators — single source for the rule editor select
 * (scholarship-rule-modal) and rule-comparison displays
 * (EligibilityDetailDialog). Values match backend
 * RosterService._evaluate_condition.
 */
export const RULE_OPERATORS = [
  { value: "==", label: "等於 (==)" },
  { value: "!=", label: "不等於 (!=)" },
  { value: ">", label: "大於 (>)" },
  { value: "<", label: "小於 (<)" },
  { value: ">=", label: "大於等於 (>=)" },
  { value: "<=", label: "小於等於 (<=)" },
  { value: "in", label: "包含於 (in)" },
  { value: "not_in", label: "不包含於 (not_in)" },
  { value: "contains", label: "包含 (contains)" },
  { value: "not_contains", label: "不包含 (not_contains)" },
] as const;

export const RULE_OPERATOR_LABELS: Record<string, string> = Object.fromEntries(
  RULE_OPERATORS.map(op => [op.value, op.label])
);
