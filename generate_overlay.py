import fitdecode
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import subprocess
import argparse
import os
import sys
from collections import deque
from datetime import timedelta

# -------------------------
# CONFIGURATION & ASSETS
# -------------------------
FONT_PATH = r"C:\Users\Hector\AppData\Local\Microsoft\Windows\Fonts\Montserrat-Bold.ttf"

def get_scaled_fonts(base_size):
    """Generates a dictionary of fonts scaled by a base size multiplier."""
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

def safe_get(rec, key, default=0.0):
    """Safely extracts a value from the FIT record, ensuring it's never None."""
    val = rec.get(key)
    if val is None:
        return float(default)
    try:
        return float(val)
    except (ValueError, TypeError):
        return float(default)

# -------------------------
# COMPONENT DRAWING FUNCTIONS
# -------------------------

def draw_timer(draw, elapsed_str, y_pos, scale):
    fonts = get_scaled_fonts(int(40 * scale))
    draw.text((1920//2, y_pos), elapsed_str, fill="white", font=fonts['huge'], anchor="ma")

def draw_speedometer(draw, speed_mps, pos, scale, use_us, activity_type="running"):
    fonts = get_scaled_fonts(int(40 * scale))
    x, y = pos
    rad = int(115 * scale)
    
    # Background Arc
    draw.arc([x-rad, y-rad, x+rad, y+rad], 135, 405, fill=(255, 255, 255, 50), width=int(12*scale))
    
    # Determine metrics based on activity type
    if activity_type == "swimming":
        max_speed_mps = 2.0 # Olympic pace max
        if use_us:
            total_sec = 91.44 / max(speed_mps, 0.1) # 100 Yards
            label_str = "PACE /100Y"
        else:
            total_sec = 100.0 / max(speed_mps, 0.1) # 100 Meters
            label_str = "PACE /100M"
        
        main_str = f"{int(total_sec // 60)}:{int(total_sec % 60):02d}" if speed_mps > 0.1 else "--:--"

    elif activity_type == "cycling":
        max_speed_mps = 16.0 # ~35 mph max
        if use_us:
            speed_val = speed_mps * 2.23694 # m/s to mph
            label_str = "SPEED MPH"
        else:
            speed_val = speed_mps * 3.6 # m/s to km/h
            label_str = "SPEED KM/H"
            
        main_str = f"{speed_val:.1f}" if speed_mps > 0.3 else "0.0"

    else: # Default to running
        max_speed_mps = 5.0 # ~5:20/mi max
        if use_us:
            total_sec = 1609.34 / max(speed_mps, 0.1)
            label_str = "PACE /MI"
        else:
            total_sec = 1000.0 / max(speed_mps, 0.1)
            label_str = "PACE /KM"
            
        main_str = f"{int(total_sec // 60)}:{int(total_sec % 60):02d}" if speed_mps > 0.3 else "--:--"

    # Progress Arc
    val_pc = min(max(speed_mps, 0.0) / max_speed_mps, 1.0)
    draw.arc([x-rad, y-rad, x+rad, y+rad], 135, 135 + (270 * val_pc), fill=(0, 255, 127, 255), width=int(14*scale))
    
    # Draw Text
    draw.text((x, y), main_str, fill="white", font=fonts['huge'], anchor="mm")
    draw.text((x, y + int(50*scale)), label_str, fill=(200, 200, 200), font=fonts['small'], anchor="mm")

def draw_hr_gauge(draw, hr, pos, scale):
    fonts = get_scaled_fonts(int(40 * scale))
    x, y = pos
    # Zone definitions: (Min, Max, Color)
    zones = [
        (0, 163, (150, 150, 150)), (164, 172, (0, 160, 255)), 
        (173, 182, (0, 255, 100)), (183, 192, (255, 160, 0)), (193, 197, (255, 30, 30))
    ]
    bh, sp, bw = int(45*scale), int(8*scale), int(18*scale)
    
    for i, (low, high, color) in enumerate(zones):
        alpha = 255 if low <= hr <= high else 60
        y_off = y - (i * (bh + sp))
        draw.rectangle([x, y_off, x+bw, y_off+bh], fill=(*color, alpha))
        if low <= hr <= high:
            draw.text((x + int(35*scale), y_off + bh//2), f"{int(hr)}", fill="white", font=fonts['large'], anchor="lm")

def draw_gps_map(draw, coord_history, pos, scale):
    if len(coord_history) < 2: return
    x, y = pos
    m_size = int(180 * scale)
    
    lats, lons = zip(*coord_history)
    span = max(max(lats)-min(lats), max(lons)-min(lons), 0.0001)
    
    pts = [(x + (ln - (min(lons)+max(lons))/2) / span * m_size, 
            y - (lt - (min(lats)+max(lats))/2) / span * m_size) for lt, ln in coord_history]
    
    draw.line(pts, fill=(255, 255, 255, 180), width=max(1, int(3*scale)))
    # Current Position Indicator
    draw.ellipse([pts[-1][0]-5, pts[-1][1]-5, pts[-1][0]+5, pts[-1][1]+5], fill=(255, 0, 0, 255))

def draw_metrics_grid(draw, data, selected, width=1920):
    fonts = get_scaled_fonts(40)
    active = [(k, data[k][0], data[k][1]) for k in selected if k in data]
    if not active: return
    
    spacing = width // (len(active) + 1)
    for i, (label, val, unit) in enumerate(active):
        lx = spacing * (i + 1)
        draw.text((lx, 1080-105), label.upper(), fill=(200, 200, 200), font=fonts['tiny'], anchor="ma")
        draw.text((lx, 1080-70), f"{val} {unit}", fill="white", font=fonts['medium'], anchor="ma")

# -------------------------
# MAIN GENERATOR
# -------------------------

def generate_overlay(args):
    print("Reading FIT data...")
    with fitdecode.FitReader(args.fit) as fit:
        records = [{f.name: (f.raw_value if f.name in ['speed', 'enhanced_speed'] else f.value) 
                   for f in frame.fields} for frame in fit if frame.frame_type == fitdecode.FIT_FRAME_DATA and frame.name == "record"]

    total = len(records)
    if total == 0:
        print("Error: No records found.")
        return

    # FFmpeg setup
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1920x1080", "-r", "30",
        "-i", "-", "-c:v", "h264_nvenc", "-preset", "fast", "-b:v", "15M", 
        "-pix_fmt", "yuv420p", args.output
    ]
    ffmpeg = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    coord_history = deque(maxlen=10000)
    speed_buffer = deque(maxlen=5)
    selected_metrics = [m.strip() for m in args.metrics.split(",") if m.strip()]

    print(f"Rendering {total} frames...")
    current_activity = "running" # Fallback default
    for idx, rec in enumerate(records):
        # Update activity type if it exists in this record
        if 'activity_type' in rec:
            current_activity = rec['activity_type']
            
        # Data processing with safe fallbacks
        raw_mps = safe_get(rec, 'enhanced_speed', safe_get(rec, 'speed', 0.0))
        speed_buffer.append(raw_mps)
        smoothed_mps = sum(speed_buffer) / len(speed_buffer)
        
        hr = safe_get(rec, 'heart_rate', 0.0)
        lat, lon = rec.get("position_lat"), rec.get("position_long")
        if lat is not None: 
            coord_history.append((lat, lon))

        # Canvas preparation
        overlay = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle([0, 1080-130, 1920, 1080], fill=(0, 0, 0, 180))

        # Component Drawing
        draw_timer(draw, str(timedelta(seconds=idx)), args.timer_y, args.timer_scale)
        draw_speedometer(draw, smoothed_mps, (args.pace_x, args.pace_y), args.pace_scale, args.us, current_activity)
        draw_hr_gauge(draw, hr, (args.hr_x, args.hr_y), args.hr_scale)
        draw_gps_map(draw, list(coord_history), (args.map_x, args.map_y), args.map_scale)
        
        # Grid Data Preparation
        dist_raw = safe_get(rec, 'distance', 0.0)
        alt_raw = safe_get(rec, 'altitude', safe_get(rec, 'enhanced_altitude', 0.0))
        
        m_data = {
            "Distance": (f"{(dist_raw/1000.0)*(0.621371 if args.us else 1.0):.2f}", "MI" if args.us else "KM"),
            "Altitude": (f"{alt_raw*(3.28084 if args.us else 1.0):.0f}", "FT" if args.us else "M"),
            "Cadence": (f"{int(safe_get(rec, 'cadence', 0.0))}", "SPM"),
            "Power": (f"{int(safe_get(rec, 'power', 0.0))}", "W"),
            "Stance": (f"{safe_get(rec, 'stance_time', 0.0):.0f}", "MS"),
            "Oscillation": (f"{safe_get(rec, 'vertical_oscillation', 0.0):.1f}", "MM")
        }
        draw_metrics_grid(draw, m_data, selected_metrics)

        # Output to FFmpeg
        final = Image.new("RGB", (1920, 1080), (0, 0, 0))
        final.paste(overlay, (0, 0), overlay)
        f_bytes = final.tobytes()
        
        # Write 30 frames per 1 second of FIT data to maintain sync
        for _ in range(30): 
            ffmpeg.stdin.write(f_bytes)

        # Update Progress
        if idx % 10 == 0:
            with open("progress.txt", "w") as f: 
                f.write(str(int((idx/total)*100)))

    ffmpeg.stdin.close()
    ffmpeg.wait()
    if os.path.exists("progress.txt"): 
        os.remove("progress.txt")
    print("\nRender Complete!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fit", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--us", action="store_true")
    parser.add_argument("--timer_y", type=int, default=60)
    parser.add_argument("--timer_scale", type=float, default=1.0)
    parser.add_argument("--pace_x", type=int, default=300)
    parser.add_argument("--pace_y", type=int, default=750)
    parser.add_argument("--pace_scale", type=float, default=1.0)
    parser.add_argument("--hr_x", type=int, default=80)
    parser.add_argument("--hr_y", type=int, default=650)
    parser.add_argument("--hr_scale", type=float, default=1.0)
    parser.add_argument("--map_x", type=int, default=1650)
    parser.add_argument("--map_y", type=int, default=750)
    parser.add_argument("--map_scale", type=float, default=1.0)
    parser.add_argument("--metrics", type=str, default="Distance,Altitude")
    
    generate_overlay(parser.parse_args())