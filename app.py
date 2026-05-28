"""
app.py - EscalationCache canvas-state-machine GUI.

Run from inside this folder:
    python app.py
or double-click run.bat.

One window, slate theme. View states: home (single-pane column list),
contribution, editor, versions, prior-version, tools (Easter egg).
Back button + Esc navigate the stack. No em dashes anywhere, by request.
"""
import tkinter as tk
from tkinter import messagebox, ttk, font as tkfont
from datetime import date

import config, store
from economy import (
    get_access_cost, get_display_tag, get_tool_cost, grant_return_bonus,
    use_influence, effective_cost, free_hours_remaining, record_access,
    is_free_access,
)

# ===========================================================================
# Theme
# ===========================================================================
T = {
    "bg":            "#1a1d24",
    "bg_alt":        "#1f2229",
    "card":          "#22262e",
    "input":         "#13161c",
    "border":        "#2c3038",
    "border_focus":  "#3a4050",
    "text":          "#e5e7eb",
    "text_muted":    "#8089a0",
    "text_dim":      "#6b7385",
    "cyan":          "#4dd0e1",
    "cyan_bright":   "#aff5fb",
    "inf_normal":    "#f97316",
    "inf_normal_bg": "#2a2018",
    "inf_high":      "#ef4444",
    "inf_high_bg":   "#2a1818",
}

TAG_STYLE = {
    "validated": {"bg": "#1a4029", "fg": "#4ade80", "border": None},
    "submitted": {"bg": None,      "fg": "#b0b6c0", "border": "#4a5060"},
    "stale":     {"bg": "#3d2e15", "fg": "#fbbf24", "border": None},
}
CITATION_TAG = {"bg": "#2d2810", "fg": "#facc15"}

DISCLAIMER_STYLE = {"bg": "#2a2520", "bar": "#f97316", "label_fg": "#fdba74"}
CITATION_BANNER  = {"bg": "#2d2810", "bar": "#facc15", "fg": "#fde68a", "muted": "#caa84c"}

INF_HIGH_THRESHOLD = 7
BROWSE_CAP = 6          # empty browse shows at most this many (newest first)
MAX_TITLE = 120         # soft cap on title length (stops paste-bombs)

# Fixed row heights (px). The row must own a height: its cells use
# pack_propagate(False) for fixed widths, so without this the row collapses to
# nothing and clips every cell.
ROW_H    = 42
HEADER_H = 30

# Fixed column widths (px). Title is bounded (around example length) and the
# table is left-grouped, with a flexible spacer absorbing extra window width.
TITLE_W     = 360
STATUS_W    = 150
CREATED_W   = 80
IMPROVED_W  = 80
VALIDATED_W = 84
SHARE_W     = 150


def fmt_date(iso_date):
    """ISO date to mm/dd/yyyy. Empty stays empty; parse error returns input."""
    if not iso_date:
        return ""
    try:
        return date.fromisoformat(iso_date).strftime("%m/%d/%Y")
    except (TypeError, ValueError):
        return iso_date


