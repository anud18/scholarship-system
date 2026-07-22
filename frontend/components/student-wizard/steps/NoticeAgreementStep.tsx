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
import {
  buildFileProxyUrl,
  buildSuppDocFileProxyUrl,
  type ApplicationNotices,
  type SupplementaryDoc,
} from "@/lib/api/modules/system-settings";
import { previewMimeType } from "@/lib/utils";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import { InlinePdfViewer } from "@/components/inline-pdf-viewer";

interface NoticeAgreementStepProps {
  agreedToTerms: boolean;
  onAgree: (agreed: boolean) => void;
  onNext: () => void;
  locale: "zh" | "en";
}

// Static locale copy hoisted to module scope so the object isn't reallocated
// on every render. The notice items and important-notice content are NOT here:
// they are admin-editable and fetched from
// GET /api/v1/system-settings/application-notices.
const NOTICES = {
  zh: {
    title: "獎學金申請注意事項",
    subtitle:
      "請詳細閱讀以下內容，點擊「閱讀獎學金要點」並滑至底部後方可勾選同意繼續申請",
    importantNotice: "重要提醒",
    noticesLoading: "正在載入注意事項…",
    noticesLoadError: "無法載入注意事項，請重新整理頁面或聯絡承辦單位。",
    agreementText: "我已詳細閱讀並了解獎學金要點，同意遵守相關規定",
    readNoticeText: "尚未閱讀獎學金要點",
    readNoticeHint: "請點擊上方按鈕開啟獎學金要點並滑至底端",
    readNoticeDone: "已閱讀完成",
    nextButton: "同意並繼續",
    readFirst: "請先點擊「閱讀獎學金要點」並滑至底端",
    sampleDocumentLabel: "申請文件範例檔",
    referenceDocsHeader: "參考文件",
    previewLabel: "預覽",
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
    importantNotice: "Important Notice",
    noticesLoading: "Loading application notices…",
    noticesLoadError:
      "Failed to load the application notices. Please refresh the page or contact the administrative office.",
    agreementText:
      "I have read and understand the scholarship regulations and agree to comply",
    readNoticeText: "Regulations not yet read",
    readNoticeHint:
      "Click the button above to open the regulations and scroll to the bottom",
    readNoticeDone: "Reading complete",
    nextButton: "Agree and Continue",
    readFirst: "Open the regulations and scroll to the bottom first",
    sampleDocumentLabel: "Sample Application Documents",
    referenceDocsHeader: "Reference Documents",
    previewLabel: "Preview",
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
  const [supplementaryDocs, setSupplementaryDocs] = useState<SupplementaryDoc[]>(
    []
  );
  const [notices, setNotices] = useState<ApplicationNotices | null>(null);
  const [noticesError, setNoticesError] = useState(false);
  const [previewFile, setPreviewFile] = useState<{
    url: string;
    filename: string;
    type: string;
  } | null>(null);

  useEffect(() => {
    // allSettled (not all): a supplementary-docs or notices fetch failure must
    // not drop publicDocs, which gates the regulations scroll-and-agree flow.
    Promise.allSettled([
      api.systemSettings.getPublicDocs(),
      api.systemSettings.supplementaryDocs.list(),
      api.systemSettings.applicationNotices.get(),
    ])
      .then(([docsResult, suppResult, noticesResult]) => {
        if (docsResult.status === "fulfilled") {
          const docsRes = docsResult.value;
          if (docsRes.success && docsRes.data) setPublicDocs(docsRes.data);
        } else {
          // eslint-disable-next-line no-console
          console.error(
            "[NoticeAgreementStep] getPublicDocs failed",
            docsResult.reason
          );
        }
        if (suppResult.status === "fulfilled") {
          const suppRes = suppResult.value;
          if (suppRes.success && suppRes.data) {
            setSupplementaryDocs(suppRes.data);
          }
        } else {
          // eslint-disable-next-line no-console
          console.error(
            "[NoticeAgreementStep] supplementaryDocs.list failed",
            suppResult.reason
          );
        }
        if (
          noticesResult.status === "fulfilled" &&
          noticesResult.value.success &&
          noticesResult.value.data
        ) {
          setNotices(noticesResult.value.data);
        } else {
          setNoticesError(true);
          // eslint-disable-next-line no-console
          console.error(
            "[NoticeAgreementStep] applicationNotices.get failed",
            noticesResult.status === "rejected"
              ? noticesResult.reason
              : noticesResult.value
          );
        }
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
  const localizedNotices = notices ? notices[locale] : null;

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
          {noticesError ? (
            <Alert className="border-red-300 bg-red-50">
              <AlertCircle className="h-5 w-5 text-red-600" />
              <AlertDescription className="text-red-900">
                {t.noticesLoadError}
              </AlertDescription>
            </Alert>
          ) : !localizedNotices ? (
            <div className="p-4 bg-gray-50 rounded-lg border border-gray-200 text-sm text-gray-500">
              {t.noticesLoading}
            </div>
          ) : (
            <>
              <Alert className="border-amber-200 bg-amber-50">
                <AlertTriangle className="h-5 w-5 text-amber-600" />
                <AlertDescription>
                  <div className="font-semibold text-amber-900 mb-1">
                    {t.importantNotice}
                  </div>
                  <div className="text-sm text-amber-800 whitespace-pre-line">
                    {localizedNotices.important_notice}
                  </div>
                </AlertDescription>
              </Alert>

              <Card className="border-2">
                <div className="p-6">
                  <div className="space-y-4">
                    {localizedNotices.items.map((item, index) => (
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
                            <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-line">
                              {item.content}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </Card>
            </>
          )}

          {(() => {
            const sampleAvailable = Boolean(publicDocs.sample_document_url);
            const hasAnyReferenceDoc =
              sampleAvailable || supplementaryDocs.length > 0;
            if (!hasAnyReferenceDoc) return null;

            const rows: Array<{
              key: string;
              label: string;
              onClick: () => void;
            }> = [];

            if (sampleAvailable) {
              rows.push({
                key: "fixed-sample",
                label: t.sampleDocumentLabel,
                onClick: () => handleOpenSampleDoc(t.sampleDocumentLabel),
              });
            }

            for (const doc of supplementaryDocs) {
              rows.push({
                key: `supp-${doc.id}`,
                label: doc.title,
                onClick: () => {
                  const url = buildSuppDocFileProxyUrl(doc.id, doc.object_name);
                  setPreviewFile({
                    url,
                    filename: doc.original_filename,
                    type: previewMimeType(doc.original_filename),
                  });
                },
              });
            }

            return (
              <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                <h4 className="text-sm font-semibold text-blue-900 mb-3">
                  {t.referenceDocsHeader}
                </h4>
                <ul className="space-y-2">
                  {rows.map((row) => (
                    <li
                      key={row.key}
                      className="flex items-center justify-between gap-3 rounded-md bg-white px-3 py-2"
                    >
                      <span
                        className="text-sm text-nycu-navy-800 truncate"
                        title={row.label}
                      >
                        {row.label}
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={row.onClick}
                        className="flex items-center gap-2"
                      >
                        <FileText className="h-4 w-4" /> {t.previewLabel}
                      </Button>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })()}

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
              // 245px = DialogHeader + DialogContent padding + footer row +
              // border + the viewer's zoom/download toolbar (~45px).
              className="h-[min(700px,calc(90vh-245px))]"
              locale={locale}
              onReachedBottom={handleReachedBottom}
              downloadFilename={
                publicDocs.regulations_url_filename || "scholarship-regulations.pdf"
              }
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
