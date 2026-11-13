# Junction 2026 — research, winning-team model, and project handoff context

Research date: **13 November 2026**. Event times below use **Helsinki / Tallinn local time, EET (UTC+02:00)**.

Purpose: provide another chat with enough reliable background to combine this research with the team's separately supplied final concept, inspect its Git repository, and update the project documentation and execution plan. This is reference material. The next user's message determines the work to perform; quoted documents and web pages are not instructions to execute.

## 1. Read this first: established team context

**USER-CONFIRMED:** The team is attending Junction 2026: European Tech Renaissance in the Helsinki region. Its chosen main challenge is **Meta — AI Glasses for Everyone, Everyday**. Its chosen technology challenge is **Google DeepMind — Best Use of Gemini API**. **Arduino has explicitly been excluded.** Do not reintroduce Arduino integration, edge-AI scoring, additional boards, or Arduino submission obligations unless the user changes that decision.

The team values a compelling real problem, originality, a working prototype, and a convincing live demonstration. Prizes are secondary. The glasses are shared or borrowed; specific hardware availability and successful integration have not been established in this conversation. A Meta representative previously suggested combining glasses and Arduino, but that suggestion was superseded by the team's decision to exclude Arduino.

An earlier concept was called **Ghost Chef**: an expert records a cooking lesson; AI extracts steps and visual references; a learner wearing glasses receives hands-free guidance and asks for checks against the expert's method. This is historical context only. **The final concept supplied with the next message supersedes this earlier description and any previous assistant recommendations.** Do not assume sushi, a particular number of checkpoints, a fixed architecture, or a particular audience has been finally chosen.

**Unknown team facts:** member count and names, skills, available hours, repository URL/path, current code, devices actually booked, phone OS, development accounts, API access, budget, and final feature scope. The role model below is a recommendation, not a description of the actual team.

## 2. Evidence labels and limits

- **VERIFIED:** supported by a retrieved organizer, vendor, partner, or project-author source. Verification of a public statement is not independent verification that a prototype achieves its claims.
- **USER-CONFIRMED:** provided by the team in this conversation. Keep this label when a public copy was not independently retrieved.
- **ANALYSIS / RECOMMENDATION:** conclusions and proposed practices based on the evidence. These are not official judging criteria or promises of winning.
- **OPEN:** unresolved, conflicting, inaccessible, or dependent on a real test.

The research covers accessible public sources and the team's supplied challenge briefs. It is not a live view of the venue, private participant channels, mentor availability, hardware bookings, submitted competing projects, or the authenticated submission form. Public pages still contain stale promotional language. There is no complete public judge scorecard explaining the causal reasons every historical project won.

Historical coverage prioritizes the **Finland main event**. Junction Asia and JunctionX events have different rules; their rules must not be imported into Junction 2026 Finland. An organizer interview with a team that won both Asia and Finland is useful evidence about the team's practices, but its event-specific anecdotes still need attribution.

## 3. Event situation and deadlines

### 3.1 Confirmed event skeleton

