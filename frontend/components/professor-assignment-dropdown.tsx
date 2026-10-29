"use client";

import { useState, useEffect } from "react";
import { logger } from "@/lib/utils/logger";
import { ErrorBoundary } from "@/components/error-boundary";
import { Check, ChevronsUpDown, Search, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Badge } from "@/components/ui/badge";
import apiClient from "@/lib/api";

const SEARCH_DEBOUNCE_MS = 300;

interface Professor {
  nycu_id: string;
  name: string;
  dept_code: string;
  dept_name: string;
  email?: string;
}

interface ProfessorAssignmentDropdownProps {
  applicationId: number;
  currentProfessorId?: string;
  currentProfessorName?: string;
  onAssigned?: (professor: Professor) => void;
  disabled?: boolean;
  compact?: boolean;
}

function ProfessorAssignmentDropdownInner({
  applicationId,
  currentProfessorId,
  currentProfessorName,
  onAssigned,
  disabled = false,
  compact = false,
}: ProfessorAssignmentDropdownProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [professors, setProfessors] = useState<Professor[]>([]);
  // Set on a successful assign until the caller passes the new current professor
  const [assignedProfessor, setAssignedProfessor] = useState<Professor | null>(
    null
  );
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [assigning, setAssigning] = useState(false);
  // Query the current `professors` list was fetched for; null until the first load
  const [loadedQuery, setLoadedQuery] = useState<string | null>(null);

  useEffect(() => {
    setAssignedProfessor(null);
  }, [currentProfessorId]);

  const currentNycuId = assignedProfessor?.nycu_id ?? currentProfessorId;
  const currentName = assignedProfessor?.name ?? currentProfessorName;

  // The list is only fetched while the popover is open. Compact dropdowns
  // render once per table row, and fetching on mount (N rows x 2 requests)
  // tripped the nginx rate limit and 429'd the rest of the page (#1499).
  const fetchProfessors = async (searchQuery: string) => {
    setLoading(true);
    try {
      const response = await apiClient.admin.getProfessors(searchQuery);
      if (!response.success || !response.data) {
        throw new Error(response.message || "Failed to fetch professors");
      }
      setProfessors(response.data as Professor[]);
      setLoadedQuery(searchQuery);
    } catch (error) {
      logger.error("Failed to fetch professors", { error: error });
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  };

  // Fetch while open: immediately on open, debounced while typing.
  // After a failure, wait for 重試 rather than re-firing at a rate limiter.
  useEffect(() => {
    if (loadError) return;
    if (!open || search === loadedQuery) return;
    const delay = search === "" ? 0 : SEARCH_DEBOUNCE_MS;
    const timer = setTimeout(() => fetchProfessors(search), delay);
    return () => clearTimeout(timer);
  }, [open, search, loadedQuery, loadError]);

  const handleSearch = (value: string) => {
    setSearch(value);
  };

  const handleAssign = async (professor: Professor) => {
    setAssigning(true);
    try {
      const response = await apiClient.admin.assignProfessor(
        applicationId,
        professor.nycu_id
      );
      if (response.success) {
        setAssignedProfessor(professor);
        setOpen(false);
        onAssigned?.(professor);
      }
    } catch (error) {
      logger.error("Failed to assign professor", { error: error });
    } finally {
      setAssigning(false);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled || assigning}
          className={compact ? "h-8 px-2 text-xs" : "w-full justify-between"}
        >
          {compact ? (
            // Compact mode for when professor is already assigned
            currentNycuId ? (
              <span className="text-xs">修改</span>
            ) : (
              <span className="text-xs">選擇</span>
            )
          ) : // Full mode for when no professor is assigned
          currentNycuId ? (
            <div className="flex items-center gap-2">
              <User className="h-4 w-4" />
              {currentName && <span>{currentName}</span>}
              <Badge variant="secondary">{currentNycuId}</Badge>
            </div>
          ) : (
            <span className="text-muted-foreground">選擇教授...</span>
          )}
          {!compact && (
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[400px] p-0">
        {/* The backend already filters by name/NYCU ID; cmdk's own filter
            matches only the item value (nycu_id) and would hide name hits */}
        <Command shouldFilter={false}>
          <CommandInput
            placeholder="搜尋姓名或 NYCU ID..."
            value={search}
            onValueChange={handleSearch}
          />
          <CommandList>
            {loadError ? (
              <div className="flex items-center justify-between gap-2 px-3 py-4 text-sm text-red-600">
                <span>載入教授清單失敗，請稍後再試</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setLoadError(false)}
                >
                  重試
                </Button>
              </div>
            ) : loading || loadedQuery === null ? (
              <CommandEmpty>載入中...</CommandEmpty>
            ) : professors.length === 0 ? (
              <CommandEmpty>找不到符合的教授</CommandEmpty>
            ) : (
              <CommandGroup>
                {professors.map(professor => (
                  <CommandItem
                    key={professor.nycu_id}
                    value={professor.nycu_id}
                    onSelect={() => handleAssign(professor)}
                  >
                    <Check
                      className={cn(
                        "mr-2 h-4 w-4",
                        currentNycuId === professor.nycu_id
                          ? "opacity-100"
                          : "opacity-0"
                      )}
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{professor.name}</span>
                        <Badge variant="outline" className="text-xs">
                          {professor.nycu_id}
                        </Badge>
                      </div>
                      <div className="text-sm text-muted-foreground">
                        {professor.dept_name}
                      </div>
                    </div>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

// Export wrapped component with error boundary
export function ProfessorAssignmentDropdown(
  props: ProfessorAssignmentDropdownProps
) {
  return (
    <ErrorBoundary
      onError={(error, errorInfo) => {
        logger.error("Professor Assignment Dropdown Error:", error, errorInfo);
      }}
    >
      <ProfessorAssignmentDropdownInner {...props} />
    </ErrorBoundary>
  );
}
