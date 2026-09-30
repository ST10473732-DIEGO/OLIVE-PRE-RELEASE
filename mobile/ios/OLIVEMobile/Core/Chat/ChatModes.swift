import Foundation

/// OLIVE's public Chat modes. The computer owns what each mode runs; these are
/// user-facing names only (never model tags, checkpoints or workflow files).
struct ChatMode: Identifiable, Hashable, Sendable {
    enum Group: String, CaseIterable, Sendable { case chat = "Chat", research = "Research", create = "Create" }
    let id: String
    let short: String
    let group: Group
    let summary: String
    let symbol: String
    var name: String { "OLIVE " + short }

    static let all: [ChatMode] = [
        ChatMode(id: "fast", short: "FAST", group: .chat, summary: "Quick answers and code.", symbol: "hare"),
        ChatMode(id: "normal", short: "NORMAL", group: .chat, summary: "Everyday answers and reasoning.", symbol: "bubble.left.and.text.bubble.right"),
        ChatMode(id: "max", short: "MAX", group: .chat, summary: "Heavy answers and code.", symbol: "bolt"),
        ChatMode(id: "uncensored", short: "UNCENSORED", group: .chat, summary: "Reduced-refusal local models. Your computer picks the tier.", symbol: "lock.open"),
        ChatMode(id: "now", short: "NOW", group: .research, summary: "Live public information with sources.", symbol: "globe"),
        ChatMode(id: "deep", short: "DEEP", group: .research, summary: "Documents and research with citations.", symbol: "doc.text.magnifyingglass"),
        ChatMode(id: "reimagine", short: "REIMAGINE", group: .create, summary: "Create or edit an image.", symbol: "photo.artframe"),
        ChatMode(id: "audio", short: "AUDIO", group: .create, summary: "Spoken audio from your words.", symbol: "waveform"),
        ChatMode(id: "video", short: "VIDEO", group: .create, summary: "A short video from your description.", symbol: "film"),
    ]
    static let legacy: Set<String> = ["fast", "normal", "max"]
    static func named(_ id: String) -> ChatMode { all.first { $0.id == id } ?? all[1] }
    var isMedia: Bool { group == .create }

    /// Phone-side ceiling on waiting for one request. The computer has its own
    /// per-mode deadlines; this only stops the phone waiting forever.
    var patience: Duration {
        switch id {
        case "now", "deep": .seconds(600)
        case "reimagine": .seconds(900)
        case "audio": .seconds(600)
        case "video": .seconds(1800)
        default: .seconds(360)
        }
    }
}

/// Availability of one mode for the selected computer, for the picker and Send.
enum ChatModeAvailability: Equatable, Sendable {
    case available
    case offline
    case unsupportedComputer
    case unavailable
    case permissionOff

    var explanation: String {
        switch self {
        case .available: ""
        case .offline: "Your OLIVE computer is offline."
        case .unsupportedComputer: "This computer's OLIVE doesn't support this mode yet."
        case .unavailable: "Not set up on this computer."
        case .permissionOff: "Remote AI is off for this iPhone on your computer."
        }
    }
}

enum ChatText {
    /// Factual progress the computer reported. Never a percentage.
    static func phase(_ code: String) -> String? {
        switch code {
        case "approval": "Waiting for approval on your computer…"
        case "queued": "Queued on your computer…"
        case "thinking": "Thinking…"
        case "retrieving": "Retrieving live sources…"
        case "reading_documents": "Reading attached evidence…"
        case "indexing": "Processing document…"
        case "synthesizing": "Writing the answer from sources…"
        case "releasing_gpu": "Freeing the graphics card…"
        case "preparing_image_engine": "Preparing image engine…"
        case "generating_image": "Generating image…"
        case "preparing_audio_engine": "Preparing audio engine…"
        case "generating_speech": "Generating speech…"
        case "preparing_video_engine": "Preparing video engine…"
        case "generating_video": "Generating video…"
        case "saving": "Saving result…"
        default: nil
        }
    }

