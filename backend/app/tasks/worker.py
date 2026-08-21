try:
    from celery import Celery
    from app.core.config import settings

    celery_app = Celery(
        "ragenius_tasks",
        broker=settings.CELERY_BROKER_URL,
        backend=settings.CELERY_RESULT_BACKEND,
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        imports=["app.tasks.ingestion_tasks"],
        worker_prefetch_multiplier=1,
    )
except ImportError:
    class DummyCelery:
        def task(self, *args, **kwargs):
            def decorator(fn):
                fn.delay = lambda *a, **kw: None
                return fn
            return decorator

    celery_app = DummyCelery()
