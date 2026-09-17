"""Persistent TLS identity for this PC.

A self-signed EC certificate generated once and reused for the life of
the installation. Phones pin its SHA-256 fingerprint at pairing time
(trust-on-first-use), so no CA is involved and future connections are
authenticated against the pinned fingerprint.
"""
from __future__ import annotations

import datetime
import hashlib
import logging
import socket
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

log = logging.getLogger(__name__)

CERT_VALIDITY_DAYS = 3650


@dataclass(frozen=True)
class DeviceIdentity:
    cert_path: Path
    key_path: Path
    fingerprint: str  # SHA-256 over the DER certificate, lowercase hex

    @classmethod
    def load_or_create(cls, directory: Path) -> "DeviceIdentity":
        directory.mkdir(parents=True, exist_ok=True)
        cert_path = directory / "receiver-cert.pem"
        key_path = directory / "receiver-key.pem"

        if cert_path.is_file() and key_path.is_file():
            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        else:
            cert = _generate(cert_path, key_path)
            log.info("Generated new TLS identity at %s", cert_path)

        der = cert.public_bytes(serialization.Encoding.DER)
        return cls(
            cert_path=cert_path,
            key_path=key_path,
            fingerprint=hashlib.sha256(der).hexdigest(),
        )


def _generate(cert_path: Path, key_path: Path) -> x509.Certificate:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, f"PixSynq-{socket.gethostname()}")]
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=CERT_VALIDITY_DAYS))
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert
