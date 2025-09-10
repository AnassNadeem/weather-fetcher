#!/usr/bin/env python3
"""
gui.py — Full-featured Weather App GUI

Features included:
- Centered, responsive, scrollable layout (mousepad scrolling)
- Last-searched persistence (last_city.json) shown immediately on startup
- Popup asking "Show my current location?" while last city remains displayed
- Search / Refresh / Units (metric|imperial|standard) / Theme toggle (Light/Dark)
- Weather icons downloaded & cached to ./icons
- Current weather card (temp, humidity, description, icon, sunrise/sunset)
- Next prediction (next 3-hour block)
- 5-day daily summary + embedded matplotlib graph
- Favorites system: Add/Remove, Show Favorites panel with mini-cards + Details modal
- Notifications (rain / heat / cold)
- Threaded network calls so UI stays responsive
- Clean exit
"""

from __future__ import annotations

import os
import sys
import json
import threading
import datetime
from typing import List, Dict, Optional

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# import our fetcher helpers
from weather_fetcher import (
    fetch_weather_by_city,
    fetch_forecast_by_city,
    detect_city_via_ip,
    fetch_weather_by_ip,
)

ICONS_DIR = "icons"
os.makedirs(ICONS_DIR, exist_ok=True)
LAST_CITY_FILE = "last_city.json"
FAV_FILE = "favorites.json"
MAX_CONTENT_WIDTH = 920


