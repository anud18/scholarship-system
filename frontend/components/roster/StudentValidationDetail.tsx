"use client"

import { AlertCircle, AlertTriangle, XCircle, CheckCircle, ChevronDown } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"
import { useState } from "react"

interface StudentValidationDetailProps {
  student: {
    is_included: boolean
    exclusion_reason: string | null
    verification_status: string
    verification_message: string | null
    is_eligible: boolean
    failed_rules: string[]
    warning_rules: string[]
    has_bank_account: boolean
    bank_account_field: string | null
  }
}

export function StudentValidationDetail({ student }: StudentValidationDetailProps) {
  const [isOpen, setIsOpen] = useState(false)

  // Determine if there are any details to show
  const hasDetails =
    !student.is_included ||
    (student.warning_rules && student.warning_rules.length > 0) ||
    (student.failed_rules && student.failed_rules.length > 0) ||
    !student.has_bank_account ||
    student.verification_message

  if (!hasDetails) {
    return (
      <Badge variant="default" className="gap-1">
        <CheckCircle className="h-3 w-3" />
        符合條件
      </Badge>
    )
  }

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="w-full">
      <div className="flex items-center gap-2 whitespace-nowrap overflow-x-auto">
        {/* Primary Status Badge */}
        {student.is_included ? (
          <Badge variant="default" className="gap-1">
            <CheckCircle className="h-3 w-3" />
            符合條件
          </Badge>
        ) : (
          <Badge variant="destructive" className="gap-1">
            <XCircle className="h-3 w-3" />
            已排除
          </Badge>
        )}

        {/* Warning Indicators */}
        {!student.has_bank_account && (
          <Badge variant="outline" className="gap-1 text-orange-600 border-orange-600">
            <AlertTriangle className="h-3 w-3" />
            缺銀行帳戶
          </Badge>
        )}

        {student.warning_rules && student.warning_rules.length > 0 && (
          <Badge variant="outline" className="gap-1 text-yellow-600 border-yellow-600">
            <AlertCircle className="h-3 w-3" />
            {student.warning_rules.length} 個警告
          </Badge>
        )}

        {student.failed_rules && student.failed_rules.length > 0 && (
          <Badge variant="outline" className="gap-1 text-red-600 border-red-600">
            <XCircle className="h-3 w-3" />
            {student.failed_rules.length} 個失敗
          </Badge>
        )}

        {/* Expand/Collapse Trigger */}
        <CollapsibleTrigger asChild>
          <button
            className="p-1 hover:bg-gray-100 rounded-md transition-colors"
            aria-label={isOpen ? "收起詳細資訊" : "展開詳細資訊"}
          >
            <ChevronDown
              className={cn(
                "h-4 w-4 text-gray-500 transition-transform duration-200",
                isOpen && "rotate-180"
              )}
            />
          </button>
        </CollapsibleTrigger>
      </div>

      {/* Expandable Details */}
      <CollapsibleContent className="mt-3">
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 space-y-3 text-sm">
          {/* Exclusion Reason */}
          {!student.is_included && student.exclusion_reason && (
            <div className="flex items-start gap-2 p-2 bg-red-50 border border-red-200 rounded">
              <XCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold text-red-900 text-xs mb-1">排除原因</div>
                <div className="text-red-700 text-xs">{student.exclusion_reason}</div>
              </div>
            </div>
          )}

          {/* Failed Rules */}
          {student.failed_rules && student.failed_rules.length > 0 && (
            <div className="flex items-start gap-2 p-2 bg-red-50 border border-red-200 rounded">
              <XCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="font-semibold text-red-900 text-xs mb-1">
                  驗證失敗 ({student.failed_rules.length})
                </div>
                <ul className="space-y-1">
                  {student.failed_rules.map((rule, idx) => (
                    <li key={idx} className="text-red-700 text-xs flex items-start gap-1">
                      <span className="text-red-400">•</span>
                      <span>{rule}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Warning Rules */}
          {student.warning_rules && student.warning_rules.length > 0 && (
            <div className="flex items-start gap-2 p-2 bg-yellow-50 border border-yellow-200 rounded">
              <AlertCircle className="h-4 w-4 text-yellow-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <div className="font-semibold text-yellow-900 text-xs mb-1">
                  警告 ({student.warning_rules.length})
                </div>
                <ul className="space-y-1">
                  {student.warning_rules.map((rule, idx) => (
                    <li key={idx} className="text-yellow-700 text-xs flex items-start gap-1">
                      <span className="text-yellow-400">•</span>
                      <span>{rule}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          {/* Bank Account Missing */}
          {!student.has_bank_account && (
            <div className="flex items-start gap-2 p-2 bg-orange-50 border border-orange-200 rounded">
              <AlertTriangle className="h-4 w-4 text-orange-600 shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold text-orange-900 text-xs mb-1">銀行帳戶資訊</div>
                <div className="text-orange-700 text-xs">
                  學生尚未填寫銀行帳戶資訊
                  {student.bank_account_field && (
                    <span className="block mt-1 text-orange-600">
                      欄位名稱: {student.bank_account_field}
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Verification Message */}
          {student.verification_message && (
            <div className="flex items-start gap-2 p-2 bg-blue-50 border border-blue-200 rounded">
              <AlertCircle className="h-4 w-4 text-blue-600 shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold text-blue-900 text-xs mb-1">驗證訊息</div>
                <div className="text-blue-700 text-xs">{student.verification_message}</div>
              </div>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
