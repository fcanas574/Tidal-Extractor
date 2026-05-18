import { useState, useEffect } from 'react';
import { auth } from '../api';
import { useApp } from '../context/AppContext';

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { dispatch } = useApp();
  const [checking, setChecking] = useState(true);
  const [linking, setLinking] = useState(false);
  const [deviceLink, setDeviceLink] = useState<{ url: string; code: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    auth.getStatus().then((status) => {
      dispatch({ type: 'SET_AUTH', payload: status });
      setChecking(false);
    }).catch(() => setChecking(false));
  }, [dispatch]);

  const handleLogin = async () => {
    setLinking(true);
    setError(null);
    try {
      const link = await auth.getDeviceLink();
      setDeviceLink({ url: link.url, code: link.code });

      const result = await auth.verifyDeviceLink();
      if (result.authenticated) {
        const status = await auth.getStatus();
        dispatch({ type: 'SET_AUTH', payload: status });
      } else {
        setError('Authentication failed. Please try again.');
      }
    } catch (e: any) {
      setError(e.message || 'Authentication failed');
    } finally {
      setLinking(false);
    }
  };

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex items-center gap-3">
          <div className="glow-dot" style={{ animation: 'pulse-glow 1.5s ease-in-out infinite' }} />
          <p style={{ color: 'var(--text-muted)' }}>Connecting to Tidal...</p>
        </div>
      </div>
    );
  }

  return (
    <AuthCheck onLogin={handleLogin} linking={linking} deviceLink={deviceLink} error={error}>
      {children}
    </AuthCheck>
  );
}

function AuthCheck({
  children,
  onLogin,
  linking,
  deviceLink,
  error,
}: {
  children: React.ReactNode;
  onLogin: () => void;
  linking: boolean;
  deviceLink: { url: string; code: string } | null;
  error: string | null;
}) {
  const { state } = useApp();

  if (state.auth.authenticated) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div
        className="w-full max-w-md animate-fade-in"
        style={{
          background: 'var(--glass-bg)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--radius)',
          backdropFilter: 'blur(16px)',
          boxShadow: '0 0 80px rgba(0, 229, 199, 0.05), 0 32px 64px rgba(0, 0, 0, 0.4)',
        }}
      >
        <div className="p-8 text-center">
          <div className="w-14 h-14 rounded-2xl mx-auto mb-5 flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
              boxShadow: '0 0 30px var(--accent-glow)',
            }}
          >
            <svg width="28" height="28" viewBox="0 0 16 16" fill="none">
              <path d="M2 8C2 4.686 4.686 2 8 2s6 2.686 6 6-2.686 6-6 6" stroke="var(--bg-abyss)" strokeWidth="2.5" strokeLinecap="round"/>
              <circle cx="8" cy="8" r="2" fill="var(--bg-abyss)"/>
            </svg>
          </div>

          <h1 className="text-xl font-bold mb-1" style={{ color: 'var(--text-bright)' }}>
            Tidal<span style={{ color: 'var(--accent-primary)' }}>Extractor</span>
          </h1>
          <p className="text-sm mb-6" style={{ color: 'var(--text-muted)' }}>
            Connect your Tidal account to begin
          </p>

          {deviceLink && (
            <div
              className="mb-6 p-4 text-left"
              style={{
                background: 'var(--bg-deep)',
                border: '1px solid var(--glass-border)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <p className="text-xs mb-2" style={{ color: 'var(--text-dim)' }}>
                Visit this URL to link your account:
              </p>
              <a
                href={deviceLink.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm break-all"
                style={{ color: 'var(--accent-primary)' }}
              >
                {deviceLink.url}
              </a>
              <div className="mt-3 flex items-center justify-between">
                <span className="text-xs" style={{ color: 'var(--text-dim)' }}>Code:</span>
                <span
                  className="mono text-sm px-3 py-1 rounded-md"
                  style={{ background: 'var(--bg-mid)', color: 'var(--text-bright)', letterSpacing: '0.15em' }}
                >
                  {deviceLink.code}
                </span>
              </div>
            </div>
          )}

          {error && (
            <p className="text-sm mb-4" style={{ color: 'var(--danger)' }}>{error}</p>
          )}

          <button
            onClick={onLogin}
            disabled={linking}
            className="btn-primary w-full"
          >
            {linking ? 'Waiting for authorization...' : 'Connect Tidal Account'}
          </button>
        </div>
      </div>
    </div>
  );
}
