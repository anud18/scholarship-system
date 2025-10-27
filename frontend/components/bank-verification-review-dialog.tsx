"use client"

import React, { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { Checkbox } from "@/components/ui/checkbox"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { CheckCircle2, XCircle, AlertTriangle, FileText, Eye } from "lucide-react"
import { apiClient } from "@/lib/api"

interface VerificationFieldData {
  field_name: string
  form_value: string
  ocr_value: string
  similarity_score: number
  is_match: boolean
  confidence: string
  needs_manual_review?: boolean
}

interface BankVerificationData {
  application_id: number
  verification_status: string
  account_number_status?: string
  account_holder_status?: string
  requires_manual_review?: boolean
  comparisons?: {
    account_number?: VerificationFieldData
    account_holder?: VerificationFieldData
  }
  form_data?: { [key: string]: string }
  ocr_data?: { [key: string]: any }
  passbook_document?: {
    file_path: string
    original_filename: string
    file_id?: number
    object_name?: string
  }
  recommendations?: string[]
}

interface BankVerificationReviewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  verificationData: BankVerificationData | null
  onReviewComplete?: () => void
}

export function BankVerificationReviewDialog({
  open,
  onOpenChange,
  verificationData,
  onReviewComplete,
}: BankVerificationReviewDialogProps) {
  // Use undefined as initial state to distinguish from explicitly unchecked (false)
  const [accountNumberApproved, setAccountNumberApproved] = useState<boolean | undefined>(undefined)
  const [accountNumberCorrected, setAccountNumberCorrected] = useState<string>("")
  const [accountHolderApproved, setAccountHolderApproved] = useState<boolean | undefined>(undefined)
  const [accountHolderCorrected, setAccountHolderCorrected] = useState<string>("")
  const [reviewNotes, setReviewNotes] = useState<string>("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!verificationData) return null

  const accountNumberComp = verificationData.comparisons?.account_number
  const accountHolderComp = verificationData.comparisons?.account_holder

  const getStatusBadge = (status?: string) => {
    switch (status) {
      case "verified":
        return (
          <Badge variant="default" className="bg-green-500">
            <CheckCircle2 className="w-3 h-3 mr-1" />
            通過
          </Badge>
        )
      case "needs_review":
        return (
          <Badge variant="default" className="bg-yellow-500">
            <AlertTriangle className="w-3 h-3 mr-1" />
            需人工檢閱
          </Badge>
        )
      case "failed":
        return (
          <Badge variant="destructive">
            <XCircle className="w-3 h-3 mr-1" />
            不通過
          </Badge>
        )
      case "no_data":
        return (
          <Badge variant="secondary">
            缺少資料
          </Badge>
        )
      case "not_reviewed":
        return <Badge variant="outline">未審核</Badge>
      case "unknown":
        return <Badge variant="secondary">未驗證</Badge>
      default:
        return <Badge variant="secondary">未知</Badge>
    }
  }

  const validateAccountNumber = (accountNumber: string): string | null => {
    if (!accountNumber) return null

    // Remove all non-digit characters
    const cleaned = accountNumber.replace(/\D/g, "")

    // Check if exactly 14 digits
    if (cleaned.length !== 14) {
      return `郵局帳號必須為 14 位數字，目前為 ${cleaned.length} 位`
    }

    // Check if all digits
    if (!/^\d+$/.test(cleaned)) {
      return "郵局帳號只能包含數字"
    }

    return null
  }

  const handleSubmit = async () => {
    if (!verificationData) return

    setSubmitting(true)
    setError(null)

    try {
      // Validate account number format if corrected value is provided
      if (accountNumberCorrected.trim()) {
        const validationError = validateAccountNumber(accountNumberCorrected.trim())
        if (validationError) {
          setError(validationError)
          setSubmitting(false)
          return
        }
      }

      const response = await apiClient.bankVerification.submitManualReview({
        application_id: verificationData.application_id,
        // Use nullish coalescing to preserve false values (explicit rejection)
        account_number_approved: accountNumberApproved !== undefined ? accountNumberApproved : undefined,
        account_number_corrected: accountNumberCorrected.trim() || undefined,
        account_holder_approved: accountHolderApproved !== undefined ? accountHolderApproved : undefined,
        account_holder_corrected: accountHolderCorrected.trim() || undefined,
        review_notes: reviewNotes.trim() || undefined,
      })

      if (response.success) {
        onOpenChange(false)
        onReviewComplete?.()
        // Reset form
        setAccountNumberApproved(undefined)
        setAccountNumberCorrected("")
        setAccountHolderApproved(undefined)
        setAccountHolderCorrected("")
        setReviewNotes("")
      } else {
        setError(response.message || "提交審核失敗")
      }
    } catch (err: any) {
      setError(err.message || "提交審核時發生錯誤")
    } finally {
      setSubmitting(false)
    }
  }

  const handleViewDocument = () => {
    if (verificationData.passbook_document?.object_name) {
      // Open document in new tab using Next.js proxy
      const token = localStorage.getItem("access_token")
      window.open(
        `/api/proxy/files/${verificationData.passbook_document.object_name}?token=${token}`,
        "_blank"
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>銀行帳號人工檢閱</DialogTitle>
          <DialogDescription>
            請檢閱 OCR 辨識結果與表單資料是否一致，並決定是否核准或修正
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Error Alert */}
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Document Preview */}
          {verificationData.passbook_document && (
            <div className="border rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <FileText className="w-5 h-5 text-blue-500" />
                  <span className="font-medium">存摺封面</span>
                </div>
                <Button variant="outline" size="sm" onClick={handleViewDocument}>
                  <Eye className="w-4 h-4 mr-1" />
                  查看檔案
                </Button>
              </div>
              <p className="text-sm text-gray-600">
                {verificationData.passbook_document.original_filename}
              </p>
            </div>
          )}

          {/* Account Number Verification */}
          {accountNumberComp && (
            <div className="border rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-lg">郵局帳號</h3>
                {getStatusBadge(verificationData.account_number_status)}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-sm text-gray-600">表單填寫</Label>
                  <p className="font-mono text-lg">{accountNumberComp.form_value || "-"}</p>
                </div>
                <div>
                  <Label className="text-sm text-gray-600">OCR 辨識</Label>
                  <p className="font-mono text-lg">{accountNumberComp.ocr_value || "-"}</p>
                </div>
              </div>

              <div className="flex items-center gap-4 text-sm">
                <span>相似度: {(accountNumberComp.similarity_score * 100).toFixed(1)}%</span>
                <span>信心度: {accountNumberComp.confidence}</span>
              </div>

              {accountNumberComp.needs_manual_review && (
                <div className="space-y-3 pt-3 border-t">
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="account-number-approved"
                      checked={accountNumberApproved === true}
                      onCheckedChange={(checked) => setAccountNumberApproved(typeof checked === 'boolean' ? checked : undefined)}
                    />
                    <label
                      htmlFor="account-number-approved"
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                    >
                      核准帳號 (確認資料正確)
                    </label>
                  </div>

                  <div>
                    <Label htmlFor="account-number-corrected">修正帳號 (如需修正)</Label>
                    <Input
                      id="account-number-corrected"
                      value={accountNumberCorrected}
                      onChange={(e) => setAccountNumberCorrected(e.target.value)}
                      placeholder="輸入正確的帳號"
                      className="font-mono"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Account Holder Verification */}
          {accountHolderComp && (
            <div className="border rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-lg">戶名</h3>
                {getStatusBadge(verificationData.account_holder_status)}
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-sm text-gray-600">表單填寫</Label>
                  <p className="font-mono text-lg">{accountHolderComp.form_value || "-"}</p>
                </div>
                <div>
                  <Label className="text-sm text-gray-600">OCR 辨識</Label>
                  <p className="font-mono text-lg">{accountHolderComp.ocr_value || "-"}</p>
                </div>
              </div>

              <div className="flex items-center gap-4 text-sm">
                <span>相似度: {(accountHolderComp.similarity_score * 100).toFixed(1)}%</span>
                <span>信心度: {accountHolderComp.confidence}</span>
              </div>

              {accountHolderComp.needs_manual_review && (
                <div className="space-y-3 pt-3 border-t">
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="account-holder-approved"
                      checked={accountHolderApproved === true}
                      onCheckedChange={(checked) => setAccountHolderApproved(typeof checked === 'boolean' ? checked : undefined)}
                    />
                    <label
                      htmlFor="account-holder-approved"
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                    >
                      核准戶名 (確認資料正確)
                    </label>
                  </div>

                  <div>
                    <Label htmlFor="account-holder-corrected">修正戶名 (如需修正)</Label>
                    <Input
                      id="account-holder-corrected"
                      value={accountHolderCorrected}
                      onChange={(e) => setAccountHolderCorrected(e.target.value)}
                      placeholder="輸入正確的戶名"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Recommendations */}
          {verificationData.recommendations && verificationData.recommendations.length > 0 && (
            <div className="border rounded-lg p-4">
              <h3 className="font-semibold mb-2">建議</h3>
              <ul className="space-y-1">
                {verificationData.recommendations.map((rec, idx) => (
                  <li key={idx} className="text-sm">
                    {rec}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Review Notes */}
          <div>
            <Label htmlFor="review-notes">審核備註</Label>
            <Textarea
              id="review-notes"
              value={reviewNotes}
              onChange={(e) => setReviewNotes(e.target.value)}
              placeholder="輸入審核備註 (選填)"
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? "提交中..." : "提交審核"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
