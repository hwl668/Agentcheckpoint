"""AgentCheckpoint: verifiable, restorable execution checkpoints for coding-agent sessions.

Core principle: machine-observed facts (git state, test exit codes, hashes,
timestamps) and agent-reported claims (goal, completed work, decisions,
blockers, next steps) are stored separately and never conflated.
"""

__version__ = "0.3.0"
