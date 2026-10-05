import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ArrowRight, Check, CircleAlert, Cpu, FolderOpen, Globe2, HardDrive, Smartphone } from "lucide-react";
import { Core } from "../../components/Core";
import { Markdown } from "../../components/Markdown";
import { Sheet } from "../../components/Sheet";
import { call } from "../../services/api";
import { Pairing } from "../devices/Pairing";
import { WorldPanel } from "../devices/WorldPanel";
import type { DevicesState, PairingState } from "../devices/types";
import relayGuide from "../../../../docs/connect-world/self-host-relay.md?raw";
import {
  STEPS,
  STEP_LABELS,
  bytes,
  hardwareLines,
  isRuntimeSlot,
  directDownloadNote,
  itemLabel,
  jobItemLabel,
  jobRunning,
  previousStep,
  profileAdditions,
  profileHasUnavailable,
  resumeStep,
  selectedTotals,
  verdictLabel,
  type Job,
  type Manifest,
  type Plan,
  type PlanItem,
  type ProfileId,
  type SetupStatus,
  type SetupStep,
  type SystemCheck,
  type Verification,
} from "./setupModel";
import "./setup.css";

const RUNTIME_NAMES: Record<string, string> = {
  "ollama-runtime": "ollama",
  "image-engine": "comfy",
  "video-engine": "video_comfy",
  "audio-engine": "voicestudio",
};

/** OLIVE first-run setup. Opens on a new profile, resumes where it was left, and
 *  only finishes after verification passes. Everything it offers comes from the
 *  backend's runtime manifest. */
