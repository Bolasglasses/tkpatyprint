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

# Set to True to disable actual printing (for development)
DRY_RUN = True

# Create download directory
DOWNLOAD_DIR.mkdir(exist_ok=True)

printed = set()
if os.path.exists(PRINTED_TRACKER):
    printed = set(open(PRINTED_TRACKER).read().splitlines())

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
                logger.info(f"Sending to printer...")
                subprocess.run([
                    "lp",
                    "-d", "Canon_CP1500",
                    "-o", "media=Postcard",      # Canon Selphy uses "Postcard" for 4x6"
                    "-o", "ColorModel=RGB",      # Ensure RGB color mode for dye-sub
                    "-o", "print-quality=5",     # Highest quality
                    str(print_path)
                ])
                logger.info(f"✅ Printed {filename}")

            printed.add(filename)
            open(PRINTED_TRACKER, "a").write(filename + "\n")
        else:
            logger.info(f"⏭️  Skipping {filename} (already printed)")

        time.sleep(5)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        time.sleep(10)
