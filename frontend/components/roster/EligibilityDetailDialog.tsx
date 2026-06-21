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
import { formatDisplayValue } from "@/lib/utils/application-helpers";
import { RULE_OPERATOR_LABELS } from "@/lib/constants/rule-operators";

/** One evaluated rule from rule_validation_result.details (rule_<id> keys). */
export interface RuleComparisonEntry {
  passed: boolean;
  rule_name: string;
  actual_value?: unknown;
  expected_value?: string | null;
  operator?: string;
  message?: string;
  is_hard_rule?: boolean;
  is_warning?: boolean;
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
  is_eligible?: boolean | null;
  verification_message?: string | null;
  rule_validation_result?: RuleValidationResult | null;
  /** 累計已領月份數（含本期）；null/undefined = 無資料 */
  received_months?: number | null;
}

interface EligibilityDetailDialogProps {
  item: EligibilityDetailItem | null;
  onClose: () => void;
}

const isRuleEntry = (value: unknown): value is RuleComparisonEntry =>
  typeof value === "object" && value !== null && "rule_name" in value;

const formatValue = (value: unknown): string => formatDisplayValue(value) || "-";

type StatusTone = "pass" | "warn" | "fail";

const STATUS_TONES: Record<
  StatusTone,
  { variant: "default" | "outline" | "destructive"; className?: string; Icon: typeof CheckCircle }
> = {
  pass: { variant: "default", Icon: CheckCircle },
  warn: { variant: "outline", className: "text-yellow-600 border-yellow-600", Icon: AlertCircle },
  fail: { variant: "destructive", Icon: XCircle },
};

function StatusBadge({ tone, label }: { tone: StatusTone; label: string }) {
  const { variant, className, Icon } = STATUS_TONES[tone];
  return (
    <Badge variant={variant} className={`gap-1 no-underline ${className ?? ""}`}>
      <Icon className="h-3 w-3" />
      {label}
    </Badge>
  );
}

/** 符合資格 badge shared by the roster detail table and this dialog. */
export function EligibilityBadge({ item }: { item: EligibilityDetailItem }) {
  if (item.is_eligible === undefined || item.is_eligible === null) {
    return <span className="text-muted-foreground">-</span>;
  }
  if (!item.is_eligible) {
    return <StatusBadge tone="fail" label="不符合" />;
  }
  if (item.rule_validation_result?.warning_rules?.length) {
    return <StatusBadge tone="warn" label="符合(警告)" />;
  }
  return <StatusBadge tone="pass" label="符合" />;
}

const RULE_LIST_TONES = {
  fail: {
    box: "bg-red-50 border-red-200",
    header: "text-red-900",
    item: "text-red-700",
    Icon: XCircle,
  },
  warn: {
    box: "bg-yellow-50 border-yellow-200",
    header: "text-yellow-900",
    item: "text-yellow-700",
    Icon: AlertCircle,
  },
} as const;

function RuleList({
  rules,
  label,
  tone,
}: {
  rules: string[] | undefined;
  label: string;
  tone: keyof typeof RULE_LIST_TONES;
}) {
  if (!rules || rules.length === 0) return null;
  const { box, header, item, Icon } = RULE_LIST_TONES[tone];
  return (
    <div className={`p-3 border rounded ${box}`}>
      <div className={`font-semibold text-sm mb-1 flex items-center gap-1 ${header}`}>
        <Icon className="h-4 w-4" />
        {label} ({rules.length})
      </div>
      <ul className="space-y-1">
        {rules.map((rule, idx) => (
          <li key={idx} className={`text-sm ${item}`}>
            • {rule}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Per-student 資格對比 dialog: shows the generation-time snapshot of every
 * evaluated scholarship rule (actual vs expected) plus failed/warning lists.
 */
export function EligibilityDetailDialog({ item, onClose }: EligibilityDetailDialogProps) {
  if (!item) return null;

  const snapshot = item.rule_validation_result;
  const ruleEntries = Object.entries(snapshot?.details ?? {}).filter(
    (entry): entry is [string, RuleComparisonEntry] => isRuleEntry(entry[1])
  );
  const hasNoRules = snapshot?.details?.no_rules_found === true;

  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>資格對比結果 - {item.student_name}</DialogTitle>
          <DialogDescription>
            {item.student_id && <span>學號: {item.student_id}</span>}
            <span className="ml-3">造冊產生當下的獎學金規則驗證快照</span>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">驗證結果:</span>
              <EligibilityBadge item={item} />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">已領月份數:</span>
              <span className="text-sm font-medium">
                {item.received_months != null ? `${item.received_months} 個月` : "-"}
              </span>
            </div>
          </div>

          <RuleList rules={snapshot?.failed_rules} label="未通過規則" tone="fail" />
          <RuleList rules={snapshot?.warning_rules} label="警告" tone="warn" />

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
                          <div className="text-xs text-muted-foreground">{rule.message}</div>
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-sm">
                        {formatValue(rule.actual_value)}
                      </TableCell>
                      <TableCell className="text-sm">
                        {rule.operator
                          ? (RULE_OPERATOR_LABELS[rule.operator] ?? rule.operator)
                          : "-"}
                      </TableCell>
                      <TableCell className="font-mono text-sm">
                        {formatValue(rule.expected_value)}
                      </TableCell>
                      <TableCell className="text-right">
                        {rule.passed ? (
                          <StatusBadge tone="pass" label="通過" />
                        ) : rule.is_warning && !rule.is_hard_rule ? (
                          <StatusBadge tone="warn" label="警告" />
                        ) : (
                          <StatusBadge tone="fail" label="未通過" />
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
      </DialogContent>
    </Dialog>
  );
}
