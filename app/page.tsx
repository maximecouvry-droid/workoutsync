"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Credentials = {
  notionToken: string;
  intervalsKey: string;
  databaseId: string;
};

type Profile = {
  ftp: number;
  ftp_pct_enabled: boolean;
  ftp_pct: number;
  im_power: number;
  im_power_pct_enabled: boolean;
  im_power_pct: number;
  ef_pace: string;
  ef_pace_pct_enabled: boolean;
  ef_pace_pct: number;
  marathon_pace: string;
  marathon_pace_pct_enabled: boolean;
  marathon_pace_pct: number;
  threshold_pace: string;
  threshold_pace_pct_enabled: boolean;
  threshold_pace_pct: number;
};

type ValidationRecord = {
  status: "ok" | "note" | "warning" | "error";
  source: string;
  output: string;
};

type Session = {
  localId: string;
  sourceType: "notion" | "manual";
  pageId?: string;
  date: string;
  sport: string;
  name: string;
  sessionId: string;
  details: string;
  editedDetails?: string;
  script?: string;
  payload?: string;
  records?: ValidationRecord[];
  checked: boolean;
};

const CREDENTIALS_KEY = "workoutsync.credentials.v1";
const PROFILE_KEY = "workoutsync.profile.v1";

const defaultCredentials: Credentials = {
  notionToken: "",
  intervalsKey: "",
  databaseId: "3879cd904ec380a6bb8dd05772b2a25f",
};

const defaultProfile: Profile = {
  ftp: 260,
  ftp_pct_enabled: true,
  ftp_pct: 3,
  im_power: 190,
  im_power_pct_enabled: true,
  im_power_pct: 3,
  ef_pace: "5:20",
  ef_pace_pct_enabled: true,
  ef_pace_pct: 5,
  marathon_pace: "4:15",
  marathon_pace_pct_enabled: true,
  marathon_pace_pct: 2,
  threshold_pace: "3:55",
  threshold_pace_pct_enabled: true,
  threshold_pace_pct: 2,
};

function textProperty(property: any): string {
  if (!property) return "";
  if (property.type === "title") {
    return (property.title ?? []).map((item: any) => item.plain_text ?? "").join("");
  }
  if (property.type === "rich_text") {
    return (property.rich_text ?? []).map((item: any) => item.plain_text ?? "").join("");
  }
  if (property.type === "select") return property.select?.name ?? "";
  if (property.type === "status") return property.status?.name ?? "";
  if (property.type === "unique_id") {
    const value = property.unique_id;
    if (!value) return "";
    return value.prefix ? `${value.prefix}-${value.number}` : String(value.number ?? "");
  }
  if (property.type === "formula") {
    const formula = property.formula ?? {};
    return String(formula[formula.type] ?? "");
  }
  return "";
}

function dateProperty(property: any): string {
  return property?.type === "date" ? property.date?.start?.slice(0, 10) ?? "" : "";
}

function notionToSession(page: any, index: number): Session | null {
  const props = page.properties ?? {};
  const sport = textProperty(props["Sport"]);
  if (/natation|swim|piscine/i.test(sport)) return null;

  return {
    localId: `notion-${page.id}-${index}`,
    sourceType: "notion",
    pageId: page.id,
    date: dateProperty(props["Date planifiée/réalisée"] ?? props["Date"] ?? props["Date planifiée"]),
    sport,
    name: textProperty(props["Séance"] ?? props["Seance"] ?? props["Nom"]),
    sessionId: textProperty(
      props["ID Séance"] ?? props["ID séance"] ?? props["ID Seance"] ?? props["ID seance"]
    ),
    details: textProperty(
      props["Détails séance"] ?? props["Details séance"] ?? props["Détails"] ?? props["Details"]
    ),
    checked: false,
  };
}

function buildEvent(session: Session, script: string) {
  const type = /vélo|velo|bike|cyclisme|home trainer|ht/i.test(session.sport) ? "Ride" : "Run";
  return {
    category: "WORKOUT",
    start_date_local: `${session.date}T00:00:00`,
    name: session.name,
    type,
    description: script,
    external_id: session.sessionId,
  };
}

