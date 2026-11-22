export function formatBytes(bytes: number, isDirectory: boolean): string {
  if (isDirectory) {
    return "—";
  }

  if (!Number.isFinite(bytes) || bytes === 0) {
    return "0 B";
  }

  const sign = bytes < 0 ? "-" : "";
  const magnitude = Math.abs(bytes);
  const units = ["B", "KB", "MB", "GB", "TB"];
  const unitIndex = Math.min(
    Math.floor(Math.log(magnitude) / Math.log(1024)),
    units.length - 1,
  );
  const value = magnitude / 1024 ** unitIndex;

  return `${sign}${value.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
