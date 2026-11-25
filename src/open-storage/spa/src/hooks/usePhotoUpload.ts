import { useCallback, useState } from "react";
import { getApiErrorDetail } from "../services/api";
import { uploadPhoto } from "../services/photosApi";
import type { PhotoItem } from "../types/photos";
import { showErrorToast } from "../utils/toast";
import { normalizePhotoFiles } from "../utils/photoUpload";
import { PHOTO_UPLOAD_CONCURRENCY, runWithConcurrency } from "../utils/photoUploadBatch";
import { generateId } from "../utils/id";

export type PhotoUploadStatus = "uploading" | "done" | "error";

export interface PhotoUploadState {
  id: string;
  name: string;
  size: number;
  progress: number;
  status: PhotoUploadStatus;
  error_code?: string;
  photo?: PhotoItem;
}

function retainActiveBatch(current: PhotoUploadState[]): PhotoUploadState[] {
  return current.some((item) => item.status === "uploading") ? current : [];
}

export function usePhotoUpload() {
  const [uploads, setUploads] = useState<PhotoUploadState[]>([]);

  const uploadPhotos = useCallback(
    async (files: File[], onUploaded?: (photo: PhotoItem) => void): Promise<number> => {
      if (files.length === 0) {
        return 0;
      }

      let normalizedFiles: File[];

      try {
        normalizedFiles = normalizePhotoFiles(files);
      } catch (error) {
        console.error("Failed to normalize photo files", error);
        return 0;
      }

      const pendingUploads: PhotoUploadState[] = normalizedFiles.map((file) => ({
        id: generateId(),
        name: file.name,
        size: file.size,
        progress: 0,
        status: "uploading",
      }));

      setUploads((current) => [...current, ...pendingUploads]);

      let stored = 0;

      await runWithConcurrency(normalizedFiles, PHOTO_UPLOAD_CONCURRENCY, async (file, index) => {
        const uploadId = pendingUploads[index].id;

        try {
          const photo = await uploadPhoto(file, (progress) => {
            setUploads((current) =>
              current.map((item) => (item.id === uploadId ? { ...item, progress } : item)),
            );
          });

          setUploads((current) =>
            retainActiveBatch(
              current.map((item) =>
                item.id === uploadId
                  ? { ...item, progress: 100, status: "done", photo }
                  : item,
              ),
            ),
          );

          stored += 1;
          onUploaded?.(photo);
        } catch (error) {
          const detail = getApiErrorDetail(error);

          setUploads((current) =>
            retainActiveBatch(
              current.map((item) =>
                item.id === uploadId
                  ? {
                      ...item,
                      status: "error",
                      error_code: detail?.error_code,
                    }
                  : item,
              ),
            ),
          );
          showErrorToast(error);
        }
      });

      return stored;
    },
    [],
  );

  return { uploads, uploadPhotos };
}
