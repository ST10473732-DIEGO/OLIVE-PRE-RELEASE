from PySide6.QtWidgets import QInputDialog, QMessageBox, QMenu
from ..components.common import populate, selected


class StudioActions:
    def save(self, checked=False, document=None, after=None):
        doc = document or self.active_document()
        if not doc:
            return
        key = (doc["workspace_id"], doc["path"])
        if key in self.saving:
            return
        self.saving.add(key)
        text = doc["editor"].get_text()

        def saved(value, error):
            self.saving.discard(key)
            if value:
                doc["hash"] = value["loaded_hash"]
                doc["saved"] = value["saved_text"]
                doc["editor"].document().setModified(doc["editor"].get_text() != value["saved_text"])
                self.statusBar().showMessage("File saved", 5000)
                if after:
                    after()

        self.call(
            "studio.access",
            saved,
            workspace_id=doc["workspace_id"],
            action="save",
            path=doc["path"],
            text=text,
            expected_hash=doc["hash"],
        )

    def save_all(self, checked=False, after=None):
        documents = [d for d in self.documents.values() if d["editor"].document().isModified()]
        remaining = {id(d) for d in documents}

        def complete(document):
            remaining.discard(id(document))
            if not remaining and after:
                after()

        for document in documents:
            self.save(document=document, after=lambda d=document: complete(d))
        if not documents and after:
            after()

    def close_tab(self, index):
        editor = self.tabs.widget(index)
        doc = next((d for d in self.documents.values() if d["editor"] is editor), None)
        if not doc:
            return
        if (doc["workspace_id"], doc["path"]) in self.saving:
            self.statusBar().showMessage("Wait for the pending save to finish before closing this file", 5000)
            return
        if editor.document().isModified():
            choice = QMessageBox.question(
                self,
                "Unsaved file",
                f"Save changes to {doc['path']}?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                return
            if choice == QMessageBox.StandardButton.Save:
                self.save(document=doc, after=lambda: self.close_tab(self.tabs.indexOf(editor)))
                return
        self.documents.pop((doc["workspace_id"], doc["path"]))
        self.tabs.removeTab(index)
        editor.deleteLater()

    def can_close(self, exiting=False):
        if self.saving:
            self.statusBar().showMessage("Wait for pending file saves to finish before closing", 5000)
            return False
        dirty = [d for d in self.documents.values() if d["editor"].document().isModified()]
        if not dirty:
            return True
        choice = QMessageBox.question(
            self,
            "Unsaved Studio files",
            "Save all modified files before closing?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if choice == QMessageBox.StandardButton.Save:
            self.save_all(after=self.manager.exit if exiting else self.close)
            return False
        if choice == QMessageBox.StandardButton.Discard:
            for document in dirty:
                document["editor"].set_text(document["saved"])
            return True
        return False

    def tab_menu(self, point):
        menu = QMenu(self)
        menu.addAction("Save", self.save)
        menu.addAction("Save all", self.save_all)
        menu.addAction("Close", lambda: self.close_tab(self.tabs.currentIndex()))
        menu.addAction("Close others", self.close_others)
        menu.addAction("Reopen recent", self.reopen_recent)
        menu.exec(self.tabs.mapToGlobal(point))

    def close_others(self):
        current = self.tabs.currentWidget()
        for index in reversed(range(self.tabs.count())):
            if self.tabs.widget(index) is not current:
                self.close_tab(index)

    def reopen_recent(self):
        values = [key for key in self.recent if key not in self.documents]
        if values:
            self.open_file(values[0][1], workspace_id=values[0][0])

    def quick_open(self):
        if not self.workspace_id:
            return

        def choose(value, error):
            if not value:
                return
            paths = [item["path"] for item in value["entries"] if not item["directory"]]
            path, ok = QInputDialog.getItem(self, "Quick open", "Workspace file", paths, editable=True)
            if ok and path:
                self.open_file(path)

        self.call("studio.access", choose, workspace_id=self.workspace_id, action="tree")

    def search_workspace(self):
        if not self.workspace_id:
            return
        query, ok = QInputDialog.getText(self, "Search workspace", "Text")
        if not ok:
            return

        def choose(value, error):
            if not value:
                return
            matches = value["matches"]
            labels = [f"{p}:{n}  {text[:100]}" for p, n, text in matches]
            if not labels:
                self.statusBar().showMessage("No matches", 5000)
                return
            label, ok = QInputDialog.getItem(self, "Search results", "Open result", labels, editable=False)
            if ok:
                path, line, _ = matches[labels.index(label)]
                self.open_file(path, line)

        self.call("studio.access", choose, workspace_id=self.workspace_id, action="search", query=query)

    def find_replace(self):
        doc = self.active_document()
        if not doc:
            return
        find, ok = QInputDialog.getText(self, "Find", "Text")
        if not ok or not find:
            return
        editor = doc["editor"]
        if not editor.find(find):
            editor.moveCursor(editor.textCursor().MoveOperation.Start)
            editor.find(find)
        replacement, ok = QInputDialog.getText(self, "Replace all", "Replacement (Cancel keeps find result)")
        if ok:
            cursor = editor.textCursor()
            cursor.beginEditBlock()
            cursor.select(cursor.SelectionType.Document)
            cursor.insertText(editor.get_text().replace(find, replacement))
            cursor.endEditBlock()

    def go_to_line(self):
        doc = self.active_document()
        if doc:
            line, ok = QInputDialog.getInt(self, "Go to line", "Line", 1, 1, doc["editor"].blockCount())
            if ok:
                doc["editor"].go_to_line(line)

    def research(self):
        doc = self.active_document()
        workspace = self.workspace_values.get(self.workspace_id, {})
        context = {"file": doc["path"][:4000] if doc else "",
                   "selection": doc["editor"].selected_text()[:4000] if doc else "",
                   "error": self.request.toPlainText()[:4000]}
        self.manager.open("research").prefill(
            self.request.toPlainText() or "Research the selected code using current documentation",
            workspace.get("project_id"), context)

    def ask(self):
        if not self.workspace_id:
            return
        doc = self.active_document()
        self.ai_status.setText("Working…")
        self.call(
            "studio.ask",
            lambda v, e: self.ai_status.setText(e or (v or {}).get("completion_summary") or "Task finished"),
            workspace_id=self.workspace_id,
            request=self.request.toPlainText(),
            path=doc["path"] if doc else "",
            selection=doc["editor"].selected_text() if doc else "",
        )

    def inline_action(self, name):
        self.request.setPlainText(name)
        self.assistant_dock.show()
        self.assistant_dock.raise_()
        self.request.setFocus()

    def run(self):
        if self.workspace_id:
            self.call("studio.run", self.started, workspace_id=self.workspace_id)

    def started(self, value, error):
        if value:
            self.session_id = value["session_id"]
            self.output_dock.show()
            self.output_dock.raise_()

    def stop(self):
        if self.session_id:
            self.call("studio.stop", session_id=self.session_id)

    def restart(self):
        if self.workspace_id:
            self.call(
                "studio.restart", self.started, workspace_id=self.workspace_id, session_id=self.session_id
            )

    def run_tests(self):
        if self.workspace_id:
            self.call(
                "studio.validate",
                lambda v, e: (
                    self.output.setPlainText(
                        "\n\n".join(
                            f"{r['name']} - exit {r['exit_code']}\n{r['stdout']}\n{r['stderr']}"
                            for r in v.get("results", [])
                        )
                    )
                    if v
                    else None
                ),
                workspace_id=self.workspace_id,
            )

    def run_terminal(self):
        if self.workspace_id and self.command.text().strip():
            self.terminal_output.appendPlainText(f"> {self.command.text()}")
            self.call("studio.terminal", workspace_id=self.workspace_id, command=self.command.text())
            self.command.clear()

    def git_status(self):
        self.git_action("status")

    def git_action(self, action, **arguments):
        if self.workspace_id:
            self.call(
                "studio.git", self.render_git, workspace_id=self.workspace_id, action=action, **arguments
            )

    def render_git(self, value, error):
        if value is None:
            return
        if "entries" in value:
            self.git_branch.setText("Branch: " + value.get("branch", ""))
            populate(self.git_files, value["entries"], ["path", "index", "worktree"])
        elif "diff" in value:
            self.git_output.setPlainText(value["diff"] or "No changes")
        elif "commits" in value:
            self.git_output.setPlainText(
                "\n".join(f"{c['short_hash']}  {c['subject']}" for c in value["commits"])
            )
        elif "branches" in value:
            self.git_output.setPlainText(
                "\n".join(("* " if b["current"] else "  ") + b["name"] for b in value["branches"])
            )
        else:
            self.git_output.setPlainText(str(value.get("result", "Git action completed")))

    def git_stage(self):
        doc = self.active_document()
        if doc:
            self.git_action("add", files=[doc["path"]])

    def git_commit(self):
        message, ok = QInputDialog.getText(self, "Commit staged files", "Commit message")
        if ok and message:
            self.git_action("commit", message=message)

    def open_problem(self):
        value = selected(self.problems)
        if value and value.get("file"):
            self.open_file(value["file"], value.get("line") or 1)

    def open_preview(self):
        if not getattr(self, "local_url", None):
            self.statusBar().showMessage("No localhost URL reported by the active RunSession", 6000)
            return
        from .preview import PreviewWindow, local_origin

        if self.preview is not None and self.preview.origin != local_origin(self.local_url):
            self.preview.dispose()
            self.preview = None
        if self.preview is None:
            self.preview = PreviewWindow(self.local_url, self)
        self.preview.show()
        self.preview.raise_()

    def on_event(self, topic, value):
        super().on_event(topic, value)
        if topic == "workspaces":
            self.workspaces_loaded(value, "")
        elif topic == "run" and value["workspace_id"] == self.workspace_id:
            self.session_id = value["id"]
            self.local_url = value.get("local_url")
            self.output.setPlainText(
                f"RUN · {value['state']} · PID {value['process_id']}\n"
                + value["stdout"]
                + "\n"
                + value["stderr"]
            )
        elif topic == "problems" and value["workspace_id"] == self.workspace_id:
            populate(
                self.problems, value["items"], ["severity", "file", "line", "error_code", "message", "tool"]
            )
            for doc in self.documents.values():
                doc["editor"].set_diagnostics([p for p in value["items"] if p.get("file") == doc["path"]])
        elif topic == "tests" and value["workspace_id"] == self.workspace_id:
            populate(self.tests, value["items"], ["name", "state", "duration_seconds", "message", "file"])
        elif topic == "terminal_stream" and value["workspace_id"] == self.workspace_id:
            self.terminal_output.setPlainText(value["channel"] + "\n" + value["text"])
        elif topic == "terminal" and value["workspace_id"] == self.workspace_id:
            self.terminal_output.appendPlainText(
                value.get("stdout", "") + "\n" + value.get("stderr", "") + f"\nExit: {value.get('exit_code')}"
            )
        elif topic == "agent":
            self.ai_status.setText(value["state"])
        elif topic == "settings":
            from PySide6.QtGui import QFont

            settings = value["settings"]
            for doc in self.documents.values():
                editor = doc["editor"]
                editor.setFont(
                    QFont(settings.get("editor_font", "Consolas"), int(settings.get("editor_size", 13)))
                )
                editor.tab_spaces = int(settings.get("editor_tab_width", 4))
                editor.setTabStopDistance(editor.fontMetrics().horizontalAdvance(" ") * editor.tab_spaces)
