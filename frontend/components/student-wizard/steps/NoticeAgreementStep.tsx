"use client";

import React, { useState } from "react";
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
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  AlertCircle,
  CheckCircle,
  FileText,
  AlertTriangle,
  ChevronRight,
} from "lucide-react";

interface NoticeAgreementStepProps {
  agreedToTerms: boolean;
  onAgree: (agreed: boolean) => void;
  onNext: () => void;
  locale: "zh" | "en";
}

export function NoticeAgreementStep({
  agreedToTerms,
  onAgree,
  onNext,
  locale,
}: NoticeAgreementStepProps) {
  const [hasReadNotice, setHasReadNotice] = useState(false);

  const notices = {
    zh: {
      title: "獎學金申請注意事項",
      subtitle: "請詳細閱讀以下內容後，勾選同意方可繼續申請",
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
      agreementText: "我已詳細閱讀並了解上述注意事項，同意遵守相關規定",
      readNoticeText: "我已詳閱所有注意事項",
      nextButton: "同意並繼續",
      readFirst: "請先詳細閱讀注意事項",
    },
    en: {
      title: "Scholarship Application Notice",
      subtitle: "Please read the following carefully and check to agree before proceeding",
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
        "I have read and understand the above notice and agree to comply with the regulations",
      readNoticeText: "I have read all notices",
      nextButton: "Agree and Continue",
      readFirst: "Please read the notice first",
    },
  };

  const t = notices[locale];

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
          {/* Important Notice Alert */}
          <Alert className="border-amber-200 bg-amber-50">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            <AlertDescription>
              <div className="font-semibold text-amber-900 mb-1">
                {t.importantNotice}
              </div>
              <div className="text-sm text-amber-800">
                {t.importantContent}
              </div>
            </AlertDescription>
          </Alert>

          {/* Notice Content */}
          <Card className="border-2">
            <ScrollArea className="h-[400px] p-6">
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
            </ScrollArea>
          </Card>

          {/* Read confirmation */}
          <div className="flex items-center space-x-2 p-4 bg-gray-50 rounded-lg">
            <Checkbox
              id="read-notice"
              checked={hasReadNotice}
              onCheckedChange={(checked) =>
                setHasReadNotice(checked as boolean)
              }
            />
            <Label
              htmlFor="read-notice"
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
            >
              {t.readNoticeText}
            </Label>
          </div>

          {/* Agreement checkbox */}
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

          {/* Action buttons */}
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
    </div>
  );
}
