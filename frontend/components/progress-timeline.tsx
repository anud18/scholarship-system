"use client";

import { CheckCircle, Clock, Circle, AlertCircle, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

interface TimelineStep {
  id: string;
  title: string;
  description?: string;
  status: "completed" | "current" | "pending" | "rejected";
  date?: string;
  estimatedDate?: string;
  stepNumber?: number;
  totalSteps?: number;
  reviewer?: {
    name: string;
    avatar?: string;
  };
  timeElapsed?: string;
}

interface ProgressTimelineProps {
  steps: TimelineStep[];
  className?: string;
  orientation?: "vertical" | "horizontal";
  isLoading?: boolean;
  showProgress?: boolean;
}

export function ProgressTimeline({
  steps,
  className,
  orientation = "vertical",
  isLoading = false,
  showProgress = true,
}: ProgressTimelineProps) {
  // Calculate overall progress
  const completedSteps = steps.filter(s => s.status === "completed").length;
  const totalSteps = steps.length;
  const progressPercentage = Math.round((completedSteps / totalSteps) * 100);
  const currentStepIndex = steps.findIndex(s => s.status === "current");

  const getStepIcon = (status: TimelineStep["status"]) => {
    switch (status) {
      case "completed":
        return <CheckCircle className="h-5 w-5" />;
      case "current":
        return <Clock className="h-5 w-5" />;
      case "rejected":
        return <AlertCircle className="h-5 w-5" />;
      default:
        return <Circle className="h-5 w-5" />;
    }
  };

  const getStepColor = (status: TimelineStep["status"]) => {
    switch (status) {
      case "completed":
        return {
          bg: "bg-emerald-50 border-emerald-200",
          text: "text-emerald-700",
          icon: "text-emerald-600",
          line: "bg-emerald-500",
        };
      case "current":
        return {
          bg: "bg-blue-50 border-blue-200",
          text: "text-blue-700",
          icon: "text-blue-600",
          line: "bg-blue-500",
        };
      case "rejected":
        return {
          bg: "bg-rose-50 border-rose-200",
          text: "text-rose-700",
          icon: "text-rose-600",
          line: "bg-rose-500",
        };
      default:
        return {
          bg: "bg-gray-50 border-gray-200",
          text: "text-gray-500",
          icon: "text-gray-400",
          line: "bg-gray-300",
        };
    }
  };

  // 水平顯示模式 - 現代卡片設計
  if (orientation === "horizontal") {
    return (
      <div className={cn("space-y-6", className)}>
        {/* Overall Progress Indicator */}
        {showProgress && (
          <div className="mb-6">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm font-medium text-gray-700">審核進度</span>
              <span className="text-sm font-semibold text-blue-600">
                {currentStepIndex >= 0 ? currentStepIndex + 1 : completedSteps}/{totalSteps} ({progressPercentage}%)
              </span>
            </div>
            <Progress value={progressPercentage} className="h-2" />
          </div>
        )}

        {/* 載入狀態 */}
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <span className="ml-2 text-gray-600">載入中...</span>
          </div>
        )}

        {/* Timeline Steps */}
        <div className="flex items-center justify-between">
          {steps.map((step, index) => {
            const colors = getStepColor(step.status);
            const isLast = index === steps.length - 1;

            return (
              <div key={step.id} className="flex items-center flex-1">
                {/* Step Node with Card */}
                <div className="flex flex-col items-center">
                  {/* Icon Circle */}
                  <div
                    className={cn(
                      "flex h-10 w-10 items-center justify-center rounded-full border-2 z-10 bg-white shadow-md transition-all duration-300",
                      colors.bg,
                      colors.icon,
                      step.status === "current" && "animate-pulse ring-4 ring-blue-100"
                    )}
                  >
                    {getStepIcon(step.status)}
                  </div>

                  {/* Step Info */}
                  <div className="mt-3 text-center min-w-[120px] max-w-[140px]">
                    <div className="text-xs font-semibold text-gray-400 mb-1">
                      {index + 1}/{totalSteps}
                    </div>
                    <h4 className={cn("text-sm font-medium mb-1", colors.text)}>
                      {step.title}
                    </h4>
                    {step.date && (
                      <div className={cn("text-xs", colors.text)}>
                        {step.date}
                      </div>
                    )}
                    {step.reviewer && (
                      <div className="flex items-center justify-center gap-1 mt-2">
                        <Avatar className="h-5 w-5">
                          <AvatarFallback className="text-xs">
                            {step.reviewer.name.charAt(0)}
                          </AvatarFallback>
                        </Avatar>
                        <span className="text-xs text-gray-600">{step.reviewer.name}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Connecting Line */}
                {!isLast && (
                  <div className="flex-1 h-0.5 mx-2 relative">
                    <div className={cn("absolute inset-0 transition-all duration-300", colors.line)} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // 垂直顯示模式 - 卡片式設計
  return (
    <div className={cn("space-y-4", className)}>
      {/* Overall Progress Indicator */}
      {showProgress && (
        <div className="mb-6">
          <div className="flex justify-between items-center mb-2">
            <span className="text-sm font-medium text-gray-700">審核進度</span>
            <span className="text-sm font-semibold text-blue-600">
              {currentStepIndex >= 0 ? currentStepIndex + 1 : completedSteps}/{totalSteps} ({progressPercentage}%)
            </span>
          </div>
          <Progress value={progressPercentage} className="h-2" />
        </div>
      )}

      {/* Timeline Steps */}
      {steps.map((step, index) => {
        const colors = getStepColor(step.status);
        const isLast = index === steps.length - 1;

        return (
          <div key={step.id} className="relative">
            <div className="flex items-start gap-4">
              {/* Timeline Node */}
              <div className="flex flex-col items-center">
                <div
                  className={cn(
                    "flex h-10 w-10 items-center justify-center rounded-full border-2 shadow-md transition-all duration-300",
                    colors.bg,
                    colors.icon,
                    step.status === "current" && "animate-pulse ring-4 ring-blue-100"
                  )}
                >
                  {getStepIcon(step.status)}
                </div>

                {/* Connecting Line */}
                {!isLast && (
                  <div className={cn("w-0.5 h-full min-h-[60px] mt-2 transition-all duration-300", colors.line)} />
                )}
              </div>

              {/* Content Card */}
              <Card className={cn("flex-1 transition-all duration-300 hover:shadow-lg", colors.bg)}>
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-semibold text-gray-400">
                          {index + 1}/{totalSteps}
                        </span>
                        <h4 className={cn("text-base font-semibold", colors.text)}>
                          {step.title}
                        </h4>
                      </div>

                      {step.description && (
                        <p className="text-sm text-gray-600 mt-1">
                          {step.description}
                        </p>
                      )}
                    </div>

                    {step.date && (
                      <div className={cn("text-xs font-medium whitespace-nowrap ml-4", colors.text)}>
                        {step.date}
                      </div>
                    )}
                  </div>

                  {/* Reviewer Info */}
                  {step.reviewer && (
                    <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-100">
                      <Avatar className="h-6 w-6">
                        <AvatarFallback className="text-xs bg-blue-100 text-blue-700">
                          {step.reviewer.name.charAt(0)}
                        </AvatarFallback>
                      </Avatar>
                      <span className="text-xs text-gray-600">
                        審核人：{step.reviewer.name}
                      </span>
                    </div>
                  )}

                  {/* Estimated Date for Pending */}
                  {!step.date && step.estimatedDate && step.status === "pending" && (
                    <div className="text-xs text-gray-500 mt-2">
                      預計完成：{step.estimatedDate}
                    </div>
                  )}

                  {/* Time Elapsed */}
                  {step.timeElapsed && step.status === "current" && (
                    <div className="text-xs text-blue-600 mt-2 font-medium">
                      已耗時：{step.timeElapsed}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </div>
        );
      })}
    </div>
  );
}
