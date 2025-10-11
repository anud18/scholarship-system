import { LucideIcon } from "lucide-react";

export interface WizardStep {
  id: string;
  label: string;
  label_en: string;
  icon: LucideIcon;
  description?: string;
  description_en?: string;
  isCompleted: boolean;
  isAccessible: boolean;
}

export interface WizardState {
  currentStepIndex: number;
  steps: WizardStep[];
  agreedToTerms: boolean;
  studentDataConfirmed: boolean;
  personalInfoCompleted: boolean;
}

export interface WizardContextType extends WizardState {
  goToStep: (stepIndex: number) => void;
  nextStep: () => void;
  prevStep: () => void;
  markStepCompleted: (stepId: string) => void;
  setAgreedToTerms: (agreed: boolean) => void;
  setStudentDataConfirmed: (confirmed: boolean) => void;
  setPersonalInfoCompleted: (completed: boolean) => void;
  canProceedToNext: () => boolean;
}
