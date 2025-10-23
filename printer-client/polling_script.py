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
DRY_RUN = False

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
    - Handles progressive JPEG, WebP, PNG, and other formats
    - Re-encodes as baseline JPEG (like 2000s digital cameras)
    - Target size: 1800x1200 pixels (4x6" at 300 DPI)
    - Maintains aspect ratio with letterboxing (no cropping)
    - Adds white borders if needed
    - Auto-rotates based on EXIF
    """
    try:
        # Open image - Pillow will handle any format (JPEG, PNG, WebP, etc.)
        with Image.open(input_path) as img:
            # Get original format info for logging
            original_format = img.format
            original_mode = img.mode

            logger.info(f"Input image: format={original_format}, mode={original_mode}, size={img.size}")

            # Auto-rotate based on EXIF data
            img = ImageOps.exif_transpose(img)

            # Convert to RGB - strips alpha channels, handles grayscale, CMYK, etc.
            # This is crucial for consistent JPEG encoding
            if img.mode != 'RGB':
                logger.info(f"Converting from {img.mode} to RGB")
                img = img.convert('RGB')

            # Target dimensions for 4x6" at 300 DPI
            # Canon Selphy CP1500 prints at 300x300 DPI
            target_width = 1800  # 6 inches * 300 DPI
            target_height = 1200  # 4 inches * 300 DPI

            # Calculate scaling to fit image within target dimensions
            img.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)

            # Create a white canvas at target size (pure RGB white)
            canvas = Image.new('RGB', (target_width, target_height), (255, 255, 255))

            # Calculate position to center the image
            x_offset = (target_width - img.width) // 2
            y_offset = (target_height - img.height) // 2

            # Paste the resized image onto the canvas
            canvas.paste(img, (x_offset, y_offset))

            # Critical: Save as baseline JPEG (like 2000s digital cameras)
            # Canon Selphy CP1500 is an older embedded system that requires:
            # - Baseline DCT encoding (NOT progressive)
            # - Standard JPEG markers
            # - No fancy optimizations
            logger.info(f"Encoding as baseline JPEG for Canon Selphy compatibility...")
            canvas.save(
                output_path,
                format='JPEG',
                quality=95,
                optimize=False,       # No optimization - keep it simple
                progressive=False,    # Baseline DCT, NOT progressive
                subsampling=0,        # 4:4:4 chroma (best quality)
                icc_profile=None,     # Strip ICC profile for compatibility
                exif=b''              # Strip EXIF data for compatibility
            )

            output_size = output_path.stat().st_size
            logger.info(f"✓ Created baseline JPEG: {output_path.name}")
            logger.info(f"  Input:  {original_format} {img.size} ({original_mode})")
            logger.info(f"  Output: JPEG {target_width}x{target_height} (RGB, {output_size:,} bytes)")

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
            # Files are stored in S3, not on the API server
            url = f"https://partyprint.s3.amazonaws.com/{filename}"

            # Download original file
            original_path = DOWNLOAD_DIR / filename
            logger.info(f"Downloading from {url}")

            try:
                download_response = requests.get(url, timeout=30)
                download_response.raise_for_status()  # Raise error for bad status codes

                # Check if we actually got an image
                content_type = download_response.headers.get('content-type', '')
                logger.info(f"Downloaded {len(download_response.content)} bytes (content-type: {content_type})")

                if len(download_response.content) == 0:
                    logger.error(f"Downloaded file is empty!")
                    continue

                # Save the file
                with open(original_path, "wb") as out:
                    out.write(download_response.content)

                logger.info(f"Saved to {original_path}")

                # Verify the file is a valid image
                if not original_path.exists():
                    logger.error(f"File was not saved properly!")
                    continue

                file_size = original_path.stat().st_size
                logger.info(f"File size on disk: {file_size} bytes")

                if file_size == 0:
                    logger.error(f"Saved file is empty!")
                    continue

            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to download image: {e}")
                continue

            # Create print-ready version (4x6" at 300 DPI with letterboxing)
            print_filename = f"print_{filename}"
            print_path = DOWNLOAD_DIR / print_filename

            logger.info(f"Processing image for 4x6\" printing...")
            try:
                preprocess_image_for_print(original_path, print_path)
            except Exception as e:
                logger.error(f"Failed to process image: {e}")
                # Check if the downloaded file is actually HTML (error page)
                with open(original_path, 'rb') as f:
                    first_bytes = f.read(100)
                    if b'<!DOCTYPE' in first_bytes or b'<html' in first_bytes:
                        logger.error(f"Downloaded file appears to be HTML, not an image!")
                        logger.error(f"First 100 bytes: {first_bytes}")
                continue

            if DRY_RUN:
                logger.info(f"🚫 Skipping print command (DRY_RUN=True)")
                logger.info(f"   Original: {original_path}")
                logger.info(f"   Print-ready: {print_path}")
            else:
                # Print the preprocessed file with Canon Selphy settings
                logger.info(f"Sending to printer '{PRINTER_NAME}'...")
                logger.info(f"Print file: {print_path} ({print_path.stat().st_size} bytes)")

                result = subprocess.run([
                    "lp",
                    "-d", PRINTER_NAME,
                    "-o", "media=Postcard",      # Canon Selphy uses "Postcard" for 4x6"
                    "-o", "ColorModel=RGB",      # Ensure RGB color mode for dye-sub
                    "-o", "print-quality=5",     # Highest quality
                    str(print_path)
                ], capture_output=True, text=True)

                if result.returncode == 0:
                    logger.info(f"✅ Print job submitted: {filename}")
                    if result.stdout.strip():
                        logger.info(f"   Job info: {result.stdout.strip()}")

                    # Check print job status
                    logger.info(f"Checking printer status...")
                    status_result = subprocess.run(
                        ["lpstat", "-p", PRINTER_NAME],
                        capture_output=True,
                        text=True
                    )
                    if status_result.stdout:
                        logger.info(f"   Printer status: {status_result.stdout.strip()}")
                else:
                    logger.error(f"❌ Print command failed: {result.stderr.strip()}")
                    continue  # Don't mark as printed if it failed

            printed.add(filename)
            open(PRINTED_TRACKER, "a").write(filename + "\n")
        else:
            logger.info(f"⏭️  Skipping {filename} (already printed)")

        time.sleep(5)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        time.sleep(10)
