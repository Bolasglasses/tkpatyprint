#!/bin/bash
# Diagnose and potentially fix Canon Selphy printer configuration

echo "========================================="
echo "Current Printer Configuration"
echo "========================================="
lpstat -l -p Canon_SELPHY_CP1500

echo ""
echo "========================================="
echo "Printer Device URI"
echo "========================================="
lpoptions -p Canon_SELPHY_CP1500 | grep device-uri

echo ""
echo "========================================="
echo "All Printer Options"
echo "========================================="
lpoptions -p Canon_SELPHY_CP1500 -l

echo ""
echo "========================================="
echo "Available Printers (including network)"
echo "========================================="
lpinfo -v

echo ""
echo "========================================="
echo "PPD File Location"
echo "========================================="
ls -la /etc/cups/ppd/Canon_SELPHY_CP1500.ppd

echo ""
echo "========================================="
echo "Recommendation"
echo "========================================="
echo "Your printer is set up as 'implicitclass' which is causing issues."
echo "The printer expects 'apple-raster' format but we're sending JPEG."
echo ""
echo "To fix, you need to:"
echo "1. Find the actual printer URI with: lpinfo -v | grep -i canon"
echo "2. Delete the implicit class: sudo lpadmin -x Canon_SELPHY_CP1500"
echo "3. Re-add with direct URI: sudo lpadmin -p Canon_SELPHY_CP1500 -v <URI> -E"
echo ""
echo "OR try setting SKIP_PREPROCESSING=True to send original files"
