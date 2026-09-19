"""Typed GUI-only facade. QML cannot call arbitrary runtime operations."""
from datetime import datetime
from pathlib import Path
import uuid
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer
from PySide6.QtWidgets import QApplication
from .models import RowsModel
from .resources import asset_root
from .tokens import DesignTokens


class ExperienceController(QObject):
    changed = Signal()
    entered = Signal()
    drawerRequested = Signal(str)
    appearanceChanged = Signal()
    ACTIVE = {"running", "planning", "executing", "validating", "starting", "researching", "preparing"}

    def __init__(self, manager):
        super().__init__(manager)
        self.manager, self.bridge = manager, manager.bridge
        preferences = manager.state.get("experience")
        self._light = preferences.get("light", False) is True
        self._reduced = preferences.get("reduced_motion", False) is True
        self._welcome_pref = preferences.get("show_welcome", True) is not False
        self._welcome = self._welcome_pref
        self._expanded = False
        self._page = "home"
        self._spaces = False
        self._gallery = False
        self._busy = False
        self._result = ""
        self._understood = ""
        self._request = None
        self._awaiting_stream = False
        self._submitted = False
        self._chat = None
        self._ready = False
        self._fatal = False
        self._degraded = False
        self._window_active = True
        self._desktop = False
        self._activities = {}
        self._approvals = set()
        self._context = ""
        self._filter = ""
        self._refresh_identity = 0
        self._favourites = [f for f in preferences.get("favourites", [])
                            if isinstance(f,str) and f in manager.registry.features][:12]
        self.tokens = DesignTokens(self, self._light)
        self.spaces = RowsModel(self)
        self.recents = RowsModel(self)
        self.filterSpaces("")
        self.bridge.event.connect(self.on_event)
        self.bridge.ready.connect(self.on_ready)
        self.bridge.confirmation.connect(self.on_confirmation)
        manager.navigation.changed.connect(self.navigated)
        self.clock = QTimer(self); self.clock.setInterval(60000)
        self.clock.timeout.connect(self.changed); self.clock.start()
        if self.bridge.is_ready:
            QTimer.singleShot(0,self.on_ready)

    @Property(QObject, constant=True)
    def spacesModel(self): return self.spaces
    @Property(QObject, constant=True)
    def recentModel(self): return self.recents
    @Property(str, constant=True)
    def assetUrl(self): return asset_root().as_uri()
    @Property(bool, notify=changed)
    def welcome(self): return self._welcome
    @Property(bool, notify=changed)
    def entryAllowed(self): return not self._fatal
    @Property(bool, notify=changed)
    def reducedMotion(self): return self._reduced
    @Property(bool, notify=changed)
    def lightTheme(self): return self._light
    @Property(bool, notify=changed)
    def windowActive(self): return self._window_active
    @Property(bool, notify=changed)
    def expanded(self): return self._expanded
    @Property(bool, notify=changed)
    def spacesOpen(self): return self._spaces
    @Property(bool, notify=changed)
    def galleryOpen(self): return self._gallery
    @Property(str, notify=changed)
    def page(self): return self._page
    @Property(str, notify=changed)
    def pageTitle(self): return self.manager.registry.get(self._page).title
    @Property(str, notify=changed)
    def greeting(self):
        hour = datetime.now().hour
        return "Good morning." if hour < 12 else "Good afternoon." if hour < 18 else "Good evening."
    @Property(str, notify=changed)
    def dateLabel(self): return datetime.now().strftime("%A, %d %B").replace(" 0", " ")
    @Property(str, notify=changed)
    def readiness(self):
        if self._fatal: return "Local workspace could not start. Open diagnostics."
        if not self._ready: return "Preparing your local workspace"
        if self._degraded: return "Local workspace ready. AI is unavailable."
        return "Local workspace ready"
    @Property(str, notify=changed)
    def coreState(self):
        if self._fatal: return "ERROR"
        if self._approvals: return "WAITING_FOR_APPROVAL"
        states = [v["state"] for v in self._activities.values()]
        for state in ("RESEARCHING","WORKING","THINKING","PAUSED"):
            if state in states: return state
        return "DEGRADED" if self._degraded else "READY"
    @Property(str, notify=changed)
    def stateLabel(self): return self.coreState.replace("_", " ").capitalize()
    @Property(int, notify=changed)
    def activityCount(self): return len(self._activities)
    @Property("QVariantList", notify=changed)
    def activities(self): return list(self._activities.values())
    @Property(bool, notify=changed)
    def busy(self): return self._busy
    @Property(str, notify=changed)
    def result(self): return self._result
    @Property(str, notify=changed)
    def understood(self): return self._understood
    @Property(str, notify=changed)
    def contextLabel(self): return self._context
    @Property(bool, notify=changed)
    def desktopEnabled(self): return self._desktop

    @Slot()
    def enter(self):
        if self._welcome and self.entryAllowed:
            self._welcome = False
            self.changed.emit(); self.entered.emit()

    @Slot(str)
    def navigate(self, feature):
        if feature not in self.manager.registry.features:
            return
        self.enter()
        self._gallery = self._spaces = False
        self.manager.open(feature)

    @Slot(str)
    def navigated(self, feature):
        self._page = feature
        if feature != "home": self.enter()
        self.changed.emit()
        if self._ready: self.refresh()

    @Slot()
    def toggleNavigation(self):
        self._expanded = not self._expanded; self.changed.emit()

    @Slot()
    def showSpaces(self):
        self.navigate("home"); self._spaces = True; self.changed.emit()

    @Slot()
    def showGallery(self):
        self.navigate("home"); self._gallery = True; self.changed.emit()

    @Slot()
    def palette(self): self.manager.command_palette()
    @Slot()
    def showActivity(self): self.drawerRequested.emit("activity")
    @Slot()
    def showAppearance(self): self.drawerRequested.emit("appearance")
    @Slot()
    def showContext(self): self.drawerRequested.emit("context")
    @Slot()
    def clearContext(self):
        if self._busy:return
        def cleared(value,error):
            if error:self._result=error
            else:self._context=""
            self.changed.emit(); self.refresh()
        self.bridge.call("interaction.clear_context",cleared,chat_id=self._chat)
    @Slot()
    def stopControl(self): self.bridge.stop_control()

    @Slot(str)
    def filterSpaces(self, query):
        self._filter = str(query)[:200].casefold()
        features = self.manager.registry.list()
        features.sort(key=lambda f: (self._favourites.index(f.id) if f.id in self._favourites else 100+f.priority))
        self.spaces.replace([{"key":f.id,"feature":f.id,"title":f.title,"subtitle":f.description,
            "glyph":f.id,"pinned":f.id in self._favourites} for f in features
            if self._filter in (f.title + " " + f.description).casefold()])

    @Slot(str)
    def togglePin(self, feature):
        if feature not in self.manager.registry.features: return
        if feature in self._favourites: self._favourites.remove(feature)
        else: self._favourites.append(feature)
        self.persist(); self.filterSpaces(self._filter)

    def persist(self):
        self.manager.state.save("experience", {"light":self._light,"reduced_motion":self._reduced,
            "show_welcome":self._welcome_pref,"favourites":self._favourites})

    @Slot(bool)
    def setReducedMotion(self,value):
        self._reduced=bool(value); self.persist(); self.changed.emit()

    @Slot(bool)
    def setLightTheme(self,value):
        self._light=bool(value); self.tokens.set_light(self._light)
        self.tokens.apply_widgets(QApplication.instance()); self.persist()
        self.changed.emit(); self.appearanceChanged.emit()

    @Slot(bool)
    def setShowWelcome(self,value):
        self._welcome_pref=bool(value); self.persist()

    def set_window_active(self, active):
        if self._window_active != active:
            self._window_active=active; self.changed.emit()

    @Slot()
    def on_ready(self):
        self._ready=True; self.changed.emit(); self.refresh()

    def refresh(self):
        self._refresh_identity += 1
        identity = self._refresh_identity
        self.bridge.call("data.home", lambda value,error:
                         self.home_loaded(value,error) if identity==self._refresh_identity else None)

    def home_loaded(self, value, error):
        if value and not error:
            self.recents.replace(value["recent"])
            if not self._busy: self._chat=value["chat_id"]
            context=value.get("context",{})
            self._context=" · ".join(context[k] for k in ("workspace","file") if context.get(k))
            self.on_event("status", value["status"])

    @Slot(str)
    def submit(self,text):
        if self._busy or self._fatal or not 1 <= len(text.strip()) <= 4000: return
        self._busy=True; self._result=""; self._understood=text.strip()
        self._awaiting_stream=False
        self._submitted=False
        identity = self._request = str(uuid.uuid4())
        self._activities[identity]={"id":identity,"title":"Your request","state":"THINKING"}
        self.changed.emit()
        def selected(value,error):
            if identity != self._request: return
            if error or not value:
                finish(None,error or "The conversation is unavailable"); return
            self._chat=value["id"]
            self._submitted=True
            self.bridge.call("interaction.submit",finish,chat_id=self._chat,text=text.strip())
        def finish(value,error):
            if identity != self._request: return
            if not error and (value or {}).get("generating"):
                self._awaiting_stream=True
                self._result=(value or {}).get("partial", "")[:6000]
                self.changed.emit()
            else:
                self.finish_request(value,error)
        self.bridge.call("chat.get",selected)

    def finish_request(self, value=None, error=None):
        self._activities.pop(self._request,None)
        self._busy=False; self._request=None; self._awaiting_stream=False
        messages=[m for m in (value or {}).get("messages",[]) if m.get("role")=="assistant"]
        self._result=error or (messages[-1].get("content", "")[:6000] if messages else "The request finished.")
        self.changed.emit(); self.refresh()

    @Slot()
    def cancel(self):
        if not self._busy: return
        if not self._submitted:
            self.finish_request(error="I cancelled the request.")
        elif self._chat:
            identity=self._request
            def cancelled(value,error):
                if identity==self._request:
                    self.finish_request(value,error or "I stopped the request.")
            self.bridge.call("interaction.cancel",cancelled,chat_id=self._chat)

    @Slot(str)
    def continueItem(self,key):
        item=next((r for r in self.recents.rows if r["key"]==key),None)
        if not item:return
        self.navigate(item["feature"])
        page=self.manager.workspace(item["feature"])
        if item["kind"]=="chat":
            if hasattr(page,"select_chat"):page.select_chat(key)
            else:self.bridge.call("chat.select",page.render,chat_id=key)
        elif item["kind"]=="workspace":
            page.workspace_id=key
            self.bridge.call("interaction.select_workspace",workspace_id=key)
            page.refresh()

    @Slot(object)
    def on_confirmation(self,request):
        self._approvals.add(request.id); self.changed.emit()

    def confirmation_finished(self,identity):
        self._approvals.discard(identity); self.changed.emit()

    @Slot(str,object)
    def on_event(self,topic,value):
        if topic=="fatal":self._fatal=True
        elif topic=="status":
            self._degraded="unavailable" in str(value.get("ollama","")).lower() or value.get("chat_models")==0
            if value.get("indexing",0):
                self._activities["indexing"]={"id":"indexing","title":"Indexing sources","state":"WORKING"}
            else:self._activities.pop("indexing",None)
        elif topic in {"agent","research"}:
            key=topic+":"+str(value.get("id","current"))
            state=str(value.get("status" if topic=="research" else "state","")).lower()
            if state in self.ACTIVE or state in {"searching", "reading", "evaluating", "synthesizing", "waiting_for_confirmation"} or state.startswith("paused"):
                self._activities[key]={"id":key,"title":"Research" if topic=="research" else "Agent task",
                    "state":"PAUSED" if state.startswith("paused") else "RESEARCHING" if topic=="research" else "WORKING"}
            else:self._activities.pop(key,None)
        elif topic=="chat":
            key="chat:"+value["id"]
            if value.get("generating") and not (self._busy and self._chat==value["id"]):
                self._activities[key]={"id":key,"title":"Conversation","state":"THINKING"}
            else:self._activities.pop(key,None)
            if self._awaiting_stream and self._chat==value["id"] and not value.get("generating"):
                self.finish_request(value)
        elif topic=="chat_stream" and self._busy and value.get("chat_id")==self._chat:
            self._result=value.get("text","")[:6000]
        elif topic=="desktop":
            self._desktop=bool(value.get("settings",{}).get("enabled") or value.get("active"))
            if value.get("active"):self._activities["desktop"]={"id":"desktop","title":"Desktop Control","state":"WORKING"}
            else:self._activities.pop("desktop",None)
        elif topic=="chats":
            if self._ready:self.refresh()
        elif topic=="interaction_activity" and self._busy and value.get("chat_id")==self._chat:
            self._activities[self._request]={"id":self._request,"title":"Your request","state":"WORKING"}
        else:return
        self.changed.emit()
