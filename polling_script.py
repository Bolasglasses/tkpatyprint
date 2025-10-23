import time, requests, subprocess, os
import logging
from pathlib import Path
from PIL import Image, ImageOps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

API_BASE = "https://party.emits.ai"
NEXT_JOB_URL = f"{API_BASE}/next-job"
PRINTED_TRACKER = "/tmp/printed.log"
DOWNLOAD_DIR = Path("/tmp/partyprint")

# Printer configuration
PRINTER_NAME = os.getenv("PRINTER_NAME", "Canon_CP1500")

# Set to True to disable actual printing (for development)
DRY_RUN = True

# Create download directory
DOWNLOAD_DIR.mkdir(exist_ok=True)

printed = set()
if os.path.exists(PRINTED_TRACKER):
    printed = set(open(PRINTED_TRACKER).read().splitlines())

# Function definitions
def get_available_printers():
    """Get list of available CUPS printers"""
    try:
        result = subprocess.run(
            ["lpstat", "-p", "-d"],
            capture_output=True,
            text=True,
            check=True
        )

        printers = []
        default_printer = None

        for line in result.stdout.split('\n'):
            line = line.strip()
            if line.startswith('printer '):
                # Extract printer name from "printer PrinterName is ..."
                parts = line.split()
                if len(parts) >= 2:
                    printer_name = parts[1]
                    printers.append(printer_name)
            elif line.startswith('system default destination:'):
                # Extract default printer
                parts = line.split(':')
                if len(parts) >= 2:
                    default_printer = parts[1].strip()

        logger.info(f"Available printers: {printers}")
        if default_printer:
            logger.info(f"Default printer: {default_printer}")

        return printers, default_printer

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to get printers: {e}")
        return [], None
    except Exception as e:
        logger.error(f"Error getting printers: {e}")
        return [], None

def verify_printer(printer_name: str) -> bool:
    """Verify that the specified printer exists"""
    printers, _ = get_available_printers()
    return printer_name in printers

def preprocess_image_for_print(input_path: Path, output_path: Path) -> None:
    """
    Preprocess image for Canon Selphy CP1500 4x6" printing.
    - Target size: 1800x1200 pixels (4x6" at 300 DPI)
    - Maintains aspect ratio with letterboxing (no cropping)
    - Adds white borders if needed
    - Auto-rotates based on EXIF
    """
    try:
        # Open and auto-rotate image based on EXIF orientation
        with Image.open(input_path) as img:
            # Auto-rotate based on EXIF data
            img = ImageOps.exif_transpose(img)

            # Convert to RGB if needed (handles RGBA, grayscale, etc.)
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Target dimensions for 4x6" at 300 DPI
            # Canon Selphy CP1500 prints at 300x300 DPI
            target_width = 1800  # 6 inches * 300 DPI
            target_height = 1200  # 4 inches * 300 DPI

            # Calculate scaling to fit image within target dimensions
            img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)

            # Create a white canvas at target size
            canvas = Image.new('RGB', (target_width, target_height), (255, 255, 255))

            # Calculate position to center the image
            x_offset = (target_width - img.width) // 2
            y_offset = (target_height - img.height) // 2

            # Paste the image onto the canvas
            canvas.paste(img, (x_offset, y_offset))

            # Save the processed image
            canvas.save(output_path, 'JPEG', quality=95, optimize=True)

            logger.info(f"Preprocessed image: {input_path.name} -> {output_path.name} "
                       f"(original: {img.width}x{img.height}, output: {target_width}x{target_height})")

    except Exception as e:
        logger.error(f"Failed to preprocess image: {e}")
        raise

# Startup checks
logger.info("=" * 60)
logger.info("PartyPrint Polling Service Starting")
logger.info("=" * 60)
logger.info(f"API Base: {API_BASE}")
logger.info(f"Dry Run Mode: {DRY_RUN}")
logger.info(f"Download Directory: {DOWNLOAD_DIR}")

# Discover and select printer (even in dry run mode)
logger.info("Scanning for printers...")
printers, default_printer = get_available_printers()

