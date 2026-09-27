import BackgroundTasks
import Foundation
import Observation
import UIKit

/// Runtime permission is never Connect authority. A task only extends work the
/// user already started, and its absence cannot authorize replay or fake success.
@MainActor @Observable
final class BackgroundWorkCoordinator {
    private static let identifier = "io.github.st10473732-diego.olive.mobile.continued"
    let notifications = CompletionNotifications()
    private let store: ProtectedStore<[BackgroundOperationRecord]>
    private(set) var records: [BackgroundOperationRecord] = []
    private(set) var notice: String?
    private(set) var canWrite = true
    private var systemTask: AnyObject?
    private var submitted = false
    private var registered = false
    var onIdle: (@MainActor () -> Void)?
    private var cancelWork: (@MainActor () async -> Void)?
    var active: BackgroundOperationRecord? { records.last(where: { $0.state == .running }) }
    var continuationGranted: Bool { systemTask != nil && active != nil }

    init(directory: URL = URL.applicationSupportDirectory.appendingPathComponent("Companion"), register: Bool = true) {
        store = ProtectedStore(url: directory.appendingPathComponent("operations-v1.json"), maximumBytes: 256_000)
        do {
            records = try store.load() ?? []
            guard records.count <= 128 else { throw ConnectFailure.localStorageUnavailable }
            let unfinished = records.contains { $0.state == .running }
            for i in records.indices { records[i].reconcileAfterLaunch() }
            if unfinished { try store.save(records) }
        } catch { canWrite = false; notice = "Operation history is unavailable. Existing data has been preserved." }
        if register, #available(iOS 26.0, *) {
            registered = BGTaskScheduler.shared.register(forTaskWithIdentifier: Self.identifier, using: .main) { [weak self] task in
                MainActor.assumeIsolated {
                    guard let self, let continued = task as? BGContinuedProcessingTask,
                          self.submitted, self.active != nil else { task.setTaskCompleted(success: false); return }
                    self.systemTask = continued
                    continued.expirationHandler = { [weak self] in
                        Task { @MainActor in await self?.cancel(expired: true) }
                    }
                    self.publishProgress()
                }
            }
        }
    }

    func begin(_ record: BackgroundOperationRecord, cancel: @escaping @MainActor () async -> Void) throws {
        guard canWrite else { throw ConnectFailure.localStorageUnavailable }
        guard active == nil else { throw ConnectFailure.resourceBusy }
        var next = Array(records.suffix(127)); next.append(record)
        try store.save(next); records = next; cancelWork = cancel; notice = nil
        if #available(iOS 26.0, *), registered, UIApplication.shared.applicationState == .active {
            let request = BGContinuedProcessingTaskRequest(identifier: Self.identifier, title: "OLIVE", subtitle: record.label)
            // Never queue a future effect after the user has left or cancelled.
            request.strategy = .fail
            submitted = true
            do { try BGTaskScheduler.shared.submit(request) }
            catch { submitted = false; notice = ConnectFailure.backgroundTaskUnavailable.localizedDescription }
        } else { notice = ConnectFailure.backgroundTaskUnavailable.localizedDescription }
    }

    func progress(_ units: Int64, total: Int64? = nil) throws {
        guard let index = records.lastIndex(where: { $0.state == .running }) else { return }
        guard units >= records[index].verifiedUnits, units >= 0,
              total == nil || total! >= units else { throw ConnectFailure.responseMalformed }
        var next = records
        next[index].verifiedUnits = units
        if let total { next[index].totalUnits = total }
        try store.save(next); records = next; publishProgress()
    }

    private func publishProgress() {
        if #available(iOS 26.0, *), let task = systemTask as? BGContinuedProcessingTask, let record = active {
            // Unknown-length Chat/Studio stays indeterminate, never elapsed-time percent.
            task.progress.totalUnitCount = record.totalUnits ?? -1
            task.progress.completedUnitCount = record.verifiedUnits
            task.updateTitle("OLIVE", subtitle: record.label)
        }
    }

    func finish(_ state: BackgroundOperationRecord.State, id: String? = nil) {
        if let id, active?.id != id { return }
        guard state != .running else { return }
        if let index = records.lastIndex(where: { $0.state == .running }) {
            var next = records; next[index].state = state
            do { try store.save(next); records = next; if state == .completed { notifications.completed(next[index]) } }
            catch {
                records[index].state = .interrupted; canWrite = false
                notice = "The last operation could not be saved. Its result must be checked."
            }
        }
        if #available(iOS 26.0, *), let task = systemTask as? BGContinuedProcessingTask {
            task.setTaskCompleted(success: state == .completed && canWrite)
        }
        systemTask = nil
        if submitted { BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: Self.identifier) }
        submitted = false; cancelWork = nil
    }

    func cancel(expired: Bool = false) async {
        guard active != nil else { return }
        let cleanup = cancelWork
        // Persist interruption before yielding to cancellation/network operations.
        finish(expired ? .expired : .cancelled)
        notice = (expired ? ConnectFailure.backgroundTaskExpired : .backgroundTaskCancelled).localizedDescription
        let assertion = UIApplication.shared.beginBackgroundTask(withName: "OLIVE cancellation") { [weak self] in
            Task { @MainActor in self?.onIdle?() }
        }
        await cleanup?()
        onIdle?()
        if assertion != .invalid { UIApplication.shared.endBackgroundTask(assertion) }
    }
}
