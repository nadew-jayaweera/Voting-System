# Real-Time Voting System (Flask + Socket.IO)

A **real-time web-based voting system** built using **Flask**, **Flask-SocketIO**, and **SQLite**.  
This system is designed for **live competitions or events**, where an admin controls voting rounds and users can cast **Yes / No** votes in real time.

---

## 📌 Key Features

### 👤 Voters
- Live voting interface
- Vote **Yes / No** for the currently active contestant
- One vote per round (IP-based restriction)
- Real-time score updates
- Automatic vote lock after time expires

### 🛠️ Admin Panel
- Secure admin login (password-protected)
- Hidden admin URL
- Start voting for a specific contestant
- Set voting duration (timer-based rounds)
- Stop voting manually
- Reset all votes
- Export voting results to **Excel**
- Live score broadcasting to all screens

### 📺 Display Screen
- Real-time public scoreboard
- Shows current contestant
- Countdown timer
- Live vote updates via WebSockets

---

## ⚙️ Tech Stack

- Python
- Flask
- Flask-SocketIO
- SQLite
- Pandas
- OpenPyXL
- HTML / CSS / JavaScript
- dotenv (.env)

---

## 🚀 Installation & Setup
```
git clone https://github.com/nadew-jayaweera/Voting-System.git  
cd Voting-System  
pip install -r requirements.txt  
python app.py
```
---

## 🌐 Routes

/ – Welcome page  
/vote – Voter interface  
/screen – Public display  
/login – Admin login

---

## 📤 Export Results

Admins can export voting data as **Competition_Results.xlsx**

---

## 👨‍💻 Author

@Nadew-Jayaweera  

