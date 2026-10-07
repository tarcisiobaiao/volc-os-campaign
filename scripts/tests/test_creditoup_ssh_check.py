"""Provas hermeticas: nenhuma conexao real e nenhuma chave privada lida."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "creditoup_check", Path(__file__).resolve().parents[1] / "creditoup_ssh_check.py"
)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class CreditUpCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key = Path(self.tmp.name) / "identity"
        self.key.touch(mode=0o600)  # arquivo vazio, nao uma chave
        self.values = dict(zip(check.NAMES, (
            "example.com", "wordpress-test", "192.0.2.10", "operator",
            str(self.key), "/var/www/example.com", "/var/www/example.com/wp-config.php",
        )))
        self.env = Path(self.tmp.name) / "references.local"
        self.env.write_text("\n".join(f"{k}={v}" for k, v in self.values.items()))
        self.env_patch = patch.dict(os.environ, {}, clear=True)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def settings(self):
        return check.load_settings(self.env)

    def test_loads_only_references(self):
        with self.env.open("a") as f:
            f.write("\nGOOGLE_ADS_CLIENT_SECRET=must-not-load\n")
        settings = self.settings()
        self.assertIsNone(settings.google_ads_client_secret)
        self.assertEqual(settings.creditoup_domain, "example.com")

    def test_missing_reference(self):
        self.env.unlink()
        with self.assertRaisesRegex(ValueError, "Referencia ausente"):
            self.settings()

    def test_duplicate_reference(self):
        with self.env.open("a") as f:
            f.write("\nCREDITOUP_DOMAIN=other.example\n")
        with self.assertRaisesRegex(ValueError, "duplicada"):
            self.settings()

    def test_process_environment_precedence(self):
        with patch.dict(os.environ, {"CREDITOUP_DOMAIN": "override.example"}):
            self.assertEqual(self.settings().creditoup_domain, "override.example")

    def test_missing_and_unsafe_key(self):
        settings = self.settings()
        self.key.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "permissao"):
            check.validate(settings)
        self.key.unlink()
        with self.assertRaisesRegex(ValueError, "Chave SSH ausente"):
            check.validate(settings)

    def test_key_in_repository_rejected(self):
        with patch.object(check, "ROOT", Path(self.tmp.name)):
            with self.assertRaisesRegex(ValueError, "fora do repositorio"):
                check.validate(self.settings())

    def test_invalid_alias_and_config_rejected(self):
        settings = self.settings()
        settings.creditoup_ssh_alias = "-oProxyCommand=anything"
        with self.assertRaisesRegex(ValueError, "invalida"):
            check.validate(settings)
        settings = self.settings()
        settings.creditoup_wp_config = "/etc/passwd"
        with self.assertRaisesRegex(ValueError, "raiz remota"):
            check.validate(settings)

    def test_no_shell_interpolation_in_remote_paths(self):
        settings = self.settings()
        settings.creditoup_remote_root = "/var/www/a; echo unexpected"
        settings.creditoup_wp_config = settings.creditoup_remote_root + "/wp-config.php"
        command = check.remote_command(settings)
        self.assertIn("test -d '/var/www/a; echo unexpected'", command)
        self.assertNotIn("cat ", command)
        self.assertIn("option get home", command)
        self.assertIn("option get siteurl", command)
        self.assertNotIn("option list", command)

    def test_ssh_fixed_options_and_sanitized_response(self):
        local = f"hostname 192.0.2.10\nuser operator\nidentityfile {self.key}\n"
        remote = (
            "DO_NOT_PRINT=unexpected\nHOST=wp-arbitragem-volc-01\nUSER=operator\n"
            "CREDITOUP_WORDPRESS_OK\nWP_CLI=WP-CLI 2.12.0\n"
            "WP_HOME=https://example.com\nWP_SITEURL=https://example.com\nWP_VERSION=6.8.2\n"
        )
        with patch.object(check, "run", side_effect=[local, remote]) as run:
            lines = check.check(self.settings())
        args = run.call_args_list[1].args[0]
        self.assertIn("BatchMode=yes", args)
        self.assertIn("StrictHostKeyChecking=yes", args)
        self.assertIn("PermitLocalCommand=no", args)
        self.assertIn("wordpress-test", args)
        self.assertFalse(any("DO_NOT_PRINT" in line for line in lines))

    def test_alias_mismatch_never_connects(self):
        with patch.object(check, "run", return_value="hostname wrong\nuser operator\n") as run:
            with self.assertRaisesRegex(ValueError, "diverge"):
                check.check(self.settings())
        self.assertEqual(run.call_count, 1)

    def test_failure_does_not_print_remote_errors(self):
        with patch.object(check.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "secret", "secret")):
            with self.assertRaises(ValueError) as error:
                check.run(["ssh"], "SSH")
        self.assertNotIn("secret", str(error.exception))

    def test_no_arbitrary_cli_arguments(self):
        with patch.object(check.sys, "argv", ["check", "rm -rf /"]), patch("sys.stderr", new=check.io.StringIO()), patch.object(check, "check") as run:
            self.assertEqual(check.main(), 2)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
