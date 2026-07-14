import contextlib
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import textwrap
import threading
import time
import unittest
import uuid
from pathlib import Path

import pytest

from config import MqttTlsConfig
from mqtt_client import MqttClient


RUN_INTEGRATION = os.getenv("RUN_MQTT_TLS_INTEGRATION") == "1"

pytestmark = [pytest.mark.integration, pytest.mark.tls]


@unittest.skipUnless(
    RUN_INTEGRATION,
    "set RUN_MQTT_TLS_INTEGRATION=1 to run Mosquitto TLS integration tests",
)
class MosquittoTlsIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("openssl") is None:
            raise unittest.SkipTest("openssl is not available")

        if shutil.which("mosquitto") is None:
            raise unittest.SkipTest("mosquitto is not available")

    def test_untrusted_ca_fails(self):
        with tempfile.TemporaryDirectory() as tempdir:
            certs = _generate_test_certs(Path(tempdir))
            port = _free_port()
            config = _write_mosquitto_config(
                Path(tempdir),
                port=port,
                ca_file=certs["ca_crt"],
                cert_file=certs["server_crt"],
                key_file=certs["server_key"],
                require_certificate=False,
            )

            with _mosquitto(config, port):
                self.assertFalse(
                    _mqtt_connects(
                        port,
                        MqttTlsConfig(enabled=True),
                    )
                )

    def test_hostname_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tempdir:
            certs = _generate_test_certs(Path(tempdir))
            port = _free_port()
            config = _write_mosquitto_config(
                Path(tempdir),
                port=port,
                ca_file=certs["ca_crt"],
                cert_file=certs["wronghost_crt"],
                key_file=certs["wronghost_key"],
                require_certificate=False,
            )

            with _mosquitto(config, port):
                self.assertFalse(
                    _mqtt_connects(
                        port,
                        MqttTlsConfig(
                            enabled=True,
                            ca_file=str(certs["ca_crt"]),
                        ),
                    )
                )

    def test_mutual_tls_succeeds(self):
        with tempfile.TemporaryDirectory() as tempdir:
            certs = _generate_test_certs(Path(tempdir))
            port = _free_port()
            config = _write_mosquitto_config(
                Path(tempdir),
                port=port,
                ca_file=certs["ca_crt"],
                cert_file=certs["server_crt"],
                key_file=certs["server_key"],
                require_certificate=True,
            )

            with _mosquitto(config, port):
                self.assertTrue(
                    _mqtt_connects(
                        port,
                        MqttTlsConfig(
                            enabled=True,
                            ca_file=str(certs["ca_crt"]),
                            cert_file=str(certs["client_crt"]),
                            key_file=str(certs["client_key"]),
                        ),
                    )
                )


def _mqtt_connects(
    port: int,
    tls_config: MqttTlsConfig,
) -> bool:
    connected = threading.Event()
    client = MqttClient(
        host="localhost",
        port=port,
        client_id=f"mqtt-tls-test-{uuid.uuid4()}",
        tls_config=tls_config,
    )
    client.set_connect_callback(connected.set)

    try:
        try:
            client.connect()
        except (OSError, RuntimeError, ssl.SSLError):
            return False

        return connected.wait(5)

    finally:
        with contextlib.suppress(Exception):
            client.disconnect()


