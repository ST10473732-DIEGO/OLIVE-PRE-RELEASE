import SwiftUI
import VisionKit

struct PairingSheet: View {
    let pairing: ConnectPairingClient
    var completed: () -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var offer = ""
    @State private var observed = ""
    @State private var scanning = false
    @State private var pasteExpanded = false
    private var scannerAvailable: Bool { DataScannerViewController.isSupported && DataScannerViewController.isAvailable }
    private var step: String {
        switch pairing.state {
        case .idle, .failed: "start"
        case .connecting: "connecting"
        case .comparing, .waiting: "compare"
        case .completed: "done"
        }
    }
    var body: some View {
        VStack(spacing: 0) {
            header
            GeometryReader { geometry in
                ScrollView {
                    content
                        .id(step)
                        .transition(reduceMotion ? .opacity : .asymmetric(
                            insertion: .opacity.combined(with: .offset(y: 16)), removal: .opacity))
                        .padding(.horizontal, OliveTheme.Space.page).padding(.vertical, OliveTheme.Space.medium)
                        .frame(maxWidth: 520)
                        .frame(maxWidth: .infinity, minHeight: geometry.size.height)
                }.scrollDismissesKeyboard(.interactively)
            }
        }
        .background(OliveTheme.surface.ignoresSafeArea())
        .animation(OliveTheme.Motion.settle, value: step)
        .fullScreenCover(isPresented: $scanning) {
            PairingScannerScreen { code in
                scanning = false; pairing.begin(Data(code.utf8))
            } close: { scanning = false }
        }
        .onDisappear { if pairing.state != .completed { pairing.cancel() } }
    }

    /// Laid out by hand so the close control can never overlap the title or status.
    private var header: some View {
        HStack(spacing: 12) {
            Button(pairing.state == .completed ? "Close" : "Cancel") { pairing.cancel(); dismiss() }
                .font(.body).foregroundStyle(OliveTheme.secondary).frame(minWidth: 64, minHeight: 44, alignment: .leading)
            Spacer(minLength: 0)
            Text("Pair computer").font(.headline).lineLimit(1).accessibilityAddTraits(.isHeader)
            Spacer(minLength: 0)
            Color.clear.frame(width: 64, height: 44)
        }.padding(.horizontal, OliveTheme.Space.medium).padding(.top, 8)
    }

    @ViewBuilder private var content: some View {
        switch pairing.state {
        case .idle, .failed: start
        case .connecting: connecting
        case .comparing, .waiting: compare
        case .completed: done
        }
    }

    private var start: some View {
        VStack(spacing: 24) {
            OliveIcon(symbol: "qrcode.viewfinder", size: 72)
            VStack(spacing: 8) {
                Text("Scan your computer’s code").font(OliveTheme.TypeStyle.heading)
                Text("On your computer, open Devices → Connect a device. Scan its pairing QR code.")
                    .foregroundStyle(OliveTheme.secondary).fixedSize(horizontal: false, vertical: true)
            }.multilineTextAlignment(.center)
            if case .failed(let message) = pairing.state {
                VStack(alignment: .leading, spacing: 8) {
                    Label(message, systemImage: "exclamationmark.triangle.fill").font(.subheadline)
                        .foregroundStyle(OliveTheme.attention).fixedSize(horizontal: false, vertical: true)
                    DisclosureGroup("Connection diagnostic") {
                        Text(pairing.diagnostic).font(.caption.monospaced()).textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(.top, 6)
                    }.font(.caption).tint(OliveTheme.muted)
                }
                .padding(14).frame(maxWidth: .infinity, alignment: .leading)
                .background(OliveTheme.attention.opacity(0.1), in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous))
            }
            VStack(spacing: 12) {
                Button("Scan pairing code", systemImage: "camera.viewfinder") { scanning = true }
                    .buttonStyle(OliveButtonStyle(fullWidth: true)).disabled(!scannerAvailable)
                if !scannerAvailable {
                    Text("The camera scanner isn’t available on this iPhone. Paste the code instead.")
                        .font(.caption).foregroundStyle(OliveTheme.muted).multilineTextAlignment(.center)
                }
                OliveCard {
                    DisclosureGroup(isExpanded: $pasteExpanded.animation(OliveTheme.Motion.settle)) {
                        VStack(spacing: 12) {
                            TextEditor(text: $offer).frame(minHeight: 110).font(.caption.monospaced())
                                .scrollContentBackground(.hidden).padding(8)
                                .background(OliveTheme.surface, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control))
                                .accessibilityIdentifier("pairing.offer")
                            Button("Begin pairing") { pairing.begin(Data(offer.utf8)); offer = "" }
                                .buttonStyle(OliveButtonStyle(kind: .secondary, fullWidth: true)).disabled(offer.isEmpty)
                        }.padding(.top, 12)
                    } label: {
                        Label("Paste a public pairing code", systemImage: "doc.on.clipboard").font(.subheadline.weight(.medium))
                            .foregroundStyle(OliveTheme.text)
                    }.tint(OliveTheme.muted)
                }
            }
        }
    }

    private var connecting: some View {
        VStack(spacing: 28) {
            PairingPulse(symbol: "desktopcomputer")
            VStack(spacing: 8) {
                Text("Verifying computer…").font(OliveTheme.TypeStyle.heading)
                Text("Opening a private, encrypted connection on your local network.")
                    .foregroundStyle(OliveTheme.secondary).fixedSize(horizontal: false, vertical: true)
            }.multilineTextAlignment(.center)
        }.accessibilityElement(children: .combine)
    }

    private var compare: some View {
        VStack(spacing: 24) {
            VStack(spacing: 12) {
                OliveIcon(symbol: "desktopcomputer", size: 56)
                Text(pairing.candidateName).font(OliveTheme.TypeStyle.heading).multilineTextAlignment(.center)
                Text("Compare the entire value on both devices.").foregroundStyle(OliveTheme.secondary)
                    .multilineTextAlignment(.center)
            }
            VStack(alignment: .leading, spacing: 10) {
                Text(pairing.comparison).font(.system(.callout, design: .monospaced).weight(.medium))
                    .foregroundStyle(OliveTheme.text).textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier("pairing.comparison")
                Divider().overlay(OliveTheme.border)
                Text("Identity: \(pairing.fingerprint)").font(.caption.monospaced()).foregroundStyle(OliveTheme.muted)
                    .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
            }
            .padding(16)
            .background(OliveTheme.ground, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous).stroke(OliveTheme.accent.opacity(0.35)))
            if pairing.state == .comparing {
                VStack(spacing: 12) {
                    TextField("Value displayed on your computer", text: $observed, axis: .vertical)
                        .textInputAutocapitalization(.characters).autocorrectionDisabled()
                        .font(.system(.body, design: .monospaced)).padding(12)
                        .background(OliveTheme.raised, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous).stroke(OliveTheme.border))
                    Button("Values match") { pairing.confirm(observed: observed.trimmingCharacters(in: .whitespacesAndNewlines)) }
                        .buttonStyle(OliveButtonStyle(fullWidth: true)).disabled(observed.isEmpty)
                }
            } else {
                VStack(spacing: 12) {
                    OliveActivityDots()
                    Text("Waiting for confirmation on your computer…").font(.subheadline).foregroundStyle(OliveTheme.secondary)
                        .multilineTextAlignment(.center)
                }.transition(.opacity)
            }
        }.animation(OliveTheme.Motion.settle, value: pairing.state)
    }

    private var done: some View {
        VStack(spacing: 24) {
            PairedCheck()
            VStack(spacing: 8) {
                Text("Paired").font(OliveTheme.TypeStyle.heading)
                Text("Enable Remote AI for this iPhone in your computer’s Devices screen.")
                    .foregroundStyle(OliveTheme.secondary).fixedSize(horizontal: false, vertical: true)
            }.multilineTextAlignment(.center)
            Button("Done") { completed(); dismiss() }.buttonStyle(OliveButtonStyle(fullWidth: true))
        }
    }
}

