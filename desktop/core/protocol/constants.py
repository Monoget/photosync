"""Shared protocol constants (spec §22)."""

PROTOCOL_VERSION = 1

# mDNS service types. The PC advertises the desktop type (it will host the
# transfer receiver); the phone advertises the mobile type so the PC can
# show devices on the network before pairing.
SERVICE_TYPE_DESKTOP = "_photosync._tcp.local."
# RFC 6763 limits service names to 15 bytes, so "photosync-mobile" is out.
SERVICE_TYPE_MOBILE = "_photosync-m._tcp.local."
