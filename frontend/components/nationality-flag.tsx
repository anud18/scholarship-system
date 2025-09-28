import { cn } from "@/lib/utils";

interface NationalityFlagProps {
  countryCode: string;
  className?: string;
  showLabel?: boolean;
  locale?: "zh" | "en";
}

// 國旗 emoji 映射
const flagEmojis: Record<string, string> = {
  TWN: "🇹🇼",
  USA: "🇺🇸",
  JPN: "🇯🇵",
  KOR: "🇰🇷",
  CHN: "🇨🇳",
  SGP: "🇸🇬",
  MYS: "🇲🇾",
  THA: "🇹🇭",
  VNM: "🇻🇳",
  IDN: "🇮🇩",
  PHL: "🇵🇭",
  IND: "🇮🇳",
  GBR: "🇬🇧",
  FRA: "🇫🇷",
  DEU: "🇩🇪",
  CAN: "🇨🇦",
  AUS: "🇦🇺",
  OTHER: "🏳️",
};

// 國家名稱映射
const countryNames = {
  zh: {
    TWN: "中華民國",
    USA: "美國",
    JPN: "日本",
    KOR: "韓國",
    CHN: "中國大陸",
    SGP: "新加坡",
    MYS: "馬來西亞",
    THA: "泰國",
    VNM: "越南",
    IDN: "印尼",
    PHL: "菲律賓",
    IND: "印度",
    GBR: "英國",
    FRA: "法國",
    DEU: "德國",
    CAN: "加拿大",
    AUS: "澳洲",
    OTHER: "其他",
  },
  en: {
    TWN: "Taiwan (ROC)",
    USA: "United States",
    JPN: "Japan",
    KOR: "South Korea",
    CHN: "China (PRC)",
    SGP: "Singapore",
    MYS: "Malaysia",
    THA: "Thailand",
    VNM: "Vietnam",
    IDN: "Indonesia",
    PHL: "Philippines",
    IND: "India",
    GBR: "United Kingdom",
    FRA: "France",
    DEU: "Germany",
    CAN: "Canada",
    AUS: "Australia",
    OTHER: "Other",
  },
};

export function NationalityFlag({
  countryCode,
  className,
  showLabel = false,
  locale = "zh",
}: NationalityFlagProps) {
  const flag = flagEmojis[countryCode] || flagEmojis["OTHER"];
  const name =
    countryNames[locale][
      countryCode as keyof (typeof countryNames)[typeof locale]
    ] || countryCode;

  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span className="text-lg" title={name}>
        {flag}
      </span>
      {showLabel && <span className="text-sm">{name}</span>}
    </span>
  );
}
