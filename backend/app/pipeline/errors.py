"""The one error type every pipeline stage raises for problems the user should see."""

# Stage names shown to users.
STAGE_FILE_CHECK = "File check"
STAGE_STT = "Speech-to-text"


class PipelineError(Exception):
    """A user-facing failure: which stage failed, what went wrong, and what to do.

    Example message:
        "Speech-to-text failed: the API key was rejected. Check STT_API_KEY in backend/.env."
    """

    def __init__(self, stage: str, problem: str, fix: str) -> None:
        self.stage = stage
        self.problem = problem
        self.fix = fix
        super().__init__(f"{stage} failed: {problem}. {fix}")