/// Expanding rings around an icon while the phone reaches the computer.
private struct PairingPulse: View {
    let symbol: String
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        TimelineView(.animation(paused: reduceMotion)) { context in
            let time = context.date.timeIntervalSinceReferenceDate
            ZStack {
                ForEach(0..<3, id: \.self) { ring in
                    let progress = reduceMotion ? 0.3 : (time / 2.1 + Double(ring) / 3).truncatingRemainder(dividingBy: 1)
                    Circle().stroke(OliveTheme.accent.opacity(0.5 * (1 - progress)), lineWidth: 1.5)
                        .frame(width: 88 + 70 * progress, height: 88 + 70 * progress)
                }
                OliveIcon(symbol: symbol, size: 80)
            }
        }.frame(width: 160, height: 160).accessibilityHidden(true)
    }
}

private struct PairedCheck: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown = false
    var body: some View {
        Image(systemName: "checkmark.shield.fill").font(.system(size: 40, weight: .semibold))
            .foregroundStyle(OliveTheme.accentInk)
            .frame(width: 88, height: 88).background(OliveTheme.accent, in: Circle())
            .scaleEffect(shown || reduceMotion ? 1 : 0.6).opacity(shown || reduceMotion ? 1 : 0)
            .onAppear { withAnimation(.spring(response: 0.45, dampingFraction: 0.6)) { shown = true } }
            .accessibilityHidden(true)
    }
}

/// Full-screen camera with its own controls, so nothing is layered over the pairing status.
private struct PairingScannerScreen: View {
    let found: (String) -> Void
    let close: () -> Void
    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()
            PairingScanner(found: found).ignoresSafeArea()
            VStack {
                HStack {
                    Button(action: close) {
                        Image(systemName: "xmark").font(.headline).foregroundStyle(.white)
                            .frame(width: 44, height: 44).background(.black.opacity(0.55), in: Circle())
                    }.accessibilityLabel("Close scanner")
                    Spacer()
                }
                Spacer()
                Text("Point at the QR code on your computer").font(.subheadline.weight(.medium)).foregroundStyle(.white)
                    .padding(.horizontal, 16).padding(.vertical, 10).background(.black.opacity(0.55), in: Capsule())
            }.padding(OliveTheme.Space.medium)
        }
    }
}

private struct PairingScanner: UIViewControllerRepresentable {
    let found: (String) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(found: found) }
    func makeUIViewController(context: Context) -> DataScannerViewController {
        let scanner = DataScannerViewController(recognizedDataTypes: [.barcode(symbologies: [.qr])],
            qualityLevel: .balanced, recognizesMultipleItems: false, isHighFrameRateTrackingEnabled: false,
            isPinchToZoomEnabled: true, isGuidanceEnabled: false, isHighlightingEnabled: true)
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
