"use client";

import React from "react";
import { Check, Circle } from "lucide-react";
import { cn } from "@/lib/utils";
import { WizardStep } from "./types";
import { Card } from "@/components/ui/card";

interface ApplicationSidebarProps {
  steps: WizardStep[];
  currentStepIndex: number;
  onStepClick: (stepIndex: number) => void;
  locale: "zh" | "en";
}

export function ApplicationSidebar({
  steps,
  currentStepIndex,
  onStepClick,
  locale,
}: ApplicationSidebarProps) {
  return (
    <div className="w-64 min-h-screen border-r border-gray-200 bg-gradient-to-b from-nycu-blue-50 to-white p-6">
      <div className="mb-8">
        <h2 className="text-xl font-bold text-nycu-navy-800 mb-2">
          {locale === "zh" ? "申請流程" : "Application Process"}
        </h2>
        <p className="text-sm text-nycu-navy-600">
          {locale === "zh"
            ? "請依序完成以下步驟"
            : "Complete the following steps in order"}
        </p>
      </div>

      <div className="space-y-2">
        {steps.map((step, index) => {
          const isActive = index === currentStepIndex;
          const isCompleted = step.isCompleted;
          const isAccessible = step.isAccessible;

          return (
            <button
              key={step.id}
              onClick={() => {
                if (isAccessible) {
                  onStepClick(index);
                }
              }}
              disabled={!isAccessible}
              className={cn(
                "w-full text-left transition-all duration-200",
                !isAccessible && "cursor-not-allowed opacity-50"
              )}
            >
              <Card
                className={cn(
                  "p-4 transition-all duration-200",
                  isActive &&
                    "border-nycu-blue-600 bg-nycu-blue-50 shadow-md",
                  isCompleted && !isActive && "border-green-200 bg-green-50/50",
                  !isActive && !isCompleted && "hover:border-nycu-blue-200"
                )}
              >
                <div className="flex items-start gap-3">
                  {/* Step indicator */}
                  <div
                    className={cn(
                      "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center transition-all",
                      isActive &&
                        "bg-nycu-blue-600 text-white ring-4 ring-nycu-blue-100",
                      isCompleted &&
                        !isActive &&
                        "bg-green-500 text-white",
                      !isActive &&
                        !isCompleted &&
                        "bg-gray-200 text-gray-500"
                    )}
                  >
                    {isCompleted ? (
                      <Check className="w-5 h-5" />
                    ) : (
                      <span className="text-sm font-semibold">{index + 1}</span>
                    )}
                  </div>

                  {/* Step content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <step.icon
                        className={cn(
                          "w-4 h-4",
                          isActive && "text-nycu-blue-600",
                          isCompleted && !isActive && "text-green-600",
                          !isActive && !isCompleted && "text-gray-500"
                        )}
                      />
                      <h3
                        className={cn(
                          "font-semibold text-sm",
                          isActive && "text-nycu-blue-800",
                          isCompleted && !isActive && "text-green-800",
                          !isActive && !isCompleted && "text-gray-700"
                        )}
                      >
                        {locale === "zh" ? step.label : step.label_en}
                      </h3>
                    </div>
                    {step.description && (
                      <p
                        className={cn(
                          "text-xs mt-1",
                          isActive && "text-nycu-blue-700",
                          isCompleted && !isActive && "text-green-700",
                          !isActive && !isCompleted && "text-gray-600"
                        )}
                      >
                        {locale === "zh" ? step.description : step.description_en}
                      </p>
                    )}
                  </div>
                </div>
              </Card>
            </button>
          );
        })}
      </div>

      {/* Progress indicator */}
      <div className="mt-8 p-4 bg-white rounded-lg border border-gray-200">
        <div className="flex items-center justify-between text-sm mb-2">
          <span className="text-gray-600">
            {locale === "zh" ? "整體進度" : "Overall Progress"}
          </span>
          <span className="font-semibold text-nycu-blue-700">
            {Math.round(
              (steps.filter((s) => s.isCompleted).length / steps.length) * 100
            )}
            %
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2">
          <div
            className="bg-gradient-to-r from-nycu-blue-500 to-nycu-blue-600 h-2 rounded-full transition-all duration-500"
            style={{
              width: `${
                (steps.filter((s) => s.isCompleted).length / steps.length) * 100
              }%`,
            }}
          ></div>
        </div>
      </div>
    </div>
  );
}
