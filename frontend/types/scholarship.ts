export enum ScholarshipCategory {
  PHD = "phd",
  UNDERGRADUATE = "undergraduate",
  MASTER = "master",
  SPECIAL = "special",
}

export enum ScholarshipSubType {
  NSTC = "nstc", // 國科會
  MOE = "moe", // 教育部
  GENERAL = "general", // 一般
}

export interface ScholarshipType {
  id: number;
  code: string;
  name: string;
  nameEn?: string;
  description?: string;
  descriptionEn?: string;
  category: ScholarshipCategory;
  subType: ScholarshipSubType;
  isCombined: boolean;
  parentScholarshipId?: number;
  amount: number;
  currency: string;
  eligibleStudentTypes?: string[];
  minGpa?: number;
  maxRankingPercent?: number;
  maxCompletedTerms?: number;
  requiredDocuments?: string[];
  applicationStartDate?: string;
  applicationEndDate?: string;
  status: string;
  requiresProfessorRecommendation: boolean;
  requiresResearchProposal: boolean;
  createdAt: string;
  updatedAt?: string;
  subScholarships?: ScholarshipType[];
  parentScholarship?: ScholarshipType;
  // Eligibility details (for eligible scholarships API response)
  configuration_id?: number;
  eligible_sub_types?: Array<{value: string; label: string; label_en?: string}>;
  passed?: RuleMessage[];
  warnings?: RuleMessage[];
  errors?: RuleMessage[];
}

export interface CombinedScholarshipCreate {
  name: string;
  nameEn: string;
  description: string;
  descriptionEn: string;
  category: ScholarshipCategory;
  applicationStartDate?: string;
  applicationEndDate?: string;
  subScholarships: SubScholarshipConfig[];
}

export interface SubScholarshipConfig {
  code: string;
  name: string;
  nameEn?: string;
  description?: string;
  descriptionEn?: string;
  subType: ScholarshipSubType;
  amount: number;
  minGpa?: number;
  maxRankingPercent?: number;
  requiredDocuments?: string[];
  applicationStartDate?: string;
  applicationEndDate?: string;
}

export interface ScholarshipApplication {
  scholarshipId: number;
  subScholarshipId?: number; // 用於合併獎學金
  personalStatement: string;
  researchProposal?: string;
  supportingDocuments?: number[];
}

export interface RuleMessage {
  rule_id: number | string;
  rule_name: string;
  rule_type: string;
  tag?: string;
  message: string;
  message_en?: string;
  sub_type?: string;
  priority?: number;
  is_warning?: boolean;
  is_hard_rule?: boolean;
  status?: 'data_unavailable' | 'validation_failed';
  system_message?: string;
}
