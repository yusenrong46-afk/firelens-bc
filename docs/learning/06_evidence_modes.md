# Learning note 06: Verified evidence and background are different products

A useful conversational assistant sometimes knows more than its reviewed
collection. FireLens makes that difference public instead of blending it into
one fluent answer.

`verified_corpus` means a local validator resolved every factual claim to an
allowed evidence ID and found every proposed quote exactly in its primary
passage. The model never supplies the public publisher, URL, page, or hash.

`general_background` means the request is related and low-risk, but the current
collection does not directly support the explanation. These claims carry no
FireLens citations, are length-bounded, and display the exact limitation:

> General background — not verified against the FireLens corpus.

Background mode cannot report current conditions, make evacuation choices,
diagnose or treat a person, or claim official authority. A response cannot mix
background claims into a verified badge. Exact quote validation proves
traceability, not semantic entailment; owner claim-to-evidence review therefore
remains a separate release gate.
