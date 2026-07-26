import pytest

from app.scheduler import scheduler, start_scheduler, stop_scheduler


def test_scheduler_start_stop():
    assert not scheduler.running
    start_scheduler()
    assert scheduler.running
    stop_scheduler()
    assert not scheduler.running


def test_scheduler_jobs():
    start_scheduler()
    jobs = scheduler.get_jobs()
    assert len(jobs) >= 1
    assert any(j.id == "rss_cycle" for j in jobs)
    stop_scheduler()
