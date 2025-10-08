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
    return apiClient.admin.getAllAnnouncements(page, size);
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
    return apiClient.admin.deleteAnnouncement(id);
  },
};
