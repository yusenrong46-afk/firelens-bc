"""Composition root for the FireLens FastAPI application."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import cast

from fastapi import FastAPI

from firelens.api.answer_routes import install_answer_routes
from firelens.api.frontend import install_frontend
from firelens.api.health_feedback import install_health_feedback_routes
from firelens.api.live_routes import install_live_routes
from firelens.api.middleware import install_exception_handlers, install_middlewares
from firelens.config import FireLensConfig
from firelens.errors import ProviderError
from firelens.live import LiveDataService
from firelens.live_answering import LiveAnswerCoordinator
from firelens.privacy_policy import ZdrPreflightReport
from firelens.providers.openrouter import OpenRouterProvider
from firelens.request_guard import AnonymousRequestGuard
from firelens.runtime import Runtime, load_runtime


def _lifespan_factory(
    config: FireLensConfig,
    runtime: Runtime | None,
    live_service: LiveDataService,
    owns_live_service: bool,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = runtime or load_runtime(config)
        app.state.live_service = live_service
        try:
            active_runtime = cast(Runtime, app.state.runtime)
            active_runtime.problems.extend(active_runtime.apply_bound_candidate())
            await _qualify_production_provider(config, active_runtime)
            yield
        finally:
            if runtime is None:
                await active_runtime.aclose()
            if owns_live_service:
                await live_service.aclose()

    return lifespan


async def _qualify_production_provider(config: FireLensConfig, runtime: Runtime) -> None:
    if config.deployment_environment != "production":
        return
    provider = runtime.provider
    if not isinstance(provider, OpenRouterProvider):
        runtime.apply_zdr_preflight(None, failed=True)
        raise RuntimeError("Production requires an OpenRouter provider with ZDR preflight.")
    try:
        report = await provider.preflight_zdr()
    except ProviderError as exc:
        failed_report = exc.zdr_report
        runtime.apply_zdr_preflight(
            failed_report if isinstance(failed_report, ZdrPreflightReport) else None,
            failed=True,
        )
        raise RuntimeError("Production OpenRouter ZDR endpoint preflight failed.") from exc
    runtime.apply_zdr_preflight(report, failed=False)


def create_app(
    config: FireLensConfig | None = None,
    *,
    runtime: Runtime | None = None,
    live_service: LiveDataService | None = None,
) -> FastAPI:
    active_config = config or FireLensConfig.from_env()
    active_live_service = live_service or LiveDataService()
    app = FastAPI(
        title="FireLens BC",
        version=active_config.release_version,
        description=(
            "Evidence-bound wildfire guidance plus bounded official incident, perimeter, "
            "and evacuation records. Not emergency direction."
        ),
        lifespan=_lifespan_factory(
            active_config,
            runtime,
            active_live_service,
            owns_live_service=live_service is None,
        ),
    )
    if runtime is not None:
        app.state.runtime = runtime
    app.state.live_service = active_live_service

    def current_runtime() -> Runtime:
        return cast(Runtime, app.state.runtime)

    def current_live_service() -> LiveDataService:
        return cast(LiveDataService, app.state.live_service)

    request_guard = AnonymousRequestGuard(
        limit=active_config.anonymous_rate_limit,
        window_seconds=active_config.anonymous_rate_window_seconds,
        max_body_bytes=active_config.max_request_body_bytes,
        trusted_proxy_platform=active_config.trusted_proxy_platform,
    )
    install_middlewares(app, request_guard)
    install_exception_handlers(app, active_config)
    install_health_feedback_routes(app, active_config, current_runtime)
    install_live_routes(app, active_config, current_live_service)
    install_answer_routes(
        app,
        active_config,
        current_runtime,
        LiveAnswerCoordinator(active_live_service),
    )
    install_frontend(app, active_config.frontend_dist_path)
    return app
