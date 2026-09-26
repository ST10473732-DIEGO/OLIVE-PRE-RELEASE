#include "OliveTLS.h"
#include <openssl/ssl.h>
#include <openssl/err.h>
#include <openssl/rand.h>
#include <string.h>
#include <limits.h>

struct olive_tls { SSL_CTX *ctx; SSL *ssl; X509 *peer; uint8_t pin[1536]; size_t pin_count; };

static X509 *certificate(const uint8_t *der, size_t count) {
    if (!der || !count || count > 1536) return NULL;
    const unsigned char *p = der;
    X509 *cert = d2i_X509(NULL, &p, (long)count);
    unsigned char *canonical = NULL;
    int length = cert ? i2d_X509(cert, &canonical) : -1;
    int valid = p == der + count && length == (int)count && canonical &&
                CRYPTO_memcmp(der, canonical, count) == 0;
    OPENSSL_free(canonical);
    if (!valid) { X509_free(cert); return NULL; }
    return cert;
}

int olive_certificate_create(const uint8_t seed[32], const char *id, int64_t created,
                             uint8_t *out, size_t capacity) {
    EVP_PKEY *key = EVP_PKEY_new_raw_private_key(EVP_PKEY_ED25519, NULL, seed, 32);
    X509 *cert = X509_new();
    X509_NAME *name = X509_NAME_new();
    uint8_t serial[20];
    BIGNUM *bn = NULL;
    int result = -1;
    if (!key || !cert || !name || !RAND_bytes(serial, sizeof serial)) goto done;
    serial[0] &= 0x7f; serial[0] |= 1;
    bn = BN_bin2bn(serial, sizeof serial, NULL);
    if (!bn || !BN_to_ASN1_INTEGER(bn, X509_get_serialNumber(cert)) ||
        !X509_set_version(cert, 2) ||
        !X509_NAME_add_entry_by_NID(name, NID_commonName, MBSTRING_ASC,
                                  (const unsigned char *)id, -1, -1, 0) ||
        !X509_set_subject_name(cert, name) || !X509_set_issuer_name(cert, name) ||
        !X509_set_pubkey(cert, key) ||
        !ASN1_TIME_set(X509_getm_notBefore(cert), (time_t)(created - 300)) ||
        !ASN1_TIME_set(X509_getm_notAfter(cert), (time_t)(created + 3650LL*86400)) ||
        !X509_sign(cert, key, NULL)) goto done;
    int length = i2d_X509(cert, NULL);
    if (length <= 0 || (size_t)length > capacity) goto done;
    unsigned char *p = out;
    result = i2d_X509(cert, &p);
done:
    BN_free(bn); X509_NAME_free(name); X509_free(cert); EVP_PKEY_free(key);
    ERR_clear_error();
    return result;
}

int olive_certificate_validate(const uint8_t *der, size_t count, const char *id,
                               int64_t created, uint8_t public_key[32]) {
    X509 *cert = certificate(der, count);
    EVP_PKEY *key = cert ? X509_get_pubkey(cert) : NULL;
    X509_NAME *expected = X509_NAME_new();
    ASN1_TIME *before = ASN1_TIME_set(NULL, (time_t)(created - 300));
    size_t size = 32;
    int ok = cert && key && expected && before &&
        X509_NAME_add_entry_by_NID(expected, NID_commonName, MBSTRING_ASC,
                                  (const unsigned char *)id, -1, -1, 0) &&
        X509_NAME_cmp(expected, X509_get_subject_name(cert)) == 0 &&
        X509_NAME_cmp(expected, X509_get_issuer_name(cert)) == 0 &&
        ASN1_TIME_compare(before, X509_get0_notBefore(cert)) == 0 &&
        EVP_PKEY_id(key) == EVP_PKEY_ED25519 &&
        X509_get_signature_nid(cert) == NID_ED25519 && X509_verify(cert, key) == 1 &&
        EVP_PKEY_get_raw_public_key(key, public_key, &size) && size == 32;
    ASN1_TIME_free(before); X509_NAME_free(expected); EVP_PKEY_free(key); X509_free(cert);
    ERR_clear_error();
    return ok ? 1 : 0;
}

static int verify(int valid, X509_STORE_CTX *store) {
    SSL *ssl = X509_STORE_CTX_get_ex_data(store, SSL_get_ex_data_X509_STORE_CTX_idx());
    olive_tls *tls = ssl ? SSL_get_app_data(ssl) : NULL;
    if (!valid || !tls || X509_STORE_CTX_get_error_depth(store) != 0) return 0;
    X509 *candidate = X509_STORE_CTX_get_current_cert(store);
    int count = i2d_X509(candidate, NULL);
    if (count <= 0 || (size_t)count != tls->pin_count || count > 1536) return 0;
    uint8_t encoded[1536], *p = encoded;
    return i2d_X509(candidate, &p) == count && CRYPTO_memcmp(encoded, tls->pin, tls->pin_count) == 0;
}

