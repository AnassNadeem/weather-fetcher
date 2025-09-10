#!/usr/bin/env python3
"""
weather_fetcher.py

Safe, normalized helpers for OpenWeather:
 - fetch_weather_by_city(city, units="metric") -> dict
 - fetch_forecast_by_city(city, units="metric") -> list[dict]
 - detect_city_via_ip() -> Optional[str]
 - fetch_weather_by_ip(units="metric") -> dict

This file loads OPENWEATHER_API_KEY from .env if present. It does NOT raise at import
time when the key is missing; instead each function gives a helpful error if the key
is not set.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional
import requests
from dotenv import load_dotenv

# Load .env (if present)
load_dotenv()
API_KEY = os.getenv("OPENWEATHER_API_KEY")

BASE = "https://api.openweathermap.org/data/2.5"


# Internal helper
def _raise_if_no_key():
    if not API_KEY:
        raise RuntimeError(
            "OPENWEATHER_API_KEY is not set. Create a .env file with:\n"
            "OPENWEATHER_API_KEY=your_api_key_here"
        )


def _get_json(url: str, params: dict) -> dict:
    """HTTP GET with timeout and friendly errors."""
    try:
        resp = requests.get(url, params=params, timeout=12)
        # raise_for_status will raise for HTTP 4xx/5xx
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            # invalid JSON
            raise RuntimeError("Invalid JSON response from server")
    except requests.HTTPError as e:
        # try to parse API message
        try:
            j = resp.json()
            msg = j.get("message") or str(j)
        except Exception:
            msg = str(e)
        raise RuntimeError(f"API error: {msg}")
    except requests.RequestException as e:
        raise RuntimeError(f"Network error: {e}")


def fetch_weather_by_city(city: str, units: str = "metric") -> Dict:
    """
    Fetch current weather for `city`. Returns a normalized dict:

    {
      "city": "CityName",
      "country": "XX",
      "temperature": float,
      "humidity": int,
      "pressure": int,
      "description": "clear sky",
      "icon": "01d",
      "wind_speed": float,
      "sunrise": unix_ts,
      "sunset": unix_ts,
      "timezone": seconds_offset,
      "coord": {"lat":..., "lon": ...}
    }

    Raises RuntimeError on network/api errors.
    """
    _raise_if_no_key()
    url = f"{BASE}/weather"
    params = {"q": city, "appid": API_KEY, "units": units}
    data = _get_json(url, params)

    # Normalize safely (use dict.get chain)
    result = {
        "city": data.get("name") or city,
        "country": (data.get("sys") or {}).get("country", ""),
        "temperature": (data.get("main") or {}).get("temp"),
        "humidity": (data.get("main") or {}).get("humidity"),
        "pressure": (data.get("main") or {}).get("pressure"),
        "description": (data.get("weather") or [{}])[0].get("description", "N/A"),
        "icon": (data.get("weather") or [{}])[0].get("icon", ""),
        "wind_speed": (data.get("wind") or {}).get("speed"),
        "sunrise": (data.get("sys") or {}).get("sunrise"),
        "sunset": (data.get("sys") or {}).get("sunset"),
        "timezone": data.get("timezone", 0),
        "coord": data.get("coord", {}),
    }
    return result


def fetch_forecast_by_city(city: str, units: str = "metric") -> List[Dict]:
    """
    Fetch 5-day / 3-hour forecast (OpenWeather). Returns list of entries:

    [
      {"dt_txt": "2025-09-03 12:00:00", "date": "2025-09-03",
       "temperature": ..., "humidity": ..., "description": ..., "icon": "..."},
      ...
    ]

    Raises RuntimeError on network/api errors.
    """
    _raise_if_no_key()
    url = f"{BASE}/forecast"
    params = {"q": city, "appid": API_KEY, "units": units}
    data = _get_json(url, params)

    out: List[Dict] = []
    for item in data.get("list", []):
        dt_txt = item.get("dt_txt")
        out.append(
            {
                "dt_txt": dt_txt,
                "date": dt_txt.split(" ")[0] if dt_txt else "",
                "temperature": (item.get("main") or {}).get("temp"),
                "humidity": (item.get("main") or {}).get("humidity"),
                "description": (item.get("weather") or [{}])[0].get("description", "N/A"),
                "icon": (item.get("weather") or [{}])[0].get("icon", ""),
            }
        )
    return out


def detect_city_via_ip() -> Optional[str]:
    """
    Try several free IP->city providers; return first non-empty city string or None.
    """
    endpoints = [
        "http://ip-api.com/json/",
        "https://ipinfo.io/json",
        "https://ipapi.co/json/",
    ]
    for url in endpoints:
        try:
            r = requests.get(url, timeout=6)
            r.raise_for_status()
            j = r.json()
            # providers vary: check multiple keys
            city = j.get("city") or j.get("region") or j.get("city_name")
            if city and isinstance(city, str) and city.strip():
                return city.strip()
        except Exception:
            continue
    return None


def fetch_weather_by_ip(units: str = "metric") -> Dict:
    """
    Detect city via IP and return same normalized dict as fetch_weather_by_city.
    Raises RuntimeError if detection or fetch fails.
    """
    city = detect_city_via_ip()
    if not city:
        raise RuntimeError("Could not detect city from IP.")
    return fetch_weather_by_city(city, units=units)
