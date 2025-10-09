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
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ApplicationFileUploadDialog } from "@/components/application-file-upload-dialog";
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

  const handleDelete = async (appId: number) => {
    if (
      !window.confirm(
        locale === "zh"
          ? "確定要刪除此申請嗎？此操作無法復原。"
          : "Are you sure you want to delete this application? This action cannot be undone."
      )
    ) {
      return;
    }

    setError(null);

    try {
      const response = await apiClient.applications.deleteApplication(appId);

      if (response.success) {
        // Remove from application states
        setApplicationStates((prev) => {
          const updated = new Map(prev);
          updated.delete(appId);
          return updated;
        });

        // Notify completion (optional - refresh parent data)
        if (onUploadComplete) {
          onUploadComplete();
        }
      } else {
        setError(
          response.message ||
            (locale === "zh" ? "刪除失敗" : "Failed to delete application")
        );
      }
    } catch (err: any) {
      setError(
        err.message ||
          (locale === "zh"
            ? "刪除時發生錯誤"
            : "Error occurred during deletion")
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
            {Array.from(applicationStates.entries()).map(([appId, state]) => (
              <TableRow key={appId}>
                {/* Student ID */}
                <TableCell className="font-mono text-sm">
                  {state.loading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : state.application ? (
                    state.application.student_id
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
                  {state.application?.submitted_form_data?.postal_account || "-"}
                </TableCell>

                {/* Sub Scholarship Types */}
                <TableCell className="text-sm">
                  <div className="flex flex-wrap gap-1">
                    {state.application?.scholarship_subtype_list &&
                     state.application.scholarship_subtype_list.length > 0 ? (
                      state.application.scholarship_subtype_list.map((subType: string) => (
                        <Badge key={subType} variant="secondary" className="text-xs">
                          {locale === "zh"
                            ? state.application?.sub_type_labels?.[subType]?.zh || subType
                            : state.application?.sub_type_labels?.[subType]?.en || subType}
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
                      >
                        <Upload className="h-3 w-3 mr-1" />
                        {locale === "zh" ? "上傳文件" : "Upload"}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDelete(appId)}
                        className="h-8 text-red-600 hover:text-red-700 hover:bg-red-50"
                      >
                        <Trash2 className="h-3 w-3 mr-1" />
                        {locale === "zh" ? "刪除申請" : "Delete"}
                      </Button>
                    </div>
                  )}
                </TableCell>
              </TableRow>
            ))}
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
    </div>
  );
}
