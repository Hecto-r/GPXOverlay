import fitdecode
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import math
import subprocess
import argparse
from collections import deque  # Added for smoothing

# -------------------------
# CONFIGURATION & ASSETS
# -------------------------
FONT_PATH = r"C:\Users\Hector\AppData\Local\Microsoft\Windows\Fonts\Montserrat-Bold.ttf"

def get_fonts(base_size=40):
    try:
        return {
            'huge': ImageFont.truetype(FONT_PATH, int(base_size * 2.0)),    
            'large': ImageFont.truetype(FONT_PATH, int(base_size * 1.4)),   
            'medium': ImageFont.truetype(FONT_PATH, int(base_size * 0.9)),  
            'small': ImageFont.truetype(FONT_PATH, int(base_size * 0.5)),   
            'tiny': ImageFont.truetype(FONT_PATH, int(base_size * 0.4))     
        }
    except:
        return {k: ImageFont.load_default() for k in ['huge', 'large', 'medium', 'small', 'tiny']}

# -------------------------
# HELPERS: Data & Pace
# -------------------------
def get_val(rec, keys, default=0.0):
    for key in keys:
        val = rec.get(key)
        if val is not None:
            return float(val)
    return default

def get_pace_str(speed_mps, use_us):
    if speed_mps <= 0.3:
        return "--:--"
    total_seconds = (1609.34 if use_us else 1000.0) / speed_mps
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    return f"{minutes}:{seconds:02d}"

# -------------------------
# HUD DRAWING FUNCTIONS
# -------------------------

def draw_speedometer(draw, speed_mps, center, fonts, use_us):
    radius = 115 
    pace_str = get_pace_str(speed_mps, use_us)
    
    draw.arc([center[0]-radius, center[1]-radius, center[0]+radius, center[1]+radius], 
             start=135, end=405, fill=(255, 255, 255, 50), width=12)
    
    val_pc = min(speed_mps / 5.0, 1.0)
    draw.arc([center[0]-radius, center[1]-radius, center[0]+radius, center[1]+radius], 
             start=135, end=135 + (270 * val_pc), fill=(0, 255, 127, 255), width=14)
    
    draw.text(center, pace_str, fill="white", font=fonts['huge'], anchor="mm")
    unit_label = "PACE /MI" if use_us else "PACE /KM"
    draw.text((center[0], center[1]+50), unit_label, fill=(200, 200, 200), font=fonts['small'], anchor="mm")

def draw_hr_gauge(draw, hr, pos, fonts):
    zones = [
        (0, 163, (150, 150, 150)), (164, 172, (0, 160, 255)), 
        (173, 182, (0, 255, 100)), (183, 192, (255, 160, 0)), (193, 197, (255, 30, 30))
    ]
    bar_w, bar_h, spacing = 18, 45, 8
    for i, (low, high, color) in enumerate(zones):
        is_active = low <= hr <= high
        alpha = 255 if is_active else 60
        y_off = pos[1] - (i * (bar_h + spacing))
        draw.rectangle([pos[0], y_off, pos[0]+bar_w, y_off+bar_h], fill=(*color, alpha))
        if is_active:
            draw.text((pos[0] + 35, y_off + bar_h/2), f"{int(hr)}", fill="white", font=fonts['large'], anchor="lm")
            draw.text((pos[0] + 35, y_off + bar_h/2 + 25), "BPM", fill="white", font=fonts['tiny'], anchor="lm")

def draw_gps_map(draw, coords, center, size=180):
    if len(coords) < 2: return
    lats, lons = zip(*coords)
    span = max(max(lats)-min(lats), max(lons)-min(lons), 0.0001)
    def to_pixel(lat, lon):
        px = center[0] + (lon - (min(lons)+max(lons))/2) / span * size
        py = center[1] - (lat - (min(lats)+max(lats))/2) / span * size
        return (px, py)
    points = [to_pixel(lat, lon) for lat, lon in coords]
    draw.line(points, fill=(255, 255, 255, 180), width=3)
    draw.ellipse([points[-1][0]-5, points[-1][1]-5, points[-1][0]+5, points[-1][1]+5], fill=(255, 0, 0, 255))

# -------------------------
# MAIN GENERATOR
# -------------------------

def generate_overlay(fit_file, output_file, width=1920, height=1080, fps=30, use_us=True):
    fonts = get_fonts(40)
    records = []
    
    print("Reading FIT data...")
    with fitdecode.FitReader(fit_file) as fit:
        for frame in fit:
            if frame.frame_type == fitdecode.FIT_FRAME_DATA and frame.name == "record":
                rec = {}
                for field in frame.fields:
                    if field.name in ['speed', 'enhanced_speed']:
                        rec[field.name] = field.raw_value
                    else:
                        rec[field.name] = field.value
                records.append(rec)

    ffmpeg_cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "-", "-c:v", "h264_nvenc", "-preset", "fast", "-b:v", "15M", output_file
    ]
    ffmpeg = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    coord_history = []
    # Smoothing buffer: 5 seconds (5 * fps frames)
    speed_buffer = deque(maxlen=int(5 * fps)) 
    total = len(records)

    for idx, rec in enumerate(records):
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # 1. Smoothing Logic
        raw_mps = get_val(rec, ["enhanced_speed", "speed"])
        speed_buffer.append(raw_mps)
        smoothed_mps = sum(speed_buffer) / len(speed_buffer)

        # 2. Data Processing
        dist_km = get_val(rec, ["distance"]) / 1000.0
        dist_display = dist_km * 0.621371 if use_us else dist_km
        alt_display = get_val(rec, ["enhanced_altitude", "altitude"]) * (3.28084 if use_us else 1.0)
        hr = get_val(rec, ["heart_rate"])

        lat, lon = rec.get("position_lat"), rec.get("position_long")
        if lat and lon: coord_history.append((lat, lon))

        # 3. Render
        draw.rectangle([0, height-130, width, height], fill=(0, 0, 0, 180)) 
        
        draw_speedometer(draw, smoothed_mps, (220, height-280), fonts, use_us)
        draw_hr_gauge(draw, hr, (60, height-380), fonts)
        draw_gps_map(draw, coord_history, (width-220, height-280))

        metrics = [
            ("Distance", f"{dist_display:.2f}", "MI" if use_us else "KM"),
            ("Altitude", f"{alt_display:.0f}", "FT" if use_us else "M"),
            ("Cadence", f"{int(get_val(rec, ['cadence']))}", "SPM"),
            ("Power", f"{int(get_val(rec, ['power']))}", "W"),
            ("Stance", f"{get_val(rec, ['stance_time']):.0f}", "MS"),
            ("Oscillation", f"{get_val(rec, ['vertical_oscillation']):.1f}", "MM")
        ]
        
        spacing = width // (len(metrics) + 1)
        for i, (label, val, unit) in enumerate(metrics):
            x = spacing * (i + 1)
            draw.text((x, height-105), label.upper(), fill=(200, 200, 200), font=fonts['tiny'], anchor="ma")
            draw.text((x, height-70), f"{val} {unit}", fill="white", font=fonts['medium'], anchor="ma")

        final_frame = Image.new("RGB", (width, height), (0, 0, 0))
        final_frame.paste(overlay, (0, 0), overlay)

        ffmpeg.stdin.write(final_frame.tobytes())
        if idx % 100 == 0:
            print(f"Progress: {idx}/{total}")

    ffmpeg.stdin.close()
    ffmpeg.wait()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--us", action="store_true")
    args = parser.parse_args()
    generate_overlay(args.fit, args.output, use_us=args.us)