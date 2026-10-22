#!/usr/bin/env python3
"""Make the values for the cluster-dashboard-auth Secret, on your own Mac.

Prompts for the password (not echoed), then prints:
  admin-password-hash  bcrypt hash (safe to store; the password itself is never printed)
  session-secret       random 32-byte hex key
  totp-secret          base32 authenticator secret, plus an otpauth:// URI and a terminal QR

Needs:  python3 -m pip install bcrypt pyotp qrcode
Run:    python3 scripts/make_auth_secret.py [--user james] [--no-qr] [--verify]

Everything printed goes straight into the SOPS-encrypted Secret; don't paste it into chat.
"""
import argparse
import getpass
import secrets
import sys

import bcrypt
import pyotp


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="james")
    ap.add_argument("--issuer", default="Homelab dashboard")
    ap.add_argument("--no-qr", action="store_true")
    ap.add_argument("--verify", action="store_true", help="ask for a code from your app to confirm the setup")
    args = ap.parse_args()

    if sys.stdin.isatty():
        pw = getpass.getpass("New dashboard password: ")
        if pw != getpass.getpass("Repeat it: "):
            print("Passwords don't match.", file=sys.stderr)
            return 1
    else:  # piped input, for testing
        pw = sys.stdin.readline().rstrip("\n")
    if len(pw) < 12:
        print("Use at least 12 characters.", file=sys.stderr)
        return 1

    pw_hash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt(rounds=12)).decode()
    assert bcrypt.checkpw(pw.encode(), pw_hash.encode())
    totp_secret = pyotp.random_base32()
    uri = pyotp.TOTP(totp_secret).provisioning_uri(name=args.user, issuer_name=args.issuer)

    print(f"admin-username:      {args.user}")
    print(f"admin-password-hash: {pw_hash}")
    print(f"session-secret:      {secrets.token_hex(32)}")
    print(f"totp-secret:         {totp_secret}")
    print(f"otpauth URI:         {uri}")
    if not args.no_qr:
        try:
            import qrcode
            qr = qrcode.QRCode(border=1)
            qr.add_data(uri)
            qr.print_ascii(invert=True)
            print("Scan this with your authenticator app.")
        except ImportError:
            print("(install 'qrcode' to show a QR here, or add the totp-secret manually)")
    if args.verify:
        code = input("Code from your app: ").strip()
        print("Code OK." if pyotp.TOTP(totp_secret).verify(code, valid_window=1) else "Code did NOT match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
