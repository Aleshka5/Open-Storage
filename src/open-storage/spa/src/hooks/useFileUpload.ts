import { useCallback, useState } from "react";
import { getApiErrorDetail } from "../services/api";
import { uploadFile } from "../services/filesApi";
import { showErrorToast, showSuccessToast } from "../utils/toast";
import { generateId } from "../utils/id";

export type UploadStatus = "uploading" | "done" | "error";

export interface UploadFileState {
  id: string;
  name: string;
  size: number;
  progress: number;
  status: UploadStatus;
  error_code?: string;
}

export interface UploadBatchResult {
  total: number;
  succeeded: number;
  failed: number;
}

/**
 * Uploads the picked files and returns only when the whole batch settled.
 *
 * Progress is reported through the `uploads` state only: the caller draws a
 * single aggregate bar from it. There is deliberately no per-file toast and no
 * per-progress callback into the file list — that used to make the list refetch
 * on every progress tick.
 */
export function useFileUpload(apiPrefix: string) {
  const [uploads, setUploads] = useState<UploadFileState[]>([]);

  const uploadFiles = useCallback(
    async (files: File[], path: string): Promise<UploadBatchResult> => {
      if (files.length === 0) {
        return { total: 0, succeeded: 0, failed: 0 };
      }

      const pendingUploads: UploadFileState[] = files.map((file) => ({
        id: generateId(),
        name: file.name,
        size: file.size,
        progress: 0,
        status: "uploading",
      }));

      setUploads((current) => [...current, ...pendingUploads]);

      let succeeded = 0;
      let failed = 0;

      await Promise.all(
        files.map(async (file, index) => {
          const uploadId = pendingUploads[index].id;

          try {
            await uploadFile(apiPrefix, path, file, (progress) => {
              setUploads((current) =>
                current.map((item) =>
                  item.id === uploadId && item.progress !== progress
                    ? { ...item, progress }
                    : item,
                ),
              );
            });

            succeeded += 1;
            setUploads((current) =>
              current.map((item) =>
                item.id === uploadId
                  ? { ...item, progress: 100, status: "done" }
                  : item,
              ),
            );
          } catch (error) {
            failed += 1;
            const detail = getApiErrorDetail(error);

            setUploads((current) =>
              current.map((item) =>
                item.id === uploadId
                  ? {
                      ...item,
                      status: "error",
                      error_code: detail?.error_code,
                    }
                  : item,
              ),
            );
            showErrorToast(error);
          }
        }),
      );

      if (succeeded === 1) {
        showSuccessToast("File uploaded");
      } else if (succeeded > 1) {
        showSuccessToast(`${succeeded} files uploaded`);
      }

      return { total: files.length, succeeded, failed };
    },
    [apiPrefix],
  );

  const clearFinished = useCallback(() => {
    setUploads((current) => current.filter((item) => item.status === "uploading"));
  }, []);

  return { uploads, uploadFiles, clearFinished };
}
