"use client";

/**
 * SIS 身分別 (std_identity) label for list/table cells.
 *
 * Resolves the code against the `identities` reference table — the same
 * source the application detail dialog uses — so list views and the detail
 * view can never disagree (e.g. 4 = 外籍生, 17 = 陸生).
 */

import { useReferenceData } from "@/hooks/use-reference-data";
import { IDENTITY_NAME_EN } from "@/lib/reference/identity-names";

type IdentityCode = number | string | null | undefined;
type Locale = "zh" | "en";

const BLANK = "-";

export function StudentIdentityLabel({
  code,
  locale = "zh",
  className,
}: {
  code: IdentityCode;
  locale?: Locale;
  className?: string;
}) {
  const { identities, isLoading, error } = useReferenceData();

  const rawCode = typeof code === "string" ? code.trim() : code;
  if (rawCode === null || rawCode === undefined || rawCode === "") {
    return <span className={className}>{BLANK}</span>;
  }

  // Don't fake a label: while the table is unavailable show the raw code,
  // flagged as unresolved, rather than "unknown identity".
  if (identities.length === 0) {
    if (isLoading) return <span className={className}>{BLANK}</span>;
    if (error) {
      return (
        <span
          className={className}
          title={
            locale === "zh"
              ? "身分別資料載入失敗"
              : "Failed to load identity reference data"
          }
        >
          {String(rawCode)}
        </span>
      );
    }
  }

  const identity = identities.find(i => i.id === Number(rawCode));
  const label = identity
    ? locale === "en"
      ? IDENTITY_NAME_EN[identity.name] || identity.name
      : identity.name
    : locale === "en"
      ? `Unknown identity (${rawCode})`
      : `未知身份 (${rawCode})`;

  return <span className={className}>{label}</span>;
}
