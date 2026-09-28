#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
المسبحة — عدّاد التسبيح لسطح المكتب (ويندوز / ماك / لينكس)

التشغيل:    python masbaha.py
لا يحتاج أي مكتبات إضافية (tkinter مضمّنة مع بايثون).

لتحويله إلى برنامج .exe مستقل على ويندوز:
    pip install pyinstaller
    pyinstaller --onefile --windowed --name Masbaha masbaha.py
ثم ستجد الملف في مجلد dist.
"""
import datetime
import json
import math
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont

DATA_FILE = Path.home() / ".masbaha_ar.json"
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]  # weekday(): الاثنين = 0
SEQ = ["subhan", "hamd", "akbar"]
FINAL_MSG = "تم التسبيح. أكمل المئة بـ: لا إله إلا الله وحده لا شريك له، له الملك وله الحمد وهو على كل شيء قدير"

THEMES = {
    "emerald": dict(name="زمرّد", bg="#0b2620", bg2="#0f322a", surface="#12372f", ink="#f2ead5",
                    muted="#8db0a2", line="#1f4c41", bead="#21493f", bead_on="#f2ead5", accent="#e5b45c"),
    "night": dict(name="ليل", bg="#12152a", bg2="#191d38", surface="#1d2242", ink="#e8e9f8",
                  muted="#9a9fc6", line="#2b3161", bead="#2a2f5a", bead_on="#c9ceff", accent="#f0c674"),
    "dawn": dict(name="فجر", bg="#e8f0ec", bg2="#dbe7e1", surface="#f5f9f7", ink="#0d2a24",
                 muted="#56706a", line="#c2d4cb", bead="#c0d3c9", bead_on="#12503f", accent="#b3711a"),
}


def defaults():
    return {
        "dhikrs": [
            {"id": "subhan", "text": "سبحان الله", "target": 33},
            {"id": "hamd", "text": "الحمد لله", "target": 33},
            {"id": "akbar", "text": "الله أكبر", "target": 34},
            {"id": "tahlil", "text": "لا إله إلا الله", "target": 100},
            {"id": "istighfar", "text": "أستغفر الله", "target": 100},
            {"id": "bihamd", "text": "سبحان الله وبحمده", "target": 100},
            {"id": "azim", "text": "سبحان الله العظيم", "target": 100},
            {"id": "salat", "text": "اللهم صلِّ وسلِّم على نبينا محمد", "target": 100},
            {"id": "hawqala", "text": "لا حول ولا قوة إلا بالله", "target": 100},
            {"id": "free", "text": "تسبيح حر", "target": 0},
        ],
        "currentId": "subhan",
        "counts": {}, "rounds": {}, "totals": {}, "daily": {},
        "step": 1, "seq": False, "geometry": "",
        "settings": {"theme": "emerald", "digits": "ar", "sound": False, "topmost": False},
    }


def toint(text, default):
    tr = {ord(a): str(i) for i, a in enumerate(AR_DIGITS)}
    tr.update({ord(a): str(i) for i, a in enumerate("۰۱۲۳۴۵۶۷۸۹")})
    s = "".join(ch for ch in str(text).translate(tr) if ch.isdigit())
    return int(s) if s else default


def today_key(d=None):
    return (d or datetime.date.today()).isoformat()


class App:
    def __init__(self):
        self.state = self.load()
        self.undo = []
        self.locked = False
        self.adv_job = None
        self.toast_job = None
        self.dlg = None
        self.last_key = 0.0
        self.chip_box = None

        self.root = tk.Tk()
        self.root.title("المسبحة")
        self.root.minsize(420, 560)
        self.root.geometry(self.state.get("geometry") or "480x700")

        fams = set(tkfont.families(self.root))
        self.f_ui = self.pick(fams, ["Segoe UI", "Tahoma", "Noto Sans Arabic", "Geeza Pro", "DejaVu Sans", "Arial"], "TkDefaultFont")
        self.f_naskh = self.pick(fams, ["Amiri", "Traditional Arabic", "Arabic Typesetting", "Noto Naskh Arabic", "Geeza Pro"], self.f_ui)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<space>", self.on_key_tap)
        self.root.bind("<Return>", self.on_key_tap)
        self.root.bind("<KP_Enter>", self.on_key_tap)
        self.root.bind("<Control-z>", lambda e: self.undo_last())
        self.root.bind("<Control-Z>", lambda e: self.undo_last())
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)

        self.apply_topmost()
        self.build_main()

    # ---------- بيانات ----------
    @staticmethod
    def pick(fams, names, default):
        for n in names:
            if n in fams:
                return n
        return default

    def load(self):
        d = defaults()
        try:
            s = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            st = {**d, **s}
            st["settings"] = {**d["settings"], **s.get("settings", {})}
            if not st.get("dhikrs"):
                st["dhikrs"] = d["dhikrs"]
            if not any(x["id"] == st["currentId"] for x in st["dhikrs"]):
                st["currentId"] = st["dhikrs"][0]["id"]
            if st["settings"]["theme"] not in THEMES:
                st["settings"]["theme"] = "emerald"
            return st
        except Exception:
            return d

    def save(self):
        try:
            DATA_FILE.write_text(json.dumps(self.state, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def on_close(self):
        try:
            self.state["geometry"] = self.root.geometry()
        except Exception:
            pass
        self.save()
        self.root.destroy()

    @property
    def t(self):
        return THEMES[self.state["settings"]["theme"]]

    def cur(self):
        for d in self.state["dhikrs"]:
            if d["id"] == self.state["currentId"]:
                return d
        return self.state["dhikrs"][0]

    # ---------- أدوات ----------
    def fmt(self, n, group=False):
        n = int(round(n))
        s = f"{n:,}" if group else str(n)
        if self.state["settings"]["digits"] == "ar":
            s = s.translate(str.maketrans("0123456789,", AR_DIGITS + "٬"))
        return s

    def plural(self, n, one, two, few, many):
        if n == 1:
            return one
        if n == 2:
            return two
        return f"{self.fmt(n)} {few if n <= 10 else many}"

    def apply_topmost(self):
        try:
            self.root.attributes("-topmost", bool(self.state["settings"]["topmost"]))
        except tk.TclError:
            pass

    def toggle_fullscreen(self, _e=None):
        try:
            self.root.attributes("-fullscreen", not self.root.attributes("-fullscreen"))
        except tk.TclError:
            pass

    def exit_fullscreen(self, _e=None):
        try:
            if self.root.attributes("-fullscreen"):
                self.root.attributes("-fullscreen", False)
        except tk.TclError:
            pass

    def sound(self, kind="tick"):
        if not self.state["settings"]["sound"]:
            return
        if sys.platform.startswith("win"):
            import winsound
            f, ms = (660, 30) if kind == "tick" else (880, 160)
            threading.Thread(target=lambda: winsound.Beep(f, ms), daemon=True).start()
        else:
            try:
                self.root.bell()
            except tk.TclError:
                pass

    def mkbtn(self, parent, text, cmd, bg=None, fg=None, font=None, padx=12, pady=8):
        t = self.t
        bg = bg or parent.cget("bg")
        fg = fg or t["muted"]
        lb = tk.Label(parent, text=text, bg=bg, fg=fg, font=font or (self.f_ui, 12), padx=padx, pady=pady, cursor="hand2")
        lb.bind("<Button-1>", lambda e: cmd())
        if fg == t["muted"]:
            lb.bind("<Enter>", lambda e: lb.config(fg=t["ink"]) if not getattr(lb, "_armed", False) else None)
            lb.bind("<Leave>", lambda e: lb.config(fg=t["muted"]) if not getattr(lb, "_armed", False) else None)
        return lb

    def confirm_click(self, w, armed_text, fn):
        t = self.t
        try:
            if getattr(w, "_armed", False):
                w._armed = False
                w.after_cancel(w._job)
                w.config(text=w._old, fg=t["muted"])
                fn()
                return
            w._armed = True
            w._old = w.cget("text")
            w.config(text=armed_text, fg=t["accent"])

            def back():
                try:
                    w._armed = False
                    w.config(text=w._old, fg=t["muted"])
                except tk.TclError:
                    pass
            w._job = w.after(2600, back)
        except tk.TclError:
            pass

    def toast(self, msg, ms=2200):
        try:
            self.toast_lb.config(text=msg)
            self.toast_lb.place(relx=0.5, rely=0.9, anchor="s")
            self.toast_lb.lift()
            if self.toast_job:
                self.root.after_cancel(self.toast_job)
            self.toast_job = self.root.after(ms, self.toast_lb.place_forget)
        except tk.TclError:
            pass

    # ---------- الواجهة الرئيسية ----------
    def build_main(self):
        t = self.t
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(bg=t["bg"])

        top = tk.Frame(self.root, bg=t["bg"])
        top.pack(fill="x", padx=10, pady=(10, 0))
        self.mkbtn(top, "الإعدادات", self.open_settings).pack(side="right")
        self.mkbtn(top, "السجل", self.open_stats).pack(side="left")
        self.name_lb = tk.Label(top, bg=t["bg"], fg=t["ink"], cursor="hand2", font=(self.f_naskh, 26, "bold"))
        self.name_lb.pack(side="top", fill="x", expand=True)
        self.name_lb.bind("<Button-1>", lambda e: self.open_picker())

        self.seq_frame = tk.Frame(self.root, bg=t["bg"])
        self.seq_frame.pack(fill="x", pady=(2, 0))

        self.mid = tk.Frame(self.root, bg=t["bg"])
        self.mid.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(self.mid, bg=t["bg"], highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        self.canvas.bind("<Configure>", lambda e: self.draw())
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.hint = tk.Label(self.mid, bg=t["bg"], fg=t["muted"], font=(self.f_ui, 12), height=2)
        self.hint.pack(fill="x")
        self.hint.bind("<Button-1>", lambda e: self.tap())

        bottom = tk.Frame(self.root, bg=t["bg"], highlightthickness=1, highlightbackground=t["line"])
        bottom.pack(fill="x", side="bottom")
        self.btn_undo = self.mkbtn(bottom, "تراجع", self.undo_last)
        self.btn_reset = self.mkbtn(bottom, "تصفير", lambda: self.confirm_click(self.btn_reset, "تأكيد؟", self.reset_current))
        self.btn_adjust = self.mkbtn(bottom, "ضبط", self.open_adjust)
        self.btn_copy = self.mkbtn(bottom, "نسخ", self.copy_share)
        self.btn_dhikr = self.mkbtn(bottom, "الأذكار", self.open_picker)
        for b in (self.btn_dhikr, self.btn_undo, self.btn_reset, self.btn_adjust, self.btn_copy):
            b.pack(side="right", expand=True, fill="x")

        self.toast_lb = tk.Label(self.root, bg=t["ink"], fg=t["bg"], font=(self.f_ui, 11), padx=14, pady=8, wraplength=360, justify="center")
        self.render()

    def render(self):
        t = self.t
        d = self.cur()
        self.name_lb.config(text=d["text"] + "  ▾", font=(self.f_naskh, 20 if len(d["text"]) > 22 else 26, "bold"))

        for w in self.seq_frame.winfo_children():
            w.destroy()
        if self.state["seq"]:
            idx = SEQ.index(self.state["currentId"]) if self.state["currentId"] in SEQ else -1
            box = tk.Frame(self.seq_frame, bg=t["bg"])
            box.pack()
            for i, sid in enumerate(SEQ):
                dd = next((x for x in self.state["dhikrs"] if x["id"] == sid), None)
                if not dd:
                    continue
                if i < idx:
                    kw = dict(text="✓ " + dd["text"], fg=t["accent"], bg=t["bg"])
                elif i == idx:
                    kw = dict(text=dd["text"], fg=t["bg"], bg=t["bead_on"])
                else:
                    kw = dict(text=dd["text"], fg=t["muted"], bg=t["bg"])
                tk.Label(box, font=(self.f_ui, 11), padx=10, pady=2, **kw).pack(side="right", padx=3)

        c = self.state["counts"].get(d["id"], 0)
        done = d["target"] > 0 and c >= d["target"]
        if done:
            self.hint.config(text="اكتملت الجولة — المس أو اضغط مسافة لبدء جولة جديدة", fg=t["accent"], font=(self.f_ui, 12, "bold"))
        elif c == 0:
            self.hint.config(text="اضغط في أي مكان أو مفتاح المسافة للعدّ", fg=t["muted"], font=(self.f_ui, 12))
        else:
            self.hint.config(text=" ", fg=t["muted"], font=(self.f_ui, 12))
        self.draw()

    def draw(self):
        c = self.canvas
        t = self.t
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        half = (min(w, h) - 10) / 2
        if half < 60:
            return
        cx, cy = w / 2, h / 2
        d = self.cur()
        cnt = self.state["counts"].get(d["id"], 0)
        tg = d["target"]
        B = min(tg, 100) if tg > 0 else 33
        if tg > 0:
            lit = min(B, int(cnt / tg * B + 0.5))
        else:
            m = cnt % 33
            lit = 33 if (m == 0 and cnt > 0) else m
        done = tg > 0 and cnt >= tg
        Rb, Rd, sc = half * 0.84, half * 0.68, half / 150

        c.create_oval(cx - Rd, cy - Rd, cx + Rd, cy + Rd, fill=t["bg2"], outline=t["line"])
        c.create_oval(cx - Rb, cy - Rb, cx + Rb, cy + Rb, outline=t["line"])
        r = max(2.2 * sc, min(9.5 * sc, 2 * math.pi * Rb / B * 0.39))
        on_col = t["accent"] if done else t["bead_on"]
        for i in range(B):
            a = -math.pi / 2 + i * 2 * math.pi / B
            x, y = cx + Rb * math.cos(a), cy + Rb * math.sin(a)
            on = i < lit
            head = on and lit < B and i == lit - 1
            c.create_oval(x - r, y - r, x + r, y + r,
                          fill=on_col if on else t["bead"],
                          outline=t["ink"] if head else (on_col if on else t["bead"]),
                          width=2 if head else 1)

        L = len(str(cnt))
        k = 0.6 if L <= 3 else 0.46 if L == 4 else 0.38 if L == 5 else 0.3
        c.create_text(cx, cy - half * 0.08, text=self.fmt(cnt), fill=t["accent"] if done else t["ink"],
                      font=(self.f_ui, -int(half * k)))

        if tg > 0:
            sub = "من " + self.fmt(tg)
            rr = self.state["rounds"].get(d["id"], 0)
            if rr > 0:
                sub += " · أكملت " + self.plural(rr, "جولة واحدة", "جولتان", "جولات", "جولة")
        else:
            sub = ("أكملت " + self.plural(cnt // 33, "دورة واحدة", "دورتان", "دورات", "دورة") + " · " if cnt >= 33 else "بلا هدف · ") + "دورة كل " + self.fmt(33)
        c.create_text(cx, cy + half * 0.30, text=sub, fill=t["muted"], font=(self.f_ui, -max(11, int(half * 0.075))))

        chip = c.create_text(cx, cy + half * 0.47, text="+" + self.fmt(self.state["step"]), fill=t["muted"],
                             font=(self.f_ui, -max(12, int(half * 0.085)), "bold"))
        x1, y1, x2, y2 = c.bbox(chip)
        pad = 8
        box = (x1 - pad * 1.5, y1 - pad * 0.5, x2 + pad * 1.5, y2 + pad * 0.5)
        rect = c.create_rectangle(*box, outline=t["line"], fill=t["surface"])
        c.tag_lower(rect, chip)
        self.chip_box = box

    # ---------- العدّ ----------
    def on_canvas_click(self, e):
        b = self.chip_box
        if b and b[0] <= e.x <= b[2] and b[1] <= e.y <= b[3]:
            self.open_adjust()
        else:
            self.tap()

    def on_key_tap(self, e):
        if isinstance(self.root.focus_get(), (tk.Entry, tk.Text)):
            return
        now = time.monotonic()
        if now - self.last_key < 0.06:
            return
        self.last_key = now
        self.tap()

    def tap(self):
        if self.locked:
            return
        s = self.state
        d = self.cur()
        c = s["counts"].get(d["id"], 0)
        tg = d["target"]
        snap = dict(id=d["id"], prev_count=c, prev_rounds=s["rounds"].get(d["id"], 0),
                    prev_seq=s["seq"], added=0, day=today_key())
        if tg > 0 and c >= tg:
            c = 0
        n = c + s["step"]
        if tg > 0 and n > tg:
            n = tg
        added = n - c
        s["counts"][d["id"]] = n
        s["totals"][d["id"]] = s["totals"].get(d["id"], 0) + added
        s["daily"][snap["day"]] = s["daily"].get(snap["day"], 0) + added
        snap["added"] = added
        self.undo.append(snap)
        if len(self.undo) > 100:
            self.undo.pop(0)

        completed = tg > 0 and n >= tg
        if completed:
            s["rounds"][d["id"]] = s["rounds"].get(d["id"], 0) + 1
            self.sound("done")
        else:
            self.sound("tick")

        if completed and s["seq"] and d["id"] in SEQ:
            idx = SEQ.index(d["id"])
            if idx < len(SEQ) - 1:
                self.locked = True
                self.adv_job = self.root.after(650, lambda: self.advance(SEQ[idx + 1]))
            else:
                s["seq"] = False
                self.toast(FINAL_MSG, 7000)
        self.save()
        self.render()

    def advance(self, nid):
        self.locked = False
        self.state["currentId"] = nid
        self.save()
        self.render()

    def undo_last(self):
        if self.adv_job:
            self.root.after_cancel(self.adv_job)
            self.adv_job = None
        self.locked = False
        if not self.undo:
            self.toast("لا يوجد ما يُتراجع عنه")
            return
        sn = self.undo.pop()
        s = self.state
        if not any(x["id"] == sn["id"] for x in s["dhikrs"]):
            return
        s["counts"][sn["id"]] = sn["prev_count"]
        s["rounds"][sn["id"]] = sn["prev_rounds"]
        if sn["added"]:
            s["totals"][sn["id"]] = max(0, s["totals"].get(sn["id"], 0) - sn["added"])
            s["daily"][sn["day"]] = max(0, s["daily"].get(sn["day"], 0) - sn["added"])
        s["currentId"] = sn["id"]
        s["seq"] = sn["prev_seq"]
        self.save()
        self.render()

    def reset_current(self):
        d = self.cur()
        s = self.state
        self.undo.append(dict(id=d["id"], prev_count=s["counts"].get(d["id"], 0),
                              prev_rounds=s["rounds"].get(d["id"], 0), prev_seq=s["seq"], added=0, day=today_key()))
        s["counts"][d["id"]] = 0
        s["rounds"][d["id"]] = 0
        self.save()
        self.render()

    def copy_share(self):
        d = self.cur()
        c = self.state["counts"].get(d["id"], 0)
        today = self.state["daily"].get(today_key(), 0)
        line = f"{d['text']} — {self.fmt(c)}" + (f" من {self.fmt(d['target'])}" if d["target"] > 0 else "")
        text = f"{line}\nإجمالي اليوم: {self.fmt(today, True)}"
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.toast("تم نسخ الحصيلة")
        except tk.TclError:
            self.toast("تعذّر النسخ")

    # ---------- نوافذ الحوار ----------
    def dialog(self, title, w, h):
        t = self.t
        if self.dlg is not None:
            try:
                self.dlg.destroy()
            except tk.TclError:
                pass
        d = tk.Toplevel(self.root)
        d.title(title)
        d.configure(bg=t["surface"])
        d.transient(self.root)
        self.root.update_idletasks()
        x = self.root.winfo_x() + max(0, (self.root.winfo_width() - w) // 2)
        y = self.root.winfo_y() + max(0, (self.root.winfo_height() - h) // 3)
        d.geometry(f"{w}x{h}+{x}+{y}")
        d.bind("<Escape>", lambda e: d.destroy())
        self.dlg = d
        return d

    def head(self, d, text):
        t = self.t
        tk.Label(d, text=text, bg=t["surface"], fg=t["ink"], font=(self.f_ui, 15, "bold"), anchor="e").pack(fill="x", padx=18, pady=(16, 8))

    def entry(self, parent, value="", width=None):
        t = self.t
        e = tk.Entry(parent, justify="right", bg=t["bg"], fg=t["ink"], insertbackground=t["ink"], relief="flat",
                     highlightthickness=1, highlightbackground=t["line"], highlightcolor=t["accent"], font=(self.f_ui, 13))
        if width:
            e.config(width=width)
        e.insert(0, value)
        return e

    def label(self, parent, text, muted=True, bold=False, size=11):
        t = self.t
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=t["muted"] if muted else t["ink"],
                        font=(self.f_ui, size, "bold" if bold else "normal"), anchor="e", justify="right")

    def scroll_frame(self, parent, bg):
        outer = tk.Frame(parent, bg=bg)
        cv = tk.Canvas(outer, bg=bg, highlightthickness=0)
        sb = tk.Scrollbar(outer, orient="vertical", command=cv.yview)
        inner = tk.Frame(cv, bg=bg)
        win = cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="left", fill="y")
        cv.pack(side="right", fill="both", expand=True)

        def wheel(e):
            try:
                if e.num == 4:
                    cv.yview_scroll(-1, "units")
                elif e.num == 5:
                    cv.yview_scroll(1, "units")
                else:
                    cv.yview_scroll(-1 if e.delta > 0 else 1, "units")
            except tk.TclError:
                pass

        def on(_e):
            cv.bind_all("<MouseWheel>", wheel)
            cv.bind_all("<Button-4>", wheel)
            cv.bind_all("<Button-5>", wheel)

        def off(_e):
            cv.unbind_all("<MouseWheel>")
            cv.unbind_all("<Button-4>")
            cv.unbind_all("<Button-5>")
        outer.bind("<Enter>", on)
        outer.bind("<Leave>", off)
        return outer, inner

    # --- الأذكار ---
    def open_picker(self):
        t = self.t
        d = self.dialog("الأذكار", 460, 640)
        self.head(d, "الأذكار")

        card = tk.Frame(d, bg=t["surface"], highlightthickness=1, highlightbackground=t["accent"], cursor="hand2")
        card.pack(fill="x", padx=18, pady=(0, 10))
        l1 = tk.Label(card, text="تسبيح ما بعد الصلاة", bg=t["surface"], fg=t["ink"], font=(self.f_ui, 13, "bold"), anchor="e", cursor="hand2")
        l2 = tk.Label(card, text="سبحان الله ٣٣ ← الحمد لله ٣٣ ← الله أكبر ٣٤ (ينتقل تلقائيًا)", bg=t["surface"], fg=t["muted"], font=(self.f_ui, 10), anchor="e", cursor="hand2")
        l1.pack(fill="x", padx=12, pady=(10, 0))
        l2.pack(fill="x", padx=12, pady=(0, 10))
        for w in (card, l1, l2):
            w.bind("<Button-1>", lambda e: self.start_seq())

        add = tk.Frame(d, bg=t["surface"])
        add.pack(side="bottom", fill="x", padx=18, pady=(6, 16))
        self.label(add, "ذكر خاص بك (الهدف ٠ = بلا هدف)").pack(fill="x", pady=(0, 4))
        row = tk.Frame(add, bg=t["surface"])
        row.pack(fill="x")
        e_text = self.entry(row)
        e_text.pack(side="right", fill="x", expand=True, ipady=6)
        e_tg = self.entry(row, width=7)
        e_tg.pack(side="right", padx=(0, 6), ipady=6)
        e_tg.insert(0, "")

        def do_add(_e=None):
            txt = e_text.get().strip()
            if not txt:
                e_text.focus_set()
                return
            nid = f"c{int(time.time() * 1000)}"
            self.state["dhikrs"].append({"id": nid, "text": txt[:60], "target": toint(e_tg.get(), 0), "custom": True})
            self.pick_dhikr(nid)
        e_text.bind("<Return>", do_add)
        self.mkbtn(add, "إضافة الذكر", do_add, bg=t["bead_on"], fg=t["bg"], font=(self.f_ui, 12, "bold")).pack(fill="x", pady=(8, 0))

        outer, inner = self.scroll_frame(d, t["surface"])
        outer.pack(fill="both", expand=True, padx=12)
        for dh in self.state["dhikrs"]:
            is_cur = dh["id"] == self.state["currentId"]
            bg = t["bg2"] if is_cur else t["surface"]
            r = tk.Frame(inner, bg=bg, cursor="hand2")
            r.pack(fill="x", pady=1)
            cnt = self.state["counts"].get(dh["id"], 0)
            name = tk.Label(r, text=dh["text"], bg=bg, fg=t["ink"], font=(self.f_naskh, 17, "bold"), anchor="e", cursor="hand2")
            name.pack(side="right", fill="x", expand=True, padx=(0, 8), pady=4)
            meta = tk.Label(r, text=("الهدف " + self.fmt(dh["target"])) if dh["target"] > 0 else "بلا هدف",
                            bg=bg, fg=t["muted"], font=(self.f_ui, 10), cursor="hand2")
            meta.pack(side="left", padx=(8, 0))
            cl = tk.Label(r, text=self.fmt(cnt), bg=bg, fg=t["ink"], font=(self.f_ui, 12, "bold"), width=4, cursor="hand2")
            cl.pack(side="left")
            for w in (r, name, meta, cl):
                w.bind("<Button-1>", lambda e, i=dh["id"]: self.pick_dhikr(i))
            if dh.get("custom"):
                dl = tk.Label(r, text="حذف", bg=bg, fg=t["muted"], font=(self.f_ui, 10), cursor="hand2", padx=6)
                dl.pack(side="left")
                dl.bind("<Button-1>", lambda e, w=dl, i=dh["id"]: self.confirm_click(w, "تأكيد؟", lambda: self.remove_dhikr(i)))

    def pick_dhikr(self, did):
        if self.adv_job:
            self.root.after_cancel(self.adv_job)
            self.adv_job = None
        self.locked = False
        self.state["currentId"] = did
        self.state["seq"] = False
        self.undo = []
        self.save()
        self.close_dialog()
        self.render()

    def remove_dhikr(self, did):
        s = self.state
        s["dhikrs"] = [x for x in s["dhikrs"] if x["id"] != did]
        for k in ("counts", "rounds", "totals"):
            s[k].pop(did, None)
        if s["currentId"] == did:
            s["currentId"] = s["dhikrs"][0]["id"]
        self.undo = []
        self.save()
        self.render()
        self.open_picker()

    def start_seq(self):
        if self.adv_job:
            self.root.after_cancel(self.adv_job)
        self.locked = False
        for sid in SEQ:
            self.state["counts"][sid] = 0
        self.state["seq"] = True
        self.state["currentId"] = SEQ[0]
        self.undo = []
        self.save()
        self.close_dialog()
        self.render()
        self.toast("ابدأ: سبحان الله")

    def close_dialog(self):
        if self.dlg is not None:
            try:
                self.dlg.destroy()
            except tk.TclError:
                pass
            self.dlg = None

    # --- ضبط العدّاد ---
    def open_adjust(self):
        t = self.t
        dh = self.cur()
        d = self.dialog("ضبط العدّاد", 400, 470)
        self.head(d, "ضبط العدّاد")
        body = tk.Frame(d, bg=t["surface"])
        body.pack(fill="both", expand=True, padx=18)

        def field(title, value, quick):
            self.label(body, title).pack(fill="x", pady=(10, 4))
            e = self.entry(body, value)
            e.pack(fill="x", ipady=6)
            if quick:
                qr = tk.Frame(body, bg=t["surface"])
                qr.pack(fill="x", pady=(6, 0))
                for v, lab in quick:
                    b = tk.Label(qr, text=lab, bg=t["surface"], fg=t["muted"], font=(self.f_ui, 10), padx=10, pady=3,
                                 highlightthickness=1, highlightbackground=t["line"], cursor="hand2")
                    b.pack(side="right", padx=(0, 5))
                    b.bind("<Button-1>", lambda ev, v=v: (e.delete(0, "end"), e.insert(0, self.fmt(v))))
            return e

        e_c = field("العدّ الحالي", self.fmt(self.state["counts"].get(dh["id"], 0)), None)
        e_s = field("مقدار الزيادة في كل ضغطة", self.fmt(self.state["step"]), [(v, self.fmt(v)) for v in (1, 2, 3, 5, 10)])
        e_t = field("الهدف (٠ = بلا هدف)", self.fmt(dh["target"]),
                    [(0, "بلا هدف")] + [(v, self.fmt(v)) for v in (33, 34, 99, 100, 1000)])
        e_c.focus_set()
        e_c.select_range(0, "end")

        def save(_e=None):
            old = self.state["counts"].get(dh["id"], 0)
            tg = toint(e_t.get(), dh["target"])
            st = min(1000, max(1, toint(e_s.get(), self.state["step"])))
            c = toint(e_c.get(), old)
            if tg > 0 and c > tg:
                c = tg
            if c != old:
                self.undo.append(dict(id=dh["id"], prev_count=old, prev_rounds=self.state["rounds"].get(dh["id"], 0),
                                      prev_seq=self.state["seq"], added=0, day=today_key()))
            dh["target"] = tg
            self.state["step"] = st
            self.state["counts"][dh["id"]] = c
            self.save()
            self.close_dialog()
            self.render()
        for e in (e_c, e_s, e_t):
            e.bind("<Return>", save)
        self.mkbtn(d, "حفظ", save, bg=t["bead_on"], fg=t["bg"], font=(self.f_ui, 13, "bold"), pady=10).pack(fill="x", padx=18, pady=16, side="bottom")

    # --- الإعدادات ---
    def open_settings(self):
        t = self.t
        d = self.dialog("الإعدادات", 420, 520)
        self.head(d, "الإعدادات")
        body = tk.Frame(d, bg=t["surface"])
        body.pack(fill="both", expand=True, padx=18)

        def seg(title, key, options):
            self.label(body, title, muted=False, size=11).pack(fill="x", pady=(10, 6))
            row = tk.Frame(body, bg=t["surface"], highlightthickness=1, highlightbackground=t["line"])
            row.pack(fill="x")
            for val, lab in options:
                on = self.state["settings"][key] == val
                b = tk.Label(row, text=lab, bg=t["bead_on"] if on else t["surface"], fg=t["bg"] if on else t["muted"],
                             font=(self.f_ui, 11, "bold" if on else "normal"), pady=7, cursor="hand2")
                b.pack(side="right", expand=True, fill="x")
                b.bind("<Button-1>", lambda e, v=val: self.set_setting(key, v))

        def toggle(title, key):
            row = tk.Frame(body, bg=t["surface"], cursor="hand2")
            row.pack(fill="x", pady=(12, 0))
            on = self.state["settings"][key]
            lb = tk.Label(row, text=title, bg=t["surface"], fg=t["ink"], font=(self.f_ui, 12), anchor="e", cursor="hand2")
            lb.pack(side="right")
            pill = tk.Label(row, text="مفعّل" if on else "متوقف", bg=t["bead_on"] if on else t["bead"],
                            fg=t["bg"] if on else t["muted"], font=(self.f_ui, 10, "bold"), padx=12, pady=2, cursor="hand2")
            pill.pack(side="left")
            for w in (row, lb, pill):
                w.bind("<Button-1>", lambda e: self.set_setting(key, not self.state["settings"][key]))

        seg("المظهر", "theme", [(k, v["name"]) for k, v in THEMES.items()])
        seg("شكل الأرقام", "digits", [("ar", "٠١٢٣"), ("en", "0123")])
        toggle("صوت نقرة عند العدّ", "sound")
        toggle("إبقاء النافذة فوق باقي النوافذ", "topmost")
        self.label(body, "نصيحة: F11 للشاشة الكاملة، وCtrl+Z للتراجع.", size=10).pack(fill="x", pady=(16, 0))

        wipe = self.mkbtn(d, "مسح كل البيانات", lambda: self.confirm_click(wipe, "اضغط مرة أخرى للتأكيد", self.wipe_all), pady=10)
        wipe.pack(fill="x", padx=18, pady=16, side="bottom")

    def set_setting(self, key, val):
        self.state["settings"][key] = val
        self.save()
        if key == "topmost":
            self.apply_topmost()
        if key in ("theme", "digits"):
            self.build_main()
        self.open_settings()

    def wipe_all(self):
        try:
            DATA_FILE.unlink()
        except Exception:
            pass
        geo = self.state.get("geometry", "")
        self.state = defaults()
        self.state["geometry"] = geo
        self.undo = []
        self.close_dialog()
        self.apply_topmost()
        self.build_main()
        self.toast("تم مسح البيانات")

    # --- السجل ---
    def streak(self):
        n = 0
        d = datetime.date.today()
        if not self.state["daily"].get(today_key(d), 0) > 0:
            d -= datetime.timedelta(days=1)
        while self.state["daily"].get(today_key(d), 0) > 0:
            n += 1
            d -= datetime.timedelta(days=1)
        return n

    def open_stats(self):
        t = self.t
        s = self.state
        d = self.dialog("السجل", 460, 640)
        self.head(d, "سجلّك")
        today = datetime.date.today()
        days = []
        for i in range(6, -1, -1):
            dd = today - datetime.timedelta(days=i)
            days.append((s["daily"].get(today_key(dd), 0), DAYS[dd.weekday()], i == 0))
        total_all = sum(s["totals"].values())
        st = self.streak()

        kp = tk.Frame(d, bg=t["surface"])
        kp.pack(fill="x", padx=18)
        for val, lab in ((self.fmt(total_all, True), "الإجمالي"),
                         (self.fmt(st), "يوم متتالٍ" if st == 1 else "أيام متتالية"),
                         (self.fmt(days[-1][0], True), "اليوم")):
            box = tk.Frame(kp, bg=t["bg2"])
            box.pack(side="right", expand=True, fill="x", padx=3)
            tk.Label(box, text=val, bg=t["bg2"], fg=t["ink"], font=(self.f_ui, 20)).pack(pady=(10, 0))
            tk.Label(box, text=lab, bg=t["bg2"], fg=t["muted"], font=(self.f_ui, 10)).pack(pady=(0, 10))

        self.label(d, "آخر ٧ أيام").pack(fill="x", padx=18, pady=(16, 4))
        cw, ch = 424, 170
        cv = tk.Canvas(d, width=cw, height=ch, bg=t["surface"], highlightthickness=0)
        cv.pack(padx=18)
        mx = max([x[0] for x in days] + [1])
        slot = cw / 7
        for idx, (n, name, is_today) in enumerate(days):
            xr = cw - idx * slot  # الأقدم على اليمين
            xc = xr - slot / 2
            bh = 0 if n == 0 else max(6, (ch - 52) * n / mx)
            base = ch - 22
            cv.create_rectangle(xc - 14, base - max(bh, 4), xc + 14, base, fill=t["accent"] if is_today else t["bead"], outline="")
            if n > 0:
                cv.create_text(xc, base - bh - 9, text=self.fmt(n), fill=t["muted"], font=(self.f_ui, 9))
            cv.create_text(xc, ch - 8, text=name, fill=t["muted"], font=(self.f_ui, 9))

        self.label(d, "حسب الذكر").pack(fill="x", padx=18, pady=(14, 4))
        rows = sorted([x for x in s["dhikrs"] if s["totals"].get(x["id"], 0) > 0], key=lambda x: -s["totals"][x["id"]])[:8]
        lst = tk.Frame(d, bg=t["surface"])
        lst.pack(fill="both", expand=True, padx=18, pady=(0, 14))
        if not rows:
            tk.Label(lst, text="لم تبدأ العدّ بعد. اضغط في النافذة الرئيسية لتبدأ.", bg=t["surface"], fg=t["muted"], font=(self.f_ui, 11)).pack(pady=8)
        for x in rows:
            r = tk.Frame(lst, bg=t["surface"])
            r.pack(fill="x", pady=3)
            tk.Label(r, text=x["text"], bg=t["surface"], fg=t["ink"], font=(self.f_naskh, 15, "bold"), anchor="e").pack(side="right")
            tk.Label(r, text=self.fmt(s["totals"][x["id"]], True), bg=t["surface"], fg=t["ink"], font=(self.f_ui, 12)).pack(side="left")

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