olive_tls *olive_tls_create(const uint8_t seed[32], const uint8_t *local, size_t lc,
                           const uint8_t *peer, size_t pc) {
    olive_tls *tls = OPENSSL_zalloc(sizeof *tls);
    X509 *cert = certificate(local, lc);
    EVP_PKEY *key = EVP_PKEY_new_raw_private_key(EVP_PKEY_ED25519, NULL, seed, 32);
    if (!tls) goto fail;
    tls->peer = certificate(peer, pc);
    if (tls->peer) { memcpy(tls->pin, peer, pc); tls->pin_count = pc; }
    tls->ctx = SSL_CTX_new(TLS_client_method());
    if (!cert || !key || !tls->peer || !tls->ctx ||
        X509_cmp_current_time(X509_get0_notBefore(cert)) >= 0 ||
        X509_cmp_current_time(X509_get0_notAfter(cert)) <= 0 ||
        !SSL_CTX_set_min_proto_version(tls->ctx, TLS1_3_VERSION) ||
        !SSL_CTX_set_max_proto_version(tls->ctx, TLS1_3_VERSION) ||
        !SSL_CTX_use_certificate(tls->ctx, cert) || !SSL_CTX_use_PrivateKey(tls->ctx, key) ||
        !SSL_CTX_check_private_key(tls->ctx) ||
        !X509_STORE_add_cert(SSL_CTX_get_cert_store(tls->ctx), tls->peer)) goto fail;
    SSL_CTX_set_session_cache_mode(tls->ctx, SSL_SESS_CACHE_OFF);
    SSL_CTX_set_options(tls->ctx, SSL_OP_NO_TICKET);
    SSL_CTX_set_verify(tls->ctx, SSL_VERIFY_PEER | SSL_VERIFY_FAIL_IF_NO_PEER_CERT, verify);
    SSL_CTX_set_verify_depth(tls->ctx, 0);
    tls->ssl = SSL_new(tls->ctx);
    if (!tls->ssl) goto fail;
    BIO *in = BIO_new(BIO_s_mem()), *out = BIO_new(BIO_s_mem());
    if (!in || !out) { BIO_free(in); BIO_free(out); goto fail; }
    BIO_set_mem_eof_return(in, -1); BIO_set_mem_eof_return(out, -1);
    SSL_set_bio(tls->ssl, in, out);
    SSL_set_app_data(tls->ssl, tls);
    SSL_set_connect_state(tls->ssl);
    X509_free(cert); EVP_PKEY_free(key);
    return tls;
fail:
    X509_free(cert); EVP_PKEY_free(key); olive_tls_free(tls); ERR_clear_error(); return NULL;
}
void olive_tls_free(olive_tls *tls) {
    if (tls) { SSL_free(tls->ssl); SSL_CTX_free(tls->ctx); X509_free(tls->peer); OPENSSL_clear_free(tls, sizeof *tls); }
}
int olive_tls_handshake(olive_tls *tls) {
    int r = SSL_do_handshake(tls->ssl);
    if (r == 1) return SSL_version(tls->ssl) == TLS1_3_VERSION ? 1 : -1;
    return SSL_get_error(tls->ssl, r) == SSL_ERROR_WANT_READ ? 0 : -1;
}
int olive_tls_feed(olive_tls *tls, const uint8_t *bytes, size_t count) {
    if (count > 32768) return -1;
    return count ? BIO_write(SSL_get_rbio(tls->ssl), bytes, (int)count) : 0;
}
int olive_tls_drain(olive_tls *tls, uint8_t *bytes, size_t capacity) {
    if (capacity > INT_MAX) return -1;
    BIO *bio = SSL_get_wbio(tls->ssl);
    return BIO_ctrl_pending(bio) ? BIO_read(bio, bytes, (int)capacity) : 0;
}
int olive_tls_read(olive_tls *tls, uint8_t *bytes, size_t capacity) {
    if (capacity > INT_MAX) return -1;
    int r = SSL_read(tls->ssl, bytes, (int)capacity);
    return r > 0 ? r : SSL_get_error(tls->ssl, r) == SSL_ERROR_WANT_READ ? 0 : -1;
}
int olive_tls_write(olive_tls *tls, const uint8_t *bytes, size_t count) {
    if (count > 72006) return -1;
    return SSL_write(tls->ssl, bytes, (int)count);
}
int olive_tls_comparison(olive_tls *tls, const uint8_t binding[32], uint8_t out[32]) {
    const char *label = "EXPORTER-OLIVE-PAIRING-v1";
    return SSL_export_keying_material(tls->ssl, out, 32, label, strlen(label), binding, 32, 1);
}
