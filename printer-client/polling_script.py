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

# Printer configuration (will be auto-detected at startup)
PRINTER_NAME = os.getenv("PRINTER_NAME", "")

# Set to True to disable actual printing (for development)
DRY_RUN = False

# Set to True to skip image preprocessing (for debugging)
# When True, sends the original downloaded file directly to printer
SKIP_PREPROCESSING = False

# Image resolution settings for Canon Selphy CP1500
# Canon Selphy specs: 300 DPI dye-sublimation printer
# Target: 4x6 inch (postcard size)
# Options to try if images are too small:
# - "300dpi": 1800x1200 pixels (standard, should be 4x6")
# - "600dpi": 3600x2400 pixels (high-res, also 4x6" but more data)
# - "native": Use whatever the Canon Selphy native resolution is
IMAGE_RESOLUTION = "300dpi"  # Try "600dpi" if images are too small

# Border width in inches (white border around image for classic photo look)
# 0.25 inch = quarter inch border on all sides
BORDER_INCHES = 0.25

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

            # Detect portrait vs landscape orientation
            is_portrait = img.height > img.width

            # Target dimensions based on IMAGE_RESOLUTION setting
            if IMAGE_RESOLUTION == "600dpi":
                # Higher resolution - 600 DPI
                base_width = 3600   # 6 inches * 600 DPI
                base_height = 2400  # 4 inches * 600 DPI
                dpi_value = 600
            else:
                # Standard resolution - 300 DPI
                base_width = 1800   # 6 inches * 300 DPI
                base_height = 1200  # 4 inches * 300 DPI
                dpi_value = 300

            # Swap dimensions for portrait photos
            if is_portrait:
                target_width = base_height   # 4 inches (narrower)
                target_height = base_width   # 6 inches (taller)
                logger.info(f"Portrait orientation detected: {target_width}x{target_height} at {dpi_value} DPI")
            else:
                target_width = base_width
                target_height = base_height
                logger.info(f"Landscape orientation detected: {target_width}x{target_height} at {dpi_value} DPI")

            # Calculate border size in pixels
            border_pixels = int(BORDER_INCHES * dpi_value)
            logger.info(f"Adding {BORDER_INCHES}\" border ({border_pixels} pixels on each side)")

            # Reduce available area by border on all sides
            available_width = target_width - (2 * border_pixels)
            available_height = target_height - (2 * border_pixels)

            # Calculate scaling to fit image within available area (inside border)
            img.thumbnail((available_width, available_height), Image.Resampling.LANCZOS)

            # Create a white canvas at full target size (pure RGB white)
            canvas = Image.new('RGB', (target_width, target_height), (255, 255, 255))

            # Calculate position to center the image (accounting for border)
            x_offset = (target_width - img.width) // 2
            y_offset = (target_height - img.height) // 2

            # Paste the resized image onto the canvas (centered with border)
            canvas.paste(img, (x_offset, y_offset))

            # Critical: Save as baseline JPEG (like 2000s digital cameras)
            # Canon Selphy CP1500 is an older embedded system that requires:
            # - Baseline DCT encoding (NOT progressive)
            # - Standard JPEG markers
            # - Proper DPI metadata
            logger.info(f"Encoding as baseline JPEG for Canon Selphy compatibility...")

            # Note: We're NOT stripping EXIF/ICC anymore - Canon Selphy might need them
            # Modern phone cameras include sRGB color space and DPI metadata
            canvas.save(
                output_path,
                format='JPEG',
                quality=95,
                optimize=False,       # No optimization - keep it simple
                progressive=False,    # Baseline DCT, NOT progressive
                subsampling=0,        # 4:4:4 chroma (best quality)
                dpi=(dpi_value, dpi_value)  # Set DPI metadata based on resolution
                # NOT stripping ICC profile - printer might need sRGB
                # NOT stripping EXIF - printer might use orientation data
            )

            logger.info(f"  DPI metadata set to: {dpi_value}x{dpi_value}")

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
logger.info(f"Skip Preprocessing: {SKIP_PREPROCESSING}")
logger.info(f"Image Resolution: {IMAGE_RESOLUTION}")
logger.info(f"Border Width: {BORDER_INCHES} inches")
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

    # Automatic printer selection (no interactive prompt)
    # Priority: 1) PRINTER_NAME env var, 2) system default, 3) first available
    env_printer = os.getenv("PRINTER_NAME")
    if env_printer and env_printer in printers:
        selected_printer = env_printer
        logger.info(f"Using printer from PRINTER_NAME env var: {selected_printer}")
    elif default_printer and default_printer in printers:
        selected_printer = default_printer
        logger.info(f"Using system default printer: {selected_printer}")
    else:
        selected_printer = printers[0]
        logger.info(f"Using first available printer: {selected_printer}")

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

            # Decide whether to preprocess or use original
            if SKIP_PREPROCESSING:
                logger.info(f"⚠️  SKIP_PREPROCESSING=True - sending original file directly to printer")
                print_path = original_path
            else:
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

                # Try minimal options first - let CUPS handle the conversion
                result = subprocess.run([
                    "lp",
                    "-d", PRINTER_NAME,
                    str(print_path)
                ], capture_output=True, text=True)

                if result.returncode == 0:
                    logger.info(f"✅ Print job submitted: {filename}")

                    # Extract job ID from output
                    job_id = None
                    if result.stdout.strip():
                        logger.info(f"   Job info: {result.stdout.strip()}")
                        # Try to extract job ID (format: "request id is Canon_SELPHY_CP1500-123")
                        import re
                        match = re.search(r'request id is ([^\s]+)', result.stdout)
                        if match:
                            job_id = match.group(1)
                            logger.info(f"   Job ID: {job_id}")

                    # Check printer status
                    logger.info(f"Checking printer status...")
                    status_result = subprocess.run(
                        ["lpstat", "-p", PRINTER_NAME],
                        capture_output=True,
                        text=True
                    )
                    if status_result.stdout:
                        logger.info(f"   Printer status: {status_result.stdout.strip()}")

                    # Monitor the job for a few seconds to catch early failures
                    if job_id:
                        import time
                        logger.info(f"Monitoring print job for errors...")
                        time.sleep(3)  # Wait 3 seconds for job to start processing

                        # Check job status
                        job_status = subprocess.run(
                            ["lpstat", "-l", "-W", "completed"],
                            capture_output=True,
                            text=True
                        )

                        if job_id in job_status.stdout:
                            logger.warning(f"⚠️  Job completed quickly - checking for errors...")

                            # Get CUPS error log
                            error_log = subprocess.run(
                                ["sudo", "tail", "-n", "20", "/var/log/cups/error_log"],
                                capture_output=True,
                                text=True
                            )
                            if error_log.returncode == 0 and error_log.stdout:
                                logger.error(f"Recent CUPS errors:")
                                for line in error_log.stdout.strip().split('\n')[-5:]:
                                    logger.error(f"  {line}")
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
