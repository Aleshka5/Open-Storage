import { create } from "zustand";
import { listFiles } from "../api/files";
import { AccessBlockedError, AuthRedirectError } from "../api/client";
import type { FileCard } from "../types";

export const FILES_PAGE_LIMIT = 50;

type FilesState = {
  items: FileCard[];
  limit: number;
  offset: number;
  total: number;
  phase: "idle" | "loading" | "ready" | "error";
  errorMessage: string | null;
  load: () => Promise<void>;
  setOffset: (offset: number) => void;
};

let loadSeq = 0;

export const useFilesStore = create<FilesState>((set, get) => ({
  items: [],
  limit: FILES_PAGE_LIMIT,
  offset: 0,
  total: 0,
  phase: "idle",
  errorMessage: null,
  setOffset: (offset) => {
    set({ offset });
    void get().load();
  },
  load: async () => {
    const seq = ++loadSeq;
    if (get().items.length === 0) {
      set({ phase: "loading", errorMessage: null });
    }
    try {
      const page = await listFiles(get().limit, get().offset);
      if (seq !== loadSeq) return;
      set({
        items: page.items.filter((item) => item.status === "ready"),
        limit: page.limit,
        offset: page.offset,
        total: page.total,
        phase: "ready",
        errorMessage: null,
      });
    } catch (error) {
      if (seq !== loadSeq) return;
      if (error instanceof AccessBlockedError || error instanceof AuthRedirectError) return;
      if (get().items.length === 0) {
        set({ phase: "error", errorMessage: "Could not load the file list" });
      }
    }
  },
}));

export function resetFilesStore(): void {
  loadSeq += 1;
  useFilesStore.setState(useFilesStore.getInitialState(), true);
}
