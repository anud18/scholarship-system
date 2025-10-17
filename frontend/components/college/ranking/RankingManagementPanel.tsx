"use client";

import { User } from "@/types/user";
import { useCollegeManagement } from "@/contexts/college-management-context";
import { useState, useEffect, useCallback } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { CollegeRankingTable } from "@/components/college-ranking-table";
import {
  Plus,
  Trophy,
  Clock,
  Loader2,
  Lock,
  LockOpen,
  Trash2,
  Pencil,
  Check,
  X,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { apiClient } from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface RankingManagementPanelProps {
  user: User;
  scholarshipType: { code: string; name: string };
}

export function RankingManagementPanel({
  user,
  scholarshipType,
}: RankingManagementPanelProps) {
  const {
    locale,
    selectedRanking,
    setSelectedRanking,
    rankingData,
    setRankingData,
    isRankingLoading,
    setIsRankingLoading,
    filteredRankings,
    rankings,
    setRankings,
    scholarshipConfig,
    selectedAcademicYear,
    selectedSemester,
    availableOptions,
    activeScholarshipTab,
    editingRankingId,
    setEditingRankingId,
    editingRankingName,
    setEditingRankingName,
    showDeleteRankingDialog,
    setShowDeleteRankingDialog,
    rankingToDelete,
    setRankingToDelete,
    saveStatus,
    setSaveStatus,
    saveTimeoutRef,
    getAcademicConfig,
    getScholarshipConfig,
    setActiveTab,
    fetchCollegeApplications,
  } = useCollegeManagement();

  const { toast } = useToast();

  // Fetch rankings on mount
  const fetchRankings = useCallback(async () => {
    try {
      console.log("Fetching rankings...");
      const response = await apiClient.college.getRankings();
      if (response.success && response.data) {
        console.log(`Fetched ${response.data.length} rankings:`, response.data);
        const normalizedRankings = response.data.map((ranking: any) => {
          const rawSemester =
            typeof ranking.semester === "string" && ranking.semester.length > 0
              ? ranking.semester.toLowerCase()
              : null;
          const safeSemester =
            rawSemester && rawSemester !== "yearly"
              ? rawSemester
              : null;
          return { ...ranking, semester: safeSemester };
        });
        setRankings(normalizedRankings);
      }
    } catch (error) {
      console.error("Failed to fetch rankings:", error);
    }
  }, [setRankings]);

  useEffect(() => {
    fetchRankings();
  }, [fetchRankings]);

  const fetchRankingDetails = useCallback(async (rankingId: number) => {
    setIsRankingLoading(true);
    try {
      const response = await apiClient.college.getRanking(rankingId);
      if (response.success && response.data) {
        // Transform the API response
        const transformedApplications = (response.data.items || []).map(
          (item: any) => ({
            id: item.application?.id || item.id,
            ranking_item_id: item.id,
            app_id: item.application?.app_id || `APP-${item.application?.id || item.id}`,
            student_name: item.student_name || item.application?.student_info?.display_name || "未提供姓名",
            student_id: item.student_id || item.application?.student_info?.student_id || "N/A",
            academy_name: item.application?.academy_name,
            academy_code: item.application?.academy_code,
            department_name: item.application?.department_name,
            scholarship_type: item.application?.scholarship_type,
            sub_type: item.sub_type,
            eligible_subtypes: item.application?.eligible_subtypes || [],
            rank_position: item.rank_position,
            is_allocated: item.is_allocated || false,
            status: item.application?.status || "pending",
            review_status: item.application?.review_status,
          })
        );

        setRankingData({
          applications: transformedApplications,
          totalQuota: response.data.total_quota || 0,
          collegeQuota: response.data.college_quota,
          collegeQuotaBreakdown: response.data.college_quota_breakdown,
          subTypeMetadata: Array.isArray(response.data.sub_type_metadata)
            ? response.data.sub_type_metadata.reduce((acc: any, meta: any) => {
                if (meta.code) acc[meta.code] = meta;
                return acc;
              }, {})
            : response.data.sub_type_metadata || {},
          subTypeCode: response.data.sub_type_code || "default",
          academicYear: response.data.academic_year || 0,
          semester: response.data.semester,
          isFinalized: response.data.is_finalized || false,
        });
      }
    } catch (error) {
      console.error("Failed to fetch ranking details:", error);
    } finally {
      setIsRankingLoading(false);
    }
  }, [setIsRankingLoading, setRankingData]);

  const createNewRanking = useCallback(async () => {
    try {
      const academicConfig = await getAcademicConfig();
      const scholarshipConfigData = await getScholarshipConfig();

      const currentScholarshipType = availableOptions?.scholarship_types.find(
        type => type.code === activeScholarshipTab
      );

      const configScholarship = scholarshipConfigData.find(
        config => config.name === currentScholarshipType?.name
      );

      const targetScholarshipId = configScholarship?.id || scholarshipConfigData[0]?.id;
      const targetSubTypeCode = configScholarship?.subTypes[0]?.code || scholarshipConfigData[0]?.subTypes[0]?.code;
      const useYear = selectedAcademicYear || academicConfig.currentYear;
      const useSemester = selectedSemester || academicConfig.currentSemester;

      const semesterName =
        useSemester === "FIRST" ? "上學期" :
        useSemester === "SECOND" ? "下學期" : "全年";

      const response = await apiClient.college.createRanking({
        scholarship_type_id: targetScholarshipId,
        sub_type_code: targetSubTypeCode,
        academic_year: useYear,
        semester: useSemester === "YEARLY" ? null : useSemester.toLowerCase(),
        ranking_name: `${scholarshipType.name} - ${useYear} ${semesterName}`,
        force_new: true, // Always create a new ranking when user clicks "建立新排名"
      });

      if (response.success && response.data) {
        try {
          // Refresh rankings list
          await fetchRankings();
          // Select the newly created ranking
          setSelectedRanking(response.data.id);
          // Load ranking details
          await fetchRankingDetails(response.data.id);

          // Show success notification
          toast({
            title: locale === 'zh' ? '建立成功' : 'Created Successfully',
            description: locale === 'zh'
              ? `排名「${response.data.ranking_name || '新排名'}」已成功建立`
              : `Ranking "${response.data.ranking_name || 'New Ranking'}" has been created successfully`,
          });
        } catch (fetchError) {
          console.error("Failed to load ranking after creation:", fetchError);
          toast({
            title: locale === 'zh' ? '建立成功，但載入失敗' : 'Created but Failed to Load',
            description: locale === 'zh'
              ? '排名已建立，但無法自動載入。請手動重新整理頁面。'
              : 'Ranking created but failed to load automatically. Please refresh the page manually.',
            variant: "destructive",
          });
        }
      } else {
        // API returned success: false
        toast({
          title: locale === 'zh' ? '建立失敗' : 'Creation Failed',
          description: response.message || (locale === 'zh' ? '無法建立排名' : 'Failed to create ranking'),
          variant: "destructive",
        });
      }
    } catch (error) {
      console.error("Failed to create ranking:", error);
      toast({
        title: locale === 'zh' ? '建立失敗' : 'Creation Failed',
        description: error instanceof Error
          ? error.message
          : (locale === 'zh' ? '建立排名時發生錯誤' : 'An error occurred while creating the ranking'),
        variant: "destructive",
      });
    }
  }, [
    getAcademicConfig,
    getScholarshipConfig,
    availableOptions,
    activeScholarshipTab,
    scholarshipConfig,
    selectedAcademicYear,
    selectedSemester,
    scholarshipType.name,
    fetchRankings,
    setSelectedRanking,
    fetchRankingDetails,
    toast,
    locale,
  ]);

  const handleRankingChange = useCallback(async (newOrder: any[]) => {
    if (!rankingData || !selectedRanking) return;

    setRankingData({
      ...rankingData,
      applications: newOrder,
    });

    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }

    setSaveStatus('idle');

    saveTimeoutRef.current = setTimeout(async () => {
      setSaveStatus('saving');
      try {
        // Use ranking_item_id (CollegeRankingItem.id) not application_id
        const rankingItems = newOrder.map((app, index) => ({
          item_id: app.ranking_item_id,
          position: index + 1,
        }));

        // Use updateRankingOrder API instead of updateRanking
        const response = await apiClient.college.updateRankingOrder(
          selectedRanking,
          rankingItems
        );

        if (response.success) {
          setSaveStatus('saved');
          setTimeout(() => setSaveStatus('idle'), 2000);
        } else {
          setSaveStatus('error');
        }
      } catch (error) {
        console.error("Failed to save ranking:", error);
        setSaveStatus('error');
      }
    }, 500);
  }, [rankingData, selectedRanking, setRankingData, saveTimeoutRef, setSaveStatus]);

  const handleReviewApplication = useCallback(async (
    applicationId: number,
    action: 'approve' | 'reject',
    comments?: string
  ) => {
    try {
      await apiClient.college.reviewApplication(applicationId, {
        recommendation: action,
        review_comments: comments,
      });
      if (selectedRanking) {
        await fetchRankingDetails(selectedRanking);
      }
      // 同時更新 Context 中的申請列表，讓學院審核管理頁面也能看到最新狀態
      await fetchCollegeApplications(
        selectedAcademicYear,
        selectedSemester,
        activeScholarshipTab
      );
    } catch (error) {
      console.error("Failed to review application:", error);
    }
  }, [selectedRanking, fetchRankingDetails, fetchCollegeApplications, selectedAcademicYear, selectedSemester, activeScholarshipTab]);

  const handleExecuteDistribution = useCallback(async () => {
    if (selectedRanking) {
      try {
        const response = await apiClient.college.executeMatrixDistribution(selectedRanking);
        if (response.success) {
          await fetchRankingDetails(selectedRanking);
          setActiveTab("distribution");
        }
      } catch (error) {
        console.error("Failed to execute distribution:", error);
      }
    }
  }, [selectedRanking, fetchRankingDetails, setActiveTab]);

  const handleFinalizeRanking = useCallback(async (targetRankingId?: number) => {
    const rankingId = targetRankingId ?? selectedRanking;
    if (!rankingId) return;

    try {
      const response = await apiClient.college.finalizeRanking(rankingId);
      if (response.success) {
        await fetchRankings();
        if (rankingData && rankingId === selectedRanking) {
          setRankingData({ ...rankingData, isFinalized: true });
        }
        toast({
          title: locale === 'zh' ? '鎖定成功' : 'Locked Successfully',
          description: locale === 'zh' ? '排名已成功鎖定' : 'Ranking has been locked successfully',
        });
      }
    } catch (error) {
      console.error("Failed to finalize ranking:", error);
    }
  }, [selectedRanking, rankingData, fetchRankings, setRankingData, toast, locale]);

  const handleUnfinalizeRanking = useCallback(async (targetRankingId?: number) => {
    const rankingId = targetRankingId ?? selectedRanking;
    if (!rankingId) return;

    try {
      const response = await apiClient.college.unfinalizeRanking(rankingId);
      if (response.success) {
        await fetchRankings();
        if (rankingData && rankingId === selectedRanking) {
          setRankingData({ ...rankingData, isFinalized: false });
        }
        toast({
          title: locale === 'zh' ? '解除鎖定成功' : 'Unlocked Successfully',
          description: locale === 'zh' ? '排名已成功解除鎖定' : 'Ranking unlocked',
        });
      }
    } catch (error) {
      console.error("Failed to unfinalize ranking:", error);
    }
  }, [selectedRanking, rankingData, fetchRankings, setRankingData, toast, locale]);

  const handleImportExcel = useCallback(async (data: any[]) => {
    if (!selectedRanking) throw new Error("No ranking selected");

    try {
      const response = await apiClient.college.importRankingExcel(selectedRanking, data);
      if (response.success) {
        await fetchRankingDetails(selectedRanking);
      } else {
        throw new Error(response.message || "Failed to import");
      }
    } catch (error) {
      console.error("Failed to import Excel:", error);
      throw error;
    }
  }, [selectedRanking, fetchRankingDetails]);

  const handleDeleteRanking = useCallback(async () => {
    if (!rankingToDelete) return;

    try {
      const response = await apiClient.college.deleteRanking(rankingToDelete.id);
      if (response.success) {
        if (selectedRanking === rankingToDelete.id) {
          setSelectedRanking(null);
          setRankingData(null);
        }
        await fetchRankings();
        setShowDeleteRankingDialog(false);
        setRankingToDelete(null);
      }
    } catch (error) {
      console.error("Failed to delete ranking:", error);
    }
  }, [rankingToDelete, selectedRanking, fetchRankings, setSelectedRanking, setRankingData, setShowDeleteRankingDialog, setRankingToDelete]);

  const handleEditRankingName = useCallback((ranking: any) => {
    setEditingRankingId(ranking.id);
    setEditingRankingName(ranking.ranking_name);
  }, [setEditingRankingId, setEditingRankingName]);

  const handleSaveRankingName = useCallback(async (rankingId: number) => {
    try {
      const response = await apiClient.college.updateRanking(rankingId, {
        ranking_name: editingRankingName,
      });
      if (response.success) {
        await fetchRankings();
        setEditingRankingId(null);
        setEditingRankingName("");
        toast({
          title: locale === 'zh' ? '更新成功' : 'Updated Successfully',
          description: locale === 'zh' ? '排名名稱已更新' : 'Ranking name has been updated',
        });
      } else {
        toast({
          title: locale === 'zh' ? '更新失敗' : 'Update Failed',
          description: response.message || (locale === 'zh' ? '無法更新排名名稱' : 'Failed to update ranking name'),
          variant: "destructive",
        });
      }
    } catch (error) {
      console.error("Failed to update ranking name:", error);
      toast({
        title: locale === 'zh' ? '更新失敗' : 'Update Failed',
        description: locale === 'zh' ? '無法更新排名名稱' : 'Failed to update ranking name',
        variant: "destructive",
      });
    }
  }, [editingRankingName, fetchRankings, setEditingRankingId, setEditingRankingName, toast, locale]);

  const handleCancelEditRankingName = useCallback(() => {
    setEditingRankingId(null);
    setEditingRankingName("");
  }, [setEditingRankingId, setEditingRankingName]);

  return (
    <>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight">
            學生排序管理 - {scholarshipType.name}
          </h2>
          <p className="text-muted-foreground">
            管理獎學金申請的排序和排名
          </p>
        </div>
        <Button onClick={createNewRanking}>
          <Plus className="h-4 w-4 mr-2" />
          建立新排名
        </Button>
      </div>

      {/* Ranking Selection */}
      <Card>
        <CardHeader>
          <CardTitle>選擇排名</CardTitle>
          <CardDescription>選擇要管理的排名清單</CardDescription>
        </CardHeader>
        <CardContent>
          {filteredRankings.length === 0 ? (
            <div className="text-center py-12">
              <Trophy className="h-12 w-12 mx-auto mb-4 text-nycu-blue-300" />
              <h3 className="text-lg font-semibold text-nycu-navy-800 mb-2">
                暫無符合條件的排名
              </h3>
              <p className="text-nycu-navy-600 mb-4">
                {scholarshipType.name} 目前在選定的學年度與學期沒有排名
              </p>
              <Button onClick={createNewRanking} variant="outline">
                <Plus className="h-4 w-4 mr-2" />
                立即建立排名
              </Button>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {filteredRankings.map((ranking: any) => {
                const isSelected = selectedRanking === ranking.id;
                const isLocked = Boolean(ranking.is_finalized);

                return (
                  <Card
                    key={ranking.id}
                    className={`cursor-pointer ${isSelected ? 'border-blue-500 bg-blue-50/80' : 'border-slate-200'}`}
                    onClick={() => {
                      setSelectedRanking(ranking.id);
                      fetchRankingDetails(ranking.id);
                    }}
                  >
                    <CardContent className="space-y-3 p-5">
                      <div className="flex items-start justify-between">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={isLocked ? "default" : "secondary"}>
                            {isLocked ? <Lock className="h-3 w-3 mr-1" /> : <Clock className="h-3 w-3 mr-1" />}
                            {isLocked ? "已鎖定" : "進行中"}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={(e) => {
                              e.stopPropagation();
                              if (isLocked) {
                                handleUnfinalizeRanking(ranking.id);
                              } else {
                                handleFinalizeRanking(ranking.id);
                              }
                            }}
                          >
                            {isLocked ? <Lock className="h-4 w-4" /> : <LockOpen className="h-4 w-4" />}
                          </Button>
                          {!isLocked && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8 text-red-600"
                              onClick={(e) => {
                                e.stopPropagation();
                                setRankingToDelete(ranking);
                                setShowDeleteRankingDialog(true);
                              }}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          )}
                        </div>
                      </div>
                      {editingRankingId === ranking.id ? (
                        <div
                          className="flex flex-1 items-center gap-2"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <Input
                            value={editingRankingName}
                            onChange={(e) => setEditingRankingName(e.target.value)}
                            className="h-8 flex-1 text-sm"
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                handleSaveRankingName(ranking.id);
                              } else if (e.key === "Escape") {
                                handleCancelEditRankingName();
                              }
                            }}
                          />
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 p-0 text-emerald-600 hover:bg-emerald-50 hover:text-emerald-700"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleSaveRankingName(ranking.id);
                            }}
                          >
                            <Check className="h-4 w-4" />
                            <span className="sr-only">
                              {locale === "zh" ? "儲存名稱" : "Save name"}
                            </span>
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 p-0 text-slate-500 hover:bg-slate-100"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleCancelEditRankingName();
                            }}
                          >
                            <X className="h-4 w-4" />
                            <span className="sr-only">
                              {locale === "zh" ? "取消編輯" : "Cancel edit"}
                            </span>
                          </Button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <h3 className="flex-1 text-sm font-semibold text-slate-800">
                            {ranking.ranking_name}
                          </h3>
                          {!isLocked && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 p-0 text-slate-500 hover:bg-blue-50 hover:text-blue-600"
                              onClick={(e) => {
                                e.stopPropagation();
                                handleEditRankingName(ranking);
                              }}
                            >
                              <Pencil className="h-3.5 w-3.5" />
                              <span className="sr-only">
                                {locale === "zh" ? "重新命名" : "Rename"}
                              </span>
                            </Button>
                          )}
                        </div>
                      )}
                      <div className="flex items-center gap-2 text-xs text-slate-500">
                        <Trophy className="h-3.5 w-3.5" />
                        <span>申請數 {ranking.total_applications ?? 0}</span>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Ranking Details */}
      {selectedRanking && rankingData && (
        <div className="space-y-6">
          {isRankingLoading ? (
            <div className="flex items-center justify-center p-8">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
          ) : (
            <CollegeRankingTable
              applications={rankingData.applications}
              totalQuota={rankingData.totalQuota}
              subTypeCode={rankingData.subTypeCode}
              academicYear={rankingData.academicYear}
              semester={rankingData.semester}
              isFinalized={rankingData.isFinalized}
              rankingId={selectedRanking}
              onRankingChange={handleRankingChange}
              onReviewApplication={handleReviewApplication}
              onExecuteDistribution={handleExecuteDistribution}
              onFinalizeRanking={handleFinalizeRanking}
              onImportExcel={handleImportExcel}
              locale={locale}
              subTypeMeta={rankingData.subTypeMetadata}
              saveStatus={saveStatus}
            />
          )}
        </div>
      )}

      {/* Delete Ranking Dialog */}
      <Dialog open={showDeleteRankingDialog} onOpenChange={setShowDeleteRankingDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>刪除排名</DialogTitle>
            <DialogDescription>
              確定要刪除排名「{rankingToDelete?.ranking_name}」嗎？此操作無法復原。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowDeleteRankingDialog(false)}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleDeleteRanking}>
              刪除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
