LINE instant messenger protocol
===============================

Matti Virkkunen <mvirkkunen@gmail.com>

Document is accurate as of 2015-04-20.

This unofficial document describes the LINE (by LINE Corporation/Naver) instant messenger protocol.
The information is based mostly on reverse engineering and therefore accuracy is not guaranteed.

Also, this document is unfinished. I'm expanding it as I go.

Overview
--------

LINE as a whole consists of a number of web services because of their multitude of apps and
subsystems, but the only service that's needed for replicating their desktop IM client's
functionality is the TalkService.

The protocol is based on a request-response architecture over HTTP(S), with a long poll return
channel. Apache Thrift is used for serialization of message data.

Wire protocol
-------------

File: line.thrift (a presumably complete Thrift interface file obtained via reverse engineering)

The protocol is Apache Thrift TCompactProtocol via HTTPS to gd2.line.naver.jp:443. The HTTP request
path is /S4 for most requests. Some specific requests use a different path, specified where
relevant.

Unencrypted HTTP also seems to work for the moment, but using it is a really bad idea security-wise.
Naver itself seems to be currently transitioning to 100% HTTPS.

If using a keep-alive connection, headers from the first request can be persisted. Headers in
following requests can temporarily override the persisted value. An HTTP header called X-LS is also
involved. If you want to persist headers, you must remember the X-LS header value the server gives
you and send it back in the next request. The values seem to be integers. The name could be short
for "Line Server", and it's probably used so that load-balancers can direct the following responses
back to the same server that knows the headers.

By using persistent headers it's possible to send each request with just two headers - X-LS and
Content-Length.

The official protocol seems to be to first make one request to get an authentication key, and then
open a new connection so that the authentication key can be persisted along with the rest of the
headers for the following requests.

Types and concepts
------------------

Friends, chats and groups are identified by 32-digit hex GUIDs prefixed with one character for the
type.

Internally any user is referred to as a Contact. Contacts are identified by a "mid" and the prefix
is "u" (presumably for "user")

Chats are called Rooms and are identified by a "mid" which is prefixed by "r" (for "room"). Rooms
are the lightweight multi-user chats that are created when you invite an extra user to a plain IM
conversation with a contact. Groups are called Groups internally as well and are identified by an
"id" which is prefixed with a "c" (presumably for "chat"). Groups are more permanent than chats and
have extra data associated with them such as a name and an icon.

Any message is represented by a Message object. Message IDs are numeric but they are stored as
strings.

Timestamps are millisecond precision UNIX time represented as 64-bit integers (TODO: check the
timezone just in case)

Message authentication
----------------------

The following HTTP headers are required for a successful request:

    X-Line-Application: DESKTOPWIN\t3.2.1.83\tWINDOWS\t5.1.2600-XP-x64
    X-Line-Access: authToken

The \t escape sequence represents a tab character. Other X-Line-Application names exist, but this is
one that works currently. An invalid application name results in an error.  The authToken is
obtained via the login procedure.

Object storage server
---------------------

Media files are stored on a separate server at http://os.line.naver.jp/ which is internally referred
to as the "object storage server". Some files (such as message attachments) seem to require
authentication with the same protocol as above, but some files (such as buddy icons) don't seem to
require authentication.

It serves files over both HTTP and HTTPS with the same authentication protocol as above.

Login procedure
---------------

This Thrift method issues a new authToken for an e-mail address and password combination. The
request should be sent to the path /api/v4/TalkService.do to avoid having to specify an auth token
when none exists yet (/S4 always requires an auth token).

    loginWithIdentityCredentialForCertificate(
        IdentityProvider.LINE, // identityProvider
        "test@example.com", // identifier (e-mail address)
        "password", // password (in plain text)
        true, // keepLoggedIn
        "127.0.0.1", // accesslocation (presumably local IP?)
        "hostname", // systemName (will show up in "Devices")
        "") // certificate (empty on first login - see login verification procedure below)

The result structure is as follows:

    struct LoginResult {
        1: string authToken;
        2: string certificate;
        3: string verifier;
        4: string pinCode;
        5: LoginResultType type;
    }

After a successful login, the type is equal to SUCCESS (1) and the authToken field contains the
X-Line-Access value to use in subsequent requests.

The official desktop client sends an encrypted e-mail/password involving RSA and no X-Line-Access
header, but it works just as fine in plain text. (TODO: Include description of RSA login procedure)

