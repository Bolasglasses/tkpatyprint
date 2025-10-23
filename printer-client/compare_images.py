#!/usr/bin/env python3
"""
Diagnostic tool to compare image metadata between phone photos and our processed images.
Usage: python compare_images.py <phone_photo.jpg> <processed_photo.jpg>
"""

import sys
from PIL import Image
from pathlib import Path

def analyze_image(path):
    """Analyze and print all metadata about an image file"""
    print(f"\n{'='*60}")
    print(f"Analyzing: {path}")
    print(f"{'='*60}")

    file_size = Path(path).stat().st_size
    print(f"File size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")

    with Image.open(path) as img:
        print(f"\n📐 Image Properties:")
        print(f"  Format: {img.format}")
        print(f"  Mode: {img.mode}")
        print(f"  Size: {img.size} ({img.width}x{img.height})")

        # DPI info
        if hasattr(img, 'info'):
            dpi = img.info.get('dpi')
            print(f"  DPI: {dpi}")

            # JPEG specific info
            if img.format == 'JPEG':
                print(f"\n📷 JPEG Info:")
                progressive = img.info.get('progressive', False)
                print(f"  Progressive: {progressive}")
                print(f"  Quality: {img.info.get('quality', 'Unknown')}")
                print(f"  Subsampling: {img.info.get('subsampling', 'Unknown')}")

                # Check for ICC profile
                icc = img.info.get('icc_profile')
                print(f"  ICC Profile: {'Present' if icc else 'None'}")

                # Check for EXIF
                exif = img.info.get('exif')
                print(f"  EXIF Data: {'Present' if exif else 'None'}")

                # If EXIF present, show orientation
                if hasattr(img, '_getexif') and img._getexif():
                    exif_data = img._getexif()
                    orientation = exif_data.get(274)  # 274 is orientation tag
                    print(f"  EXIF Orientation: {orientation}")

        # Try to get more detailed info
        try:
            print(f"\n🔍 Detailed Info:")
            for key, value in img.info.items():
                if key not in ['icc_profile', 'exif']:  # Skip binary data
                    print(f"  {key}: {value}")
        except:
            pass

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python compare_images.py <image1.jpg> [image2.jpg] ...")
        sys.exit(1)

    for image_path in sys.argv[1:]:
        if Path(image_path).exists():
            analyze_image(image_path)
        else:
            print(f"\n❌ File not found: {image_path}")

    print(f"\n{'='*60}")
    print("Analysis complete!")
    print(f"{'='*60}\n")
