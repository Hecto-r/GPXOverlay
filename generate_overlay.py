import fitdecode
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import math
import subprocess
from datetime import datetime, timedelta
import argparse

# -------------------------
# HUD functions
# -------------------------
def draw_speedometer(draw, speed, max_speed=15, center=(300, 300), radius=100):
    # Draw circular dial
    draw.ellipse([center[0]-radius, center[1]-radius, center[0]+radius, center[1]+radius], outline="white", width=3)
    
    # Draw needle
    angle = math.radians(180 * speed / max_speed)  # semi-circle
    needle_length = radius - 10
    needle_x = center[0] + needle_length * math.cos(math.pi - angle)
    needle_y = center[1] + needle_length * math.sin(math.pi - angle)
    draw.line([center, (needle_x, needle_y)], fill="red", width=4)
    
    # Draw numeric speed
    font = ImageFont.load_default()
    draw.text((center[0]-15, center[1]-10), f"{speed:.1f}", fill="white", font=font)

def draw_hr_zone(draw, hr):
    # Zones with RGBA tuples for semi-transparent fill
    colors = {
        "blue":   (0, 0, 255, 80),
        "green":  (0, 255, 0, 80),
        "yellow": (255, 255, 0, 80),
        "orange": (255, 165, 0, 80),
        "red":    (255, 0, 0, 80)
    }

    zones = [
        (0, 120, "blue"),
        (121, 140, "green"),
        (141, 160, "yellow"),
        (161, 180, "orange"),
        (181, 220, "red")
    ]

    pos = (500, 500)  # adjust HUD position
    radius = 50        # adjust size

    for low, high, color in zones:
        if low <= hr <= high:
            fill_color = colors[color]
            draw.ellipse([pos[0]-radius, pos[1]-radius, pos[0]+radius, pos[1]+radius], fill=fill_color)
            break

# -------------------------
# Helper functions
# -------------------------
def m_to_feet(m):
    return m * 3.28084 if m is not None else 0.0

def mps_to_mph(mps):
    return mps * 2.23694 if mps is not None else 0.0

def km_to_miles(km):
    return km * 0.621371 if km is not None else 0.0

def mm_to_inches(mm):
    return mm * 0.0393701 if mm is not None else 0.0

# Format a single record in US units
def format_us(record):
    lines = []

    # Telemetry with safe fallbacks
    speed_mps = record.get("enhanced_speed") or record.get("speed") or 0.0
    distance_km = float(record.get("distance", 0.0)) / 1000.0
    altitude_m = record.get("enhanced_altitude") or record.get("altitude") or 0.0
    heart_rate = record.get("heart_rate") or 0
    cadence = record.get("cadence") or 0
    step_length_mm = record.get("step_length") or 0.0
    vertical_osc_mm = record.get("vertical_oscillation") or 0.0
    vertical_ratio = record.get("vertical_ratio") or 0.0
    power = record.get("power") or 0
    stance_time_ms = record.get("stance_time") or 0.0
    effort_pace_mps = record.get("Effort Pace") or 0.0

    # Convert to US units
    speed_mph = mps_to_mph(speed_mps)
    distance_miles = km_to_miles(distance_km)
    altitude_ft = m_to_feet(altitude_m)
    step_length_in = mm_to_inches(step_length_mm)
    vertical_osc_in = mm_to_inches(vertical_osc_mm)
    stance_time_s = stance_time_ms / 1000.0

    # Build display lines
    lines.append(f"Speed: {speed_mph:.1f} mph")
    lines.append(f"Distance: {distance_miles:.2f} mi")
    lines.append(f"Altitude: {altitude_ft:.0f} ft")
    lines.append(f"Heart Rate: {heart_rate} bpm")
    lines.append(f"Cadence: {cadence} rpm")
    lines.append(f"Step Length: {step_length_in:.1f} in")
    lines.append(f"Vertical Oscillation: {vertical_osc_in:.1f} in")
    lines.append(f"Vertical Ratio: {vertical_ratio:.1f}%")
    lines.append(f"Power: {power} W")
    lines.append(f"Stance Time: {stance_time_s:.2f} s")
    lines.append(f"Effort Pace: {mps_to_mph(effort_pace_mps):.1f} mph")

    return lines

