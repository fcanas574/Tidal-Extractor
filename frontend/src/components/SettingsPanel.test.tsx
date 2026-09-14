import { act, fireEvent, render, screen, within } from '@testing-library/react';
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
  act(() => {
    screen.getByRole('button', { name: 'Set settings' }).click();
    const trigger = screen.getByRole('button', { name: 'Open settings' });
    trigger.focus();
    trigger.click();
  });
}

afterEach(() => vi.clearAllMocks());

describe('SettingsPanel', () => {
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