Login verification procedure
----------------------------

In current versions, LINE now requires you to verify your identity using a PIN code when logging in
to a desktop client for the first time. It seems this is partially based on geo-IP, as clients that
had logged in before the verification procedure was added do not need to verify themselves. New
logins will all likely need to be verified.

When PIN verification is required, the login method returns a type of REQUIRE_DEVICE_CONFIRM (3)
instead of SUCCESS (1). The pinCode field contains a PIN code to display to the user and the
verifier field is set to a random token that is used to identify this verification session. The
token stays the same for the whole process.

The client then issues an empty request to the HTTP path /Q with the X-Line-Access header set to the
verifier token. This request blocks until the user enters the correct PIN code on their mobile
device.

There doesn't seem to be a limit for incorrect PIN entries on the mobile device, but there is
currently a three minute time limit. After this the token expires. The client keeps track of the
time limit locally and aborts the request when it's over.

A success response from /Q is JSON containing the following:

    {
        "timestamp": "946684800000",
        "result": {
            "verifier": "the_verifier_token",
            "authPhase": "QRCODE_VERIFIED"
        }
    }

After this response is received the client issues a loginWithVerifierForCertificate() call with the
verifier token as the parameter. The server then returns a normal LoginReply message with the usual
authToken. The LoginReply message also contains a certificate value (random hex string) which should
be stored and used in future calls to loginWithIdentityCredentialForCertificate() to skip the
validation step. If the certificate is not used, every login will prompt for PIN verification.

If the token has already expired the response from /Q looks like the following:

    {
        "timestamp": "946684800000",
        "errorCode": "404",
        "errorMessage": "key+is+not+found%3A+the_verifier_token+NOT_FOUND"
    }

Initial sync
------------

After logging in the client sends out a sequence of requests to synchronize with the server. It
seems some messages are not always sent - the client could be storing data locally somewhere and
comparing with the revision ID from getLastOpRevision(). The client runs multiple sync sequences in
parallel in order to make it faster.

There is no requirement to implement all or any of these sync operations in a third-party client.

### Sequence 1

This seems to be the main sync sequence.

    getLastOpRevision()

Gets the revision ID to use for the long poll return channel later. It's fetched first to ensure
nothing is missed even if something happens during the sync procedure.

    getDownloads()

Mystery. Probably not related to software updates as that is a separate call. Could be related to
sticker downloads.

    getProfile()

Gets the currently logged in user's profile, which includes their display name and status message
and so forth.

    getSettingsAttributes(8458272)

Gets some of the stored settings (the bits are NOTIFICATION_INCOMING_CALL, IDENTITY_IDENTIFIER,
NOTIFICATION_DISABLED_WITH_SUB and PRIVACY_PROFILE_IMAGE_POST_TO_MYHOME)

    getAllContactIds()

Gets all contact IDs added as friends.

    getBlockedContactIds()

List of blocked user IDs.

    fetchNotificationItems()

Mystery.

    getContacts(contactIds) - with IDs from the previous methods that fetched contact IDs

Gets details for the users.

    getGroupIdsJoined()

Gets all groups current user is a member of.

    getGroupIdsInvited()

Gets all groups for which the user has a pending invitation.

    getGroups(groupIds) - with IDs from the previous methods

Gets details for the groups. This included member lists.

    getMessageBoxCompactWrapUpList(1, 50)

Returns a complicated structure with "current active chats". This returns a list of of rooms and
groups with partial information as well as the latest message(s) for them. This call seems to be the
only way to get a list of rooms the current user is a member of as there is no separate getRooms
method.

### Sequence 2

    getActivePurchaseVersions(0, 1000, "en", "US")

Mystery. Probably related to sticker versions.

    getConfigurations(...) - parameters involve country codes

Returns a map of configuration settings with string keys. I do not have exact metadata for this
function. Example:

    {
      "function.linecall.mobile_network_expire_period": "604800",
      "function.linecall.store": "N",
      "contact_ui.show_addressbook": "N",
      "function.music": "N",
      "group.max_size": "200",
      "function.linecall.validate_caller_id": "N",
      "function.linecall.spot": "N",
      "main_tab.show_timeline": "N",
      "function.linecall": "N",
      "room.max_size": "100"
    }

