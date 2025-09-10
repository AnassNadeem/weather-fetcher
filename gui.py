#!/usr/bin/env python3
"""
Final GUI: polished Weather app with:
- last-searched persistence
- favorites (mini-cards + details modal)
- auto-detect IP (with permission)
- units dropdown
- theme (Light / Dark)
- refresh, notifications, icons, 5-day forecast + graph + next prediction
- scrollable & centered layout + mousepad scrolling
- threaded network calls to keep UI responsive
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

from weather_fetcher import (
    fetch_weather_by_city,
    fetch_forecast_by_city,
    fetch_weather_by_ip,
    detect_city_via_ip,
)

# ---------------- config / persistence ----------------
ICONS_DIR = "icons"
os.makedirs(ICONS_DIR, exist_ok=True)
LAST_CITY_FILE = "last_city.json"
FAV_FILE = "favorites.json"
MAX_WIDTH = 900

# ---------------- utilities ----------------
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

def download_icon(icon_code: str, size: int = 80) -> Optional[ImageTk.PhotoImage]:
    """Download and cache OpenWeather icons; return PhotoImage or None."""
    if not icon_code:
        return None
    path = os.path.join(ICONS_DIR, f"{icon_code}@2x.png")
    if not os.path.exists(path):
        try:
            url = f"https://openweathermap.org/img/wn/{icon_code}@2x.png"
            import requests
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

# ---------------- main app ----------------
class WeatherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Weather App — Final")
        self.geometry("980x720")
        self.minsize(820, 600)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # state
        self.units = tk.StringVar(value="metric")
        self.theme = tk.StringVar(value="light")
        self.current_city: Optional[str] = None
        self.favorites: List[str] = load_favorites()

        # theme colors
        self._themes = {
            "light": {"bg": "#EAF4FC", "card": "#FFFFFF", "fg": "#111827", "header": "#3A83F1"},
            "dark": {"bg": "#111827", "card": "#1f2937", "fg": "#e6eef8", "header": "#2563EB"},
        }

        # build UI
        self._build_ui()
        # ensure responsive centering
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # mousepad / trackpad scroll bindings
        self._bind_mousewheel()

        # load last city or ask permission for location
        self.after(200, self._startup_load)

    # ---------------- UI build ----------------
    def _build_ui(self):
        self._apply_theme()

        outer = ttk.Frame(self, style="App.TFrame")
        outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(outer, bg=self._colors["bg"], highlightthickness=0)
        self.vscroll = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vscroll.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vscroll.pack(side="right", fill="y")

        # content frame inside canvas (we center this)
        self.content = ttk.Frame(self.canvas, style="App.TFrame")
        self.win = self.canvas.create_window(0, 0, window=self.content, anchor="n")

        # header
        header = tk.Frame(self.content, bg=self._colors["header"])
        header.pack(fill="x")
        tk.Label(header, text="Weather App", bg=self._colors["header"], fg="white",
                 font=("Segoe UI", 18, "bold"), pady=10).pack()

        # controls row
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
        self.units_cb = ttk.Combobox(controls, textvariable=self.units, values=["metric","imperial","standard"], width=10, state="readonly")
        self.units_cb.grid(row=0, column=4, padx=4)
        self.units_cb.bind("<<ComboboxSelected>>", lambda e: self._on_units_change())

        # favorites row (dropdown removed, just add/remove/show buttons)
        self.add_fav_btn = ttk.Button(controls, text="Add Favorite", command=self.add_favorite)
        self.add_fav_btn.grid(row=1, column=1, padx=4, pady=(8,0))

        # remove favorite button (disabled until a favorite is applicable)
        self.remove_fav_btn = ttk.Button(controls, text="Remove Favorite", command=self.remove_favorite, state="disabled")
        self.remove_fav_btn.grid(row=1, column=2, padx=4, pady=(8,0))

        self.show_favs_btn = ttk.Button(controls, text="Show Favorites", command=self.open_favorites_panel)
        self.show_favs_btn.grid(row=1, column=3, padx=4, pady=(8,0))

        # Theme toggle
        self.theme_btn = ttk.Button(controls, text="Theme: Light", command=self.toggle_theme)
        self.theme_btn.grid(row=0, column=5, padx=12)

        # current weather card
        self.card = tk.Frame(self.content, bg=self._colors["card"], bd=0)
        self.card.pack(padx=16, pady=12, fill="x")

        self.city_label = tk.Label(self.card, text="—", font=("Segoe UI", 16, "bold"), bg=self._colors["card"], fg=self._colors["fg"])
        self.city_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10,6))

        self.icon_label = tk.Label(self.card, bg=self._colors["card"])
        self.icon_label.grid(row=1, column=0, rowspan=3, padx=12, pady=8)

        self.desc_label = tk.Label(self.card, text="—", bg=self._colors["card"], fg=self._colors["fg"], font=("Segoe UI", 12))
        self.desc_label.grid(row=1, column=1, sticky="w")

        self.temp_label = tk.Label(self.card, text="Temperature: —", bg=self._colors["card"], fg=self._colors["fg"], font=("Segoe UI", 12))
        self.temp_label.grid(row=2, column=1, sticky="w", pady=2)

        self.hum_label = tk.Label(self.card, text="Humidity: —", bg=self._colors["card"], fg=self._colors["fg"], font=("Segoe UI", 12))
        self.hum_label.grid(row=3, column=1, sticky="w")

        # next prediction label
        self.next_label = tk.Label(self.card, text="", bg=self._colors["card"], fg=self._colors["fg"], font=("Segoe UI", 10))
        self.next_label.grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(6,12))

        # forecast & graph
        self.forecast_frame = tk.Frame(self.content, bg=self._colors["card"])
        self.forecast_frame.pack(padx=16, pady=(0,12), fill="x")

        tk.Label(self.forecast_frame, text="5-day forecast", bg=self._colors["card"], fg=self._colors["fg"], font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=12, pady=(8,4))

        self.day_panels = tk.Frame(self.forecast_frame, bg=self._colors["card"])
        self.day_panels.pack(fill="x", padx=12)

        # graph container
        self.graph_container = tk.Frame(self.content, bg=self._colors["card"])
        self.graph_container.pack(padx=16, pady=(8,20), fill="x")

        # status bar
        self.status = tk.Label(self.content, text="Ready", bg=self._colors["bg"], fg=self._colors["fg"], font=("Segoe UI", 10))
        self.status.pack(pady=(6,14))

    # ---------------- theme ----------------
    @property
    def _colors(self):
        return self._themes[self.theme.get()]

    def _apply_theme(self):
        # configure ttk styles
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("App.TFrame", background=self._themes[self.theme.get()]["bg"])
        self.configure(bg=self._themes[self.theme.get()]["bg"])

    def toggle_theme(self):
        self.theme.set("dark" if self.theme.get() == "light" else "light")
        self._apply_theme()
        self._refresh_colors()
        self.theme_btn.configure(text=f"Theme: {'Dark' if self.theme.get()=='dark' else 'Light'}")

    def _refresh_colors(self):
        cols = self._colors
        self.canvas.configure(bg=cols["bg"])
        self.card.configure(bg=cols["card"])
        self.city_label.configure(bg=cols["card"], fg=cols["fg"])
        self.desc_label.configure(bg=cols["card"], fg=cols["fg"])
        self.temp_label.configure(bg=cols["card"], fg=cols["fg"])
        self.hum_label.configure(bg=cols["card"], fg=cols["fg"])
        self.forecast_frame.configure(bg=cols["card"])
        self.day_panels.configure(bg=cols["card"])
        self.graph_container.configure(bg=cols["card"])
        self.status.configure(bg=cols["bg"], fg=cols["fg"])
        self.icon_label.configure(bg=cols["card"])

        # update remove/add favorite button state
        try:
            if self.current_city and self.current_city in self.favorites:
                self.remove_fav_btn.config(state="normal")
            else:
                self.remove_fav_btn.config(state="disabled")
        except Exception:
            pass

    # ---------------- scrolling helpers ----------------
    def _bind_mousewheel(self):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel_windows_mac)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_linux)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_linux)

    def _on_mousewheel_windows_mac(self, event):
        delta = int(-1 * (event.delta/120))
        self.canvas.yview_scroll(delta, "units")

    def _on_mousewheel_linux(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")

    def _on_canvas_configure(self, event):
        # center content and constrain width
        canvas_width = event.width
        width = min(canvas_width, MAX_WIDTH)
        self.canvas.itemconfig(self.win, width=width)
        self.canvas.coords(self.win, canvas_width/2, 0)

    # ---------------- startup ----------------
    def _startup_load(self):
        # try last city first
        last = load_last_city()
        if last:
            self.city_var.set(last)
            self._load_weather_async(last)
            return
        # else ask permission for IP detection
        allow = messagebox.askyesno("Location", "Allow detecting your city from your IP?")
        if allow:
            try:
                city = detect_city_via_ip()
                if city:
                    self.city_var.set(city)
                    self._load_weather_async(city)
                else:
                    self.status.configure(text="Location detection failed")
            except Exception as e:
                self.status.configure(text=f"Location error: {e}")

    # ---------------- actions ----------------
    def search(self):
        city = self.city_var.get().strip()
        if not city:
            messagebox.showinfo("Input", "Please enter a city.")
            return
        self._load_weather_async(city)

    def refresh(self):
        if self.current_city:
            self._load_weather_async(self.current_city)
        else:
            self.search()

    def _on_units_change(self):
        if self.current_city:
            self._load_weather_async(self.current_city)

    def add_favorite(self):
        if self.current_city and self.current_city not in self.favorites:
            self.favorites.append(self.current_city)
            save_favorites(self.favorites)
            messagebox.showinfo("Favorites", f"Saved {self.current_city}")
            self._refresh_colors()

    def remove_favorite(self):
        if self.current_city and self.current_city in self.favorites:
            self.favorites.remove(self.current_city)
            save_favorites(self.favorites)
            messagebox.showinfo("Favorites", f"Removed {self.current_city}")
            self._refresh_colors()
        else:
            messagebox.showinfo("Favorites", "City not in favorites.")

    # ---------------- threaded loader ----------------
    def _load_weather_async(self, city: str):
        """Start thread to fetch current + forecast; update UI on main thread."""
        self.status.configure(text="Fetching...")
        thread = threading.Thread(target=self._load_weather_thread, args=(city,), daemon=True)
        thread.start()

    def _load_weather_thread(self, city: str):
        units = self.units.get()
        try:
            cur = fetch_weather_by_city(city, units=units)
        except Exception as e:
            self.after(0, lambda: self._show_error(e))
            return

        try:
            forecast = fetch_forecast_by_city(city, units=units)
        except Exception:
            forecast = []

        # schedule UI update on main thread
        self.after(0, lambda: self._update_ui(cur, forecast))

    def _show_error(self, e):
        msg = str(e)
        if "Network error" in msg or "No Internet" in msg:
            messagebox.showerror("No Internet", "Network error — check your connection.")
        else:
            messagebox.showerror("Error", msg)
        self.status.configure(text="Error")

    # ---------------- UI updater ----------------
    def _update_ui(self, cur: Dict, forecast: List[Dict]):
        # update current
        self.current_city = cur.get("city") or self.city_var.get()
        save_last_city(self.current_city)
        unit_label = {"metric":"°C","imperial":"°F","standard":"K"}.get(self.units.get(), "°")

        citytext = f"{cur.get('city','')}" + (f", {cur.get('country','')}" if cur.get("country") else "")
        self.city_label.config(text=citytext)
        self.desc_label.config(text=(cur.get("description") or "—").title())
        self.temp_label.config(text=f"Temperature: {cur.get('temperature','—')}{unit_label}")
        self.hum_label.config(text=f"Humidity: {cur.get('humidity','—')}%")

        # icon
        img = download_icon(cur.get("icon",""), size=80)
        if img:
            self.icon_label.config(image=img)
            self.icon_label.image = img
        else:
            self.icon_label.config(image="")

        # next prediction (first upcoming forecast)
        next_pred = None
        for it in forecast:
            if it.get("dt_txt"):
                next_pred = it
                break
        if next_pred:
            self.next_label.config(text=f"Next: {next_pred['dt_txt']} — {next_pred['temperature']}{unit_label} — {next_pred['description']}")
        else:
            self.next_label.config(text="")

        # forecast daily summary: pick 12:00 entries or compute avg per day
        by_date = {}
        for it in forecast:
            d = it.get("date")
            if not d:
                continue
            if d not in by_date:
                by_date[d] = []
            by_date[d].append(it)

        # prepare 5-day summary
        days = sorted(by_date.keys())[:5]
        summaries = []
        for d in days:
            entries = by_date[d]
            # prefer entry that endswith 12:00:00, else average
            chosen = None
            for e in entries:
                if e.get("dt_txt","").endswith("12:00:00"):
                    chosen = e
                    break
            if not chosen:
                # average temperature
                temps = [e.get("temperature") for e in entries if e.get("temperature") is not None]
                avg = sum(temps)/len(temps) if temps else None
                desc = entries[0].get("description","") if entries else ""
                icon = entries[0].get("icon","") if entries else ""
                chosen = {"date": d, "temperature": round(avg,1) if avg is not None else None, "description": desc, "icon": icon}
            summaries.append(chosen)

        # render day panels
        for ch in self.day_panels.winfo_children():
            ch.destroy()
        for s in summaries:
            frame = tk.Frame(self.day_panels, bg=self._colors["card"], bd=0)
            frame.pack(side="left", padx=8, pady=6)
            icon_img = download_icon(s.get("icon",""), size=48)
            if icon_img:
                lbl_img = tk.Label(frame, image=icon_img, bg=self._colors["card"])
                lbl_img.image = icon_img
                lbl_img.pack()
            tk.Label(frame, text=s.get("date",""), bg=self._colors["card"], fg=self._colors["fg"]).pack()
            tk.Label(frame, text=f"{s.get('temperature','—')}{unit_label}", bg=self._colors["card"], fg=self._colors["fg"], font=("Segoe UI",10,"bold")).pack()
            tk.Label(frame, text=(s.get("description") or "").title(), bg=self._colors["card"], fg=self._colors["fg"], font=("Segoe UI",9)).pack()

        # graph: plot daily averages
        graph_days = []
        graph_temps = []
        for d in days:
            entries = by_date[d]
            temps = [e.get("temperature") for e in entries if e.get("temperature") is not None]
            if temps:
                graph_days.append(d)
                graph_temps.append(round(sum(temps)/len(temps),1))

        for ch in self.graph_container.winfo_children():
            ch.destroy()
        if graph_days:
            fig, ax = plt.subplots(figsize=(7.2,2.6), dpi=100)
            ax.plot(graph_days, graph_temps, marker="o", color="#3A83F1")
            ax.set_ylabel({"metric":"Temp (°C)","imperial":"Temp (°F)","standard":"Temp (K)"}[self.units.get()])
            ax.set_title("Daily temperature (next days)")
            ax.tick_params(axis="x", rotation=30)
            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=self.graph_container)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="x")
            plt.close(fig)

        # update status/time
        self.status.config(text=f"Last updated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        # refresh remove-fav button state (replaces old combobox refresh)
        self._refresh_favs_cb()

        # notifications for rain/heat/cold
        desc = (cur.get("description") or "").lower()
        temp_val = cur.get("temperature")
        try:
            if desc and ("rain" in desc or "drizzle" in desc or "shower" in desc):
                messagebox.showinfo("Rain alert", f"It's wet in {cur.get('city')}. Consider umbrella.")
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

    # ---------------- favorites panel & details ----------------
    def _refresh_favs_cb(self):
        # combobox removed — update remove button state instead
        try:
            if self.current_city and self.current_city in self.favorites:
                self.remove_fav_btn.config(state="normal")
            else:
                self.remove_fav_btn.config(state="disabled")
        except Exception:
            pass

    def add_favorite(self):
        # kept earlier but redefining here ensures any call works
        if self.current_city and self.current_city not in self.favorites:
            self.favorites.append(self.current_city)
            save_favorites(self.favorites)
            messagebox.showinfo("Favorites", f"Added {self.current_city}")
            self._refresh_favs_cb()

    def open_favorites_panel(self):
        favs = self.favorites
        if not favs:
            messagebox.showinfo("Favorites", "No favorites yet.")
            return
        win = tk.Toplevel(self)
        win.title("Favorites")
        win.geometry("720x480")
        win.configure(bg=self._colors["bg"])

        # scroll area inside panel
        canvas = tk.Canvas(win, bg=self._colors["bg"], highlightthickness=0)
        v = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        frame = ttk.Frame(canvas)
        canvas.create_window((0,0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=v.set)
        canvas.pack(side="left", fill="both", expand=True)
        v.pack(side="right", fill="y")
        frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # create mini cards
        for city in favs:
            card = tk.Frame(frame, bg=self._colors["card"], bd=1, relief="solid")
            card.pack(fill="x", padx=12, pady=8)

            # fetch summary (synchronously here, small number expected)
            try:
                summary = fetch_weather_by_city(city, units=self.units.get())
            except Exception:
                summary = {"city": city, "temperature": "—", "description": "N/A", "icon": ""}

            left = tk.Frame(card, bg=self._colors["card"])
            left.pack(side="left", padx=8, pady=6)
            icon_img = download_icon(summary.get("icon",""), size=64)
            if icon_img:
                lbl = tk.Label(left, image=icon_img, bg=self._colors["card"])
                lbl.image = icon_img
                lbl.pack()

            right = tk.Frame(card, bg=self._colors["card"])
            right.pack(side="left", padx=8)
            tk.Label(right, text=summary.get("city", city), bg=self._colors["card"], fg=self._colors["fg"], font=("Segoe UI",12,"bold")).pack(anchor="w")
            tk.Label(right, text=f"{summary.get('temperature','—')}{' '}", bg=self._colors["card"], fg=self._colors["fg"]).pack(anchor="w")
            tk.Label(right, text=(summary.get("description") or "").title(), bg=self._colors["card"], fg=self._colors["fg"]).pack(anchor="w")

            btns = tk.Frame(card, bg=self._colors["card"])
            btns.pack(side="right", padx=8)
            ttk.Button(btns, text="Details", command=lambda c=city: self._open_favorite_details(c)).pack(padx=4, pady=6)

    def _open_favorite_details(self, city: str):
        win = tk.Toplevel(self)
        win.title(f"{city} — Details")
        win.geometry("760x520")
        win.transient(self)
        win.configure(bg=self._colors["bg"])

        try:
            w = fetch_weather_by_city(city, units=self.units.get())
            f = fetch_forecast_by_city(city, units=self.units.get())
        except Exception as e:
            messagebox.showerror("Error", f"Could not fetch details: {e}")
            win.destroy()
            return

        top = tk.Frame(win, bg=self._colors["bg"], pady=8)
        top.pack(fill="x")
        tk.Label(top, text=f"{w.get('city','')}, {w.get('country','')}", font=("Segoe UI",16,"bold"), bg=self._colors["bg"], fg=self._colors["fg"]).pack(anchor="w", padx=10)

        # left summary
        left = tk.Frame(win, bg=self._colors["bg"])
        left.pack(side="left", fill="y", padx=10, pady=6)
        icon_img = download_icon(w.get("icon",""), size=120)
        if icon_img:
            tk.Label(left, image=icon_img, bg=self._colors["bg"]).pack()
            left.image = icon_img
        tk.Label(left, text=f"{w.get('description','').title()}", bg=self._colors["bg"], fg=self._colors["fg"]).pack(pady=6)
        tk.Label(left, text=f"Temp: {w.get('temperature','—')}", bg=self._colors["bg"], fg=self._colors["fg"]).pack()
        tk.Label(left, text=f"Humidity: {w.get('humidity','—')}%", bg=self._colors["bg"], fg=self._colors["fg"]).pack()

        # right graph / stats
        right = tk.Frame(win, bg=self._colors["bg"])
        right.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        # group by date for averages
        by_date = {}
        for it in f:
            d = it.get("date")
            if not d:
                continue
            by_date.setdefault(d, []).append(it.get("temperature"))
        days = sorted(by_date.keys())[:5]
        avg = [round(sum(by_date[d])/len(by_date[d]),1) for d in days] if days else []

        stats = tk.Frame(right, bg=self._colors["bg"])
        stats.pack(fill="x")
        tk.Label(stats, text=f"Avg next {len(days)} days: {round(sum(avg)/len(avg),1) if avg else '—'}", bg=self._colors["bg"], fg=self._colors["fg"]).pack(anchor="w")
        tk.Label(stats, text=f"Min: {min((min(by_date[d]) for d in by_date), default='—')}    Max: {max((max(by_date[d]) for d in by_date), default='—')}", bg=self._colors["bg"], fg=self._colors["fg"]).pack(anchor="w")

        if days:
            fig, ax = plt.subplots(figsize=(6.2,2.4), dpi=100)
            ax.plot(days, avg, marker="o", color="#3A83F1")
            ax.set_title("Avg daily temp")
            ax.tick_params(axis="x", rotation=30)
            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=right)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True, pady=6)
            plt.close(fig)

    # ---------------- exit ----------------
    def _on_close(self):
        try:
            self.destroy()
        finally:
            sys.exit(0)


# ---------------- run ----------------
if __name__ == "__main__":
    app = WeatherApp()
    app.mainloop()
