"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { NationalityFlag } from "@/components/nationality-flag";
import { Check, ChevronsUpDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { getTranslation } from "@/lib/i18n";

interface NationalitySelectorProps {
  value: string;
  onValueChange: (value: string) => void;
  locale: "zh" | "en";
  className?: string;
}

const nationalities = [
  { code: "TWN", priority: 1 },
  { code: "USA", priority: 2 },
  { code: "JPN", priority: 3 },
  { code: "KOR", priority: 4 },
  { code: "CHN", priority: 5 },
  { code: "SGP", priority: 6 },
  { code: "MYS", priority: 7 },
  { code: "THA", priority: 8 },
  { code: "VNM", priority: 9 },
  { code: "IDN", priority: 10 },
  { code: "PHL", priority: 11 },
  { code: "IND", priority: 12 },
  { code: "GBR", priority: 13 },
  { code: "FRA", priority: 14 },
  { code: "DEU", priority: 15 },
  { code: "CAN", priority: 16 },
  { code: "AUS", priority: 17 },
  { code: "OTHER", priority: 99 },
];

export function NationalitySelector({
  value,
  onValueChange,
  locale,
  className,
}: NationalitySelectorProps) {
  const [open, setOpen] = useState(false);
  const t = (key: string) => getTranslation(locale, key);

  const selectedNationality = nationalities.find(n => n.code === value);
  const sortedNationalities = [...nationalities].sort(
    (a, b) => a.priority - b.priority
  );

  return (
    <div className={className}>
      <Label htmlFor="nationality">{t("student.std_nation1")} *</Label>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className="w-full justify-between"
          >
            {selectedNationality ? (
              <div className="flex items-center gap-2">
                <NationalityFlag
                  countryCode={selectedNationality.code}
                  locale={locale}
                  showLabel={true}
                />
              </div>
            ) : (
              <span>
                {locale === "zh" ? "選擇國籍..." : "Select nationality..."}
              </span>
            )}
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-full p-0">
          <Command>
            <CommandInput
              placeholder={
                locale === "zh" ? "搜尋國籍..." : "Search nationality..."
              }
            />
            <CommandList>
              <CommandEmpty>
                {locale === "zh" ? "找不到相符的國籍" : "No nationality found"}
              </CommandEmpty>
              <CommandGroup>
                {sortedNationalities.map(nationality => (
                  <CommandItem
                    key={nationality.code}
                    value={nationality.code}
                    onSelect={currentValue => {
                      onValueChange(currentValue === value ? "" : currentValue);
                      setOpen(false);
                    }}
                  >
                    <Check
                      className={cn(
                        "mr-2 h-4 w-4",
                        value === nationality.code ? "opacity-100" : "opacity-0"
                      )}
                    />
                    <NationalityFlag
                      countryCode={nationality.code}
                      locale={locale}
                      showLabel={true}
                    />
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
