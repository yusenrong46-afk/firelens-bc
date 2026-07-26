# Learning note 03: The frontend renders backend truth

The Source Lens UI has six explicit states: idle, loading, answer, abstention,
provider unavailable, and unexpected error. It never infers evidence from answer
text. A claim is clickable only because the API returned local support pairs;
the source panel is filled from the paired evidence object.

This keeps UI polish from weakening the backend boundary. Current-status
questions show an abstention and official-information direction rather than a
partially helpful static answer.
