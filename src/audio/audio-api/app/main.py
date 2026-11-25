"""uvicorn entry point: `uvicorn app.main:app`."""

from app.presentation.api import create_app

app = create_app()
