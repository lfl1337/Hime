"""
Hime training-time helpers (curriculum learning, callbacks, dataset loaders).

This package is imported by the standalone training scripts in scripts/, NOT by
the FastAPI backend. Do not import from `app.routers` or `app.services` here —
that would pull SQLAlchemy/FastAPI into the training process, which only needs
HuggingFace + datasets.
"""
