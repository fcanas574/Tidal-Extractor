import { useEffect } from 'react';
import { queue, quality } from '../api';
import { useApp } from '../context/AppContext';

const statusStyles: Record<string, string> = {
  queued: 'bg-gray-700 text-gray-300',
  downloading: 'bg-blue-900 text-blue-300',
  complete: 'bg-green-900 text-green-300',
  failed: 'bg-red-900 text-red-300',
};

export default function QueueView() {
  const { state, dispatch } = useApp();

  useEffect(() => {
    queue.list().then((items) => dispatch({ type: 'SET_QUEUE', payload: items }));
  }, [dispatch]);

  const handleRemove = async (id: number) => {
    await queue.remove(id);
    dispatch({ type: 'REMOVE_QUEUE_ITEM', payload: id });
  };

  const handleProbeQuality = async () => {
    try {
      await quality.probe();
    } catch (e) {
      console.error('Quality probe failed:', e);
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-bold">Download Queue</h2>
        <button
          onClick={handleProbeQuality}
          className="bg-purple-600 hover:bg-purple-700 text-white text-sm font-medium px-3 py-1 rounded-md transition-colors"
        >
          Probe Quality
        </button>
      </div>

      {state.queue.length === 0 ? (
        <p className="text-gray-500 text-center py-8">Queue is empty. Search and add tracks to download.</p>
      ) : (
        <div className="space-y-2">
          {state.queue.map((item) => (
            <div
              key={item.id}
              className="bg-gray-800 rounded-lg p-4"
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex-1 min-w-0">
                  <p className="text-white font-medium truncate">{item.title}</p>
                  <p className="text-gray-400 text-sm truncate">
                    {item.artist} &middot; {item.album} &middot;
                    <span className="ml-1">{item.quality}</span> &middot;
                    <span className="ml-1">{item.format}</span>
                  </p>
                </div>
                <div className="flex items-center gap-2 ml-3">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${statusStyles[item.status] || 'bg-gray-700 text-gray-300'}`}>
                    {item.status}
                  </span>
                  <button
                    onClick={() => handleRemove(item.id)}
                    className="text-gray-500 hover:text-red-400 transition-colors text-sm"
                  >
                    Cancel
                  </button>
                </div>
              </div>
              {item.status === 'downloading' && (
                <div className="w-full bg-gray-700 rounded-full h-2 mt-2">
                  <div
                    className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                    style={{ width: `${item.progress}%` }}
                  />
                </div>
              )}
              {item.status === 'failed' && item.error && (
                <p className="text-red-400 text-sm mt-2">{item.error}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
