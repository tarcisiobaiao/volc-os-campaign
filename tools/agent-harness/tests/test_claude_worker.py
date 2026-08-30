import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from volc_agent_harness.claude_worker import (
    AUTH_SOURCE_NAME,
    CHILD_AUTH_NAME,
    ClaudeIsolationNoGo,
    ExplicitClaudeAuthentication,
    isolated_claude_runtime,
)


class ClaudeWorkerIsolationTest(unittest.TestCase):
    def test_is_no_go_by_default(self) -> None:
        with self.assertRaisesRegex(ClaudeIsolationNoGo, "NO-GO"):
            with isolated_claude_runtime(None):
                self.fail("runtime nao deveria iniciar")

    def test_requires_dedicated_explicit_auth_source(self) -> None:
        personal = {
            "CLAUDE_CODE_OAUTH_TOKEN": "personal-token",
            "ANTHROPIC_API_KEY": "personal-api-key",
        }
        with self.assertRaisesRegex(ClaudeIsolationNoGo, AUTH_SOURCE_NAME):
            ExplicitClaudeAuthentication.from_mapping(personal)

        auth = ExplicitClaudeAuthentication.from_mapping(
            {AUTH_SOURCE_NAME: "explicit-token"}
        )
        self.assertNotIn("explicit-token", repr(auth))

    def test_does_not_inherit_home_or_read_personal_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            personal_home = root / "personal-home"
            personal_config = personal_home / ".claude"
            personal_config.mkdir(parents=True)
            personal_settings = personal_config / "settings.json"
            personal_settings.write_text('{"forbidden": true}\n', encoding="utf-8")

            auth = ExplicitClaudeAuthentication("explicit-token")
            original_read_text = Path.read_text

            def guarded_read_text(path: Path, *args, **kwargs):
                if path.resolve() == personal_settings.resolve():
                    raise AssertionError("configuracao pessoal foi lida")
                return original_read_text(path, *args, **kwargs)

            with patch.object(Path, "read_text", guarded_read_text):
                with isolated_claude_runtime(
                    auth,
                    base_environment={
                        "PATH": "/bin",
                        "HOME": str(personal_home),
                        "CLAUDE_CONFIG_DIR": str(personal_config),
                        "CLAUDE_CODE_OAUTH_TOKEN": "ambient-personal-token",
                        "ANTHROPIC_API_KEY": "ambient-api-key",
                    },
                    temporary_parent=root / "isolated",
                ) as runtime:
                    self.assertNotEqual(runtime.home, personal_home)
                    self.assertNotEqual(runtime.config_dir, personal_config)
                    self.assertEqual(runtime.environment["HOME"], str(runtime.home))
                    self.assertEqual(
                        runtime.environment["CLAUDE_CONFIG_DIR"],
                        str(runtime.config_dir),
                    )
                    self.assertEqual(
                        runtime.environment[CHILD_AUTH_NAME], "explicit-token"
                    )
                    self.assertNotIn("ANTHROPIC_API_KEY", runtime.environment)
                    self.assertEqual(
                        (runtime.config_dir / "settings.json").read_text(
                            encoding="utf-8"
                        ),
                        "{}\n",
                    )
                    self.assertNotIn("explicit-token", repr(runtime))
                    self.assertNotIn("explicit-token", repr(runtime.environment))

            self.assertEqual(
                personal_settings.read_text(encoding="utf-8"),
                '{"forbidden": true}\n',
            )

    def test_runtime_is_ephemeral(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            auth = ExplicitClaudeAuthentication("explicit-token")
            with isolated_claude_runtime(
                auth, temporary_parent=Path(temp)
            ) as runtime:
                root = runtime.home.parent
                self.assertTrue(root.exists())
                self.assertEqual(runtime.home.stat().st_mode & 0o777, 0o700)
                self.assertEqual(runtime.config_dir.stat().st_mode & 0o777, 0o700)
                self.assertEqual(
                    (runtime.config_dir / "settings.json").stat().st_mode & 0o777,
                    0o600,
                )
            self.assertFalse(root.exists())

    def test_rejects_empty_or_multiline_token(self) -> None:
        for token in ("", "   ", "one\ntwo", "one\rtwo", "one\0two"):
            with self.subTest(token=repr(token)):
                with self.assertRaises(ClaudeIsolationNoGo):
                    ExplicitClaudeAuthentication(token)


if __name__ == "__main__":
    unittest.main()
