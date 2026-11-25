// Sidebar: flat list of recordings (newest on top), upload button, status + progress.

import { useRef } from 'react';
import type { RecordingListItem } from '../api/types';
import { formatTime } from '../strings';

export interface SidebarProps {
  recordings: RecordingListItem[];
  activeId: string | null;
  collapsed: boolean;
  uploadingPct: number | null; // [0,1] or null when there is no upload in progress
  onSelect: (id: string) => void;
  onToggleCollapse: () => void;
  onUpload: (file: File) => void;
}

function statusText(item: RecordingListItem): string {
  switch (item.status) {
    case 'uploaded':
      return 'Uploaded';
    case 'diarizing':
      return 'Detecting voices…';
    case 'transcribing':
      return 'Transcribing speech…';
    case 'ready':
      return 'Ready';
    case 'failed':
      return 'Error';
    default:
      return item.status;
  }
}

export function Sidebar({
  recordings,
  activeId,
  collapsed,
  uploadingPct,
  onSelect,
  onToggleCollapse,
  onUpload,
}: SidebarProps) {
  const fileInput = useRef<HTMLInputElement | null>(null);

  const pickFile = () => fileInput.current?.click();

  const onFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) onUpload(f);
    e.target.value = '';
  };

  if (collapsed) {
    return (
      <div className="sidebar is-collapsed">
        <button
          type="button"
          className="sidebar-reveal"
          onClick={onToggleCollapse}
          aria-label="Expand sidebar"
        >
          &gt;&gt;
        </button>
      </div>
    );
  }

  return (
    <aside className="sidebar" aria-label="Recordings">
      <div className="sidebar-head">
        <span className="collapsed-label">Recordings</span>
        <button
          type="button"
          className="sidebar-toggle"
          onClick={onToggleCollapse}
          aria-label="Collapse sidebar"
        >
          &lt;&lt;
        </button>
      </div>

      <button type="button" className="btn sidebar-upload" onClick={pickFile}>
        Upload file
      </button>
      <input
        ref={fileInput}
        type="file"
        accept="audio/*"
        hidden
        onChange={onFiles}
      />

      <ul className="sidebar-list">
        {uploadingPct !== null && (
          <li className="record-item" aria-live="polite">
            <span className="record-title">Uploading… {Math.round(uploadingPct * 100)}%</span>
            <span className="record-progress">File upload in progress</span>
          </li>
        )}
        {recordings.length === 0 && uploadingPct === null && (
          <li className="record-item record-item-collapsed">
            <span className="record-meta">No recordings yet</span>
          </li>
        )}
        {recordings.map((r) => {
          const active = r.id === activeId;
          return (
            <li key={r.id}>
              <button
                type="button"
                className={`record-item${active ? ' is-active' : ''}`}
                onClick={() => onSelect(r.id)}
                aria-current={active ? 'true' : undefined}
              >
                <span className="record-title">{r.title}</span>
                <span className="record-meta">
                  {statusText(r)}
                  {r.progress
                    ? ` · ${r.progress.phrases_done} / ${r.progress.phrases_total} phrases`
                    : r.status === 'ready'
                      ? ` · ${formatTime(r.duration_ms)}`
                      : ''}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
