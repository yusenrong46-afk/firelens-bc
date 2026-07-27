"""Vercel entry point for the existing FireLens FastAPI application."""

from pathlib import Path

from firelens.api import create_app
from firelens.config import FireLensConfig


app = create_app(FireLensConfig.from_env(Path(__file__).resolve().parent))
