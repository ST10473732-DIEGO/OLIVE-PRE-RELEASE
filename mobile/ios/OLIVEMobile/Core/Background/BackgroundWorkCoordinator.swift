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
    private var submittedIdentifier: String?
    private let registrationEnabled: Bool
    private(set) var cancelling = false
    var onIdle: (@MainActor () -> Void)?
    private var cancelWork: (@MainActor () async -> Void)?
    var active: BackgroundOperationRecord? { records.last(where: { $0.state == .running }) }
    var continuationGranted: Bool { systemTask != nil && active != nil }

    init(directory: URL = URL.applicationSupportDirectory.appendingPathComponent("Companion"), register: Bool = true) {
        registrationEnabled = register
        store = ProtectedStore(url: directory.appendingPathComponent("operations-v1.json"), maximumBytes: 256_000)
        do {
            records = try store.load() ?? []
            guard records.count <= 128 else { throw ConnectFailure.localStorageUnavailable }
            let unfinished = records.contains { $0.state == .running }
            for i in records.indices { records[i].reconcileAfterLaunch() }
            if unfinished { try store.save(records) }
        } catch { canWrite = false; notice = "Operation history is unavailable. Existing data has been preserved." }
    }

    @available(iOS 26.0, *)
    private func register(_ identifier: String, operation: String) -> Bool {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: identifier, using: .main) { [weak self] task in
            MainActor.assumeIsolated {
                guard let self, let continued = task as? BGContinuedProcessingTask,
                      self.submittedIdentifier == task.identifier, self.active?.id == operation else {
                    task.setTaskCompleted(success: false); return
                }
                self.systemTask = continued
                continued.expirationHandler = { [weak self] in
                    Task { @MainActor in
                        guard self?.submittedIdentifier == identifier, self?.active?.id == operation else { return }
                        await self?.cancel(expired: true)
                    }
                }
                self.publishProgress()
            }
        }
    }

    func begin(_ record: BackgroundOperationRecord, cancel: @escaping @MainActor () async -> Void) throws {
        guard canWrite else { throw ConnectFailure.localStorageUnavailable }
        guard active == nil, !cancelling else { throw ConnectFailure.resourceBusy }
        var next = Array(records.suffix(127)); next.append(record)
        try store.save(next); records = next; cancelWork = cancel; notice = nil
        if #available(iOS 26.0, *), registrationEnabled, UIApplication.shared.applicationState == .active {
            // Register one unique identifier per user action. A delayed callback
            // from a previous action must never extend a replacement operation.
            let identifier = Self.identifier + "." + UUID().uuidString.lowercased()
            guard register(identifier, operation: record.id) else {
                notice = ConnectFailure.backgroundTaskUnavailable.localizedDescription; return
            }
            let request = BGContinuedProcessingTaskRequest(identifier: identifier, title: "OLIVE", subtitle: record.label)
            request.strategy = .fail // No deferred effect queue.
            submittedIdentifier = identifier
            if #available(iOS 27.0, *) {
                Task.detached { [weak self] in
                    guard await self?.submittedIdentifier == identifier else { return }
                    do { try await BGTaskScheduler.shared.submitTaskRequest(request) }
                    catch { await self?.submissionFailed(identifier) }
                }
            } else {
                do { try BGTaskScheduler.shared.submit(request) }
                catch { submissionFailed(identifier) }
            }
        } else { notice = ConnectFailure.backgroundTaskUnavailable.localizedDescription }
    }

    private func submissionFailed(_ identifier: String) {
        guard submittedIdentifier == identifier else { return }
        submittedIdentifier = nil
        if #available(iOS 26.0, *), let task = systemTask as? BGContinuedProcessingTask { task.setTaskCompleted(success: false) }
        systemTask = nil
        notice = ConnectFailure.backgroundTaskUnavailable.localizedDescription
        if UIApplication.shared.applicationState == .background { Task { await cancel(expired: true) } }
    }

    func progress(_ units: Int64, total: Int64? = nil, id: String? = nil) throws {
        if let id, active?.id != id { return }
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

    func finish(_ state: BackgroundOperationRecord.State, id: String? = nil, failure: ConnectFailure? = nil) {
        if let id, active?.id != id { return }
        guard state != .running else { return }
        if let index = records.lastIndex(where: { $0.state == .running }) {
            var next = records; next[index].state = state
            next[index].failure = state == .completed ? nil : failure
            next[index].finishedAt = Date()
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
        if let identifier = submittedIdentifier { BGTaskScheduler.shared.cancel(taskRequestWithIdentifier: identifier) }
        submittedIdentifier = nil; cancelWork = nil
    }

    func cancel(expired: Bool = false) async {
        guard active != nil, !cancelling else { return }
        cancelling = true
        defer { cancelling = false }
        let cleanup = cancelWork
        // Persist interruption before yielding to cancellation/network operations.
        finish(expired ? .expired : .cancelled, failure: expired ? .backgroundTaskExpired : .backgroundTaskCancelled)
        notice = (expired ? ConnectFailure.backgroundTaskExpired : .backgroundTaskCancelled).localizedDescription
        let assertion = UIApplication.shared.beginBackgroundTask(withName: "OLIVE cancellation") { [weak self] in
            Task { @MainActor in self?.onIdle?() }
        }
        await cleanup?()
        onIdle?()
        if assertion != .invalid { UIApplication.shared.endBackgroundTask(assertion) }
    }
}
