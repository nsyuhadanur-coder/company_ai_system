# NexusScan - Barcode & Inventory Management System

A lightweight, fast, and modular barcode-driven inventory system. Designed for physical barcode scanners (USB/Bluetooth) as well as camera-based scanning. Features real-time stock quantity tracking, per-batch expiration date management with automated **FEFO (First Expired, First Out)** logic, and comprehensive stock movement logs (*Stock In & Stock Out*).

> **Raspberry Pi Ready & Built for Office System Integration**: Developed using Python (Flask) + SQLite with RESTful API endpoints for seamless future integration into central office ERP/database systems.

---

## 🌟 Key Features

1. **3-in-1 Barcode Scan Station**:
   - **Check Stock**: Scan any barcode to instantly display product information, total available units, batch breakdown with expiration dates, and recent movements.
   - **Stock In**: Scan barcode, input received quantity, set expiration date, and record supplier / PO reference.
   - **Stock Out**: Intelligent stock dispatching with **FEFO (First Expired, First Out)** prioritization to reduce inventory shrinkage and wastage.
2. **Per-Batch Expiration Tracking & Financial Loss Valuation**:
   - Dynamic visual badges: **Green** (Valid), **Yellow** (Expiring within 30 days), and **Red** (Expired).
   - Real-time countdown timer showing remaining days before expiration.
   - Financial loss estimation per batch to quantify the exact monetary value at risk.
3. **Financial Valuation & Profitability Analytics**:
   - Track **Cost Price** and **Retail Selling Price** per product.
   - Real-time metrics on dashboard: **Total Inventory Cost**, **Potential Retail Sales Value**, **Potential Gross Profit & Margin %**, and **Expired Stock Loss Valuation**.
   - Interactive **7-Day Movement Trend Chart (Chart.js)** showing daily volume comparison of stock received (IN) vs stock dispatched (OUT).
4. **Comprehensive Movement Audit Logs & Date Range Filter**:
   - Filter transactions by date presets (*Today*, *Yesterday*, *Last 7 Days*, *Last 30 Days*, *This Month*, or *Custom Range*).
   - Filter by transaction type (*IN* / *OUT*) and search by product, barcode, or reference notes.
   - Real-time summary metrics for filtered movements (Total In, Total Out, Net Movement).
5. **Excel / CSV Export Reports**:
   - **Export Movement Logs**: Download filtered transaction history directly into Excel-friendly CSV.
   - **Export Inventory Stock**: One-click download of the complete inventory catalog with cost, selling prices, and total valuation.
   - **Export Expiry Report**: Instant report of all expired batches, item quantities, and estimated loss values.
6. **Printable Barcode Label Generator**:
   - Generate and print barcode stickers (CODE128, EAN13) for items that lack pre-printed barcodes.
7. **Auditory Feedback (Sound FX)**:
   - Built-in audio cues using Web Audio API (high-pitch pleasant chime for success, buzzer for errors).
8. **Multi-Hardware Support**:
   - Out-of-the-box support for USB and Bluetooth handheld scanners (acting as keyboard input).
   - Optional web camera / smartphone camera scanner directly via the web browser.

---

## 🚀 How to Run the System (On Windows / Current PC)

1. Make sure Python 3.8+ is installed.
2. Open PowerShell in this project directory:
   ```powershell
   cd "C:\Users\uer\Documents\BARCODE SYSTEM"
   ```
3. Install dependencies if not already installed:
   ```powershell
   pip install flask pillow
   ```
4. Start the application:
   ```powershell
   python app.py
   ```
5. Open your web browser (Chrome, Edge, Firefox) and navigate to:
   ```
   http://127.0.0.1:5000
   ```

---

## 🍓 Raspberry Pi Deployment Guide (Future Step)

The application is lightweight and runs efficiently on any Raspberry Pi (Raspberry Pi 3, 4, 5, or Zero 2W).

### 1. Installation on Raspberry Pi OS:
```bash
# Update packages
sudo apt update && sudo apt install python3-pip python3-flask git -y

# Copy project folder to Raspberry Pi
cd /home/pi/
cd "BARCODE SYSTEM"

# Run the app
python3 app.py
```

### 2. Auto-Start on Boot (Systemd Service):
Create a systemd service file:
```bash
sudo nano /etc/systemd/system/barcode.service
```
Insert the following configuration:
```ini
[Unit]
Description=Smart Barcode Inventory System
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/BARCODE SYSTEM
ExecStart=/usr/bin/python3 /home/pi/BARCODE SYSTEM/app.py
Restart=always

[Install]
WantedBy=multi-user.target
```
Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable barcode.service
sudo systemctl start barcode.service
```

### 3. Dedicated Kiosk Mode (Touchscreen or Dedicated Monitor):
To launch Raspberry Pi directly into full-screen scanning mode on boot:
```bash
chromium-browser --kiosk --app=http://localhost:5000/scan
```

---

## 🏢 Office System Integration Guide (REST API)

The system includes a clean **REST API (JSON)**. Your office system, ERP, or server can interact directly with the Raspberry Pi across the local network:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/dashboard-stats` | Retrieve inventory summary metrics |
| `GET` | `/api/products` | Retrieve all registered products and current stock |
| `GET` | `/api/product/<barcode>` | Fetch details of a specific barcode including active batches and expiry dates |
| `POST` | `/api/stock-in` | Receive new stock into inventory from office system |
| `POST` | `/api/stock-out` | Dispatch stock from inventory via office system |
| `GET` | `/api/expiring` | Retrieve list of products expiring within 30 days or expired |
| `GET` | `/api/transactions` | Fetch movement logs for financial or ERP reconciliation |

### Example Request (Add Stock In via REST API):
```json
POST http://<RASPBERRY_PI_IP>:5000/api/stock-in
Content-Type: application/json

{
  "barcode": "9556001234567",
  "name": "Fresh Whole Milk 1L",
  "quantity": 10,
  "expiration_date": "2026-12-31",
  "category": "Food & Beverage",
  "reference": "Purchase Order PO-909"
}
```

---

## 📁 File Structure

```
BARCODE SYSTEM/
├── app.py                   # Flask server, web routes & REST API
├── database.py              # SQLite database logic, batches, FEFO & movements
├── seed_demo.py             # Sample test data seeding script
├── inventory.db             # Local SQLite database
├── index.html               # Auto-redirect launcher
├── templates/
│   ├── base.html            # Main layout and Web Audio sound synthesizer
│   ├── dashboard.html       # Overview metrics, alerts & quick scan
│   ├── scan.html            # Primary barcode scanning workstation (Check, In, Out)
│   ├── products.html        # Inventory list & batch details
│   ├── expiring.html        # Expiry tracking monitor
│   ├── transactions.html    # Movement audit log
│   └── barcode_generator.html # Printable barcode label maker
└── README.md                # System documentation
```
