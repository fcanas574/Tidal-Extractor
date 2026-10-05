// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DownloadButton from './DownloadButton';

describe('DownloadButton', () => {
  it('uses the canonical queue state for progress and completion', () => {
    const onDownload = vi.fn();
    const { rerender } = render(
      <DownloadButton title="Night Drive" status="downloading" progress={68} onDownload={onDownload} />,
    );

    expect(screen.getByRole('button', { name: 'Downloading Night Drive, 68 percent' })).toBeDisabled();
    expect(screen.getByRole('button')).toHaveTextContent('68');

    rerender(<DownloadButton title="Night Drive" status="complete" progress={100} onDownload={onDownload} />);
    expect(screen.getByRole('button', { name: 'Download complete for Night Drive' })).toBeDisabled();
    expect(screen.queryByText('68')).not.toBeInTheDocument();
  });

  it('offers a fixed retry action for failed downloads', () => {
    const onDownload = vi.fn();
    render(<DownloadButton title="Night Drive" status="failed" error="Network error" onDownload={onDownload} />);

    fireEvent.click(screen.getByRole('button', { name: 'Retry download Night Drive' }));
    expect(onDownload).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button')).toHaveAttribute('title', 'Network error. Retry download');
  });
});
