import { useEffect, useState, type ReactNode } from 'react';
import { auth } from '../api';
import { useApp } from '../context/AppContext';

export default function AuthGate({ children }: { children: ReactNode }) {
  const { dispatch, state } = useApp();
  const [checking, setChecking] = useState(true);
  const [checkingError, setCheckingError] = useState<string | null>(null);
  const [linking, setLinking] = useState(false);
  const [deviceLink, setDeviceLink] = useState<{ url: string; code: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const checkAuth = async () => {
    setChecking(true);
    setCheckingError(null);
    try {
      dispatch({ type: 'SET_AUTH', payload: await auth.getStatus() });
    } catch (checkError) {
      setCheckingError(checkError instanceof Error ? checkError.message : 'Could not check your Tidal session.');
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => { void checkAuth(); }, []);

  const handleLogin = async () => {
    setLinking(true);
    setError(null);
    try {
      const link = await auth.getDeviceLink();
      setDeviceLink({ url: link.url, code: link.code });
      const result = await auth.verifyDeviceLink();
      if (!result.authenticated) {
        setError('Authentication was not completed. Try connecting again.');
        return;
      }
      dispatch({ type: 'SET_AUTH', payload: await auth.getStatus() });
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : 'Authentication failed.');
    } finally {
      setLinking(false);
    }
  };

  if (checking) return <div className="min-h-screen flex items-center justify-center" role="status" aria-live="polite"><div className="flex items-center gap-3"><div className="glow-dot" aria-hidden="true" /><p style={{ color: 'var(--text-muted)' }}>Checking Tidal connection…</p></div></div>;

  if (checkingError) return <div className="min-h-screen flex items-center justify-center p-4"><div className="glass w-full max-w-md p-8 text-center" role="alert"><h1 className="text-lg font-semibold" style={{ color: 'var(--text-bright)' }}>Connection check failed</h1><p className="text-sm mt-2" style={{ color: 'var(--text-muted)' }}>{checkingError}</p><button type="button" className="btn-primary w-full mt-6" onClick={() => void checkAuth()}>Retry connection</button></div></div>;

  if (state.auth.authenticated) return <>{children}</>;

  return <AuthCheck onLogin={handleLogin} linking={linking} deviceLink={deviceLink} error={error} />;
}

function AuthCheck({ onLogin, linking, deviceLink, error }: { onLogin: () => void; linking: boolean; deviceLink: { url: string; code: string } | null; error: string | null }) {
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="glass w-full max-w-md animate-fade-in" style={{ background: 'var(--glass-bg)', backdropFilter: 'blur(16px)', boxShadow: '0 0 80px rgba(141, 231, 213, 0.05), 0 32px 64px rgba(0, 0, 0, 0.4)' }}>
        <div className="p-8 text-center">
          <div className="w-14 h-14 rounded-2xl mx-auto mb-5 flex items-center justify-center" aria-hidden="true" style={{ background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))', boxShadow: '0 0 30px var(--accent-glow)' }}><svg width="28" height="28" viewBox="0 0 16 16" fill="none"><path d="M2 8C2 4.686 4.686 2 8 2s6 2.686 6 6-2.686 6-6 6" stroke="var(--bg-abyss)" strokeWidth="2.5" strokeLinecap="round" /><circle cx="8" cy="8" r="2" fill="var(--bg-abyss)" /></svg></div>
          <h1 className="text-xl font-bold mb-1" style={{ color: 'var(--text-bright)' }}>Tidal<span style={{ color: 'var(--accent-primary)' }}>Extractor</span></h1>
          <p className="text-sm mb-6" style={{ color: 'var(--text-muted)' }}>Connect your Tidal account to begin.</p>

          {deviceLink && <div className="mb-6 p-4 text-left" aria-live="polite" style={{ background: 'var(--bg-deep)', border: '1px solid var(--glass-border)', borderRadius: 'var(--radius-sm)' }}><p className="text-xs mb-2" style={{ color: 'var(--text-dim)' }}>Open this link to authorize Tidal:</p><a href={deviceLink.url} target="_blank" rel="noopener noreferrer" className="text-sm break-all" style={{ color: 'var(--accent-primary)' }}>{deviceLink.url}</a><div className="mt-3 flex items-center justify-between gap-3"><span className="text-xs" style={{ color: 'var(--text-dim)' }}>Device code</span><span className="mono text-sm px-3 py-1 rounded-md" style={{ background: 'var(--bg-mid)', color: 'var(--text-bright)', letterSpacing: '0.15em' }}>{deviceLink.code}</span></div>{linking && <p className="text-xs mt-3" role="status" style={{ color: 'var(--accent-secondary)' }}>Waiting for authorization…</p>}</div>}
          {error && <p className="text-sm mb-4" role="alert" style={{ color: 'var(--danger)' }}>{error}</p>}
          <button type="button" onClick={onLogin} disabled={linking} className="btn-primary w-full">{linking ? 'Waiting for authorization…' : error ? 'Try again' : 'Connect Tidal account'}</button>
        </div>
      </div>
    </div>
  );
}
