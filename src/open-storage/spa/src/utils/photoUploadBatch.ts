export const PHOTO_UPLOAD_CONCURRENCY = 2;

export interface PhotoBatchItem {
  size: number;
  progress: number;
  status: "uploading" | "done" | "error";
}

/**
 * One size-weighted meter for the photos pick.
 * Settled files count as their full size. The value stays at most 99 while any
 * file is still uploading, including when every byte has already been sent.
 */
export function photoBatchPercent(items: readonly PhotoBatchItem[]): {
  isUploading: boolean;
  percent: number;
} {
  const isUploading = items.some((item) => item.status === "uploading");

  if (!isUploading) {
    return { isUploading: false, percent: 100 };
  }

  const totalBytes = items.reduce((sum, item) => sum + item.size, 0);
  const transferredBytes = items.reduce(
    (sum, item) =>
      sum + (item.status === "uploading" ? (item.size * item.progress) / 100 : item.size),
    0,
  );
  const percent =
    totalBytes === 0 ? 99 : Math.min(99, Math.round((transferredBytes / totalBytes) * 100));

  return { isUploading: true, percent };
}

/**
 * Runs `worker` over `items` with at most `limit` calls in flight.
 * Later items wait until a slot is free. Workers run in index order as slots open.
 */
export async function runWithConcurrency<T>(
  items: readonly T[],
  limit: number,
  worker: (item: T, index: number) => Promise<void>,
): Promise<void> {
  if (items.length === 0 || limit < 1) {
    return;
  }

  let nextIndex = 0;

  const runNext = async (): Promise<void> => {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      await worker(items[index], index);
    }
  };

  const workers = Math.min(limit, items.length);
  await Promise.all(Array.from({ length: workers }, () => runNext()));
}
