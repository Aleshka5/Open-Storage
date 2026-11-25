// "Make it my voice" tests (US-07): inactive until the vector is ready, calls
// PUT /api/me/voice, contract errors (409 / 503 / 404), works for a note and for a speaker.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MakeMeVoiceButton } from './MakeMeVoiceButton';
import { isVoiceReady } from './embedding';

vi.mock('./api', () => ({ setMeVoice: vi.fn() }));

import { setMeVoice } from './api';

const setMeVoiceMock = vi.mocked(setMeVoice);

function apiError(status: number, error_code: string): Error {
  const err = new Error(error_code) as Error & { status: number; error_code: string };
  err.status = status;
  err.error_code = error_code;
  return err;
}

describe('MakeMeVoiceButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('isVoiceReady is true only for ready', () => {
    expect(isVoiceReady('ready')).toBe(true);
    for (const s of ['none', 'pending', 'failed', 'incompatible', undefined] as const) {
      expect(isVoiceReady(s)).toBe(false);
    }
  });

  it('is inactive with a hint while embedding = pending', () => {
    render(<MakeMeVoiceButton recordingId="note-1" speakerId={null} embedding="pending" />);
    const btn = screen.getByRole('menuitem', { name: 'Make it my voice' });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('Voice is still being processed')).toBeTruthy();
    fireEvent.click(btn);
    expect(setMeVoiceMock).not.toHaveBeenCalled();
  });

  it('too_short (embedding = failed) is inactive as well', () => {
    render(<MakeMeVoiceButton recordingId="note-1" speakerId={null} embedding="failed" />);
    expect((screen.getByRole('menuitem', { name: 'Make it my voice' }) as HTMLButtonElement).disabled).toBe(true);
  });

  it('voice from a note: PUT with speaker_id = null, onDone', async () => {
    setMeVoiceMock.mockResolvedValue({
      label: 'Me',
      has_default_voice: true,
      default_voice: { recording_id: 'note-1', kind: 'voice_note', title: 'Note 1' },
    });
    const onDone = vi.fn();
    render(
      <MakeMeVoiceButton
        recordingId="note-1"
        speakerId={null}
        embedding="ready"
        onDone={onDone}
      />,
    );
    const btn = screen.getByRole('menuitem', { name: 'Make it my voice' });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(btn);

    await waitFor(() => expect(setMeVoiceMock).toHaveBeenCalledTimes(1));
    expect(setMeVoiceMock).toHaveBeenCalledWith({ recording_id: 'note-1', speaker_id: null });
    await waitFor(() => expect(onDone).toHaveBeenCalledWith({ label: 'Me', has_default_voice: true }));
    await screen.findByText('This is your voice');
  });

  it('voice from a speaker: PUT with speaker_id', async () => {
    setMeVoiceMock.mockResolvedValue({ label: 'Me', has_default_voice: true, default_voice: null });
    render(<MakeMeVoiceButton recordingId="rec-1" speakerId="spk-1" embedding="ready" />);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Make it my voice' }));
    await waitFor(() =>
      expect(setMeVoiceMock).toHaveBeenCalledWith({ recording_id: 'rec-1', speaker_id: 'spk-1' }),
    );
  });

  it('409 VOICE_NOT_READY shows the waiting hint', async () => {
    setMeVoiceMock.mockRejectedValue(apiError(409, 'VOICE_NOT_READY'));
    render(<MakeMeVoiceButton recordingId="note-2" speakerId={null} embedding="ready" />);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Make it my voice' }));
    await screen.findByRole('alert');
    expect(screen.getAllByText('Voice is still being processed').length).toBeGreaterThan(0);
  });

  it('503 VOICE_INDEX_INCOMPATIBLE — a clear error, not a generic failure', async () => {
    setMeVoiceMock.mockRejectedValue(apiError(503, 'VOICE_INDEX_INCOMPATIBLE'));
    render(<MakeMeVoiceButton recordingId="note-2" speakerId={null} embedding="ready" />);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Make it my voice' }));
    await screen.findByText('Voice is incompatible with the voice index');
  });

  it('404 — recording not found', async () => {
    setMeVoiceMock.mockRejectedValue(apiError(404, 'NOT_FOUND'));
    render(<MakeMeVoiceButton recordingId="foreign" speakerId={null} embedding="ready" />);
    fireEvent.click(screen.getByRole('menuitem', { name: 'Make it my voice' }));
    await screen.findByText('Recording not found');
  });

  it('a second click sends no second request while the first is in flight', async () => {
    let resolve!: (v: never) => void;
    setMeVoiceMock.mockImplementation(
      () => new Promise((r) => { resolve = r as never; }) as never,
    );
    render(<MakeMeVoiceButton recordingId="note-1" speakerId={null} embedding="ready" />);
    const btn = screen.getByRole('menuitem', { name: 'Make it my voice' });
    fireEvent.click(btn);
    await waitFor(() => expect((btn as HTMLButtonElement).disabled).toBe(true));
    fireEvent.click(btn);
    expect(setMeVoiceMock).toHaveBeenCalledTimes(1);
    resolve(undefined as never);
  });
});
