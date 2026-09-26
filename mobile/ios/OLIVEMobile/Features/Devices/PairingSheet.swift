import SwiftUI
import VisionKit

struct PairingSheet: View {
    let pairing: ConnectPairingClient
    var completed: () -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var offer = ""
    @State private var observed = ""
    @State private var scanning = false
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    switch pairing.state {
                    case .idle, .failed:
                        Text("On your computer, open Devices → Connect a device. Scan its pairing QR code.")
                        Button("Scan pairing code", systemImage: "qrcode.viewfinder") { scanning = true }
                            .buttonStyle(.borderedProminent)
                            .disabled(!DataScannerViewController.isSupported || !DataScannerViewController.isAvailable)
                        DisclosureGroup("Paste a public pairing code") {
                            TextEditor(text: $offer).frame(minHeight: 120).font(.caption.monospaced())
                                .accessibilityIdentifier("pairing.offer")
                            Button("Begin pairing") { pairing.begin(Data(offer.utf8)); offer = "" }.disabled(offer.isEmpty)
                        }
                        if case .failed(let message) = pairing.state {
                            Text(message).foregroundStyle(OliveTheme.attention)
                            DisclosureGroup("Connection diagnostic") { Text(pairing.diagnostic).font(.caption.monospaced()).textSelection(.enabled) }
                        }
                    case .connecting:
                        ProgressView("Verifying computer…")
                    case .comparing, .waiting:
                        Text(pairing.candidateName).font(.title2)
                        Text("Compare the entire value on both devices.")
                        Text(pairing.comparison).font(.system(.callout, design: .monospaced)).textSelection(.enabled)
                            .accessibilityIdentifier("pairing.comparison")
                        Text("Identity: \(pairing.fingerprint)").font(.caption.monospaced()).textSelection(.enabled)
                        if pairing.state == .comparing {
                            TextField("Value displayed on your computer", text: $observed, axis: .vertical)
                                .textInputAutocapitalization(.characters).autocorrectionDisabled().textFieldStyle(.roundedBorder)
                            Button("Values match") { pairing.confirm(observed: observed.trimmingCharacters(in: .whitespacesAndNewlines)) }
                                .buttonStyle(.borderedProminent).disabled(observed.isEmpty)
                        } else { ProgressView("Waiting for confirmation on your computer…") }
                    case .completed:
                        Label("Paired", systemImage: "checkmark.shield")
                        Text("Enable Remote AI for this iPhone in your computer’s Devices screen.")
                        Button("Done") { completed(); dismiss() }.buttonStyle(.borderedProminent)
                    }
                }.padding(24)
            }.background(OliveTheme.surface).navigationTitle("Pair computer")
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { pairing.cancel(); dismiss() } } }
                .sheet(isPresented: $scanning) {
                    PairingScanner { code in
                        scanning = false; pairing.begin(Data(code.utf8))
                    }.ignoresSafeArea()
                }
                .onDisappear { if pairing.state != .completed { pairing.cancel() } }
        }
    }
}

private struct PairingScanner: UIViewControllerRepresentable {
    let found: (String) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(found: found) }
    func makeUIViewController(context: Context) -> DataScannerViewController {
        let scanner = DataScannerViewController(recognizedDataTypes: [.barcode(symbologies: [.qr])],
            qualityLevel: .balanced, recognizesMultipleItems: false, isHighFrameRateTrackingEnabled: false,
            isPinchToZoomEnabled: true, isGuidanceEnabled: true, isHighlightingEnabled: true)
        scanner.delegate = context.coordinator
        do { try scanner.startScanning() } catch { /* Camera remains dismissible; public-code fallback remains available. */ }
        return scanner
    }
    func updateUIViewController(_ controller: DataScannerViewController, context: Context) {}
    static func dismantleUIViewController(_ controller: DataScannerViewController, coordinator: Coordinator) { controller.stopScanning() }
    @MainActor final class Coordinator: NSObject, DataScannerViewControllerDelegate {
        let found: (String) -> Void
        private var delivered = false
        init(found: @escaping (String) -> Void) { self.found = found }
        func dataScanner(_ dataScanner: DataScannerViewController, didAdd addedItems: [RecognizedItem], allItems: [RecognizedItem]) {
            guard !delivered else { return }
            for case .barcode(let barcode) in addedItems {
                if let text = barcode.payloadStringValue, text.utf8.count <= 4096 {
                    delivered = true; dataScanner.stopScanning(); found(text); return
                }
            }
        }
    }
}
