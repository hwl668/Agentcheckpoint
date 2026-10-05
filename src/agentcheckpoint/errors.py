"""User-facing error types.

Everything raised to the CLI is a subclass of AgentCheckpointError; the CLI
turns those into ``error: ...`` messages on stderr with exit code 2.
"""


class AgentCheckpointError(RuntimeError):
    """Base class for user-facing errors."""


class StoreError(AgentCheckpointError):
    """Problem with the .agentcheckpoint store (missing, malformed, bad reference)."""


class NotAGitRepository(StoreError):
    """The working directory is not inside a git work tree."""


class CheckpointError(StoreError):
    """A checkpoint is missing, corrupt, or the reference is ambiguous."""


class GitError(AgentCheckpointError):
    """A git command failed."""


class RestoreError(AgentCheckpointError):
    """A restore operation could not be completed safely."""
