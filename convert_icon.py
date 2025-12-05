"""
Convert logo.png to logo.ico for Windows icon
Requires Pillow: pip install Pillow
"""
try:
    from PIL import Image
    import os
    
    if os.path.exists('logo.png'):
        # Open PNG image
        img = Image.open('logo.png')
        
        # Convert to RGBA if not already (for transparency support)
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Windows prefers multiple sizes: 256x256, 128x128, 64x64, 48x48, 32x32, 16x16
        sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
        
        # Create resized images for each size
        resized_images = []
        for size in sizes:
            resized = img.resize(size, Image.Resampling.LANCZOS)
            resized_images.append(resized)
        
        # Save as ICO - PIL will create ICO with all specified sizes
        # Use the largest size as base and specify all sizes
        resized_images[0].save('logo.ico', format='ICO', sizes=[(w, h) for w, h in sizes])
        print("Successfully converted logo.png to logo.ico")
        print(f"Created ICO with sizes: {', '.join([f'{s[0]}x{s[1]}' for s in sizes])}")
    else:
        print("logo.png not found!")
except ImportError:
    print("Pillow not installed. Installing...")
    import subprocess
    import sys
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("Pillow installed. Please run this script again.")
    except:
        print("Failed to install Pillow. Please install manually: pip install Pillow")
except Exception as e:
    print(f"Error converting icon: {e}")
    import traceback
    traceback.print_exc()

