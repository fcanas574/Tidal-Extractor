import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppProvider, useApp } from '../context/AppContext';
import { quality, settings } from '../api';
import type { Settings } from '../api';
import SettingsPanel from './SettingsPanel';

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return { ...actual, settings: { ...actual.settings, update: vi.fn() }, quality: { ...actual.quality, cache: vi.fn(), probe: vi.fn() } };
});

const currentSettings: Settings = { default_quality: 'high_lossless', default_format: 'FLAC', output_dir: '~/Music/TidalDownloads', waveform_color: '3band' };

function Harness() {
  const { dispatch } = useApp();
  return <><button type="button" onClick={() => dispatch({ type: 'SET_SETTINGS', payload: currentSettings })}>Set settings</button><button type="button" onClick={() => dispatch({ type: 'TOGGLE_SETTINGS_PANEL' })}>Open settings</button><SettingsPanel /></>;
}

function renderPanel() {
  render(<AppProvider><Harness /></AppProvider>);
  act(() => {
    screen.getByRole('button', { name: 'Set settings' }).click();
    const trigger = screen.getByRole('button', { name: 'Open settings' });
    trigger.focus();
    trigger.click();
  });
}

afterEach(() => vi.clearAllMocks());

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => { resolve = res; });
  return { promise, resolve };
}

describe('SettingsPanel', () => {
  it('groups preferences and keeps the existing quality, format, waveform, and output controls', async () => {
    vi.mocked(quality.cache).mockResolvedValue({ preset: 'FLAC', bitrate: 1411 });
    renderPanel();
    await act(async () => {});

    const dialog = screen.getByRole('dialog', { name: 'Settings' });
    const sections = within(dialog).getByRole('navigation', { name: 'Settings sections' });
    for (const section of ['Account', 'Download', 'Preview', 'Output']) {
      expect(within(sections).getByRole('link', { name: section })).toHaveAttribute('href', `#settings-section-${section.toLowerCase()}`);
      expect(within(dialog).getByRole('heading', { name: section })).toBeInTheDocument();
    }
    expect(within(dialog).getByText('Default quality')).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /HiRes Lossless/ })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /High \(320kbps AAC\)/ })).toBeInTheDocument();
    expect(within(dialog).getByRole('group', { name: 'Default format' })).toBeInTheDocument();
    expect(within(dialog).getByRole('group', { name: 'Waveform color' })).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /3Band \(Rekordbox\)/ })).toHaveAttribute('aria-pressed', 'true');
    expect(within(dialog).getByRole('button', { name: /RGB/ })).toBeInTheDocument();
    expect(within(dialog).getByLabelText('Output directory')).toHaveValue('~/Music/TidalDownloads');
    expect(within(dialog).getByText('FLAC · 1411 kbps')).toBeInTheDocument();

    const highQuality = within(dialog).getByRole('button', { name: /High \(320kbps AAC\)/ });
    fireEvent.click(highQuality);
    expect(highQuality).toHaveAttribute('aria-pressed', 'true');
    const mp3 = within(within(dialog).getByRole('group', { name: 'Default format' })).getByRole('button', { name: /MP3/ });
    fireEvent.click(mp3);
    expect(mp3).toHaveAttribute('aria-pressed', 'true');
    const rgb = within(within(dialog).getByRole('group', { name: 'Waveform color' })).getByRole('button', { name: /RGB/ });
    fireEvent.click(rgb);
    expect(rgb).toHaveAttribute('aria-pressed', 'true');
    vi.mocked(quality.probe).mockResolvedValue({ preset: 'AAC', bitrate: 320 });
    fireEvent.click(within(dialog).getByRole('button', { name: 'Re-probe' }));
    await act(async () => {});
    expect(quality.probe).toHaveBeenCalledOnce();
  });

  it('traps focus, restores the trigger, and closes on Escape', async () => {
    vi.mocked(quality.cache).mockResolvedValue(null);
    renderPanel();
    await act(async () => {});
    const dialog = screen.getByRole('dialog', { name: 'Settings' });
    const closeButton = within(dialog).getByRole('button', { name: 'Close settings' });
    const trigger = screen.getByRole('button', { name: 'Open settings' });
    expect(dialog).toBeInTheDocument();
    expect(closeButton).toHaveFocus();
    fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
    expect(screen.getByRole('button', { name: 'Disconnect account' })).toHaveFocus();
    fireEvent.click(closeButton);
    expect(trigger).toHaveFocus();

    fireEvent.click(trigger);
    await act(async () => {});
    expect(within(screen.getByRole('dialog', { name: 'Settings' })).getByRole('button', { name: 'Close settings' })).toHaveFocus();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Settings' })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();

    fireEvent.click(trigger);
    await act(async () => {});
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss settings overlay' }));
    expect(screen.queryByRole('dialog', { name: 'Settings' })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('offers Discard only for dirty settings and restores the saved draft', async () => {
    vi.mocked(quality.cache).mockResolvedValue(null);
    renderPanel();
    await act(async () => {});
    expect(screen.queryByRole('button', { name: 'Discard' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Output directory'), { target: { value: '/music/new' } });
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }));
    expect(screen.getByLabelText('Output directory')).toHaveValue('~/Music/TidalDownloads');
    expect(screen.queryByRole('button', { name: 'Discard' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
  });

  it('keeps edited values after save failure and offers inline retry', async () => {
    vi.mocked(quality.cache).mockResolvedValue(null);
    vi.mocked(settings.update).mockRejectedValueOnce(new Error('Disk unavailable'));
    vi.mocked(settings.update).mockResolvedValueOnce({ ...currentSettings, output_dir: '/music/new' });
    renderPanel();
    fireEvent.change(screen.getByLabelText('Output directory'), { target: { value: '/music/new' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await act(async () => {});
    expect(screen.getByLabelText('Output directory')).toHaveValue('/music/new');
    expect(screen.getByRole('button', { name: 'Retry save' })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Disk unavailable');

    fireEvent.click(screen.getByRole('button', { name: 'Retry save' }));
    await act(async () => {});
    expect(screen.getByRole('status')).toHaveTextContent('Settings saved.');
    expect(screen.getByLabelText('Output directory')).toHaveValue('/music/new');
  });

  it('keeps the save action stable while busy and reflects a successful update', async () => {
    vi.mocked(quality.cache).mockResolvedValue(null);
    const pending = deferred<Settings>();
    vi.mocked(settings.update).mockReturnValue(pending.promise);
    renderPanel();
    fireEvent.change(screen.getByLabelText('Output directory'), { target: { value: '/music/updated' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
    await act(async () => pending.resolve({ ...currentSettings, output_dir: '/music/updated' }));
    expect(screen.getByRole('status')).toHaveTextContent('Settings saved.');
    expect(screen.getByRole('button', { name: 'Save changes' })).toBeDisabled();
  });
});
