/**
 * Split a sub-type display name into its main name and a trailing
 * parenthesised note, e.g.
 *   "115學年度教育部博士生獎學金 (指導教授配合款每月 $5000 元)"
 *   → ["115學年度教育部博士生獎學金", "(指導教授配合款每月 $5000 元)"]
 *
 * Display-only: the stored label is never changed. Splits at the first
 * half- or full-width opening bracket; a label without one (or one that
 * starts with a bracket) comes back whole with a null note.
 */
export function splitSubTypeLabel(label: string): [string, string | null] {
  const index = label.search(/[(（]/);
  if (index <= 0) return [label, null];
  const main = label.slice(0, index).trim();
  if (!main) return [label, null];
  return [main, label.slice(index).trim()];
}
