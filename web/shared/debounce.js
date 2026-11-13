// Watcher debounce, API-CONTRACT §3.3. Pure: no timers, no DOM; time is passed in.
// The iOS app implements the same rules.

export function createDebouncer({ threshold = 0.7, requiredConsecutive = 2, muteMs = 20000 } = {}) {
  let streakId = null;
  let streakCount = 0;
  let errors = 0;
  const mutedUntil = new Map();

  function breakStreak() {
    streakId = null;
    streakCount = 0;
  }

  function isMuted(id, nowMs) {
    const until = mutedUntil.get(id);
    if (until === undefined) return false;
    if (nowMs >= until) {
      mutedUntil.delete(id);
      return false;
    }
    return true;
  }

  return {
    /** Feed one successful /watch response. Returns it when it should raise an alert, else null. */
    ingest(response, nowMs) {
      errors = 0;
      const id = response && response.mistake_id;
      const counts =
        response &&
        response.status === "warn" &&
        id &&
        typeof response.confidence === "number" &&
        response.confidence >= threshold &&
        !isMuted(id, nowMs);
      if (!counts) {
        breakStreak();
        return null;
      }
      if (id === streakId) streakCount += 1;
      else {
        streakId = id;
        streakCount = 1;
      }
      if (streakCount >= requiredConsecutive) {
        breakStreak();
        return response;
      }
      return null;
    },

    /** The wearer dismissed (or ignored for 12 s) a warning: mute that mistake. */
    dismissed(mistakeId, nowMs) {
      if (mistakeId) mutedUntil.set(mistakeId, nowMs + muteMs);
      breakStreak();
    },

    /** Step change or restart. Mutes run out on their own. */
    reset() {
      breakStreak();
      errors = 0;
    },

    /** A /watch call failed. True on every third consecutive error (pause the watcher). */
    recordError() {
      breakStreak();
      errors += 1;
      if (errors >= 3) {
        errors = 0;
        return true;
      }
      return false;
    },

    get threshold() {
      return threshold;
    },
    set threshold(v) {
      threshold = v;
    },
  };
}
