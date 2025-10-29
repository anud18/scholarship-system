"use client";

import { X } from "lucide-react";
import { useState, KeyboardEvent, forwardRef } from "react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface TagsInputProps {
  value: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  className?: string;
  validator?: (tag: string) => boolean;
  maxTags?: number;
  disabled?: boolean;
}

export const TagsInput = forwardRef<HTMLDivElement, TagsInputProps>(
  ({ value, onChange, placeholder, className, validator, maxTags, disabled }, ref) => {
    const [inputValue, setInputValue] = useState("");
    const [error, setError] = useState<string | null>(null);

    const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter" || e.key === ",") {
        e.preventDefault();
        addTag();
      } else if (e.key === "Backspace" && !inputValue && value.length > 0) {
        // Remove last tag when backspace is pressed on empty input
        removeTag(value.length - 1);
      }
    };

    const addTag = () => {
      const trimmedValue = inputValue.trim();

      if (!trimmedValue) {
        return;
      }

      // Check max tags limit
      if (maxTags && value.length >= maxTags) {
        setError(`最多只能添加 ${maxTags} 個標籤`);
        return;
      }

      // Check for duplicates
      if (value.includes(trimmedValue)) {
        setError("此標籤已存在");
        setInputValue("");
        setTimeout(() => setError(null), 2000);
        return;
      }

      // Custom validation
      if (validator && !validator(trimmedValue)) {
        setError("無效的標籤格式");
        setTimeout(() => setError(null), 2000);
        return;
      }

      // Add tag
      onChange([...value, trimmedValue]);
      setInputValue("");
      setError(null);
    };

    const removeTag = (index: number) => {
      if (disabled) return;
      onChange(value.filter((_, i) => i !== index));
    };

    const handlePaste = (e: React.ClipboardEvent<HTMLInputElement>) => {
      e.preventDefault();
      const pastedText = e.clipboardData.getData("text");

      // Split by common delimiters
      const tags = pastedText
        .split(/[\n,;]+/)
        .map(tag => tag.trim())
        .filter(tag => tag.length > 0);

      // Validate and add tags
      const validTags: string[] = [];
      for (const tag of tags) {
        if (maxTags && value.length + validTags.length >= maxTags) {
          break;
        }
        if (!value.includes(tag) && !validTags.includes(tag)) {
          if (!validator || validator(tag)) {
            validTags.push(tag);
          }
        }
      }

      if (validTags.length > 0) {
        onChange([...value, ...validTags]);
      }
    };

    return (
      <div ref={ref} className={cn("space-y-2", className)}>
        {/* Tags display */}
        {value.length > 0 && (
          <div className="flex flex-wrap gap-2 p-2 border rounded-md bg-muted/50">
            {value.map((tag, index) => (
              <Badge
                key={index}
                variant="secondary"
                className="pl-2 pr-1 py-1 text-sm font-normal"
              >
                <span className="mr-1">{tag}</span>
                {!disabled && (
                  <button
                    type="button"
                    onClick={() => removeTag(index)}
                    className="ml-1 rounded-full hover:bg-muted-foreground/20 p-0.5 transition-colors"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </Badge>
            ))}
          </div>
        )}

        {/* Input field */}
        <div className="relative">
          <Input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            onBlur={addTag}
            placeholder={placeholder}
            disabled={disabled || (maxTags !== undefined && value.length >= maxTags)}
            className={cn(error && "border-red-500 focus-visible:ring-red-500")}
          />
          {error && (
            <p className="text-xs text-red-500 mt-1">{error}</p>
          )}
        </div>

        {/* Helper text */}
        <p className="text-xs text-muted-foreground">
          按 Enter 或逗號鍵新增標籤{maxTags && ` (最多 ${maxTags} 個)`}
          {value.length > 0 && ` • 已添加 ${value.length} 個`}
        </p>
      </div>
    );
  }
);

TagsInput.displayName = "TagsInput";
