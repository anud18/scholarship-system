/**
 * Quota Management Utility Functions
 *
 * Helper functions for quota calculations and status determination
 */

import type { MatrixQuotaData } from '@/types/quota';

/**
 * Calculate total quota from matrix quota data
 */
export function calculateTotalQuota(quotaData: MatrixQuotaData): number {
  let total = 0;
  Object.values(quotaData.phd_quotas).forEach(colleges => {
    Object.values(colleges).forEach(cell => {
      total += cell.total_quota;
    });
  });
  return total;
}

/**
 * Calculate usage percentage
 */
export function calculateUsagePercentage(used: number, total: number): number {
  if (total === 0) return 0;
  return Math.round((used / total) * 100);
}

/**
 * Get quota status color based on usage percentage
 */
export function getQuotaStatusColor(percentage: number): string {
  if (percentage >= 95) return 'red';
  if (percentage >= 80) return 'orange';
  if (percentage >= 50) return 'yellow';
  return 'green';
}
