"use client";

import { useState, useEffect } from "react";
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
  onAssigned?: (professor: Professor) => void;
  disabled?: boolean;
  compact?: boolean;
}

function ProfessorAssignmentDropdownInner({
  applicationId,
  currentProfessorId,
  onAssigned,
  disabled = false,
  compact = false,
}: ProfessorAssignmentDropdownProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [professors, setProfessors] = useState<Professor[]>([]);
  const [selectedProfessor, setSelectedProfessor] = useState<Professor | null>(
    null
  );
  const [loading, setLoading] = useState(false);
  const [assigning, setAssigning] = useState(false);

  // Load professors
  useEffect(() => {
    fetchProfessors("");
  }, []);

  // Set current professor if exists
  useEffect(() => {
    if (currentProfessorId && professors.length > 0) {
      const current = professors.find(p => p.nycu_id === currentProfessorId);
      if (current) setSelectedProfessor(current);
    }
  }, [currentProfessorId, professors]);

  const fetchProfessors = async (searchQuery: string) => {
    setLoading(true);
    try {
      const response = await apiClient.admin.getProfessors(searchQuery);
      if (response.success && response.data) {
        setProfessors(response.data);
      }
    } catch (error) {
      console.error("Failed to fetch professors:", error);
    } finally {
      setLoading(false);
    }
  };

  // Debounced search effect to prevent memory leaks
  useEffect(() => {
    const timer = setTimeout(() => {
      if (search !== undefined) {
        // Only fetch if search has been set
        fetchProfessors(search);
      }
    }, 300);

    return () => clearTimeout(timer); // Proper cleanup
  }, [search]);

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
        setSelectedProfessor(professor);
        setOpen(false);
        onAssigned?.(professor);
      }
    } catch (error) {
      console.error("Failed to assign professor:", error);
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
            selectedProfessor ? (
              <span className="text-xs">修改</span>
            ) : (
              <span className="text-xs">選擇</span>
            )
          ) : // Full mode for when no professor is assigned
          selectedProfessor ? (
            <div className="flex items-center gap-2">
              <User className="h-4 w-4" />
              <span>{selectedProfessor.name}</span>
              <Badge variant="secondary">{selectedProfessor.nycu_id}</Badge>
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
        <Command>
          <CommandInput
            placeholder="搜尋姓名或 NYCU ID..."
            value={search}
            onValueChange={handleSearch}
          />
          <CommandList>
            {loading ? (
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
                        selectedProfessor?.nycu_id === professor.nycu_id
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
        console.error("Professor Assignment Dropdown Error:", error, errorInfo);
      }}
    >
      <ProfessorAssignmentDropdownInner {...props} />
    </ErrorBoundary>
  );
}