export function Setup({ initial, close }: { initial: SetupStatus; close: (state: string) => void }) {
  const [status, setStatus] = useState(initial);
  const [step, setStepState] = useState<SetupStep>(resumeStep(initial));
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [system, setSystem] = useState<SystemCheck | null>(null);
  const [profile, setProfile] = useState<ProfileId>(initial.profile ?? "core");
  const [plan, setPlan] = useState<Plan | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [job, setJob] = useState<Job | null>(initial.job?.job_id ? initial.job : null);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [mediaSmoke, setMediaSmoke] = useState(false);
  const [name, setName] = useState(initial.preferred_name);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [guide, setGuide] = useState(false);
  const [pairing, setPairing] = useState<PairingState | null>(null);
  const [devices, setDevices] = useState<DevicesState | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  const act = useCallback(async <T,>(work: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError("");
    try {
      return await work();
    } catch (e) {
      setError(e instanceof Error ? e.message : "That did not work.");
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);

  const refreshStatus = useCallback(async () => setStatus(await call<SetupStatus>("runtime.setup_status", {})), []);
  const go = useCallback(
    async (target: SetupStep, extra: { profile?: ProfileId; preferred_name?: string } = {}) => {
      await act(async () => {
        await call("runtime.setup_update", { step: target, ...extra });
        setStepState(target);
      });
    },
    [act],
  );

  useEffect(() => heading.current?.focus(), [step]);
  useEffect(() => {
    void act(async () => setManifest(await call<Manifest>("runtime.manifest", {})));
  }, [act]);
  useEffect(() => {
    if (step === "system" && !system) void act(async () => setSystem(await call<SystemCheck>("runtime.system_check", {})));
  }, [step, system, act]);

  const loadPlan = useCallback(async () => {
    const next = await call<Plan>("runtime.install_plan", { profile });
    setPlan(next);
    setSelected(new Set(next.default));
  }, [profile]);
  useEffect(() => {
    if (step === "runtimes" || step === "models") void act(loadPlan);
  }, [step, loadPlan, act]);

  // Poll while something installs (progress is read-only and never fills the request ledger).
  useEffect(() => {
    if (!jobRunning(job)) return;
    const timer = setInterval(() => {
      void call<Job>("runtime.install_progress", { job_id: job!.job_id! })
        .then((next) => {
          setJob(next);
          if (!jobRunning(next)) void loadPlan().catch(() => undefined);
        })
        .catch(() => undefined);
    }, 1000);
    return () => clearInterval(timer);
  }, [job, loadPlan]);

  const [address, setAddress] = useState("");
  useEffect(() => {
    if ((step === "connect" || step === "world") && !devices)
      void call<DevicesState>("connect.snapshot", {}).then(setDevices).catch(() => undefined);
  }, [step, devices]);
  const connectOn = devices?.network.state === "on";

  const coreSize = useMemo(() => {
    if (!manifest) return 0;
    const slots = new Set(manifest.features.filter((f) => f.profile === "core").flatMap((f) => [...f.requires, ...(f.optional ?? [])]));
    let total = 0;
    for (const slot of slots) total += manifest.entries.find((e) => e.provides === slot && e.installable)?.installed_bytes ?? 0;
    return total;
  }, [manifest]);

  const install = (items: PlanItem[]) =>
    act(async () => {
      const entries = items.filter((i) => i.action === "install" && selected.has(i.entry.id)).map((i) => i.entry.id);
      setJob(await call<Job>("runtime.install_start", { profile, entries }));
    });
  const running = jobRunning(job);
  const skip = () =>
    void act(async () => {
      await call("runtime.setup_update", { action: "skip" });
      close("skipped");
    });

  const footer = (primary: { label: string; run: () => void; disabled?: boolean }, back = true) => (
    <footer className="setup-footer">
      {back && step !== "welcome" ? (
        <button type="button" className="quiet" disabled={busy || running} onClick={() => void go(previousStep(step))}>
          <ArrowLeft size={15} aria-hidden="true" /> Back
        </button>
      ) : (
        <span />
      )}
      <button type="button" className="primary" disabled={busy || primary.disabled} onClick={primary.run}>
        {primary.label} <ArrowRight size={15} aria-hidden="true" />
      </button>
    </footer>
  );

  const itemRow = (item: PlanItem, selectable: boolean) => {
    const runtimeName = RUNTIME_NAMES[item.slot];
    const row = runtimeName ? status.runtimes[runtimeName] : undefined;
    return (
      <li key={item.slot} className="setup-item" data-action={item.action}>
        {selectable && item.action === "install" ? (
          <input
            type="checkbox"
            aria-label={`Install ${item.entry.name}`}
            checked={selected.has(item.entry.id)}
            disabled={running}
            onChange={(e) => {
              const next = new Set(selected);
              if (e.target.checked) next.add(item.entry.id);
              else next.delete(item.entry.id);
              setSelected(next);
            }}
          />
        ) : (
          <span className="setup-item-mark" aria-hidden="true">
            {item.action === "present" || item.action === "different_build" ? <Check size={13} /> : <span />}
          </span>
        )}
        <span className="setup-item-text">
          <strong>{item.entry.name}</strong>
          <small>
            {itemLabel(item)}
            {item.action === "install" && ` · ${bytes(item.entry.download_bytes)}`}
            {item.action === "install" && !item.entry.validated && " · Not yet verified on this system"}
            {item.entry.licence.spdx && item.action === "install" && ` · ${item.entry.licence.spdx}`}
          </small>
          {item.action === "install" && directDownloadNote(item.entry) && (
            <small className="setup-muted">{directDownloadNote(item.entry)}</small>
          )}
          {item.detail && item.action !== "install" && item.action !== "present" && <small className="setup-muted">{item.detail}</small>}
          {item.action === "external" && item.entry.link && (
            <button type="button" className="link" onClick={() => void window.olive.openExternal(item.entry.link!)}>
              Open the official download page
            </button>
          )}
          {runtimeName && row && (item.action === "choose" || row.reason === "stale") && (
            <span className="setup-choices">
              {row.also_found.map((candidate) => (
                <button
                  key={JSON.stringify(candidate.paths)}
                  type="button"
                  disabled={busy || running}
                  onClick={() =>
                    void act(async () => {
                      await call("runtime.choose", { name: runtimeName as "ollama", paths: candidate.paths as { executable?: string } });
                      await refreshStatus();
                      await loadPlan();
                    })
                  }
                >
                  Use {Object.values(candidate.paths)[0]}
                </button>
              ))}
              <button
                type="button"
                disabled={busy || running}
                onClick={() =>
                  void act(async () => {
                    const folder = (await window.olive.chooseDirectory()) as string | null | undefined;
                    if (!folder) return;
                    await call("runtime.choose", { name: runtimeName as "ollama", folder });
                    await refreshStatus();
                    await loadPlan();
                  })
                }
              >
                <FolderOpen size={14} aria-hidden="true" /> Choose folder…
              </button>
              {row.reason === "stale" && (
                <button
                  type="button"
                  className="quiet"
                  disabled={busy || running}
                  onClick={() =>
                    void act(async () => {
                      await call("runtime.forget", { name: runtimeName as "ollama" });
                      await refreshStatus();
                      await loadPlan();
                    })
                  }
                >
                  Forget the old location
                </button>
              )}
            </span>
          )}
        </span>
      </li>
    );
  };

  const progress = job && job.job_id && (
    <section className="setup-progress" aria-label="Installation progress" aria-live="polite">
      <ul>
        {job.items.map((item) => (
          <li key={item.id} data-state={item.state}>
            <span>{item.name}</span>
            <small>
              {jobItemLabel(item)}
              {item.total_bytes > 0 && ["downloading", "pulling"].includes(item.state) &&
                ` · ${bytes(item.done_bytes)} of ${bytes(item.total_bytes)}`}
              {item.state === "failed" && item.message && ` · ${item.message}`}
            </small>
            {item.total_bytes > 0 && (
              <progress max={item.total_bytes} value={Math.min(item.done_bytes, item.total_bytes)} />
            )}
          </li>
        ))}
      </ul>
      <div className="setup-row">
        {running && (
          <button type="button" className="quiet" onClick={() => void act(async () => setJob(await call<Job>("runtime.install_cancel", { job_id: job.job_id! })))}>
            Cancel
          </button>
        )}
        {(job.state === "failed" || job.state === "cancelled") && (
          <button type="button" onClick={() => void act(async () => setJob(await call<Job>("runtime.install_retry", { job_id: job.job_id! })))}>
            Retry
          </button>
        )}
      </div>
    </section>
  );

  const space = (items: PlanItem[]) => {
    if (!plan) return null;
    const download = selectedTotals({ ...plan, items }, selected);
    const short = plan.totals.volumes.filter((v) => !v.enough);
    return (
      <p className="setup-muted setup-space">
        <HardDrive size={14} aria-hidden="true" /> Download {bytes(download)}
        {plan.totals.volumes.map((v) => ` · ${bytes(v.free_bytes)} free (${v.label})`).join("")}
        {short.length > 0 && <strong className="setup-warning"> · Not enough free space</strong>}
      </p>
    );
  };

  let body: ReactNode;
  switch (step) {
    case "welcome":
      body = (
        <>
          <div className="setup-hero">
            <Core large state="Ready" />
          </div>
          <h1 ref={heading} tabIndex={-1}>Welcome to OLIVE</h1>
          <ul className="setup-points">
            <li><Cpu size={15} aria-hidden="true" /> OLIVE runs AI on this computer.</li>
            <li><Check size={15} aria-hidden="true" /> No cloud AI account is needed.</li>
            <li><Globe2 size={15} aria-hidden="true" /> Some optional features use the internet.</li>
            <li><HardDrive size={15} aria-hidden="true" /> Models need space{coreSize ? `: about ${bytes(coreSize)} for OLIVE Core` : ""}.</li>
          </ul>
          {footer({ label: "Set up OLIVE", run: () => void act(async () => {
            await call("runtime.setup_update", { action: "resume", step: "name" });
            setStepState("name");
          }) }, false)}
        </>
      );
      break;
    case "name":
      body = (
        <>
          <h1 ref={heading} tabIndex={-1}>What should OLIVE call you?</h1>
          <input
            className="setup-input"
            value={name}
            maxLength={120}
            placeholder="Optional"
            aria-label="Your name"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void go("system", { preferred_name: name })}
          />
          {footer({ label: "Continue", run: () => void go("system", { preferred_name: name }) })}
        </>
      );
      break;
    case "system":
      body = (
        <>
          <h1 ref={heading} tabIndex={-1}>System check</h1>
          {system ? (
            <>
              <p className="setup-assessment" data-state={system.assessment.state}>
                <strong>{system.assessment.label}</strong> · {system.assessment.detail}
              </p>
              <dl className="setup-facts">
                {hardwareLines(system).map((line) => (
                  <div key={line.label}>
                    <dt>{line.label}</dt>
                    <dd>{line.value}</dd>
                  </div>
                ))}
              </dl>
            </>
          ) : (
            <p className="setup-muted">Checking this computer…</p>
          )}
          {footer({ label: "Continue", run: () => void go("package"), disabled: !system || system.assessment.state === "unsupported" })}
        </>
      );
      break;
    case "package":
      body = (
        <>
          <h1 ref={heading} tabIndex={-1}>Choose your OLIVE</h1>
          <div className="setup-packages" role="radiogroup" aria-label="OLIVE package">
            {manifest?.profiles.map((p) => (
              <button
                key={p.id}
                type="button"
                role="radio"
                aria-checked={profile === p.id}
                className="setup-package"
                onClick={() => setProfile(p.id)}
              >
                <strong>{p.label}</strong>
                <small>{p.summary}</small>
                <span className="setup-tags">
                  {profileAdditions(manifest, p.id).map((f) => (
                    <span key={f.id}>{f.label}</span>
                  ))}
                </span>
                {profileHasUnavailable(manifest, p.id) && (
                  <span className="setup-notice">Some components are not yet available in this build</span>
                )}
              </button>
            ))}
          </div>
          {footer({ label: "Continue", run: () => void go("runtimes", { profile }), disabled: !manifest })}
        </>
      );
      break;
    case "runtimes":
    case "models": {
      const runtimes = step === "runtimes";
      const items = (plan?.items ?? []).filter((i) => isRuntimeSlot(i.slot) === runtimes);
      const installable = items.some((i) => i.action === "install" && selected.has(i.entry.id));
      const blocked = runtimes && items.some((i) => i.slot === "ollama-runtime" && !["present", "different_build"].includes(i.action));
      body = (
        <>
          <h1 ref={heading} tabIndex={-1}>{runtimes ? "Runtimes" : "Models"}</h1>
          {plan?.some_unavailable && <p className="setup-notice">Some components are not yet available in this build</p>}
          {plan ? <ul className="setup-items">{items.map((i) => itemRow(i, true))}</ul> : <p className="setup-muted">Checking…</p>}
          {items.some((i) => i.action === "install") && space(items)}
          {progress}
          {items.some((i) => i.action === "install") && (
            <div className="setup-row">
              <button type="button" disabled={busy || running || !installable || !plan?.totals.enough_space} onClick={() => void install(items)}>
                Install selected
              </button>
            </div>
          )}
          {footer({
            label: blocked ? "Continue without it" : "Continue",
            run: () => void go(runtimes ? "models" : "verify"),
            disabled: running,
          })}
        </>
      );
      break;
    }
    case "verify":
      body = (
        <>
          <h1 ref={heading} tabIndex={-1}>Verify</h1>
          {profile !== "core" && (
            <label className="setup-check">
              <input type="checkbox" checked={mediaSmoke} onChange={(e) => setMediaSmoke(e.target.checked)} />
              Also try a small media test
            </label>
          )}
          {verification && (
            <ul className="setup-verdicts">
              {verification.features.map((f) => (
                <li key={f.id} data-state={f.state}>
                  <span>{f.state === "ready" || f.state === "built_in" ? <Check size={14} /> : <CircleAlert size={14} />}</span>
                  <strong>{f.label}</strong>
                  <small>{verdictLabel(f.state)}{f.detail && f.state !== "not_in_build" ? ` · ${f.detail}` : ""}</small>
                </li>
              ))}
              {verification.media && (
                <li data-state="optional">
                  <span><CircleAlert size={14} /></span>
                  <strong>Media test</strong>
                  <small>{verification.media.detail}</small>
                </li>
              )}
            </ul>
          )}
          <div className="setup-row">
            <button type="button" disabled={busy} onClick={() => void act(async () => {
              setVerification(await call<Verification>("runtime.verify", { profile, run_fast: true, media_smoke: mediaSmoke }));
              await refreshStatus();
            })}>
              {busy ? "Checking…" : verification ? "Check again" : "Check that everything works"}
            </button>
          </div>
          {verification && !verification.ok && <p className="setup-warning">Setup is not finished: something above needs attention.</p>}
          {footer({ label: "Continue", run: () => void go("connect"), disabled: !verification?.ok })}
        </>
      );
      break;
    case "connect":
      body = (
        <>
          <h1 ref={heading} tabIndex={-1}>Connect your iPhone</h1>
          <p className="setup-muted">Use OLIVE from your phone on the same network. Optional.</p>
          {devices && !connectOn && (
            <>
              <p className="setup-muted">Pairing needs OLIVE Connect on your local network. Choose the network:</p>
              <div className="setup-row" role="radiogroup" aria-label="Local network">
                {devices.interfaces.map((i) => (
                  <button key={i.address} type="button" role="radio" aria-checked={address === i.address} onClick={() => setAddress(i.address)}>
                    {i.name} · {i.address}
                  </button>
                ))}
              </div>
              {!devices.interfaces.length && <p className="setup-warning">No approved local network is available right now.</p>}
              <div className="setup-row">
                <button type="button" disabled={busy || !address} onClick={() => void act(async () => {
                  await call("connect.enable", { address, discovery: true, persistent: true });
                  setDevices(await call<DevicesState>("connect.snapshot", {}));
                })}>
                  Turn on OLIVE Connect
                </button>
              </div>
            </>
          )}
          {connectOn && (
            <div className="setup-row">
              <button type="button" disabled={busy} onClick={() => void act(async () => setPairing(await call<PairingState>("connect.pair_create", {})))}>
                <Smartphone size={15} aria-hidden="true" /> Pair iPhone
              </button>
            </div>
          )}
          {pairing && <Pairing key={pairing.session_id} initial={pairing} close={() => setPairing(null)} refresh={() => undefined} />}
          {footer({ label: "Continue", run: () => void go("world") })}
        </>
      );
      break;
    case "world":
      body = (
        <>
          <h1 ref={heading} tabIndex={-1}>Use OLIVE away from home?</h1>
          <p className="setup-muted">
            Connect World reaches this computer through a relay server you run. The relay passes encrypted traffic; it
            cannot read your chats or files. Optional, and off until you set up a relay.
          </p>
          <div className="setup-row">
            <button type="button" onClick={() => setGuide(true)}>Read the self-host guide</button>
          </div>
          {devices?.world && <WorldPanel data={devices} act={(work) => void act(async () => {
            await work();
            setDevices(await call<DevicesState>("connect.snapshot", {}));
          })} />}
          {footer({ label: "Continue", run: () => void go("complete") })}
        </>
      );
      break;
    default:
      body = (
        <>
          <div className="setup-hero">
            <Core large state="Ready" />
          </div>
          <h1 ref={heading} tabIndex={-1}>{status.state === "complete" ? "OLIVE is ready" : "Setup is not finished"}</h1>
          <p className="setup-muted">
            {status.state === "complete"
              ? `${status.verified_features.length} features verified on this computer.`
              : "You can finish it any time from Settings."}
          </p>
          {footer({ label: "Open OLIVE", run: () => close(status.state) }, false)}
        </>
      );
  }

  return (
    <main className="setup" aria-label="OLIVE setup">
      <header className="setup-head">
        <ol className="setup-steps" aria-label="Setup steps">
          {STEPS.map((s) => (
            <li key={s} aria-current={s === step ? "step" : undefined} data-done={STEPS.indexOf(s) < STEPS.indexOf(step)} title={STEP_LABELS[s]} />
          ))}
        </ol>
        <span className="setup-step-name">{STEP_LABELS[step]}</span>
        {step !== "complete" && (
          <button type="button" className="quiet" disabled={busy || running} onClick={skip}>
            Set up later
          </button>
        )}
      </header>
      {status.manifest_source === "test" && <p className="setup-warning setup-banner">Test manifest in use: not a release setup.</p>}
      <div className="setup-body">
        {body}
        {error && <p className="setup-error" role="alert">{error}</p>}
      </div>
      <Sheet open={guide} onOpenChange={setGuide} title="Run your own relay" description="Connect World self-host guide">
        <div className="setup-guide">
          <Markdown text={relayGuide} />
        </div>
      </Sheet>
    </main>
  );
}

