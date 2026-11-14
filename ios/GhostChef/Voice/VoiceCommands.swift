import Foundation

// Voice commands as Live function calls (IOS-05.5, API-CONTRACT §5.2).
// The function declarations live in the token (ai/); the app only executes and answers them.

enum VoiceCommand: Equatable, Sendable {
    case checkMyWork
    case nextStep
    case previousStep
    case showMe
    case repeatInstruction
    case unknown(String)

    init(functionName: String) {
        switch functionName {
        case "check_my_work": self = .checkMyWork
        case "next_step": self = .nextStep
        case "previous_step": self = .previousStep
        case "show_me": self = .showMe
        case "repeat_instruction": self = .repeatInstruction
        default: self = .unknown(functionName)
        }
    }

    /// The gesture path this command runs; `nil` = nothing changes on screen.
    var input: CookInput? {
        switch self {
        case .checkMyWork: .primary
        case .nextStep: .next
        case .previousStep: .previous
        case .showMe: .showMe
        case .repeatInstruction, .unknown: nil
        }
    }
}

enum VoiceCommandResponses {
    static let checkNote = "The app has shown and spoken the result. Say nothing more."

    /// "5 of 6: Close", the step the cook is on after the command ran.
    static func nowOn(stepIdx: Int, total: Int, title: String) -> String {
        "\(stepIdx) of \(total): \(title)"
    }

    /// The tool response from the contract's table. `nowOn` is read *after* the command ran;
    /// `instruction` is the current step's full instruction.
    ///
    /// `check_my_work`, `next_step`, `previous_step`, `show_me` reply with `scheduling: SILENT` so
    /// the model does not talk over the app (AI-05: without it the model spoke 2 of 2 times).
    /// `repeat_instruction` replies without it: the model then reads the instruction aloud.
    static func response(for call: LiveFunctionCall, nowOn: String, instruction: String) -> LiveToolResponse {
        let command = VoiceCommand(functionName: call.name)
        let body: [String: JSONValue]
        let silent: Bool
        switch command {
        case .checkMyWork:
            body = ["status": .string("done"), "note": .string(checkNote)]
            silent = true
        case .nextStep, .previousStep:
            body = ["status": .string("done"), "now_on": .string(nowOn)]
            silent = true
        case .showMe:
            body = ["status": .string("done")]
            silent = true
        case .repeatInstruction:
            body = ["instruction": .string(instruction)]
            silent = false
        case .unknown(let name):
            // Never leave a call unanswered: the model stalls waiting for it.
            body = ["error": .string("Unknown function \(name)")]
            silent = true
        }
        return LiveToolResponse(id: call.id, name: call.name, response: body, silent: silent)
    }
}
