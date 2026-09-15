"""Generate the Android release keystore + keystore.properties.

The password is created locally and written only to keystore.properties
(git-ignored). Run once; back up both files somewhere safe — losing the
keystore means you can never update installed copies of the app.

Usage:  python generate_keystore.py [path-to-keytool]
"""
from __future__ import annotations

import secrets
import string
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEYSTORE = HERE / "photosync-release.keystore"
PROPS = HERE / "keystore.properties"

DEFAULT_KEYTOOL = r"C:\Program Files\Android\Android Studio\jbr\bin\keytool.exe"


def main() -> int:
    if KEYSTORE.exists():
        print(f"Refusing to overwrite existing {KEYSTORE.name}")
        return 1
    keytool = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_KEYTOOL

    alphabet = string.ascii_letters + string.digits
    password = "".join(secrets.choice(alphabet) for _ in range(32))

    result = subprocess.run(
        [
            keytool, "-genkeypair", "-v",
            "-keystore", str(KEYSTORE),
            "-alias", "photosync",
            "-keyalg", "RSA", "-keysize", "4096",
            "-validity", "10000",
            "-storepass:env", "KSPASS",
            "-keypass:env", "KSPASS",
            "-dname", "CN=PhotoSync, O=PhotoSync",
        ],
        env={"KSPASS": password, "PATH": ""},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr[-500:])
        return 1

    PROPS.write_text(
        "storeFile=photosync-release.keystore\n"
        f"storePassword={password}\n"
        "keyAlias=photosync\n"
        f"keyPassword={password}\n",
        encoding="utf-8",
    )
    print(f"Created {KEYSTORE.name} and {PROPS.name}")
    print("BACK BOTH FILES UP somewhere safe (password manager / offline).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
