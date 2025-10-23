# PartyPrint Printer Client

This is the Raspberry Pi client that polls the PartyPrint server for new photos and prints them to a local Canon Selphy CP1500 printer.

## Setup on Raspberry Pi

### 1. Create Virtual Environment

```bash
cd printer-client

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Printer

Make sure your Canon Selphy CP1500 is connected and configured in CUPS:

```bash
# Check available printers
lpstat -p -d

# If not configured, add your printer through CUPS web interface
# http://localhost:631
```

### 4. Run the Script

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Run the script
python polling_script.py
```

The script will:
1. Scan for available printers
2. Ask you to select one (or use `PRINTER_NAME` env var to skip)
3. Start polling the server for new print jobs
4. Download, resize, and print photos automatically

## Configuration

### Environment Variables

- `PRINTER_NAME` - Skip interactive printer selection (e.g., `PRINTER_NAME=Canon_CP1500`)

### Script Settings

Edit `polling_script.py` to change:

- `API_BASE` - Server URL (default: `https://party.emits.ai`)
- `DRY_RUN` - Set to `False` to enable actual printing (default: `True`)

## How It Works

1. **Polls** the server's `/next-job` endpoint every 5 seconds
2. **Downloads** new photos from the server
3. **Processes** images for optimal 4x6" printing:
   - Resizes to 1800x1200px (300 DPI)
   - Maintains aspect ratio with white letterboxing
   - Auto-rotates based on EXIF data
4. **Prints** to the selected Canon Selphy printer
5. **Tracks** printed files to avoid duplicates

## Files

- `polling_script.py` - Main polling and printing script
- `requirements.txt` - Python dependencies
- `/tmp/partyprint/` - Downloaded and processed images
- `/tmp/printed.log` - Tracking file for printed jobs

## Running as a Service

To run automatically on boot, create a systemd service:

```bash
sudo nano /etc/systemd/system/partyprint.service
```

```ini
[Unit]
Description=PartyPrint Printer Client
After=network.target cups.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/tkpatyprint/printer-client
Environment="PRINTER_NAME=Canon_CP1500"
ExecStart=/home/pi/tkpatyprint/printer-client/venv/bin/python /home/pi/tkpatyprint/printer-client/polling_script.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```bash
sudo systemctl enable partyprint
sudo systemctl start partyprint
sudo systemctl status partyprint
```
