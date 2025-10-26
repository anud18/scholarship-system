"use client";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Search, X, Filter } from "lucide-react";

export interface FilterState {
  searchTerm: string;
  actionTypes: string[];
  dateRange: {
    start: string | null;
    end: string | null;
  };
}

interface AuditLogFiltersProps {
  filters: FilterState;
  onFiltersChange: (filters: FilterState) => void;
  totalCount: number;
  filteredCount: number;
  locale?: "zh" | "en";
}

const ACTION_TYPES = [
  "view",
  "update",
  "submit",
  "approve",
  "reject",
  "create",
  "delete",
  "request_documents",
];

const getActionLabel = (action: string, locale: "zh" | "en"): string => {
  const labels = {
    view: locale === "zh" ? "查看" : "View",
    update: locale === "zh" ? "更新" : "Update",
    submit: locale === "zh" ? "提交" : "Submit",
    approve: locale === "zh" ? "核准" : "Approve",
    reject: locale === "zh" ? "駁回" : "Reject",
    create: locale === "zh" ? "上傳" : "Upload",
    delete: locale === "zh" ? "刪除" : "Delete",
    request_documents: locale === "zh" ? "請求補件" : "Request Documents",
  };
  return labels[action as keyof typeof labels] || action;
};

export function AuditLogFilters({
  filters,
  onFiltersChange,
  totalCount,
  filteredCount,
  locale = "zh",
}: AuditLogFiltersProps) {
  const handleSearchChange = (value: string) => {
    onFiltersChange({ ...filters, searchTerm: value });
  };

  const handleActionTypeToggle = (actionType: string) => {
    const newActionTypes = filters.actionTypes.includes(actionType)
      ? filters.actionTypes.filter((t) => t !== actionType)
      : [...filters.actionTypes, actionType];
    onFiltersChange({ ...filters, actionTypes: newActionTypes });
  };

  const handleClearFilters = () => {
    onFiltersChange({
      searchTerm: "",
      actionTypes: [],
      dateRange: { start: null, end: null },
    });
  };

  const hasActiveFilters =
    filters.searchTerm ||
    filters.actionTypes.length > 0 ||
    filters.dateRange.start ||
    filters.dateRange.end;

  return (
    <div className="space-y-4 mb-6">
      {/* Search bar */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
        <Input
          type="text"
          placeholder={
            locale === "zh"
              ? "搜尋描述、用戶、IP 位址..."
              : "Search description, user, IP address..."
          }
          value={filters.searchTerm}
          onChange={(e) => handleSearchChange(e.target.value)}
          className="pl-10 pr-10 h-11 border-gray-300 focus:border-nycu-blue-500 focus:ring-nycu-blue-500"
        />
        {filters.searchTerm && (
          <button
            onClick={() => handleSearchChange("")}
            className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Action type filters */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-gray-600" />
          <span className="text-sm font-medium text-gray-700">
            {locale === "zh" ? "動作類型" : "Action Types"}
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {ACTION_TYPES.map((actionType) => {
            const isSelected = filters.actionTypes.includes(actionType);
            return (
              <Badge
                key={actionType}
                variant={isSelected ? "default" : "outline"}
                className={`cursor-pointer transition-all ${
                  isSelected
                    ? "bg-nycu-blue-600 hover:bg-nycu-blue-700"
                    : "hover:bg-gray-100"
                }`}
                onClick={() => handleActionTypeToggle(actionType)}
              >
                {getActionLabel(actionType, locale)}
              </Badge>
            );
          })}
        </div>
      </div>

      {/* Results summary and clear button */}
      <div className="flex items-center justify-between pt-2">
        <div className="text-sm text-gray-600">
          {locale === "zh" ? (
            <>
              顯示 <span className="font-semibold">{filteredCount}</span> /{" "}
              {totalCount} 筆紀錄
            </>
          ) : (
            <>
              Showing <span className="font-semibold">{filteredCount}</span> /{" "}
              {totalCount} entries
            </>
          )}
        </div>
        {hasActiveFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClearFilters}
            className="text-gray-600 hover:text-gray-900"
          >
            <X className="h-4 w-4 mr-1" />
            {locale === "zh" ? "清除篩選" : "Clear Filters"}
          </Button>
        )}
      </div>
    </div>
  );
}