@contextlib.contextmanager
def _mosquitto(
    config_path: Path,
    port: int,
):
    process = subprocess.Popen(
        [
            "mosquitto",
            "-c",
            str(config_path),
            "-v",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_port(port, process)
        yield process
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.communicate(timeout=5)
        if process.poll() is None:
            process.kill()
            process.communicate(timeout=5)


def _wait_for_port(
    port: int,
    process: subprocess.Popen,
) -> None:
    deadline = time.time() + 8

    while time.time() < deadline:
        if process.poll() is not None:
            output = ""
            if process.stdout is not None:
                output = process.stdout.read()
            raise AssertionError(
                f"mosquitto exited before listening: {output}"
            )

        with contextlib.suppress(OSError):
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return

        time.sleep(0.1)

    raise AssertionError(f"mosquitto did not listen on port {port}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _write_mosquitto_config(
    directory: Path,
    port: int,
    ca_file: Path,
    cert_file: Path,
    key_file: Path,
    require_certificate: bool,
) -> Path:
    config_path = directory / "mosquitto.conf"
    config_path.write_text(
        textwrap.dedent(
            f"""
            listener {port} 127.0.0.1
            allow_anonymous true
            cafile {ca_file}
            certfile {cert_file}
            keyfile {key_file}
            require_certificate {'true' if require_certificate else 'false'}
            use_identity_as_username false
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    return config_path


def _generate_test_certs(
    directory: Path,
) -> dict[str, Path]:
    ca_key = directory / "ca.key"
    ca_crt = directory / "ca.crt"
    server_key = directory / "server.key"
    server_csr = directory / "server.csr"
    server_crt = directory / "server.crt"
    wronghost_key = directory / "wronghost.key"
    wronghost_csr = directory / "wronghost.csr"
    wronghost_crt = directory / "wronghost.crt"
    client_key = directory / "client.key"
    client_csr = directory / "client.csr"
    client_crt = directory / "client.crt"

    _openssl(
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-subj",
        "/CN=mqtt-tls-test-ca",
        "-keyout",
        ca_key,
        "-out",
        ca_crt,
    )

    _certificate_request(
        directory,
        common_name="localhost",
        san="DNS:localhost",
        key_path=server_key,
        csr_path=server_csr,
    )
    _sign_certificate(
        directory,
        csr_path=server_csr,
        ca_crt=ca_crt,
        ca_key=ca_key,
        cert_path=server_crt,
        san="DNS:localhost",
    )

    _certificate_request(
        directory,
        common_name="wronghost",
        san="DNS:wronghost",
        key_path=wronghost_key,
        csr_path=wronghost_csr,
    )
    _sign_certificate(
        directory,
        csr_path=wronghost_csr,
        ca_crt=ca_crt,
        ca_key=ca_key,
        cert_path=wronghost_crt,
        san="DNS:wronghost",
    )

    _certificate_request(
        directory,
        common_name="mqtt-client",
        san="",
        key_path=client_key,
        csr_path=client_csr,
    )
    _sign_certificate(
        directory,
        csr_path=client_csr,
        ca_crt=ca_crt,
        ca_key=ca_key,
        cert_path=client_crt,
        san="",
        client_auth=True,
    )

    return {
        "ca_crt": ca_crt,
        "server_key": server_key,
        "server_crt": server_crt,
        "wronghost_key": wronghost_key,
        "wronghost_crt": wronghost_crt,
        "client_key": client_key,
        "client_crt": client_crt,
    }


def _certificate_request(
    directory: Path,
    common_name: str,
    san: str,
    key_path: Path,
    csr_path: Path,
) -> None:
    config_path = directory / f"{common_name}.req.cnf"
    config_path.write_text(
        _openssl_config(common_name, san),
        encoding="utf-8",
    )
    _openssl(
        "req",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-keyout",
        key_path,
        "-out",
        csr_path,
        "-config",
        config_path,
    )


def _sign_certificate(
    directory: Path,
    csr_path: Path,
    ca_crt: Path,
    ca_key: Path,
    cert_path: Path,
    san: str,
    client_auth: bool = False,
) -> None:
    config_path = directory / f"{cert_path.stem}.ext.cnf"
    config_path.write_text(
        _openssl_extension_config(san, client_auth),
        encoding="utf-8",
    )
    _openssl(
        "x509",
        "-req",
        "-in",
        csr_path,
        "-CA",
        ca_crt,
        "-CAkey",
        ca_key,
        "-CAcreateserial",
        "-out",
        cert_path,
        "-days",
        "1",
        "-sha256",
        "-extensions",
        "v3_req",
        "-extfile",
        config_path,
    )


def _openssl_config(
    common_name: str,
    san: str,
) -> str:
    lines = [
        "[req]",
        "prompt = no",
        "distinguished_name = dn",
        "req_extensions = v3_req",
        "[dn]",
        f"CN = {common_name}",
        "[v3_req]",
    ]

    if san:
        lines.append(f"subjectAltName = {san}")

    return "\n".join(lines) + "\n"


def _openssl_extension_config(
    san: str,
    client_auth: bool,
) -> str:
    lines = ["[v3_req]"]

    if san:
        lines.append(f"subjectAltName = {san}")

    if client_auth:
        lines.append("extendedKeyUsage = clientAuth")

    return "\n".join(lines) + "\n"


def _openssl(
    *args,
) -> None:
    subprocess.run(
        ["openssl", *[str(arg) for arg in args]],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    unittest.main()
