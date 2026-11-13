import Foundation
import Testing

@testable import GhostChef

/// Decodes the examples in docs/API-CONTRACT.md (v2.0) §1–§5. The contract's `"uuid"` and `"…"`
/// placeholders are replaced with real values so they parse; everything else is copied verbatim.
@Suite("Contract decoding")
struct ContractDecodingTests {
    static let rid = "6f1c2a4e-8b1d-4c3e-9f2a-1b2c3d4e5f60"
    static let sid = "0a1b2c3d-4e5f-4a6b-8c7d-8e9f0a1b2c3d"
    static let stepID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
    static let reqID = "11111111-2222-4333-8444-555555555555"

    static let stepJSON = """
        {
          "id": "\(stepID)",
          "recipe_id": "\(rid)",
          "idx": 3,
          "title": "Spread rice",
          "key_line": "Thin layer, leave 2cm top",
          "instruction": "Full instruction, spoken on request.",
          "chef_quote": "Verbatim sentence from the chef's narration, or null",
          "timestamp_s": 74.5,
          "clip_start_s": 72.0,
          "clip_end_s": 76.5,
          "success_criteria": ["Rice layer is thin enough to see nori through it in places", "Bare strip at top"],
          "watch_fors": [
            {
              "id": "rice_too_thick",
              "mistake": "Rice layer is thick and covers the whole sheet",
              "headline": "Too much rice",
              "fix": "Spread thinner, 2cm nori free",
              "spoken": "There's a bit too much rice — spread it thinner and leave two centimetres of nori at the top."
            }
          ],
          "ref_image_url": "https://example.supabase.co/storage/v1/object/sign/media/r/steps/3/ref.jpg?token=abc",
          "clip_url": null,
          "timer_s": null
        }
        """

