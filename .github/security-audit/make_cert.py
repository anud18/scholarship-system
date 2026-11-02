"""Write a throwaway self-signed TLS cert for the scan's nginx.

Usage: make_cert.py HOSTNAME OUT_DIR

Produces the three files nginx.prod.conf references (fullchain.pem,
privkey.pem, chain.pem). Runs inside the backend image, which already ships
`cryptography`, so the runner needs no openssl.
"""

import datetime
import pathlib
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

VALID_DAYS = 2


def main(host: str, out_dir: pathlib.Path) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=VALID_DAYS))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "fullchain.pem").write_bytes(cert_pem)
    (out_dir / "chain.pem").write_bytes(cert_pem)
    (out_dir / "privkey.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    print(f"self-signed cert for {host} written to {out_dir}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], pathlib.Path(sys.argv[2]))
