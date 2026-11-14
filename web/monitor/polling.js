// One in-flight monitor request at a time. Independent discovery runs every 5 s.
export class MonitorPoller {
  constructor({ listSessions, getMonitor, enabled = () => true, now = Date.now,
    onSessions = () => {}, onAttach = () => {}, onFeed = () => {}, onError = () => {} }) {
    Object.assign(this, { listSessions, getMonitor, enabled, now, onSessions, onAttach, onFeed, onError });
    this.sessionId = null;
    this.pinned = false;
    this.generation = 0;
    this.lastDiscovery = -Infinity;
    this.listing = false;
    this.polling = false;
  }
  reset() {
    this.generation++;
    this.lastDiscovery = -Infinity;
    this.onAttach(this.sessionId, this.pinned);
  }
  select(id, pinned = true) {
    const changed = id !== this.sessionId;
    this.pinned = pinned;
    if (!pinned) this.lastDiscovery = -Infinity;
    if (changed) {
      this.sessionId = id;
      this.generation++;
      this.onAttach(id, pinned);
    }
    return this.poll();
  }
  async discover() {
    if (this.listing || !this.enabled() || this.now() - this.lastDiscovery < 5000) return;
    this.listing = true;
    this.lastDiscovery = this.now();
    const generation = this.generation;
    try {
      const data = await this.listSessions();
      if (generation !== this.generation) return;
      const sessions = [...(data?.sessions || [])].sort((a, b) => Date.parse(b.started_at) - Date.parse(a.started_at));
      this.onSessions(sessions);
      if (!this.pinned && sessions[0] && sessions[0].id !== this.sessionId) await this.select(sessions[0].id, false);
    } catch (error) {
      if (generation === this.generation) this.onError(error, 'discovery');
    } finally { this.listing = false; }
  }
  async poll() {
    if (this.polling || !this.sessionId || !this.enabled()) return;
    this.polling = true;
    const id = this.sessionId, generation = this.generation;
    try {
      const feed = await this.getMonitor(id);
      if (generation === this.generation && id === this.sessionId) this.onFeed(feed, this.now());
    } catch (error) {
      if (generation === this.generation && id === this.sessionId) this.onError(error, 'monitor');
    } finally {
      this.polling = false;
      if (generation !== this.generation) void this.poll();
    }
  }
  async tick() {
    if (!this.enabled()) return;
    await Promise.all([this.discover(), this.poll()]);
  }
}
