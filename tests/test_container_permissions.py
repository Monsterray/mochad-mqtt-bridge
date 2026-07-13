from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ContainerPermissionsTests(unittest.TestCase):
    def test_entrypoint_has_valid_shell_syntax(self) -> None:
        subprocess.run(
            ["sh", "-n", str(ROOT / "docker-entrypoint.sh")],
            check=True,
        )

    def test_entrypoint_prepares_only_config_before_dropping_privileges(self) -> None:
        entrypoint = (ROOT / "docker-entrypoint.sh").read_text()

        self.assertIn('PUID="${PUID:-911}"', entrypoint)
        self.assertIn('PGID="${PGID:-911}"', entrypoint)
        self.assertIn('TZ="${TZ:-UTC}"', entrypoint)
        self.assertIn('UMASK="${UMASK:-022}"', entrypoint)
        self.assertIn('ALLOW_ROOT="${ALLOW_ROOT:-false}"', entrypoint)
        self.assertIn('mkdir -p /config', entrypoint)
        self.assertIn('chown -R "$PUID:$PGID" /config', entrypoint)
        self.assertNotIn("chown -R \"$PUID:$PGID\" /app", entrypoint)
        self.assertNotIn("chown -R \"$PUID:$PGID\" .", entrypoint)
        self.assertIn("ALLOW_ROOT=true", entrypoint)
        self.assertIn('exec su-exec "$user_name" "$@"', entrypoint)

    def test_dockerfile_keeps_application_owned_by_root(self) -> None:
        dockerfile = (ROOT / "Dockerfile").read_text()

        self.assertNotIn("USER bridge", dockerfile)
        self.assertNotIn("COPY --chown", dockerfile)
        self.assertIn("ENV PUID=911", dockerfile)
        self.assertIn("ENV PGID=911", dockerfile)
        self.assertIn("ENV UMASK=022", dockerfile)
        self.assertIn("su-exec", dockerfile)
        self.assertIn('ENTRYPOINT ["/sbin/tini","--","/app/docker-entrypoint.sh"]', dockerfile)

    def test_secrets_compose_uses_run_secrets_and_file_env_vars(self) -> None:
        compose = (ROOT / "docker-compose.secrets.yml").read_text()

        self.assertIn("secrets:", compose)
        self.assertIn("MQTT_PASSWORD_FILE: /run/secrets/mqtt_password", compose)
        self.assertIn("MQTT_TLS_CA_FILE: /run/secrets/mqtt_ca", compose)
        self.assertIn("MQTT_TLS_CERT_FILE: /run/secrets/mqtt_client_cert", compose)
        self.assertIn("MQTT_TLS_KEY_FILE: /run/secrets/mqtt_client_key", compose)
        self.assertIn(
            "MQTT_TLS_KEY_PASSWORD_FILE: /run/secrets/mqtt_client_key_password",
            compose,
        )
        self.assertNotIn("/config/mqtt_password", compose)

    def test_compose_exposes_allow_root_as_false_by_default(self) -> None:
        compose = (ROOT / "docker-compose.yml").read_text()
        env_example = (ROOT / ".env.example").read_text()

        self.assertIn("ALLOW_ROOT: ${ALLOW_ROOT:-false}", compose)
        self.assertIn("ALLOW_ROOT=false", env_example)

    def test_gitignore_excludes_real_secret_files(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text()

        self.assertIn("secrets/", gitignore)
        self.assertIn("*.key", gitignore)
        self.assertIn("*.pem", gitignore)

    def test_container_permission_validator_has_valid_shell_syntax(self) -> None:
        script = ROOT / "scripts" / "validate" / "container_permissions.sh"

        subprocess.run(["bash", "-n", str(script)], check=True)
