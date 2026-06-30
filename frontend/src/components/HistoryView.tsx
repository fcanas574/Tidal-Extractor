import { useEffect, useState } from "react";
import { history as historyApi } from "../api";
import { useApp } from "../context/AppContext";

export default function HistoryView() {
  const { state, dispatch } = useApp();
  const [offset] = useState(0);
  const limit = 50;

  useEffect(() => {
    dispatch({ type: "SET_HISTORY_LOADING", payload: true });
    historyApi.list(offset, limit).then((items) => {
      dispatch({ type: "SET_HISTORY", payload: items });
    });
  }, [offset, dispatch]);

  const handleReDownload = async (item: any) => {
    try {
      const added = await historyApi.reDownload({
        tidal_id: item.tidal_id,
        title: item.title,
        artist: item.artist,
        album: item.album,
        quality: item.quality,
        format: item.format,
      });
      dispatch({ type: "UPDATE_QUEUE_ITEM", payload: added });
      dispatch({
        type: "ADD_TOAST",
        payload: {
          id: `re-dl-${Date.now()}`,
          type: "info",
          title: "Re-added to queue",
          detail: item.title,
          dismissAt: Date.now() + 3000,
        },
      });
    } catch {
      dispatch({
        type: "ADD_TOAST",
        payload: {
          id: `re-dl-err-${Date.now()}`,
          type: "error",
          title: "Failed to re-download",
          detail: item.title,
          dismissAt: Date.now() + 4000,
        },
      });
    }
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 animate-fade-in">
      <h2 className="text-lg font-bold mb-6" style={{ color: "var(--text-bright)" }}>
        Download History
      </h2>

      {state.historyLoading ? (
        <div className="text-center py-12">
          <div className="w-6 h-6 border-2 border-current border-t-transparent rounded-full animate-spin mx-auto" style={{ color: "var(--text-dim)" }} />
        </div>
      ) : state.history.length === 0 ? (
        <div className="text-center py-24">
          <p className="text-sm" style={{ color: "var(--text-dim)" }}>No download history yet.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {state.history.map((item) => (
            <div
              key={item.id}
              className="glass p-4 flex items-center justify-between"
            >
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate" style={{ color: "var(--text-bright)" }}>
                  {item.title}
                </p>
                <p className="text-xs truncate mt-0.5" style={{ color: "var(--text-muted)" }}>
                  {item.artist}
                  {item.album && ` · ${item.album}`}
                  {" · "}
                  <span className="mono" style={{ color: "var(--text-dim)" }}>{item.quality}</span>
                  {" · "}
                  <span className="mono" style={{ color: "var(--text-dim)" }}>{item.format}</span>
                </p>
                <p className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
                  {formatSize(item.file_size)} · {new Date(item.downloaded_at).toLocaleDateString()}
                </p>
              </div>
              <div className="flex items-center gap-2 ml-3">
                <button
                  onClick={() => handleReDownload(item)}
                  className="btn-primary text-xs px-3 py-1.5"
                >
                  Re-download
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
