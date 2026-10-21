"""Versioned encrypt-then-MAC transport. No secrets embedded in source."""
import base64
import hashlib
import hmac
import json
import secrets
import pyaes

AAD = b"photonicat-companion-v1"


class Crypto:
    def __init__(self, key):
        if len(key) != 32:
            raise ValueError("Expected 256-bit key")
        self.enc = hmac.digest(key, AAD + b"/enc", "sha256")
        self.mac = hmac.digest(key, AAD + b"/mac", "sha256")

    def seal(self, data):
        nonce = secrets.token_bytes(16)
        cipher = pyaes.AESModeOfOperationCTR(
            self.enc, counter=pyaes.Counter(int.from_bytes(nonce, "big"))
        )
        body = b"\x01" + nonce + cipher.encrypt(
            json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode()
        )
        return base64.b64encode(body + hmac.digest(self.mac, AAD + body, "sha256"))

    def open(self, encoded):
        packet = base64.b64decode(encoded, validate=True)
        if len(packet) < 50 or packet[0] != 1:
            raise ValueError("Invalid envelope")
        body, tag = packet[:-32], packet[-32:]
        if not hmac.compare_digest(tag, hmac.digest(self.mac, AAD + body, "sha256")):
            raise ValueError("Authentication failed")
        cipher = pyaes.AESModeOfOperationCTR(
            self.enc, counter=pyaes.Counter(int.from_bytes(body[1:17], "big"))
        )
        result = json.loads(cipher.decrypt(body[17:]))
        if not isinstance(result, dict):
            raise ValueError("Expected object")
        return result