Many of the settings seem to be related to features being enabled or disabled and maximum limits for
them.

    getRecommendationIds()

List of suggested friend IDs.

    getBlockedRecommendationIds()

List of suggested friend IDs that have been dismissed (why can't the previous method just not return
these...?)

    getContacts(contactIds) - with IDs from the previous methods

Managing the contact list
-------------------------

Contacts have multiple statuses.

FRIEND = appears on friend list, unless hidden.

RECOMMEND = appears on "recommended contacts" list.

DELETE = used in notifications only AFAIK, to notify that a friend has been completely deleted.

Each state also has a _BLOCKED version where the current user will not receive messages from the
user. Friends also have a "hidden" status, that is set via the CONTACT_SETTING_CONTACT_HIDE setting
flag. Blocking is done via blockContact/unblockContact.

There is no separate function to delete a contact for some reason, instead it's done by setting the
CONTACT_SETTING_DELETE setting. Even though it's a setting, this is equivalent to really deleting
the friend - they won't appear on getallContactIds() anymore. (FIXME: actually test this...)

Sending messages
----------------

Messages are sent using the sendMessage() function.

    sendMessage(seq, msg)

The seq parameter doesn't seem to be matter, and can be sent as zero. The msg parameter is the
Message object to send.

The only required fields for a text message are "to", which can be the ID for any valid message
recipient (user, chat or group), and the "text" field which is the text content to send. Other
message types involve the contentMetadata fields and possibly uploading files to a separate server.

The return value from sendMessage is a partial Message object that only contains the fields "id",
"createdTime" and "from". The ID is a numeric string that can be used to refer to that message
later.

Message types
-------------

LINE supports various types of messages from simple text messages to pictures and video. Each
message has a contentType field that specifies the type of content, and some messages include
attached files from various locations.

Messages can contain extra attributes in the contentMetadata map. One globally used attribute is
"BOT_CHECK" which is included with a value of "1" for automatic messages I've received from
"official accounts" - this could be an auto-reply indicator.

### NONE (0)

The first contentType is called NONE internally but is actually text. It's the simplest content
type. The text field contains the message content encoded in UTF-8.

The only thing to watch out for is emoji which are sent as Unicode private use area codepoints.

Example:

    client.sendMessage(0, line.Message(
        to="u0123456789abcdef0123456789abcdef",
        contentType=line.ContentType.NONE,
        text="Hello, world!"))

TODO: make a list of emoji

### IMAGE (1)

#### Receiving

Image message content can be delivered in one of two ways.

For normal image messages, a preview image is included as a plain JPEG in the contentPreview field.
However, for some reason the official desktop client seems to ignore it and rather downloads
everything from the object storage server.

The preview image URLs are http://os.line.naver.jp/os/m/MSGID/preview and the full-size image URL
are http://os.line.naver.jp/os/m/MSGID where MSGID is the message's id field.

"Official accounts" broadcast messages to many clients at once, so their image message data is
stored on publicly accessible servers (currently seems to be Akamai CDN). For those messages no
embedded preview is included and the image URLs are stored in the contentMetadata map with the
following keys:

