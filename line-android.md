LINE instant messenger protocol - Android version
=================================================

Matti Virkkunen <mvirkkunen@gmail.com>

Document is accurate as of 2015-04-02 (LINE 5.0.4)

This document describes the custom protocols used by the Android version of LINE. It's meant to be a
companion to line-protocol.md, as it mostly describes the differences.

Overview
--------

The Android version of LINE also uses Apache Thrift as the serialization format for most of its
communications. There are however significant differences. This makes the total protocol suite more
complicated, but it saves a lot of bandwidth, which is presumably their main goal. The mobile
versions of LINE have vastly more users than the desktop versions, so it makes sense to primarily
optimize them.

SPDY instead of HTTP
--------------------

The Android client primarily uses SPDY (Draft 2) instead of HTTP. This has numerous advantages, for
instance the ability to use one TCP stream for multiple transactions and header compression.

Custom SPDY encryption
----------------------

SPDY is normally encrypted using standard SSL, but LINE implements its own custom encryption. Their
justification for it is that it does away with SSL handshakes and overhead and therefore puts less
of a burder on mobile devices and networks.

The encryption scheme encrypts the body part of the SPDY request only. The standard headers portion
of SPDY is left unencrypted, but the body can also optionally contain encrypted headers.

When the client connects to the server, it generates a 128 bit random key, encrypts it with an RSA
public key, and sends it to the server as a header with the first request. This key is used by both
the client and the server to encrypt the body with AES in CBC mode with a fixed IV. The AES context
is reset for each message. Cryptanalysts may have something to say about the fixed IV and new
context for each message.

The AES encrypted messages are signed with a custom 32-bit HMAC called legy_hmac, which is curiously
only available in native code. I haven't yet analyzed how it works. I am not sure if the native
library approach is taken to enable code re-use between platforms, or as some futile attempt to add
security by obscurity. It seems to be built on this hash algorithm:

https://github.com/Cyan4973/xxHash

Interestingly they seem to have forgotten to include the copyright notice for xxHash in their app.

(TODO)

(TODO attach: RSA key and AES IV)

(TODO add example code: custom encryption)

(TODO add example code: legy_hmac implementation)

Authentication
--------------

The mobile version of LINE does not require the user to manually register an account - one is
automatically generated when the app is first installed. Therefore the user authentication method is
also different.

The Android client stores a 15 byte auth key which is used to authenticate it to the LINE servers.
The key is stored in an encrypted settings database, but obviously since the app needs to be able to
read it, this is easy to circumvent (it turns out they essentially use an 8-bit encryption key,
which is generated from the phone's ANDROID_ID value). The auth key is likely generated when the app
is first installed and it does not seem to ever change.

You can use the tools/view-android-settings.py script to view the auth key for your account. It
needs the LINE settings SQLite database and optionally the ANDROID_ID (it can also bruteforce it
which takes about a millisecond on a modern computer). The database on my phone is located at:

/data/data/jp.naver.line.android/databases/naver_line

The displayed user MID and auth key are used to generate an authentication token whenever the client
connects to the server.

(TODO)

(TODO add example code: mobile authentication token generation)

Custom Thrift protocol
----------------------

The custom protocol, among other things, stores GUIDs (which are used as user IDs throughout the
system) as binary instead of strings, halving their size.

(TODO)

Compact message protocol
------------------------

There is a custom, presumably non-Thrift binary protocol for sending messages.

(TODO)
