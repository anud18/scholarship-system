"use client";

import React, { useState, useEffect } from "react";
import { ApplicationSidebar } from "./ApplicationSidebar";
import { NoticeAgreementStep } from "./steps/NoticeAgreementStep";
import { StudentDataReviewStep } from "./steps/StudentDataReviewStep";
import { ScholarshipApplicationStep } from "./steps/ScholarshipApplicationStep";
import { WizardStep } from "./types";
import { FileText, User, Award } from "lucide-react";
import { User as UserType } from "@/types/user";
import { Application } from "@/lib/api";
import { getTranslation } from "@/lib/i18n";

interface StudentApplicationWizardProps {
  user: UserType;
  locale: "zh" | "en";
  onApplicationComplete?: () => void;
  editingApplication?: Application | null;
  initialStep?: number;
}

export function StudentApplicationWizard({
  user,
  locale,
  onApplicationComplete,
  editingApplication,
  initialStep,
}: StudentApplicationWizardProps) {
  const [currentStepIndex, setCurrentStepIndex] = useState(
    editingApplication && initialStep !== undefined ? initialStep : 0
  );

  const [agreedToTerms, setAgreedToTerms] = useState(
    editingApplication && initialStep !== undefined && initialStep >= 1
      ? true
      : false
  );

  const [studentDataConfirmed, setStudentDataConfirmed] = useState(
    editingApplication && initialStep !== undefined && initialStep >= 2
      ? true
      : false
  );

  const initialSteps: WizardStep[] = [
    {
      id: "notice",
      label: getTranslation("zh", "wizard.steps.notice.label"),
      label_en: getTranslation("en", "wizard.steps.notice.label"),
      icon: FileText,
      description: getTranslation("zh", "wizard.steps.notice.description"),
      description_en: getTranslation("en", "wizard.steps.notice.description"),
      isCompleted: false,
      isAccessible: true,
    },
    {
      id: "student-data",
      label: getTranslation("zh", "wizard.steps.review.label"),
      label_en: getTranslation("en", "wizard.steps.review.label"),
      icon: User,
      description: getTranslation("zh", "wizard.steps.review.description"),
      description_en: getTranslation("en", "wizard.steps.review.description"),
      isCompleted: false,
      isAccessible: false,
    },
    {
      id: "scholarship",
      label: getTranslation("zh", "wizard.steps.apply.label"),
      label_en: getTranslation("en", "wizard.steps.apply.label"),
      icon: Award,
      description: getTranslation("zh", "wizard.steps.apply.description"),
      description_en: getTranslation("en", "wizard.steps.apply.description"),
      isCompleted: false,
      isAccessible: false,
    },
  ];

  const [steps, setSteps] = useState<WizardStep[]>(initialSteps);

  useEffect(() => {
    setSteps((prevSteps) => {
      const newSteps = [...prevSteps];
      newSteps[0].isAccessible = true;
      newSteps[0].isCompleted = agreedToTerms;
      newSteps[1].isAccessible = agreedToTerms;
      newSteps[1].isCompleted = studentDataConfirmed;
      newSteps[2].isAccessible = studentDataConfirmed;
      return newSteps;
    });
  }, [agreedToTerms, studentDataConfirmed]);

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [currentStepIndex]);

  const goToStep = (stepIndex: number) => {
    if (
      stepIndex >= 0 &&
      stepIndex < steps.length &&
      steps[stepIndex].isAccessible
    ) {
      setCurrentStepIndex(stepIndex);
    }
  };

  const nextStep = () => {
    if (currentStepIndex < steps.length - 1) {
      setCurrentStepIndex(currentStepIndex + 1);
    }
  };

  const prevStep = () => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex(currentStepIndex - 1);
    }
  };

  const handleNoticeAgree = (agreed: boolean) => {
    setAgreedToTerms(agreed);
  };

  const handleStudentDataConfirm = (confirmed: boolean) => {
    setStudentDataConfirmed(confirmed);
  };

  const handleApplicationComplete = () => {
    setSteps((prevSteps) => {
      const newSteps = [...prevSteps];
      newSteps[2].isCompleted = true;
      return newSteps;
    });
    if (onApplicationComplete) {
      onApplicationComplete();
    }
  };

  const renderCurrentStep = () => {
    const currentStep = steps[currentStepIndex];
    switch (currentStep.id) {
      case "notice":
        return (
          <NoticeAgreementStep
            agreedToTerms={agreedToTerms}
            onAgree={handleNoticeAgree}
            onNext={nextStep}
            locale={locale}
          />
        );
      case "student-data":
        return (
          <StudentDataReviewStep
            onNext={nextStep}
            onBack={prevStep}
            onConfirm={handleStudentDataConfirm}
            locale={locale}
          />
        );
      case "scholarship":
        return (
          <ScholarshipApplicationStep
            onBack={prevStep}
            onComplete={handleApplicationComplete}
            locale={locale}
            userId={parseInt(user.id) || 1}
            editingApplication={editingApplication}
          />
        );
      default:
        return null;
    }
  };

  return (
    <div className="flex min-h-screen bg-gradient-to-br from-slate-50 to-nycu-blue-50">
      <div className="hidden lg:block">
        <ApplicationSidebar
          steps={steps}
          currentStepIndex={currentStepIndex}
          onStepClick={goToStep}
          locale={locale}
        />
      </div>

      <div className="lg:hidden fixed top-0 left-0 right-0 z-10 bg-white border-b border-gray-200 p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600">
              {getTranslation(locale, "wizard.mobile_step_label")}{" "}
              {currentStepIndex + 1} / {steps.length}
            </p>
            <p className="font-semibold text-nycu-navy-800">
              {locale === "zh"
                ? steps[currentStepIndex].label
                : steps[currentStepIndex].label_en}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {steps.map((step, index) => (
              <div
                key={step.id}
                className={`w-2 h-2 rounded-full transition-all ${
                  index === currentStepIndex
                    ? "bg-nycu-blue-600 w-6"
                    : step.isCompleted
                      ? "bg-green-500"
                      : "bg-gray-300"
                }`}
              />
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 p-6 lg:p-12 mt-20 lg:mt-0">
        <div className="max-w-4xl mx-auto">{renderCurrentStep()}</div>
      </div>
    </div>
  );
}
