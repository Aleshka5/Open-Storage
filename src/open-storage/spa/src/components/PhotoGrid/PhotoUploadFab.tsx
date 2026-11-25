import { Plus } from "lucide-react";
import { useCallback, useMemo, useRef } from "react";
import type { PhotoUploadState } from "../../hooks/usePhotoUpload";
import { photoBatchPercent } from "../../utils/photoUploadBatch";
import { ViewportPortal } from "../ui/ViewportPortal";

interface PhotoUploadFabProps {
  uploads: PhotoUploadState[];
  onFilesSelected: (files: File[]) => void;
}

export function PhotoUploadFab({ uploads, onFilesSelected }: PhotoUploadFabProps) {
  const isProcessingRef = useRef(false);
  const batch = useMemo(() => photoBatchPercent(uploads), [uploads]);

  const handleFiles = useCallback(
    (input: HTMLInputElement) => {
      const selectedFiles = input.files ? Array.from(input.files) : [];

      if (selectedFiles.length === 0 || isProcessingRef.current) {
        return;
      }

      isProcessingRef.current = true;
      onFilesSelected(selectedFiles);

      // Сброс input после завершения обработки (iOS чувствителен к раннему reset).
      window.setTimeout(() => {
        input.value = "";
        isProcessingRef.current = false;
      }, 500);
    },
    [onFilesSelected],
  );

  const handleInputChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      handleFiles(event.currentTarget);
    },
    [handleFiles],
  );

  return (
    <ViewportPortal>
      <div className="upload-fab">
        <label className="btn" aria-label="Upload photos">
          <input
            type="file"
            accept="image/*"
            multiple
            onChange={handleInputChange}
            onInput={handleInputChange}
          />
          <Plus size={18} aria-hidden="true" />
        </label>
      </div>

      {batch.isUploading && (
        <div className="upload-dock surface">
          <div
            className="meter"
            role="progressbar"
            aria-label="Uploading photos"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={batch.percent}
          >
            <span style={{ width: `${batch.percent}%` }} />
          </div>
        </div>
      )}
    </ViewportPortal>
  );
}
