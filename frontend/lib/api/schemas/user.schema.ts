/**
 * Zod schemas for User API responses
 *
 * Usage example:
 *
 * ```typescript
 * import { UserSchema } from '@/lib/api/schemas/user.schema';
 * import { api } from '@/lib/api';
 *
 * // Runtime validation - automatically validates in development
 * const response = await api.users.getCurrentUser({
 *   schema: UserSchema,
 *   validateResponse: true  // Force validation in production
 * });
 * ```
 */

import { z } from 'zod';

export const UserRoleSchema = z.enum([
  'student',
  'professor',
  'college',
  'admin',
  'super_admin',
]);

export const UserTypeSchema = z.enum(['student', 'employee']);

export const UserStatusSchema = z.enum(['在學', '畢業', '在職', '退休']);

export const UserSchema = z.object({
  id: z.string(),
  nycu_id: z.string(),
  email: z.string().email(),
  name: z.string(),
  role: UserRoleSchema,
  user_type: UserTypeSchema.optional(),
  status: UserStatusSchema.optional(),
  dept_code: z.string().optional(),
  dept_name: z.string().optional(),
  comment: z.string().optional(),
  last_login_at: z.string().optional(),
  created_at: z.string(),
  updated_at: z.string(),
  raw_data: z.record(z.any()).optional(),
  // Backward compatibility fields
  username: z.string().optional(),
  full_name: z.string().optional(),
  is_active: z.boolean().optional(),
});

export const UserListResponseSchema = z.object({
  items: z.array(UserSchema),
  total: z.number(),
  page: z.number(),
  size: z.number(),
  pages: z.number(),
});

export type User = z.infer<typeof UserSchema>;
export type UserListResponse = z.infer<typeof UserListResponseSchema>;
