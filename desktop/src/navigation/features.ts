// One registry for every shipped capability. Navigation, the Home launcher, the
// command palette and availability labels all read from here, so they cannot
// drift apart. A new module registers once and appears in all of them.
import {
  Activity,
  BookOpen,
  Bell,
  Brain,
  CalendarDays,
  CheckSquare,
  Code2,
  Folder,
  Home,
  Mail,
  MessageSquare,
  Palette,
  Monitor,
  NotebookPen,
  Globe,
  Plug,
  Settings,
  Workflow,
} from "lucide-react";

export type FeatureCategory = "Work" | "Build" | "Knowledge" | "Personal" | "System";
/** `ready` ships today. `setup` needs configuration the user can do. */
export type FeatureAvailability = "ready" | "setup";
export interface Feature {
  id: string;
  label: string;
  /** One short line; used under the label in the launcher, never a slogan. */
  description: string;
  icon: typeof Home;
  category: FeatureCategory;
  availability: FeatureAvailability;
  /** Extra words the palette and launcher search should match. */
  aliases?: string[];
  /** Shown in navigation itself rather than only in the launcher. */
  primary?: boolean;
  /** Reached through another feature's page rather than its own nav row. */
  within?: string;
  /** Short tab name inside a multi-view space (OLIVE DrawNote › Notes). */
  view?: string;
}

export const features: Feature[] = [
  {id:"devices", label:"Devices", description:"Local pairing and device permissions.", icon:Monitor, category:"System", availability:"ready", primary:true, aliases:["devices","connect","pair","paired devices"]},
  {
    id: "home",
    label: "Home",
    description: "Start a request or open an app.",
    icon: Home,
    category: "Work",
    availability: "ready",
    primary: true,
    aliases: ["start", "dashboard", "launcher"],
  },
  {
    id: "chat",
    label: "Chat",
    description: "Think it through with a local model.",
    icon: MessageSquare,
    category: "Work",
    availability: "ready",
    primary: true,
    aliases: ["conversation", "ask", "talk", "prompt", "research", "sources", "investigate"],
  },
  {id:"notes", label:"OLIVE Notes", view:"Notes", description:"Plain-text notes that sync with your phone.", icon:NotebookPen, category:"Work", availability:"ready", primary:true, aliases:["notes","note","notepad","memo","jot","scratchpad","shopping list","drawnote","olive drawnote"]},
  {id:"draw", label:"OLIVE Draw", view:"Draw", description:"Freehand drawings; export PNG or JPEG.", icon:Palette, category:"Work", availability:"ready", primary:true, aliases:["draw","drawing","sketch","paint","canvas","doodle","pen","drawnote","olive drawnote"]},
  {id:'browser', label:'OLIVE GO', description:'Browse the web in your own browser.', icon:Globe, category:'Work', availability:'ready', primary:true, aliases:['browser','web','Google','tabs','favourites','bookmarks','downloads','history']},
  {
    id: "studio",
    label: "Studio",
    description: "Write, run and debug real code.",
    icon: Code2,
    category: "Build",
    availability: "ready",
    primary: true,
    aliases: ["code", "editor", "ide", "develop", "programming", "project"],
  },
  {
    id: "agent",
    label: "Agent",
    description: "Turn an objective into steps.",
    icon: Workflow,
    category: "Work",
    availability: "ready",
    primary: true,
    aliases: ["task", "objective", "automate", "plan"],
  },
  {
    id: "desktop",
    label: "Desktop tasks",
    within: "chat",
    description: "Work with installed applications.",
    icon: Monitor,
    category: "Build",
    availability: "ready",
    aliases: ["automation", "windows", "apps", "control"],
  },
  {
    id: "projects",
    label: "Projects",
    description: "Group related work and records.",
    icon: Folder,
    category: "Knowledge",
    availability: "ready",
    primary: true,
    aliases: ["workspace", "group", "folder"],
  },
  {
    id: "knowledge",
    label: "Knowledge",
    description: "Search your indexed sources.",
    icon: BookOpen,
    category: "Knowledge",
    availability: "ready",
    primary: true,
    aliases: ["documents", "rag", "index", "sources", "files"],
  },
  {
    id: "memory",
    label: "Memory",
    description: "What OLIVE remembers for you.",
    icon: Brain,
    category: "Knowledge",
    availability: "ready",
    aliases: ["remember", "facts", "context"],
  },
  {
    id: "mail",
    label: "Mail",
    description: "Read, draft and send with review.",
    icon: Mail,
    category: "Personal",
    availability: "ready",
    primary: true,
    aliases: ["email", "inbox", "compose", "message"],
  },
  {
    id: "calendar",
    label: "Calendar",
    description: "Your schedule, stored on this device.",
    icon: CalendarDays,
    category: "Personal",
    availability: "ready",
    primary: true,
    aliases: ["schedule", "events", "meetings", "agenda"],
  },
  {
    id: "tasks",
    label: "Tasks",
    description: "Track what you need to do.",
    icon: CheckSquare,
    category: "Personal",
    availability: "ready",
    primary: true,
    aliases: ["todo", "to-do", "checklist"],
  },
  {
    id: "reminders",
    label: "Reminders",
    description: "Prompts while OLIVE runs.",
    icon: Bell,
    category: "Personal",
    availability: "ready",
    aliases: ["alerts", "notify", "prompts"],
  },
  {
    id: "settings",
    label: "Settings",
    description: "Appearance, models and data.",
    icon: Settings,
    category: "System",
    availability: "ready",
    primary: true,
    aliases: ["preferences", "options", "configure", "permissions", "models"],
  },
  {
    id: "connections",
    label: "Connections",
    description: "Optional mail and services.",
    icon: Plug,
    category: "System",
    availability: "ready",
    aliases: ["accounts", "smtp", "imap", "servers"],
  },
  {
    id: "diagnostics",
    label: "Diagnostics",
    description: "Runtime health, logs and export.",
    icon: Activity,
    category: "System",
    availability: "ready",
    within: "settings",
    aliases: ["logs", "health", "debug", "support", "troubleshoot"],
  },
];