    static func limitation(_ code: String, mode: ChatMode) -> String? {
        switch code {
        case "text_only": mode.short + " currently supports text prompts only."
        case "speech_only": "Spoken audio only — not music, singing or sound effects."
        case "one_reference_image": "Attach one image to edit it."
        case "automatic_tier": "Your computer chooses the tier automatically."
        case "public_web_only": "Public questions only; attachments stay on this iPhone."
        case "video_with_audio": "Videos include generated sound."
        default: nil
        }
    }

    /// Specific, safe failures. Unknown codes fall back to a generic sentence.
    static func error(_ code: String, mode: ChatMode) -> String {
        switch code {
        case "mode_unavailable": mode.short + " isn't set up on this computer."
        case "permission_denied", "confirmation_required": "Remote AI isn't allowed for this iPhone on your computer."
        case "busy", "engine_busy": "Your computer is busy with another request. Try again shortly."
        case "rate_limited": "Too many requests. Wait a minute, then send again."
        case "unsupported_attachment": "This attachment type isn't supported by " + mode.short + " on this computer."
        case "attachment_unsupported_mode": mode.short + " doesn't accept this attachment."
        case "private_context": "OLIVE NOW answers public questions only. Remove attachments to send."
        case "too_many_attachments": "Too many attachments for " + mode.short + "."
        case "too_many_references": "Attach one reference image for this edit."
        case "attachment_too_large": "This file is too large for " + mode.short + " on this computer."
        case "attachment_missing", "attachment_corrupt": "Upload failed. Your attachment is still on this iPhone; send again."
        case "storage_full": "Your computer is low on space for attachments."
        case "document_unreadable": "The document has no readable text."
        case "indexing_failed": "Document indexing failed. The document was not read."
        case "vision_unavailable": "Image reading isn't set up on this computer."
        case "input_too_large": "This request is too long for the computer's model. Shorten it or clear the chat."
        case "output_limit": "The answer reached its size limit."
        case "generation_timeout", "timeout": "Your computer took too long and stopped the request."
        case "cancelled": "Generation stopped."
        case "request_indeterminate": "Your computer restarted while working on this. The result is unknown; nothing was resent."
        case "computer_stopped": "Your computer stopped this request when OLIVE restarted or went offline. Nothing was resent."
        case "model_unavailable", "local_required": mode.short + " needs its local model on your computer."
        case "search_unavailable", "page_failed": "Live research is unavailable on your computer right now; current information couldn't be verified."
        case "weather_unavailable": "The weather source is unavailable; current conditions couldn't be verified."
        case "no_fresh_evidence": "No fresh evidence was found; current information couldn't be verified."
        case "place_required": "Say which place, for example: weather in Cape Town tomorrow."
        case "weather_period": "Weather covers now, today, tomorrow and yesterday."
        case "question_limit": "Keep live questions under 1,000 characters."
        case "synthesis_invalid": "The answer couldn't be verified against its sources, so it was withheld."
        case "image_not_configured": "Image generation isn't set up on this computer."
        case "audio_not_configured", "audio_model_missing": "Audio generation isn't set up on this computer."
        case "audio_exposed", "audio_unverified": "Your computer paused AUDIO: its speech service isn't verified as local-only."
        case "video_not_configured": "Video generation isn't set up on this computer."
        case "workflow_missing", "model_missing", "engine_start_failed", "engine_unreachable", "engine_incompatible":
            "The media engine on your computer isn't ready. Nothing was generated."
        case "gpu_busy", "gpu_release_unverified": "Another app is using your computer's graphics card. Nothing was generated."
        case "generation_failed", "no_artifact": "The media engine reported an error. Nothing was saved."
        case "prompt_required": "Describe what OLIVE should create."
        case "prompt_too_long": "Keep media requests under 4,000 characters."
        case "audio_unsupported": "OLIVE AUDIO creates spoken audio only — not music, singing or sound effects."
        case "speech_text_required": "Say what OLIVE should speak, for example: Say: Welcome to OLIVE."
        case "speech_too_long": "Keep speech text under 4,000 characters."
        case "artifact_unavailable": "This result is no longer available on your computer."
        case "changed_duplicate": "This request changed while it was being sent. Nothing was run twice."
        case "ledger_full": "Your computer's request history is full. Check Devices on the computer."
        case "expired_request": "The request expired. Check the time on your iPhone and computer."
        default: mode.short + " couldn't finish this request on your computer."
        }
    }
}
