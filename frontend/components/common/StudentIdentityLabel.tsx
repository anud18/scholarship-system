"use client";

/**
 * SIS 身分別 (std_identity) label for list/table cells.
 *
 * Resolves the code against the `identities` reference table — the same
 * source the application detail dialog uses — so list views and the detail
 * view can never disagree (e.g. 4 = 外籍生, 17 = 陸生).
 */

import { getIdentityName, useReferenceData } from "@/hooks/use-reference-data";

type IdentityCode = number | string | null | undefined;

export function StudentIdentityLabel({
  code,
  className,
}: {
  code: IdentityCode;
  className?: string;
}) {
  const { identities, isLoading } = useReferenceData();

  const isBlank = code === null || code === undefined || code === "";
  const numericCode = Number(code);
  const label =
    isBlank || (isLoading && identities.length === 0)
      ? "-"
      : Number.isInteger(numericCode)
        ? getIdentityName(numericCode, identities)
        : String(code);

  return <span className={className}>{label}</span>;
}