function stats(records: ValidationRecord[] = []) {
  return records.reduce(
    (acc, record) => {
      acc[record.status] += 1;
      return acc;
    },
    { ok: 0, note: 0, warning: 0, error: 0 }
  );
}

export default function Home() {
  const [credentials, setCredentials] = useState(defaultCredentials);
  const [profile, setProfile] = useState(defaultProfile);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [message, setMessage] = useState("Prêt");
  const [busy, setBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [diagnostic, setDiagnostic] = useState("");
  const autoCompileRef = useRef<string | null>(null);

  useEffect(() => {
    const savedCredentials = window.localStorage.getItem(CREDENTIALS_KEY);
    const savedProfile = window.localStorage.getItem(PROFILE_KEY);
    if (savedCredentials) {
      try {
        setCredentials({ ...defaultCredentials, ...JSON.parse(savedCredentials) });
      } catch {}
    }
    if (savedProfile) {
      try {
        setProfile({ ...defaultProfile, ...JSON.parse(savedProfile) });
      } catch {}
    }
  }, []);

  const selected = useMemo(
    () => sessions.find((session) => session.localId === selectedId) ?? null,
    [sessions, selectedId]
  );

  const selectedStats = stats(selected?.records);
  const allChecked = sessions.length > 0 && sessions.every((session) => session.checked);

  useEffect(() => {
    if (!selected || selected.script || busy) return;
    if (autoCompileRef.current === selected.localId) return;

    autoCompileRef.current = selected.localId;
    let cancelled = false;

    (async () => {
      setBusy(true);
      setMessage(`Compilation automatique de « ${selected.name} »…`);
      try {
        const compiled = await compileSession(selected);
        if (cancelled) return;
        setSessions((current) =>
          current.map((session) =>
            session.localId === compiled.localId ? compiled : session
          )
        );
        setMessage("Compilation terminée");
      } catch (error) {
        if (cancelled) return;
        const msg = error instanceof Error ? error.message : "Erreur de compilation";
        setMessage(msg);
        setDiagnostic(msg);
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  function patchSelected(patch: Partial<Session>) {
    if (!selectedId) return;
    setSessions((current) =>
      current.map((session) =>
        session.localId === selectedId ? { ...session, ...patch } : session
      )
    );
  }

  async function readJsonResponse(response: Response) {
    const raw = await response.text();
    try {
      return raw ? JSON.parse(raw) : {};
    } catch {
      const preview = raw.slice(0, 240).replace(/\s+/g, " " );
      throw new Error(
        `Réponse non JSON (${response.status}) depuis ${response.url}: ${preview || "réponse vide"}`
      );
    }
  }

  function saveSettings() {
    window.localStorage.setItem(CREDENTIALS_KEY, JSON.stringify(credentials));
    window.localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
    setMessage("Réglages mémorisés sur cet appareil");
  }

  async function loadNotion() {
    if (!credentials.notionToken || !credentials.databaseId) {
      setMessage("Renseigne le token Notion et l’ID de base dans Réglages");
      setSettingsOpen(true);
      return;
    }

    setBusy(true);
    setMessage("Chargement de Notion…");
    try {
      const response = await fetch("/api/notion/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: credentials.notionToken,
          database_id: credentials.databaseId,
        }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.error ?? "Erreur Notion");

      const manual = sessions.filter((session) => session.sourceType === "manual");
      const notion = (data.results ?? [])
        .map((page: any, index: number) => notionToSession(page, index))
        .filter(Boolean) as Session[];

      autoCompileRef.current = null;
      setSessions([...manual, ...notion]);
      setSelectedId(manual[0]?.localId ?? notion[0]?.localId ?? null);
      setMessage(`${notion.length} séance(s) Notion chargée(s), natation exclue`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Erreur Notion");
    } finally {
      setBusy(false);
    }
  }

  async function compileSession(session: Session, useCurrentEdits = true): Promise<Session> {
    const details = (useCurrentEdits ? session.editedDetails ?? session.details : session.details).trim();
    if (!details) throw new Error(`Aucun détail à compiler pour « ${session.name} »`);

    setDiagnostic(
      `POST /api/compile — ${session.sport} — ${details.length} caractères`
    );

    const response = await fetch("/api/compile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      cache: "no-store",
      body: JSON.stringify({ sport: session.sport, details, profile }),
    });
    const data = await readJsonResponse(response);
    if (!response.ok) throw new Error(data.error ?? `Erreur de compilation HTTP ${response.status}`);
    if (typeof data.script !== "string" || !data.script.trim()) {
      throw new Error("L’API a répondu sans script compilé");
    }

    const event = {
      ...buildEvent(session, data.script),
      ...(data.moving_time ? { moving_time: data.moving_time } : {}),
    };
    setDiagnostic(
      `Compilation OK — ${data.records?.length ?? 0} ligne(s) analysée(s) — ${data.script.length} caractères de script`
    );

    return {
      ...session,
      editedDetails: details,
      script: data.script,
      records: data.records ?? [],
      payload: JSON.stringify([event], null, 2),
    };
  }

  async function compileSelected() {
    if (!selected) return;
    autoCompileRef.current = selected.localId;
    setBusy(true);
    setMessage("Compilation…");
    try {
      const compiled = await compileSession(selected);
      setSessions((current) =>
        current.map((session) => (session.localId === compiled.localId ? compiled : session))
      );
      setMessage("Compilation terminée");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Erreur de compilation");
    } finally {
      setBusy(false);
    }
  }

  function regeneratePayload() {
    if (!selected?.script) return;
    const event = buildEvent(selected, selected.script);
    patchSelected({ payload: JSON.stringify([event], null, 2) });
    setMessage("Payload actualisé depuis le script");
  }

  async function sendChecked() {
    const checked = sessions.filter((session) => session.checked);
    if (!checked.length) {
      setMessage("Coche au moins une séance");
      return;
    }
    if (!credentials.intervalsKey) {
      setMessage("Renseigne la clé Intervals dans Réglages");
      setSettingsOpen(true);
      return;
    }

    setBusy(true);
    setMessage(`Préparation de ${checked.length} séance(s)…`);
    try {
      const compiled: Session[] = [];
      for (const session of checked) {
        if (session.payload && session.script && session.records) {
          compiled.push(session);
        } else {
          compiled.push(await compileSession(session));
        }
      }

      const blocking = compiled.filter((session) =>
        (session.records ?? []).some((record) => record.status === "error")
      );
      if (blocking.length) {
        throw new Error(
          `Envoi bloqué : ${blocking.map((session) => session.name).join(", ")} contient une ligne rouge`
        );
      }

      const events = compiled.map((session) => {
        const parsed = JSON.parse(session.payload ?? "[]");
        return parsed[0];
      });

      const response = await fetch("/api/intervals/events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: credentials.intervalsKey,
          events,
        }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok) throw new Error(data.error ?? "Erreur Intervals");

      for (const session of compiled) {
        if (session.sourceType === "notion" && session.pageId) {
          await fetch("/api/notion/status", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              token: credentials.notionToken,
              page_id: session.pageId,
            }),
          });
        }
      }

      setSessions((current) =>
        current
          .map((session) => compiled.find((item) => item.localId === session.localId) ?? session)
          .filter((session) => !checked.some((item) => item.localId === session.localId && item.sourceType === "notion"))
      );
      setSelectedId(null);
      setMessage(`${events.length} séance(s) envoyée(s)`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Erreur d’envoi");
    } finally {
      setBusy(false);
    }
  }

  function addManual(session: Omit<Session, "localId" | "sourceType" | "checked">) {
    const item: Session = {
      ...session,
      localId: `manual-${Date.now()}`,
      sourceType: "manual",
      checked: false,
    };
    setSessions((current) => [item, ...current]);
    setSelectedId(item.localId);
    setManualOpen(false);
    setMessage("Séance manuelle ajoutée");
  }

  function deleteSelected() {
    if (!selected) return;
    setSessions((current) => current.filter((session) => session.localId !== selected.localId));
    setSelectedId(null);
  }

  return (
    <main>
      <header className="hero">
        <div>
          <p className="eyebrow">WORKOUT SYNC</p>
          <h1>Notion → Intervals.icu → Garmin</h1>
          <p className="subtitle">Même moteur Python, nouvelle interface web installable.</p>
        </div>
        <div className="heroActions">
          <button className="ghostLight" onClick={() => setSettingsOpen(true)}>
            Réglages
          </button>
          <button className="dark" onClick={sendChecked} disabled={busy}>
            Envoyer
          </button>
        </div>
      </header>

      <nav className="toolbar">
        <button className="dark" onClick={loadNotion} disabled={busy}>
          Charger Notion
        </button>
        <button className="orange" onClick={() => setManualOpen(true)}>
          + Ajouter une séance
        </button>
        <button onClick={compileSelected} disabled={!selected || busy}>
          Régénérer script + payload
        </button>
        <button onClick={regeneratePayload} disabled={!selected?.script}>
          Actualiser payload
        </button>
        <span className="toolbarSpacer" />
        <div className="statusBlock">
          <span className="status">{busy ? "Traitement…" : message}</span>
          {diagnostic && <span className="diagnostic">{diagnostic}</span>}
        </div>
      </nav>

      <section className="workspace">
        <article className="panel sourcePanel">
          <PanelHeader title="Source Notion / manuelle" subtitle="Les modifications restent locales jusqu’au prochain rechargement Notion." />

          <label className="selectAll">
            <input
              type="checkbox"
              checked={allChecked}
              onChange={(event) =>
                setSessions((current) =>
                  current.map((session) => ({ ...session, checked: event.target.checked }))
                )
              }
            />
            Tout sélectionner
          </label>

          <div className="sessionList">
            {sessions.length === 0 && (
              <div className="empty">Charge Notion ou ajoute une séance manuelle.</div>
            )}
            {sessions.map((session) => (
              <button
                key={session.localId}
                className={`sessionRow ${session.localId === selectedId ? "selected" : ""}`}
                onClick={() => {
                  autoCompileRef.current = null;
                  setSelectedId(session.localId);
                }}
              >
                <input
                  type="checkbox"
                  checked={session.checked}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(event) =>
                    setSessions((current) =>
                      current.map((item) =>
                        item.localId === session.localId
                          ? { ...item, checked: event.target.checked }
                          : item
                      )
                    )
                  }
                />
                <span className="sourceBadge">{session.sourceType === "manual" ? "Manuelle" : "Notion"}</span>
                <span className="sessionDate">{session.date}</span>
                <span className="sessionName">{session.name}</span>
              </button>
            ))}
          </div>

          <textarea
            className="editor sourceEditor"
            value={selected?.editedDetails ?? selected?.details ?? ""}
            onChange={(event) => patchSelected({ editedDetails: event.target.value })}
            placeholder="Détails de la séance"
            disabled={!selected}
          />
          <div className="panelActions">
            <button onClick={deleteSelected} disabled={!selected}>
              Supprimer de la liste
            </button>
          </div>
        </article>

        <article className="panel scriptPanel">
          <PanelHeader title="Script Intervals" subtitle="Tu peux corriger directement le script avant de régénérer le payload." />

          <textarea
            className="editor scriptEditor"
            value={selected?.script ?? ""}
            onChange={(event) => patchSelected({ script: event.target.value })}
            placeholder="Le script compilé apparaîtra ici."
            disabled={!selected}
          />

          <div className="validationHeader">
            <strong>Validation</strong>
            <div className="stats">
              <Stat label="Compris" value={selectedStats.ok} kind="ok" />
              <Stat label="Info" value={selectedStats.note} kind="note" />
              <Stat label="Approx." value={selectedStats.warning} kind="warning" />
              <Stat label="Erreur" value={selectedStats.error} kind="error" />
            </div>
          </div>

          <div className="validationList">
            {(selected?.records ?? []).map((record, index) => (
              <div key={`${record.source}-${index}`} className={`validationItem ${record.status}`}>
                <strong>{record.source}</strong>
                <span>{record.output}</span>
              </div>
            ))}
            {selected && !selected.records?.length && (
              <div className="empty">Compile la séance pour afficher l’analyse ligne par ligne.</div>
            )}
          </div>
        </article>

        <article className="panel payloadPanel">
          <PanelHeader title="Payload Intervals.icu" subtitle="Le JSON final envoyé à l’API." />
          <textarea
            className="editor payloadEditor"
            value={selected?.payload ?? ""}
            onChange={(event) => patchSelected({ payload: event.target.value })}
            placeholder="Le payload apparaîtra ici."
            disabled={!selected}
          />
          <div className="panelActions">
            <button
              onClick={() => {
                try {
                  JSON.parse(selected?.payload ?? "");
                  setMessage("Payload JSON valide");
                } catch {
                  setMessage("Payload JSON invalide");
                }
              }}
              disabled={!selected?.payload}
            >
              Valider JSON
            </button>
            <button
              onClick={() => navigator.clipboard.writeText(selected?.payload ?? "")}
              disabled={!selected?.payload}
            >
              Copier
            </button>
          </div>
        </article>
      </section>

      {settingsOpen && (
        <SettingsModal
          credentials={credentials}
          profile={profile}
          onCredentials={setCredentials}
          onProfile={setProfile}
          onSave={() => {
            saveSettings();
            setSettingsOpen(false);
          }}
          onClose={() => setSettingsOpen(false)}
        />
      )}

      {manualOpen && (
        <ManualModal
          onAdd={addManual}
          onClose={() => setManualOpen(false)}
        />
      )}
    </main>
  );
}

function PanelHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <>
      <div className="panelTitle">{title}</div>
      <p className="panelSubtitle">{subtitle}</p>
    </>
  );
}

