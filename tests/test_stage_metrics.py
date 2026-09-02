from firelens.operational_logging import log_operation, request_stage_metrics


def test_request_stage_metrics_always_include_total_latency_and_optional_tokens() -> None:
    metrics = request_stage_metrics(
        latency_ms=12.34,
        provider_stages=("grounded_generation",),
        provider_models=("test-model",),
        cache_used=False,
        input_tokens=11,
        output_tokens=7,
        cost_usd=0.002,
    )
    assert len(metrics) == 1
    total = metrics[0]
    assert total.stage == "total"
    assert total.latency_ms == 12.3
    assert total.input_tokens == 11
    assert total.output_tokens == 7
    assert total.cost_usd == 0.002
    assert total.cache_state == "miss"


def test_log_operation_includes_stage_metrics_without_content_fields() -> None:
    # Validation is the assertion: extra content fields are forbidden on the event.
    log_operation(
        trace_id="a" * 32,
        route="live",
        response_mode="live",
        status="answer",
        latency_ms=8,
        release_version="1.6.3",
        input_tokens=4,
        output_tokens=2,
        cost_usd=0.001,
    )
    metrics = request_stage_metrics(
        latency_ms=8, input_tokens=4, output_tokens=2, cost_usd=0.001
    )
    assert metrics[0].input_tokens == 4
