import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AppProvider, useApp } from '../context/AppContext';
import { quality, settings } from '../api';
import SettingsPanel from './SettingsPanel';

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return { ...actual, settings: { ...actual.settings, update: vi.fn() }, quality: { ...actual.quality, cache: vi.fn(), probe: vi.fn() } };
});

const currentSettings = { default_quality: 'high_lossless', default_format: 'FLAC', output_dir: '~/Music/TidalDownloads', waveform_color: '3band' as const };

function Harness() {
  const { dispatch } = useApp();
  return <><button type="button" onClick={() => dispatch({ type: 'SET_SETTINGS', payload: currentSettings })}>Set settings</button><button type="button" onClick={() => dispatch({ type: 'TOGGLE_SETTINGS_PANEL' })}>Open settings</button><SettingsPanel /></>;
}

function renderPanel() {
  render(<AppProvider><Harness /></AppProvider>);
  act(() => { screen.getByRole('button', { name: 'Set settings' }).click(); screen.getByRole('button', { name: 'Open settings' }).click(); });
}

afterEach(() => vi.clearAllMocks());

describe('SettingsPanel', () => {
  it('exposes dialog semantics, Escape, and a focusable close action', () => {
    vi.mocked(quality.cache).mockResolvedValue(null);
    renderPanel();
    expect(screen.getByRole('dialog', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Close settings' })).toHaveFocus();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Settings' })).not.toBeInTheDocument();
  });

  it('keeps edited values after save failure and offers inline retry', async () => {
    vi.mocked(quality.cache).mockResolvedValue(null);
    vi.mocked(settings.update).mockRejectedValueOnce(new Error('Disk unavailable'));
    renderPanel();
    fireEvent.change(screen.getByLabelText('Output directory'), { target: { value: '/music/new' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save changes' }));
    await act(async () => {});
    expect(screen.getByLabelText('Output directory')).toHaveValue('/music/new');
    expect(screen.getByRole('button', { name: 'Retry save' })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Disk unavailable');
  });
});
