import apiClient, {
  type ApiResponse,
  type NotificationResponse,
  type AnnouncementCreate,
  type AnnouncementUpdate,
} from "@/lib/api";

export const announcementsService = {
  getAll: async (
    page: number = 1,
    size: number = 10
  ): Promise<ApiResponse<NotificationResponse[]>> => {
    const response = await apiClient.admin.getAllAnnouncements(page, size);
    // Transform paginated response to array for backwards compatibility
    if (response.success && response.data && 'items' in response.data) {
      return {
        success: response.success,
        message: response.message,
        data: response.data.items as NotificationResponse[],
      };
    }
    return response as unknown as ApiResponse<NotificationResponse[]>;
  },

  create: async (
    data: AnnouncementCreate
  ): Promise<ApiResponse<NotificationResponse>> => {
    return apiClient.admin.createAnnouncement(data);
  },

  update: async (
    id: number,
    data: AnnouncementUpdate
  ): Promise<ApiResponse<NotificationResponse>> => {
    return apiClient.admin.updateAnnouncement(id, data);
  },

  delete: async (id: number): Promise<ApiResponse<void>> => {
    const response = await apiClient.admin.deleteAnnouncement(id);
    // Transform message response to void for backwards compatibility
    return {
      success: response.success,
      message: response.message,
      data: undefined,
    };
  },
};
