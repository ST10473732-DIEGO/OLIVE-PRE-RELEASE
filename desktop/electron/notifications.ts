/** Only explicit completion events reach the OS; never forward arbitrary content. */
export type Notice = { key: string; title: string; body: string };
export function completionNotice(topic: string, data: Record<string, unknown>): Notice | null {
  if (topic === 'personal.reminders' && Number(data.new_count) > 0 && Array.isArray(data.delivery_ids))
    return {key: `reminders:${data.delivered_at}:${data.delivery_ids.join(',')}`, title: 'OLIVE — Reminders', body: `${Number(data.new_count)} reminders are ready in your activity centre.`};
  if (topic === 'agent' && data.id && ['completed', 'failed', 'cancelled'].includes(String(data.state)))
    return {key: `agent:${data.id}:${data.state}`, title: 'OLIVE — Agent', body: `Agent task ${data.state}. Review its result in OLIVE.`};
  if (topic === 'build.result' && data.id && ['completed', 'failed'].includes(String(data.state)))
    return {key: `studio:${data.id}`, title: 'OLIVE — Studio', body: `Studio job ${data.state}. Review its output in OLIVE.`};
  if (topic === 'mail.attention' && data.connection_id)
    return {key: `mail:${data.connection_id}`, title: 'OLIVE — Mail', body: 'Mail needs attention. Review the connection in OLIVE.'};
  if (topic === 'download.completed' && data.id)
    return {key: `download:${data.id}`, title: 'OLIVE — Downloads', body: 'Your download is complete.'};
  return null;
}

export class NoticeGate {
  private times: number[] = [];
  constructor(private seen: string[], private save: (keys: string[]) => void, private show: (notice: Notice) => void) {}
  deliver(notice: Notice, now = Date.now()) {
    if (this.seen.includes(notice.key)) return;
    // Persist the claim before OS delivery: at most once across restarts.
    // A crash in between can lose a popup; durable in-app history is authoritative.
    const next = [...this.seen, notice.key].slice(-2000);
    this.save(next);
    this.seen = next;
    this.times = this.times.filter(time => now - time < 60000);
    if (this.times.length >= 4) return;
    this.times.push(now);
    this.show(notice);
  }
}
