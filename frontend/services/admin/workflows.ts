import apiClient, { type ApiResponse, type Workflow } from "@/lib/api";

export const workflowsService = {
  getAll: async (): Promise<ApiResponse<Workflow[]>> => {
    return apiClient.admin.getWorkflows();
  },
};
