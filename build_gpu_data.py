import csv
import json
from datetime import datetime
from collections import defaultdict

# Board-partner / FE naming variants → canonical GPU name
GPU_RENAMES = {
    "RTX 5060 Ti 16GB PNY":  "RTX 5060 Ti 16GB",
    "RTX 5060 Ti 16GB Asus": "RTX 5060 Ti 16GB",
    "RTX 5070 FE":            "RTX 5070",
    "Arc B570 ASRock":        "Arc B570",
}

# Epochs with noticeably different test conditions — kept as a separate series
SEPARATE_EPOCHS = {
    "5050_1440pUltra_September 26 2025.png",
    "5050_1080pUltra_September 26 2025.png",
    "5050_4KUltra_September 26 2025.png",
}

# VRAM (GB) and PCIe slot per GPU
GPU_SPECS: dict[str, dict] = {
    # RTX 50 series
    "RTX 5090":          {"vram": 32, "pcie": "5.0×16"},
    "RTX 5080":          {"vram": 16, "pcie": "5.0×16"},
    "RTX 5070 Ti":       {"vram": 16, "pcie": "5.0×16"},
    "RTX 5070":          {"vram": 12, "pcie": "5.0×16"},
    "RTX 5060 Ti 16GB":  {"vram": 16, "pcie": "5.0×8"},
    "RTX 5060 Ti 8GB":   {"vram":  8, "pcie": "5.0×8"},
    "RTX 5060":          {"vram":  8, "pcie": "5.0×8"},
    "RTX 5050":          {"vram":  8, "pcie": "5.0×8"},
    # RTX 40 series
    "RTX 4090":          {"vram": 24, "pcie": "4.0×16"},
    "RTX 4080 Super":    {"vram": 16, "pcie": "4.0×16"},
    "RTX 4070 Ti Super": {"vram": 16, "pcie": "4.0×16"},
    "RTX 4070 Ti":       {"vram": 12, "pcie": "4.0×16"},
    "RTX 4070 Super":    {"vram": 12, "pcie": "4.0×16"},
    "RTX 4070":          {"vram": 12, "pcie": "4.0×16"},
    "RTX 4060 Ti 16GB":  {"vram": 16, "pcie": "4.0×8"},
    "RTX 4060 Ti 8GB":   {"vram":  8, "pcie": "4.0×8"},
    "RTX 4060":          {"vram":  8, "pcie": "4.0×8"},
    # RTX 30 series
    "RTX 3060 Ti":       {"vram":  8, "pcie": "4.0×16"},
    "RTX 3060 12GB":     {"vram": 12, "pcie": "4.0×16"},
    "RTX 3050":          {"vram":  8, "pcie": "4.0×8"},
    # RX 9000 series
    "RX 9070 XT":        {"vram": 16, "pcie": "5.0×16"},
    "RX 9070":           {"vram": 16, "pcie": "5.0×16"},
    "RX 9060 XT 16GB":   {"vram": 16, "pcie": "5.0×16"},
    "RX 9060 XT 8GB":    {"vram":  8, "pcie": "5.0×16"},
    # RX 7000 series
    "RX 7900 XTX":       {"vram": 24, "pcie": "4.0×16"},
    "RX 7900 XT":        {"vram": 20, "pcie": "4.0×16"},
    "RX 7800 XT":        {"vram": 16, "pcie": "4.0×16"},
    "RX 7700 XT":        {"vram": 12, "pcie": "4.0×16"},
    "RX 7600 XT":        {"vram": 16, "pcie": "4.0×8"},
    "RX 7600":           {"vram":  8, "pcie": "4.0×8"},
    "RX 6600":           {"vram":  8, "pcie": "4.0×8"},
    # Arc
    "Arc B580":          {"vram": 12, "pcie": "4.0×8"},
    "Arc B570":          {"vram": 10, "pcie": "4.0×8"},
    "Arc A770 16GB":     {"vram": 16, "pcie": "4.0×16"},
    "Arc A750":          {"vram":  8, "pcie": "4.0×16"},
}

def get_vendor(gpu):
    if any(k in gpu for k in ("RTX", "GTX", "TITAN")): return "Nvidia"
    if gpu.startswith("RX "): return "AMD"
    if "Arc" in gpu: return "Intel"
    return "Other"

def parse_resolution(res_str):
    r = res_str.strip()
    if r in ('2160p', '4K'): return '4K'
    return r

