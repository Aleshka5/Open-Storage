// Root component: holds the recording list, the open recording, chat polling,
// the player and auto-follow. Identity is the gateway header; the frontend never touches owner_id.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  getRecording,
  listRecordings,
  renameRecording,
  uploadRecordingWithProgress,
} from './api/client';
import type { RecordingDetail, RecordingListItem, Phrase, PhraseSide } from './api/types';
import { Sidebar } from './components/Sidebar';
import { ChatPane } from './components/ChatPane';
import { Player } from './components/Player';
import { usePlayer } from './hooks/usePlayer';
import { usePolling } from './hooks/usePolling';
import { useAutoFollow } from './hooks/useAutoFollow';
import { readBool, writeBool } from './core/utils';
import { audioUrl } from './api/client';
import { MicButton } from './components/MicButton';
import { useVoiceNote } from './voice-note/useVoiceNote';
import { strings } from './strings';
import type { EmbeddingState } from './me/embedding';
import { noteListItem, toListItem } from './core/list';

export function App() {
  const [recordings, setRecordings] = useState<RecordingListItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RecordingDetail | null>(null);
  const [collapsed, setCollapsed] = useState<boolean>(() => readBool('sidebar.collapsed', false));
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Loading the recording list.
  const refresh = useCallback(async () => {
    try {
      const res = await listRecordings();
      setRecordings(res.items);
      setLoadError(null);
    } catch (e) {
      setLoadError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Loading the full recording when one is selected.
  useEffect(() => {
    if (!activeId) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    void getRecording(activeId)
      .then((res) => {
        if (!cancelled) setDetail(res.recording);
      })
      .catch((e) => {
        if (!cancelled) setLoadError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  // Polling the growing chat: the phrase history is back-filled on open, then kept in sync
  // (a ready note whose voice vector is still being computed keeps polling too, US-07).
  const polling = usePolling(activeId, detail?.status ?? null, []);

  // Speaker label assignment (US-06): after the menu responds, update the labels and
  // side of this speaker's phrases without reloading the page.
  const [assignedLabels, setAssignedLabels] = useState<
    Record<string, { label: string; side: PhraseSide }>
  >({});

  // Finalized phrases: from polling (not duplicated from detail).
  const phrases: Phrase[] = polling.phrases.map((p) => {
    const a = assignedLabels[p.speaker_id];
    return a ? { ...p, label: a.label, side: a.side } : p;
  });

  const handlePhraseAssigned = useCallback(
    (
      speakerId: string,
      result: { label: string; nick_id: string | null; is_me: boolean },
    ) => {
      setAssignedLabels((prev) => ({
        ...prev,
        [speakerId]: {
          label: result.label,
          side: result.is_me ? 'right' : 'left',
        },
      }));
    },
    [],
  );

  // Player. The status comes from polling (the detail response is a snapshot taken when the
  // recording was opened, so it would stay `transcribing` after the work is done).
  const liveStatus = polling.status ?? detail?.status ?? null;
  const canPlay = liveStatus === 'ready';
  const player = usePlayer(activeId, canPlay, detail?.duration_ms ?? 0);

  // "Me" voice replaced from a phrase or note menu (US-07): re-read detail so the
  // menu item and hints see the new state without reloading the page.
  const handleMeVoiceSet = useCallback(() => {
    if (!activeId) return;
    void getRecording(activeId)
      .then((res) => {
        setDetail(res.recording);
        void refresh();
      })
      .catch(() => {
        /* silently: the next poll will catch up on the state */
      });
  }, [activeId, refresh]);

  // Detail with the live status, progress and voice-vector state from polling (US-04/US-07):
  // `detail` is a snapshot of the moment the recording was opened, polling keeps it current.
  const detailLive: RecordingDetail | null = useMemo(() => {
    if (!detail) return null;
    const processing = detail.processing
      ? {
          ...detail.processing,
          phrases_done: Math.max(detail.processing.phrases_done, polling.phrasesDone),
          phrases_total: Math.max(detail.processing.phrases_total, polling.phrasesTotal),
          ...(polling.embedding ? { embedding: polling.embedding as EmbeddingState } : {}),
        }
      : detail.processing;
    return { ...detail, status: liveStatus ?? detail.status, processing };
  }, [detail, liveStatus, polling.phrasesDone, polling.phrasesTotal, polling.embedding]);

  // The sidebar badge follows the live status too: a recording that finished while it was
  // open used to keep saying `uploaded` / `recording` until a page reload.
  useEffect(() => {
    if (liveStatus === 'ready' || liveStatus === 'failed') void refresh();
  }, [liveStatus, refresh]);

  // Auto-scroll to the active phrase (five-second rule).
  const { scrollRef, activeSeq, handleUserScroll } = useAutoFollow(
    phrases.map((p) => ({ seq: p.seq, start_ms: p.start_ms, end_ms: p.end_ms })),
    player.playheadMs,
    player.playing,
  );

  // Voice note (US-05): fixed mic button + error toast.
  const [noteError, setNoteError] = useState<string | null>(null);
  const voiceNote = useVoiceNote({
    onStart: (created) => {
      // Switch to the note immediately: its phrase (`seq=1`, `state: partial`) grows in the
      // chat while the microphone records, instead of the note being invisible until the end.
      setActiveId(created.recording_id);
      setDetail(null);
    },
    onDone: (created) => {
      // The recording shows up in the sidebar as `ready`; the player is available.
      setRecordings((prev) => [
        noteListItem(created),
        ...prev.filter((r) => r.id !== created.recording_id),
      ]);
      setActiveId(created.recording_id);
      void refresh();
    },
    onError: (code) => {
      setNoteError(
        code === 'ASR_BUSY' || code === '4503'
          ? strings['error.asr_busy']
          : `Recording error: ${code}`,
      );
    },
  });

  const toggleMic = () => {
    setNoteError(null);
    if (voiceNote.state === 'recording') {
      void voiceNote.stop();
    } else if (voiceNote.state === 'idle') {
      void voiceNote.start().catch((e) => {
        setNoteError((e as Error).message);
      });
    }
  };

  const toggleCollapse = () => {
    setCollapsed((c) => {
      writeBool('sidebar.collapsed', !c);
      return !c;
    });
  };

  const selectRecording = (id: string) => {
    setActiveId(id);
  };

  const handleUpload = async (file: File) => {
    setUploadPct(0);
    try {
      // `201` carries the recording object itself — no `{recording, speakers}` envelope
      // (api.md). Reading it as `created.recording` used to throw inside the `setRecordings`
      // updater, i.e. during render: React unmounted the whole tree and the UI vanished
      // until a manual reload.
      const created = await uploadRecordingWithProgress(file, (f) =>
        setUploadPct(f),
      );
      // The recording shows up right after 201 (chat-and-player/init.md item 3).
      setRecordings((prev) => [
        toListItem(created),
        ...prev.filter((r) => r.id !== created.id),
      ]);
      setActiveId(created.id);
      setDetail(created);
    } catch (e) {
      setLoadError((e as Error).message);
    } finally {
      setUploadPct(null);
    }
  };

  const handleRename = async (title: string) => {
    if (!activeId) return;
    try {
      const res = await renameRecording(activeId, title);
      setDetail(res.recording);
      setRecordings((prev) =>
        prev.map((r) =>
          r.id === activeId ? { ...r, title: res.recording.title } : r,
        ),
      );
    } catch (e) {
      setLoadError((e as Error).message);
    }
  };

  const progressText =
    detailLive &&
    (detailLive.status === 'transcribing' || detailLive.status === 'diarizing')
      ? detailLive.processing
        ? `${detailLive.processing.phrases_done} / ${detailLive.processing.phrases_total} phrases`
        : null
      : null;

  return (
    <div className={`stage${collapsed ? ' sidebar-collapsed' : ''}`}>
      <Sidebar
        recordings={recordings}
        activeId={activeId}
        collapsed={collapsed}
        uploadingPct={uploadPct}
        onSelect={selectRecording}
        onToggleCollapse={toggleCollapse}
        onUpload={handleUpload}
      />

      <ChatPane
        recording={detailLive}
        phrases={phrases}
        activeSeq={activeSeq}
        progressText={progressText}
        scrollRef={scrollRef}
        handleUserScroll={handleUserScroll}
        onRename={handleRename}
        onPhraseAssigned={handlePhraseAssigned}
        onMeVoiceSet={handleMeVoiceSet}
      />

      <Player
        playing={player.playing}
        playheadMs={player.playheadMs}
        durationMs={player.durationMs}
        speed={player.speed}
        disabled={!canPlay}
        onToggle={player.toggle}
        onSeek={player.seek}
        onSpeedChange={player.setSpeed}
      />

      {/* The single <audio>: src only when the recording is ready (Range proxy). */}
      <audio
        ref={player.audioRef}
        src={activeId && canPlay ? audioUrl(activeId) : undefined}
        preload="metadata"
        style={{ display: 'none' }}
      />

      {/* Voice note: fixed mic button in the bottom-right corner. */}
      <div className="mic-fab">
        <MicButton state={voiceNote.state} onToggle={toggleMic} />
      </div>

      {(noteError || loadError) && (
        <div className="toast-stack">
          {noteError && (
            <div className="error-banner" role="alert">
              {noteError}
            </div>
          )}
          {loadError && (
            <div className="error-banner" role="alert">
              {loadError}
            </div>
          )}
        </div>
      )}

      {recordings.length === 0 && !activeId && (
        <div className="empty-state empty-state-chat">
          <p>Upload a file or record a note</p>
        </div>
      )}
    </div>
  );
}

export default App;