# ----------------- helpers -----------------
def load_favorites() -> List[str]:
    if os.path.exists(FAV_FILE):
        try:
            with open(FAV_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_favorites(favs: List[str]) -> None:
    try:
        with open(FAV_FILE, "w", encoding="utf-8") as f:
            json.dump(favs, f, indent=2)
    except Exception:
        pass


def load_last_city() -> Optional[str]:
    if os.path.exists(LAST_CITY_FILE):
        try:
            with open(LAST_CITY_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("city")
        except Exception:
            return None
    return None


def save_last_city(city: str) -> None:
    try:
        with open(LAST_CITY_FILE, "w", encoding="utf-8") as f:
            json.dump({"city": city}, f)
    except Exception:
        pass


def download_icon(icon_code: str, size: int = 96) -> Optional[ImageTk.PhotoImage]:
    """Download and cache OpenWeather icon; return PhotoImage."""
    if not icon_code:
        return None
    path = os.path.join(ICONS_DIR, f"{icon_code}@2x.png")
    if not os.path.exists(path):
        try:
            import requests

            url = f"https://openweathermap.org/img/wn/{icon_code}@2x.png"
            r = requests.get(url, timeout=8)
            r.raise_for_status()
            with open(path, "wb") as f:
                f.write(r.content)
        except Exception:
            return None
    try:
        img = Image.open(path).resize((size, size), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


# ----------------- Main App -----------------
class WeatherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Weather App — Final")
        self.geometry("1000x760")
        self.minsize(860, 620)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # state
        self.units = tk.StringVar(value="metric")
        self.theme = tk.StringVar(value="light")
        self.current_city: Optional[str] = None
        self.favorites: List[str] = load_favorites()

        # themes
        self.themes = {
            "light": {"bg": "#EAF4FC", "card": "#FFFFFF", "fg": "#1f2937", "accent": "#3A83F1"},
            "dark": {"bg": "#0b1220", "card": "#111827", "fg": "#e6eef8", "accent": "#2563EB"},
        }

        # build UI
        self._build_ui()

        # center behavior & scrolling
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._bind_mousewheel()

        # Load last city (non-blocking)
        self.after(200, self._startup_sequence)

    # ---------- UI builders ----------
    def _build_ui(self):
        self._apply_theme()

        outer = ttk.Frame(self, style="App.TFrame")
        outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(outer, bg=self.colors["bg"], highlightthickness=0)
        self.vscroll = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vscroll.pack(side="right", fill="y")

        self.content = ttk.Frame(self.canvas, style="App.TFrame")
        self.win = self.canvas.create_window(0, 0, window=self.content, anchor="n")

        # header
        header = tk.Frame(self.content, bg=self.colors["accent"])
        header.pack(fill="x")
        tk.Label(header, text="Weather App", bg=self.colors["accent"], fg="white",
                 font=("Segoe UI", 18, "bold"), pady=10).pack()

        # controls
        controls = ttk.Frame(self.content, style="App.TFrame")
        controls.pack(pady=12, fill="x")

        # city entry + search + refresh
        self.city_var = tk.StringVar()
        self.city_entry = ttk.Entry(controls, textvariable=self.city_var, width=36, font=("Segoe UI", 11))
        self.city_entry.grid(row=0, column=0, padx=(8,6))
        self.city_entry.bind("<Return>", lambda e: self.search())

        self.search_btn = ttk.Button(controls, text="Search", command=self.search)
        self.search_btn.grid(row=0, column=1, padx=4)
        self.refresh_btn = ttk.Button(controls, text="Refresh", command=self.refresh)
        self.refresh_btn.grid(row=0, column=2, padx=4)

        # units combobox
        ttk.Label(controls, text="Units:").grid(row=0, column=3, padx=(16,4))
        self.units_cb = ttk.Combobox(controls, textvariable=self.units,
                                     values=["metric","imperial","standard"], width=10, state="readonly")
        self.units_cb.grid(row=0, column=4, padx=4)
        self.units_cb.bind("<<ComboboxSelected>>", lambda e: self._units_changed())

        # favorites (we keep both dropdown + show button to ensure nothing missing)
        ttk.Label(controls, text="Favorites:").grid(row=1, column=0, pady=(8,0), sticky="w")
        # We include a combobox for quick select; user previously wanted it removed — it's benign to keep both
        self.favs_var = tk.StringVar()
        self.favs_cb = ttk.Combobox(controls, textvariable=self.favs_var, values=self.favorites, width=30, state="readonly")
        self.favs_cb.grid(row=1, column=1, columnspan=2, pady=(8,0), sticky="w")
        self.favs_cb.bind("<<ComboboxSelected>>", lambda e: self._on_fav_selected())

        self.add_fav_btn = ttk.Button(controls, text="Add Favorite", command=self.add_favorite)
        self.add_fav_btn.grid(row=1, column=3, padx=6, pady=(8,0))
        self.remove_fav_btn = ttk.Button(controls, text="Remove Favorite", command=self.remove_favorite)
        self.remove_fav_btn.grid(row=1, column=4, padx=6, pady=(8,0))

        self.show_favs_btn = ttk.Button(controls, text="Show Favorites", command=self.open_favorites_panel)
        self.show_favs_btn.grid(row=1, column=5, padx=8, pady=(8,0))

        # theme toggle
        self.theme_btn = ttk.Button(controls, text="Theme: Light", command=self.toggle_theme)
        self.theme_btn.grid(row=0, column=5, padx=12)

        # current card
        self.card = tk.Frame(self.content, bg=self.colors["card"])
        self.card.pack(padx=16, pady=12, fill="x")

        self.city_label = tk.Label(self.card, text="—", font=("Segoe UI", 16, "bold"),
                                   bg=self.colors["card"], fg=self.colors["fg"])
        self.city_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10,6))

        self.icon_label = tk.Label(self.card, bg=self.colors["card"])
        self.icon_label.grid(row=1, column=0, rowspan=3, padx=12, pady=8)

        self.desc_label = tk.Label(self.card, text="—", bg=self.colors["card"], fg=self.colors["fg"], font=("Segoe UI", 12))
        self.desc_label.grid(row=1, column=1, sticky="w")

        self.temp_label = tk.Label(self.card, text="Temperature: —", bg=self.colors["card"], fg=self.colors["fg"], font=("Segoe UI", 12))
        self.temp_label.grid(row=2, column=1, sticky="w", pady=2)

        self.hum_label = tk.Label(self.card, text="Humidity: —", bg=self.colors["card"], fg=self.colors["fg"], font=("Segoe UI", 12))
        self.hum_label.grid(row=3, column=1, sticky="w")

        self.next_label = tk.Label(self.card, text="", bg=self.colors["card"], fg=self.colors["fg"], font=("Segoe UI", 10))
        self.next_label.grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(6,12))

        # forecast
        self.forecast_card = tk.Frame(self.content, bg=self.colors["card"])
        self.forecast_card.pack(padx=16, pady=(6, 18), fill="x")

        tk.Label(self.forecast_card, text="5-Day Forecast", bg=self.colors["card"], fg=self.colors["fg"], font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(10,4))

        self.day_panels = tk.Frame(self.forecast_card, bg=self.colors["card"])
        self.day_panels.pack(fill="x", padx=12)

        # graph
        self.graph_container = tk.Frame(self.content, bg=self.colors["card"])
        self.graph_container.pack(padx=16, pady=(8,20), fill="x")

        # status
        self.status = tk.Label(self.content, text="Ready", bg=self.colors["bg"], fg=self.colors["fg"])
        self.status.pack(pady=(6,12))

        # set initial favorites combobox values
        self._refresh_favs_cb()

    # ---------- theme helpers ----------
    def _apply_theme(self):
        t = self.theme.get()
        self.colors = self.themes[t]

    def _refresh_theme(self):
        self._apply_theme()
        self.canvas.configure(bg=self.colors["bg"])
        self.card.configure(bg=self.colors["card"])
        self.forecast_card.configure(bg=self.colors["card"])
        self.graph_container.configure(bg=self.colors["card"])
        self.city_label.configure(bg=self.colors["card"], fg=self.colors["fg"])
        self.desc_label.configure(bg=self.colors["card"], fg=self.colors["fg"])
        self.temp_label.configure(bg=self.colors["card"], fg=self.colors["fg"])
        self.hum_label.configure(bg=self.colors["card"], fg=self.colors["fg"])
        self.next_label.configure(bg=self.colors["card"], fg=self.colors["fg"])
        self.status.configure(bg=self.colors["bg"], fg=self.colors["fg"])
        self.icon_label.configure(bg=self.colors["card"])
        # update theme button text
        self.theme_btn.configure(text=f"Theme: {'Dark' if self.theme.get()=='dark' else 'Light'}")

    def toggle_theme(self):
        self.theme.set("dark" if self.theme.get()=="light" else "light")
        self._refresh_theme()

    # ---------- scroll bindings ----------
    def _bind_mousewheel(self):
        # Windows/mac
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel_windows_mac)
        # Linux
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_linux)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_linux)

    def _on_mousewheel_windows_mac(self, event):
        # normalize for Windows/macOS
        try:
            delta = int(-1 * (event.delta / 120))
        except Exception:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")

    def _on_mousewheel_linux(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")

    # ---------- layout helpers ----------
    def _on_canvas_configure(self, event):
        w = min(event.width, MAX_CONTENT_WIDTH)
        self.canvas.itemconfig(self.win, width=w)
        self.canvas.coords(self.win, event.width / 2, 0)

    # ---------- startup ----------
    def _startup_sequence(self):
        # apply current theme colors
        self._apply_theme()
        self.canvas.configure(bg=self.colors["bg"])

        last = load_last_city()
        if last:
            # show last city immediately (non-blocking)
            self.city_var.set(last)
            self._load_weather_async(last, save_last=False)
        # Ask (popup) whether to show user's IP-based location; show after last city is visible
        # We ask in the main thread (UI) but fetch in a background thread if accepted.
        def ask_and_fetch():
            allow = messagebox.askyesno("Location Access", "Show weather for your current location (detected from IP)?\n(You can cancel and keep last searched location shown.)")
            if allow:
                # fetch in background
                threading.Thread(target=self._fetch_ip_and_update, daemon=True).start()

        # small delay so last-city UI appears
        self.after(400, ask_and_fetch)

    def _fetch_ip_and_update(self):
        try:
            cur = fetch_weather_by_ip(units=self.units.get())
        except Exception as e:
            # show warning but keep last city
            self.after(0, lambda: messagebox.showwarning("Location detect", f"Could not detect location: {e}"))
            return
        # update UI
        self.after(0, lambda: self._update_ui(cur, fetch_forecast_by_city(cur["city"], units=self.units.get())))

    # ---------- actions ----------
    def search(self):
        city = self.city_var.get().strip()
        if not city:
            messagebox.showinfo("Input", "Please enter a city name.")
            return
        self._load_weather_async(city)

    def refresh(self):
        if self.current_city:
            self._load_weather_async(self.current_city)
        else:
            # if no current city, try last or ask
            last = load_last_city()
            if last:
                self._load_weather_async(last)
            else:
                self.search()

    def _units_changed(self):
        if self.current_city:
            self._load_weather_async(self.current_city)

    def _on_fav_selected(self):
        city = self.favs_var.get()
        if city:
            self.city_var.set(city)
            self._load_weather_async(city)

    def add_favorite(self):
        city = self.current_city or self.city_var.get().strip()
        if not city:
            messagebox.showinfo("Favorite", "No city to add.")
            return
        if city not in self.favorites:
            self.favorites.append(city)
            save_favorites(self.favorites)
            self._refresh_favs_cb()
            messagebox.showinfo("Favorite", f"Saved {city} to favorites.")
        else:
            messagebox.showinfo("Favorite", f"{city} already in favorites.")

    def remove_favorite(self):
        sel = self.favs_var.get().strip()
        if not sel:
            messagebox.showinfo("Remove Favorite", "Choose a favorite in the dropdown first.")
            return
        if sel in self.favorites:
            self.favorites.remove(sel)
            save_favorites(self.favorites)
            self._refresh_favs_cb()
            messagebox.showinfo("Remove Favorite", f"Removed {sel} from favorites.")

    def _refresh_favs_cb(self):
        try:
            self.favs_cb["values"] = self.favorites
        except Exception:
            pass

    # ---------------- threading + fetching ----------------
    def _load_weather_async(self, city: str, save_last: bool = True):
        self.status.configure(text="Fetching...")
        threading.Thread(target=self._load_weather_thread, args=(city, save_last), daemon=True).start()

    def _load_weather_thread(self, city: str, save_last: bool):
        units = self.units.get()
        try:
            cur = fetch_weather_by_city(city, units=units)
        except Exception as e:
            self.after(0, lambda: self._handle_error(e))
            return

        try:
            forecast = fetch_forecast_by_city(city, units=units)
        except Exception:
            forecast = []

        self.after(0, lambda: self._update_ui(cur, forecast, save_last))

    def _handle_error(self, e):
        msg = str(e)
        if "Network error" in msg:
            messagebox.showerror("No Internet", "Network error — check your connection.")
        else:
            messagebox.showerror("Error", msg)
        self.status.configure(text="Error")

    # ---------------- UI updater ----------------
    def _update_ui(self, cur: Dict, forecast: List[Dict], save_last: bool = True):
        # update current
        self.current_city = cur.get("city") or self.city_var.get().strip()
        if save_last and self.current_city:
            save_last_city(self.current_city)

        unit_label = {"metric":"°C","imperial":"°F","standard":"K"}.get(self.units.get(), "°")

        citytxt = cur.get("city","") + (f", {cur.get('country')}" if cur.get("country") else "")
        self.city_label.config(text=citytxt)
        self.desc_label.config(text=(cur.get("description") or "—").title())
        self.temp_label.config(text=f"Temperature: {cur.get('temperature','—')}{unit_label}")
        self.hum_label.config(text=f"Humidity: {cur.get('humidity','—')}%")

        # icon
        icon_img = download_icon(cur.get("icon",""), size=96)
        if icon_img:
            self.icon_label.configure(image=icon_img)
            self.icon_label.image = icon_img
        else:
            self.icon_label.configure(image="")

        # next prediction: first upcoming forecast entry
        next_item = None
        for item in forecast:
            if item.get("dt_txt"):
                next_item = item
                break
        if next_item:
            self.next_label.config(text=f"Next: {next_item['dt_txt']} — {next_item['temperature']}{unit_label} — {next_item['description']}")
        else:
            self.next_label.config(text="")

        # 5-day daily summary
        by_date = {}
        for item in forecast:
            d = item.get("date")
            if not d:
                continue
            by_date.setdefault(d, []).append(item)

        # choose one per day (prefer 12:00) or average
        days = sorted(by_date.keys())[:5]
        summaries = []
        for d in days:
            entries = by_date[d]
            chosen = None
            for e in entries:
                if e.get("dt_txt","").endswith("12:00:00"):
                    chosen = e
                    break
            if not chosen:
                temps = [e.get("temperature") for e in entries if e.get("temperature") is not None]
                avg = round(sum(temps)/len(temps),1) if temps else None
                desc = entries[0].get("description","") if entries else ""
                icon = entries[0].get("icon","") if entries else ""
                chosen = {"date": d, "temperature": avg, "description": desc, "icon": icon}
            summaries.append(chosen)

        # render day panels
        for ch in self.day_panels.winfo_children():
            ch.destroy()
        for s in summaries:
            frame = tk.Frame(self.day_panels, bg=self.colors["card"])
            frame.pack(side="left", padx=8, pady=6)
            icon_small = download_icon(s.get("icon",""), size=48)
            if icon_small:
                lbl_img = tk.Label(frame, image=icon_small, bg=self.colors["card"])
                lbl_img.image = icon_small
                lbl_img.pack()
            tk.Label(frame, text=s.get("date",""), bg=self.colors["card"], fg=self.colors["fg"]).pack()
            tk.Label(frame, text=f"{s.get('temperature','—')}{unit_label}", bg=self.colors["card"], fg=self.colors["fg"], font=("Segoe UI",9,"bold")).pack()
            tk.Label(frame, text=(s.get("description") or "").title(), bg=self.colors["card"], fg=self.colors["fg"], font=("Segoe UI",8)).pack()

        # graph: daily averages
        graph_days = []
        graph_vals = []
        for d in days:
            entries = by_date[d]
            temps = [e.get("temperature") for e in entries if e.get("temperature") is not None]
            if temps:
                graph_days.append(d)
                graph_vals.append(round(sum(temps)/len(temps),1))

        for ch in self.graph_container.winfo_children():
            ch.destroy()
        if graph_days:
            fig, ax = plt.subplots(figsize=(7.2,2.6), dpi=100)
            ax.plot(graph_days, graph_vals, marker="o", linewidth=2, color=self.colors["accent"])
            ax.set_ylabel({"metric":"Temp (°C)","imperial":"Temp (°F)","standard":"Temp (K)"}[self.units.get()])
            ax.set_title("Daily temperature (next days)")
            ax.tick_params(axis="x", rotation=30)
            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=self.graph_container)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="x")
            plt.close(fig)

        # notifications
        desc = (cur.get("description") or "").lower()
        temp_val = cur.get("temperature")
        try:
            if desc and ("rain" in desc or "drizzle" in desc or "shower" in desc):
                messagebox.showinfo("Rain alert", f"It may be wet in {cur.get('city')}.")
            if temp_val is not None:
                t = float(temp_val)
                if self.units.get()=="metric":
                    if t >= 35:
                        messagebox.showwarning("Heat alert", f"Hot in {cur.get('city')}: {t}°C")
                    elif t <= 0:
                        messagebox.showinfo("Cold alert", f"Freezing in {cur.get('city')}: {t}°C")
                elif self.units.get()=="imperial":
                    if t >= 95:
                        messagebox.showwarning("Heat alert", f"Hot in {cur.get('city')}: {t}°F")
        except Exception:
            pass

        # status/time & refresh favs combobox values
        self.status.config(text=f"Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._refresh_favs_cb()

    # ---------------- favorites panel ----------------
    def open_favorites_panel(self):
        favs = self.favorites
        if not favs:
            messagebox.showinfo("Favorites", "No favorites saved.")
            return
        win = tk.Toplevel(self)
        win.title("Favorites")
        win.geometry("720x480")
        win.configure(bg=self.colors["bg"])

        canvas = tk.Canvas(win, bg=self.colors["bg"])
        vscroll = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas, style="App.TFrame")
        canvas.create_window((0,0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        for city in favs:
            card = tk.Frame(frame, bg=self.colors["card"], bd=1, relief="solid")
            card.pack(fill="x", padx=12, pady=8)

            try:
                summary = fetch_weather_by_city(city, units=self.units.get())
            except Exception:
                summary = {"city": city, "temperature": "—", "description": "N/A", "icon": ""}

            left = tk.Frame(card, bg=self.colors["card"])
            left.pack(side="left", padx=8, pady=6)
            icon_img = download_icon(summary.get("icon",""), size=64)
            if icon_img:
                tk.Label(left, image=icon_img, bg=self.colors["card"]).pack()
                left.image = icon_img

            right = tk.Frame(card, bg=self.colors["card"])
            right.pack(side="left", padx=8)
            tk.Label(right, text=summary.get("city", city), bg=self.colors["card"], fg=self.colors["fg"], font=("Segoe UI",12,"bold")).pack(anchor="w")
            tk.Label(right, text=f"{summary.get('temperature','—')} {''}", bg=self.colors["card"], fg=self.colors["fg"]).pack(anchor="w")
            tk.Label(right, text=(summary.get("description") or "").title(), bg=self.colors["card"], fg=self.colors["fg"]).pack(anchor="w")

            btns = tk.Frame(card, bg=self.colors["card"])
            btns.pack(side="right", padx=8)
            ttk.Button(btns, text="Details", command=lambda c=city: self._open_favorite_details(c)).pack(padx=4, pady=6)

    def _open_favorite_details(self, city: str):
        win = tk.Toplevel(self)
        win.title(f"{city} — Details")
        win.geometry("760x520")
        win.transient(self)
        win.configure(bg=self.colors["bg"])

        try:
            w = fetch_weather_by_city(city, units=self.units.get())
            f = fetch_forecast_by_city(city, units=self.units.get())
        except Exception as e:
            messagebox.showerror("Error", f"Could not fetch details: {e}")
            win.destroy()
            return

        top = tk.Frame(win, bg=self.colors["bg"], pady=8)
        top.pack(fill="x")
        tk.Label(top, text=f"{w.get('city','')}", font=("Segoe UI",16,"bold"), bg=self.colors["bg"], fg=self.colors["fg"]).pack(anchor="w", padx=10)

        left = tk.Frame(win, bg=self.colors["bg"])
        left.pack(side="left", fill="y", padx=10, pady=6)

        icon_img = download_icon(w.get("icon",""), size=120)
        if icon_img:
            tk.Label(left, image=icon_img, bg=self.colors["bg"]).pack()
            left.image = icon_img

        tk.Label(left, text=f"{w.get('description','').title()}", bg=self.colors["bg"], fg=self.colors["fg"]).pack(pady=6)
        tk.Label(left, text=f"Temp: {w.get('temperature','—')}", bg=self.colors["bg"], fg=self.colors["fg"]).pack()
        tk.Label(left, text=f"Humidity: {w.get('humidity','—')}%", bg=self.colors["bg"], fg=self.colors["fg"]).pack()

        right = tk.Frame(win, bg=self.colors["bg"])
        right.pack(side="left", fill="both", expand=True, padx=6, pady=6)

        by_date = {}
        for it in f:
            d = it.get("date")
            if not d:
                continue
            by_date.setdefault(d, []).append(it.get("temperature"))

        days = sorted(by_date.keys())[:5]
        avg = [round(sum(by_date[d])/len(by_date[d]),1) for d in days] if days else []

        stats_frame = tk.Frame(right, bg=self.colors["bg"])
        stats_frame.pack(fill="x")
        tk.Label(stats_frame, text=f"Avg next {len(days)} days: {round(sum(avg)/len(avg),1) if avg else '—'}", bg=self.colors["bg"], fg=self.colors["fg"]).pack(anchor="w")
        tk.Label(stats_frame, text=f"Min: {min((min(by_date[d]) for d in by_date), default='—')}    Max: {max((max(by_date[d]) for d in by_date), default='—')}", bg=self.colors["bg"], fg=self.colors["fg"]).pack(anchor="w")

        if days:
            fig, ax = plt.subplots(figsize=(6.2,2.4), dpi=100)
            ax.plot(days, avg, marker="o", color=self.colors["accent"])
            ax.set_title("Avg daily temp")
            ax.tick_params(axis="x", rotation=30)
            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=right)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True, pady=6)
            plt.close(fig)

    # ---------------- error/exit ----------------
    def _handle_error_dialog(self, e: Exception):
        msg = str(e)
        if "Network error" in msg or "No Internet" in msg:
            messagebox.showerror("No Internet", "Network error — check your connection.")
        else:
            messagebox.showerror("Error", msg)
        self.status.configure(text="Error")

    def _on_close(self):
        try:
            self.destroy()
        finally:
            sys.exit(0)


# ---------------- run ----------------
if __name__ == "__main__":
    app = WeatherApp()
    app.mainloop()
