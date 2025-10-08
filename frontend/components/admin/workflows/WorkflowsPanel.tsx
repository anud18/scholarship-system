"use client";

import { ScholarshipWorkflowMermaid } from "@/components/ScholarshipWorkflowMermaid";
import { useWorkflows } from "@/hooks/admin/use-workflows";

export function WorkflowsPanel() {
  const {
    configurations,
    selectedConfigurationId,
    setSelectedConfigurationId,
    isLoading,
  } = useWorkflows();

  return (
    <div className="space-y-4">
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="flex items-center gap-3">
            <div className="animate-spin rounded-full h-6 w-6 border-2 border-nycu-blue-600 border-t-transparent"></div>
            <span className="text-nycu-navy-600">載入獎學金配置中...</span>
          </div>
        </div>
      ) : (
        <ScholarshipWorkflowMermaid
          configurations={configurations}
          selectedConfigId={selectedConfigurationId ?? undefined}
          onConfigChange={setSelectedConfigurationId}
        />
      )}
    </div>
  );
}
