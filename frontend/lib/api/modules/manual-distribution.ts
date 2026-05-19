/**
 * Manual Distribution API Module
 *
 * Provides endpoints for admin to manually allocate scholarships to students.
 * Replaces the automated quota/matrix distribution with a UI-driven workflow.
 */

import { typedClient } from "../typed-client";
import { toApiResponse } from "../compat";
import type { ApiResponse } from "../types";

export interface DistributionStudent {
  ranking_item_id: number;
  application_id: number;
  rank_position: number;
  applied_sub_types: string[];
  rejected_sub_types: string[];
  allocated_sub_type: string | null;
  allocation_year: number | null;
  status: string;
  college_rejected: boolean;
  college_code: string;
  college_name: string;
  department_name: string;
  term_count: number | null;
  student_name: string;
  nationality: string;
  enrollment_date: string;
  student_id: string;
  application_identity: string;
  is_renewal: boolean;
  renewal_year: number | null;
  renewal_sub_type: string | null;
  received_months: number | null;
  received_months_source: string | null;
  is_supplementary: boolean;
}