# Tom's Hardware review each benchmark image was lifted from, keyed by the
# leading token of the source-image filename (the launch the run accompanied).
GPU_SOURCES: dict[str, tuple[str, str]] = {
    "B570":       ("https://www.tomshardware.com/pc-components/gpus/intel-arc-b570-review-asrock-challenger-oc-tested",
                   "Intel Arc B570 review (ASRock Challenger OC)"),
    "5080":       ("https://www.tomshardware.com/pc-components/gpus/nvidia-geforce-rtx-5080-review",
                   "Nvidia GeForce RTX 5080 Founders Edition review"),
    "5070Ti":     ("https://www.tomshardware.com/pc-components/gpus/nvidia-geforce-rtx-5070-ti-review-asus",
                   "Nvidia GeForce RTX 5070 Ti review"),
    "5070":       ("https://www.tomshardware.com/pc-components/gpus/nvidia-geforce-rtx-5070-review-founders-edition",
                   "Nvidia GeForce RTX 5070 Founders Edition review"),
    "9070XT":     ("https://www.tomshardware.com/pc-components/gpus/amd-radeon-rx-9070-xt-review",
                   "AMD Radeon RX 9070 XT and RX 9070 review"),
    "5060Ti16GB": ("https://www.tomshardware.com/pc-components/gpus/nvidia-geforce-rtx-5060-ti-16gb-review",
                   "Nvidia GeForce RTX 5060 Ti 16GB review"),
    "9060XT16GB": ("https://www.tomshardware.com/pc-components/gpus/amd-radeon-rx-9060-xt-16gb-review",
                   "AMD Radeon RX 9060 XT 16GB review"),
    "5050":       ("https://www.tomshardware.com/pc-components/gpus/nvidia-geforce-rtx-5050-review",
                   "Nvidia GeForce RTX 5050 review"),
}

def source_for(image: str) -> tuple[str, str]:
    token = image.split("_", 1)[0]
    return GPU_SOURCES.get(token, ("", ""))

rows = []
# Track which source images belong to each resolution
res_images: dict[str, list[str]] = defaultdict(list)
image_dates: dict[str, str] = {}

with open('msfs24_gpu_data.csv', 'r') as f:
    reader = csv.DictReader(f)
    for r in reader:
        gpu_raw = r['GPU'].strip()
        gpu = GPU_RENAMES.get(gpu_raw, gpu_raw)
        resolution = parse_resolution(r['Resolution'])
        preset = r['Preset'].strip()
        source_image = r.get('SourceImage', '').strip()
        date = r['Date'].strip()

        group = source_image or date
        url, title = source_for(source_image)

        row = {
            "cpu": gpu,
            "vendor": get_vendor(gpu),
            "x3d": False,
            "avg": float(r['Avg']) if r['Avg'] else 0,
            "low": float(r['P1']) if r['P1'] and r['P1'].lower() not in ('', 'nan') else None,
            "p02": None,
            "source": group,
            "date": date,
            "site": "Tom's Hardware",
            "group": group,
            "resolution": resolution,
            "url": url,
            "title": title,
        }
        rows.append(row)

        if group not in res_images[resolution]:
            res_images[resolution].append(group)
            image_dates[group] = date

# Build 2 NormSeries per resolution: "main" (stable baseline) and "5050 era" (separate)
EPOCH_MAIN_COLOR = "#2171b5"
EPOCH_SEP_COLOR  = "#e08214"

norm = []
for resolution, images in res_images.items():
    main_images = [img for img in images if img not in SEPARATE_EPOCHS]
    sep_images  = [img for img in images if img in SEPARATE_EPOCHS]

    if main_images:
        start = min(image_dates[i] for i in main_images)
        end   = max(image_dates[i] for i in main_images)
        try:
            s = datetime.strptime(start, "%Y-%m-%d").strftime("%b %Y")
            e = datetime.strptime(end,   "%Y-%m-%d").strftime("%b %Y")
        except Exception:
            s, e = start, end
        label = s if s == e else f"{s}–{e}"
        norm.append({
            "name":       f"{resolution} Ultra · {label} (combined)",
            "color":      EPOCH_MAIN_COLOR,
            "site":       "Tom's Hardware",
            "group":      f"{resolution}-main",
            "groups":     main_images,
            "resolution": resolution,
            "span":       end,
        })

    if sep_images:
        sep_date = max(image_dates[i] for i in sep_images)
        try:
            sep_label = datetime.strptime(sep_date, "%Y-%m-%d").strftime("%b %Y")
        except Exception:
            sep_label = sep_date
        norm.append({
            "name":       f"{resolution} Ultra · {sep_label} (5050 era)",
            "color":      EPOCH_SEP_COLOR,
            "site":       "Tom's Hardware",
            "group":      f"{resolution}-5050",
            "groups":     sep_images,
            "resolution": resolution,
            "span":       sep_date,
        })

data = {
    "rows":  rows,
    "norm":  norm,
    "specs": GPU_SPECS,
}

with open('public/gpu_data.json', 'w') as f:
    json.dump(data, f)

n_eps = len(norm)
print(f"gpu_data.json created — {len(rows)} rows, {n_eps} epoch series")