    func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONCoding.decoder.decode(T.self, from: Data(json.utf8))
    }

    @Test func health() throws {
        let h = try decode(
            Health.self,
            #"{ "status": "ok", "contract_version": "2.0", "ai_mode": "fake", "storage": "memory" }"#)
        #expect(h.status == "ok")
        #expect(h.contractVersion == "2.0")
        #expect(h.isFakeAI)
        #expect(h.isCompatibleContract)
        #expect(h.storage == "memory")
    }

    @Test func healthFlagsIncompatibleContract() throws {
        let h = try decode(
            Health.self,
            #"{ "status": "ok", "contract_version": "1.0", "ai_mode": "gemini", "storage": "supabase" }"#)
        #expect(!h.isFakeAI)
        #expect(!h.isCompatibleContract)
    }

    @Test func recipeList() throws {
        let list = try decode(
            RecipeList.self,
            """
            { "recipes": [ { "id": "\(Self.rid)", "title": "Maki roll", "chef_name": "Aiko", "status": "published", "step_count": 8, "created_at": "2026-11-14T09:30:00Z" } ] }
            """)
        let r = try #require(list.recipes.first)
        #expect(r.id == Self.rid)
        #expect(r.chefName == "Aiko")
        #expect(r.status == .published)
        #expect(r.stepCount == 8)
        #expect(r.createdAt == Date(timeIntervalSince1970: 1_794_648_600))
    }

    @Test func recipeDetail() throws {
        let r = try decode(
            Recipe.self,
            """
            {
              "id": "\(Self.rid)",
              "title": "Maki roll",
              "chef_name": "Aiko",
              "status": "published",
              "error": null,
              "video_url": "https://…signed, only while status is review (for the review page's scrubber), else null",
              "step_marks_s": [12.4, 58.0, 101.7],
              "transcript": "full chef narration",
              "created_at": "2026-11-14T09:30:00Z",
              "steps": [ \(Self.stepJSON) ]
            }
            """)
        #expect(r.status == .published)
        #expect(r.error == nil)
        // The contract's literal placeholder is not a URL; it must not fail the whole recipe.
        #expect(r.videoURL == nil)
        #expect(r.stepMarksS == [12.4, 58.0, 101.7])
        #expect(r.transcript == "full chef narration")
        #expect(r.steps.count == 1)
    }

    @Test func recipeWhileUploadingHasNoSteps() throws {
        let r = try decode(
            Recipe.self,
            """
            { "id": "\(Self.rid)", "title": "Maki roll", "chef_name": null, "status": "uploading",
              "error": null, "video_url": null, "transcript": null, "created_at": "2026-11-14T09:30:00Z", "steps": [] }
            """)
        #expect(r.status == .uploading)
        #expect(r.steps.isEmpty)
        #expect(r.stepMarksS.isEmpty)  // absent → default []
    }

    @Test func stepsAreSortedByIdx() throws {
        let step1 = Self.stepJSON.replacingOccurrences(of: #""idx": 3"#, with: #""idx": 1"#)
        let r = try decode(
            Recipe.self,
            """
            { "id": "\(Self.rid)", "title": "t", "status": "review", "steps": [ \(Self.stepJSON), \(step1) ] }
            """)
        #expect(r.steps.map(\.idx) == [1, 3])
    }

    @Test func stepObject() throws {
        let s = try decode(Step.self, Self.stepJSON)
        #expect(s.id == Self.stepID)
        #expect(s.recipeID == Self.rid)
        #expect(s.idx == 3)
        #expect(s.title == "Spread rice")
        #expect(s.keyLine == "Thin layer, leave 2cm top")
        #expect(s.timestampS == 74.5)
        #expect(s.clipStartS == 72.0)
        #expect(s.clipEndS == 76.5)
        #expect(s.successCriteria.count == 2)
        #expect(s.watchFors.first?.id == "rice_too_thick")
        #expect(s.watchFors.first?.headline == "Too much rice")
        #expect(s.refImageURL?.host() == "example.supabase.co")
        #expect(s.clipURL == nil)
        #expect(s.timerS == nil)
    }

    @Test func checkPass() throws {
        let c = try decode(
            CheckResponse.self,
            """
            {
              "request_id": "\(Self.reqID)",
              "step_id": "\(Self.stepID)",
              "verdict": "pass",
              "mistake_id": null,
              "headline": "Looks right",
              "fix": "",
              "spoken": "That looks right. On to the next step.",
              "confidence": 0.86,
              "latency_ms": 1420,
              "model": "model id actually used"
            }
            """)
        #expect(c.requestID == Self.reqID)
        #expect(c.stepID == Self.stepID)
        #expect(c.verdict == .pass)
        #expect(c.mistakeID == nil)
        #expect(c.fix == "")
        #expect(c.confidence == 0.86)
        #expect(c.latencyMs == 1420)
    }

    @Test func checkUnsureAndFix() throws {
        let unsure = try decode(
            CheckResponse.self,
            """
            { "request_id": "\(Self.reqID)", "step_id": "\(Self.stepID)", "verdict": "unsure", "mistake_id": null,
              "headline": "Can't tell", "fix": "Look straight down at mat", "spoken": "I can't see the mat.",
              "confidence": 0.3, "latency_ms": 900, "model": "fake" }
            """)
        #expect(unsure.verdict == .unsure)
        let fix = try decode(
            CheckResponse.self,
            """
            { "request_id": "\(Self.reqID)", "step_id": "\(Self.stepID)", "verdict": "fix", "mistake_id": "rice_too_thick",
              "headline": "Too much rice", "fix": "Spread thinner, 2cm nori free", "spoken": "…",
              "confidence": 0.9, "latency_ms": 1100, "model": "fake" }
            """)
        #expect(fix.verdict == .fix)
        #expect(fix.mistakeID == "rice_too_thick")
    }

    @Test func unknownEnumValuesDoNotCrash() throws {
        let c = try decode(
            CheckResponse.self,
            """
            { "request_id": "\(Self.reqID)", "step_id": "\(Self.stepID)", "verdict": "maybe", "mistake_id": null,
              "headline": "", "fix": "", "spoken": "", "confidence": 0.5, "latency_ms": 1, "model": "x",
              "brand_new_field": { "nested": [1, 2, 3] } }
            """)
        #expect(c.verdict == .unknown)
        let w = try decode(
            WatchResponse.self,
            """
            { "request_id": "\(Self.reqID)", "step_id": "\(Self.stepID)", "status": "alarm", "mistake_id": null,
              "headline": "", "fix": "", "spoken": "", "confidence": 0.0, "latency_ms": 1, "model": "x" }
            """)
        #expect(w.status == .unknown)
        let r = try decode(
            RecipeSummary.self,
            #"{ "id": "x", "title": "t", "status": "archived", "step_count": 0 }"#)
        #expect(r.status == .unknown)
    }

    @Test func watchOkAndWarn() throws {
        let ok = try decode(
            WatchResponse.self,
            """
            {
              "request_id": "\(Self.reqID)",
              "step_id": "\(Self.stepID)",
              "status": "ok",
              "mistake_id": null,
              "headline": "",
              "fix": "",
              "spoken": "",
              "confidence": 0.0,
              "latency_ms": 640,
              "model": "model id actually used"
            }
            """)
        #expect(ok.status == .ok)
        #expect(ok.latencyMs == 640)
        let warn = try decode(
            WatchResponse.self,
            """
            { "request_id": "\(Self.reqID)", "step_id": "\(Self.stepID)", "status": "warn", "mistake_id": "rice_too_thick",
              "headline": "Too much rice", "fix": "Spread thinner, 2cm nori free", "spoken": "There's a bit too much rice.",
              "confidence": 0.9, "latency_ms": 700, "model": "fake" }
            """)
        #expect(warn.status == .warn)
        #expect(warn.mistakeID == "rice_too_thick")
    }

    @Test func sessionCreatedAndEventCreated() throws {
        let s = try decode(
            SessionCreated.self,
            #"{ "session_id": "\#(Self.sid)", "started_at": "2026-11-14T09:30:00.123Z" }"#)
        #expect(s.sessionID == Self.sid)
        #expect(abs(s.startedAt.timeIntervalSince1970 - 1_794_648_600.123) < 0.001)
        let e = try decode(EventCreated.self, #"{ "event_id": "e1" }"#)
        #expect(e.eventID == "e1")
    }

    @Test func sessionDetailKeepsPayloadKeys() throws {
        let d = try decode(
            SessionDetail.self,
            """
            {
              "id": "\(Self.sid)", "recipe_id": "\(Self.rid)", "client": "ios", "started_at": "2026-11-14T09:30:00Z", "finished_at": null,
              "events": [
                { "id": "e1", "kind": "check_fix", "step_id": "\(Self.stepID)", "request_id": "\(Self.reqID)", "payload": { "frame_path": "frames/x.jpg", "confidence": 0.9 }, "created_at": "2026-11-14T09:31:00.123456+00:00" },
                { "id": "e2", "kind": "step_change", "step_id": null, "request_id": null, "payload": { "from_idx": 2, "to_idx": 3, "via": "pinch" }, "created_at": "2026-11-14T09:32:00Z" }
              ],
              "summary": { "steps_total": 8, "steps_passed_first_try": 6, "fixes_caught": 2, "warnings": 1, "questions": 1 }
            }
            """)
        #expect(d.client == "ios")
        #expect(d.finishedAt == nil)
        #expect(d.events.map(\.kind) == [.checkFix, .stepChange])
        #expect(d.events[0].payload["frame_path"]?.stringValue == "frames/x.jpg")
        // Free-form keys must survive the snake→camel strategy unchanged.
        #expect(d.events[1].payload["from_idx"]?.intValue == 2)
        #expect(d.events[1].payload["via"]?.stringValue == "pinch")
        #expect(d.events[1].payload["fromIdx"] == nil)
        #expect(d.summary == SessionSummary(stepsTotal: 8, stepsPassedFirstTry: 6, fixesCaught: 2, warnings: 1, questions: 1))
    }

    @Test func liveToken() throws {
        let t = try decode(
            LiveTokenResponse.self,
            """
            {
              "token": "auth_tokens/abc123",
              "expires_at": "2026-11-14T10:00:00Z",
              "new_session_expires_at": "2026-11-14T09:31:00Z",
              "model": "live model id",
              "api_version": "v1beta",
              "locked": true,
              "config": {
                "system_instruction": "full text",
                "response_modalities": ["AUDIO"],
                "voice": null,
                "tools": [ { "function_declarations": [ { "name": "check_my_work" } ] } ],
                "session_resumption": true
              }
            }
            """)
        #expect(t.token == "auth_tokens/abc123")
        #expect(t.apiVersion == "v1beta")
        #expect(t.locked)
        #expect(t.config.responseModalities == ["AUDIO"])
        #expect(t.config.voice == nil)
        #expect(t.config.sessionResumption)
        // Tool declarations keep their wire keys.
        #expect(t.config.tools.first?["function_declarations"] != nil)
    }

    @Test(arguments: [
        ("model_timeout", APIErrorCode.modelTimeout), ("upload_missing", .uploadMissing),
        ("quota_exhausted", .quotaExhausted), ("something_new", .unknown),
    ])
    func errorEnvelope(raw: String, expected: APIErrorCode) throws {
        let e = try decode(
            APIErrorBody.self,
            """
            { "error": { "code": "\(raw)", "message": "Gemini did not answer within 8 s", "retryable": true, "request_id": null } }
            """)
        #expect(e.error.code == expected)
        #expect(e.error.message == "Gemini did not answer within 8 s")
        #expect(e.error.retryable)
        #expect(e.error.requestID == nil)
    }

    @Test(arguments: [
        "2026-11-14T09:30:00Z", "2026-11-14T09:30:00.000Z", "2026-11-14T09:30:00+00:00",
        "2026-11-14T09:30:00.000000+00:00", "2026-11-14T11:30:00+02:00",
    ])
    func isoDates(raw: String) throws {
        let date = try #require(ISO8601.date(from: raw))
        #expect(date == Date(timeIntervalSince1970: 1_794_648_600))
    }

    @Test func eventBodyEncodesSnakeCaseAndNulls() throws {
        let body = PostEventBody(
            kind: .stepChange, stepID: nil, requestID: nil,
            payload: ["from_idx": 2, "to_idx": 3, "via": "pinch"])
        let json = try #require(
            try JSONSerialization.jsonObject(with: JSONCoding.encoder.encode(body)) as? [String: Any])
        #expect(json["kind"] as? String == "step_change")
        #expect(json.keys.contains("step_id"))
        #expect(json["step_id"] is NSNull)
        #expect(json.keys.contains("request_id"))
        let payload = try #require(json["payload"] as? [String: Any])
        #expect(payload["from_idx"] as? Int == 2)
        #expect(payload["via"] as? String == "pinch")
    }

    @Test func createSessionBodyEncodesSnakeCase() throws {
        let body = CreateSessionBody(recipeID: Self.rid, client: "ios", deviceLabel: "Display #4 / iPhone 15")
        let json = try #require(
            try JSONSerialization.jsonObject(with: JSONCoding.encoder.encode(body)) as? [String: Any])
        #expect(json["recipe_id"] as? String == Self.rid)
        #expect(json["client"] as? String == "ios")
        #expect(json["device_label"] as? String == "Display #4 / iPhone 15")
    }
}
