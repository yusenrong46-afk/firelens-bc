# Comparisons

Status: no canonical comparison recorded.

`python -m firelens_eval compare BASE_SHA CANDIDATE_SHA` reads retained
normalized envelopes without checking out or mutating either revision. Both
runs must name the same suite. A missing or ambiguous artifact, status
regression, failed-count increase, or newly failed case prevents a pass.
