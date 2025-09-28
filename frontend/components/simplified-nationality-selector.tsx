"use client";

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getTranslation } from "@/lib/i18n";

interface SimplifiedNationalitySelectorProps {
  value: string;
  onValueChange: (value: string) => void;
  locale: "zh" | "en";
  className?: string;
}

const nationalityOptions = [
  {
    code: "TWN",
    zh: "台灣",
    en: "Taiwan",
    flag: "🇹🇼",
  },
  {
    code: "HKM",
    zh: "中港澳",
    en: "Hong Kong, Macau & China",
    flag: "🇭🇰",
  },
  {
    code: "OTHER",
    zh: "其他",
    en: "Other",
    flag: "🌍",
  },
];

export function SimplifiedNationalitySelector({
  value,
  onValueChange,
  locale,
  className,
}: SimplifiedNationalitySelectorProps) {
  const t = (key: string) => getTranslation(locale, key);

  return (
    <div className={className}>
      <Label htmlFor="nationality" className="text-sm font-medium">
        {t("student.std_nation1")} *
      </Label>
      <Select value={value} onValueChange={onValueChange}>
        <SelectTrigger>
          <SelectValue
            placeholder={
              locale === "zh"
                ? "請選擇國籍類別..."
                : "Select nationality category..."
            }
          />
        </SelectTrigger>
        <SelectContent>
          {nationalityOptions.map(option => (
            <SelectItem key={option.code} value={option.code}>
              <div className="flex items-center gap-2">
                <span>{option.flag}</span>
                <span>{locale === "zh" ? option.zh : option.en}</span>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
