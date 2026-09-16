// mesh_crypto.h — AES-CTR payload encryption + device keypair for ALMA-MESH,
// the v0.2 roadmap item noted in ARCHITECTURE.md §7 ("⬜ AES-CTR payload
// encryption") and design/04-firmware-os.md §5 (keys/device.key).
//
// Purity note: AES itself is a public NIST standard, not "someone else's
// product" — a from-scratch constant-time AES-128 implementation (small,
// auditable, ~200 lines) keeps us off external crypto libs (no mbedTLS
// dependency beyond what the Arduino core already links for TLS-less builds).
// CTR mode reuses the mesh frame's existing msgid (mesh.h) as part of the
// nonce, avoiding a separate nonce field in the wire format.
//
// STUB: interface only, no implementation yet. mesh.h's frame format gains
// one new `type` value (ALMA_MSG_ENCRYPTED) when this lands; unencrypted
// ALMA_MSG stays supported for back-compat / debug builds.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once
#include <Arduino.h>

#define ALMA_KEY_BYTES 16   // AES-128

struct AlmaDeviceKey {
  uint8_t key[ALMA_KEY_BYTES];
  bool    valid;
};

// Loads SD:/alma/keys/device.key, generating one via HW RNG (esp_random())
// on first boot if absent. Never transmitted; used to derive per-peer
// session keys in a future key-exchange step (not yet designed — v0.2 ships
// a single shared network key as the honest first cut, matching the
// existing private-syncword model in board_tdeck.h).
AlmaDeviceKey almaMeshLoadOrCreateKey();

// Encrypt/decrypt a mesh payload in place. `nonce` should be derived from
// (src node id, msgid) already present in every mesh.h frame header — see
// design doc §5. Returns false on any length/key error.
bool almaMeshEncrypt(uint8_t *payload, size_t len, const AlmaDeviceKey &key, uint64_t nonce);
bool almaMeshDecrypt(uint8_t *payload, size_t len, const AlmaDeviceKey &key, uint64_t nonce);
