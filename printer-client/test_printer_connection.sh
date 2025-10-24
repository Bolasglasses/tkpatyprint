#!/bin/bash
# Test if the Canon Selphy is reachable on the network

echo "========================================="
echo "Testing Network Connection to Printer"
echo "========================================="

echo ""
echo "1. Checking if mDNS/Bonjour can find the printer..."
avahi-browse -t _ipps._tcp --resolve | grep -i canon

echo ""
echo "2. Trying to resolve the hostname..."
ping -c 2 "Canon SELPHY CP1500.local" 2>/dev/null || echo "Cannot ping printer"

echo ""
echo "3. Checking if cups-browsed is running..."
systemctl status cups-browsed | grep Active

echo ""
echo "4. Current printer state..."
lpstat -p Canon_SELPHY_CP1500

echo ""
echo "========================================="
echo "Recommendations:"
echo "========================================="
echo "If the printer isn't found:"
echo "1. Make sure the Canon Selphy is ON and connected to the SAME network"
echo "2. Make sure the Pi and printer are on the same WiFi"
echo "3. Restart cups-browsed: sudo systemctl restart cups-browsed"
echo "4. Check printer's IP address from its menu and try: ping <IP>"
echo ""
echo "Alternative: Connect via USB instead of network"
