"use client";

import { useState, useEffect } from "react";
import { ErrorBoundary, useErrorHandler } from "@/components/error-boundary";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Search, Eye, CheckCircle, AlertCircle, Clock, X } from "lucide-react";
import apiClient, { Application, ApiResponse } from "@/lib/api";
import { User } from "@/types/user";
import { getDisplayStatusInfo } from "@/lib/utils/application-helpers";
import { Locale } from "@/lib/validators";

interface ProfessorReviewComponentProps {
  user: User;
}

interface SubTypeOption {
  value: string;
  label: string;
  label_en: string;
  is_default: boolean;
}

interface ReviewItem {
  sub_type_code: string;
  recommendation: 'approve' | 'reject' | 'pending';
  comments?: string;
}

interface ReviewData {
  recommendation?: string;
  items: ReviewItem[];
}

function ProfessorReviewComponentInner({
  user,
}: ProfessorReviewComponentProps) {
  const handleError = useErrorHandler();
  const [applications, setApplications] = useState<Application[]>([]);
  const [filteredApplications, setFilteredApplications] = useState<
    Application[]
  >([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [selectedApplication, setSelectedApplication] =
    useState<Application | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("pending");

  // Review form states
  const [subTypes, setSubTypes] = useState<SubTypeOption[]>([]);
  const [reviewData, setReviewData] = useState<ReviewData>({
    recommendation: "",
    items: [],
  });
  const [existingReview, setExistingReview] = useState<any>(null);
  const [reviewModalOpen, setReviewModalOpen] = useState(false);

  // Load applications
  const fetchApplications = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.professor.getApplications(statusFilter);
      if (response.success && response.data) {
        setApplications(response.data);
        setFilteredApplications(response.data);
      } else {
        setError(response.message || "Failed to load applications");
        setApplications([]);
        setFilteredApplications([]);
      }
    } catch (e: any) {
      setError(e.message || "Failed to load applications");
      setApplications([]);
      setFilteredApplications([]);
    } finally {
      setLoading(false);
    }
  };

  // Load applications on mount and when filter changes
  useEffect(() => {
    fetchApplications();
  }, [statusFilter]);

  // Search filtering
  useEffect(() => {
    if (!searchQuery) {
      setFilteredApplications(applications);
    } else {
      const filtered = applications.filter(
        app =>
          (app.student_name?.toLowerCase() || "").includes(
            searchQuery.toLowerCase()
          ) ||
          (app.student_no?.toLowerCase() || "").includes(
            searchQuery.toLowerCase()
          ) ||
          (app.scholarship_name?.toLowerCase() || "").includes(
            searchQuery.toLowerCase()
          )
      );
      setFilteredApplications(filtered);
    }
  }, [searchQuery, applications]);

  // Ensure reviewData.items is always initialized when subTypes change
  useEffect(() => {
    if (subTypes.length > 0 && reviewData.items.length === 0) {
      const initialItems = subTypes.map(subType => ({
        sub_type_code: subType.value,
        recommendation: 'pending' as const,
        comments: "",
      }));

      setReviewData(prev => ({
        ...prev,
        items: initialItems,
      }));
    }
  }, [subTypes, reviewData.items.length]);

  // Get status badge variant
  const getStatusVariant = (status: string) => {
    switch (status) {
      case "under_review":
        return "default";
      case "submitted":
        return "secondary";
      default:
        return "outline";
    }
  };

  // Get status display text
  const getStatusText = (status: string) => {
    switch (status) {
      case "under_review":
        return "審核中";
      case "submitted":
        return "已提交";
      default:
        return status;
    }
  };

  // Open review modal
  const openReviewModal = async (application: Application) => {
    setSelectedApplication(application);
    setLoading(true);
    setError(null);

    try {
      // Get available sub-types
      const subTypesResponse = await apiClient.professor.getSubTypes(
        application.id
      );

      let availableSubTypes: SubTypeOption[] = [];
      if (subTypesResponse.success && subTypesResponse.data) {
        availableSubTypes = subTypesResponse.data;
        setSubTypes(availableSubTypes);
      }

      // Always initialize items based on available sub-types
      const initializeItems = (subTypes: SubTypeOption[]) => {
        return subTypes.map(subType => ({
          sub_type_code: subType.value,
          recommendation: 'pending' as const,
          comments: "",
        }));
      };

      // Get existing review if any
      const initialItems = initializeItems(availableSubTypes);

      try {
        const reviewResponse = await apiClient.professor.getReview(
          application.id
        );

        // Check if this is an actual existing review (id > 0) or a new review (id = 0)
        if (
          reviewResponse.success &&
          reviewResponse.data &&
          reviewResponse.data.id &&
          reviewResponse.data.id > 0
        ) {
          setExistingReview(reviewResponse.data);

          // Merge existing review items with all available sub-types
          const existingItems: ReviewItem[] = reviewResponse.data.items || [];
          const mergedItems = availableSubTypes.map(subType => {
            const existingItem = existingItems.find(
              item => item.sub_type_code === subType.value
            );
            return (
              existingItem || {
                sub_type_code: subType.value,
                recommendation: 'pending' as const,
                comments: "",
              }
            );
          });

          setReviewData({
            recommendation: reviewResponse.data.recommendation || "",
            items: mergedItems,
          });
        } else {
          // No existing review (id = 0 or no data), use initial items
          setExistingReview(null);
          setReviewData({
            recommendation: "",
            items: initialItems,
          });
        }
      } catch (e) {
        // No existing review, use initial items
        setExistingReview(null);
        setReviewData({
          recommendation: "",
          items: initialItems,
        });
      }

      setReviewModalOpen(true);
    } catch (e: any) {
      console.error("Error opening review modal:", e);
      setError(e.message || "Failed to load review data");
    } finally {
      setLoading(false);
    }
  };

  // Submit or update review
  const submitReview = async () => {
    if (!selectedApplication) return;

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      let response: ApiResponse<any>;

      // Filter out pending items - only send approve/reject items to API
      const filteredItems = reviewData.items
        .filter(
          item => item.recommendation === 'approve' || item.recommendation === 'reject'
        )
        .map(item => ({
          sub_type_code: item.sub_type_code,
          recommendation: item.recommendation as 'approve' | 'reject',
          comments: item.comments
        }));

      // Validate that at least one item has been evaluated
      if (filteredItems.length === 0) {
        setError('請至少對一個獎學金申請項目進行評估（選擇同意或不同意）');
        setLoading(false);
        return;
      }

      // Validate that all rejected items have comments
      const rejectedWithoutComments = filteredItems.filter(
        item => item.recommendation === 'reject' && (!item.comments || item.comments.trim() === '')
      );

      if (rejectedWithoutComments.length > 0) {
        setError('當選擇「不同意」時必須填寫評估意見');
        setLoading(false);
        return;
      }

      const submissionData = {
        items: filteredItems
      };

      if (existingReview) {
        // Update existing review
        response = await apiClient.professor.updateReview(
          selectedApplication.id,
          existingReview.id,
          submissionData
        );
      } else {
        // Submit new review
        response = await apiClient.professor.submitReview(
          selectedApplication.id,
          submissionData
        );
      }

      if (response.success) {
        setSuccess("推薦意見已成功提交");
        setReviewModalOpen(false);
        setSelectedApplication(null);
        setReviewData({ recommendation: "", items: [] });
        setExistingReview(null);
        // Refresh applications list
        fetchApplications();
      } else {
        setError(response.message || "Failed to submit review");
      }
    } catch (e: any) {
      setError(e.message || "Failed to submit review");
    } finally {
      setLoading(false);
    }
  };

  // Update review item
  const updateReviewItem = (subTypeCode: string, field: string, value: any) => {
    setReviewData(prev => {
      const newData = {
        ...prev,
        items: prev.items.map(item => {
          if (item.sub_type_code === subTypeCode) {
            return { ...item, [field]: value };
          }
          return item;
        }),
      };

      return newData;
    });
  };

  // Get sub-type label
  const getSubTypeLabel = (subTypeCode: string) => {
    const subType = subTypes.find(st => st.value === subTypeCode);
    return subType?.label || subTypeCode;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">獎學金申請審查</h2>
          <p className="text-muted-foreground">
            審查學生獎學金申請並提供推薦意見
          </p>
        </div>
      </div>

      {/* Error/Success Messages */}
      {error && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 text-red-700">
              <AlertCircle className="h-4 w-4" />
              <span>{error}</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setError(null)}
                className="ml-auto"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {success && (
        <Card className="border-green-200 bg-green-50">
          <CardContent className="pt-4">
            <div className="flex items-center gap-2 text-green-700">
              <CheckCircle className="h-4 w-4" />
              <span>{success}</span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSuccess(null)}
                className="ml-auto"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Search and Filter Controls */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="搜尋學生姓名、學號或獎學金..."
            className="pl-8"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="狀態篩選" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="pending">待審查</SelectItem>
            <SelectItem value="completed">已完成</SelectItem>
            <SelectItem value="all">全部</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Applications Table */}
      <Card>
        <CardHeader>
          <CardTitle>獎學金申請列表</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-12 text-center">
              <div className="flex flex-col items-center gap-4">
                <Clock className="h-12 w-12 animate-spin text-blue-600" />
                <div className="space-y-2">
                  <p className="text-lg font-medium">載入申請資料中...</p>
                  <p className="text-sm text-muted-foreground">
                    正在取得需要您審查的獎學金申請
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>學生資訊</TableHead>
                  <TableHead>就讀學期數</TableHead>
                  <TableHead>獎學金類型</TableHead>
                  <TableHead>提交日期</TableHead>
                  <TableHead>狀態</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredApplications.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center py-12">
                      <div className="flex flex-col items-center gap-4">
                        <div className="p-4 bg-muted rounded-full">
                          <Eye className="h-8 w-8 text-muted-foreground" />
                        </div>
                        <div className="text-center space-y-2">
                          <p className="text-lg font-medium text-muted-foreground">
                            {error
                              ? "載入申請時發生錯誤"
                              : searchQuery
                                ? "沒有符合搜尋條件的申請"
                                : "目前沒有需要審查的申請"}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            {error
                              ? "請重新整理頁面或聯繫系統管理員"
                              : searchQuery
                                ? "請嘗試不同的搜尋關鍵字"
                                : "新的申請提交後會顯示在這裡"}
                          </p>
                          {error && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={fetchApplications}
                              className="mt-2"
                            >
                              重新載入
                            </Button>
                          )}
                        </div>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredApplications.map(app => (
                    <TableRow key={app.id}>
                      <TableCell>
                        <div>
                          <p className="font-medium">
                            {app.student_name || "未知學生"}
                          </p>
                          <p className="text-sm text-muted-foreground">
                            {app.student_no}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell>
                        {app.student_data?.std_termcount || "-"}
                      </TableCell>
                      <TableCell>
                        <div>
                          <p>{app.scholarship_name}</p>
                          {app.is_renewal && (
                            <Badge variant="outline" className="text-xs mt-1">
                              續領
                            </Badge>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {app.submitted_at
                          ? new Date(app.submitted_at).toLocaleDateString()
                          : "未提交"}
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-2">
                          {(() => {
                            const statusInfo = getDisplayStatusInfo(app, "zh");
                            return (
                              <>
                                <Badge variant={statusInfo.statusVariant}>
                                  {statusInfo.statusLabel}
                                </Badge>
                                {statusInfo.showStage && statusInfo.stageLabel && (
                                  <Badge variant={statusInfo.stageVariant}>
                                    {statusInfo.stageLabel}
                                  </Badge>
                                )}
                              </>
                            );
                          })()}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => openReviewModal(app)}
                          disabled={loading}
                        >
                          <Eye className="h-4 w-4 mr-1" />
                          審查
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Review Modal */}
      <Dialog open={reviewModalOpen} onOpenChange={setReviewModalOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              審查申請 - {selectedApplication?.student_name}
            </DialogTitle>
            <DialogDescription>
              請審查此獎學金申請並針對各子類型提供推薦意見
            </DialogDescription>
          </DialogHeader>

          {selectedApplication && (
            <div className="space-y-6">
              {/* Application Info */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-lg">申請資訊</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="text-sm font-medium">學生姓名</label>
                      <p>{selectedApplication.student_name}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium">學號</label>
                      <p>{selectedApplication.student_no}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium">就讀學期數</label>
                      <p>{selectedApplication.student_data?.std_termcount || "未提供"}</p>
                    </div>
                    <div>
                      <label className="text-sm font-medium">獎學金類型</label>
                      <p>{selectedApplication.scholarship_name}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Sub-type Reviews - SIMPLIFIED VERSION */}
              {subTypes.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg flex items-center gap-2">
                      <CheckCircle className="h-5 w-5 text-blue-600" />
                      是否同意學生申請
                    </CardTitle>
                    <p className="text-sm text-muted-foreground">
                      請針對每個獎學金申請進行評估，並提供您的推薦意見
                    </p>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {subTypes.map(subType => {
                      const reviewItem = reviewData.items.find(
                        item => item.sub_type_code === subType.value
                      );
                      const isRecommended = reviewItem?.recommendation === 'approve';

                      return (
                        <div
                          key={subType.value}
                          className="border rounded-lg p-4 space-y-4"
                        >
                          {/* Sub-type Title */}
                          <div>
                            <h3 className="font-semibold text-lg mb-1">
                              {subType.label}
                            </h3>
                            {subType.label_en && (
                              <p className="text-sm text-muted-foreground mb-2">
                                {subType.label_en}
                              </p>
                            )}
                          </div>

                          {/* Checkbox options */}
                          <div className="space-y-3">
                            <div className="flex items-center gap-4">
                              <div className="flex items-center space-x-2">
                                <Checkbox
                                  id={`agree-${subType.value}`}
                                  checked={reviewItem?.recommendation === 'approve'}
                                  onCheckedChange={checked => {
                                    updateReviewItem(
                                      subType.value,
                                      "recommendation",
                                      checked ? 'approve' : 'pending'
                                    );
                                  }}
                                />
                                <label
                                  htmlFor={`agree-${subType.value}`}
                                  className="text-sm font-medium cursor-pointer"
                                >
                                  同意
                                </label>
                              </div>
                              <div className="flex items-center space-x-2">
                                <Checkbox
                                  id={`disagree-${subType.value}`}
                                  checked={reviewItem?.recommendation === 'reject'}
                                  onCheckedChange={checked => {
                                    updateReviewItem(
                                      subType.value,
                                      "recommendation",
                                      checked ? 'reject' : 'pending'
                                    );
                                  }}
                                />
                                <label
                                  htmlFor={`disagree-${subType.value}`}
                                  className="text-sm font-medium cursor-pointer"
                                >
                                  不同意
                                </label>
                              </div>
                            </div>
                            {reviewItem?.recommendation && reviewItem.recommendation !== 'pending' && (
                              <Badge
                                variant={reviewItem.recommendation === 'approve' ? 'default' : 'destructive'}
                                className="w-fit"
                              >
                                {reviewItem.recommendation === 'approve' ? '✓ 同意' : '✗ 不同意'}
                              </Badge>
                            )}
                          </div>

                          {/* Comments Section */}
                          <div>
                            <label className="text-sm font-medium mb-2 block">
                              評估意見 {reviewItem?.recommendation === 'reject' && <span className="text-red-500">*</span>} (當選擇「不同意」時為必填)
                            </label>
                            <Textarea
                              placeholder={`請說明您對「${subType.label}」的評估意見...`}
                              value={reviewItem?.comments || ""}
                              onChange={e => {
                                updateReviewItem(
                                  subType.value,
                                  "comments",
                                  e.target.value
                                );
                              }}
                              rows={3}
                              className={reviewItem?.recommendation === 'reject' && (!reviewItem?.comments || reviewItem.comments.trim() === '') ? 'border-red-500' : ''}
                            />
                            {reviewItem?.recommendation === 'reject' && (!reviewItem?.comments || reviewItem.comments.trim() === '') && (
                              <p className="text-sm text-red-600 mt-1">
                                當選擇「不同意」時必須填寫評估意見
                              </p>
                            )}
                          </div>
                        </div>
                      );
                    })}

                  </CardContent>
                </Card>
              )}

              {/* Actions */}
              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  onClick={() => setReviewModalOpen(false)}
                  disabled={loading}
                >
                  取消
                </Button>
                <Button
                  onClick={submitReview}
                  disabled={
                    loading ||
                    !reviewData.items.some(
                      item => item.recommendation === "approve" || item.recommendation === "reject"
                    ) ||
                    reviewData.items.some(
                      item => item.recommendation === "reject" && (!item.comments || item.comments.trim() === "")
                    )
                  }
                >
                  {loading
                    ? "提交中..."
                    : existingReview
                      ? "更新推薦"
                      : "提交推薦"}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

// Export wrapped component with error boundary
export function ProfessorReviewComponent({
  user,
}: ProfessorReviewComponentProps) {
  return (
    <ErrorBoundary
      onError={(error, errorInfo) => {
        console.error("Professor Review Component Error:", error, errorInfo);
        // In production, send to error reporting service
      }}
    >
      <ProfessorReviewComponentInner user={user} />
    </ErrorBoundary>
  );
}
