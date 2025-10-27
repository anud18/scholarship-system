"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Trophy,
  CheckCircle,
  Lock,
  LockOpen,
  Clock,
  Trash2,
  Pencil,
  Check,
  X,
  Award,
} from "lucide-react";

interface RankingCardProps {
  ranking: {
    id: number;
    ranking_name: string;
    is_finalized: boolean;
    distribution_executed: boolean;
    total_applications: number;
    allocated_count?: number;
    distribution_date?: string;
  };
  isSelected?: boolean;
  showActions?: boolean;
  onSelect: (rankingId: number) => void;
  onEdit?: (ranking: any) => void;
  onDelete?: (ranking: any) => void;
  onToggleLock?: (rankingId: number) => void;
  editingId?: number | null;
  editingName?: string;
  onEditNameChange?: (name: string) => void;
  onEditNameSave?: (rankingId: number) => void;
  onEditNameCancel?: () => void;
  locale?: "zh" | "en";
}

export function RankingCard({
  ranking,
  isSelected = false,
  showActions = false,
  onSelect,
  onEdit,
  onDelete,
  onToggleLock,
  editingId,
  editingName,
  onEditNameChange,
  onEditNameSave,
  onEditNameCancel,
  locale = "zh",
}: RankingCardProps) {
  const isLocked = Boolean(ranking.is_finalized);
  const isDistributed = Boolean(ranking.distribution_executed);
  const canBeUsedForRoster = isDistributed && isLocked;
  const isEditing = editingId === ranking.id;

  return (
    <Card
      className={`cursor-pointer transition-all duration-200 relative ${
        isSelected
          ? "border-blue-500 bg-blue-50/80 ring-2 ring-blue-300"
          : canBeUsedForRoster
            ? "border-emerald-500 border-2 bg-gradient-to-br from-emerald-50 to-white ring-4 ring-emerald-200 ring-offset-2 shadow-xl hover:shadow-2xl hover:ring-emerald-300 hover:scale-[1.02]"
            : "border-slate-200 hover:border-slate-300"
      }`}
      onClick={() => onSelect(ranking.id)}
    >
      {/* 可用於造冊的醒目標籤 */}
      {canBeUsedForRoster && (
        <div className="absolute -top-3 left-4 z-10">
          <div className="flex items-center gap-1.5 px-3 py-1 bg-gradient-to-r from-emerald-600 to-emerald-500 text-white rounded-full shadow-lg border-2 border-white">
            <Trophy className="h-3.5 w-3.5 animate-pulse" />
            <span className="text-xs font-bold">
              {locale === "zh" ? "此排名將用於造冊" : "Ready for Roster"}
            </span>
          </div>
        </div>
      )}

      {/* 左側綠色指示條 */}
      {canBeUsedForRoster && (
        <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-gradient-to-b from-emerald-500 via-emerald-600 to-emerald-500 rounded-l-lg" />
      )}

      <CardContent className="space-y-3 p-5">
        {/* 徽章區域 */}
        <div className="flex items-start justify-between">
          <div className="flex flex-wrap items-center gap-2">
            {/* 鎖定狀態徽章 */}
            <Badge variant={isLocked ? "default" : "secondary"}>
              {isLocked ? (
                <Lock className="h-3 w-3 mr-1" />
              ) : (
                <Clock className="h-3 w-3 mr-1" />
              )}
              {isLocked
                ? locale === "zh"
                  ? "已鎖定"
                  : "Locked"
                : locale === "zh"
                  ? "進行中"
                  : "In Progress"}
            </Badge>

            {/* 分發狀態徽章 */}
            {isDistributed && (
              <Badge
                variant="secondary"
                className="bg-blue-100 text-blue-800 border-blue-200"
              >
                <CheckCircle className="h-3 w-3 mr-1" />
                {locale === "zh" ? "已執行分發" : "Distributed"}
              </Badge>
            )}
          </div>

          {/* 操作按鈕區域 */}
          {showActions && (
            <div className="flex items-center gap-1">
              {/* 鎖定/解鎖按鈕 */}
              {onToggleLock && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleLock(ranking.id);
                  }}
                >
                  {isLocked ? (
                    <Lock className="h-4 w-4" />
                  ) : (
                    <LockOpen className="h-4 w-4" />
                  )}
                </Button>
              )}

              {/* 刪除按鈕（只在未鎖定時顯示） */}
              {!isLocked && onDelete && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-red-600"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(ranking);
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </div>
          )}
        </div>

        {/* 排名名稱區域 */}
        {isEditing ? (
          <div
            className="flex flex-1 items-center gap-2"
            onClick={(e) => e.stopPropagation()}
          >
            <Input
              value={editingName}
              onChange={(e) => onEditNameChange?.(e.target.value)}
              className="h-8 flex-1 text-sm"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  onEditNameSave?.(ranking.id);
                } else if (e.key === "Escape") {
                  onEditNameCancel?.();
                }
              }}
            />
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 p-0 text-emerald-600 hover:bg-emerald-50"
              onClick={(e) => {
                e.stopPropagation();
                onEditNameSave?.(ranking.id);
              }}
            >
              <Check className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 p-0 text-slate-500 hover:bg-slate-100"
              onClick={(e) => {
                e.stopPropagation();
                onEditNameCancel?.();
              }}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <h3 className="flex-1 text-sm font-semibold text-slate-800">
              {ranking.ranking_name}
            </h3>
            {!isLocked && showActions && onEdit && (
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 p-0 text-slate-500 hover:bg-blue-50 hover:text-blue-600"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(ranking);
                }}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        )}

        {/* 統計資訊 */}
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Trophy className="h-3.5 w-3.5" />
          <span>
            {locale === "zh" ? "申請數" : "Applications"}{" "}
            {ranking.total_applications ?? 0}
          </span>
          {isDistributed && ranking.allocated_count !== undefined && (
            <>
              <span className="text-slate-300">•</span>
              <Award className="h-3.5 w-3.5 text-emerald-600" />
              <span className="text-emerald-600 font-medium">
                {locale === "zh" ? "正取" : "Admitted"}{" "}
                {ranking.allocated_count}
              </span>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
