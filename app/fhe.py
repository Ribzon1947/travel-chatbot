"""
Zama FHE encryption layer for pricing data.

Primary:  concrete-python (Zama) — compiles an FHE circuit on startup, then
          encrypts each pricing integer before it is written to the database.
          Keys are persisted to .fhe/concrete.keys so data survives restarts.

Fallback: AES-256-GCM (cryptography library) — used automatically on Windows
          or any platform where concrete-python is not available.
"""
import os
import struct
import logging
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)

_PRICING_MAX = 100_000          # maximum pricing value in rupees
_FHE_DIR = Path(os.environ.get("FHE_DIR", str(Path(__file__).parent.parent / ".fhe")))
_AES_KEY_FILE = _FHE_DIR / "aes.key"
_CONCRETE_KEY_FILE = _FHE_DIR / "concrete.keys"
_CIRCUIT_FILE = _FHE_DIR / "circuit"   # cached compiled circuit (avoids recompile on restart)

_circuit = None        # Zama concrete circuit
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

        # Fast path: load a pre-compiled circuit saved from the previous run
        if _CIRCUIT_FILE.exists():
            try:
                logger.info("Loading cached Zama FHE circuit from %s…", _CIRCUIT_FILE)
                _circuit = fhe.Circuit.load(str(_CIRCUIT_FILE))
                logger.info("Cached circuit loaded — skipping recompilation.")
            except Exception as load_err:
                logger.warning("Circuit cache invalid (%s); recompiling…", load_err)
                _circuit = None

        # Slow path: compile from scratch (first run, or cache was invalid)
        if _circuit is None:
            @fhe.compiler({"x": "encrypted"})
            def _identity(x):
                return x

            # Small inputset — covers every realistic pricing value with minimal memory use
            inputset = [0, 500, 700, 800, 1800, 2000, 2200, 2500, 2800,
                        3000, 3700, 4000, 4300, 5000, 10000, 50000, 100000]
            logger.info("Compiling Zama FHE circuit — first run, may take 1-2 min…")
            _circuit = _identity.compile(inputset)
            _circuit.save(str(_CIRCUIT_FILE))
            logger.info("Circuit saved to %s for future restarts.", _CIRCUIT_FILE)

        # Load or generate encryption keys
        if _CONCRETE_KEY_FILE.exists():
            logger.info("Loading persisted FHE keys from %s", _CONCRETE_KEY_FILE)
            _circuit.client.keys.load(str(_CONCRETE_KEY_FILE))
        else:
            _circuit.keygen()
            _circuit.client.keys.save(str(_CONCRETE_KEY_FILE))
            logger.info("FHE keys generated and saved to %s", _CONCRETE_KEY_FILE)

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
        return pickle.dumps(result)
    if _mode == "aes":
        return _aes_encrypt(value)
    raise RuntimeError("FHE layer not initialised — call compile_circuit() first.")


def decrypt_value(data: bytes) -> int:
    """Decrypt a pricing integer."""
    if _mode == "concrete":
        result = pickle.loads(data)
        return int(_circuit.decrypt(result))
    if _mode == "aes":
        return _aes_decrypt(data)
    raise RuntimeError("FHE layer not initialised — call compile_circuit() first.")


def encryption_mode() -> str:
    """Return the active encryption backend: 'concrete' or 'aes'."""
    return _mode
