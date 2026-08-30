import unittest

from volc_agent_harness.preflight import parse_worktrees


class ParseWorktreesTest(unittest.TestCase):
    def test_preserves_each_isolated_tree(self) -> None:
        result = parse_worktrees(
            """worktree /repo
HEAD abc123
branch refs/heads/main

worktree /repo/.agent-worktrees/task-a
HEAD def456
branch refs/heads/agent/task-a
"""
        )

        self.assertEqual(
            result,
            [
                {
                    "worktree": "/repo",
                    "HEAD": "abc123",
                    "branch": "refs/heads/main",
                },
                {
                    "worktree": "/repo/.agent-worktrees/task-a",
                    "HEAD": "def456",
                    "branch": "refs/heads/agent/task-a",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
