import Foundation
import Security

protocol SecretStore: Sendable {
    func read(account: String) async throws -> Data?
    func write(_ data: Data, account: String) async throws
    func remove(account: String) async throws
}

/// Connect identity storage: device-only, unlocked access; no iCloud or shared access group.
actor KeychainSecretStore: SecretStore {
    struct Failure: Error { let status: OSStatus }
    private let service: String
    init(service: String = "io.github.st10473732-diego.olive.mobile.connect") { self.service = service }
    private func query(_ account: String) -> [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: service, kSecAttrAccount as String: account,
         kSecAttrSynchronizable as String: false]
    }
    func read(account: String) throws -> Data? {
        var request = query(account)
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw Failure(status: status) }
        guard let data = result as? Data else { throw Failure(status: errSecDecode) }
        return data
    }
    func write(_ data: Data, account: String) throws {
        var request = query(account)
        request[kSecValueData as String] = data
        request[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        let status = SecItemAdd(request as CFDictionary, nil)
        if status == errSecDuplicateItem {
            let update = [kSecValueData as String: data,
                          kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly] as [String: Any]
            let updated = SecItemUpdate(query(account) as CFDictionary, update as CFDictionary)
            guard updated == errSecSuccess else { throw Failure(status: updated) }
        } else if status != errSecSuccess { throw Failure(status: status) }
    }
    func remove(account: String) throws {
        let status = SecItemDelete(query(account) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw Failure(status: status) }
    }
}
