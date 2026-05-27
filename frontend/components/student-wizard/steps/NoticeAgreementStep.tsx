"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertCircle,
  CheckCircle,
  FileText,
  AlertTriangle,
  ChevronRight,
  BookOpen,
} from "lucide-react";
import { api } from "@/lib/api";
import { buildFileProxyUrl } from "@/lib/api/modules/system-settings";
import { previewMimeType } from "@/lib/utils";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import { InlinePdfViewer } from "@/components/inline-pdf-viewer";

interface NoticeAgreementStepProps {
  agreedToTerms: boolean;
  onAgree: (agreed: boolean) => void;
  onNext: () => void;
  locale: "zh" | "en";
}

// Static locale copy hoisted to module scope so the ~140-line object isn't
// reallocated on every render.
const NOTICES = {
  zh: {
    title: "獎學金申請注意事項",
    subtitle:
      "請詳細閱讀以下內容，點擊「閱讀獎學金要點」並滑至底部後方可勾選同意繼續申請",
    items: [
      {
        title: "申請資格",
        content:
          "申請人必須為本校在學學生，且符合各獎學金規定的申請條件。請確認您的學籍狀態與申請資格。",
      },
      {
        title: "申請期限",
        content:
          "各獎學金有不同的申請期限，逾期申請恕不受理。請注意各獎學金的開放申請日期與截止日期。",
      },
      {
        title: "文件準備",
        content:
          "請備妥所需文件，包括但不限於成績單、在學證明、指導教授推薦函等。所有文件必須為清晰可辨識的電子檔案（PDF、JPG、JPEG 或 PNG 格式）。",
      },
      {
        title: "資料正確性",
        content:
          "申請人應確保所填寫資料及上傳文件之正確性與真實性。如有虛偽不實，將取消申請資格並依校規處理。",
      },
      {
        title: "個人資料使用",
        content:
          "您的個人資料將僅用於獎學金申請審核及後續相關作業，本校將依個人資料保護法規定妥善保管。",
      },
      {
        title: "審核流程",
        content:
          "申請送出後將經過系所初審、院級複審及行政單位核定等程序。審核期間請隨時注意系統通知。",
      },
      {
        title: "獎金撥款",
        content:
          "獲獎學生請確認銀行帳戶資料正確無誤，獎學金將於核定後撥款至指定帳戶。",
      },
      {
        title: "申請撤回",
        content:
          "申請送出後如需撤回，請於審核開始前聯繫承辦單位。審核程序啟動後將無法撤回申請。",
      },
    ],
    importantNotice: "重要提醒",
    importantContent:
      "請務必詳細閱讀各獎學金的申請條款與相關規定。每位學生每學期限申請一項獎學金，請謹慎選擇。",
    agreementText: "我已詳細閱讀並了解獎學金要點，同意遵守相關規定",
    readNoticeText: "尚未閱讀獎學金要點",
    readNoticeHint: "請點擊上方按鈕開啟獎學金要點並滑至底端",
    readNoticeDone: "已閱讀完成",
    nextButton: "同意並繼續",
    readFirst: "請先點擊「閱讀獎學金要點」並滑至底端",
    sampleDocumentLabel: "申請文件範例檔",
    sampleDocumentRow: "需要參考申請文件格式？",
    sampleDocumentNotProvided: "尚未提供",
    regulationsHeader: "獎學金要點",
    regulationsOpenButton: "閱讀獎學金要點",
    regulationsRow: "請開啟並閱讀獎學金要點全文",
    regulationsDialogTitle: "獎學金要點",
    regulationsDialogSubtitle: "請滑動至文件底端以完成閱讀",
    regulationsMissing:
      "系統管理員尚未上傳獎學金要點，目前無法進行申請。請聯絡承辦單位。",
    regulationsLoading: "正在檢查獎學金要點…",
    closeButton: "關閉",
  },
  en: {
    title: "Scholarship Application Notice",
    subtitle:
      "Read the following carefully. Scroll the Scholarship Regulations below to the bottom before agreeing to continue.",
    items: [
      {
        title: "Eligibility",
        content:
          "Applicants must be currently enrolled students and meet the specific requirements of each scholarship. Please verify your enrollment status and eligibility.",
      },
      {
        title: "Application Deadline",
        content:
          "Each scholarship has different application deadlines. Late applications will not be accepted. Please note the opening and closing dates for each scholarship.",
      },
      {
        title: "Document Preparation",
        content:
          "Please prepare all required documents, including but not limited to transcripts, enrollment certificates, and advisor recommendation letters. All documents must be clear electronic files (PDF, JPG, JPEG, or PNG format).",
      },
      {
        title: "Data Accuracy",
        content:
          "Applicants must ensure the accuracy and authenticity of all information and uploaded documents. False information will result in disqualification and disciplinary action according to university regulations.",
      },
      {
        title: "Personal Data Usage",
        content:
          "Your personal data will be used solely for scholarship application review and related procedures. The university will safeguard your data according to Personal Data Protection Act.",
      },
      {
        title: "Review Process",
        content:
          "After submission, applications will go through department preliminary review, college review, and administrative approval. Please monitor system notifications during the review period.",
      },
      {
        title: "Award Distribution",
        content:
          "Award recipients should ensure their bank account information is correct. Scholarships will be disbursed to the designated account after approval.",
      },
      {
        title: "Application Withdrawal",
        content:
          "If you need to withdraw your application after submission, please contact the administrative office before the review begins. Withdrawal is not possible once the review process has started.",
      },
    ],
    importantNotice: "Important Notice",
    importantContent:
      "Please read the terms and conditions of each scholarship carefully. Each student may only apply for one scholarship per semester. Choose wisely.",
    agreementText:
      "I have read and understand the scholarship regulations and agree to comply",
    readNoticeText: "Regulations not yet read",
    readNoticeHint:
      "Click the button above to open the regulations and scroll to the bottom",
    readNoticeDone: "Reading complete",
    nextButton: "Agree and Continue",
    readFirst: "Open the regulations and scroll to the bottom first",
    sampleDocumentLabel: "Sample Application Documents",
    sampleDocumentRow: "Need to see the application document format?",
    sampleDocumentNotProvided: "Not available",
    regulationsHeader: "Scholarship Regulations",
    regulationsOpenButton: "Open Scholarship Regulations",
    regulationsRow: "Open and read the full scholarship regulations",
    regulationsDialogTitle: "Scholarship Regulations",
    regulationsDialogSubtitle:
      "Scroll to the bottom of the document to complete reading",
    regulationsMissing:
      "The system administrator has not uploaded the scholarship regulations. Applications cannot proceed. Please contact the administrative office.",
    regulationsLoading: "Checking scholarship regulations…",
    closeButton: "Close",
  },
} as const;

