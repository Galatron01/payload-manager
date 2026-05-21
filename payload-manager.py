#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
import os, subprocess, json

PAYLOADS_DIR = os.path.expanduser("~/payloads")
TESTTYPES_FILE = os.path.join(PAYLOADS_DIR, ".testtypes.json")
os.makedirs(PAYLOADS_DIR, exist_ok=True)

DEFAULT_TYPES = ["Web Test", "External Network", "Internal", "API"]


class PayloadWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Payload Manager")
        self.set_default_size(1050, 650)
        self.current_category = None
        self.current_testtype = None   # None = All Types
        self._updating_tags = False
        self.tt_data = self._load_tt_data()

        css = Gtk.CssProvider()
        css.load_from_string("""
            .payload-row { padding: 6px 10px; font-family: monospace; }
            .cat-row  { padding: 6px 10px; }
            .tt-row   { padding: 5px 10px; }
            .cat-hint { padding: 0 10px; font-size: 0.75em; opacity: 0.6; }
            .status   { padding: 4px 8px; opacity: 0.7; }
            .copied   { color: #50fa7b; }
        """)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(root)

        # ── Left panel ────────────────────────────────────────────
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_size_request(200, -1)
        left.set_margin_start(10); left.set_margin_end(6)
        left.set_margin_top(10);   left.set_margin_bottom(10)

        # Test Types section
        tt_lbl = Gtk.Label(label="Test Types", xalign=0)
        tt_lbl.add_css_class("heading")
        left.append(tt_lbl)

        self.tt_list = Gtk.ListBox()
        self.tt_list.connect("row-selected", self.on_testtype_selected)
        tt_scroll = Gtk.ScrolledWindow()
        tt_scroll.set_min_content_height(100)
        tt_scroll.set_max_content_height(180)
        tt_scroll.set_vexpand(False)
        tt_scroll.set_child(self.tt_list)
        left.append(tt_scroll)

        tt_btns = Gtk.Box(spacing=6)
        add_tt = Gtk.Button(label="+ Type")
        add_tt.connect("clicked", self.on_add_testtype)
        del_tt = Gtk.Button(label="Delete")
        del_tt.connect("clicked", self.on_delete_testtype)
        tt_btns.append(add_tt); tt_btns.append(del_tt)
        left.append(tt_btns)

        left.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Categories section
        cat_lbl = Gtk.Label(label="Categories", xalign=0)
        cat_lbl.add_css_class("heading")
        left.append(cat_lbl)

        self.cat_list = Gtk.ListBox()
        self.cat_list.set_vexpand(True)
        self.cat_list.connect("row-selected", self.on_category_selected)
        cat_scroll = Gtk.ScrolledWindow(vexpand=True)
        cat_scroll.set_child(self.cat_list)
        left.append(cat_scroll)

        cat_btns = Gtk.Box(spacing=6)
        add_cat = Gtk.Button(label="+ Category")
        add_cat.connect("clicked", self.on_add_category)
        del_cat = Gtk.Button(label="Delete")
        del_cat.connect("clicked", self.on_delete_category)
        cat_btns.append(add_cat); cat_btns.append(del_cat)
        left.append(cat_btns)

        root.append(left)
        root.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # ── Right panel ───────────────────────────────────────────
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right.set_hexpand(True)
        right.set_margin_start(6); right.set_margin_end(10)
        right.set_margin_top(10);  right.set_margin_bottom(10)

        top_bar = Gtk.Box(spacing=6)
        self.cat_title = Gtk.Label(label="Select a category", xalign=0)
        self.cat_title.set_hexpand(True)
        self.cat_title.add_css_class("heading")
        self.search = Gtk.SearchEntry(placeholder_text="Filter payloads...")
        self.search.connect("search-changed", self.on_search)
        top_bar.append(self.cat_title); top_bar.append(self.search)
        right.append(top_bar)

        self.payload_list = Gtk.ListBox()
        self.payload_list.set_vexpand(True)
        self.payload_list.set_filter_func(self.filter_payloads)
        self.payload_list.connect("row-activated", self.on_payload_clicked)
        self.payload_list.connect("row-selected",  self.on_payload_selected)
        payload_scroll = Gtk.ScrolledWindow(vexpand=True)
        payload_scroll.set_child(self.payload_list)
        right.append(payload_scroll)

        # Input bar
        add_box = Gtk.Box(spacing=6)
        self.payload_entry = Gtk.Entry(hexpand=True, placeholder_text="New payload — press Enter to add")
        self.payload_entry.connect("activate", self.on_add_payload)
        add_btn = Gtk.Button(label="Add")
        add_btn.connect("clicked", self.on_add_payload)
        del_btn = Gtk.Button(label="Delete selected")
        del_btn.connect("clicked", self.on_delete_payload)
        imp_btn = Gtk.Button(label="Import file…")
        imp_btn.connect("clicked", self.on_import_file)
        exp_btn = Gtk.Button(label="Export…")
        exp_btn.connect("clicked", self.on_export_file)
        add_box.append(self.payload_entry); add_box.append(add_btn)
        add_box.append(del_btn); add_box.append(imp_btn); add_box.append(exp_btn)
        right.append(add_box)

        # Tag bar — checkboxes for each test type
        self.tag_bar = Gtk.Box(spacing=8)
        self.tag_bar_lbl = Gtk.Label(label="Assign to:", xalign=0)
        self.tag_bar.append(self.tag_bar_lbl)
        self.tag_toggles = {}
        self._rebuild_tag_bar()
        right.append(self.tag_bar)

        self.status = Gtk.Label(label="Click a payload to copy to clipboard", xalign=0)
        self.status.add_css_class("status")
        right.append(self.status)

        root.append(right)
        self.load_testtypes()
        self.load_categories()

    # ── Test type data ────────────────────────────────────────────

    def _load_tt_data(self):
        if os.path.exists(TESTTYPES_FILE):
            with open(TESTTYPES_FILE) as f:
                try:
                    return json.load(f)
                except Exception:
                    pass
        return {"types": list(DEFAULT_TYPES), "assignments": {}}

    def _save_tt_data(self):
        with open(TESTTYPES_FILE, "w") as f:
            json.dump(self.tt_data, f, indent=2)

    def _tt_key(self, category, payload):
        # Use null byte as separator — safe since it can't appear in either field
        return f"{category}\x00{payload}"

    def _payload_testtypes(self, category, payload):
        return self.tt_data["assignments"].get(self._tt_key(category, payload), [])

    def _set_payload_testtype(self, category, payload, type_name, active):
        key = self._tt_key(category, payload)
        types = list(self.tt_data["assignments"].get(key, []))
        if active and type_name not in types:
            types.append(type_name)
        elif not active and type_name in types:
            types.remove(type_name)
        if types:
            self.tt_data["assignments"][key] = types
        elif key in self.tt_data["assignments"]:
            del self.tt_data["assignments"][key]
        self._save_tt_data()

    # ── Test types UI ─────────────────────────────────────────────

    def load_testtypes(self):
        while row := self.tt_list.get_row_at_index(0):
            self.tt_list.remove(row)
        for label, name in [("All Types", None)] + [(t, t) for t in self.tt_data["types"]]:
            lbl = Gtk.Label(label=label, xalign=0)
            lbl.add_css_class("tt-row")
            row = Gtk.ListBoxRow()
            row.set_child(lbl)
            row.tt_name = name
            self.tt_list.append(row)
        self.tt_list.select_row(self.tt_list.get_row_at_index(0))

    def on_testtype_selected(self, listbox, row):
        if row is None:
            return
        self.current_testtype = row.tt_name
        self.load_payloads()

    def on_add_testtype(self, btn):
        win = Gtk.Window(transient_for=self, modal=True, title="New Test Type")
        win.set_default_size(300, 80)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(12); box.set_margin_end(12)
        box.set_margin_top(12);   box.set_margin_bottom(12)
        entry = Gtk.Entry(placeholder_text="Test type name")
        btn2 = Gtk.Button(label="Create")
        box.append(entry); box.append(btn2)
        win.set_child(box)
        def create(w):
            name = entry.get_text().strip()
            if name and name not in self.tt_data["types"]:
                self.tt_data["types"].append(name)
                self._save_tt_data()
                self.load_testtypes()
                self._rebuild_tag_bar()
            win.close()
        btn2.connect("clicked", create)
        entry.connect("activate", create)
        win.present()

    def on_delete_testtype(self, btn):
        row = self.tt_list.get_selected_row()
        if row is None or row.tt_name is None:
            return
        name = row.tt_name
        self.tt_data["types"] = [t for t in self.tt_data["types"] if t != name]
        for key in list(self.tt_data["assignments"]):
            types = [t for t in self.tt_data["assignments"][key] if t != name]
            if types:
                self.tt_data["assignments"][key] = types
            else:
                del self.tt_data["assignments"][key]
        self._save_tt_data()
        if self.current_testtype == name:
            self.current_testtype = None
        self.load_testtypes()
        self._rebuild_tag_bar()
        self.load_payloads()

    def _rebuild_tag_bar(self):
        for cb in self.tag_toggles.values():
            self.tag_bar.remove(cb)
        self.tag_toggles.clear()
        for t in self.tt_data["types"]:
            cb = Gtk.CheckButton(label=t)
            cb.set_sensitive(False)
            cb.connect("toggled", self._on_tag_toggled, t)
            self.tag_bar.append(cb)
            self.tag_toggles[t] = cb

    def on_payload_selected(self, listbox, row):
        if row is None:
            for cb in self.tag_toggles.values():
                cb.set_sensitive(False)
            return
        self._update_tag_bar(row)

    def _update_tag_bar(self, row):
        self._updating_tags = True
        cat = getattr(row, "source_category", self.current_category)
        assigned = self._payload_testtypes(cat, row.payload) if cat else []
        for t, cb in self.tag_toggles.items():
            cb.set_active(t in assigned)
            cb.set_sensitive(True)
        self._updating_tags = False

    def _on_tag_toggled(self, cb, type_name):
        if self._updating_tags:
            return
        row = self.payload_list.get_selected_row()
        if row is None:
            return
        cat = getattr(row, "source_category", self.current_category)
        if cat:
            self._set_payload_testtype(cat, row.payload, type_name, cb.get_active())
        if self.current_testtype is not None:
            self.payload_list.invalidate_filter()

    # ── Categories ────────────────────────────────────────────────

    def load_categories(self):
        while row := self.cat_list.get_row_at_index(0):
            self.cat_list.remove(row)
        for f in sorted(os.listdir(PAYLOADS_DIR)):
            if f.endswith(".txt"):
                lbl = Gtk.Label(label=f[:-4], xalign=0)
                lbl.add_css_class("cat-row")
                row = Gtk.ListBoxRow()
                row.set_child(lbl)
                row.category = f[:-4]
                self.cat_list.append(row)

    def on_category_selected(self, listbox, row):
        if row is None:
            return
        self.current_category = row.category
        self.load_payloads()

    def on_add_category(self, btn):
        win = Gtk.Window(transient_for=self, modal=True, title="New Category")
        win.set_default_size(300, 80)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(12); box.set_margin_end(12)
        box.set_margin_top(12);   box.set_margin_bottom(12)
        entry = Gtk.Entry(placeholder_text="Category name")
        btn2 = Gtk.Button(label="Create")
        box.append(entry); box.append(btn2)
        win.set_child(box)
        def create(w):
            name = entry.get_text().strip()
            if name:
                open(os.path.join(PAYLOADS_DIR, f"{name}.txt"), "a").close()
                self.load_categories()
            win.close()
        btn2.connect("clicked", create)
        entry.connect("activate", create)
        win.present()

    def on_delete_category(self, btn):
        if not self.current_category:
            return
        path = os.path.join(PAYLOADS_DIR, f"{self.current_category}.txt")
        if os.path.exists(path):
            os.remove(path)
        self.current_category = None
        self.load_categories()
        self.load_payloads()

    # ── Payloads ──────────────────────────────────────────────────

    def load_payloads(self):
        while row := self.payload_list.get_row_at_index(0):
            self.payload_list.remove(row)
        for cb in self.tag_toggles.values():
            cb.set_sensitive(False)

        if self.current_category:
            # Single category view
            path = os.path.join(PAYLOADS_DIR, f"{self.current_category}.txt")
            if os.path.exists(path):
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self._add_payload_row(line, self.current_category)
            title = self.current_category
            if self.current_testtype:
                title = f"{self.current_testtype}  ›  {self.current_category}"
            self.cat_title.set_text(title)

        elif self.current_testtype:
            # No category: show all payloads tagged with this type across all categories
            for fname in sorted(os.listdir(PAYLOADS_DIR)):
                if not fname.endswith(".txt"):
                    continue
                cat = fname[:-4]
                with open(os.path.join(PAYLOADS_DIR, fname)) as f:
                    for line in f:
                        line = line.strip()
                        if line and self.current_testtype in self._payload_testtypes(cat, line):
                            self._add_payload_row(line, cat, show_category=True)
            self.cat_title.set_text(self.current_testtype)

        else:
            self.cat_title.set_text("Select a category")

        self.payload_list.invalidate_filter()

    def _add_payload_row(self, text, category, show_category=False):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        if show_category:
            hint = Gtk.Label(label=category, xalign=0)
            hint.add_css_class("cat-hint")
            box.append(hint)
        lbl = Gtk.Label(label=text, xalign=0)
        lbl.set_ellipsize(3)
        lbl.add_css_class("payload-row")
        box.append(lbl)
        row = Gtk.ListBoxRow()
        row.set_child(box)
        row.payload = text
        row.source_category = category
        self.payload_list.append(row)

    def _save_category_to_disk(self, category):
        # In single-category view the list holds ALL rows for this category (GTK hides
        # filtered rows but keeps them in the list), so we can safely reconstruct.
        payloads = []
        i = 0
        while row := self.payload_list.get_row_at_index(i):
            if getattr(row, "source_category", None) == category:
                payloads.append(row.payload)
            i += 1
        path = os.path.join(PAYLOADS_DIR, f"{category}.txt")
        with open(path, "w") as f:
            f.write("\n".join(payloads) + "\n")

    def _delete_payload_from_file(self, category, payload_text):
        # Used in cross-category view where the list only shows tagged payloads —
        # read the file directly and remove one occurrence to avoid data loss.
        path = os.path.join(PAYLOADS_DIR, f"{category}.txt")
        if not os.path.exists(path):
            return
        with open(path) as f:
            lines = [l.strip() for l in f if l.strip()]
        try:
            lines.remove(payload_text)
        except ValueError:
            pass
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")

    def save_payloads(self):
        if self.current_category:
            self._save_category_to_disk(self.current_category)

    def on_payload_clicked(self, listbox, row):
        subprocess.run(["wl-copy", row.payload])
        short = row.payload[:60] + "..." if len(row.payload) > 60 else row.payload
        self.status.set_text(f"Copied: {short}")
        self.status.add_css_class("copied")
        GLib.timeout_add(2000, self.reset_status)

    def reset_status(self):
        self.status.set_text("Click a payload to copy to clipboard")
        self.status.remove_css_class("copied")
        return False

    def on_add_payload(self, widget):
        if not self.current_category:
            return
        text = self.payload_entry.get_text().strip()
        if not text:
            return
        self._add_payload_row(text, self.current_category)
        self.save_payloads()
        self.payload_entry.set_text("")

    def on_delete_payload(self, btn):
        row = self.payload_list.get_selected_row()
        if not row:
            return
        cat = getattr(row, "source_category", self.current_category)
        payload_text = row.payload
        self.payload_list.remove(row)
        if not cat:
            return
        if self.current_category == cat:
            self._save_category_to_disk(cat)
        else:
            self._delete_payload_from_file(cat, payload_text)

    def on_search(self, entry):
        self.payload_list.invalidate_filter()

    def filter_payloads(self, row):
        query = self.search.get_text().lower()
        if query and query not in row.payload.lower():
            return False
        # Test type filter only applies in single-category view
        # (cross-category view pre-filters at load time)
        if self.current_testtype and self.current_category:
            cat = getattr(row, "source_category", self.current_category)
            return self.current_testtype in self._payload_testtypes(cat, row.payload)
        return True

    # ── Import ────────────────────────────────────────────────────

    def on_import_file(self, btn):
        dialog = Gtk.FileChooserDialog(
            title="Import payloads from file",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons("_Cancel", Gtk.ResponseType.CANCEL,
                           "_Import", Gtk.ResponseType.ACCEPT)

        f_all = Gtk.FileFilter()
        f_all.set_name("Text & JSON files")
        f_all.add_pattern("*.txt"); f_all.add_pattern("*.json")

        f_txt = Gtk.FileFilter()
        f_txt.set_name("Text files (*.txt)"); f_txt.add_pattern("*.txt")

        f_json = Gtk.FileFilter()
        f_json.set_name("JSON files (*.json)"); f_json.add_pattern("*.json")

        dialog.add_filter(f_all)
        dialog.add_filter(f_txt)
        dialog.add_filter(f_json)
        dialog.connect("response", self._on_import_response)
        dialog.present()

    def _on_import_response(self, dialog, response):
        if response != Gtk.ResponseType.ACCEPT:
            dialog.destroy()
            return
        path = dialog.get_file().get_path()
        dialog.destroy()
        if path.endswith(".json"):
            self._import_json(path)
        else:
            self._import_txt(path)

    def _import_txt(self, path):
        if not self.current_category:
            self._show_error("Select a category before importing a text file.")
            return
        with open(path) as f:
            lines = [l.strip() for l in f if l.strip()]
        if not lines:
            self.status.set_text("Import: file was empty.")
            return
        for line in lines:
            self._add_payload_row(line, self.current_category)
        self.save_payloads()
        self.status.set_text(f"Imported {len(lines)} payload(s) from {os.path.basename(path)}")

    def _import_json(self, path):
        with open(path) as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                self._show_error(f"Invalid JSON: {e}")
                return

        if isinstance(data, list):
            if not self.current_category:
                self._show_error("Select a category before importing a JSON array.")
                return
            items = [str(x) for x in data if str(x).strip()]
            for item in items:
                self._add_payload_row(item, self.current_category)
            self.save_payloads()
            self.status.set_text(f"Imported {len(items)} payload(s) from {os.path.basename(path)}")
            return

        if isinstance(data, dict):
            total = 0
            for cat_name, payloads in data.items():
                cat_name = str(cat_name).strip()
                if not cat_name:
                    continue
                if isinstance(payloads, list):
                    lines = [str(p).strip() for p in payloads if str(p).strip()]
                elif isinstance(payloads, str):
                    lines = [l.strip() for l in payloads.splitlines() if l.strip()]
                else:
                    lines = [str(payloads).strip()] if str(payloads).strip() else []
                cat_path = os.path.join(PAYLOADS_DIR, f"{cat_name}.txt")
                existing = []
                if os.path.exists(cat_path):
                    with open(cat_path) as cf:
                        existing = [l.strip() for l in cf if l.strip()]
                with open(cat_path, "w") as cf:
                    cf.write("\n".join(existing + lines) + "\n")
                total += len(lines)
            self.load_categories()
            if self.current_category:
                self.load_payloads()
            self.status.set_text(
                f"Imported {total} payload(s) across {len(data)} category/categories from {os.path.basename(path)}"
            )
            return

        self._show_error("JSON must be an array of strings or an object mapping category names to arrays.")

    # ── Export ────────────────────────────────────────────────────

    def on_export_file(self, btn):
        if not self.current_category:
            self._show_error("Select a category before exporting.")
            return
        dlg = Gtk.Window(transient_for=self, modal=True, title="Export format")
        dlg.set_default_size(260, 120)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(16); box.set_margin_end(16)
        box.set_margin_top(16);   box.set_margin_bottom(16)
        lbl = Gtk.Label(label="Choose export format:", xalign=0)
        btns = Gtk.Box(spacing=8, homogeneous=True)
        btn_txt  = Gtk.Button(label="Text (.txt)")
        btn_json = Gtk.Button(label="JSON (.json)")
        btn_all  = Gtk.Button(label="All categories (.json)")
        btns.append(btn_txt); btns.append(btn_json)
        box.append(lbl); box.append(btns); box.append(btn_all)
        dlg.set_child(box)
        def pick(fmt):
            dlg.close()
            self._open_save_dialog(fmt)
        btn_txt.connect("clicked",  lambda _: pick("txt"))
        btn_json.connect("clicked", lambda _: pick("json"))
        btn_all.connect("clicked",  lambda _: pick("json_all"))
        dlg.present()

    def _open_save_dialog(self, fmt):
        titles = {
            "txt": "Export as text",
            "json": "Export as JSON",
            "json_all": "Export all categories as JSON",
        }
        dialog = Gtk.FileChooserDialog(
            title=titles[fmt], transient_for=self, action=Gtk.FileChooserAction.SAVE,
        )
        dialog.set_current_name(
            f"{self.current_category}.txt" if fmt == "txt"
            else ("payloads.json" if fmt == "json_all" else f"{self.current_category}.json")
        )
        dialog.add_buttons("_Cancel", Gtk.ResponseType.CANCEL, "_Save", Gtk.ResponseType.ACCEPT)
        ff = Gtk.FileFilter()
        if fmt == "txt":
            ff.set_name("Text files (*.txt)"); ff.add_pattern("*.txt")
        else:
            ff.set_name("JSON files (*.json)"); ff.add_pattern("*.json")
        dialog.add_filter(ff)
        dialog.connect("response", self._on_export_response, fmt)
        dialog.present()

    def _on_export_response(self, dialog, response, fmt):
        if response != Gtk.ResponseType.ACCEPT:
            dialog.destroy()
            return
        path = dialog.get_file().get_path()
        dialog.destroy()
        if fmt == "txt":
            self._export_txt(path)
        elif fmt == "json":
            self._export_json(path)
        else:
            self._export_json_all(path)

    def _export_txt(self, path):
        payloads = self._current_payloads()
        with open(path, "w") as f:
            f.write("\n".join(payloads) + "\n")
        self.status.set_text(f"Exported {len(payloads)} payload(s) to {os.path.basename(path)}")

    def _export_json(self, path):
        payloads = self._current_payloads()
        with open(path, "w") as f:
            json.dump(payloads, f, indent=2)
        self.status.set_text(f"Exported {len(payloads)} payload(s) to {os.path.basename(path)}")

    def _export_json_all(self, path):
        data = {}
        for fname in sorted(os.listdir(PAYLOADS_DIR)):
            if fname.endswith(".txt"):
                cat = fname[:-4]
                with open(os.path.join(PAYLOADS_DIR, fname)) as f:
                    data[cat] = [l.strip() for l in f if l.strip()]
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        total = sum(len(v) for v in data.values())
        self.status.set_text(
            f"Exported {total} payload(s) across {len(data)} categories to {os.path.basename(path)}"
        )

    def _current_payloads(self):
        payloads = []
        i = 0
        while row := self.payload_list.get_row_at_index(i):
            payloads.append(row.payload)
            i += 1
        return payloads

    def _show_error(self, msg):
        dlg = Gtk.MessageDialog(
            transient_for=self, modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK, text=msg,
        )
        dlg.connect("response", lambda d, _: d.destroy())
        dlg.present()


class PayloadApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.stargazer.payloads")

    def do_activate(self):
        win = PayloadWindow(self)
        win.present()


PayloadApp().run()
