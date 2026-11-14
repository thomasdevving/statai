import SwiftUI

/// Settings → Voice Lab (IOS-05.1): connect to Gemini Live outside a cook-along, type a question,
/// and read the event log. The acceptance check for the wire protocol and audio out.
struct VoiceLabView: View {
    @Environment(AppEnvironment.self) private var env
    @State private var voice: VoiceController?
    @State private var host = VoiceLabHost()
    @State private var question = "Why spread it to the edges?"  // the demo question, ai/eval/qa.csv
    @State private var recipeError: String?

    var body: some View {
        Form {
            Section {
                LabeledContent("Status", value: statusText)
                LabeledContent("Recipe", value: host.recipeTitle ?? "—")
                if let recipeError {
                    Text(recipeError).font(.footnote).foregroundStyle(.red)
                }
                if voice?.isConnected == true {
                    Button("Disconnect", role: .destructive) { voice?.stop() }
                } else {
                    Button("Connect") { Task { await connect() } }
                        .disabled(voice?.status == .connecting)
                }
            } footer: {
                Text("Fetches a token from /live-token for the first published recipe and opens the Live socket from the phone.")
            }

            Section("Ask") {
                TextField("Question", text: $question, axis: .vertical)
                Button("Send Question") { voice?.sendTypedQuestion(question) }
                    .disabled(voice?.isConnected != true)
                Button("Send Context Line") {
                    voice?.sendTypedQuestion(liveContextLine(stepIdx: 4, total: 6, title: "Add fillings"))
                }
                .disabled(voice?.isConnected != true)
            }

            Section("Last turn") {
                LabeledContent("You said", value: voice?.inputText.isEmpty == false ? voice!.inputText : "—")
                LabeledContent("Caption", value: voice?.outputText.isEmpty == false ? LiveCaption.clean(voice!.outputText) : "—")
                LabeledContent("Lens", value: host.lastLens)
            }

            Section("Events") {
                if let log = voice?.log, !log.isEmpty {
                    ForEach(Array(log.enumerated().reversed()), id: \.offset) { _, line in
                        Text(line).font(.caption.monospaced())
                    }
                } else {
                    Text("No events yet").foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle("Voice Lab")
        .onDisappear { voice?.stop() }
    }

    private var statusText: String {
        switch voice?.status ?? .off {
        case .off: "Off"
        case .connecting: "Connecting…"
        case .ready: "Connected"
        case .unavailable(let why): "Unavailable: \(why)"
        case .micDenied: "Microphone denied"
        }
    }

    private func connect() async {
        recipeError = nil
        do {
            let recipes = try await env.api.recipes(status: .published)
            guard let first = recipes.first else {
                recipeError = "No published recipe on this backend."
                return
            }
            host.recipeID = first.id
            host.recipeTitle = first.title
        } catch {
            recipeError = error.localizedDescription
            return
        }
        let controller = voice ?? env.makeVoiceLabController()
        controller.host = host
        voice = controller
        controller.start()
    }
}

/// A stand-in cook-along for the lab: one fixed step, lens changes shown as text.
@MainActor
@Observable
final class VoiceLabHost: VoiceHost {
    var recipeID: String?
    var recipeTitle: String?
    var lastLens = "—"

    var voiceRecipeID: String? { recipeID }
    var voiceSessionID: String? { nil }
    var voiceStep: VoiceStepContext? {
        VoiceStepContext(idx: 4, total: 6, title: "Add fillings", instruction: "Lay the ham and cheese in one even layer, right to the edges.")
    }

    func voiceShowTalking(_ phase: TalkPhase, caption: String) { lastLens = "talking \(phase.rawValue): \(caption)" }
    func voiceEndTalking() { lastLens = "back to the step" }
    func voiceRun(_ input: CookInput) { lastLens = "command: \(input)" }
    func voicePostQuestion(caption: String, transcript: String) {}
    func voicePostClientError(_ detail: String) { lastLens = "error: \(detail)" }
}
