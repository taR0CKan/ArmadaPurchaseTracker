from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CERTS_DIR = BASE_DIR
PEM_DIR = CERTS_DIR / "pem"
CA_BUNDLE = PEM_DIR / "mincifry-ca-bundle.pem"

def certificate_to_pem(certificate: Path) -> bytes:
    """Return a certificate as PEM, accepting either PEM or DER .cer files."""
    raw = certificate.read_bytes()
    if b"-----BEGIN CERTIFICATE-----" in raw:
        return raw if raw.endswith(b"\n") else raw + b"\n"

    # DER certificates are ASN.1 sequences. Convert using Python's standard
    # library so this does not depend on OpenSSL being installed.
    import base64
    import textwrap

    encoded = base64.b64encode(raw).decode("ascii")
    pem = "-----BEGIN CERTIFICATE-----\n"
    pem += "\n".join(textwrap.wrap(encoded, 64))
    pem += "\n-----END CERTIFICATE-----\n"
    return pem.encode("ascii")


def prepare_ca_bundle() -> Path:
    if CA_BUNDLE.is_file():
        return CA_BUNDLE

    certificates = sorted(CERTS_DIR.glob("*.cer"))
    if not certificates:
        raise FileNotFoundError(f"No .cer certificates found in {CERTS_DIR}")

    PEM_DIR.mkdir(exist_ok=True)
    converted = []
    for certificate in certificates:
        pem_path = PEM_DIR / f"{certificate.stem}.pem"
        pem_path.write_bytes(certificate_to_pem(certificate))
        converted.append(pem_path.read_bytes())

    CA_BUNDLE.write_bytes(b"\n".join(converted))
    return CA_BUNDLE