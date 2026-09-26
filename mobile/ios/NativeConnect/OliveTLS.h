#ifndef OLIVE_TLS_H
#define OLIVE_TLS_H
#include <stdint.h>
#include <stddef.h>
// No sockets, files, global peer state, system roots, or error strings.
typedef struct olive_tls olive_tls;
int olive_certificate_create(const uint8_t seed[32], const char *device_id, int64_t created,
                             uint8_t *out, size_t capacity);
int olive_certificate_validate(const uint8_t *der, size_t count, const char *device_id,
                               int64_t created, uint8_t public_key[32]);
olive_tls *olive_tls_create(const uint8_t seed[32], const uint8_t *local, size_t local_count,
                           const uint8_t *peer, size_t peer_count);
void olive_tls_free(olive_tls *tls);
// Return 1 when complete, 0 on WANT_READ; -1 fails closed.
int olive_tls_handshake(olive_tls *tls);
int olive_tls_feed(olive_tls *tls, const uint8_t *bytes, size_t count);
int olive_tls_drain(olive_tls *tls, uint8_t *bytes, size_t capacity);
int olive_tls_read(olive_tls *tls, uint8_t *bytes, size_t capacity);
int olive_tls_write(olive_tls *tls, const uint8_t *bytes, size_t count);
int olive_tls_comparison(olive_tls *tls, const uint8_t binding[32], uint8_t out[32]);
#endif
