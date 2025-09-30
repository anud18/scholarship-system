"use client";

import type React from "react";

import { AlertTriangle, CheckCircle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface ValidationMessageProps {
  type: "error" | "warning" | "success" | "info";
  message: string;
  className?: string;
}

export function ValidationMessage({
  type,
  message,
  className,
}: ValidationMessageProps) {
  const getIcon = () => {
    switch (type) {
      case "error":
        return <AlertTriangle className="h-4 w-4" />;
      case "warning":
        return <AlertTriangle className="h-4 w-4" />;
      case "success":
        return <CheckCircle className="h-4 w-4" />;
      case "info":
        return <Info className="h-4 w-4" />;
    }
  };

  const getColorClass = () => {
    switch (type) {
      case "error":
        return "text-red-600";
      case "warning":
        return "text-orange-600";
      case "success":
        return "text-green-600";
      case "info":
        return "text-blue-600";
    }
  };

  return (
    <div
      className={cn(
        "flex items-center gap-1 mt-1 text-sm",
        getColorClass(),
        className
      )}
    >
      {getIcon()}
      <span>{message}</span>
    </div>
  );
}

interface FormFieldProps {
  children: React.ReactNode;
  error?: string;
  warning?: string;
  success?: string;
  info?: string;
  className?: string;
}

export function FormField({
  children,
  error,
  warning,
  success,
  info,
  className,
}: FormFieldProps) {
  return (
    <div className={className}>
      {children}
      {error && <ValidationMessage type="error" message={error} />}
      {warning && <ValidationMessage type="warning" message={warning} />}
      {success && <ValidationMessage type="success" message={success} />}
      {info && <ValidationMessage type="info" message={info} />}
    </div>
  );
}