export const featureById = (id: string) => features.find((f) => f.id === id);
export const categories: FeatureCategory[] = ["Work", "Build", "Knowledge", "Personal", "System"];

/** Navigation rows: everything with its own route, excluding items reached
 *  through another feature's page (Diagnostics lives inside Settings). */
export const navigationFeatures = features.filter((f) => !f.within);

/** Navigation rows for a given session. Developer Mode opts into the
 *  Diagnostics shortcut; it is a user choice, never a dead control. */
export const navigationRows = (developer: boolean): Feature[] =>
  developer
    ? features.filter((f) => !f.within || f.id === "diagnostics")
    : navigationFeatures;

/** Launcher items: everything a person can open, Home excluded (they are there). */
export const launcherFeatures = features.filter((f) => f.id !== "home" && !f.within);

export function searchFeatures(query: string, list: Feature[] = features): Feature[] {
  const text = query.trim().toLowerCase();
  if (!text) return list;
  return list.filter((feature) =>
    [feature.label, feature.description, ...(feature.aliases || [])]
      .join(" ")
      .toLowerCase()
      .includes(text),
  );
}

/* ---------- Spaces (Grove redesign) ----------
   Navigation shows seven spaces instead of one row per feature. A space owns
   one or more existing routes; routes, handoffs and the palette are unchanged.
   Multi-route spaces show their views as a switcher in the title bar. */
export interface Space {
  id: string;
  label: string;
  icon: typeof Home;
  /** Routes shown as this space's views, in switcher order. */
  routes: string[];
  /** Routes that belong to the space without being one of its views. */
  also?: string[];
}
export const spaces: Space[] = [
  { id: "home", label: "Home", icon: Home, routes: ["home"] },
  { id: "chat", label: "Chat", icon: MessageSquare, routes: ["chat"], also: ["research", "desktop"] },
  // OLIVE DrawNote: two sub-applications. The routes stay "notes" and "draw",
  // so every existing Notes link, handoff and test keeps working unchanged.
  { id: "drawnote", label: "OLIVE DrawNote", icon: NotebookPen, routes: ["notes", "draw"] },
  { id: "plan", label: "Plan", icon: CalendarDays, routes: ["calendar", "tasks", "reminders"] },
  { id: "mail", label: "Mail", icon: Mail, routes: ["mail"] },
  { id: "library", label: "Library", icon: BookOpen, routes: ["knowledge", "memory", "projects"] },
  { id: "build", label: "Build", icon: Code2, routes: ["agent", "studio"] },
  { id: "web", label: "Web", icon: Globe, routes: ["browser"] },
];
/** Pinned to the foot of the navigation. */
export const footSpaces: Space[] = [
  { id: "devices", label: "Devices", icon: Monitor, routes: ["devices"] },
  { id: "settings", label: "Settings", icon: Settings, routes: ["settings"], also: ["diagnostics", "connections"] },
];
export function spaceOf(route: string): Space {
  return [...spaces, ...footSpaces].find((s) => s.routes.includes(route) || s.also?.includes(route)) || spaces[0];
}

/** Old navigation targets remain safe without a standalone Research page. */
export const chatCompatibleRoute = (id: string) => id === "research" || id === "desktop" ? "chat" : id;

/** Where a "drawnote.navigate" request lands: an explicit Notes or Draw
 *  request wins; otherwise the DrawNote section last used on this device. */
export function drawNoteRoute(section: unknown, remembered: string | undefined): "notes" | "draw" {
  if (section === "draw" || section === "notes") return section;
  return remembered === "draw" ? "draw" : "notes";
}
