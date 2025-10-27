"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Calendar } from "lucide-react";

interface ConfigSelectorProps {
  selectedCombination?: string;
  availableYears: number[];
  availableSemesters: string[];
  onCombinationChange: (combination: string) => void;
  locale?: "zh" | "en";
}

const SEMESTER_LABELS = {
  zh: {
    first: "上學期",
    second: "下學期",
    yearly: "全年",
  },
  en: {
    first: "First Semester",
    second: "Second Semester",
    yearly: "Yearly",
  },
};

export function ConfigSelector({
  selectedCombination,
  availableYears,
  availableSemesters,
  onCombinationChange,
  locale = "zh",
}: ConfigSelectorProps) {
  const getSemesterLabel = (semester: string) => {
    return (
      SEMESTER_LABELS[locale][
        semester as keyof typeof SEMESTER_LABELS.zh
      ] || semester
    );
  };

  const getDisplayText = () => {
    if (!selectedCombination) {
      return locale === "zh" ? "選擇學期" : "Select Semester";
    }
    const [year, semester] = selectedCombination.split("-");
    return `${year} ${getSemesterLabel(semester)}`;
  };

  return (
    <Select
      value={selectedCombination || ""}
      onValueChange={onCombinationChange}
    >
      <SelectTrigger className="w-48">
        <SelectValue
          placeholder={locale === "zh" ? "選擇學期" : "Select Semester"}
        >
          <div className="flex items-center">
            <Calendar className="h-4 w-4 mr-2" />
            {getDisplayText()}
          </div>
        </SelectValue>
      </SelectTrigger>
      <SelectContent>
        {availableYears.map((year) =>
          availableSemesters.map((semester) => (
            <SelectItem
              key={`${year}-${semester}`}
              value={`${year}-${semester}`}
            >
              {year} {locale === "zh" ? "學年度" : "Academic Year"}{" "}
              {getSemesterLabel(semester)}
            </SelectItem>
          ))
        )}
      </SelectContent>
    </Select>
  );
}
