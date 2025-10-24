#!/bin/bash
# Switch Canon Selphy from network to USB connection

echo "========================================="
echo "Finding USB Printers"
echo "========================================="
echo "Please make sure the Canon Selphy is connected via USB cable"
echo ""
read -p "Press Enter when ready..."

echo ""
echo "Scanning for USB devices..."
sudo lpinfo -v | grep -i usb

echo ""
echo "Scanning for Canon devices specifically..."
USB_URI=$(sudo lpinfo -v | grep -i canon | grep usb | head -n 1 | awk '{print $2}')

if [ -z "$USB_URI" ]; then
    echo ""
    echo "❌ No Canon USB printer found!"
    echo ""
    echo "Troubleshooting:"
    echo "1. Make sure the Canon Selphy is connected via USB"
    echo "2. Make sure it's powered ON"
    echo "3. Try: lsusb | grep -i canon"
    echo "4. Check cable connection"
    exit 1
fi

echo ""
echo "✅ Found Canon printer at: $USB_URI"
echo ""
read -p "Configure this printer? (y/n) " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Removing old network-based printer..."
    sudo lpadmin -x Canon_SELPHY_CP1500

    echo "Adding USB printer..."
    sudo lpadmin -p Canon_SELPHY_CP1500 \
        -v "$USB_URI" \
        -m everywhere \
        -E \
        -o printer-is-shared=false

    echo ""
    echo "Setting as default printer..."
    sudo lpadmin -d Canon_SELPHY_CP1500

    echo ""
    echo "✅ Printer configured!"
    echo ""
    echo "Testing printer status..."
    lpstat -p Canon_SELPHY_CP1500

    echo ""
    echo "========================================="
    echo "Test Print"
    echo "========================================="
    read -p "Send a test print? (y/n) " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Create a small test image
        echo "Creating test image..."
        python3 << 'PYTHON'
from PIL import Image, ImageDraw, ImageFont

# Create 4x6 test image at 300 DPI
img = Image.new('RGB', (1800, 1200), color='white')
draw = ImageDraw.Draw(img)

# Draw some test patterns
draw.rectangle([50, 50, 1750, 1150], outline='black', width=5)
draw.text((900, 600), "PartyPrint Test", fill='black', anchor='mm')

img.save('/tmp/test_print.jpg', 'JPEG', quality=95)
print("Test image created: /tmp/test_print.jpg")
PYTHON

        echo ""
        echo "Sending to printer..."
        lp -d Canon_SELPHY_CP1500 /tmp/test_print.jpg

        echo ""
        echo "Check the printer!"
    fi
fi

echo ""
echo "Done!"
