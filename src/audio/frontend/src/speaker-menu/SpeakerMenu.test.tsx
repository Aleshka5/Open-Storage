// Speaker menu tests: request only on open, the "unavailable" state, assignment.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SpeakerMenuButton } from './SpeakerMenu';
import type { SpeakerRef } from './types';

// Mock the network: fetchSuggestions/assignNick are replaced with vi.fn.
vi.mock('./api', () => ({
  fetchSuggestions: vi.fn(),
  assignNick: vi.fn(),
}));
// "Make it my voice" calls /api/me/voice (US-07), not /nick.
vi.mock('../me/api', () => ({ setMeVoice: vi.fn() }));

import { assignNick, fetchSuggestions } from './api';
import { setMeVoice } from '../me/api';

const fetchSuggestionsMock = vi.mocked(fetchSuggestions);
const assignNickMock = vi.mocked(assignNick);
const setMeVoiceMock = vi.mocked(setMeVoice);

const speaker: SpeakerRef = {
  recording_id: 'rec-1',
  speaker_id: 'spk-1',
  label: 'Speaker 1',
  is_me: false,
  nick_id: null,
};

describe('SpeakerMenuButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not send the suggestions request before the menu is opened', () => {
    render(<SpeakerMenuButton speaker={speaker} onAssigned={() => {}} />);
    expect(fetchSuggestionsMock).not.toHaveBeenCalled();
  });

  it('sends the suggestions request exactly once on open', async () => {
    fetchSuggestionsMock.mockResolvedValue({
      speaker: { id: 'spk-1', label: 'Speaker 1', current: { kind: 'none' } },
      items: [
        { kind: 'nick', nick_id: 'n1', name: 'Ann', score: 0.9 },
        { kind: 'nick', nick_id: 'n2', name: 'Dima', score: 0.7 },
      ],
    });

    render(<SpeakerMenuButton speaker={speaker} onAssigned={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Speaker 1' }));

    await waitFor(() => expect(fetchSuggestionsMock).toHaveBeenCalledTimes(1));
    expect(fetchSuggestionsMock).toHaveBeenCalledWith('rec-1', 'spk-1');
    // The "Ann" item appeared.
    await screen.findByRole('menuitem', { name: 'Ann' });
  });

  it('shows "Suggestions unavailable" on 503', async () => {
    const err = new Error('unavailable') as Error & { status: number };
    err.status = 503;
    fetchSuggestionsMock.mockRejectedValue(err);

    render(<SpeakerMenuButton speaker={speaker} onAssigned={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Speaker 1' }));

    await screen.findByText('Suggestions unavailable');
  });

  it('creates a new nickname and calls onAssigned', async () => {
    fetchSuggestionsMock.mockResolvedValue({
      speaker: { id: 'spk-1', label: 'Speaker 1', current: { kind: 'none' } },
      items: [],
    });
    assignNickMock.mockResolvedValue({
      speaker: { id: 'spk-1', label: 'Ann', nick_id: 'n9', is_me: false },
      nick: { id: 'n9', name: 'Ann', reused: false },
      phrases_updated: 3,
    });

    const onAssigned = vi.fn();
    render(<SpeakerMenuButton speaker={speaker} onAssigned={onAssigned} />);
    fireEvent.click(screen.getByRole('button', { name: 'Speaker 1' }));

    await waitFor(() => expect(fetchSuggestionsMock).toHaveBeenCalled());
    fireEvent.change(screen.getByLabelText('New nickname'), {
      target: { value: 'Ann' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(assignNickMock).toHaveBeenCalledWith('rec-1', 'spk-1', { name: 'Ann' }));
    await waitFor(() => expect(onAssigned).toHaveBeenCalled());
    expect(onAssigned).toHaveBeenCalledWith({
      label: 'Ann',
      nick_id: 'n9',
      is_me: false,
    });
  });

  it('does not show the "New nickname" field or the "Me" item for an is_me speaker', async () => {
    const meSpeaker: SpeakerRef = { ...speaker, is_me: true, label: 'Me' };
    fetchSuggestionsMock.mockResolvedValue({
      speaker: { id: 'spk-1', label: 'Me', current: { kind: 'me' } },
      items: [],
    });

    render(<SpeakerMenuButton speaker={meSpeaker} onAssigned={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Me' }));

    await waitFor(() => expect(fetchSuggestionsMock).toHaveBeenCalled());
    // The "New nickname" field is absent (your own voice gets no nickname).
    expect(screen.queryByLabelText('New nickname')).toBeNull();
  });

  it('"Make it my voice" is inactive until the vector is ready and sends no request', () => {
    fetchSuggestionsMock.mockResolvedValue({
      speaker: { id: 'spk-1', label: 'Speaker 1', current: { kind: 'none' } },
      items: [],
    });
    render(
      <SpeakerMenuButton speaker={speaker} onAssigned={() => {}} embedding="pending" />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Speaker 1' }));
    const item = screen.getByRole('menuitem', { name: 'Make it my voice' });
    expect((item as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText('Voice is still being processed')).toBeTruthy();
    fireEvent.click(item);
    expect(setMeVoiceMock).not.toHaveBeenCalled();
    // Labeling "Me" does not happen through this item either — it replaces the voice.
    expect(assignNickMock).not.toHaveBeenCalled();
  });

  it('with a ready vector the item replaces the "Me" voice and calls onMeVoiceSet', async () => {
    fetchSuggestionsMock.mockResolvedValue({
      speaker: { id: 'spk-1', label: 'Speaker 1', current: { kind: 'none' } },
      items: [],
    });
    setMeVoiceMock.mockResolvedValue({ label: 'Me', has_default_voice: true, default_voice: null });
    const onMeVoiceSet = vi.fn();
    const onAssigned = vi.fn();
    render(
      <SpeakerMenuButton
        speaker={speaker}
        onAssigned={onAssigned}
        embedding="ready"
        onMeVoiceSet={onMeVoiceSet}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Speaker 1' }));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Make it my voice' }));

    await waitFor(() =>
      expect(setMeVoiceMock).toHaveBeenCalledWith({ recording_id: 'rec-1', speaker_id: 'spk-1' }),
    );
    await waitFor(() => expect(onMeVoiceSet).toHaveBeenCalled());
    // The speaker label does not change: past chats are not relabeled (ADR-008).
    expect(onAssigned).not.toHaveBeenCalled();
    expect(assignNickMock).not.toHaveBeenCalled();
  });
});