export function NoticeAgreementStep({
  agreedToTerms,
  onAgree,
  onNext,
  locale,
}: NoticeAgreementStepProps) {
  const [hasReadNotice, setHasReadNotice] = useState(false);
  const [showRegulationsDialog, setShowRegulationsDialog] = useState(false);

  const [publicDocs, setPublicDocs] = useState<{
    regulations_url?: string;
    sample_document_url?: string;
    regulations_url_filename?: string;
    sample_document_url_filename?: string;
  }>({});
  const [docsLoaded, setDocsLoaded] = useState(false);
  const [previewFile, setPreviewFile] = useState<{
    url: string;
    filename: string;
    type: string;
  } | null>(null);

  useEffect(() => {
    api.systemSettings
      .getPublicDocs()
      .then((res) => {
        if (res.success && res.data) setPublicDocs(res.data);
      })
      .catch((err) => {
        // Network failure / unexpected throw. Surface the same "no
        // regulations" blocking alert (publicDocs stays empty) so the
        // student isn't stuck on a loading skeleton. Logged for ops.
        // eslint-disable-next-line no-console
        console.error("[NoticeAgreementStep] getPublicDocs failed", err);
      })
      .finally(() => {
        setDocsLoaded(true);
      });
  }, []);

  const handleOpenSampleDoc = useCallback(
    (label: string) => {
      const objectName = publicDocs.sample_document_url;
      const url = buildFileProxyUrl("sample_document_url", objectName);
      if (!url) return;
      const originalName = publicDocs.sample_document_url_filename;
      const filename = originalName || label;
      const type = previewMimeType(originalName || objectName || "");
      setPreviewFile({ url, filename, type });
    },
    [publicDocs.sample_document_url, publicDocs.sample_document_url_filename],
  );

  const handleOpenRegulationsDialog = useCallback(
    () => setShowRegulationsDialog(true),
    [],
  );
  const handleReachedBottom = useCallback(
    () => setHasReadNotice(true),
    [],
  );

  const hasRegulationsUploaded = Boolean(publicDocs.regulations_url);
  const t = NOTICES[locale];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-3 bg-nycu-blue-100 rounded-lg">
              <FileText className="h-6 w-6 text-nycu-blue-600" />
            </div>
            <div>
              <CardTitle className="text-2xl">{t.title}</CardTitle>
              <CardDescription className="mt-1">{t.subtitle}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          <Alert className="border-amber-200 bg-amber-50">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            <AlertDescription>
              <div className="font-semibold text-amber-900 mb-1">
                {t.importantNotice}
              </div>
              <div className="text-sm text-amber-800">{t.importantContent}</div>
            </AlertDescription>
          </Alert>

          <Card className="border-2">
            <div className="p-6">
              <div className="space-y-4">
                {t.items.map((item, index) => (
                  <div
                    key={index}
                    className="pb-4 border-b last:border-b-0 last:pb-0"
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-nycu-blue-100 text-nycu-blue-700 flex items-center justify-center font-semibold text-sm">
                        {index + 1}
                      </div>
                      <div className="flex-1">
                        <h4 className="font-semibold text-nycu-navy-800 mb-2">
                          {item.title}
                        </h4>
                        <p className="text-sm text-gray-700 leading-relaxed">
                          {item.content}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200 flex items-center justify-between gap-3">
            <p className="text-sm text-blue-900">{t.sampleDocumentRow}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleOpenSampleDoc(t.sampleDocumentLabel)}
              disabled={!publicDocs.sample_document_url}
              className="flex items-center gap-2"
            >
              <FileText className="h-4 w-4" />
              {t.sampleDocumentLabel}
              {!publicDocs.sample_document_url && (
                <span className="text-xs text-gray-400 ml-1">
                  ({t.sampleDocumentNotProvided})
                </span>
              )}
            </Button>
          </div>

          {!docsLoaded ? (
            <div className="p-4 bg-gray-50 rounded-lg border border-gray-200 text-sm text-gray-500">
              {t.regulationsLoading}
            </div>
          ) : hasRegulationsUploaded ? (
            <div
              className={`p-4 rounded-lg border flex items-center justify-between gap-3 transition-colors ${
                hasReadNotice
                  ? "bg-emerald-50 border-emerald-200"
                  : "bg-nycu-blue-50 border-nycu-blue-200"
              }`}
            >
              <div className="flex-1">
                <p
                  className={`text-sm font-medium ${
                    hasReadNotice ? "text-emerald-900" : "text-nycu-blue-900"
                  }`}
                >
                  {t.regulationsRow}
                </p>
                {!hasReadNotice && (
                  <p className="text-xs text-nycu-blue-700 mt-1 flex items-center gap-1">
                    <AlertCircle className="h-3 w-3" />
                    {t.readNoticeHint}
                  </p>
                )}
              </div>
              <Button
                variant={hasReadNotice ? "outline" : "default"}
                size="sm"
                onClick={handleOpenRegulationsDialog}
                className={`flex items-center gap-2 ${
                  !hasReadNotice ? "nycu-gradient text-white" : ""
                }`}
              >
                <BookOpen className="h-4 w-4" />
                {t.regulationsOpenButton}
                {hasReadNotice && (
                  <CheckCircle className="h-4 w-4 text-emerald-600 ml-1" />
                )}
              </Button>
            </div>
          ) : (
            <Alert className="border-amber-300 bg-amber-50">
              <AlertCircle className="h-5 w-5 text-amber-700" />
              <AlertDescription className="text-amber-900">
                {t.regulationsMissing}
              </AlertDescription>
            </Alert>
          )}

          <div
            className={`flex items-center space-x-2 p-4 rounded-lg transition-colors ${
              hasReadNotice
                ? "bg-emerald-50 border border-emerald-200"
                : "bg-gray-50"
            }`}
          >
            <Checkbox id="read-notice" checked={hasReadNotice} disabled />
            <Label
              htmlFor="read-notice"
              className="text-sm font-medium leading-none cursor-default"
            >
              {hasReadNotice ? t.readNoticeDone : t.readNoticeText}
            </Label>
          </div>

          <div
            className={`p-6 rounded-lg border-2 transition-all ${
              hasReadNotice
                ? "bg-white border-nycu-blue-200"
                : "bg-gray-50 border-gray-200 opacity-60"
            }`}
          >
            <div className="flex items-start space-x-3">
              <Checkbox
                id="agree-terms"
                checked={agreedToTerms}
                onCheckedChange={(checked) => onAgree(checked as boolean)}
                disabled={!hasReadNotice}
                className="mt-1"
              />
              <div className="flex-1">
                <Label
                  htmlFor="agree-terms"
                  className={`text-base font-semibold leading-relaxed ${
                    hasReadNotice
                      ? "cursor-pointer text-nycu-navy-800"
                      : "cursor-not-allowed text-gray-500"
                  }`}
                >
                  {t.agreementText}
                </Label>
                {!hasReadNotice && (
                  <p className="text-sm text-amber-600 mt-2 flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    {t.readFirst}
                  </p>
                )}
              </div>
            </div>
          </div>

          <div className="flex justify-end pt-4">
            <Button
              onClick={onNext}
              disabled={!agreedToTerms}
              size="lg"
              className="nycu-gradient text-white px-8"
            >
              {agreedToTerms && <CheckCircle className="h-5 w-5 mr-2" />}
              {t.nextButton}
              <ChevronRight className="h-5 w-5 ml-2" />
            </Button>
          </div>
        </CardContent>
      </Card>

      <FilePreviewDialog
        isOpen={previewFile !== null}
        onClose={() => setPreviewFile(null)}
        file={previewFile}
        locale={locale}
      />

      <Dialog
        open={showRegulationsDialog}
        onOpenChange={setShowRegulationsDialog}
      >
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-nycu-blue-600" />
              {t.regulationsDialogTitle}
            </DialogTitle>
            <DialogDescription>{t.regulationsDialogSubtitle}</DialogDescription>
          </DialogHeader>
          {hasRegulationsUploaded && (
            <InlinePdfViewer
              url={buildFileProxyUrl(
                "regulations_url",
                publicDocs.regulations_url,
              )!}
              // 200px = DialogHeader + DialogContent padding + footer row + border.
              className="h-[min(700px,calc(90vh-200px))]"
              locale={locale}
              onReachedBottom={handleReachedBottom}
            />
          )}
          <div className="flex items-center justify-between pt-3 border-t mt-2">
            <p
              className={`text-sm font-medium flex items-center gap-2 ${
                hasReadNotice ? "text-emerald-700" : "text-amber-700"
              }`}
            >
              {hasReadNotice ? (
                <>
                  <CheckCircle className="h-4 w-4" />
                  {t.readNoticeDone}
                </>
              ) : (
                <>
                  <AlertCircle className="h-4 w-4" />
                  {t.readNoticeHint}
                </>
              )}
            </p>
            <Button
              variant={hasReadNotice ? "default" : "outline"}
              size="sm"
              onClick={() => setShowRegulationsDialog(false)}
              className={hasReadNotice ? "nycu-gradient text-white" : ""}
            >
              {t.closeButton}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
