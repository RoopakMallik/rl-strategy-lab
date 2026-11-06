// Formatting is done by hand rather than with the runtime's locale so the HTML rendered at
// build time matches what the browser renders (no hydration differences, no time-zone shifts).

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MISSING = "–";

function withThousands(value: number, decimals: number): string {
  const [whole, fraction] = Math.abs(value).toFixed(decimals).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const sign = value < 0 && Number(Math.abs(value).toFixed(decimals)) !== 0 ? "−" : "";
  return sign + grouped + (fraction ? `.${fraction}` : "");
}

export function formatNumber(value: number | null | undefined, decimals = 0): string {
  return value == null ? MISSING : withThousands(value, decimals);
}

/** A value that is already a percentage: 12.3 -> "12.3%". `signed` adds "+" to positive values. */
export function formatPercent(value: number | null | undefined, { decimals = 1, signed = false } = {}): string {
  if (value == null) return MISSING;
  const text = `${withThousands(value, decimals)}%`;
  return signed && Number(value.toFixed(decimals)) > 0 ? `+${text}` : text;
}

/** A share between 0 and 1: 0.875 -> "87.5%". */
export function formatShare(value: number | null | undefined): string {
  return value == null ? MISSING : formatPercent(100 * value, { decimals: 0 });
}

/** Seed-averaged equity starting at 1.0, shown as the value of $1 invested. */
export function formatEquity(value: number | null | undefined): string {
  return value == null ? MISSING : `$${withThousands(value, 2)}`;
}

export function formatLatency(milliseconds: number | null | undefined): string {
  if (milliseconds == null) return MISSING;
  return milliseconds < 1000 ? `${Math.round(milliseconds)} ms` : `${withThousands(milliseconds / 1000, 1)} s`;
}

/** "2025-01-02" or "2025-01-02T14:44:23" -> "2 Jan 2025". */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return MISSING;
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  return `${day} ${MONTHS[month - 1]} ${year}`;
}

/** "2026-11-05T14:44:23.1+05:30" -> "5 Nov 2026, 14:44 UTC+05:30" (the time as written, with its zone). */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return MISSING;
  const time = iso.slice(11, 16);
  if (!time) return formatDate(iso);
  const offset = iso.match(/(Z|[+-]\d{2}:\d{2})$/)?.[1];
  const zone = offset === undefined ? "" : offset === "Z" ? " UTC" : ` UTC${offset}`;
  return `${formatDate(iso)}, ${time}${zone}`;
}

export function formatDateRange(start: string, end: string): string {
  return `${formatDate(start)} – ${formatDate(end)}`;
}

/** "2025-03-03" -> "Mar 2025", for date axes. */
export function formatMonth(iso: string): string {
  return `${MONTHS[Number(iso.slice(5, 7)) - 1]} ${iso.slice(0, 4)}`;
}

/** ["A", "B", "C"] -> "A, B and C". */
export function formatList(items: string[]): string {
  return items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}
