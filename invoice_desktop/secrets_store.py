from __future__ import annotations

import base64


def protect_secret(secret: str) -> str:
    if not secret:
        return ""
    import win32crypt

    protected = win32crypt.CryptProtectData(
        secret.encode("utf-8"),
        "SYNTEC Invoice Manager",
        None,
        None,
        None,
        0,
    )
    return base64.b64encode(protected).decode("ascii")


def unprotect_secret(protected_secret: str) -> str:
    if not protected_secret:
        return ""
    import win32crypt
    import pywintypes

    encrypted = base64.b64decode(protected_secret.encode("ascii"))
    try:
        _, unprotected = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
    except pywintypes.error:
        return ""
    return unprotected.decode("utf-8")
