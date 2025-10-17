"use client";

import React, { useState, useEffect, useMemo } from "react";
import { apiClient } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Upload,
  Loader2,
  AlertTriangle,
  Trash2,
  RotateCcw,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ApplicationFileUploadDialog } from "@/components/application-file-upload-dialog";
import { DeleteApplicationDialog } from "@/components/delete-application-dialog";
import type { Application } from "@/lib/api";

interface BatchApplicationFileUploadProps {
  applicationIds: number[];
  onUploadComplete?: () => void;
  locale?: "zh" | "en";
}

interface ApplicationState {
  application: Application | null;
  loading: boolean;
}

interface DocumentType {
  value: string;
  label_zh: string;
  label_en: string;
}

export function BatchApplicationFileUpload({
  applicationIds,
  onUploadComplete,
  locale = "zh",
}: BatchApplicationFileUploadProps) {
  const [applicationStates, setApplicationStates] = useState<Map<number, ApplicationState>>(
    new Map()
  );
  const [error, setError] = useState<string | null>(null);
  const [scholarshipDocuments, setScholarshipDocuments] = useState<DocumentType[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedApplication, setSelectedApplication] = useState<Application | null>(null);
  const [selectedAppId, setSelectedAppId] = useState<number | null>(null);

  // Delete dialog state
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [applicationToDelete, setApplicationToDelete] = useState<{ id: number; name: string } | null>(null);

  // Fetch application details on mount
  useEffect(() => {
    const fetchApplications = async () => {
      const newStates = new Map<number, ApplicationState>();

      for (const appId of applicationIds) {
        newStates.set(appId, {
          application: null,
          loading: true,
        });
      }
      setApplicationStates(newStates);

      // Fetch each application
      for (const appId of applicationIds) {
        try {
          const response = await apiClient.applications.getApplicationById(appId);
          if (response.success && response.data) {
            setApplicationStates((prev) => {
              const updated = new Map(prev);
              const state = updated.get(appId);
              if (state) {
                updated.set(appId, {
                  ...state,
                  application: response.data || null,
                  loading: false,
                });
              }
              return updated;
            });
          }
        } catch (err) {
          console.error(`Failed to fetch application ${appId}:`, err);
          setApplicationStates((prev) => {
            const updated = new Map(prev);
            const state = updated.get(appId);
            if (state) {
              updated.set(appId, {
                ...state,
                loading: false,
              });
            }
            return updated;
          });
        }
      }
    };

    if (applicationIds.length > 0) {
      fetchApplications();
    }
  }, [applicationIds]);

  // Fetch scholarship-specific document types
  useEffect(() => {
    const fetchScholarshipDocuments = async () => {
      // Get scholarship type from the first application
      const firstState = Array.from(applicationStates.values()).find(
        (state) => state.application && !state.loading
      );

      if (!firstState || !firstState.application) {
        return;
      }

      const scholarshipType = firstState.application.scholarship_type;
      if (!scholarshipType) {
        return;
      }

      setDocumentsLoading(true);
      try {
        // Use getFormConfig to get documents including fixed documents (存摺封面)
        const response = await apiClient.applicationFields.getFormConfig(scholarshipType);
        if (response.success && response.data?.documents && response.data.documents.length > 0) {
          // Transform API response to DocumentType format
          const transformedDocs: DocumentType[] = response.data.documents.map((doc: any) => ({
            value: doc.document_name.toLowerCase().replace(/\s+/g, "_"),
            label_zh: doc.document_name,
            label_en: doc.document_name_en || doc.document_name,
          }));
          setScholarshipDocuments(transformedDocs);
        } else {
          setScholarshipDocuments([]);
        }
      } catch (err) {
        console.error("Failed to fetch scholarship documents:", err);
        setScholarshipDocuments([]);
      } finally {
        setDocumentsLoading(false);
      }
    };

    // Only fetch when we have at least one loaded application
    const hasLoadedApp = Array.from(applicationStates.values()).some(
      (state) => state.application && !state.loading
    );

    if (hasLoadedApp && scholarshipDocuments.length === 0 && !documentsLoading) {
      fetchScholarshipDocuments();
    }
  }, [applicationStates, scholarshipDocuments.length, documentsLoading]);

  // Get dynamic fields from form_data or submitted_form_data
  const displayFields = useMemo(() => {
    const firstApp = Array.from(applicationStates.values())
      .find((s) => s.application)?.application;

    if (!firstApp) return [];

    // For batch import: use submitted_form_data.custom_fields (show all fields)
    const customFields = firstApp.submitted_form_data?.custom_fields;
    if (customFields && typeof customFields === 'object' && Object.keys(customFields).length > 0) {
      return Object.keys(customFields); // Show all custom fields
    }

    // For regular applications: use form_data (show all fields)
    if (firstApp.form_data && typeof firstApp.form_data === 'object') {
      return Object.keys(firstApp.form_data); // Show all form data fields
    }

    return [];
  }, [applicationStates]);

  const handleOpenDialog = (application: Application, appId: number) => {
    setSelectedApplication(application);
    setSelectedAppId(appId);
    setDialogOpen(true);
  };

  const handleUploadComplete = () => {
    if (onUploadComplete) {
      onUploadComplete();
    }
  };

  const handleDelete = (appId: number, studentName: string) => {
    setApplicationToDelete({ id: appId, name: studentName });
    setShowDeleteDialog(true);
  };

  const handleDeleteSuccess = () => {
    if (applicationToDelete) {
      // Remove from application states
      setApplicationStates((prev) => {
        const updated = new Map(prev);
        updated.delete(applicationToDelete.id);
        return updated;
      });

      // Notify completion (optional - refresh parent data)
      if (onUploadComplete) {
        onUploadComplete();
      }

      // Reset delete state
      setApplicationToDelete(null);
    }
  };

  const handleRestore = async (appId: number) => {
    try {
      const response = await apiClient.applications.updateApplication(appId, {
        status: "draft",
      });

      if (response.success) {
        // Refresh application data
        const refreshResponse = await apiClient.applications.getApplicationById(appId);
        if (refreshResponse.success && refreshResponse.data) {
          setApplicationStates((prev) => {
            const updated = new Map(prev);
            const state = updated.get(appId);
            if (state) {
              updated.set(appId, {
                ...state,
                application: refreshResponse.data || null,
              });
            }
            return updated;
          });
        }

        // Notify completion
        if (onUploadComplete) {
          onUploadComplete();
        }
      } else {
        setError(
          locale === "zh"
            ? `恢復申請失敗: ${response.message}`
            : `Failed to restore application: ${response.message}`
        );
      }
    } catch (err) {
      console.error(`Failed to restore application ${appId}:`, err);
      setError(
        locale === "zh"
          ? "恢復申請失敗，請稍後再試"
          : "Failed to restore application, please try again"
      );
    }
  };

  if (applicationIds.length === 0) {
    return (
      <Alert>
        <AlertTriangle className="h-4 w-4" />
        <AlertDescription>
          {locale === "zh"
            ? "沒有可用的申請記錄"
            : "No applications available"}
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="overflow-hidden rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[120px]">
                {locale === "zh" ? "學號" : "Student ID"}
              </TableHead>
              <TableHead className="w-[100px]">
                {locale === "zh" ? "申請 ID" : "App ID"}
              </TableHead>
              <TableHead className="w-[200px]">
                {locale === "zh" ? "獎學金類型" : "Scholarship"}
              </TableHead>
              <TableHead className="w-[150px]">
                {locale === "zh" ? "郵局帳號" : "Postal Account"}
              </TableHead>
              <TableHead className="w-[180px]">
                {locale === "zh" ? "子獎學金項目" : "Sub Types"}
              </TableHead>
              {displayFields.map((field) => (
                <TableHead key={field} className="min-w-[120px]">
                  {field}
                </TableHead>
              ))}
              <TableHead className="w-[240px] text-right">
                {locale === "zh" ? "操作" : "Actions"}
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Array.from(applicationStates.entries()).map(([appId, state]) => {
              const isDeleted = (state.application?.status as ApplicationStatus) === 'deleted';
              return (
              <TableRow
                key={appId}
                className={isDeleted ? "bg-gray-50 opacity-70" : ""}
              >
                {/* Student ID */}
                <TableCell className="font-mono text-sm">
                  {state.loading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : state.application ? (
                    <div className="flex items-center gap-2">
                      <span>{state.application.student_id}</span>
                      {isDeleted && (
                        <Badge variant="destructive" className="text-xs">
                          {locale === "zh" ? "已刪除" : "Deleted"}
                        </Badge>
                      )}
                    </div>
                  ) : (
                    <span className="text-red-500 text-xs">
                      {locale === "zh" ? "載入失敗" : "Error"}
                    </span>
                  )}
                </TableCell>

                {/* Application ID */}
                <TableCell className="text-sm text-muted-foreground">
                  {appId}
                </TableCell>

                {/* Scholarship Type (Chinese Name) */}
                <TableCell className="text-sm">
                  {state.application?.scholarship_type_zh ||
                   state.application?.scholarship_name ||
                   state.application?.scholarship_type || "-"}
                </TableCell>

                {/* Postal Account */}
                <TableCell className="text-sm font-mono">
                    {state.application?.submitted_form_data?.fields?.postal_account?.value || "-"}
                </TableCell>

                {/* Sub Scholarship Types */}
                <TableCell className="text-sm">
                  <div className="flex flex-wrap gap-1">
                    {state.application?.scholarship_subtype_list &&
                     state.application.scholarship_subtype_list.length > 0 ? (
                      state.application.scholarship_subtype_list.map((subType: string) => (
                        <Badge key={subType} variant="secondary" className="text-xs">
                          {state.application?.sub_type_labels?.[subType]?.zh || subType}
                        </Badge>
                      ))
                    ) : (
                      "-"
                    )}
                  </div>
                </TableCell>

                {/* Dynamic Form Data Fields */}
                {displayFields.map((field) => (
                  <TableCell key={field} className="text-sm">
                    {state.application?.submitted_form_data?.custom_fields?.[field] ||
                     state.application?.form_data?.[field] || "-"}
                  </TableCell>
                ))}

                {/* Actions */}
                <TableCell className="text-right">
                  {!state.loading && state.application && (
                    <div className="flex items-center justify-end gap-2">
                      <Button
                        size="sm"
                        onClick={() => {
                          if (state.application) {
                            handleOpenDialog(state.application, appId);
                          }
                        }}
                        className="h-8"
                        disabled={isDeleted}
                      >
                        <Upload className="h-3 w-3 mr-1" />
                        {locale === "zh" ? "上傳文件" : "Upload"}
                      </Button>
                      {!isDeleted ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDelete(appId, state.application?.student_name || "未知學生")}
                          className="h-8 text-red-600 hover:text-red-700 hover:bg-red-50"
                        >
                          <Trash2 className="h-3 w-3 mr-1" />
                          {locale === "zh" ? "刪除申請" : "Delete"}
                        </Button>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRestore(appId)}
                          className="h-8 text-green-600 hover:text-green-700 hover:bg-green-50"
                        >
                          <RotateCcw className="h-3 w-3 mr-1" />
                          {locale === "zh" ? "恢復申請" : "Restore"}
                        </Button>
                      )}
                    </div>
                  )}
                </TableCell>
              </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      <div className="text-sm text-muted-foreground">
        {locale === "zh"
          ? `總計 ${applicationIds.length} 個申請`
          : `Total ${applicationIds.length} applications`}
      </div>

      {/* Upload Dialog */}
      <ApplicationFileUploadDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        application={selectedApplication}
        applicationId={selectedAppId}
        scholarshipDocuments={scholarshipDocuments}
        onUploadComplete={handleUploadComplete}
        locale={locale}
      />

      {/* Delete Dialog */}
      <DeleteApplicationDialog
        open={showDeleteDialog}
        onOpenChange={(open) => {
          setShowDeleteDialog(open);
          if (!open) setApplicationToDelete(null);
        }}
        applicationId={applicationToDelete?.id || 0}
        applicationName={applicationToDelete?.name || ""}
        onSuccess={handleDeleteSuccess}
        locale={locale}
        requireReason={true}
      />
    </div>
  );
}
