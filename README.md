# 🌦️ Weather Fetcher App

A polished Python weather application with a responsive graphical interface.
It fetches real-time weather data from the **OpenWeather API**, displays current conditions, and provides a 5-day forecast with graphs and icons.

---

## ✨ Features

* 🔍 **City Search** – get weather by city name
* 📌 **Favorites** – save and view your favorite cities
* 📍 **Auto-Detect Location** – fetch weather using your IP (with permission)
* 🌡️ **Units Dropdown** – switch between Celsius/Fahrenheit
* 🌓 **Light / Dark Theme**
* 🔄 **Refresh & Notifications**
* 📊 **5-Day Forecast + Graph + Next Prediction**
* 🖱️ **Scrollable & Centered Layout** (with mousepad scrolling)
* ⚡ **Threaded Network Calls** – keeps the UI smooth and responsive

---

## 📂 Project Structure

```
weather-fetcher/
│-- gui.py                # Main GUI interface for the weather app
│-- weather_fetcher.py    # Helper functions to fetch weather & forecast
│-- requirements.txt      # Dependencies list
│-- .env                  # Stores API key (placeholder in repo: "YOUR API HERE")
```

---

## ⚙️ Setup & Installation

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-username/weather-fetcher.git
   cd weather-fetcher
   ```

2. **Create a virtual environment (recommended)**

   ```bash
   python -m venv venv
   source venv/bin/activate   # Linux/Mac
   venv\Scripts\activate      # Windows
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Set up API key**

   * Open the `.env` file
   * Replace:

     ```env
     OPENWEATHER_API_KEY=YOUR API HERE
     ```

     with your actual [OpenWeather API key](https://openweathermap.org/api).

---

## 🚀 Run the App

```bash
python gui.py
```

---

## 📡 API References

* [OpenWeather Current Weather API](https://openweathermap.org/current)


---

## 📸 Screenshots
<img width="1364" height="706" alt="Screenshot 2025-09-10 210000" src="https://github.com/user-attachments/assets/a5bde3cf-08ba-4dba-b69f-13b12dec6738" />

<img width="1365" height="509" alt="Screenshot 2025-09-10 210028" src="https://github.com/user-attachments/assets/80036d4c-bd52-4f65-800c-f92d6decd7fc" />

<img width="301" height="421" alt="Screenshot 2025-09-10 210219" src="https://github.com/user-attachments/assets/80736605-e4a4-4ac8-bd78-92c155c8e711" />

---

## 📜 License

This project is for **educational purposes**.
Feel free to fork and improve!

---

👨‍💻 **Author:** Muhammad Anas Nadeem
🔗 [LinkedIn](https://www.linkedin.com/in/muhammad-anas-nadeem)