# ===========================================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(config.APP_TITLE)
        self.geometry("1080x560")
        self.minsize(1000, 520)
        self.configure(bg=T["bg"])

        # Themed scrollbar via clam (the native tk scrollbar ignores colors on
        # Windows; clam-styled ttk does not). Only ttk widget we use.
        self._style = ttk.Style(self)
        try:
            self._style.theme_use("clam")
        except tk.TclError:
            pass
        self._style.configure(
            "Cache.Vertical.TScrollbar", troughcolor=T["bg"],
            background=T["border"], bordercolor=T["bg"],
            arrowcolor=T["text_muted"], relief="flat", borderwidth=0)
        self._style.map("Cache.Vertical.TScrollbar",
                        background=[("active", T["border_focus"]),
                                    ("pressed", T["border_focus"])])
        self.title_font = tkfont.Font(family="Segoe UI", size=10)

        store.init()
        self.user = store.get_user()
        bonus = grant_return_bonus(self.user)
        self.user = store.get_user(self.user["id"], self.user.get("display_name"))

        self.back_target = None
        self.balance_lbl = None
        self._refs = {}

        self.top_bar = tk.Frame(self, bg=T["bg_alt"], height=44)
        self.top_bar.pack(side="top", fill="x")
        self.top_bar.pack_propagate(False)

        self.content = tk.Frame(self, bg=T["bg"])
        self.content.pack(side="top", fill="both", expand=True)

        self.bind("<Escape>", self._on_escape)
        self.show_home()

        if bonus:
            self.after(150, lambda: self._info(
                "Welcome back", f"Return bonus: +{bonus} influence."))

    # ---- Small text helpers ----
    def _short(self, text, n=70):
        text = text or ""
        return text if len(text) <= n else text[:n].rstrip() + "..."

    def _truncate(self, text, max_px):
        """Truncate to fit max_px with a real ellipsis, using the title font."""
        text = text or ""
        if self.title_font.measure(text) <= max_px:
            return text
        ell = "\u2026"
        while text and self.title_font.measure(text + ell) > max_px:
            text = text[:-1]
        return text.rstrip() + ell

    # ---- Modals ----
    def _confirm(self, title, msg):
        return messagebox.askyesno(title, msg, parent=self)

    def _info(self, title, msg):
        messagebox.showinfo(title, msg, parent=self)

    def _warn(self, title, msg):
        messagebox.showwarning(title, msg, parent=self)

    # ---- Esc ----
    def _on_escape(self, _e=None):
        if self.back_target is not None:
            self.back_target()
            return
        sv = self._refs.get("search_var")
        if sv is not None and sv.get():
            sv.set("")
            self._do_search()

    # ---- Clear / rebuild ----
    def _clear_top_bar(self):
        for w in self.top_bar.winfo_children():
            w.destroy()
        self.balance_lbl = None

    def _clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()
        self._refs.clear()

    def _scrollbar(self, parent, command):
        return ttk.Scrollbar(parent, orient="vertical", command=command,
                             style="Cache.Vertical.TScrollbar")

    # ---- Tree walk + row background helpers ----
    def _descendants(self, w):
        out = []
        for c in w.winfo_children():
            out.append(c)
            out.extend(self._descendants(c))
        return out

    def _set_subtree_bg(self, w, color):
        try:
            if w.cget("bg") in (T["bg"], T["card"]):
                w.configure(bg=color)
        except tk.TclError:
            pass
        for c in w.winfo_children():
            self._set_subtree_bg(c, color)

    # ---- Top bars ----
    def _build_top_bar_home(self):
        self._clear_top_bar()
        brand = tk.Frame(self.top_bar, bg=T["bg_alt"])
        brand.pack(side="left", padx=(16, 12))
        tk.Label(brand, text="Escalation", bg=T["bg_alt"], fg=T["text"],
                 font=("Segoe UI", 13, "bold"), padx=0, bd=0,
                 highlightthickness=0).pack(side="left")
        tk.Label(brand, text="Cache", bg=T["bg_alt"], fg=T["cyan"],
                 font=("Segoe UI", 13, "bold"), padx=0, bd=0,
                 highlightthickness=0).pack(side="left")

        home_btn = self._make_pill_button(self.top_bar, "\u2302",
                                          self.show_home, font_size=12, padx=6)
        home_btn.pack(side="left", padx=(0, 8))

        sv = tk.StringVar()
        self._refs["search_var"] = sv
        search_entry = tk.Entry(self.top_bar, textvariable=sv,
                                bg=T["input"], fg=T["text"],
                                insertbackground=T["text"], relief="flat",
                                font=("Segoe UI", 10), highlightthickness=1,
                                highlightbackground=T["border"],
                                highlightcolor=T["cyan"])
        search_entry.pack(side="left", fill="x", expand=True, ipady=4, pady=8)
        search_entry.bind("<Return>", lambda _e: self._do_search())
        self._refs["search_entry"] = search_entry
        self._attach_placeholder(search_entry, sv, "Search entries...")

        btn = self._make_pill_button(self.top_bar, "Search", self._do_search)
        btn.pack(side="left", padx=(6, 12))

        self._build_influence_chip()

    def _build_top_bar_back(self, title_text=""):
        self._clear_top_bar()
        back = self._make_pill_button(
            self.top_bar, "\u2190 back",
            lambda: self.back_target() if self.back_target else None)
        back.pack(side="left", padx=(14, 10))
        if title_text:
            tk.Label(self.top_bar, text=title_text, bg=T["bg_alt"],
                     fg=T["text_muted"], font=("Segoe UI", 10)).pack(
                         side="left", padx=(4, 0))
        self._build_influence_chip()

    def _build_influence_chip(self):
        wrap = tk.Frame(self.top_bar, bg=T["bg_alt"])
        wrap.pack(side="right", padx=14)
        tk.Label(wrap, text="Influence", bg=T["bg_alt"], fg=T["text_muted"],
                 font=("Segoe UI", 10)).pack(side="left", padx=(0, 8))
        num = tk.Label(wrap, text=str(self.user["influence"]),
                       bg=T["input"], fg=T["cyan"],
                       font=("Segoe UI", 11, "bold"), padx=12, pady=2)
        num.pack(side="left")
        self.balance_lbl = num

    def _add_versions_button(self, entry):
        btn = self._make_pill_button(
            self.top_bar, "Versions", lambda: self.show_versions(entry))
        btn.pack(side="right", padx=(0, 8))

    def _make_pill_button(self, parent, text, command, *,
                          font_size=10, padx=12, primary=False):
        bg = T["input"] if primary else T["card"]
        fg = T["cyan"] if primary else T["text"]
        border = T["cyan"] if primary else T["border"]
        btn = tk.Label(parent, text=text, bg=bg, fg=fg,
                       font=("Segoe UI", font_size), padx=padx, pady=4,
                       cursor="hand2", highlightthickness=1,
                       highlightbackground=border)
        btn.bind("<Button-1>", lambda _e: command())
        return btn

    # ---- Balance ----
    def _refresh_balance(self):
        self.user = store.get_user(self.user["id"], self.user.get("display_name"))
        if self.balance_lbl is None:
            return
        try:
            self.balance_lbl.config(text=str(self.user["influence"]))
            self._flash_balance()
        except tk.TclError:
            pass

    def _flash_balance(self):
        if self.balance_lbl is None:
            return
        try:
            self.balance_lbl.config(fg=T["cyan_bright"])
            self.after(180, self._restore_balance_color)
        except tk.TclError:
            pass

    def _restore_balance_color(self):
        if self.balance_lbl is None:
            return
        try:
            self.balance_lbl.config(fg=T["cyan"])
        except tk.TclError:
            pass

    # ---- Placeholders ----
    def _attach_placeholder(self, entry_widget, var, placeholder):
        flag = f"ph_{id(entry_widget)}"
        self._refs[flag] = True

        def show():
            entry_widget.delete(0, tk.END)
            entry_widget.insert(0, placeholder)
            entry_widget.config(fg=T["text_dim"])
            self._refs[flag] = True

        def hide(_e=None):
            if self._refs.get(flag):
                entry_widget.delete(0, tk.END)
                entry_widget.config(fg=T["text"])
                self._refs[flag] = False

        def restore(_e=None):
            if entry_widget.get() == "":
                show()

        show()
        entry_widget.bind("<FocusIn>", hide)
        entry_widget.bind("<FocusOut>", restore)

    def _placeholder_active(self, entry_widget):
        return self._refs.get(f"ph_{id(entry_widget)}", False)

    def _focus_text(self, text_widget):
        """Focus the body text widget, clearing its grey placeholder if showing."""
        flag = f"tph_{id(text_widget)}"
        if self._refs.get(flag):
            text_widget.delete("1.0", "end")
            text_widget.config(fg=T["text"])
            self._refs[flag] = False
        try:
            text_widget.focus_set()
        except tk.TclError:
            pass

    def _attach_text_placeholder(self, text_widget, placeholder):
        flag = f"tph_{id(text_widget)}"
        text_widget.insert("1.0", placeholder)
        text_widget.config(fg=T["text_dim"])
        self._refs[flag] = True

        def hide(_e=None):
            if self._refs.get(flag):
                text_widget.delete("1.0", "end")
                text_widget.config(fg=T["text"])
                self._refs[flag] = False

        def restore(_e=None):
            if text_widget.get("1.0", "end-1c").strip() == "":
                text_widget.delete("1.0", "end")
                text_widget.insert("1.0", placeholder)
                text_widget.config(fg=T["text_dim"])
                self._refs[flag] = True

        text_widget.bind("<FocusIn>", hide, add="+")
        text_widget.bind("<FocusOut>", restore, add="+")

    # ---- Chips / pills ----
    def _make_tag_chip(self, parent, tag):
        style = TAG_STYLE.get(tag)
        if not style:
            return None
        if style["border"]:
            return tk.Label(parent, text=tag, bg=T["bg"], fg=style["fg"],
                            font=("Segoe UI", 9), padx=8, pady=0,
                            highlightthickness=1,
                            highlightbackground=style["border"])
        return tk.Label(parent, text=tag, bg=style["bg"], fg=style["fg"],
                        font=("Segoe UI", 9, "bold"), padx=8, pady=1)

    def _make_citation_chip(self, parent):
        return tk.Label(parent, text="\u2690 citation", bg=CITATION_TAG["bg"],
                        fg=CITATION_TAG["fg"], font=("Segoe UI", 9, "bold"),
                        padx=8, pady=1)

    # ---- Block renderers (contribution + prior version) ----
    def _render_text(self, parent, content):
        tk.Label(parent, text=content, bg=T["bg"], fg=T["text"],
                 wraplength=920, justify="left", font=("Segoe UI", 10),
                 anchor="w").pack(fill="x", anchor="w", pady=(4, 4))

    def _render_step(self, parent, content):
        row = tk.Frame(parent, bg=T["bg"])
        row.pack(fill="x", anchor="w", pady=2)
        state = {"on": False}
        box = tk.Label(row, text="\u2610", bg=T["bg"], fg=T["text"],
                       font=("Segoe UI", 13), cursor="hand2", padx=2)
        box.pack(side="left", anchor="n")
        lbl = tk.Label(row, text=content, bg=T["bg"], fg=T["text"],
                       wraplength=820, justify="left", font=("Segoe UI", 10),
                       anchor="w")
        lbl.pack(side="left", fill="x", expand=True, padx=(8, 0))

        def toggle(_e=None):
            state["on"] = not state["on"]
            box.config(text="\u2611" if state["on"] else "\u2610",
                       fg=T["cyan"] if state["on"] else T["text"])

        box.bind("<Button-1>", toggle)
        lbl.bind("<Button-1>", toggle)

    def _render_code(self, parent, content):
        outer = tk.Frame(parent, bg=T["input"], highlightthickness=1,
                         highlightbackground=T["border"])
        outer.pack(fill="x", anchor="w", pady=(6, 6))
        header = tk.Frame(outer, bg=T["input"])
        header.pack(fill="x", padx=8, pady=(4, 2))
        tk.Label(header, text="code", bg=T["input"], fg=T["text_muted"],
                 font=("Segoe UI", 9)).pack(side="left")
        copy_btn = tk.Label(header, text="Copy", bg=T["card"], fg=T["text"],
                            font=("Segoe UI", 9), padx=10, pady=1,
                            cursor="hand2", highlightthickness=1,
                            highlightbackground=T["border"])
        copy_btn.pack(side="right")
        copy_btn.bind("<Button-1>", lambda _e: self._copy_code(content))
        tk.Label(outer, text=content, bg=T["input"], fg=T["text"],
                 font=("Consolas", 10), justify="left", anchor="w",
                 padx=10).pack(fill="x", pady=(0, 8))

    def _render_disclaimer(self, parent, content):
        wrap = tk.Frame(parent, bg=T["bg"])
        wrap.pack(fill="x", anchor="w", pady=(6, 6))
        bar = tk.Frame(wrap, bg=DISCLAIMER_STYLE["bar"], width=3)
        bar.pack(side="left", fill="y")
        inner = tk.Frame(wrap, bg=DISCLAIMER_STYLE["bg"])
        inner.pack(side="left", fill="both", expand=True)
        tk.Label(inner, text="DISCLAIMER", bg=DISCLAIMER_STYLE["bg"],
                 fg=DISCLAIMER_STYLE["label_fg"], font=("Segoe UI", 9, "bold"),
                 anchor="w", padx=12).pack(fill="x", pady=(8, 0))
        tk.Label(inner, text=content, bg=DISCLAIMER_STYLE["bg"], fg=T["text"],
                 wraplength=820, justify="left", font=("Segoe UI", 10),
                 anchor="w", padx=12).pack(fill="x", pady=(2, 8))

    def _copy_code(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.title(config.APP_TITLE + "   code copied")
        self.after(900, self._restore_title)

    def _restore_title(self):
        try:
            if self.winfo_exists():
                self.title(config.APP_TITLE)
        except tk.TclError:
            pass

    # ---- Date column strings ----
    def _created_str(self, entry):
        return fmt_date(entry.get("created") or entry.get("updated") or "")

    def _improved_str(self, entry):
        if int(entry.get("version", 1)) > 1:
            return fmt_date(entry.get("updated") or "")
        return "not yet"

    def _validated_str(self, entry):
        dates = [v.get("date") for v in store.get_validations(entry) if v.get("date")]
        return fmt_date(max(dates)) if dates else "not yet"

    # =======================================================================
    # HOME VIEW (single-pane column list)
    # =======================================================================
    def show_home(self):
        self.back_target = None
        self._clear_content()
        self._build_top_bar_home()

        # Margin/buffer on all sides; also gives the scrollbar breathing room.
        wrap = tk.Frame(self.content, bg=T["bg"])
        wrap.pack(fill="both", expand=True, padx=14, pady=(8, 10))

        canvas = tk.Canvas(wrap, bg=T["bg"], highlightthickness=0, bd=0)
        sb = self._scrollbar(wrap, canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(6, 0))
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=T["bg"])
        cw = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(cw, width=e.width))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        self._make_header_row(inner)
        holder = tk.Frame(inner, bg=T["bg"])
        holder.pack(fill="x")
        self._refs["rows_holder"] = holder

        entries = store.get_all_entries()
        entries.sort(key=lambda e: e.get("updated", ""), reverse=True)
        note = None
        if len(entries) > BROWSE_CAP:
            note = f"Showing the {BROWSE_CAP} most recent. Search to find the rest."
            entries = entries[:BROWSE_CAP]
        self._populate_rows(entries, note=note)

        self._refs["search_entry"].focus_set()

    def _col(self, parent, width):
        c = tk.Frame(parent, bg=T["bg"], width=width)
        c.pack(side="left", fill="y")
        c.pack_propagate(False)
        return c

    def _make_header_row(self, parent):
        row = tk.Frame(parent, bg=T["bg"], height=HEADER_H)
        row.pack(fill="x")
        row.pack_propagate(False)
        cols = (("CONTRIBUTION", TITLE_W), ("STATUS", STATUS_W),
                ("CREATED", CREATED_W), ("IMPROVED", IMPROVED_W),
                ("VALIDATED", VALIDATED_W), ("SHARE", SHARE_W))
        for label, width in cols:
            c = self._col(row, width)
            lpad = (8, 0) if width == TITLE_W else (0, 0)
            tk.Label(c, text=label, bg=T["bg"], fg=T["text_dim"],
                     font=("Segoe UI", 8), anchor="w").pack(
                         expand=True, anchor="w", padx=lpad)
        tk.Frame(row, bg=T["bg"]).pack(side="left", fill="both", expand=True)
        tk.Frame(parent, bg=T["border"], height=1).pack(fill="x")

    def _populate_rows(self, entries, empty_term=None, note=None):
        holder = self._refs.get("rows_holder")
        if holder is None:
            return
        for w in holder.winfo_children():
            w.destroy()
        if not entries:
            tk.Label(holder,
                     text=(f'No contributions match "{self._short(empty_term, 50)}".'
                           if empty_term else "No contributions yet."),
                     bg=T["bg"], fg=T["text_dim"], font=("Segoe UI", 10),
                     pady=16).pack(fill="x", padx=14)
            if empty_term:
                link = tk.Label(holder,
                                text=f'Be the first to document "{self._short(empty_term, 40)}"?',
                                bg=T["bg"], fg=T["cyan"],
                                font=("Segoe UI", 10, "underline"), cursor="hand2")
                link.pack(fill="x", padx=14, pady=(0, 14))
                link.bind("<Button-1>",
                          lambda _e: self.show_editor("pioneer", seed_title_hint=empty_term))
            return
        for e in entries:
            self._make_entry_row(holder, e)
        if note:
            tk.Label(holder, text=note, bg=T["bg"], fg=T["text_dim"],
                     font=("Segoe UI", 8), anchor="w").pack(
                         fill="x", padx=14, pady=(10, 0))

    def _make_entry_row(self, parent, entry):
        row = tk.Frame(parent, bg=T["bg"], cursor="hand2", height=ROW_H)
        row.pack(fill="x")
        row.pack_propagate(False)   # fixed height so the cells have room

        tcell = self._col(row, TITLE_W)
        disp = self._truncate(entry.get("title", ""), TITLE_W - 24)
        title_lbl = tk.Label(tcell, text=disp, bg=T["bg"], fg=T["text"],
                             font=("Segoe UI", 10), anchor="w")
        title_lbl.pack(expand=True, anchor="w", padx=(8, 8))

        scell = self._col(row, STATUS_W)
        sc_inner = tk.Frame(scell, bg=T["bg"])
        sc_inner.pack(expand=True, anchor="w")
        chip = self._make_tag_chip(sc_inner, get_display_tag(entry))
        if chip:
            chip.pack(side="left", padx=(0, 4))
        if entry.get("cited_by"):
            self._make_citation_chip(sc_inner).pack(side="left", padx=(0, 4))

        self._date_cell(row, self._created_str(entry), CREATED_W)
        self._date_cell(row, self._improved_str(entry), IMPROVED_W)
        self._date_cell(row, self._validated_str(entry), VALIDATED_W)

        share_cell = self._col(row, SHARE_W)
        cost = effective_cost(self.user, entry)
        free_h = free_hours_remaining(self.user, entry["id"]) if cost == 0 else None
        self._fill_share_cell(share_cell, cost, free_h)

        tk.Frame(row, bg=T["bg"]).pack(side="left", fill="both", expand=True)
        tk.Frame(parent, bg=T["border"], height=1).pack(fill="x")

        def enter(_e=None):
            self._set_subtree_bg(row, T["card"])
            try:
                title_lbl.config(fg=T["cyan"])
            except tk.TclError:
                pass

        def leave(_e=None):
            self._set_subtree_bg(row, T["bg"])
            try:
                title_lbl.config(fg=T["text"])
            except tk.TclError:
                pass

        def click(_e=None):
            self.attempt_open_entry(entry["id"])

        for w in [row] + self._descendants(row):
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)
            w.bind("<Button-1>", click)

    def _date_cell(self, parent, text, width):
        cell = self._col(parent, width)
        fg = T["text_dim"] if text == "not yet" else T["text_muted"]
        tk.Label(cell, text=text, bg=T["bg"], fg=fg, font=("Segoe UI", 9),
                 anchor="w").pack(expand=True, anchor="w")

    def _fill_share_cell(self, cell, cost, free_h):
        box = tk.Frame(cell, bg=T["bg"])
        box.pack(expand=True, anchor="w")
        if cost == 0:
            tk.Label(box, text="0 INF", bg=T["bg"], fg=T["text"],
                     font=("Segoe UI", 9, "bold")).pack(side="left")
            tk.Label(box, text=f"  (next {free_h}h)", bg=T["bg"], fg=T["cyan"],
                     font=("Segoe UI", 8)).pack(side="left")
        else:
            if cost >= INF_HIGH_THRESHOLD:
                bg, fg = T["inf_high_bg"], T["inf_high"]
            else:
                bg, fg = T["inf_normal_bg"], T["inf_normal"]
            tk.Label(box, text=f"{cost} INF", bg=bg, fg=fg,
                     font=("Segoe UI", 9, "bold"), padx=8, pady=1).pack(side="left")

    # ---- Search ----
    def _do_search(self):
        sv = self._refs.get("search_var")
        entry_w = self._refs.get("search_entry")
        if sv is None or entry_w is None:
            return
        term = "" if self._placeholder_active(entry_w) else sv.get().strip()

        if term.lower() == "tools":
            self.show_tools()
            return

        if not term:
            entries = store.get_all_entries()
            entries.sort(key=lambda e: e.get("updated", ""), reverse=True)
            note = None
            if len(entries) > BROWSE_CAP:
                note = f"Showing the {BROWSE_CAP} most recent. Search to find the rest."
                entries = entries[:BROWSE_CAP]
            self._populate_rows(entries, note=note)
            return

        results = store.search_entries(term)
        if not results:
            self._populate_rows([], empty_term=term)
            return
        full = [store.get_entry(r["id"]) for r in results]
        full = [e for e in full if e is not None]
        self._populate_rows(full)

    # ---- Open (free window aware) ----
    def attempt_open_entry(self, entry_id):
        e = store.get_entry(entry_id)
        if e is None:
            return
        cost = effective_cost(self.user, e)
        if cost > 0:
            if not self._confirm(
                "Confirm spend",
                f'Open "{self._short(e["title"])}"?\n\nShare: {cost} influence\n'
                f'Your balance: {self.user["influence"]}'):
                return
            if not use_influence(self.user, cost):
                self._warn("Not enough influence",
                           "You can't afford this contribution yet.")
                self._refresh_balance()
                return
            record_access(self.user, e["id"])   # start/restart the free window
            self._refresh_balance()
        self.show_contribution(e)

    # =======================================================================
    # CONTRIBUTION VIEW
    # =======================================================================
    def show_contribution(self, entry, *, read_only=False, parent_entry=None):
        if read_only:
            self.back_target = lambda: self.show_versions(parent_entry)
        else:
            self.back_target = self.show_home

        self._clear_content()
        self._build_top_bar_back()
        if not read_only:
            self._add_versions_button(entry)
            entry = store.get_entry(entry["id"])

        if not read_only:
            action_row = tk.Frame(self.content, bg=T["bg_alt"], height=48)
            action_row.pack(side="bottom", fill="x")
            action_row.pack_propagate(False)
            self._build_action_row(action_row, entry)

        body = tk.Frame(self.content, bg=T["bg"])
        body.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(body, bg=T["bg"], highlightthickness=0, bd=0)
        sb = self._scrollbar(body, canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(6, 6))
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=T["bg"])
        cw = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(cw, width=e.width))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        pad = tk.Frame(inner, bg=T["bg"])
        pad.pack(fill="both", expand=True, padx=22, pady=18)

        title_text = entry.get("title", "")
        if read_only:
            title_text = f"(prior version) {title_text}"
        tk.Label(pad, text=title_text, bg=T["bg"], fg=T["text"],
                 font=("Segoe UI", 14, "bold"), anchor="w", justify="left",
                 wraplength=980).pack(fill="x", anchor="w")

        meta = tk.Frame(pad, bg=T["bg"])
        meta.pack(fill="x", anchor="w", pady=(8, 0))
        chip = self._make_tag_chip(meta, get_display_tag(entry))
        if chip:
            chip.pack(side="left", padx=(0, 6))
        if entry.get("cited_by"):
            self._make_citation_chip(meta).pack(side="left", padx=(0, 6))
        tk.Label(meta, text=self._meta_people_line(entry), bg=T["bg"],
                 fg=T["text_muted"], font=("Segoe UI", 9)).pack(side="left")

        if entry.get("cited_by"):
            self._render_citation_banner(pad, entry)

        body_frame = tk.Frame(pad, bg=T["bg"])
        body_frame.pack(fill="x", anchor="w", pady=(14, 0))
        for kind, content in store.parse_body(entry.get("body") or ""):
            if kind == "text":
                self._render_text(body_frame, content)
            elif kind == "step":
                self._render_step(body_frame, content)
            elif kind == "code":
                self._render_code(body_frame, content)
            elif kind == "disclaimer":
                self._render_disclaimer(body_frame, content)

        tk.Frame(pad, bg=T["border"], height=1).pack(fill="x", pady=(14, 8))
        vals = store.get_validations(entry)
        if vals:
            for v in vals:
                tk.Label(pad, text=f"\u2713  Validated by {v['by']} on "
                                   f"{fmt_date(v.get('date', ''))}",
                         bg=T["bg"], fg=T["text_muted"], font=("Segoe UI", 9),
                         anchor="w").pack(fill="x", anchor="w")
        else:
            tk.Label(pad, text="Not yet validated.", bg=T["bg"],
                     fg=T["text_dim"], font=("Segoe UI", 9), anchor="w").pack(
                         fill="x", anchor="w")

    def _meta_people_line(self, entry):
        ver = int(entry.get("version", 1))
        creator = entry.get("created_by") or entry.get("author", "")
        improver = entry.get("author", "")
        if ver > 1 and improver and improver != creator:
            return (f"v{ver}  \u00b7  created by {creator}  \u00b7  "
                    f"improved by {improver}  \u00b7  {fmt_date(entry.get('updated', ''))}")
        created_date = fmt_date(entry.get("created") or entry.get("updated", ""))
        return f"v{ver}  \u00b7  created by {creator}  \u00b7  {created_date}"

    def _render_citation_banner(self, parent, entry):
        wrap = tk.Frame(parent, bg=T["bg"])
        wrap.pack(fill="x", anchor="w", pady=(12, 0))
        bar = tk.Frame(wrap, bg=CITATION_BANNER["bar"], width=3)
        bar.pack(side="left", fill="y")
        inner = tk.Frame(wrap, bg=CITATION_BANNER["bg"])
        inner.pack(side="left", fill="both", expand=True)
        cby = entry.get("cited_by", "")
        cdate = fmt_date(entry.get("cited_date", ""))
        head = f"Citation requested by {cby}" + (f"  \u00b7  {cdate}" if cdate else "")
        tk.Label(inner, text=head, bg=CITATION_BANNER["bg"],
                 fg=CITATION_BANNER["fg"], font=("Segoe UI", 10), anchor="w",
                 padx=12).pack(fill="x", pady=(8, 0))
        tk.Label(inner, text="Improve or validate this contribution to resolve the flag.",
                 bg=CITATION_BANNER["bg"], fg=CITATION_BANNER["muted"],
                 font=("Segoe UI", 9), anchor="w", padx=12).pack(fill="x", pady=(0, 8))

    def _build_action_row(self, parent, entry):
        citation_label = "Clear citation" \
            if entry.get("cited_by") == self.user["display_name"] \
            else "Citation request"
        imp = self._make_pill_button(parent, "Improve",
                                      lambda: self._action_improve(entry), primary=True)
        imp.pack(side="left", padx=(22, 8), pady=10)
        val = self._make_pill_button(parent, "Validate",
                                      lambda: self._action_validate(entry))
        val.pack(side="left", padx=(0, 8), pady=10)
        cit = self._make_pill_button(parent, citation_label,
                                      lambda: self._action_citation(entry))
        cit.pack(side="left", pady=10)

    # ---- Actions ----
    def _action_improve(self, entry):
        self.show_editor("improve", entry=entry)

    def _action_validate(self, entry):
        if entry.get("author") == self.user["display_name"]:
            self._info("Cannot validate your own work",
                       "You authored the current version, so you can't validate "
                       "it. Once someone else improves it, you can validate "
                       "their version.")
            return
        vals = store.get_validations(entry)
        if any(v.get("by") == self.user["display_name"] for v in vals):
            self._info("Already validated",
                       "You have already validated this contribution.")
            return
        cited = bool(entry.get("cited_by"))
        msg = ("Validating adds your name and today's date, vouching that this "
               "fix works. That is what makes it trustworthy for the next person.")
        if cited:
            msg += ("\n\nThis contribution has an open citation. Validating it "
                    "will also clear that flag.")
        if not self._confirm("Go on record", msg + "\n\nReady to go on record?"):
            return
        result = store.confirm_entry(entry, self.user)
        if result is None:
            self._info("Already validated",
                       "You have already validated this contribution.")
            return
        _entry, reward = result
        self._refresh_balance()
        self._info("Validated", f"Validated (+{reward}). Your name is on record.")
        self.show_contribution(store.get_entry(entry["id"]))

    def _action_citation(self, entry):
        if entry.get("cited_by") == self.user["display_name"]:
            store.clear_citation(entry)
            self._info("Citation cleared", "Your citation request has been cleared.")
            self.show_contribution(store.get_entry(entry["id"]))
            return
        if entry.get("cited_by"):
            self._info("Already flagged", f"Already flagged by {entry['cited_by']}.")
            return
        if not self._confirm("Request a citation",
                             "A citation request flags that something here looks "
                             "unverified or inaccurate, so the next person knows "
                             "to double-check, and it nudges someone to improve "
                             "it. Information ages; this keeps it honest.\n\n"
                             "Do you have a specific concern to flag?"):
            return
        store.set_citation(entry, self.user)
        self._info("Citation requested", "Citation requested.")
        self.show_contribution(store.get_entry(entry["id"]))

    # =======================================================================
    # EDITOR
    # =======================================================================
    def show_editor(self, mode, *, entry=None, seed_title_hint=""):
        if mode == "pioneer":
            self.back_target = self.show_home
            header_text = "New contribution"
        else:
            self.back_target = lambda: self.show_contribution(entry)
            header_text = f'Improve  \u00b7  {self._short(entry.get("title", ""), 50)}'

        self._clear_content()
        self._build_top_bar_back(title_text=header_text)

        footer = tk.Frame(self.content, bg=T["bg_alt"], height=52)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)

        main_wrap = tk.Frame(self.content, bg=T["bg"])
        main_wrap.pack(side="top", fill="both", expand=True, padx=22, pady=16)

        title_var = tk.StringVar()
        title_entry = tk.Entry(main_wrap, textvariable=title_var, bg=T["input"],
                               fg=T["text"], insertbackground=T["text"],
                               relief="flat", font=("Segoe UI", 11),
                               highlightthickness=1, highlightbackground=T["border"],
                               highlightcolor=T["cyan"])
        title_entry.pack(fill="x", ipady=6)

        if mode == "pioneer":
            placeholder = (f'Title (e.g. "{seed_title_hint}")'
                           if seed_title_hint else "Title")
            self._attach_placeholder(title_entry, title_var, placeholder)
        else:
            title_var.set(entry.get("title", ""))

        # Soft length cap (enabled after any initial value is set so existing
        # titles are never rejected). Blocks paste-bombs into the field.
        vcmd = (self.register(lambda P: len(P) <= MAX_TITLE), "%P")
        title_entry.config(validate="key", validatecommand=vcmd)

        main = tk.Frame(main_wrap, bg=T["bg"])
        main.pack(fill="both", expand=True, pady=(10, 0))

        aids = tk.Frame(main, bg=T["bg"], width=190)
        aids.pack(side="right", fill="y")
        aids.pack_propagate(False)
        tk.Label(aids, text="AIDS", bg=T["bg"], fg=T["text_muted"],
                 font=("Segoe UI", 9), anchor="w").pack(fill="x")
        tk.Label(aids, text="Optional. Use them or ignore them.", bg=T["bg"],
                 fg=T["text_dim"], font=("Segoe UI", 8), wraplength=180,
                 justify="left", anchor="w").pack(fill="x", pady=(0, 12))

        text_widget = tk.Text(main, bg=T["input"], fg=T["text"],
                              insertbackground=T["text"], relief="flat",
                              font=("Consolas", 10), wrap="word", undo=True,
                              highlightthickness=1, highlightbackground=T["border"],
                              highlightcolor=T["cyan"])
        text_widget.pack(side="left", fill="both", expand=True, padx=(0, 14))

        if mode == "improve":
            text_widget.insert("1.0", entry.get("body", ""))
            text_widget.config(fg=T["text"])
        else:
            self._attach_text_placeholder(
                text_widget,
                "Type freely, paste from a doc, or use the aids on the right.")

        self._make_aid_button(aids, "\u2610  Step",
                              "Wrap selection (or insert empty) as a checkbox step.",
                              lambda: self._wrap_in_text(text_widget, "step"))
        self._make_aid_button(aids, "{ }  Code",
                              "Monospace command or script block, with a Copy button.",
                              lambda: self._wrap_in_text(text_widget, "code"))
        self._make_aid_button(aids, "\u26a0  Disclaimer",
                              "Caveat or warning. Inserts default text you can edit.",
                              lambda: self._wrap_in_text(text_widget, "disclaimer",
                                                         default_text="Use at your own risk."))

        earn = config.EARN_PIONEER if mode == "pioneer" else config.EARN_IMPROVE

        def do_contribute(_e=None):
            t = "" if self._placeholder_active(title_entry) else title_var.get().strip()
            if not t:
                self._warn("Title required", "Please give the contribution a title.")
                title_entry.focus_set()
                return
            ph = f"tph_{id(text_widget)}"
            b = "" if self._refs.get(ph) else text_widget.get("1.0", "end-1c").strip()
            if mode == "pioneer":
                e = store.new_entry(t, b, self.user)
                self._refresh_balance()
                self._info("Contributed",
                           f'Contributed "{self._short(e["title"])}" '
                           f'(+{config.EARN_PIONEER}). Free to reopen for 24h.')
                self.show_contribution(e)
            else:
                store.update_entry(entry, t, b, self.user)
                self._refresh_balance()
                self._info("Improved",
                           f"Improved (+{config.EARN_IMPROVE}). "
                           "Set to submitted, version bumped.")
                self.show_contribution(store.get_entry(entry["id"]))

        contrib = self._make_pill_button(footer, "Contribute", do_contribute, primary=True)
        contrib.pack(side="left", padx=(22, 8), pady=12)
        cancel = self._make_pill_button(
            footer, "Cancel", lambda: self.back_target() if self.back_target else None)
        cancel.pack(side="left", pady=12)
        tk.Label(footer, text=f"+{earn} influence on submit", bg=T["bg_alt"],
                 fg=T["text_muted"], font=("Segoe UI", 9)).pack(side="right", padx=22)

        # Focus the body first for both modes: write the fix before naming it.
        # Clears the body placeholder (pioneer) so the cursor lands ready to type.
        self.after(80, lambda: self._focus_text(text_widget))

    def _make_aid_button(self, parent, label, description, command):
        card = tk.Frame(parent, bg=T["card"], cursor="hand2",
                        highlightthickness=1, highlightbackground=T["border"])
        card.pack(fill="x", pady=(0, 8))
        l1 = tk.Label(card, text=label, bg=T["card"], fg=T["text"],
                      font=("Segoe UI", 10, "bold"), anchor="w", padx=10)
        l1.pack(fill="x", pady=(8, 0))
        l2 = tk.Label(card, text=description, bg=T["card"], fg=T["text_muted"],
                      font=("Segoe UI", 8), wraplength=170, justify="left",
                      anchor="w", padx=10)
        l2.pack(fill="x", pady=(0, 8))
        for w in (card, l1, l2):
            w.bind("<Button-1>", lambda _e: command())

    def _wrap_in_text(self, text_widget, tag, *, default_text=""):
        ph = f"tph_{id(text_widget)}"
        if self._refs.get(ph):
            text_widget.delete("1.0", "end")
            text_widget.config(fg=T["text"])
            self._refs[ph] = False
        try:
            sel_start = text_widget.index("sel.first")
            sel_end = text_widget.index("sel.last")
            selected = text_widget.get(sel_start, sel_end).strip("\n")
            text_widget.delete(sel_start, sel_end)
            insert_at = sel_start
        except tk.TclError:
            selected = default_text
            insert_at = text_widget.index("insert")
        col = int(insert_at.split(".")[1])
        prefix = "" if col == 0 else "\n"
        text_widget.insert(insert_at, f"{prefix}[{tag}]\n{selected}\n[/{tag}]\n")
        text_widget.focus_set()

    # =======================================================================
    # VERSIONS
    # =======================================================================
    def _version_key(self, entry_id, version):
        return f"{int(entry_id)}.v{int(version)}"

    def show_versions(self, entry):
        self.back_target = lambda: self.show_contribution(entry)
        self._clear_content()
        self._build_top_bar_back(
            title_text=f'Versions  \u00b7  {self._short(entry.get("title", ""), 45)}')

        wrap = tk.Frame(self.content, bg=T["bg"])
        wrap.pack(fill="both", expand=True, padx=22, pady=18)
        tk.Label(wrap, text="Prior versions cost influence based on age. "
                            "Opening one is free to reopen for 24h.",
                 bg=T["bg"], fg=T["text_muted"], font=("Segoe UI", 9),
                 anchor="w").pack(fill="x", pady=(0, 14))

        versions = store.get_prior_versions(entry["id"])
        if not versions:
            tk.Label(wrap, text="No prior versions yet.", bg=T["bg"],
                     fg=T["text_dim"], font=("Segoe UI", 10)).pack(pady=20)
            return
        for v in reversed(versions):
            self._make_version_card(wrap, entry, v)

    def _make_version_card(self, parent, parent_entry, version):
        vkey = self._version_key(parent_entry["id"], version.get("version", 0))
        free = is_free_access(self.user, vkey)
        cost = 0 if free else get_access_cost(version)
        free_h = free_hours_remaining(self.user, vkey) if free else None

        card = tk.Frame(parent, bg=T["card"], cursor="hand2",
                        highlightthickness=1, highlightbackground=T["border"])
        card.pack(fill="x", pady=(0, 6))
        inner = tk.Frame(card, bg=T["card"])
        inner.pack(fill="x", padx=14, pady=10)
        tk.Label(inner, text=f'v{version.get("version")}', bg=T["card"],
                 fg=T["cyan"], font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 14))
        info = tk.Frame(inner, bg=T["card"])
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=version.get("author", ""), bg=T["card"], fg=T["text"],
                 font=("Segoe UI", 10), anchor="w").pack(fill="x", anchor="w")
        tk.Label(info, text=fmt_date(version.get("updated", "")), bg=T["card"],
                 fg=T["text_muted"], font=("Segoe UI", 9), anchor="w").pack(fill="x", anchor="w")

        cost_box = tk.Frame(inner, bg=T["card"])
        cost_box.pack(side="right")
        if cost == 0:
            tk.Label(cost_box, text="0 INF", bg=T["card"], fg=T["text"],
                     font=("Segoe UI", 9, "bold")).pack(side="left")
            tk.Label(cost_box, text=f"  (next {free_h}h)", bg=T["card"],
                     fg=T["cyan"], font=("Segoe UI", 8)).pack(side="left")
        else:
            if cost >= INF_HIGH_THRESHOLD:
                bg, fg = T["inf_high_bg"], T["inf_high"]
            else:
                bg, fg = T["inf_normal_bg"], T["inf_normal"]
            tk.Label(cost_box, text=f"{cost} INF", bg=bg, fg=fg,
                     font=("Segoe UI", 9, "bold"), padx=8, pady=1).pack(side="left")

        def on_click(_e=None):
            c = 0 if is_free_access(self.user, vkey) else get_access_cost(version)
            if c > 0:
                if not self._confirm(
                    "Confirm spend",
                    f'View v{version.get("version")} of '
                    f'"{self._short(parent_entry.get("title", ""))}"?\n\n'
                    f'Share: {c} influence\nYour balance: {self.user["influence"]}'):
                    return
                if not use_influence(self.user, c):
                    self._warn("Not enough influence", "You can't afford this version yet.")
                    self._refresh_balance()
                    return
                record_access(self.user, vkey)   # 24h grace on this version
                self._refresh_balance()
            self.show_contribution(version, read_only=True, parent_entry=parent_entry)

        for w in [card] + self._descendants(card):
            w.bind("<Button-1>", on_click)

    # =======================================================================
    # TOOLS (Easter egg)
    # =======================================================================
    def show_tools(self):
        self.back_target = self.show_home
        self._clear_content()
        self._build_top_bar_back(title_text="Tools")
        wrap = tk.Frame(self.content, bg=T["bg"])
        wrap.pack(fill="both", expand=True, padx=22, pady=18)
        tk.Label(wrap, text="Tools are placeholders in the alpha. Running one "
                            "simulates the action; functional tools land in a "
                            "later phase.",
                 bg=T["bg"], fg=T["text_muted"], font=("Segoe UI", 9),
                 wraplength=820, justify="left", anchor="w").pack(fill="x", pady=(0, 14))
        tools = store.get_tools()
        if not tools:
            tk.Label(wrap, text="No tools seeded.", bg=T["bg"], fg=T["text_dim"]).pack()
            return
        for t in tools:
            self._make_tool_card(wrap, t)

    def _make_tool_card(self, parent, tool):
        card = tk.Frame(parent, bg=T["card"], highlightthickness=1,
                        highlightbackground=T["border"])
        card.pack(fill="x", pady=(0, 6))
        inner = tk.Frame(card, bg=T["card"])
        inner.pack(fill="x", padx=14, pady=10)
        col = tk.Frame(inner, bg=T["card"])
        col.pack(side="left", fill="x", expand=True)
        tk.Label(col, text=tool.get("name", tool["id"]), bg=T["card"], fg=T["text"],
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x", anchor="w")
        tk.Label(col, text=tool.get("description", ""), bg=T["card"],
                 fg=T["text_muted"], font=("Segoe UI", 9), wraplength=600,
                 justify="left", anchor="w").pack(fill="x", anchor="w")
        cost = get_tool_cost(tool, store.get_entry)
        if cost >= INF_HIGH_THRESHOLD:
            bg, fg = T["inf_high_bg"], T["inf_high"]
        else:
            bg, fg = T["inf_normal_bg"], T["inf_normal"]
        tk.Label(inner, text=f"{cost} INF", bg=bg, fg=fg,
                 font=("Segoe UI", 9, "bold"), padx=8, pady=1).pack(side="right", padx=(0, 8))

        def on_run(_e=None):
            if not self._confirm("Confirm spend",
                                 f'Run "{tool.get("name", tool["id"])}"?\n\n'
                                 f'Share: {cost} influence\n'
                                 f'Your balance: {self.user["influence"]}'):
                return
            if not use_influence(self.user, cost):
                self._warn("Not enough influence", "You can't afford this tool yet.")
                self._refresh_balance()
                return
            self._refresh_balance()
            self._info("Tool ran",
                       f'Running "{tool.get("name", tool["id"])}" ... (simulated in alpha).')

        run_btn = self._make_pill_button(inner, "Run", on_run, primary=True)
        run_btn.pack(side="right", padx=(0, 8))


# ===========================================================================
if __name__ == "__main__":
    App().mainloop()
