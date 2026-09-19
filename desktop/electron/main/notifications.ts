import { Notification } from 'electron';
import { readFileSync, mkdirSync, writeFileSync, renameSync } from 'node:fs';
import path from 'node:path';
import { completionNotice, NoticeGate } from '../notifications';

export function nativeNotifications(profile: string, icon: string, failed: () => void) {
  const file = path.join(profile, 'native-notification-claims.json');
  let keys: string[] = [];
  let usable = true;
  try {
    const value: unknown = JSON.parse(readFileSync(file, 'utf8'));
    if (!Array.isArray(value) || !value.every(key => typeof key === 'string')) throw new Error('Invalid claims');
    keys = value.slice(-2000);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') usable = false;
  }
  let reported = false;
  const report = () => { if (!reported) { reported = true; failed(); } };
  const gate = new NoticeGate(keys, next => {
    mkdirSync(profile, {recursive: true});
    writeFileSync(file + '.tmp', JSON.stringify(next), {mode: 0o600});
    renameSync(file + '.tmp', file);
  }, notice => {
    if (!Notification.isSupported()) throw new Error('Notifications unavailable');
    const notification = new Notification({title: notice.title, body: notice.body, icon});
    notification.on('failed', report);
    notification.show();
  });
  return (topic: string, data: Record<string, unknown>) => {
    if (process.platform !== 'linux') return;
    const notice = completionNotice(topic, data);
    if (!notice) return;
    try {
      if (!usable) throw new Error('Notification claims unavailable');
      gate.deliver(notice);
    } catch {
      report();
    }
  };
}