**VERIFIED:** Junction 2026 runs **13–15 November 2026** at **Hype Areena, Espoo**, in the Helsinki region. The event platform lists teams of **1–4**. This differs from the five-person limit appearing in some 2025 materials. Use the 2026 limit, and confirm any exception with organizers. [Junction 2026 event platform](https://hackjunction.app/hackathons/junction-2026)

Advertised scale: **2,000 builders, 100+ countries, €100,000 total prizes**. These are promotional figures, not verified attendance or the main-prize amount. [Official event site](https://2026.hackjunction.com/)

### 3.2 Published schedule

| Local date/time | Published event | Source/status |
|---|---|---|
| Fri 13 Nov, 16:00 | Doors open | Event platform |
| Fri 13 Nov, 18:00 | Opening ceremony | Event platform |
| Fri 13 Nov, 19:30 | Hacking starts | Homepage |
| Fri 13 Nov, 23:55 | Preliminary submission | Event platform; conflict below |
| Sat 14 Nov, 12:00 | Submissions open | Event platform |
| Sun 15 Nov, 10:00 | Final submissions | Both public sources |
| Sun 15 Nov, 17:00 | Event ends | Event platform |
| Sun 15 Nov, 18:00 | Doors close | Event platform |

Sources: [event platform](https://hackjunction.app/hackathons/junction-2026), [homepage schedule](https://2026.hackjunction.com/).

**CONFLICT:** Preliminary deadline: homepage **23:59**, platform **23:55**. Sunday: homepage review **10:30**, ceremony **14:00**; platform review **14:00**. [Homepage](https://2026.hackjunction.com/), [platform](https://hackjunction.app/hackathons/junction-2026)

**RECOMMENDATION:** Until corrected by organizers, plan against the earlier preliminary deadline and be demo-ready before 10:30 Sunday. Use an internal preliminary target of 23:30 and a final submission target of 09:00. Those buffers are team recommendations, not event rules.

**CALCULATION:** Friday 19:30 to Sunday 10:00 is **38 hours 30 minutes**, not 48 hours of unrestricted implementation time. The advertised weekend includes opening, judging, and closing activities. Meals, sleep, borrowing hardware, setup, and demonstrations reduce usable development time further. Do not build a plan that needs 48 engineer-hours from every member.

### 3.3 Useful opportunities and practical implications

Google DeepMind workshop: Friday **20:00–20:30, Loft, fourth floor**. [Official schedule](https://2026.hackjunction.com/)

**RECOMMENDATION:** If that workshop is still upcoming, send the person responsible for Gemini integration with a short list of access, quota, model, and judging questions. Have another member handle glasses access. If it has passed, ask for materials and a mentor rather than reorganizing the whole team around missed content.

The broader event includes physical-AI experimentation. Intel's public channel carries Junction's announcement of a robot-arm-and-camera challenge with on-site support. This helps explain the wider event environment; it does not create a reason to expand this team's scope. [Intel channel carrying Junction's announcement](https://lb.linkedin.com/showcase/intel-software)

A public Meta representative profile carries Junction's announcement emphasizing hands-free, first-person everyday experiences across display and displayless devices. This independently supports the broad direction of the team's Meta brief, but not every logistical detail in it. [Meta representative sharing the Junction announcement](https://se.linkedin.com/in/janneelvelid)

Spend mentor time on facts that can change the build: device access, permitted interfaces, misunderstood criteria, submission requirements, and specific user problems. A workshop or conversation should resolve an uncertainty or produce a concrete next step.

### 3.4 Rules that require care

The FAQ states team ownership and **MIT-licensed submissions**. [Official FAQ](https://2026.hackjunction.com/)

**OPEN:** The linked terms page returned no readable body during this research. The authenticated participant guide and submission fields were not inspected. Consequently, this report does not certify the complete rules for pre-existing code, permitted preparation, AI-use disclosures, repository visibility, external assets, code-freeze timing, video length, pitch duration, or late edits. [Terms page checked](https://www.hackjunction.com/terms-and-conditions)

**RECOMMENDATION:** Check the accepted participant terms before changing an existing repository license or publishing media. Keep third-party licenses and instructor/media permissions distinct from your own source-code license. Record which components were pre-existing, which were created during the event, and which results are live or replayed. Do not assume a submission video or a public repository is mandatory merely because another hackathon required one.

## 4. How judging works, and what that changes

**VERIFIED:** Partner winners are selected by the partners. Face-to-face peer review selects five overall finalists; a live pitch and grand jury determine the overall winner. [Official judging description](https://2026.hackjunction.com/)

Treat these as different audiences, not one interchangeable evaluation:

| Audience | What your evidence should make easy to assess | Recommended proof |
|---|---|---|
| Meta challenge judges | Whether the wearer's perspective creates meaningful everyday value, and whether the experience works responsibly | Actual glasses interaction, user benefit, graceful failure, clear pilot |
| Gemini technology judges | What Gemini makes possible and what your team engineered around it | Real multimodal inputs, structured decisions, grounding, evaluation, demonstrated effect of the integration |
| Peer reviewers | What the project does, why it matters, and what is impressive about it | A short explanation and repeatable demonstration visible to someone not wearing the glasses |
| Overall grand jury | Why this particular project deserves attention beyond its track | A distinctive insight, working proof, honest limits, and a plausible next deployment |

This table is **ANALYSIS**, not an extra official rubric. Winning a partner challenge must not be assumed to automatically qualify a team for the overall final.

### 4.1 Public jury signals

Jury: **Kia Kanninen, Daksh Raghuvanshi, Otto Söderlund, Timo Ahopelto, Umar Noor, Hubertus van der Drift, Arturs Polis**. Published priorities include meaningful problems (Kanninen), failure evaluation (Raghuvanshi), repeat use (Söderlund), pragmatic insight (van der Drift), and production feasibility (Polis). [Official jury profiles](https://2026.hackjunction.com/)

**ANALYSIS:** Prepare for four kinds of questions: “Does anyone need it?”, “Does it actually work?”, “What is the distinctive insight?”, and “What happens after Sunday?” This is a preparation model, not a claim that each judge has a secret scoring formula. Do not invent personal preferences from employers or tailor unsupported claims to individual judges.

## 5. Selected challenges: preserve this context accurately

The detailed requirements in this section are **USER-CONFIRMED from the supplied briefs**. A complete public copy of these exact challenge pages was not retrieved. Reconfirm against the live platform before final submission.

### 5.1 Meta — main challenge

Title: **AI Glasses for Everyone, Everyday**.

The functional prototype should show how first-person field of view makes an everyday interaction possible or meaningfully better. Mirroring a phone screen is insufficient. Audio-first and display experiences are judged equally. Web apps and mobile integrations through Meta's Device Access Toolkit are accepted.

Submission requirements reported by the team: working prototype, deck, clear intended audience, and a plausible adoption or pilot path. The brief emphasizes accessibility, consent, responsible handling of data, and behavior when permissions, connectivity, or device state change.

Four equally weighted dimensions:

| Criterion | Weight | Evidence to prepare — recommendation |
|---|---:|---|
| Creativity and use case | 25% | The specific interaction that first-person perspective improves; comparison with the ordinary alternative |
| Technical execution | 25% | A working device-to-model-to-feedback loop, architecture, measured latency, and tested recovery |
| Real-world value and feasibility | 25% | A narrow audience, a real task, credible feedback from users, and a reachable pilot |
| UX, accessibility, and trust | 25% | Minimal interaction burden, useful uncertainty, consent, appropriate alternatives, and clear status |

Resources reported: ten shared Ray-Ban Meta Display pairs and ten shared Ray-Ban Meta Gen 2 pairs; on-site developer support. **Amanda Le** is the supplied challenge contact and Android DAT mentor. A specific pair has not been confirmed for this team.

Reported prize: a pair of Ray-Ban Meta glasses per winning team member. Strong submissions may receive an invitation to Meta's AI forum on **18 November 2026**. An invitation is a possibility, not an entitlement.

### 5.2 Google DeepMind — technology challenge

Title: **Best Use of Gemini API**.

The supplied brief asks teams to explain the problem, the integration, what is innovative or technically impressive, and why Gemini matters. An otherwise complete product with a superficial chatbot added is a weak fit.

Credits are reportedly available to up to 400 participating teams, with event access instructions. Participation and Google-provided account access are restricted to people 18 or older. Receipt of credits has not been established for this team.

Reported prizes: first place €4,000 plus $1,000 Google Cloud credits per team member; second €2,000; third €1,000. Do not let prize values dictate unnecessary architecture.

**RECOMMENDATION:** Show the actual chain from input to decision to user consequence. Preserve a small evaluation set, a clear data contract, and evidence of what fails without the relevant reference/context. A model does not need to be claimed uniquely capable among all vendors; it needs to be integral to this project and used thoughtfully.

### 5.3 Challenge selection

The team reports the rule as one main challenge plus multiple technology challenges. Its current selection is **Meta + Gemini only**. Arduino's separate main challenge and its UNO Q technology challenge are both outside this project. The user has already resolved this choice; future chats should not reopen it by default.

## 6. Technical context that can change feasibility

### 6.1 Meta capabilities: current documentation versus real access

Meta's public FAQ describes native DAT integrations across display and displayless glasses and a separate web-app route for Display. It also notes capability differences by device, country availability, and use of the Meta AI app for pairing. Public documentation is evidence of a supported route, not evidence of this team's account or borrowed-device readiness. [Meta developer FAQ](https://developers.meta.com/wearables/faq/)

The Android changelog includes a display module with text, images, and other UI components, plus API and lifecycle changes across releases. Therefore, old advice that third-party display output is categorically unavailable should not guide this build. Pin a tested version and follow its matching sample. [Meta Android changelog](https://github.com/meta/meta-wearables-dat-android/blob/main/CHANGELOG.md)

The official camera sample describes streaming, photos, recording, optional sound-in-video, and explicit session handling. [CameraAccess sample](https://github.com/meta/meta-wearables-dat-android/blob/main/samples/CameraAccess/README.md)

**RECOMMENDED first integration proof:** connect the actual pair; obtain permission; capture a usable first-person image; process it; return a short response through the glasses; receive a wearer request; repeat. If Display is available, test an image card in the same required operating flow. Do not infer simultaneous camera, microphone, speaker, and display behavior from separate successful samples.

Record actual phone, OS, glasses model, firmware, SDK version, account setup, permission steps, tested functions, and remaining failures. Test whether looking down produces the intended work-surface framing; a camera mounted near the eyes does not guarantee every hand action is in frame.

Web-app acceptance by the challenge is not proof of API parity with native DAT. Ask the mentor to confirm the exact route before committing to camera-dependent functionality. Likewise, camera perspective is not eye tracking or measured gaze. Historical Pixieray eye-tracking examples do not establish Ray-Ban capabilities.

Audio should provide a coherent experience if the selected use case allows it. Display can support quick reference and accessibility without becoming a dependency that prevents demonstration on another available pair. The best fallback depends on the final concept and must be tested, not just described.

### 6.2 Gemini: use the model for the hard judgment, control the surrounding application

Gemini documentation supports video understanding, timestamp-based references, image understanding, structured outputs, and a Live API for real-time voice/vision interaction. These are building blocks, not evidence of reliable task-specific performance. [Video understanding](https://ai.google.dev/gemini-api/docs/video-understanding), [image understanding](https://ai.google.dev/gemini-api/docs/image-understanding), [structured outputs](https://ai.google.dev/gemini-api/docs/structured-output), [Live API](https://ai.google.dev/gemini-api/docs/live)

**RECOMMENDATION:** Choose the smallest integration that proves the final concept. A capture-on-request pipeline may be easier to evaluate than continuous streaming. Live conversation may be justified when interruption and natural dialogue are central. Measure the complete interaction before choosing; do not equate more APIs with better execution.

For a visual coaching application, useful result fields might include current step, observation, evidence references, assessment, one correction, and a reason for uncertainty. Validate the returned structure. Keep session transitions, permissions, request cancellation, and stale-result rejection in ordinary application logic. A syntactically valid result is not a correct visual judgment.

Rate limits vary by model and project/account tier and are applied at the project level rather than independently to every key. Credits do not establish the available throughput. Check the actual project's limits in AI Studio. [Gemini rate-limit documentation](https://ai.google.dev/gemini-api/docs/rate-limits)

Make a bounded timeout and retry plan. Avoid several overlapping checks on the same user action. Capture latency and failure counts. Keep keys outside public client code and the repository. Document data retention and account settings rather than assuming a particular privacy policy applies to every credit arrangement.

Do not choose a model identifier from this report: exact availability, pricing, limits, and supported features need checking in the team's account at implementation time. Record the identifier and configuration actually tested.

## 7. Previous winners: what is known and what can reasonably be learned

These are selected evidence-backed cases, not an exhaustive list of every award. Statements about what made a project special are distinguished from documented winner status and participant recollections. No public source here proves that a single trait caused victory.

### 7.1 WAVELET — 2025 overall winner and Sensofusion Radio City winner

**Evidence:** Sensofusion's Mikko Hypponen identifies WAVELET as both its radio-challenge winner and the overall winner. The project's public repository describes a C++/OpenGL electromagnetic-wave simulation using Maxwell equations, GPU compute shaders, interactive controls, and a Hong Kong scene. These are the authors' implementation claims, not independently reproduced physics results. [Sponsor account](https://www.linkedin.com/posts/hypponen_we-at-sensofusion-had-an-excellent-time-at-activity-7396199187996045312-QXf6), [WAVELET repository](https://github.com/ron0studios/WAVELET)

**What distinguished it — analysis:** The technical work had an immediately visible effect: invisible wave propagation became something an audience could explore. The visual output exposed the engine's behavior rather than merely decorating it. Its complexity aligned with the challenge.

**Transfer to this team:** Show a meaningful transformation of real input and make that transformation visible to reviewers. Spend complexity on the central capability. This example does not justify dropping Gemini from a Gemini entry, nor does it imply every winner needs difficult graphics or physical simulation.

### 7.2 BREAKDANCE / Frank Sandqvist — 2024 overall winner

**Evidence:** A KONE partner account names BREAKDANCE as the grand-prize winner. Junction's profile of Frank Sandqvist describes his solo 2024 entry as AI-assisted inventory management with gamified equipment reporting. It reports that he thought an AI-generated rap presentation may have helped. The same profile recommends working to strengths, choosing an exciting idea, and presenting a clean, credible product engagingly. [KONE partner account](https://www.linkedin.com/posts/shahram-heidari-96b35_junction2024-kone-granlund-activity-7261440179553370112-3Kj-), [Junction's Sandqvist profile](https://www.hackjunction.com/blog/frank-sandqvist-story)

**What distinguished it — analysis:** A practical workflow received a participation mechanism and a memorable presentation. The rap's causal importance is the winner's interpretation, not a published jury finding.

**Transfer:** Give the audience one memorable event that demonstrates the product. A performance or joke is optional; a clear relationship between the presentation and the working feature matters more. Solo victory is not evidence that a team should avoid collaboration.

The same organizer profile reports **LoreDash as 2025 overall runner-up**, turning Wikipedia articles into AI-assisted minigames. Treat that as further evidence that playful interactions can communicate value; it is not the 2025 overall winner. [Same organizer profile](https://www.hackjunction.com/blog/frank-sandqvist-story)

### 7.3 Driving Change — 2023 overall winner

**Evidence:** The main-prize partner Maki.vc and a Pixieray representative congratulate Driving Change on the overall win. A team member's public profile describes using eye/head movement for a driver-fatigue concept, with GPS supporting review of driving performance. [Main-prize partner](https://www.linkedin.com/posts/maki-vc_we-were-proud-to-be-the-partner-of-this-years-activity-7131199696131280896-f7nl), [Pixieray representative](https://www.linkedin.com/posts/hlehmuskallio_junction2023-junction-hackathon-activity-7130137689604902913-EawU), [team member account](https://www.linkedin.com/in/markus-andersson-1a77a1196)

**What distinguished it — analysis:** It connected the challenge's unusual sensor input to a recognizable consequence and an understandable feedback loop. This is a useful example of starting from what a device can observe uniquely.

**Transfer:** Make the reason for glasses explicit in the actual interaction. Do not borrow claims about driving safety, fatigue accuracy, or eye tracking: these sources do not establish validated prevention outcomes, and the devices differ from this team's.

### 7.4 Haru / Bitter Sweet — 2022 overall winner, with additional awards

**Evidence:** Junction confirms Bitter Sweet's overall, track, and challenge wins. A member describes Haru as a diary application generating an illustration from a user's daily story, intended to encourage journaling. The account reports GPT-3, Stable Diffusion, and Google Cloud use, and a Google Cloud side-challenge win. [Organizer announcement](https://fi.linkedin.com/posts/hackjunction_junction-2022-winners-activity-6997906878580076544-iVyf), [team account](https://www.linkedin.com/posts/kshgroup_we-won-at-junction-2022-activity-6995318216663216128-AoGW)

**Firsthand team practices:** In an organizer interview, members emphasize trust that permits direct criticism and flexibility to abandon an unmotivating idea. The interview discusses a team that won both Asia and Finland, so those recollections should not all be assigned to the Finland build. [Organizer interview](https://medium.com/%40junctionasia_2023/we-are-the-winner-of-junction-fd91c3aa475b)

**What distinguished it — analysis:** AI produced an immediate, personal reward connected to the desired behavior. Multiple technologies served one coherent experience.

**Transfer:** Connect model output to an action or payoff the user cares about. For coaching, a useful correction and successful retry are stronger evidence than a long fluent explanation. Do not infer measured mental-health benefits from a hackathon award.

### 7.5 Nice-ify / Bryce Cronin — 2021 overall winner, second in its challenge

**Evidence:** Junction's interview says Cronin researched existing approaches, noticed their emphasis on text rather than voice, chose an idea within roughly two hours, and built a focused implementation. He combined development with UI, design, and presentation work. The challenge partner confirms that Nice-ify placed second in its challenge but won overall. [Junction interview](https://hackjunction.medium.com/replacing-hateful-language-with-a-nice-ified-alternative-interview-with-bryce-cronin-399238426bf), [challenge-partner recap](https://vikes.fi/uutiset/empatiaa-pelaamiseen-junction-tuotti-22-ratkaisuehdotusta-ja-osoitti-etta-empatiassa-on-voimaa)

**What distinguished it — analysis:** A specific gap in the interaction medium made a familiar problem feel newly actionable. The implementation was focused enough to communicate quickly.

**Transfer:** Research what generic visual assistants already do. Identify the exact missing interaction, then demonstrate it. This case also illustrates that partner and overall rankings can diverge; it does not prove that 2021 judging mechanics are identical to 2026.

### 7.6 Sonaptics — reported 2024 second place; relevant hands-free case

**Evidence:** The participants' employer reports second place among approximately 200 teams. Sonaptics addressed communication in an HK Foods factory where hygiene and protective equipment constrained interaction. The account attributes the team's execution to complementary roles and describes gesture input, hardware integration, a responsive interface, and real-time communication. A partner conversation clarified the real need. Integration occurred late and was stressful. [Participant-employer retrospective](https://www.taitounited.fi/blog/menestyst%C3%A4-junction-hackathonista/)

**What distinguished it — analysis:** Hands-free interaction followed from a concrete environmental constraint. Hardware had a necessary role, and the team made its effect understandable through the interface.

**Transfer:** Explain the exact moment when ordinary touch interaction breaks down. Use sponsor conversations to understand constraints. Learn from the late-integration risk rather than copying it. This historical case does not reverse the team's decision to exclude Arduino.

### 7.7 What the evidence does not support

There is no demonstrated universal formula such as “hardware wins,” “the most complex code wins,” “add more sponsors,” or “make the biggest social-impact claim.” The cases vary widely. Selection bias matters: public winner stories reveal little about equally strong losing teams or unpublished judging discussions.

A source calling a project a “Junction winner” may mean a track prize. For example, a DroneStalker creator page describes a top-five finish; the overall 2025 award is separately attributed to WAVELET by the sponsor. Keep award levels explicit. [DroneStalker creator page](https://codya.dev/project/2511-junction), [overall-winner confirmation](https://www.linkedin.com/posts/hypponen_we-at-sensofusion-had-an-excellent-time-at-activity-7396199187996045312-QXf6)

## 8. Synthesis: the competitive model to use

The following is **ANALYSIS**, not an official formula:

**A strong submission makes a valuable and distinctive capability work, makes its operation understandable, and supplies enough evidence to believe it.**

Five useful dimensions:

1. **Problem precision:** a named person, a concrete moment, and a costly or frustrating failure of the current alternative.
2. **Distinctive mechanism:** the specific interaction or technical insight that changes the experience.
3. **Working execution:** the integrated system actually performs that interaction under the demo conditions.
4. **Evidence and boundaries:** the team can show success, acknowledge failure, and explain what it has and has not tested.
5. **Communication:** another person can understand and retell the benefit after a brief encounter.

Think of these as bottlenecks. Excellent visual design cannot compensate for an absent core capability; excellent implementation can still be overlooked if observers cannot tell what happened. This is a planning heuristic, not a statistical model or a way to calculate a winning probability.

Junction's own pitching guidance recommends a relevant story, user focus, a prototype, rehearsal, and clear answers without exaggeration. Its 2025 retrospective describes partner interest in fresh approaches and practical impact. [Organizer pitch guidance](https://hackjunction.medium.com/how-to-pitch-your-idea-at-a-hackathon-a95cd3f62f60), [2025 organizer retrospective](https://hackjunction.medium.com/48-hours-at-junction-2025-creativity-community-and-the-spirit-of-innovation-fce609acb6b6)

For Meta + Gemini, prepare four one-sentence explanations:

- What becomes better because the input comes from the wearer's perspective?
- What meaningful task does Gemini perform that the rest of the application depends on?
- What did this team implement beyond calling an API?
- What observable user outcome improves because those pieces work together?

Do not claim unique technical superiority over all competing models without evidence. The stronger claim is the concrete capability you have demonstrated with the selected stack.

## 9. A strong team operating model

This is a recommended allocation of responsibilities for up to four people. Adjust it to the actual team rather than inventing capabilities.

| Responsibility | Primary outcome | Early proof | Continuing ownership |
|---|---|---|---|
| Product, users, and story | One coherent user problem and demonstration | A person outside the team understands the use case and its current alternative | Scope decisions, mentor questions, pilot, deck, submission |
| Glasses and client integration | Reliable wearer interaction | Actual device capture and returned feedback | Pairing, audio/display, permissions, reconnect, device readiness |
| Gemini and backend | Task-specific reasoning with controlled inputs/outputs | A real request succeeds on representative data | Grounding, schemas, timing, quota handling, evaluation |
| UX, evaluation, and demo operations | A usable and observable experience | A novice can complete the core interaction | Reference/monitor UI, test cases, recordings, rehearsal, reset procedure |

Each work area needs one owner and one named backup. One person can own multiple areas. With three people, combine product/story with UX and evaluation. With two, combine glasses/client/UX and model/backend; explicitly share product interviews and submission duties. Do not leave presentation and submission as work that “someone will do later.”

### 9.1 Decision discipline

- Agree on the core demonstration in plain language before building separate components.
- Write down the highest-risk assumption and test it first. For this team it may be device integration, not the model prompt.
- Let technical owners choose reversible implementation details. Have a clear scope owner settle feature disputes after a short evidence-based discussion.
- Discuss an idea's weaknesses without treating criticism as criticism of the person proposing it.
- Change scope when a failed test invalidates the plan; avoid unbounded brainstorming after a viable core is established.
- Every proposed feature must explain which user benefit or judged criterion it strengthens and what existing work it would displace.
- Separate mentor advice, official rules, and team decisions in the notes. A friendly suggestion is not automatically a requirement.

### 9.2 Integration discipline

Agree early on the exchanged data: session identifier, current step/task, capture timestamp, request identifier, evidence, assessment, and user-facing response. A recorded input may help parallel development, but label it as replay and replace it with live data as soon as the device path works.

Keep a functioning integrated version available. Short-lived branches and small changes are useful when they match the repository's workflow; no particular Git branching scheme is required. The key is that integration happens repeatedly, not for the first time on Sunday morning.

Use a brief check-in every few hours: show the working interaction, identify the current bottleneck, choose the next evidence-producing task, and cut anything that threatens the deadline. Prefer showing a result over reporting a percentage complete.

Plan rest and handovers so that the person operating the final demo can think clearly. Historical reports of little sleep are descriptions, not a recommended performance strategy.

### 9.3 Working definition of done

A feature is ready for the demo when its intended path works on the relevant device, its key failure behavior is clear, another teammate can operate it, and its actual state is reflected in the documentation. A successful isolated API response is not proof that the complete wearer experience works.

## 10. Execution plan anchored to the real deadline

**RECOMMENDATION:** Rebase this plan to the time remaining when the next chat begins. If the event has progressed, do not pretend earlier milestones are still available. The final deadline must be rechecked against current organizer instructions.

| Phase | Output | Gate before adding scope |
|---|---|---|
| First 1–2 working hours | Device/account access, final use case, data contracts, risk list | An actual device input can reach the application; critical permissions and credentials are understood |
| First 4–6 working hours | One complete live interaction | Real input changes the response; the wearer receives useful feedback |
| By Saturday midday | Core user journey and initial evaluation | The central mistake/success or task transition works on several examples |
| Saturday afternoon | Improved reliability, usability, and source grounding | Another person can use it; failures are identifiable and recoverable |
| Saturday evening | Frozen essential feature set, deck draft, backup recording | Full demonstration can be repeated; no essential component exists only in a mock |
| Sunday before internal 09:00 target | Final artifacts, links, permissions, submission receipt | Every submitted link opens and every capability claim matches the build |
| After submission | Allowed rehearsals and review preparation | No unauthorized post-deadline implementation changes |

Fallback decisions should preserve the user benefit where possible. If display is unreliable and the use case works through audio, simplify to audio. If continuous streaming is fragile, consider explicit captures. If a supposed visual criterion is unobservable, replace that criterion or narrow the promise. If real glasses access cannot be obtained, a phone demonstration is a development fallback; do not silently claim it proves the Meta requirement.

## 11. Evidence, evaluation, and reliability

Create a small evidence ledger rather than a long list of aspirations:

| Claim | Evidence needed | Honest boundary |
|---|---|---|
| Hands-free during the core task | Observe or record the user completing it | Setup and occasional recovery may still need the phone |
| Grounded in an expert/reference | Identify the source frame, timestamp, or instruction supporting an answer | Advice absent from the source is an inference |
| Detects a defined mistake | Held-out correct and incorrect examples | One lesson's evaluation does not establish general cooking ability |
| Responds promptly | End-to-end timings on the actual setup | Separate typical response from slow/failing cases |
| Handles uncertainty | Obscured, ambiguous, or unsupported examples | Abstention is a deliberate outcome |
| Creates user value | A few observed sessions with the intended audience | Early observations are not population-level validation |

For a visual verification concept, measure false approval, false rejection, appropriate uncertainty, failure to answer, time to useful feedback, and successful correction after advice. Avoid reporting only an aggregate accuracy that hides confident mistakes.

Split the images or situations used to develop prompts from those used for a final check. Include correct alternatives, viewpoint changes, different hands, occlusion, lighting variation, and deliberately unsupported questions. Select a small set that can be labeled competently within the weekend.

A practical initial test might contain twenty varied cases, but the number and threshold should follow the final task. Label any target as a target. Do not write “90% accurate” into the deck before running the test; do not imply a small convenience sample establishes general reliability.

Important recovery tests include permission denial, disconnect/reconnect, unavailable network, model timeout, quota failure, repeated requests, changing steps during a pending response, and stale images. Prevent a previous frame's answer from being presented as confirmation of the current state.

Show model output in terms a user can act on. One correction should be short and specific. The application can contain detailed technical evidence for judges without forcing the wearer to hear it all.

## 12. Presentation and demonstration design

Prepare three lengths as practice formats: a one-sentence description, a roughly one-minute table explanation, and a longer stage presentation that can be shortened. These are not verified event time limits; confirm the actual allotted duration.

The demonstration should expose the cause-and-effect chain:

1. Establish who is performing which task.
2. Show the relevant real-world input.
3. Trigger the central interaction.
4. Show the system's meaningful response.
5. Show the user's resulting action or improved outcome.
6. Briefly expose one limit or recovery behavior.

Because glasses are personal, audience visibility matters. Prepare a monitor view that accurately shows the input, reference/context, and returned result. Label any reconstructed UI, recorded segment, or development replay. Keep live evidence distinguishable from slides illustrating future functionality.

A backup recording preserves evidence if venue connectivity fails; it must not be presented as a live run. Confirm permission to record the wearer and instructor, and avoid including incidental bystanders or private data.

Recommended deck content: user/problem, current alternative, key insight, working demonstration, architecture and technology roles, measured evidence and limits, pilot/adoption path, and next step. Combine these into the number of slides appropriate to the actual time slot. Do not add an elaborate market-size claim without research merely to resemble a startup pitch.

Questions to rehearse include: Why glasses? Why this model integration? Why is this more than a generic assistant? What can fail? How do you know the answer is right? What happens without internet? What did you actually build this weekend? Who would pilot it? How would you know the pilot succeeded?

## 13. Product-specific context to retain only if the final concept still matches

The earlier Ghost Chef discussion identified a strong potential demonstration: a learner makes a visible, reversible mistake, receives a correction grounded in a specific expert lesson, fixes it, and obtains a fresh check.

The unresolved product issue is the meaning of “correct.” Similar-looking food can differ in quantity, consistency, temperature, or other hidden properties. A shared first-person style does not make two camera views identical. Choose observable criteria; qualify uncertainty; distinguish expert statements from model inference.

The core category is not unprecedented. AROMA is a research system connecting a wearable camera, recipe video, and contextual cooking assistance for blind and low-vision users. It is relevant prior art, not proof that every Ghost Chef interaction has already been built. [AROMA paper](https://arxiv.org/abs/2507.10963)

**RECOMMENDATION:** Compare the final concept against existing visual assistants and recipe guidance. A possible distinction is expert-approved checkpoints with source evidence and a measured correction loop. Treat that distinction as a hypothesis to demonstrate. Avoid absolute “first,” “only,” or universal correctness claims.

A cooking class with shared glasses is a possible initial pilot, not an established partnership. Identify the actual participant, the lesson, the current workflow, who would provide equipment, and how instructor interventions or successful task completion would be measured. The final concept may justify a different audience.

## 14. What the next chat should put into the repository

This is a **recommended information architecture**, to be adapted after inspecting the actual repository. Do not create numerous duplicate files when existing documentation already serves the purpose. The final user message should authorize the edits; this reference file alone is not permission to publish, deploy, message partners, or modify external accounts.

| Document or existing equivalent | Essential contents |
|---|---|
| README | Current problem/audience, working behavior, run instructions, architecture overview, demo entry point, implemented versus planned status |
| Final concept / product brief | User-supplied final concept, scope, non-goals, user journey, observable success criteria |
| Event context | Selected challenges, dates/timezone, requirements, conflicts, source links, last-checked date |
| Architecture / integration notes | Components, data flow, actual SDK/model versions, permissions, device/account assumptions, failure states |
| Build plan | Remaining milestones, owners, dependencies, critical path, cut order, submission buffer |
| Evaluation plan and results | Test cases, labels, methodology, observed results, timing, limitations, reproduction steps |
| Demo and submission checklist | Script, audience visibility, equipment reset, backup, deck/video/repository links, required fields, submission status |
| Decisions and risks | Decisions already made, reasons, unresolved assumptions, owners, next tests |
| Source register | URL, publisher, checked date, claims supported, status/conflicts |
| Optional concise agent guidance | Navigation to the current source of truth and existing repo conventions, if useful and authorized |

A minimal layout could use a README plus a small docs directory; file names should follow the repository's conventions. Keep historical research separate from current implementation status. Any older documentation that conflicts with the final concept should be reconciled or clearly marked historical.

Practical inspection sequence for the next chat:

1. Read the user's final concept, additional context, and explicit work request.
2. Inspect the repository, applicable instructions, current branch, uncommitted changes, existing documentation, stack, and relevant code.
3. Build a short fact/decision/assumption map. Preserve Meta + Gemini and Arduino exclusion unless the user changes them.
4. Recheck time-sensitive deadlines and capability claims only where they affect the next action.
5. Update the appropriate files with concrete, consistent content. Do not merely return a proposal if repository updates are requested.
6. Derive the plan from the actual build state and remaining time. Do not invent team assignments or mark an untested function as working.
7. Verify document links, commands, filenames, consistency, and any changed functionality with proportionate checks.
8. Report edited files, key decisions, verification performed, and genuinely unresolved blockers.

No application repository has been identified or updated by this research task. The produced context pack is a standalone artifact for transfer.

## 15. High-priority unknowns to resolve on site or from the next message

| Unknown | Why it matters | Best evidence |
|---|---|---|
| Final concept and intended audience | Determines scope and appropriate evaluation | User's next message |
| Repository and current implementation | Determines what work remains | Actual checkout and project files |
| Team skills/availability | Determines realistic ownership and throughput | Team-provided information |
| Glasses allocation and access windows | Determines development and demo feasibility | Hardware desk / Meta mentor confirmation |
| Actual device integration path | Determines stack and supported interaction | Working on-device test |
| Gemini credits, models, and quota | Determines reliability and cost constraints | Team's account and Google mentor |
| Preliminary and review-time discrepancies | Avoids missed obligations | Current organizer announcement/platform |
| Required submission fields and formats | Avoids an incomplete entry | Authenticated submission form |
| Code/asset preparation and licensing rules | Determines what can be submitted/shared | Accepted 2026 terms and organizer clarification |
| Pitch duration and review logistics | Determines presentation and staffing | Organizer instructions |
| Media consent and retention | Determines what can be recorded and published | Explicit permissions and implemented settings |
| Pilot access | Determines credibility of adoption claims | A real conversation or documented commitment |

Do not ask the user to reconfirm settled choices. Resolve what the repository, accounts, or provided materials already answer; ask only for missing information that changes execution.

## 16. Source register and research confidence

All sources below were checked or surfaced during research on **13 November 2026**. Search-indexed content is distinguished from a fully readable page where relevant. Source links throughout the text support adjacent claims; this register also gives the next chat a route for refreshing them.

| Source | Type and use | Limitation |
|---|---|---|
| [Junction 2026 homepage](https://2026.hackjunction.com/) | Official; schedule, judging, jury, logistics | Schedule labeled preliminary; conflicts with platform; stale promotional sections |
| [Junction 2026 platform](https://hackjunction.app/hackathons/junction-2026) | Official; event identity, team size, deadlines | Public event page only; authenticated submission not inspected |
| [Terms and conditions](https://www.hackjunction.com/terms-and-conditions) | Official destination for rules | No readable body retrieved; not a verified rules extract |
| [Meta/Junction public announcement](https://se.linkedin.com/in/janneelvelid) | First-party sharing of organizer announcement | Public profile excerpt; not complete challenge rules |
| [Intel/Junction announcement](https://lb.linkedin.com/showcase/intel-software) | First-party channel; physical-AI event context | Broad event context only |
| Team-supplied challenge briefs and later messages | User-provided; Meta/Gemini rubric, resources, selection | Exact full challenge pages not independently retrieved |
| [Meta developer FAQ](https://developers.meta.com/wearables/faq/) | Vendor primary documentation | Capability/account/device combinations still require testing |
| [Android DAT changelog](https://github.com/meta/meta-wearables-dat-android/blob/main/CHANGELOG.md) | Vendor primary source; capabilities and version changes | Pin and check the version actually used |
| [CameraAccess sample](https://github.com/meta/meta-wearables-dat-android/blob/main/samples/CameraAccess/README.md) | Vendor primary source; camera integration | Not evidence the team's environment works |
| [Gemini video](https://ai.google.dev/gemini-api/docs/video-understanding) and [image](https://ai.google.dev/gemini-api/docs/image-understanding) documentation | Vendor primary source; multimodal capabilities | Task performance must be measured |
| [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output), [Live API](https://ai.google.dev/gemini-api/docs/live), and [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) | Vendor primary source; integration and constraints | Account-specific availability and limits may differ |
| [Sensofusion 2025 recap](https://www.linkedin.com/posts/hypponen_we-at-sensofusion-had-an-excellent-time-at-activity-7396199187996045312-QXf6) | Sponsor; WAVELET award confirmation | Does not publish a full comparative scorecard |
| [WAVELET](https://github.com/ron0studios/WAVELET) | Project authors; implementation description | Public repository description reviewed; no build or independent physics validation |
| [KONE 2024 recap](https://www.linkedin.com/posts/shahram-heidari-96b35_junction2024-kone-granlund-activity-7261440179553370112-3Kj-) | Partner; BREAKDANCE award confirmation | Partner account, not jury deliberations |
| [Frank Sandqvist profile](https://www.hackjunction.com/blog/frank-sandqvist-story) | Organizer interview; 2024 project and 2025 runner-up | Search-indexed body readable; direct page returned no body; rap effect is participant interpretation |
| [Maki.vc 2023 announcement](https://www.linkedin.com/posts/maki-vc_we-were-proud-to-be-the-partner-of-this-years-activity-7131199696131280896-f7nl) | Prize partner; Driving Change award | No technical evaluation |
| [Pixieray representative](https://www.linkedin.com/posts/hlehmuskallio_junction2023-junction-hackathon-activity-7130137689604902913-EawU) and [team member](https://www.linkedin.com/in/markus-andersson-1a77a1196) | Firsthand context; 2023 input and concept | Team profile available through search; direct access restricted |
| [Junction 2022 winner announcement](https://fi.linkedin.com/posts/hackjunction_junction-2022-winners-activity-6997906878580076544-iVyf) | Organizer; Bitter Sweet awards | Limited description |
| [Haru team account](https://www.linkedin.com/posts/kshgroup_we-won-at-junction-2022-activity-6995318216663216128-AoGW) | Project authors; application, stack, awards | Self-report; no outcome study |
| [Bitter Sweet interview](https://medium.com/%40junctionasia_2023/we-are-the-winner-of-junction-fd91c3aa475b) | Organizer interview; team practices | Discusses both Asia and Finland |
| [Nice-ify interview](https://hackjunction.medium.com/replacing-hateful-language-with-a-nice-ified-alternative-interview-with-bryce-cronin-399238426bf) | Organizer interview; process and awards | Retrospective, not causal study |
| [Vikes challenge recap](https://vikes.fi/uutiset/empatiaa-pelaamiseen-junction-tuotti-22-ratkaisuehdotusta-ja-osoitti-etta-empatiassa-on-voimaa) | Challenge partner; award distinction | Finnish source; specific to 2021 |
| [Sonaptics retrospective](https://www.taitounited.fi/blog/menestyst%C3%A4-junction-hackathonista/) | Participant employer; implementation and collaboration | Reported runner-up status; not grand-jury scorecard |
| [DroneStalker creator page](https://codya.dev/project/2511-junction) | Creator; example of award-label ambiguity | Top-five claim must not become overall-winner claim |
| [Junction pitch guidance](https://hackjunction.medium.com/how-to-pitch-your-idea-at-a-hackathon-a95cd3f62f60) | Organizer advice | Published 2023; advice, not 2026 timing/rules |
| [Junction 2025 retrospective](https://hackjunction.medium.com/48-hours-at-junction-2025-creativity-community-and-the-spirit-of-innovation-fce609acb6b6) | Organizer; partner/participant perspectives | Retrospective themes, not 2026 scoring weights |
| [AROMA research](https://arxiv.org/abs/2507.10963) | Primary research; relevant prior art | Overlap does not establish identical product scope |

The main conclusions are supported as planning judgments, not guarantees: choose a concrete problem, prove the distinctive interaction early, make evidence observable, keep the scope controlled, and deliver a submission whose claims match the working system.
