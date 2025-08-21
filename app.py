import os
import io
import requests
import datetime as dt

# GUI + images
import customtkinter as ctk
from PIL import Image

# Charts
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# .env loader (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ---------- Config ----------
API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
BASE_URL = "https://api.openweathermap.org/data/2.5"
ICON_URL = "https://openweathermap.org/img/wn/{code}@2x.png"

DEFAULT_CITY = "Mumbai"
DEFAULT_UNITS = "metric"  # "metric" for °C, "imperial" for °F


def temp_to_bg(temp_c: float) -> str:
    """
    Map temperature to a pleasant background color.
    """
    if temp_c is None:
        return "#2b2b2b"
    if temp_c <= 0:
        return "#74b9ff"
    if temp_c <= 15:
        return "#a29bfe"
    if temp_c <= 25:
        return "#55efc4"
    if temp_c <= 35:
        return "#ffeaa7"
    return "#ff7675"


def kph_from_ms(ms):
    return round(ms * 3.6, 1)


def mph_from_ms(ms):
    return round(ms * 2.23694, 1)


class WeatherApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Window basics ---
        self.title("Weather Dashboard")
        self.geometry("860x560")
        self.minsize(820, 520)
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # --- State ---
        self.units = DEFAULT_UNITS  # "metric" or "imperial"
        self.city = DEFAULT_CITY
        self.current_temp_c = None

        # --- Layout: 3 rows (header / content / chart) ---
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header / controls
        self.header = ctk.CTkFrame(self, corner_radius=16)
        self.header.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        self.header.grid_columnconfigure(1, weight=1)

        self.title_label = ctk.CTkLabel(
            self.header,
            text="🌤️ Weather Dashboard",
            font=("Segoe UI", 22, "bold"),
        )
        self.title_label.grid(row=0, column=0, padx=12, pady=10, sticky="w")

        # Search box
        self.city_entry = ctk.CTkEntry(
            self.header, placeholder_text="Enter city (e.g., Mumbai, London, Tokyo)",
            width=340
        )
        self.city_entry.grid(row=0, column=1, padx=6, pady=10, sticky="ew")
        self.city_entry.insert(0, self.city)

        self.search_btn = ctk.CTkButton(self.header, text="Search", command=self.on_search, width=90)
        self.search_btn.grid(row=0, column=2, padx=6, pady=10)

        # Unit toggle
        self.unit_switch_var = ctk.StringVar(value="°C")
        self.unit_switch = ctk.CTkSegmentedButton(
            self.header,
            values=["°C", "°F"],
            command=self.on_units_change,
            variable=self.unit_switch_var
        )
        self.unit_switch.grid(row=0, column=3, padx=6, pady=10)

        # Theme toggle
        self.theme_switch_var = ctk.StringVar(value="System")
        self.theme_switch = ctk.CTkSegmentedButton(
            self.header,
            values=["Light", "Dark", "System"],
            command=self.on_theme_change,
            variable=self.theme_switch_var
        )
        self.theme_switch.grid(row=0, column=4, padx=(6, 12), pady=10)

        # --- Content (current weather card) ---
        self.content = ctk.CTkFrame(self, corner_radius=16)
        self.content.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        for i in range(3):
            self.content.grid_columnconfigure(i, weight=1)
        self.content.grid_rowconfigure(1, weight=1)

        # Left: big temp + icon
        self.left_card = ctk.CTkFrame(self.content, corner_radius=16)
        self.left_card.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=12, pady=12)
        self.left_card.grid_rowconfigure(2, weight=1)
        self.icon_label = ctk.CTkLabel(self.left_card, text="")
        self.icon_label.grid(row=0, column=0, padx=12, pady=(14, 4))
        self.temp_label = ctk.CTkLabel(self.left_card, text="--°", font=("Segoe UI", 48, "bold"))
        self.temp_label.grid(row=1, column=0, padx=12, pady=4)
        self.desc_label = ctk.CTkLabel(self.left_card, text="—", font=("Segoe UI", 16))
        self.desc_label.grid(row=2, column=0, padx=12, pady=(0, 14), sticky="n")

        # Middle: details grid
        self.mid_card = ctk.CTkFrame(self.content, corner_radius=16)
        self.mid_card.grid(row=0, column=1, sticky="nsew", padx=12, pady=12)
        self.mid_card.grid_columnconfigure(1, weight=1)

        self.city_label = ctk.CTkLabel(self.mid_card, text="City: —", font=("Segoe UI", 18, "bold"))
        self.city_label.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 6))

        self.feels_label = ctk.CTkLabel(self.mid_card, text="Feels like: —")
        self.humid_label = ctk.CTkLabel(self.mid_card, text="Humidity: —")
        self.wind_label = ctk.CTkLabel(self.mid_card, text="Wind: —")
        self.press_label = ctk.CTkLabel(self.mid_card, text="Pressure: —")
        self.range_label = ctk.CTkLabel(self.mid_card, text="Min/Max: —")

        for i, w in enumerate([self.feels_label, self.humid_label, self.wind_label, self.press_label, self.range_label], start=1):
            w.grid(row=i, column=0, sticky="w", padx=12, pady=4)

        # Right: status / errors
        self.right_card = ctk.CTkFrame(self.content, corner_radius=16)
        self.right_card.grid(row=0, column=2, sticky="nsew", padx=12, pady=12)
        self.status_label = ctk.CTkLabel(self.right_card, text="", wraplength=240)
        self.status_label.pack(padx=12, pady=12)

        # --- Chart area (forecast) ---
        self.chart_frame = ctk.CTkFrame(self, corner_radius=16)
        self.chart_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(6, 12))
        self.chart_frame.grid_columnconfigure(0, weight=1)
        self.chart_frame.grid_rowconfigure(0, weight=1)

        self.figure = Figure(figsize=(7.4, 2.6), dpi=100)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("Next 24h temperature", fontsize=11)
        self.ax.set_xlabel("Time")
        self.ax.set_ylabel("Temp")
        self.ax.grid(True, alpha=0.3)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self.chart_frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # Load initial city
        self.fetch_and_render(self.city)

    # ---------- UI callbacks ----------
    def on_search(self):
        city = self.city_entry.get().strip()
        if not city:
            self.set_status("Enter a city name.")
            return
        self.fetch_and_render(city)

    def on_units_change(self, value):
        self.units = "metric" if value == "°C" else "imperial"
        self.fetch_and_render(self.city)

    def on_theme_change(self, value):
        ctk.set_appearance_mode(value)

    # ---------- Render helpers ----------
    def set_status(self, msg: str):
        self.status_label.configure(text=msg)

    def set_bg_by_temp(self):
        if self.current_temp_c is None:
            return
        bg = temp_to_bg(self.current_temp_c)
        self.content.configure(fg_color=bg)

    def set_icon(self, icon_code: str):
        if not icon_code:
            self.icon_label.configure(text="(no icon)")
            return
        try:
            url = ICON_URL.format(code=icon_code)
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(100, 100))
            self.icon_label.configure(image=ctk_img, text="")
            self.icon_label.image = ctk_img
        except Exception:
            self.icon_label.configure(text="(icon failed)")

    # ---------- Networking ----------
    def fetch_current(self, city: str):
        params = {"q": city, "appid": API_KEY, "units": self.units}
        r = requests.get(f"{BASE_URL}/weather", params=params, timeout=12)
        r.raise_for_status()
        return r.json()

    def fetch_forecast(self, city: str):
        params = {"q": city, "appid": API_KEY, "units": self.units, "cnt": 10}
        r = requests.get(f"{BASE_URL}/forecast", params=params, timeout=12)
        r.raise_for_status()
        return r.json()

    def fetch_and_render(self, city: str):
        if not API_KEY:
            self.set_status("Set OPENWEATHER_API_KEY as environment variable or .env")
            return

        try:
            self.set_status("Fetching weather…")
            current = self.fetch_current(city)
            forecast = self.fetch_forecast(city)
        except Exception as e:
            self.set_status(f"Error: {e}")
            return

        # --- Render current ---
        try:
            name = f"{current.get('name','')} {current['sys'].get('country','')}".strip()
            weather = current["weather"][0]
            main = current["main"]
            wind = current.get("wind", {})

            temp = main.get("temp")
            feels = main.get("feels_like")
            tmin = main.get("temp_min")
            tmax = main.get("temp_max")
            humid = main.get("humidity")
            press = main.get("pressure")
            icon_code = weather.get("icon")
            desc = weather.get("description", "").title()

            # Convert to °C for background
            if self.units == "metric":
                temp_c = temp
            else:
                temp_c = (temp - 32) * 5 / 9 if temp is not None else None
            self.current_temp_c = temp_c

            deg_symbol = "°C" if self.units == "metric" else "°F"
            self.temp_label.configure(text=f"{round(temp)}{deg_symbol}" if temp is not None else "--°")
            self.desc_label.configure(text=desc or "—")
            self.city_label.configure(text=f"City: {name or city}")
            self.feels_label.configure(text=f"Feels like: {round(feels)}{deg_symbol}" if feels is not None else "Feels like: —")
            self.humid_label.configure(text=f"Humidity: {humid}%" if humid is not None else "Humidity: —")
            wind_str = f"{kph_from_ms(wind.get('speed', 0))} km/h" if self.units == "metric" else f"{mph_from_ms(wind.get('speed', 0))} mph"
            self.wind_label.configure(text=f"Wind: {wind_str}")
            self.press_label.configure(text=f"Pressure: {press} hPa" if press is not None else "Pressure: —")
            if tmin is not None and tmax is not None:
                self.range_label.configure(text=f"Min/Max: {round(tmin)}/{round(tmax)}{deg_symbol}")
            else:
                self.range_label.configure(text="Min/Max: —")

            self.set_icon(icon_code)
            self.set_bg_by_temp()
            self.city = city
        except Exception as e:
            self.set_status(f"Render error: {e}")
            return

        # --- Render forecast chart ---
        try:
            times = []
            temps = []
            for item in forecast.get("list", []):
                ts = item.get("dt")
                t = item.get("main", {}).get("temp")
                if ts is None or t is None:
                    continue
                times.append(dt.datetime.fromtimestamp(ts).strftime("%H:%M"))
                temps.append(t)

            self.ax.clear()
            self.ax.set_title("Next 30h temperature", fontsize=11)
            self.ax.set_xlabel("Time")
            self.ax.set_ylabel("Temp (" + ("°C" if self.units == "metric" else "°F") + ")")
            self.ax.grid(True, alpha=0.3)
            if times and temps:
                self.ax.plot(times, temps, marker="o")
            self.canvas.draw()
            self.set_status("Updated ✓")
        except Exception as e:
            self.set_status(f"Chart error: {e}")


if __name__ == "__main__":
    app = WeatherApp()
    app.mainloop()