* PREVIEW_URL = absolute URL for preview image
* DOWNLOAD_URL = absolute URL for full-size image
* PUBLIC = "TRUE" (haven't seen other values)

As an example of a publicly available image message, have a Pikachu:

http://dl-obs.official.line.naver.jp/r/talk/o/u3ae3691f73c7a396fb6e5243a8718915-1379585871

#### Sending

Sending an image message is done in two steps. First a Thrift sendMessage call is used to obtain a
message ID, and then the image data is uploaded to the Object Storage Server with a separate HTTP
upload request.

The message will not be delivered to the recipient until the HTTP upload is complete. The official
client displays messages in the order of the sendMessage calls, even if the image data is uploaded
much later. It might be possible to have fun by "reserving" a spot for an image message in a
conversation and then filling it in later. It's unknown if there's an internal timeout for uploading
the image data.

In order to send an image message, first send a message normally with contentType=1 (IMAGE) and make
note of the returned message ID. The official client also puts "1000000000" in the text field. The
meaning of this is unknown and it's not required.

The upload HTTP request is a multipart/form-data ("file upload") POST request to the URL:

https://os.line.naver.jp/talk/m/upload.nhn

The request uses the usual X-Line-Application and the X-Line-Access headers for authentication.
There are two fields in the multipart request. The first field is called "params" and the content is
a JSON object containing among other things the message ID. There is on Content-Type header.

{"name":"1.jpg","oid":"1234567890123","size":28878,"type":"image","ver":"1.0"}

The name field does not seem to be used for anything. oid should be set to the message ID obtained
earlier. size should be set to the size of the image file to upload.

The second field is called "file" with a filename argument, has a Content-Type header, and contains
the image data itself. The filename and Content-Type headers seem to be ignored and the image format
is automatically detected. At least JPEG and PNG data is supported for uploading, but everything is
converted to JPEG by the server.

Example sendMessage call:

    # First send the message by using sendMessage
    result = client.sendMessage(0, line.Message(
        to="u0123456789abcdef0123456789abcdef",
        contentType=line.ContentType.IMAGE))

    # Store the ID
    oid = result.id

Example HTTP upload:

    POST /talk/m/upload.nhn HTTP/1.1
    Content-Length: 29223
    Content-Type: multipart/form-data; boundary=separator-CU3U3JIM7B17R0C4SIWX1NS7I1G0LV6BF76GPTNN
    Host: obs-de.line-apps.com:443
    X-Line-Access: D82j....=
    X-Line-Application: DESKTOPWIN\t3.6.0.32\tWINDOWS 5.0.2195-XP-x64

    --separator-CU3U3JIM7B17R0C4SIWX1NS7I1G0LV6BF76GPTNN
    Content-Disposition: form-data; name="params"

    {"name":"1.jpg","oid":"1234567890123","size":28878,"type":"image","ver":"1.0"}
    --separator-CU3U3JIM7B17R0C4SIWX1NS7I1G0LV6BF76GPTNN
    Content-Disposition: form-data; name="file"; filename="1.jpg"
    Content-Type: image/jpeg

    ...image data...
    --separator-CU3U3JIM7B17R0C4SIWX1NS7I1G0LV6BF76GPTNN--

### STICKER (7)

Sticker messages are simply a reference to a separately hosted image file. The information required
to reference a sticker is contained in the contentMetadata map.

A sticker reference consists of three numbers, the STKVER (sticker version), STKPKGID (sticker
package ID) and STKID (sticker ID within package). To send a sticker, a message with contentType=7
and these three values specified are enough. When receiving a sticker some stickers also return a
meaningful textual name for the sticker in the STKTXT metadata field - this is added automatically
and does not need to be specified when sending.

Sticker image files are hosted on yet another CDN server at dl.stickershop.line.naver.jp. The CDN
server does not require authentication and can be viewed with a plain browser for testing. The base
URL for a sticker package is formed from the STKVER and STKPKGID values. First, the version is split
into three numbers as follows:

    VER = floor(STKVER / 1000000) + "/" + floor(STKVER / 1000) + "/" + (STKVER % 1000)

Using this the package base URL can be determined:

http://dl.stickershop.line.naver.jp/products/{VER}/{STKPKGID}/{PLATFORM}/

PLATFORM is a platform identifier which is presumably used to deliver different image sizes etc to
different platforms. The "WindowsPhone" platform seems to have most interesting files. Other known
platforms are "PC". Not all platforms contain all file types.

Sticker package version 100, package 1 ("Moon & James") is used as an example in the following URLs.
Substitute another package base URL to see other packages.

The sticker package contains a metadata file for a listing its contents:

http://dl.stickershop.line.naver.jp/products/0/0/100/1/WindowsPhone/productInfo.meta

This is a JSON file with metadata about the stickers in this package including names in multiple
languages, the price in multiple currencies and a list of stickers.

Each package also has an icon:

http://dl.stickershop.line.naver.jp/products/0/0/100/1/WindowsPhone/tab_on.png - active

http://dl.stickershop.line.naver.jp/products/0/0/100/1/WindowsPhone/tab_off.png - dimmed

Each referenced sticker image is available in the subdirectory "stickers" as a PNG image. The
filename is {STKID}.png for the full image and {STKID}_key.png for a thumbnail.

http://dl.stickershop.line.naver.jp/products/0/0/100/1/WindowsPhone/stickers/13.png - full size

http://dl.stickershop.line.naver.jp/products/0/0/100/1/WindowsPhone/stickers/13_key.png - thumbnail

All sticker images as well as the icons can be downloaded as a single package from:

http://dl.stickershop.line.naver.jp/products/0/0/100/1/WindowsPhone/stickers.zip

The ShopService is used with the path /SHOP4 to get a list of sticker packages the current user has.
TODO: specify more

Interestingly the official client sends some emoji as a sticker message instead of a plain text
message if the message content consists only of the single emoji. Emoji as stickers are in package
number 5: (TODO: figure out how they're mapped)

http://dl.stickershop.line.naver.jp/products/0/0/100/5/WindowsPhone/productInfo.meta

The official clients also contain references to "old" stickers that have no STKVER or STKPKGID and
use a URL of the format:

http://line.naver.jp/stickers/android/{STKID}.png

http://line.naver.jp/stickers/android/13.png

These seem to just be redirects to new URLs now.

Return channel
--------------

    fetchOperations(localRev, count)

For incoming events, fetchOperations() calls to the HTTP path /P4 is used. Using the /P4 path
enables long polling, where the responses block until something happens or a timeout expires. An
HTTP 410 Gone response signals a timed out poll, in which case a new request should be issued.

When new data arrives, a list of Operation objects is returned. Each Operation (except the end
marker) comes with a version number, and the next localRev should be the highest revision number
received.

The official client uses a count parameter of 50.

Operation data is contained either as a Message object in the message field, or in the string fields
param1-param3.

In general NOTIFIED_* messages notify the current user about other users' actions, while their
non-NOTIFIED counterparts notify the current user about their own actions, in order to sync them
across devices.

For many operations the official client doesn't seem to care about the fact that the param1-param3
fields contain the details of the operation and will rather re-fetch data with a get method instead.
For instance, many group member list changes will cause the client to do a getGroup(). This may be
either just lazy coding or a sign of the param parameters being phased out.

The following is a list of operation types.

### END_OF_OPERATION (0)

Signifies the end of the list. This presumably means all operations were returned and none were left
out due to the count param. This message contains no data, not even a revision number, so don't
accidentally set your localRev to zero.

### UPDATE_PROFILE (1)

The current user updated their profile. Refresh using getProfile().

* param1 = UpdateProfileAttributeAttr, which property was changed (possibly bitfield)

### NOTIFIED_UPDATE_PROFILE (2)

Another user updated their profile. Refresh using getContact[s]().

* param1 = the user ID
* param2 = UpdateProfileAttributeAttr, which property was changed (possibly bitfield)

### REGISTER_USERID (3)

(Mystery)

### ADD_CONTACT (4)

The current user has added a contact as a friend.

* param1 = ID of the user that was added
* param2 = (mystery - seen "0")

### NOTIFIED_ADD_CONTACT (5)

Another user has added the current user as a friend.

* param1 = ID of the user that added the current user

### BLOCK_CONTACT (6)

The current user has blocked a contact.

* param1 = ID of the user that was blocked
* param2 = (mystery, seen "NORMAL")

### UNBLOCK_CONTACT (7)

The current user has unblocked a contact.

* param1 = ID of the user that was unblocked
* param2 = (mystery, seen "NORMAL")

### CREATE_GROUP (9)

The current user has created a group. The official client immediately fetches group details with
getGroup().

* param1 = ID of the group.

### UPDATE_GROUP (10)

The current user has updated a group.

* param1 = ID of the group
* param2 = (Maybe a bitfield of properties? 1 = name, 2 = picture)

### NOTIFIED_UPDATE_GROUP (11)

Another user has updated group the current user is a member of.

* param1 = ID of the group
* param2 = ID of the user who updated the group
* param3 = (Maybe a bitfield of properties?)

###  INVITE_INTO_GROUP (12)

The current user has invited somebody to join a group.

* param1 = ID of the group
* param2 = ID of the user that has been invited

### NOTIFIED_INVITE_INTO_GROUP (13)

The current user has been invited to join a group.

* param1 = ID of the group
* param2 = ID of the user who invited the current user
* param3 = ID of the current user

### LEAVE_GROUP (14)

The current user has left a group.

* param1 = ID of the group

### NOTIFIED_LEAVE_GROUP (15)

Another user has left a group the current user is a member of.

* param1 = ID of the group
* param2 = ID of the user that left the group

### ACCEPT_GROUP_INVITATION (16)

The current user has accepted a group invitation.

* param1 = ID of the group

### NOTIFIED_ACCEPT_GROUP_INVITATION (17)

Another user has joined a group the current user is a member of.

* param1 = ID of the group
* param2 = ID of the user that joined the group

### KICKOUT_FROM_GROUP (18)

The current user has removed somebody from a group.

* param1 = ID of the group
* param2 = ID of the user that was removed

### NOTIFIED_KICKOUT_FROM_GROUP (19)

Another user has removed a user from a group. The removed user can also be the current user.

* param1 = ID of the group
* param2 = ID of the user that removed the current user
* param3 = ID of the user that was removed

### CREATE_ROOM (20)

The current user has created a room.

* param1 = ID of the room

### INVITE_INTO_ROOM (21)

The current user has invited users into a room.

* param1 = ID of the room
* param2 = IDs of the users, multiple IDs are separated by U+001E INFORMATION SEPARATOR TWO

### NOTIFIED_INVITE_INTO_ROOM (22)

The current user has been invited into a room. Invitations to rooms to others are not actually sent
until a message is sent to the room.

* param1 = ID of the room
* param2 = ID of the user that invited the current user
* param3 = IDs of the users in the room, multiple IDs are separated by U+001E INFORMATION SEPARATOR
           TWO. The user ID in param2 is not included in this list.

### LEAVE_ROOM (23)

The current user has left a room. Seems to be immediately followed by SEND_CHAT_REMOVED (41).

* param1 = ID of the room

### NOTIFIED_LEAVE_ROOM (24)

Another user has left a room.

* param1 = ID of the room
* param2 = ID of the user that left

### SEND_MESSAGE (25)

Informs about a message that the current user sent. This is returned to all connected devices,
including the one that sent the message.

* message = sent message

### RECEIVE_MESSAGE (26)

Informs about a received message that another user sent either to the current user or to a chat. The
message field contains the message.

The desktop client doesn't seem to care about the included message data, but instead immediately
re-requests it using getNextMessages().

* message = received message

### RECEIVE_MESSAGE_RECEIPT (28)

Informs that another user has read (seen) messages sent by the current user.

* param1 = ID of the user that read the message
* param2 = IDs of the messages, multiple IDs are separated by U+001E INFORMATION SEPARATOR TWO

### CANCEL_INVITATION_GROUP (31)

The current user has canceled a group invitation.

* param1 = ID of the group
* param2 = ID of the user whose invitation was canceled

### NOTIFIED_CANCEL_INVITATION_GROUP (32)

Another user has canceled a group invitation. The canceled invitation can also be that of the
current user.

* param1 = ID of the group
* param2 = ID of the user that canceled the request (or invited them in the first place?)
* param3 = ID of the user whose invitation was canceled

### REJECT_GROUP_INVITATION (34)

The current user has rejected a group infication.

* param1 = ID of the group

### NOTIFIED_REJECT_GROUP_INVITATION (35)

Presumably means another user has rejected a group invitation. However this message doesn't seem to
get sent.

### UPDATE_SETTINGS (36)

User settings have changed. Refresh with getSettingsAttributes() or getSettings()

* param1 = probably bitfield of changed properties
* param2 = probably new value of property (seem things like "bF"/"bT" for a boolean attribute)

### SEND_CHAT_CHECKED (40)

### SEND_CHAT_REMOVED (41)

The current user has cleared the history of a chat.

* param1 = user ID or group ID or room ID
* param2 = seen "990915482402" - maybe an ID, it's similar to IDs

### UPDATE_CONTACT (49)

The current user's settings (e.g. hidden status) for a contact has changed. Refresh with
getContact[s]().

* param1 = ID of the user that changed
* param2 = probably bitfield of changed properties

### (Mystery) 60

Meaning unknown. Has appeared after NOTIFIED_ACCEPT_GROUP_INVITATION and NOTIFIED_INVITE_INTO_ROOM.

Seen the following parameters:

* param1 = a group ID
* param2 = another user's ID

### (Mystery) 61

Meaning unknown. Has appeared after NOTIFIED_LEAVE_GROUP, KICKOUT_FROM_GROUP and
NOTIFIED_KICKOUT_FROM_GROUP and NOTIFIED_LEAVE_ROOM.

Seen the following parameters:

* param1 = a group ID
* param2 = another user's ID
* param3 = "0"
