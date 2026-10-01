import Foundation
import Network

/// One logical computer over two paths: Direct (LAN) preferred, World as the
/// automatic fallback. Mirrors olive/world/paths.py exactly (same transitions,
/// tested with the same scenarios). Every attempt carries a generation, so a late
/// callback from a retired transport can never overwrite the current state.
struct WorldPathSelector: Equatable {
    enum State: String { case offline, discovering, directConnecting, direct, worldConnecting, world, switching, revoked, error }
    enum Action: Equatable {
        case connect(ConnectPath, generation: Int, delay: Double)
        case close(ConnectPath, generation: Int)
        case cancel(ConnectPath, generation: Int)
    }
    static let worldFallbackDelay = 1.5

    var worldAvailable = false
    var directAllowed = true
    var worldAllowed = true
    private(set) var state = State.offline
    private(set) var active: ConnectPath?
    private(set) var activeGeneration = 0
    private(set) var generation = 0
    private(set) var attempts: [ConnectPath: Int] = [:]

    init(worldAvailable: Bool = false, directAllowed: Bool = true, worldAllowed: Bool = true) {
        self.worldAvailable = worldAvailable; self.directAllowed = directAllowed; self.worldAllowed = worldAllowed
    }

    private mutating func next(_ path: ConnectPath) -> Int { generation += 1; attempts[path] = generation; return generation }

    mutating func start(lanUsable: Bool) -> [Action] {
        guard state != .revoked else { return [] }
        var actions: [Action] = []
        state = .discovering
        if directAllowed { actions.append(.connect(.direct, generation: next(.direct), delay: 0)); state = .directConnecting }
        if worldAllowed && worldAvailable {
            let delay = directAllowed && lanUsable ? Self.worldFallbackDelay : 0
            actions.append(.connect(.world, generation: next(.world), delay: delay))
            if !directAllowed { state = .worldConnecting }
        }
        if actions.isEmpty { state = .offline }
        return actions
    }

    mutating func authenticated(_ path: ConnectPath, generation: Int) -> [Action] {
        guard state != .revoked, attempts[path] == generation else { return [.close(path, generation: generation)] }
        attempts[path] = nil
        if active == .direct && path == .world { return [.close(.world, generation: generation)] }
        var actions: [Action] = []
        if let current = active, current != path {
            actions.append(.close(current, generation: activeGeneration)); state = .switching
        }
        if path == .direct, let pending = attempts.removeValue(forKey: .world) {
            actions.append(.cancel(.world, generation: pending))
        }
        active = path; activeGeneration = generation; state = path == .direct ? .direct : .world
        return actions
    }

    mutating func failed(_ path: ConnectPath, generation: Int) -> [Action] {
        guard state != .revoked else { return [] }
        if attempts[path] == generation { attempts[path] = nil }
        else if !(active == path && activeGeneration == generation) { return [] }
        if active == path && activeGeneration == generation { active = nil }
        var actions: [Action] = []
        if active == nil {
            if path == .direct && worldAllowed && worldAvailable && attempts[.world] == nil {
                actions.append(.connect(.world, generation: next(.world), delay: 0)); state = .worldConnecting
            } else if !attempts.isEmpty {
                state = attempts[.world] != nil ? .worldConnecting : .directConnecting
            } else {
                state = .offline
            }
        }
        return actions
    }

    mutating func directCandidate() -> [Action] {
        guard state == .world, directAllowed, attempts[.direct] == nil else { return [] }
        return [.connect(.direct, generation: next(.direct), delay: 0)]
    }

    mutating func revoke() -> [Action] {
        var actions = attempts.map { Action.close($0.key, generation: $0.value) }
        if let active { actions.append(.close(active, generation: activeGeneration)) }
        attempts.removeAll(); active = nil; state = .revoked
        return actions
    }

    mutating func reset() { attempts.removeAll(); active = nil; state = .offline }
}

/// Bounded exponential reconnect with jitter (mirrors olive/world/backoff.py).
struct WorldBackoff {
    static let delays: [Double] = [0.5, 1, 2, 5, 10, 30]
    static let stableAfter: Double = 30
    private(set) var attempt = 0
    var jitter = 0.2
    mutating func next(random: Double = Double.random(in: -1...1)) -> Double {
        let base = Self.delays[min(attempt, Self.delays.count - 1)]
        attempt += 1
        return max(0.05, base * (1 + jitter * random))
    }
    mutating func reset() { attempt = 0 }
    mutating func settled(lived: Double) { if lived >= Self.stableAfter { reset() } }
}

/// Normal iOS network-change signals (no polling). Wi-Fi <-> cellular and
/// "network back" trigger one immediate bounded reconnect attempt.
@MainActor
final class WorldNetworkMonitor {
    struct Snapshot: Equatable { var satisfied: Bool; var wifi: Bool; var cellular: Bool }
    private var monitor: NWPathMonitor?          // A cancelled monitor cannot restart: one per start().
    private let queue = DispatchQueue(label: "olive.world.path")
    private(set) var current = Snapshot(satisfied: true, wifi: true, cellular: false)
    var onChange: (@MainActor (Snapshot, Snapshot) -> Void)?
    func start() {
        guard monitor == nil else { return }
        let monitor = NWPathMonitor()
        monitor.pathUpdateHandler = { [weak self] path in
            let snapshot = Snapshot(satisfied: path.status == .satisfied,
                                    wifi: path.usesInterfaceType(.wifi) || path.usesInterfaceType(.wiredEthernet),
                                    cellular: path.usesInterfaceType(.cellular))
            Task { @MainActor in self?.update(snapshot) }
        }
        monitor.start(queue: queue)
        self.monitor = monitor
    }
    private func update(_ snapshot: Snapshot) {
        let previous = current
        current = snapshot
        if previous != snapshot { onChange?(previous, snapshot) }
    }
    func stop() { monitor?.cancel(); monitor = nil }
}
