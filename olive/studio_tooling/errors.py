"""Studio tooling failures carry curated, user-readable messages.

They describe the user's own project, toolchain or session (build output,
launch failures, missing tooling); model or provider text never reaches them.
"""


class StudioToolingError(Exception):
    pass
