import Foundation
import Network
import Observation

struct NearbyConnectPeer: Identifiable, Sendable {
    let id: String
    let endpoint: NWEndpoint
    // C3 deliberately advertises an opaque instance, not a device display name.
    var title: String { "OLIVE computer" }
}

@MainActor @Observable
final class ConnectDiscoveryService {
    private(set) var nearby: [NearbyConnectPeer] = []
    private(set) var status = "Discovery off"
    private var browser: NWBrowser?
    private var generation = UUID()
    @ObservationIgnored var onNewEndpoints: (() -> Void)?
    private(set) var revision = 0
    func updateNearby(_ peers: [NearbyConnectPeer]) {
        let next = Self.bounded(peers)
        let added = !Set(next.map(\.id)).subtracting(nearby.map(\.id)).isEmpty
        nearby = next
        if added { revision += 1; onNewEndpoints?() }
    }
    func start() {
        guard browser == nil else { return }
        let token = UUID(); generation = token
        let parameters = NWParameters.tcp
        parameters.requiredInterfaceType = .wifi
        parameters.prohibitedInterfaceTypes = [.cellular]
        parameters.includePeerToPeer = false
        let browser = NWBrowser(for: .bonjourWithTXTRecord(type: "_olive-connect._tcp", domain: "local."), using: parameters)
        self.browser = browser; status = "Looking nearby…"
        browser.stateUpdateHandler = { [weak self] state in
            Task { @MainActor in
                guard let self, self.generation == token else { return }
                switch state {
                case .ready: self.status = "Looking on your local network"
                case .waiting(let error), .failed(let error):
                    self.status = error == .dns(DNSServiceErrorType(-65570)) ? ConnectFailure.localNetworkDenied.localizedDescription : ConnectFailure.discoveryUnavailable.localizedDescription
                default: break
                }
            }
        }
        browser.browseResultsChangedHandler = { [weak self] results, _ in
            let valid = results.compactMap { result -> NearbyConnectPeer? in
                guard case .service(let name, let type, let domain, _) = result.endpoint,
                      ["_olive-connect._tcp", "_olive-connect._tcp."].contains(type), ["local", "local."].contains(domain), name.utf8.count <= 128,
                      case .bonjour(let txt) = result.metadata,
                      txt.dictionary == ["product": "OLIVE", "version": "1"] else { return nil }
                return NearbyConnectPeer(id: name, endpoint: result.endpoint)
            }.sorted { $0.id < $1.id }
            Task { @MainActor in
                guard let self, self.generation == token else { return }
                self.updateNearby(valid)
            }
        }
        browser.start(queue: DispatchQueue(label: "olive.connect.discovery"))
    }
    /// Nearby entries not already proven to be a paired computer. The advertisement is
    /// deliberately opaque (a random instance per start, no identity), so only an exact
    /// pinned-TLS success on an endpoint can show it belongs to a paired computer.
    static func unverified(_ peers: [NearbyConnectPeer], verified: Set<String>) -> [NearbyConnectPeer] {
        peers.filter { !verified.contains($0.id) }
    }
    static func bounded(_ peers: [NearbyConnectPeer]) -> [NearbyConnectPeer] {
        var unique: [String: NearbyConnectPeer] = [:]
        for peer in peers where unique.count < 64 { unique[peer.id] = peer }
        return unique.values.sorted { $0.id < $1.id }
    }
    func stop() {
        generation = UUID(); browser?.cancel(); browser = nil; nearby = []; status = "Discovery off"
    }
}
