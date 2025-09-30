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
