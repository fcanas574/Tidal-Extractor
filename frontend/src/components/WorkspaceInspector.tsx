import type { ReactNode } from 'react';

interface WorkspaceInspectorProps {
  label: string;
  title: string;
  onClose: () => void;
  eyebrow?: string;
  returnLabel?: string;
  children: ReactNode;
}

export default function WorkspaceInspector({
  label,
  title,
  onClose,
  eyebrow = 'Catalog details',
  returnLabel = '← Back to search',
  children,
}: WorkspaceInspectorProps) {
  return (
    <aside className="workspace-inspector" aria-label={`${label} inspector`}>
      <header className="workspace-inspector-header">
        <div className="min-w-0">
          <p className="workspace-eyebrow">{eyebrow}</p>
          <h2 className="workspace-inspector-title">{label}</h2>
        </div>
        <button type="button" className="workspace-inspector-close" onClick={onClose} aria-label={returnLabel} title={`Return from ${title}`}>
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M16 10H4m0 0 5-5m-5 5 5 5" />
          </svg>
          <span>{returnLabel.replace(/^←\s*/, '')}</span>
        </button>
      </header>
      <div className="workspace-inspector-body">{children}</div>
    </aside>
  );
}
