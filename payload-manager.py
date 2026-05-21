#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
import os, subprocess, json

PAYLOADS_DIR = os.path.expanduser("~/payloads")
TESTTYPES_FILE = os.path.join(PAYLOADS_DIR, ".testtypes.json")
os.makedirs(PAYLOADS_DIR, exist_ok=True)

DEFAULT_TYPES = ["Web Test", "External Network", "Internal", "API"]

CSS = """
/* ── Layout ── */
.sidebar        { background-color: alpha(@card_bg_color, 0.5); }
.cat-row        { padding: 7px 14px; font-size: 0.95em; }
.cat-hint       { padding: 0 12px; font-size: 0.72em; opacity: 0.55; }
.payload-row    { padding: 6px 12px; font-family: monospace; font-size: 0.88em; }
.section-label  { padding: 4px 6px; font-size: 0.78em; font-weight: bold;
                  letter-spacing: 0.08em; opacity: 0.6; }
.status-bar     { padding: 4px 10px; font-size: 0.85em; opacity: 0.75; }
.copied         { color: #2ec27e; opacity: 1; }

/* ── Test type chips ── */
.tt-chip        { border-radius: 99px; padding: 3px 14px;
                  background: alpha(@card_bg_color, 0.6); font-size: 0.85em; }
.tt-chip:hover  { background: alpha(@accent_bg_color, 0.25); }
.tt-chip:checked { background: @accent_bg_color; color: @accent_fg_color; }

/* ── Coloured buttons ── */
.btn-add        { background: #2ec27e; color: white; font-weight: bold; }
.btn-add:hover  { background: #26a96c; }
.btn-del        { background: #e01b24; color: white; font-weight: bold; }
.btn-del:hover  { background: #c0161e; }
.btn-import     { background: #1c71d8; color: white; font-weight: bold; }
.btn-import:hover { background: #1660c0; }
.btn-export     { background: #e5a50a; color: white; font-weight: bold; }
.btn-export:hover { background: #c88e08; }
.btn-manage     { font-size: 0.8em; opacity: 0.75; }
"""


class PayloadWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Payload Manager")
        self.set_default_size(1100, 680)
        self.current_category = None
        self.current_testtype = None   # None = All
        self._updating_tags = False
        self.tt_data = self._load_tt_data()
        self._tt_buttons = {}          # type_name → ToggleButton

        css = Gtk.CssProvider()
        css.load_from_string(CSS)
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(root)

        # ── Left sidebar ──────────────────────────────────────────
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sidebar.add_css_class("sidebar")
        sidebar.set_size_request(210, -1)
        sidebar.set_margin_start(0); sidebar.set_margin_end(0)
        sidebar.set_margin_top(14);  sidebar.set_margin_bottom(10)

        cat_hdr = Gtk.Label(label="CATEGORIES", xalign=0)
        cat_hdr.add_css_class("section-label")
        cat_hdr.set_margin_start(10)
        sidebar.append(cat_hdr)

        self.cat_list = Gtk.ListBox()
        self.cat_list.set_vexpand(True)
        self.cat_list.connect("row-selected", self.on_category_selected)
        cat_scroll = Gtk.ScrolledWindow(vexpand=True)
        cat_scroll.set_child(self.cat_list)
        sidebar.append(cat_scroll)

        # Category buttons
        cat_btns = Gtk.Box(spacing=6, homogeneous=True)
        cat_btns.set_margin_start(8); cat_btns.set_margin_end(8)
        cat_btns.set_margin_top(4);   cat_btns.set_margin_bottom(8)
        add_cat = Gtk.Button(label="＋ New")
        add_cat.add_css_class("btn-add")
        add_cat.connect("clicked", self.on_add_category)
        del_cat = Gtk.Button(label="✕ Delete")
        del_cat.add_css_class("btn-del")
        del_cat.connect("clicked", self.on_delete_category)
        cat_btns.append(add_cat); cat_btns.append(del_cat)
        sidebar.append(cat_btns)

        root.append(sidebar)
        root.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))

        # ── Right panel ───────────────────────────────────────────
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        right.set_hexpand(True)
        right.set_margin_start(12); right.set_margin_end(12)
        right.set_margin_top(12);   right.set_margin_bottom(10)

        # Title + search row
        top_bar = Gtk.Box(spacing=8)
        top_bar.set_margin_bottom(8)
        self.cat_title = Gtk.Label(label="Select a category", xalign=0)
        self.cat_title.set_hexpand(True)
        self.cat_title.add_css_class("heading")
        self.search = Gtk.SearchEntry(placeholder_text="Search payloads…")
        self.search.set_size_request(220, -1)
        self.search.connect("search-changed", self.on_search)
        top_bar.append(self.cat_title)
        top_bar.append(self.search)
        right.append(top_bar)

        # Test type chip bar
        tt_bar_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        tt_bar_wrap.set_margin_bottom(8)

        tt_bar_hdr = Gtk.Box(spacing=6)
        tt_type_lbl = Gtk.Label(label="FILTER BY TEST TYPE", xalign=0)
        tt_type_lbl.add_css_class("section-label")
        tt_type_lbl.set_hexpand(True)
        manage_btn = Gtk.Button(label="Manage types…")
        manage_btn.add_css_class("btn-manage")
        manage_btn.connect("clicked", self.on_manage_testtypes)
        tt_bar_hdr.append(tt_type_lbl)
        tt_bar_hdr.append(manage_btn)
        tt_bar_wrap.append(tt_bar_hdr)

        self.tt_chip_bar = Gtk.Box(spacing=6)
        self.tt_chip_bar.set_margin_top(4)
        self._build_chip_bar()
        tt_chip_scroll = Gtk.ScrolledWindow()
        tt_chip_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        tt_chip_scroll.set_child(self.tt_chip_bar)
        tt_bar_wrap.append(tt_chip_scroll)
        right.append(tt_bar_wrap)

        right.append(Gtk.Separator())

        # Payload list
        self.payload_list = Gtk.ListBox()
        self.payload_list.set_vexpand(True)
        self.payload_list.set_filter_func(self.filter_payloads)
        self.payload_list.connect("row-activated", self.on_payload_clicked)
        self.payload_list.connect("row-selected",  self.on_payload_selected)
        payload_scroll = Gtk.ScrolledWindow(vexpand=True)
        payload_scroll.set_child(self.payload_list)
        payload_scroll.set_margin_top(6)
        right.append(payload_scroll)

        right.append(Gtk.Separator())

        # Input / action bar
        action_bar = Gtk.Box(spacing=6)
        action_bar.set_margin_top(8)
        self.payload_entry = Gtk.Entry(hexpand=True, placeholder_text="Type a payload and press Enter to add…")
        self.payload_entry.connect("activate", self.on_add_payload)

        btn_add = Gtk.Button(label="＋ Add")
        btn_add.add_css_class("btn-add")
        btn_add.connect("clicked", self.on_add_payload)

        btn_del = Gtk.Button(label="✕ Delete")
        btn_del.add_css_class("btn-del")
        btn_del.connect("clicked", self.on_delete_payload)

        btn_imp = Gtk.Button(label="⬆ Import")
        btn_imp.add_css_class("btn-import")
        btn_imp.connect("clicked", self.on_import_file)

        btn_exp = Gtk.Button(label="⬇ Export")
        btn_exp.add_css_class("btn-export")
        btn_exp.connect("clicked", self.on_export_file)

        action_bar.append(self.payload_entry)
        action_bar.append(btn_add)
        action_bar.append(btn_del)
        action_bar.append(btn_imp)
        action_bar.append(btn_exp)
        right.append(action_bar)

        # Tag assignment bar
        tag_bar = Gtk.Box(spacing=8)
        tag_bar.set_margin_top(6)
        tag_lbl = Gtk.Label(label="Assign to:", xalign=0)
        tag_lbl.add_css_class("section-label")
        tag_bar.append(tag_lbl)
        self.tag_toggles = {}
        self.tag_bar_box = tag_bar
        self._rebuild_tag_bar()
        right.append(tag_bar)

        # Status bar
        self.status = Gtk.Label(label="Click a payload to copy to clipboard", xalign=0)
        self.status.add_css_class("status-bar")
        self.status.set_margin_top(2)
        right.append(self.status)

        root.append(right)
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

    # ── Test type chip bar ────────────────────────────────────────

    def _build_chip_bar(self):
        while self.tt_chip_bar.get_first_child():
            self.tt_chip_bar.remove(self.tt_chip_bar.get_first_child())
        self._tt_buttons.clear()

        all_btn = Gtk.ToggleButton(label="All")
        all_btn.add_css_class("tt-chip")
        all_btn.set_active(self.current_testtype is None)
        all_btn.connect("clicked", self._on_chip_clicked, None)
        self.tt_chip_bar.append(all_btn)
        self._tt_buttons[None] = all_btn

        for t in self.tt_data["types"]:
            btn = Gtk.ToggleButton(label=t)
            btn.add_css_class("tt-chip")
            btn.set_active(self.current_testtype == t)
            btn.connect("clicked", self._on_chip_clicked, t)
            self.tt_chip_bar.append(btn)
            self._tt_buttons[t] = btn

    def _on_chip_clicked(self, btn, type_name):
        if not btn.get_active():
            # Don't allow deselecting — always keep one active
            btn.set_active(True)
            return
        self.current_testtype = type_name
        # Deactivate all others
        for k, b in self._tt_buttons.items():
            if k != type_name:
                b.set_active(False)
        self.load_payloads()

    def on_manage_testtypes(self, btn):
        win = Gtk.Window(transient_for=self, modal=True, title="Manage Test Types")
        win.set_default_size(320, 340)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        outer.set_margin_start(14); outer.set_margin_end(14)
        outer.set_margin_top(14);   outer.set_margin_bottom(14)

        outer.append(Gtk.Label(label="Test types:", xalign=0))

        self._manage_list = Gtk.ListBox()
        self._manage_list.set_vexpand(True)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self._manage_list)
        outer.append(scroll)

        def refresh_list():
            while r := self._manage_list.get_row_at_index(0):
                self._manage_list.remove(r)
            for t in self.tt_data["types"]:
                lbl = Gtk.Label(label=t, xalign=0)
                lbl.set_margin_start(8); lbl.set_margin_top(5); lbl.set_margin_bottom(5)
                row = Gtk.ListBoxRow()
                row.set_child(lbl)
                row.tt_name = t
                self._manage_list.append(row)

        refresh_list()

        # Add row
        add_row = Gtk.Box(spacing=6)
        new_entry = Gtk.Entry(hexpand=True, placeholder_text="New type name…")
        add_btn = Gtk.Button(label="＋ Add")
        add_btn.add_css_class("btn-add")
        add_row.append(new_entry); add_row.append(add_btn)
        outer.append(add_row)

        del_btn = Gtk.Button(label="✕ Delete selected")
        del_btn.add_css_class("btn-del")
        outer.append(del_btn)

        close_btn = Gtk.Button(label="Done")
        close_btn.add_css_class("suggested-action")
        outer.append(close_btn)

        win.set_child(outer)

        def add_type(w):
            name = new_entry.get_text().strip()
            if name and name not in self.tt_data["types"]:
                self.tt_data["types"].append(name)
                self._save_tt_data()
                refresh_list()
                self._build_chip_bar()
                self._rebuild_tag_bar()
            new_entry.set_text("")

        def del_type(w):
            row = self._manage_list.get_selected_row()
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
            refresh_list()
            self._build_chip_bar()
            self._rebuild_tag_bar()
            self.load_payloads()

        add_btn.connect("clicked", add_type)
        new_entry.connect("activate", add_type)
        del_btn.connect("clicked", del_type)
        close_btn.connect("clicked", lambda w: win.close())
        win.present()

    # ── Tag assignment bar ────────────────────────────────────────

    def _rebuild_tag_bar(self):
        for cb in self.tag_toggles.values():
            self.tag_bar_box.remove(cb)
        self.tag_toggles.clear()
        for t in self.tt_data["types"]:
            cb = Gtk.CheckButton(label=t)
            cb.set_sensitive(False)
            cb.connect("toggled", self._on_tag_toggled, t)
            self.tag_bar_box.append(cb)
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
        win.set_default_size(300, 90)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(12); box.set_margin_end(12)
        box.set_margin_top(12);   box.set_margin_bottom(12)
        entry = Gtk.Entry(placeholder_text="Category name")
        btn2 = Gtk.Button(label="＋ Create")
        btn2.add_css_class("btn-add")
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
        self.cat_title.set_text("Select a category")
        self.load_categories()
        self.load_payloads()

    # ── Payloads ──────────────────────────────────────────────────

    def load_payloads(self):
        while row := self.payload_list.get_row_at_index(0):
            self.payload_list.remove(row)
        for cb in self.tag_toggles.values():
            cb.set_sensitive(False)

        if self.current_category:
            path = os.path.join(PAYLOADS_DIR, f"{self.current_category}.txt")
            if os.path.exists(path):
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self._add_payload_row(line, self.current_category)
            title = self.current_category
            if self.current_testtype:
                title = f"{self.current_category}  ·  {self.current_testtype}"
            self.cat_title.set_text(title)

        elif self.current_testtype:
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
        if self.current_category == category:
            payloads = []
            i = 0
            while row := self.payload_list.get_row_at_index(i):
                if getattr(row, "source_category", None) == category:
                    payloads.append(row.payload)
                i += 1
            path = os.path.join(PAYLOADS_DIR, f"{category}.txt")
            with open(path, "w") as f:
                f.write("\n".join(payloads) + "\n")
        else:
            self._remove_deleted_from_disk(category)

    def _remove_deleted_from_disk(self, category):
        path = os.path.join(PAYLOADS_DIR, f"{category}.txt")
        if not os.path.exists(path):
            return
        in_list = set()
        i = 0
        while row := self.payload_list.get_row_at_index(i):
            if getattr(row, "source_category", None) == category:
                in_list.add(row.payload)
            i += 1
        with open(path) as f:
            lines = [l.strip() for l in f if l.strip()]
        try:
            lines.remove(next(p for p in lines if p not in in_list))
        except StopIteration:
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

    def _delete_payload_from_file(self, category, payload_text):
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

    def on_search(self, entry):
        self.payload_list.invalidate_filter()

    def filter_payloads(self, row):
        query = self.search.get_text().lower()
        if query and query not in row.payload.lower():
            return False
        # When a category is selected show everything in it — type chips are
        # only for cross-category browsing (no category selected).
        return True

    # ── Import ────────────────────────────────────────────────────

    def on_import_file(self, btn):
        dialog = Gtk.FileChooserDialog(
            title="Import payloads from file",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons("_Cancel", Gtk.ResponseType.CANCEL,
                           "_Next", Gtk.ResponseType.ACCEPT)

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
        self._show_testtype_picker(path)

    def _show_testtype_picker(self, path):
        win = Gtk.Window(transient_for=self, modal=True, title="Assign test types")
        win.set_default_size(320, 240)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(14); box.set_margin_end(14)
        box.set_margin_top(14);   box.set_margin_bottom(14)

        lbl = Gtk.Label(label="Tag imported payloads with test types\n(optional — can be changed later):", xalign=0)
        lbl.set_wrap(True)
        box.append(lbl)

        checks = {}
        for t in self.tt_data["types"]:
            cb = Gtk.CheckButton(label=t)
            box.append(cb)
            checks[t] = cb

        btn_row = Gtk.Box(spacing=8, homogeneous=True)
        btn_skip   = Gtk.Button(label="Skip tagging")
        btn_import = Gtk.Button(label="⬆ Import")
        btn_import.add_css_class("btn-import")
        btn_row.append(btn_skip); btn_row.append(btn_import)
        box.append(btn_row)
        win.set_child(box)

        def do_import(w):
            selected = [t for t, cb in checks.items() if cb.get_active()]
            win.close()
            if path.endswith(".json"):
                self._import_json(path, selected)
            else:
                self._import_txt(path, selected)

        btn_import.connect("clicked", do_import)
        btn_skip.connect("clicked", lambda w: (
            win.close(),
            self._import_json(path, []) if path.endswith(".json") else self._import_txt(path, [])
        ))
        win.present()

    def _assign_types(self, category, payloads, types):
        for payload in payloads:
            for t in types:
                self._set_payload_testtype(category, payload, t, True)

    def _import_txt(self, path, assign_types):
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
        if assign_types:
            self._assign_types(self.current_category, lines, assign_types)
        self.status.set_text(f"Imported {len(lines)} payload(s) from {os.path.basename(path)}")

    def _import_json(self, path, assign_types):
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
            if assign_types:
                self._assign_types(self.current_category, items, assign_types)
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
                if assign_types:
                    self._assign_types(cat_name, lines, assign_types)
                total += len(lines)
            self.load_categories()
            if self.current_category:
                self.load_payloads()
            self.status.set_text(
                f"Imported {total} payload(s) across {len(data)} categories from {os.path.basename(path)}"
            )
            return

        self._show_error("JSON must be an array of strings or an object mapping category names to arrays.")

    # ── Export ────────────────────────────────────────────────────

    def on_export_file(self, btn):
        if not self.current_category:
            self._show_error("Select a category before exporting.")
            return
        dlg = Gtk.Window(transient_for=self, modal=True, title="Export format")
        dlg.set_default_size(280, 130)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(16); box.set_margin_end(16)
        box.set_margin_top(16);   box.set_margin_bottom(16)
        lbl = Gtk.Label(label="Choose export format:", xalign=0)
        btns = Gtk.Box(spacing=8, homogeneous=True)
        btn_txt  = Gtk.Button(label="Text (.txt)")
        btn_txt.add_css_class("btn-export")
        btn_json = Gtk.Button(label="JSON (.json)")
        btn_json.add_css_class("btn-export")
        btn_all  = Gtk.Button(label="All categories (.json)")
        btn_all.add_css_class("btn-import")
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
