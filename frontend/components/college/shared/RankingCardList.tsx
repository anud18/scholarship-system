"use client";

import { useMemo } from "react";
import { RankingCard } from "./RankingCard";
import { Trophy, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

interface RankingCardListProps {
  rankings: any[];
  selectedRankingId: number | null;
  onRankingSelect: (id: number) => void;
  showActions?: boolean;
  showOnlyDistributed?: boolean;
  emptyStateConfig?: {
    icon?: React.ReactNode;
    title: string;
    description: string;
    actionButton?: {
      label: string;
      onClick: () => void;
    };
  };
  editingId?: number | null;
  editingName?: string;
  onEdit?: (ranking: any) => void;
  onEditNameChange?: (name: string) => void;
  onEditNameSave?: (id: number) => void;
  onEditNameCancel?: () => void;
  onDelete?: (ranking: any) => void;
  onToggleLock?: (id: number, isLocked: boolean) => void;
  locale?: "zh" | "en";
}

export function RankingCardList({
  rankings,
  selectedRankingId,
  onRankingSelect,
  showActions = false,
  showOnlyDistributed = false,
  emptyStateConfig,
  editingId,
  editingName,
  onEdit,
  onEditNameChange,
  onEditNameSave,
  onEditNameCancel,
  onDelete,
  onToggleLock,
  locale = "zh",
}: RankingCardListProps) {
  // 過濾並排序排名（按 ID 降序，最新的在前）
  const filteredRankings = useMemo(() => {
    let filtered = rankings;

    if (showOnlyDistributed) {
      filtered = rankings.filter(
        (ranking) => ranking.distribution_executed === true
      );
    }

    // 按 ID 降序排序，保證順序穩定，避免卡片跳動
    return [...filtered].sort((a, b) => b.id - a.id);
  }, [rankings, showOnlyDistributed]);

  // 空狀態
  if (filteredRankings.length === 0) {
    const defaultEmptyState = {
      icon: <Trophy className="h-12 w-12 mx-auto mb-4 text-slate-300" />,
      title: locale === "zh" ? "暫無排名" : "No Rankings",
      description:
        locale === "zh"
          ? "目前沒有符合條件的排名"
          : "No rankings match the current criteria",
    };

    const emptyState = emptyStateConfig || defaultEmptyState;

    return (
      <div className="text-center py-12">
        {emptyState.icon}
        <h3 className="text-lg font-semibold text-slate-800 mb-2">
          {emptyState.title}
        </h3>
        <p className="text-slate-600 mb-4">{emptyState.description}</p>
        {"actionButton" in emptyState && emptyState.actionButton && (
          <Button
            onClick={emptyState.actionButton.onClick}
            variant="outline"
          >
            <Plus className="h-4 w-4 mr-2" />
            {emptyState.actionButton.label}
          </Button>
        )}
      </div>
    );
  }

  // 卡片網格
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {filteredRankings.map((ranking) => (
        <RankingCard
          key={ranking.id}
          ranking={ranking}
          isSelected={selectedRankingId === ranking.id}
          showActions={showActions}
          onSelect={onRankingSelect}
          onEdit={onEdit}
          onDelete={onDelete}
          onToggleLock={(id) =>
            onToggleLock?.(id, ranking.is_finalized)
          }
          editingId={editingId}
          editingName={editingName}
          onEditNameChange={onEditNameChange}
          onEditNameSave={onEditNameSave}
          onEditNameCancel={onEditNameCancel}
          locale={locale}
        />
      ))}
    </div>
  );
}
