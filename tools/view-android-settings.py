#!/usr/bin/env python3

# Requires: PyCrypto

import sys
import base64
import re
import sqlite3
from Crypto.Cipher import AES

def get_setting(path, name):
    """Gets a setting value from the settings database."""

    db = sqlite3.connect(path)

    r = db.execute("SELECT value FROM setting WHERE key = ?", (name,)).fetchone()

    return r[0] if r else None

def crazy_operation(key, constant):
    """Derives an AES key from two values using an unknown algorithm."""

    def byte(n):
        return n & 0xff

    arr = [0] * 16
    arr[0] = byte(key)
    arr[1] = byte(key - 71)
    arr[2] = byte(key - 142)

    for i in range(3, 16):
        arr[i] = byte(i ^ (0xffffffb9 ^ (arr[i - 3] ^ arr[i - 2])))

    if constant < 2 and constant > -2:
        constant = 0xfffffffffffb389d + 0xd2dfaf * constant;

    i = 0
    k = -7

    larr = len(arr)
    for _ in range(0, larr):
        k1 = (i + 1) & (larr - 1)
        l1 = constant * arr[k1] + k
        k = byte(l1 >> 32)
        i2 = l1 + k

        if i2 < k:
            i2 += 1
            k += 1

        arr[k1] = byte(-2 - i2)
        i = k1

    return bytes(arr)

def decrypt_setting(value, key):
    """Decrypts an encrypted setting using the supplied 8-bit integer key."""

    ciphertext = base64.b64decode(value)

    # generate AES key from 8-bit key
    aes_key = crazy_operation(key, 0xec4ba7)

    # decrypt setting with AES
    aes = AES.new(aes_key, AES.MODE_ECB)
    plaintext = aes.decrypt(ciphertext)

    if len(plaintext) == 0:
        return plaintext

    # remove PKCS#7 padding
    plaintext = plaintext[0:-plaintext[-1]]

    return plaintext

def java_string_hash(string):
    """Equivalent of java.lang.String.hashCode()."""

    r = 0
    for c in string:
        r = (31 * r + ord(c)) & 0xffffffff

    return r

def is_profile_auth_key(value):
    """Checks if a value looks like a PROFILE_AUTH_KEY."""

    return re.match(b"^u[a-z0-9]{32}:[a-zA-Z0-9+/]+$", value) != None

def bruteforce_key(auth_key_value):
    """Brute forces the key for a PROFILE_AUTH_KEY."""

    for key in range(0x00, 0xff):
        plaintext = decrypt_setting(auth_key_value, key)

        if is_profile_auth_key(plaintext):
            return key

    raise Exception("Couldn't brute force key.")

def get_encrypted_setting(path, key, name):
    """Shorthand for getting the value of an encrypted settings."""

    value = get_setting(path, name)
    if value is None:
        return None

    return decrypt_setting(value, key).decode("utf-8")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        print("USAGE: {0} SQLITE_DB [ANDROID_ID]".format(sys.argv[0]))
        print()
        sys.exit(1)

    path = sys.argv[1]

    auth_key_value = get_setting(path, "PROFILE_AUTH_KEY")

    if len(sys.argv) == 2:
        print("No ANDROID_ID given, bruteforcing.")
        key = bruteforce_key(auth_key_value)
    else:
        key = java_string_hash(sys.argv[2])

    auth_key_plaintext = decrypt_setting(auth_key_value, key)
    if not is_profile_auth_key(auth_key_plaintext):
        print("Key seems to be wrong.")
        sys.exit(2)

    mid, auth_key = get_encrypted_setting(path, key, "PROFILE_AUTH_KEY").split(":")

    print("User MID: " + mid)
    print("Auth key: " + auth_key)
    print("Name:     " + get_encrypted_setting(path, key, "PROFILE_NAME"))
    print("LINE ID:  " + get_encrypted_setting(path, key, "PROFILE_ID"))
    print("Region:   " + get_encrypted_setting(path, key, "PROFILE_REGION"))
    print("Phone:    " + get_encrypted_setting(path, key, "PROFILE_NORMALIZED_PHONE"))
