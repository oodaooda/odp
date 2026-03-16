/** Format a date/timestamp using the user's configured timezone from Settings. */

function getTimezone(): string {
  return localStorage.getItem("odp_timezone") || Intl.DateTimeFormat().resolvedOptions().timeZone;
}

export function formatDate(value: string | number): string {
  try {
    const d = typeof value === "number" ? new Date(value) : new Date(value);
    return d.toLocaleString("en-US", {
      timeZone: getTimezone(),
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      hour12: false,
    });
  } catch {
    return String(value);
  }
}

export function formatTime(value: string | number): string {
  try {
    const d = typeof value === "number" ? new Date(value) : new Date(value);
    return d.toLocaleString("en-US", {
      timeZone: getTimezone(),
      month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
      hour12: false,
    });
  } catch {
    return String(value);
  }
}
