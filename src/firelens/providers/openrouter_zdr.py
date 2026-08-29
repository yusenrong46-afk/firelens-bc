"""ZDR roster preflight kept separate from the OpenRouter transport adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping

import httpx

from firelens.config import FireLensConfig
from firelens.errors import ProviderError, ProviderErrorKind
from firelens.privacy_policy import ZdrPreflightReport, evaluate_zdr_preflight


async def preflight(
    *,
    config: FireLensConfig,
    client: httpx.AsyncClient,
    headers: Mapping[str, str],
) -> ZdrPreflightReport:
    """Return the ZDR report or raise if a required stage is ineligible."""

    if not config.privacy.any_zdr_required:
        raise ProviderError(
            ProviderErrorKind.INVALID_REQUEST,
            "OpenRouter ZDR preflight requires a ZDR-required stage.",
        )
    try:
        response = await client.get(
            f"{config.openrouter_base_url}/endpoints/zdr", headers=dict(headers)
        )
    except httpx.TimeoutException as exc:
        raise ProviderError(
            ProviderErrorKind.TIMEOUT,
            "OpenRouter ZDR endpoint preflight timed out.",
            retryable=True,
        ) from exc
    except httpx.HTTPError as exc:
        raise ProviderError(
            ProviderErrorKind.UNAVAILABLE,
            "OpenRouter ZDR endpoint preflight was unavailable.",
            retryable=True,
        ) from exc
    if response.status_code == 401:
        raise ProviderError(
            ProviderErrorKind.AUTHENTICATION,
            "OpenRouter rejected the ZDR endpoint preflight credentials.",
            status_code=401,
        )
    if response.status_code >= 400:
        raise ProviderError(
            ProviderErrorKind.UNAVAILABLE,
            "OpenRouter could not verify the ZDR endpoint roster.",
            status_code=response.status_code,
            retryable=response.status_code >= 500,
        )
    try:
        payload = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderError(
            ProviderErrorKind.INVALID_RESPONSE,
            "OpenRouter returned an invalid ZDR endpoint roster.",
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ProviderError(
            ProviderErrorKind.INVALID_RESPONSE,
            "OpenRouter returned an invalid ZDR endpoint roster.",
        )
    eligible_models = {
        endpoint.get("model_id")
        for endpoint in payload["data"]
        if isinstance(endpoint, dict) and isinstance(endpoint.get("model_id"), str)
    }
    report = evaluate_zdr_preflight(
        config.privacy,
        embedding_model=config.embedding_model,
        rerank_model=config.rerank_model,
        generation_model=config.generation_model,
        eligible_models={model for model in eligible_models if isinstance(model, str)},
    )
    if report.missing_required_models:
        raise ProviderError(
            ProviderErrorKind.MODEL_UNAVAILABLE,
            "One or more required stages have no eligible OpenRouter ZDR endpoint.",
            zdr_report=report,
        )
    return report


async def required_models(
    *, config: FireLensConfig, client: httpx.AsyncClient, headers: Mapping[str, str]
) -> tuple[str, ...]:
    await preflight(config=config, client=client, headers=headers)
    required: list[str] = []
    if config.privacy.embedding_zdr == "required":
        required.append(config.embedding_model)
    if config.privacy.reranking_zdr == "required":
        required.append(config.rerank_model)
    if config.privacy.generation_zdr == "required":
        required.append(config.generation_model)
    return tuple(required)