# Format a single record in Metric units
def format_metric(record):
    lines = []

    # Telemetry with safe fallbacks
    speed_kph = (record.get("enhanced_speed") or record.get("speed") or 0.0) * 3.6  # m/s → km/h
    distance_km = float(record.get("distance", 0.0)) / 1000.0
    altitude_m = record.get("enhanced_altitude") or record.get("altitude") or 0.0
    heart_rate = record.get("heart_rate") or 0
    cadence = record.get("cadence") or 0
    step_length_mm = record.get("step_length") or 0.0
    vertical_osc_mm = record.get("vertical_oscillation") or 0.0
    vertical_ratio = record.get("vertical_ratio") or 0.0
    power = record.get("power") or 0
    stance_time_ms = record.get("stance_time") or 0.0
    effort_pace_mps = record.get("Effort Pace") or 0.0

    # Convert mm → m for step length / vertical oscillation
    step_length_m = step_length_mm / 1000.0
    vertical_osc_m = vertical_osc_mm / 1000.0
    stance_time_s = stance_time_ms / 1000.0

    # Build display lines
    lines.append(f"Speed: {speed_kph:.1f} km/h")
    lines.append(f"Distance: {distance_km:.3f} km")
    lines.append(f"Altitude: {altitude_m:.0f} m")
    lines.append(f"Heart Rate: {heart_rate} bpm")
    lines.append(f"Cadence: {cadence} rpm")
    lines.append(f"Step Length: {step_length_m:.2f} m")
    lines.append(f"Vertical Oscillation: {vertical_osc_m:.2f} m")
    lines.append(f"Vertical Ratio: {vertical_ratio:.1f}%")
    lines.append(f"Power: {power} W")
    lines.append(f"Stance Time: {stance_time_s:.2f} s")
    lines.append(f"Effort Pace: {effort_pace_mps:.2f} m/s")

    return lines

# -------------------------
# Main overlay generator
# -------------------------
def generate_overlay(fit_file, output_file, width=1920, height=1080, fps=30, use_us_units=True):
    print("Parsing FIT file...")
    records = []
    device_name = None
    start_timestamp = None
    events = []

    # --- Read FIT file ---
    with fitdecode.FitReader(fit_file) as fit:
        for frame in fit:
            if frame.frame_type != fitdecode.FIT_FRAME_DATA:
                continue

            # Telemetry records
            if frame.name == "record":
                rec = {}
                for field in frame.fields:
                    rec[field.name] = field.value
                records.append(rec)  # append every record

            # Device info
            elif frame.name == "device_info":
                for field in frame.fields:
                    if field.name == "product_name":
                        device_name = field.value
                    elif field.name == "timestamp":
                        start_timestamp = field.value

            # Event markers
            elif frame.name == "event":
                ev = {}
                for field in frame.fields:
                    ev[field.name] = field.value
                events.append(ev)

    print(f"Loaded {len(records)} records.")
    print(f"Device: {device_name}")
    print(f"Start time: {start_timestamp}")
    print(f"Events found: {len(events)}")

    # --- Prepare FFmpeg process ---
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}",
        "-r", str(fps),
        "-i", "-",
        "-an",
        "-c:v", "h264_nvenc",
        "-preset", "fast",
        "-rc", "vbr",
        "-cq", "19",
        "-b:v", "10M",
        output_file
    ]
    ffmpeg = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)

    font = ImageFont.load_default()
    total_frames = len(records)
    print(f"Generating {total_frames} frames...")

    # --- Render each record as a frame ---
    for idx, rec in enumerate(records):
        img = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        draw = ImageDraw.Draw(img, "RGBA")

        # Telemetry
        lines = format_us(rec) if use_us_units else format_metric(rec)
        for i, line in enumerate(lines):
            draw.text((50, 50 + i*25), line, font=font, fill=(255, 255, 255))
        
        # Speedometer
        speed = rec.get("enhanced_speed") or rec.get("speed") or 0.0
        if use_us_units:
            speed = mps_to_mph(speed)
        draw_speedometer(draw, speed)

        # # Heart rate zone
        hr = rec.get("heart_rate") or 0
        draw_hr_zone(draw, hr)

        # Optional overlays
        if device_name:
            draw.text((width - 400, height - 80), f"Device: {device_name}", font=font, fill=(255, 255, 0))
        if start_timestamp:
            ts_str = start_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            draw.text((width - 400, height - 50), f"Start: {ts_str}", font=font, fill=(255, 255, 0))

        # Event markers
        for ev in events:
            ev_time = ev["timestamp"]
            if rec.get("timestamp") and abs((rec.get("timestamp") - ev_time).total_seconds()) < 0.5:
                draw.text((50, 10), f"Event: {ev['event']} ({ev['event_type']})", font=font, fill=(255, 0, 0))

        img_rgb = img.convert("RGB")  # flatten alpha
        ffmpeg.stdin.write(img_rgb.tobytes())

        if idx % 100 == 0:
            print(f"Rendered {idx}/{total_frames}")

    ffmpeg.stdin.close()
    ffmpeg.wait()
    print("Overlay video generated.")

# -------------------------
# Command-line entry
# -------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fit", required=True, help="Input FIT file")
    parser.add_argument("--output", required=True, help="Output video file")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--us_units", action="store_true", help="Use US units (mph, mi, ft)")
    args = parser.parse_args()

    generate_overlay(
        fit_file=args.fit,
        output_file=args.output,
        width=args.width,
        height=args.height,
        fps=args.fps,
        use_us_units=args.us_units
    )