"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AlertCircle, CheckCircle, XCircle } from "lucide-react";

/** One evaluated rule from rule_validation_result.details (rule_<id> keys). */
export interface RuleComparisonEntry {
  passed: boolean;
  rule_name: string;
  rule_type?: string;
  actual_value?: unknown;
  expected_value?: string | null;
  operator?: string;
  message?: string;
  is_hard_rule?: boolean;
  is_warning?: boolean;
  error?: string;
}

/** Generation-time validation snapshot stored on each roster item. */
export interface RuleValidationResult {
  is_eligible?: boolean;
  failed_rules?: string[];
  warning_rules?: string[];
  details?: Record<string, unknown>;
}

export interface EligibilityDetailItem {
  student_name: string;
  student_id?: string;
  is_eligible?: boolean;
  failed_rules?: string[];
  warning_rules?: string[];
  verification_message?: string | null;
  rule_validation_result?: RuleValidationResult | null;
}

interface EligibilityDetailDialogProps {
  item: EligibilityDetailItem | null;
  onClose: () => void;
}

const OPERATOR_LABELS: Record<string, string> = {
  ">=": "≥",
  "<=": "≤",
  ">": ">",
  "<": "<",
  "==": "等於",
  "!=": "不等於",
  in: "屬於",
  not_in: "不屬於",
  contains: "包含",
  not_contains: "不包含",
};

const isRuleEntry = (value: unknown): value is RuleComparisonEntry =>
  typeof value === "object" && value !== null && "rule_name" in value;

const formatValue = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
};

/** 符合資格 badge shared by the roster detail table and this dialog. */
export function EligibilityBadge({ item }: { item: EligibilityDetailItem }) {
  if (item.is_eligible === undefined || item.is_eligible === null) {
    return <span className="text-muted-foreground">-</span>;
  }
  if (!item.is_eligible) {
    return (
      <Badge variant="destructive" className="gap-1 no-underline">
        <XCircle className="h-3 w-3" />
        不符合
      </Badge>
    );
  }
  if (item.warning_rules && item.warning_rules.length > 0) {
    return (
      <Badge
        variant="outline"
        className="gap-1 text-yellow-600 border-yellow-600 no-underline"
      >
        <AlertCircle className="h-3 w-3" />
        符合(警告)
      </Badge>
    );
  }
  return (
    <Badge variant="default" className="gap-1 no-underline">
      <CheckCircle className="h-3 w-3" />
      符合
    </Badge>
  );
}

/**
 * Per-student 資格對比 dialog: shows the generation-time snapshot of every
 * evaluated scholarship rule (actual vs expected) plus failed/warning lists.
 */
export function EligibilityDetailDialog({ item, onClose }: EligibilityDetailDialogProps) {
  const ruleEntries = Object.entries(item?.rule_validation_result?.details ?? {})
    .filter((entry): entry is [string, RuleComparisonEntry] => isRuleEntry(entry[1]));
  const hasNoRules = item?.rule_validation_result?.details?.no_rules_found === true;

  return (
    <Dialog open={!!item} onOpenChange={open => !open && onClose()}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>資格對比結果 - {item?.student_name}</DialogTitle>
          <DialogDescription>
            {item?.student_id && <span>學號: {item.student_id}</span>}
            <span className="ml-3">
              造冊產生當下的獎學金規則驗證快照
            </span>
          </DialogDescription>
        </DialogHeader>

        {item && (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">驗證結果:</span>
              <EligibilityBadge item={item} />
            </div>

            {item.failed_rules && item.failed_rules.length > 0 && (
              <div className="p-3 bg-red-50 border border-red-200 rounded">
                <div className="font-semibold text-red-900 text-sm mb-1 flex items-center gap-1">
                  <XCircle className="h-4 w-4" />
                  未通過規則 ({item.failed_rules.length})
                </div>
                <ul className="space-y-1">
                  {item.failed_rules.map((rule, idx) => (
                    <li key={idx} className="text-red-700 text-sm">
                      • {rule}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {item.warning_rules && item.warning_rules.length > 0 && (
              <div className="p-3 bg-yellow-50 border border-yellow-200 rounded">
                <div className="font-semibold text-yellow-900 text-sm mb-1 flex items-center gap-1">
                  <AlertCircle className="h-4 w-4" />
                  警告 ({item.warning_rules.length})
                </div>
                <ul className="space-y-1">
                  {item.warning_rules.map((rule, idx) => (
                    <li key={idx} className="text-yellow-700 text-sm">
                      • {rule}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {item.verification_message && (
              <div className="p-3 bg-blue-50 border border-blue-200 rounded text-sm text-blue-800">
                驗證訊息: {item.verification_message}
              </div>
            )}

            {ruleEntries.length > 0 ? (
              <div>
                <h4 className="text-sm font-semibold mb-2">規則逐項對比</h4>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>規則</TableHead>
                      <TableHead>學生實際值</TableHead>
                      <TableHead>條件</TableHead>
                      <TableHead>要求值</TableHead>
                      <TableHead className="text-right">結果</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {ruleEntries.map(([key, rule]) => (
                      <TableRow key={key}>
                        <TableCell>
                          <div className="font-medium">{rule.rule_name}</div>
                          {rule.message && (
                            <div className="text-xs text-muted-foreground">
                              {rule.message}
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="font-mono text-sm">
                          {formatValue(rule.actual_value)}
                        </TableCell>
                        <TableCell className="text-sm">
                          {rule.operator
                            ? (OPERATOR_LABELS[rule.operator] ?? rule.operator)
                            : "-"}
                        </TableCell>
                        <TableCell className="font-mono text-sm">
                          {formatValue(rule.expected_value)}
                        </TableCell>
                        <TableCell className="text-right">
                          {rule.passed ? (
                            <Badge variant="default" className="gap-1">
                              <CheckCircle className="h-3 w-3" />
                              通過
                            </Badge>
                          ) : rule.is_warning && !rule.is_hard_rule ? (
                            <Badge
                              variant="outline"
                              className="gap-1 text-yellow-600 border-yellow-600"
                            >
                              <AlertCircle className="h-3 w-3" />
                              警告
                            </Badge>
                          ) : (
                            <Badge variant="destructive" className="gap-1">
                              <XCircle className="h-3 w-3" />
                              未通過
                            </Badge>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                {hasNoRules
                  ? "此獎學金於造冊期間無設定驗證規則，視為符合資格。"
                  : "此造冊項目無規則對比快照（較舊造冊或未啟用規則驗證）。"}
              </p>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
