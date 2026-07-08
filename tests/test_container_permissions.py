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
        self.assertIn('mkdir -p /config', entrypoint)
        self.assertIn('chown -R "$PUID:$PGID" /config', entrypoint)
        self.assertNotIn("chown -R \"$PUID:$PGID\" /app", entrypoint)
        self.assertNotIn("chown -R \"$PUID:$PGID\" .", entrypoint)
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

