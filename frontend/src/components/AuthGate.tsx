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
        <p className="text-gray-400">Checking authentication...</p>
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
    <div className="min-h-screen flex items-center justify-center">
      <div className="bg-gray-900 rounded-xl p-8 max-w-md w-full text-center">
        <h1 className="text-2xl font-bold mb-2">TidalExtractor</h1>
        <p className="text-gray-400 mb-6">Connect your Tidal account to get started</p>

        {deviceLink && (
          <div className="mb-6 p-4 bg-gray-800 rounded-lg">
            <p className="text-sm text-gray-400 mb-2">Visit this URL to link your account:</p>
            <a
              href={deviceLink.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 underline break-all text-sm"
            >
              {deviceLink.url}
            </a>
            <p className="text-sm text-gray-400 mt-2">Code: <span className="text-white font-mono">{deviceLink.code}</span></p>
          </div>
        )}

        {error && <p className="text-red-400 text-sm mb-4">{error}</p>}

        <button
          onClick={onLogin}
          disabled={linking}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white font-semibold py-2 px-6 rounded-lg transition-colors"
        >
          {linking ? 'Waiting for authorization...' : 'Connect Tidal Account'}
        </button>
      </div>
    </div>
  );
}