function Stat({
  label,
  value,
  kind,
}: {
  label: string;
  value: number;
  kind: "ok" | "note" | "warning" | "error";
}) {
  return (
    <span className={`stat ${kind}`}>
      {label} {value}
    </span>
  );
}

function SettingsModal({
  credentials,
  profile,
  onCredentials,
  onProfile,
  onSave,
  onClose,
}: {
  credentials: Credentials;
  profile: Profile;
  onCredentials: (value: Credentials) => void;
  onProfile: (value: Profile) => void;
  onSave: () => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<"credentials" | "profile" | "syntax">("credentials");

  return (
    <div className="modalBackdrop">
      <div className="modal largeModal">
        <div className="modalHeader">
          <h2>Réglages</h2>
          <button onClick={onClose}>×</button>
        </div>
        <div className="tabs">
          <button className={tab === "credentials" ? "active" : ""} onClick={() => setTab("credentials")}>
            Connexion
          </button>
          <button className={tab === "profile" ? "active" : ""} onClick={() => setTab("profile")}>
            Zones personnelles
          </button>
          <button className={tab === "syntax" ? "active" : ""} onClick={() => setTab("syntax")}>
            Syntaxe Intervals
          </button>
        </div>

        {tab === "credentials" && (
          <div className="formGrid">
            <label>
              Token Notion
              <input
                type="password"
                value={credentials.notionToken}
                onChange={(event) =>
                  onCredentials({ ...credentials, notionToken: event.target.value })
                }
              />
            </label>
            <label>
              Clé API Intervals
              <input
                type="password"
                value={credentials.intervalsKey}
                onChange={(event) =>
                  onCredentials({ ...credentials, intervalsKey: event.target.value })
                }
              />
            </label>
            <label>
              ID de base Notion
              <input
                value={credentials.databaseId}
                onChange={(event) =>
                  onCredentials({ ...credentials, databaseId: event.target.value })
                }
              />
            </label>
          </div>
        )}

        {tab === "profile" && (
          <div className="profileGrid">
            <ProfileField label="FTP" value={profile.ftp} pct={profile.ftp_pct} onValue={(value) => onProfile({ ...profile, ftp: Number(value) })} onPct={(value) => onProfile({ ...profile, ftp_pct: Number(value) })} />
            <ProfileField label="Puissance IM" value={profile.im_power} pct={profile.im_power_pct} onValue={(value) => onProfile({ ...profile, im_power: Number(value) })} onPct={(value) => onProfile({ ...profile, im_power_pct: Number(value) })} />
            <ProfileField label="Allure EF" value={profile.ef_pace} pct={profile.ef_pace_pct} onValue={(value) => onProfile({ ...profile, ef_pace: value })} onPct={(value) => onProfile({ ...profile, ef_pace_pct: Number(value) })} />
            <ProfileField label="Allure marathon" value={profile.marathon_pace} pct={profile.marathon_pace_pct} onValue={(value) => onProfile({ ...profile, marathon_pace: value })} onPct={(value) => onProfile({ ...profile, marathon_pace_pct: Number(value) })} />
            <ProfileField label="Allure seuil" value={profile.threshold_pace} pct={profile.threshold_pace_pct} onValue={(value) => onProfile({ ...profile, threshold_pace: value })} onPct={(value) => onProfile({ ...profile, threshold_pace_pct: Number(value) })} />
          </div>
        )}

        {tab === "syntax" && <SyntaxGuide />}

        <div className="modalActions">
          <button onClick={onClose}>Annuler</button>
          <button className="orange" onClick={onSave}>
            Enregistrer
          </button>
        </div>
      </div>
    </div>
  );
}

function ProfileField({
  label,
  value,
  pct,
  onValue,
  onPct,
}: {
  label: string;
  value: string | number;
  pct: number;
  onValue: (value: string) => void;
  onPct: (value: string) => void;
}) {
  return (
    <div className="profileField">
      <strong>{label}</strong>
      <input value={value} onChange={(event) => onValue(event.target.value)} />
      <span>±</span>
      <input type="number" value={pct} onChange={(event) => onPct(event.target.value)} />
      <span>%</span>
    </div>
  );
}

function SyntaxGuide() {
  return (
    <div className="syntaxGuide">
      <h3>Format général</h3>
      <pre>{`- durée ou distance [cible] [cadence]
- 5m30s 60% 90rpm
- 1km 70% HR
- 500mtr 5:00/km Pace`}</pre>

      <h3>Durées et distances</h3>
      <pre>{`1h
10m
30s
1h2m30s
2km
500mtr
1mi

Important : m = minutes ; mtr = mètres.`}</pre>

      <h3>Puissance, fréquence cardiaque et allure</h3>
      <pre>{`75%
95-105%
220w
200-240w
Z2
70% HR
95% LTHR
5:00 Pace
5:00/km Pace
Z2 Pace`}</pre>

      <h3>Répétitions</h3>
      <pre>{`5x
- 30s 120%
- 30s 50%

Ne pas imbriquer des répétitions.`}</pre>

      <h3>Rampes et mode libre</h3>
      <pre>{`- 10m ramp 50%-75%
- 15m ramp 60%-90% 85rpm
- 20m freeride`}</pre>
    </div>
  );
}

function ManualModal({
  onAdd,
  onClose,
}: {
  onAdd: (session: Omit<Session, "localId" | "sourceType" | "checked">) => void;
  onClose: () => void;
}) {
  const [date, setDate] = useState("");
  const [sport, setSport] = useState("Course");
  const [name, setName] = useState("");
  const [details, setDetails] = useState("");

  function submit() {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !name.trim() || !details.trim()) return;
    onAdd({
      date,
      sport,
      name,
      sessionId: `manual-${date}-${Date.now()}`,
      details,
    });
  }

  return (
    <div className="modalBackdrop">
      <div className="modal">
        <div className="modalHeader">
          <h2>Ajouter une séance</h2>
          <button onClick={onClose}>×</button>
        </div>
        <div className="formGrid">
          <label>
            Date
            <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
          </label>
          <label>
            Sport
            <select value={sport} onChange={(event) => setSport(event.target.value)}>
              <option>Course</option>
              <option>Vélo</option>
              <option>Home trainer</option>
            </select>
          </label>
          <label>
            Nom
            <input value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            Contenu
            <textarea value={details} onChange={(event) => setDetails(event.target.value)} />
          </label>
        </div>
        <div className="modalActions">
          <button onClick={onClose}>Annuler</button>
          <button className="orange" onClick={submit}>
            Valider et ajouter
          </button>
        </div>
      </div>
    </div>
  );
}
