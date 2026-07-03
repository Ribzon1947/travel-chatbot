"""
Zama FHE encryption layer for pricing data.

Primary:  concrete-python (Zama) — compiles an FHE circuit on startup, then
          encrypts each pricing integer before it is written to the database.

Fallback: AES-256-GCM (cryptography library) — used automatically on Windows
          or any platform where concrete-python is not available.
"""
import os
import struct
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_FHE_DIR = Path(os.environ.get("FHE_DIR", str(Path(__file__).parent.parent / ".fhe")))
_AES_KEY_FILE = _FHE_DIR / "aes.key"

_circuit = None
_aes_key: bytes | None = None
_mode: str = "none"    # "concrete" | "aes"


def compile_circuit() -> str:
    """
    Self-compile step — called once at startup.
    Returns the encryption mode that will be used: "concrete" or "aes".
    """
    global _circuit, _aes_key, _mode
    _FHE_DIR.mkdir(exist_ok=True)

    # ── Try Zama concrete-python ──────────────────────────────────────────────
    try:
        from concrete import fhe

        @fhe.compiler({"x": "encrypted"})
        def _identity(x):
            return x

        # Minimal inputset covering all real pricing values — keeps compilation fast
        # Includes base prices, Latvaria's high values, and extended range for future increases
        # Range: 0 to 500000+ to support all current and future destination price increases
        inputset = [0, 100, 300, 500, 600, 700, 800, 1000, 1500, 1800, 2000, 2200, 2500, 2800,
                    3000, 3300, 3500, 3700, 4000, 4300, 4500, 5000, 6000, 7000, 8000, 10000,
                    12000, 15000, 20000, 25000, 30000, 40000, 50000, 60000, 75000, 100000, 
                    150000, 200000, 300000, 500000]

        logger.info("Compiling Zama FHE circuit…")
        _circuit = _identity.compile(inputset)
        _circuit.keygen()

        _mode = "concrete"
        logger.info("Zama FHE ready — mode=concrete")
        return _mode

    except Exception as exc:
        logger.warning(
            "Zama concrete-python unavailable (%s). Falling back to AES-256-GCM.", exc
        )

    # ── AES-256-GCM fallback ─────────────────────────────────────────────────
    if _AES_KEY_FILE.exists():
        _aes_key = _AES_KEY_FILE.read_bytes()
        logger.info("AES-256-GCM key loaded from %s", _AES_KEY_FILE)
    else:
        _aes_key = os.urandom(32)
        _AES_KEY_FILE.write_bytes(_aes_key)
        logger.info("AES-256-GCM key generated and saved to %s", _AES_KEY_FILE)

    _mode = "aes"
    return _mode


# ── AES helpers ───────────────────────────────────────────────────────────────

def _aes_encrypt(value: int) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    plaintext = struct.pack(">Q", value)  # 8-byte big-endian unsigned int
    ct = AESGCM(_aes_key).encrypt(nonce, plaintext, None)
    return nonce + ct                      # 12-byte nonce prepended


def _aes_decrypt(data: bytes) -> int:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce, ct = data[:12], data[12:]
    plaintext = AESGCM(_aes_key).decrypt(nonce, ct, None)
    return struct.unpack(">Q", plaintext)[0]


# ── Public API ────────────────────────────────────────────────────────────────

def encrypt_value(value: int) -> bytes:
    """Encrypt a pricing integer. Uses Zama FHE if available, else AES-GCM."""
    if _mode == "concrete":
        enc = _circuit.encrypt(value)
        result = _circuit.run(enc)
        return bytes(result.serialize())   # TransportValue native serialization
    if _mode == "aes":
        return _aes_encrypt(value)
    raise RuntimeError("FHE layer not initialised — call compile_circuit() first.")


def decrypt_value(data: bytes) -> int:
    """Decrypt a pricing integer."""
    if _mode == "concrete":
        from concrete.fhe import Value          
        result = Value.deserialize(data)
        return int(_circuit.decrypt(result))
    if _mode == "aes":
        return _aes_decrypt(data)
    raise RuntimeError("FHE layer not initialised — call compile_circuit() first.")


def encryption_mode() -> str:
    """Return the active encryption backend: 'concrete' or 'aes'."""
    return _mode
