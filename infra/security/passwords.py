import base64
import hashlib
import hmac
import os


ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 390000
SALT_SIZE = 16


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    salt = os.urandom(SALT_SIZE)
    digest = hashlib.pbkdf2_hmac("sha256", password_bytes, salt, ITERATIONS)

    return (
        f"{ALGORITHM}$"
        f"{ITERATIONS}$"
        f"{base64.b64encode(salt).decode('utf-8')}$"
        f"{base64.b64encode(digest).decode('utf-8')}"
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations_str, salt_b64, digest_b64 = password_hash.split("$", 3)
        if algorithm != ALGORITHM:
            return False

        iterations = int(iterations_str)
        salt = base64.b64decode(salt_b64.encode("utf-8"))
        expected_digest = base64.b64decode(digest_b64.encode("utf-8"))

        actual_digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )

        return hmac.compare_digest(actual_digest, expected_digest)
    except Exception:
        return False