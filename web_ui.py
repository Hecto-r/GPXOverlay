import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import subprocess
import os
import sys
import time

# --- CONFIG ---
FONT_PATH = r"C:\Users\Hector\AppData\Local\Microsoft\Windows\Fonts\Montserrat-Bold.ttf"

def get_p_fonts(base):
    try:
        return {
            'huge': ImageFont.truetype(FONT_PATH, int(base * 2.0)),
            'large': ImageFont.truetype(FONT_PATH, int(base * 1.4)),
            'medium': ImageFont.truetype(FONT_PATH, int(base * 0.9)),
            'tiny': ImageFont.truetype(FONT_PATH, int(base * 0.4))
        }
    except:
        return {k: ImageFont.load_default() for k in ['huge','large','medium','tiny']}

st.set_page_config(page_title="Overlay Pro", layout="wide")
st.title("🏃‍♂️ GPX Overlay Control Center")

with st.sidebar:
    st.header("1. Files & Units")
    fit_file = st.file_uploader("Upload FIT", type=["fit"])
    output_name = st.text_input("Output Name", "render.mp4")
    use_us = st.checkbox("US Units", True)
    metrics_list = ["Distance", "Altitude", "Cadence", "Power", "Stance", "Oscillation"]
    selected = st.multiselect("Visible Data", metrics_list, default=["Distance", "Altitude", "Cadence"])

st.header("2. Layout & Scale")
c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("⏱ Timer")
    t_y = st.slider("Timer Y", 0, 500, 60)
    t_s = st.slider("Timer Scale", 0.5, 3.0, 1.0)
with c2:
    st.subheader("📉 Pace Gauge")
    p_x = st.slider("Pace X", 0, 1920, 300)
    p_y = st.slider("Pace Y", 0, 1080, 750)
    p_s = st.slider("Pace Scale", 0.5, 3.0, 1.0)
with c3:
    st.subheader("❤️ HR & 🗺 Map")
    h_x = st.slider("HR X", 0, 1920, 80)
    h_y = st.slider("HR Y", 0, 1080, 650)
    h_s = st.slider("HR Scale", 0.5, 3.0, 1.0)
    st.divider()
    m_x = st.slider("Map X", 0, 1920, 1650)
    m_y = st.slider("Map Y", 0, 1080, 750)
    m_s = st.slider("Map Scale", 0.5, 3.0, 1.0)

# --- FULL PREVIEW LOGIC ---
st.header("🖼 Live Layout Preview")

def draw_mock_ui():
    img = Image.new("RGB", (1920, 1080), (30, 30, 30))
    draw = ImageDraw.Draw(img)
    
    # 1. Timer
    t_f = get_p_fonts(40 * t_s)
    draw.text((960, t_y), "00:34:01", fill="white", font=t_f['huge'], anchor="ma")

    # 2. Speedometer
    p_f = get_p_fonts(40 * p_s)
    rad = int(115 * p_s)
    draw.arc([p_x-rad, p_y-rad, p_x+rad, p_y+rad], 135, 405, fill=(100, 100, 100), width=int(12*p_s))
    draw.arc([p_x-rad, p_y-rad, p_x+rad, p_y+rad], 135, 320, fill=(0, 255, 127), width=int(14*p_s))
    draw.text((p_x, p_y), "08:45", fill="white", font=p_f['huge'], anchor="mm")
    draw.text((p_x, p_y+int(50*p_s)), "PACE /MI" if use_us else "PACE /KM", fill=(200, 200, 200), font=p_f['tiny'], anchor="mm")

    # 3. HR Gauge
    h_f = get_p_fonts(40 * h_s)
    bh, sp, bw = int(45*h_s), int(8*h_s), int(18*h_s)
    colors = [(150, 150, 150), (0, 160, 255), (0, 255, 100), (255, 160, 0), (255, 30, 30)]
    for i, color in enumerate(colors):
        alpha = 255 if i == 2 else 60
        y_off = h_y - (i * (bh + sp))
        draw.rectangle([h_x, y_off, h_x+bw, y_off+bh], fill=(*color, alpha))
        if i == 2:
            draw.text((h_x + int(35*h_s), y_off + bh//2), "171", fill="white", font=h_f['large'], anchor="lm")

    # 4. Map Area
    m_size = int(180 * m_s)
    draw.rectangle([m_x-m_size//2, m_y-m_size//2, m_x+m_size//2, m_y+m_size//2], outline=(100, 100, 100), width=2)
    draw.text((m_x, m_y), "MAP AREA", fill=(100, 100, 100), font=h_f['medium'], anchor="mm")

    # 5. Dashboard Grid
    draw.rectangle([0, 950, 1920, 1080], fill=(0, 0, 0))
    if selected:
        spacing = 1920 // (len(selected) + 1)
        m_f = get_p_fonts(40)
        for i, label in enumerate(selected):
            lx = spacing * (i + 1)
            draw.text((lx, 975), label.upper(), fill=(200, 200, 200), font=m_f['tiny'], anchor="ma")
            draw.text((lx, 1010), "123.4", fill="white", font=m_f['medium'], anchor="ma")

    return img

st.image(draw_mock_ui(), width="stretch")

# --- EXECUTION ---
if st.button("🚀 START RENDER"):
    if fit_file:
        with open("input.fit", "wb") as f: f.write(fit_file.getbuffer())
        if os.path.exists("progress.txt"): os.remove("progress.txt")
        
        cmd = [
            sys.executable, "generate_overlay.py", 
            "--fit", "input.fit", "--output", output_name,
            "--timer_y", str(t_y), "--timer_scale", str(t_s),
            "--pace_x", str(p_x), "--pace_y", str(p_y), "--pace_scale", str(p_s),
            "--hr_x", str(h_x), "--hr_y", str(h_y), "--hr_scale", str(h_s),
            "--map_x", str(m_x), "--map_y", str(m_y), "--map_scale", str(m_s),
            "--metrics", ",".join(selected)
        ]
        if use_us: cmd.append("--us")
        
        subprocess.Popen(cmd)
        
        bar = st.progress(0)
        status = st.empty()
        while True:
            if os.path.exists("progress.txt"):
                with open("progress.txt", "r") as f:
                    try:
                        p = int(f.read().strip())
                        bar.progress(p)
                        status.text(f"Rendering: {p}%")
                        if p >= 99: break
                    except: pass
            time.sleep(1)
        st.success("Finished!")