if not printers:
    logger.warning("⚠️  No printers found.")
    if not DRY_RUN:
        logger.error("❌ Cannot run in print mode without a printer.")
        logger.error("Please check CUPS configuration and ensure printer is connected.")
        logger.error("Run 'lpstat -p -d' to check available printers.")
        exit(1)
    else:
        logger.info("Continuing in dry run mode without printer selection...")
        PRINTER_NAME = "None"
else:
    logger.info(f"Found {len(printers)} printer(s):")
    for i, p in enumerate(printers, 1):
        marker = " (system default)" if p == default_printer else ""
        logger.info(f"  {i}. {p}{marker}")

    # Check if PRINTER_NAME env var is set and valid
    if os.getenv("PRINTER_NAME") and PRINTER_NAME in printers:
        logger.info(f"Using printer from PRINTER_NAME env var: {PRINTER_NAME}")
        selected_printer = PRINTER_NAME
    else:
        # Interactive selection
        print()
        print("=" * 60)
        while True:
            try:
                choice = input(f"Select printer (1-{len(printers)}) or press Enter for default: ").strip()

                if choice == "":
                    if default_printer and default_printer in printers:
                        selected_printer = default_printer
                        print(f"Using system default: {selected_printer}")
                        break
                    elif printers:
                        selected_printer = printers[0]
                        print(f"Using first printer: {selected_printer}")
                        break

                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(printers):
                    selected_printer = printers[choice_idx]
                    print(f"Selected: {selected_printer}")
                    break
                else:
                    print(f"Invalid choice. Please enter a number between 1 and {len(printers)}")
            except ValueError:
                print(f"Invalid input. Please enter a number between 1 and {len(printers)}")
            except KeyboardInterrupt:
                print("\nCancelled by user")
                exit(0)

        print("=" * 60)
        print()

    PRINTER_NAME = selected_printer
    logger.info(f"✅ Using printer: {PRINTER_NAME}")

if DRY_RUN:
    logger.info("🚫 Dry run mode enabled - no actual printing will occur")

logger.info("=" * 60)

# Main polling loop
while True:
    try:
        response = requests.get(NEXT_JOB_URL, timeout=5).json()

        # Check if there's a job to print
        if response.get("id") is None:
            logger.info("No pending jobs. Waiting...")
            time.sleep(5)
            continue

        filename = response["filename"]

        if filename not in printed:
            logger.info(f"{'[DRY RUN] Would print' if DRY_RUN else 'Printing'} {filename}...")
            url = f"{API_BASE}/files/{filename}"

            # Download original file
            original_path = DOWNLOAD_DIR / filename
            logger.info(f"Downloading from {url}")

            with open(original_path, "wb") as out:
                out.write(requests.get(url).content)

            logger.info(f"Downloaded to {original_path}")

            # Create print-ready version (4x6" at 300 DPI with letterboxing)
            print_filename = f"print_{filename}"
            print_path = DOWNLOAD_DIR / print_filename

            logger.info(f"Processing image for 4x6\" printing...")
            preprocess_image_for_print(original_path, print_path)

            if DRY_RUN:
                logger.info(f"🚫 Skipping print command (DRY_RUN=True)")
                logger.info(f"   Original: {original_path}")
                logger.info(f"   Print-ready: {print_path}")
            else:
                # Print the preprocessed file with Canon Selphy settings
                logger.info(f"Sending to printer '{PRINTER_NAME}'...")
                result = subprocess.run([
                    "lp",
                    "-d", PRINTER_NAME,
                    "-o", "media=Postcard",      # Canon Selphy uses "Postcard" for 4x6"
                    "-o", "ColorModel=RGB",      # Ensure RGB color mode for dye-sub
                    "-o", "print-quality=5",     # Highest quality
                    str(print_path)
                ], capture_output=True, text=True)

                if result.returncode == 0:
                    logger.info(f"✅ Printed {filename}")
                    if result.stdout.strip():
                        logger.info(f"   Print job: {result.stdout.strip()}")
                else:
                    logger.error(f"❌ Print failed: {result.stderr.strip()}")
                    continue  # Don't mark as printed if it failed

            printed.add(filename)
            open(PRINTED_TRACKER, "a").write(filename + "\n")
        else:
            logger.info(f"⏭️  Skipping {filename} (already printed)")

        time.sleep(5)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        time.sleep(10)
