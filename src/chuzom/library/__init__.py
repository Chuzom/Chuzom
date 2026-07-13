"""chuzom Library — persistent session memory in OKF.

Metaphor map (see docs/LIBRARY.md):
  Library         .chuzom/context/           the store
  Biography       biography/biography.md     stable cross-session project brief
  Book            books/<session>/           one session's memory
  Chapter         books/<s>/chapters/*.md    immutable, sealed on git events
  Working Memory  working-memory/delta.md    mutable in-flight context
  Manuscript      books/<s>/raw/events.jsonl mechanical zero-token harvest
  Abridgement     abridgements/<sha>/<tier>  fit-to-window cache
  Remembering     session-open pack assembly
"""

from chuzom.library.store import LibraryStore  # noqa: F401
