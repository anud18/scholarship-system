/**
 * Audit log types for application operations
 */

export interface AuditLog {
  id: number;
  action: string;
  user_id: number;
  user_name: string;
  description: string;
  old_values?: Record<string, any>;
  new_values?: Record<string, any>;
  ip_address?: string;
  request_method?: string;
  request_url?: string;
  status: string;
  error_message?: string;
  meta_data?: Record<string, any>;
  created_at: string;
}

export interface AuditTrailResponse {
  success: boolean;
  message: string;
  data: AuditLog[];
}
