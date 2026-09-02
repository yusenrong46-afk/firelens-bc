from __future__ import annotations

import pytest
from pydantic import ValidationError

from firelens.api.health_feedback import ProductEventRequest
from firelens.operational_logging import ProductEvent, log_product_event


def test_product_event_rejects_content_fields() -> None:
    with pytest.raises(ValidationError):
        ProductEventRequest.model_validate({"event": "map_opened", "question": "what fires"})
    with pytest.raises(ValidationError):
        ProductEvent.model_validate(
            {
                "event": "map_opened",
                "release_version": "1.6.3",
                "place": "Kelowna",
            }
        )


def test_product_event_accepts_allowlisted_name() -> None:
    event = log_product_event(event="map_opened", release_version="1.6.3")
    assert event.event == "map_opened"
