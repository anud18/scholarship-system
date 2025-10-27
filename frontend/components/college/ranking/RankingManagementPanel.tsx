"use client";

import { User } from "@/types/user";
import { useCollegeManagement } from "@/contexts/college-management-context";
import { useState, useEffect, useCallback } from "react";
import { Semester } from "@/lib/enums";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CollegeRankingTable } from "@/components/college-ranking-table";
import { ConfigSelector } from "../shared/ConfigSelector";
import { RankingCardList } from "../shared/RankingCardList";
import {
  Plus,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
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
    setSelectedAcademicYear,
    selectedSemester,
    setSelectedSemester,
    selectedCombination,
    setSelectedCombination,
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
        useSemester === Semester.FIRST ? "上學期" :
        useSemester === Semester.SECOND ? "下學期" : "全年";

      const response = await apiClient.college.createRanking({
        scholarship_type_id: targetScholarshipId,
        sub_type_code: targetSubTypeCode,
        academic_year: useYear,
        semester: useSemester === Semester.YEARLY ? null : useSemester,
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
          toast.success(
            locale === 'zh'
              ? `排名「${response.data.ranking_name || '新排名'}」已成功建立`
              : `Ranking "${response.data.ranking_name || 'New Ranking'}" has been created successfully`
          );
        } catch (fetchError) {
          console.error("Failed to load ranking after creation:", fetchError);
          toast.error(locale === 'zh'
              ? '排名已建立，但無法自動載入。請手動重新整理頁面。'
              : 'Ranking created but failed to load automatically. Please refresh the page manually.');
        }
      } else {
        // API returned success: false
        toast.error(response.message || (locale === 'zh' ? '無法建立排名' : 'Failed to create ranking'));
      }
    } catch (error) {
      console.error("Failed to create ranking:", error);
      toast.error(error instanceof Error
          ? error.message
          : (locale === 'zh' ? '建立排名時發生錯誤' : 'An error occurred while creating the ranking'));
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
      const response = await apiClient.college.reviewApplication(applicationId, {
        recommendation: action,
        review_comments: comments,
      });

      // 檢查是否自動重新執行了分發
      if (response.success && response.data) {
        const redistribution = response.data.redistribution_info;

        if (redistribution?.auto_redistributed) {
          toast.success(
            `審核完成並已自動重新執行分發，分配 ${redistribution.total_allocated} 名學生`,
            { duration: 5000 }
          );
        } else if (redistribution?.reason === "roster_exists") {
          toast.warning(
            `審核完成。此排名已開始造冊 (${redistribution.roster_info?.roster_code})，未重新執行分發`,
            { duration: 6000 }
          );
        } else {
          toast.success(`審核${action === 'approve' ? '核准' : '駁回'}完成`);
        }
      }

      // 刷新所有相關資料以確保 UI 同步
      await Promise.all([
        // 刷新當前排名的詳細資訊（包含最新的分配結果）
        selectedRanking ? fetchRankingDetails(selectedRanking) : Promise.resolve(),
        // 刷新排名列表（更新分配計數等統計資訊）
        fetchRankings(),
        // 刷新申請列表（更新學生狀態）
        fetchCollegeApplications(
          selectedAcademicYear,
          selectedSemester,
          activeScholarshipTab
        ),
      ]);
    } catch (error) {
      console.error("Failed to review application:", error);
      toast.error("審核提交失敗");
    }
  }, [selectedRanking, fetchRankingDetails, fetchRankings, fetchCollegeApplications, selectedAcademicYear, selectedSemester, activeScholarshipTab]);

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
        toast.success(locale === 'zh' ? '排名已成功鎖定' : 'Ranking has been locked successfully');
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
        toast.success(locale === 'zh' ? '排名已成功解除鎖定' : 'Ranking unlocked');
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
        toast.success(locale === 'zh' ? '排名名稱已更新' : 'Ranking name has been updated');
      } else {
        toast.error(response.message || (locale === 'zh' ? '無法更新排名名稱' : 'Failed to update ranking name'));
      }
    } catch (error) {
      console.error("Failed to update ranking name:", error);
      toast.error(locale === 'zh' ? '無法更新排名名稱' : 'Failed to update ranking name');
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

        <div className="flex items-center gap-2">
          <ConfigSelector
            selectedCombination={selectedCombination}
            availableYears={availableOptions?.academic_years || []}
            availableSemesters={availableOptions?.semesters || []}
            onCombinationChange={(value) => {
              setSelectedCombination(value);
              const [year, semester] = value.split("-");
              setSelectedAcademicYear(parseInt(year));
              setSelectedSemester(semester || undefined);
            }}
            locale={locale}
          />

          <Button onClick={createNewRanking}>
            <Plus className="h-4 w-4 mr-2" />
            建立新排名
          </Button>
        </div>
      </div>

      {/* Ranking Selection */}
      <Card>
        <CardHeader>
          <CardTitle>選擇排名</CardTitle>
          <CardDescription>選擇要管理的排名清單</CardDescription>
        </CardHeader>
        <CardContent>
          <RankingCardList
            rankings={filteredRankings}
            selectedRankingId={selectedRanking}
            onRankingSelect={(id) => {
              setSelectedRanking(id);
              fetchRankingDetails(id);
            }}
            showActions={true}
            showOnlyDistributed={false}
            emptyStateConfig={{
              title: "暫無符合條件的排名",
              description: `${scholarshipType.name} 目前在選定的學年度與學期沒有排名`,
              actionButton: {
                label: "立即建立排名",
                onClick: createNewRanking,
              },
            }}
            editingId={editingRankingId}
            editingName={editingRankingName}
            onEdit={handleEditRankingName}
            onEditNameChange={setEditingRankingName}
            onEditNameSave={handleSaveRankingName}
            onEditNameCancel={handleCancelEditRankingName}
            onDelete={(ranking) => {
              setRankingToDelete(ranking);
              setShowDeleteRankingDialog(true);
            }}
            onToggleLock={(id, isLocked) => {
              if (isLocked) {
                handleUnfinalizeRanking(id);
              } else {
                handleFinalizeRanking(id);
              }
            }}
            locale={locale}
          />
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
