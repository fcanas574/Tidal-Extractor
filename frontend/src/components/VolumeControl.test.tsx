// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import VolumeControl from './VolumeControl';

describe('VolumeControl component', () => {
  it('renders mute button and volume slider with accessible attributes', () => {
    render(
      <VolumeControl
        sliderValue={0.8}
        isMuted={false}
        onSliderChange={vi.fn()}
        onToggleMute={vi.fn()}
      />
    );

    const button = screen.getByRole('button', { name: 'Mute preview' });
    expect(button).toBeTruthy();
    expect(button.getAttribute('aria-pressed')).toBe('false');

    const slider = screen.getByRole('slider', { name: 'Preview volume' });
    expect(slider).toBeTruthy();
    expect(slider.getAttribute('aria-valuenow')).toBe('80');
    expect(slider.getAttribute('aria-valuemin')).toBe('0');
    expect(slider.getAttribute('aria-valuemax')).toBe('100');
    expect(slider.getAttribute('aria-valuetext')).toContain('80%');
    expect(slider.getAttribute('aria-valuetext')).toContain('dB');
  });

  it('triggers onSliderChange when slider value is adjusted', () => {
    const onSliderChange = vi.fn();
    render(
      <VolumeControl
        sliderValue={0.8}
        isMuted={false}
        onSliderChange={onSliderChange}
        onToggleMute={vi.fn()}
      />
    );

    const slider = screen.getByRole('slider', { name: 'Preview volume' });
    fireEvent.change(slider, { target: { value: '0.5' } });
    expect(onSliderChange).toHaveBeenCalledWith(0.5);
  });

  it('triggers onToggleMute when mute button is clicked', () => {
    const onToggleMute = vi.fn();
    render(
      <VolumeControl
        sliderValue={0.8}
        isMuted={false}
        onSliderChange={vi.fn()}
        onToggleMute={onToggleMute}
      />
    );

    const button = screen.getByRole('button', { name: 'Mute preview' });
    fireEvent.click(button);
    expect(onToggleMute).toHaveBeenCalledTimes(1);
  });

  it('reflects muted state correctly', () => {
    render(
      <VolumeControl
        sliderValue={0.8}
        isMuted={true}
        onSliderChange={vi.fn()}
        onToggleMute={vi.fn()}
      />
    );

    const button = screen.getByRole('button', { name: 'Unmute preview' });
    expect(button).toBeTruthy();
    expect(button.getAttribute('aria-pressed')).toBe('true');

    const slider = screen.getByRole('slider', { name: 'Preview volume' });
    expect(slider.getAttribute('aria-valuenow')).toBe('0');
    expect(slider.getAttribute('aria-valuetext')).toBe('Muted (-inf dB)');
  });

  it('toggles mute when pressing M on slider', () => {
    const onToggleMute = vi.fn();
    render(
      <VolumeControl
        sliderValue={0.8}
        isMuted={false}
        onSliderChange={vi.fn()}
        onToggleMute={onToggleMute}
      />
    );

    const slider = screen.getByRole('slider', { name: 'Preview volume' });
    fireEvent.keyDown(slider, { key: 'm' });
    expect(onToggleMute).toHaveBeenCalledTimes(1);

    fireEvent.keyDown(slider, { key: 'M' });
    expect(onToggleMute).toHaveBeenCalledTimes(2);
  });

  it('displays persistent dB readout when showReadout is true', () => {
    render(
      <VolumeControl
        sliderValue={1.0}
        isMuted={false}
        onSliderChange={vi.fn()}
        onToggleMute={vi.fn()}
        showReadout={true}
      />
    );

    expect(screen.getByText('0.0 dB')).toBeTruthy();
  });
});
