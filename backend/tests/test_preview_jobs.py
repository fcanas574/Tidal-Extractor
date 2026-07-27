from backend.preview_jobs import PreviewJobManager


def test_start_or_get_is_idempotent():
    manager = PreviewJobManager(analyzer=lambda *_: {})
    first = manager.start_or_get(12, "https://example.test/stream", 240.0)
    second = manager.start_or_get(12, "https://example.test/stream", 240.0)
    assert first.track_id == second.track_id == 12
    assert manager.active_job_count() == 1


def test_snapshot_reports_failed_job():
    manager = PreviewJobManager(
        analyzer=lambda *_: (_ for _ in ()).throw(RuntimeError("decode failed"))
    )
    manager.start_or_get(12, "https://example.test/stream", 240.0)
    manager.run_pending_for_test()
    snapshot = manager.snapshot(12)
    assert snapshot is not None
    assert snapshot.status == "failed"
    assert snapshot.error == "decode failed"
