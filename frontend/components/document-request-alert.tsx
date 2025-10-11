"use client";

import { useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FileText, AlertCircle, ChevronRight, CheckCircle } from "lucide-react";
import type { StudentDocumentRequest } from "@/lib/api/modules/document-requests";

interface DocumentRequestAlertProps {
  documentRequests: StudentDocumentRequest[];
  locale?: "zh" | "en";
  onFulfill?: (requestId: number) => void;
}

export function DocumentRequestAlert({
  documentRequests,
  locale = "zh",
  onFulfill,
}: DocumentRequestAlertProps) {
  const [showDetails, setShowDetails] = useState(false);
  const [selectedRequest, setSelectedRequest] = useState<StudentDocumentRequest | null>(null);

  // Only show pending requests
  const pendingRequests = documentRequests.filter((req) => req.status === "pending");

  if (pendingRequests.length === 0) {
    return null;
  }

  const handleViewDetails = (request: StudentDocumentRequest) => {
    setSelectedRequest(request);
  };

  const handleFulfill = async (requestId: number) => {
    if (onFulfill) {
      await onFulfill(requestId);
      setSelectedRequest(null);
    }
  };

  return (
    <>
      <Alert className="border-orange-200 bg-orange-50">
        <AlertCircle className="h-5 w-5 text-orange-600" />
        <AlertTitle className="text-orange-900 font-semibold">
          {locale === "zh" ? "文件補件通知" : "Document Request Notification"}
        </AlertTitle>
        <AlertDescription className="mt-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-orange-800">
                {locale === "zh"
                  ? `您有 ${pendingRequests.length} 項待補文件需求`
                  : `You have ${pendingRequests.length} pending document request(s)`}
              </span>
              <Badge variant="destructive" className="bg-orange-600">
                {pendingRequests.length}
              </Badge>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowDetails(!showDetails)}
              className="border-orange-300 text-orange-700 hover:bg-orange-100"
            >
              {showDetails
                ? locale === "zh"
                  ? "收起"
                  : "Collapse"
                : locale === "zh"
                ? "查看詳情"
                : "View Details"}
              <ChevronRight
                className={`ml-1 h-4 w-4 transition-transform ${
                  showDetails ? "rotate-90" : ""
                }`}
              />
            </Button>
          </div>

          {showDetails && (
            <div className="mt-4 space-y-3">
              {pendingRequests.map((request) => (
                <Card key={request.id} className="border-orange-200">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <CardTitle className="text-base text-gray-900">
                          {request.scholarship_type_name}
                        </CardTitle>
                        <CardDescription className="text-sm mt-1">
                          {locale === "zh" ? "申請編號：" : "Application ID: "}
                          {request.application_app_id} •{" "}
                          {request.academic_year} {request.semester}
                        </CardDescription>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleViewDetails(request)}
                        className="ml-2"
                      >
                        {locale === "zh" ? "詳情" : "Details"}
                      </Button>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2 text-sm">
                      <div>
                        <span className="font-medium text-gray-700">
                          {locale === "zh" ? "需補文件：" : "Required Documents: "}
                        </span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {request.requested_documents.map((doc, idx) => (
                            <Badge
                              key={idx}
                              variant="secondary"
                              className="text-xs"
                            >
                              {doc}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <div>
                        <span className="font-medium text-gray-700">
                          {locale === "zh" ? "補件原因：" : "Reason: "}
                        </span>
                        <span className="text-gray-600">{request.reason}</span>
                      </div>
                      {request.notes && (
                        <div>
                          <span className="font-medium text-gray-700">
                            {locale === "zh" ? "補充說明：" : "Notes: "}
                          </span>
                          <span className="text-gray-600">{request.notes}</span>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </AlertDescription>
      </Alert>

      {/* Details Dialog */}
      {selectedRequest && (
        <Dialog open={!!selectedRequest} onOpenChange={() => setSelectedRequest(null)}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <div className="flex items-center gap-2 text-orange-600 mb-2">
                <FileText className="h-5 w-5" />
                <DialogTitle>
                  {locale === "zh" ? "文件補件詳情" : "Document Request Details"}
                </DialogTitle>
              </div>
              <DialogDescription>
                {locale === "zh"
                  ? `查看申請「${selectedRequest.scholarship_type_name}」的補件要求`
                  : `View document request for "${selectedRequest.scholarship_type_name}" application`}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              {/* Application Info */}
              <div className="rounded-lg bg-gray-50 p-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">
                    {locale === "zh" ? "申請編號" : "Application ID"}
                  </span>
                  <span className="font-medium">{selectedRequest.application_app_id}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">
                    {locale === "zh" ? "獎學金" : "Scholarship"}
                  </span>
                  <span className="font-medium">{selectedRequest.scholarship_type_name}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">
                    {locale === "zh" ? "學年度學期" : "Academic Year"}
                  </span>
                  <span className="font-medium">
                    {selectedRequest.academic_year} {selectedRequest.semester}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">
                    {locale === "zh" ? "要求時間" : "Requested At"}
                  </span>
                  <span className="font-medium">
                    {new Date(selectedRequest.requested_at).toLocaleString(
                      locale === "zh" ? "zh-TW" : "en-US"
                    )}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-gray-600">
                    {locale === "zh" ? "要求人員" : "Requested By"}
                  </span>
                  <span className="font-medium">{selectedRequest.requested_by_name}</span>
                </div>
              </div>

              {/* Required Documents */}
              <div>
                <h4 className="text-sm font-semibold text-gray-900 mb-2">
                  {locale === "zh" ? "需補文件" : "Required Documents"}
                </h4>
                <div className="flex flex-wrap gap-2">
                  {selectedRequest.requested_documents.map((doc, idx) => (
                    <Badge key={idx} variant="secondary" className="text-sm px-3 py-1">
                      <FileText className="h-3 w-3 mr-1" />
                      {doc}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Reason */}
              <div>
                <h4 className="text-sm font-semibold text-gray-900 mb-2">
                  {locale === "zh" ? "補件原因" : "Reason"}
                </h4>
                <div className="rounded-lg bg-gray-50 p-3 text-sm text-gray-700">
                  {selectedRequest.reason}
                </div>
              </div>

              {/* Notes */}
              {selectedRequest.notes && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-900 mb-2">
                    {locale === "zh" ? "補充說明" : "Additional Notes"}
                  </h4>
                  <div className="rounded-lg bg-gray-50 p-3 text-sm text-gray-700">
                    {selectedRequest.notes}
                  </div>
                </div>
              )}

              {/* Instructions */}
              <div className="rounded-lg bg-blue-50 border border-blue-200 p-4">
                <div className="flex gap-2">
                  <AlertCircle className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-blue-900">
                    <p className="font-medium mb-1">
                      {locale === "zh" ? "如何補件" : "How to Submit"}
                    </p>
                    <p>
                      {locale === "zh"
                        ? "請至您的申請頁面上傳所需文件，上傳完成後點擊下方「標記為已完成」按鈕。"
                        : "Please go to your application page to upload the required documents. After uploading, click the 'Mark as Fulfilled' button below."}
                    </p>
                  </div>
                </div>
              </div>

              {/* Action Button */}
              <Button
                onClick={() => handleFulfill(selectedRequest.id)}
                className="w-full bg-green-600 hover:bg-green-700"
              >
                <CheckCircle className="h-4 w-4 mr-2" />
                {locale === "zh" ? "標記為已完成" : "Mark as Fulfilled"}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
