import os
import sys
import json
import uuid
import re
import subprocess
import threading
import webbrowser
import shutil
import traceback
import base64
import io
import math
import zipfile
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def _get_short_path(path):
    """获取 Windows 短路径（8.3），避免 bat 中中文路径在 cmd 下乱码"""
    if sys.platform != 'win32':
        return str(path)
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(500)
        r = ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, 500)
        if r and 0 < r < 500:
            return buf.value
    except Exception:
        pass
    return str(path)


# ━━━ Windows 控制台编码修复 ━━━
if sys.platform == 'win32':
    # 设置控制台代码页为 UTF-8
    try:
        os.system('chcp 65001 >nul 2>&1')
    except Exception:
        pass
    # 强制 Python I/O 使用 UTF-8
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass
    if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
        try:
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass


def _fatal_error(msg):
    """致命错误：写入日志文件并暂停，防止窗口闪退"""
    err_file = Path(sys.executable).parent / 'error.log' if getattr(sys, 'frozen', False) \
        else Path(__file__).parent / 'error.log'
    try:
        err_file.write_text(msg, encoding='utf-8')
    except Exception:
        pass
    print(f"\n[ERROR] {msg}\n")
    if getattr(sys, 'frozen', False):
        input("按回车键退出...")
    sys.exit(1)


# ━━━ 安全导入依赖 ━━━
try:
    from flask import Flask, request, jsonify, render_template, send_from_directory, Response
except ImportError:
    _fatal_error("缺少 Flask 库。请检查打包是否完整。")

try:
    import imageio_ffmpeg
except ImportError:
    _fatal_error("缺少 imageio_ffmpeg 库。请检查打包是否完整。")

# 可选依赖
try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PyInstaller 兼容支持：区分执行模式和开发模式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try:
    if getattr(sys, 'frozen', False):
        _BUNDLE_DIR = Path(sys._MEIPASS)
        BASE_DIR = Path(sys.executable).parent
        app = Flask(__name__,
                    template_folder=str(_BUNDLE_DIR / 'templates'),
                    static_folder=str(_BUNDLE_DIR / 'static'))
    else:
        BASE_DIR = Path(__file__).parent.resolve()
        app = Flask(__name__)
except Exception as e:
    _fatal_error(f"Flask 初始化失败:\n{traceback.format_exc()}")

UPLOAD_DIR = BASE_DIR / "uploads"
RENAME_UPLOAD_DIR = BASE_DIR / "uploads_rename"
UPLOAD_DIR_EDITOR = BASE_DIR / "uploads_editor"
TEMPLATE_DIR = BASE_DIR / "uploads" / "templates"
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR.mkdir(exist_ok=True)
RENAME_UPLOAD_DIR.mkdir(exist_ok=True)
UPLOAD_DIR_EDITOR.mkdir(exist_ok=True)
TEMPLATE_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024 * 1024  # 4GB
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # 禁用静态文件缓存

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 动态配置 — config.json
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIG_PATH = BASE_DIR / 'config.json'

DEFAULT_CREATORS = [
    {'label': '钟海明', 'value': 'ZHM'},
    {'label': '杨懿', 'value': 'YY'},
    {'label': '赵晟悦', 'value': 'ZSY'},
    {'label': '高娇阳', 'value': 'GJY'},
    {'label': '杨皓然', 'value': 'YHR'},
    {'label': '盛妍', 'value': 'SY'},
    {'label': '董慧媛', 'value': 'DHY'},
    {'label': '常广瑜', 'value': 'CGY'},
    {'label': '乔翾宇', 'value': 'QXY'},
    {'label': '崔佳仪', 'value': 'CJY'},
    {'label': '王仲茨', 'value': 'WZC'},
    {'label': '任智斌', 'value': 'RZB'},
    {'label': '刘阳', 'value': 'LY'},
    {'label': '李文迪', 'value': 'LWD'},
]

DEFAULT_CONFIG = {
    'creators': DEFAULT_CREATORS,
    'defaultRegion': 'JP',
    'defaultPlatform': 'GG',
    'defaultCreator': 'ZHM',
}


def load_config():
    """从 config.json 加载配置，合并默认值"""
    config = dict(DEFAULT_CONFIG)
    config['creators'] = [dict(c) for c in DEFAULT_CREATORS]
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                saved = json.load(f)
            if 'creators' in saved and isinstance(saved['creators'], list):
                config['creators'] = saved['creators']
            if 'defaultRegion' in saved:
                config['defaultRegion'] = saved['defaultRegion']
            if 'defaultPlatform' in saved:
                config['defaultPlatform'] = saved['defaultPlatform']
            if 'defaultCreator' in saved:
                config['defaultCreator'] = saved['defaultCreator']
        except Exception as e:
            print(f"  [Config] Failed to load config.json: {e}")
    return config


def save_config(config):
    """保存配置到 config.json"""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def sync_known_creators():
    """从 config 同步 KNOWN_CREATORS 集合，用于文件名解析"""
    global KNOWN_CREATORS
    cfg = load_config()
    KNOWN_CREATORS = {c['value'] for c in cfg.get('creators', []) if c.get('value')}


# 启动时同步
sync_known_creators()


# ━━━ 版本号（用于缓存失效） ━━━
APP_VERSION = '2.6.0'


@app.after_request
def add_no_cache_headers(response):
    """所有响应禁止浏览器缓存，确保每次加载最新版本"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# imageio-ffmpeg 可能不含 ffprobe，尝试查找
_ffprobe_candidate = os.path.join(os.path.dirname(FFMPEG_PATH),
    "ffprobe" + (".exe" if sys.platform == "win32" else ""))
FFPROBE_PATH = _ffprobe_candidate if os.path.exists(_ffprobe_candidate) else None

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 通用常量
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RATIO_LABELS = {"9:16": "竖", "1:1": "方", "16:9": "横"}
LABEL_TO_RATIO = {"竖": "9:16", "方": "1:1", "横": "16:9"}
BLUR_SIGMA = 50

VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm', '.m4v', '.mpg', '.mpeg'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
MEDIA_EXTENSIONS = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS

# 全局进度追踪
progress_store = {}

# 抑制 Windows 子进程控制台窗口
_subprocess_kwargs = {}
if sys.platform == 'win32':
    _subprocess_kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 配置文件管理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIG_FILE = BASE_DIR / "config.json"


def load_config():
    """加载配置文件"""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def save_config_file(config):
    """保存配置文件"""
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 视频/图片信息获取
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def get_video_info(filepath):
    """使用 ffprobe 或 ffmpeg 回退获取视频宽高和时长"""
    if FFPROBE_PATH:
        cmd = [
            FFPROBE_PATH, '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams', '-show_format',
            str(filepath)
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    encoding='utf-8', errors='replace',
                                    timeout=30, **_subprocess_kwargs)
            data = json.loads(result.stdout)
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    w = int(stream['width'])
                    h = int(stream['height'])
                    duration = float(stream.get('duration', 0))
                    if duration == 0:
                        duration = float(data.get('format', {}).get('duration', 0))
                    return {'width': w, 'height': h, 'duration': duration}
        except Exception:
            pass

    # 回退：解析 ffmpeg -i 的 stderr 输出
    cmd = [FFMPEG_PATH, '-i', str(filepath)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace',
                                timeout=30, **_subprocess_kwargs)
        stderr = result.stderr
        match = re.search(r'Stream.*Video.*?(\d{2,5})x(\d{2,5})', stderr)
        if match:
            w, h = int(match.group(1)), int(match.group(2))
            dur_match = re.search(r'Duration:\s*(\d+):(\d+):(\d+\.\d+)', stderr)
            duration = 0
            if dur_match:
                hh, mm, ss = dur_match.groups()
                duration = int(hh) * 3600 + int(mm) * 60 + float(ss)
            return {'width': w, 'height': h, 'duration': duration}
    except Exception:
        pass

    return None


def get_image_info(filepath):
    """使用 Pillow 获取图片宽高"""
    if HAS_PIL:
        try:
            with PILImage.open(filepath) as img:
                return {'width': img.width, 'height': img.height}
        except Exception:
            pass
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 比例转换工具 - 核心逻辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def classify_ratio(width, height):
    """将视频分类到最接近的标准比例"""
    ratio = width / height
    diffs = {
        "16:9": abs(ratio - 16 / 9),
        "1:1": abs(ratio - 1.0),
        "9:16": abs(ratio - 9 / 16),
    }
    return min(diffs, key=diffs.get)


# 固定输出三种标准尺寸，规避原视频尺寸不符合标准的情况
STANDARD_RATIOS = ["9:16", "1:1", "16:9"]


def get_target_ratios(_current_ratio=None):
    """始终返回全部三种比例，使每个视频都输出：原比例标准尺寸 + 另外两种标准尺寸，共 3 个视频"""
    return list(STANDARD_RATIOS)


def make_even(n):
    """确保数字为偶数（FFmpeg 要求）"""
    return n if n % 2 == 0 else n + 1


def calculate_output_dimensions(orig_w, orig_h, target_ratio):
    """固定输出尺寸：横 1920x1080，方 1080x1080，竖 1080x1920"""
    if target_ratio == "16:9":
        w, h = 1920, 1080
    elif target_ratio == "9:16":
        w, h = 1080, 1920
    else:  # 1:1
        w = h = 1080
    return make_even(w), make_even(h)


def generate_output_filename(original_name, target_ratio):
    """生成输出文件名，替换比例标签"""
    name_part = Path(original_name).stem
    ext = Path(original_name).suffix
    target_label = RATIO_LABELS[target_ratio]

    found_label = None
    for label in LABEL_TO_RATIO:
        if label in name_part:
            found_label = label
            break

    if found_label:
        new_name = name_part.replace(found_label, target_label)
    else:
        new_name = f"{name_part}_{target_label}"

    return f"{new_name}{ext}"


def process_video(input_path, target_ratio, output_path):
    """处理单个视频到目标比例（模糊背景）"""
    info = get_video_info(input_path)
    if not info:
        raise ValueError(f"无法读取视频信息: {input_path}")

    orig_w, orig_h = info['width'], info['height']
    out_w, out_h = calculate_output_dimensions(orig_w, orig_h, target_ratio)

    filter_complex = (
        f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
        f"crop={out_w}:{out_h},gblur=sigma={BLUR_SIGMA}[bg];"
        f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2[out]"
    )

    cmd = [
        FFMPEG_PATH, '-y', '-i', str(input_path),
        '-filter_complex', filter_complex,
        '-map', '[out]', '-map', '0:a?',
        '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
        '-c:a', 'copy',
        '-movflags', '+faststart',
        str(output_path)
    ]

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding='utf-8', errors='replace',
        **_subprocess_kwargs
    )
    _, stderr = process.communicate()

    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg 错误: {stderr}")

    return output_path


def detect_transparent_region(template_path, threshold=10, col_row_pct=0.5):
    """检测 PNG 套版的透明区域（视频放置位置）

    逻辑：逐列/逐行统计透明像素占比，>50% 透明的列/行才算"透明"，
    取这些列/行的连续范围作为透明区域。
    避免零星透明像素（圆角、抗锯齿）把检测范围拉到整张图。

    返回: {x, y, width, height, template_width, template_height}
    """
    if not HAS_PIL:
        raise RuntimeError("需要 Pillow 库来检测套版透明区域")

    img = PILImage.open(template_path).convert('RGBA')
    alpha = img.split()[3]  # Alpha 通道
    w, h = img.size

    # 逐列统计：该列中透明像素(alpha < threshold)占比 > col_row_pct 才算透明列
    transparent_cols = []
    for col in range(w):
        count = sum(1 for row in range(h) if alpha.getpixel((col, row)) < threshold)
        if count / h >= col_row_pct:
            transparent_cols.append(col)

    # 逐行统计：该行中透明像素占比 > col_row_pct 才算透明行
    transparent_rows = []
    for row in range(h):
        count = sum(1 for col in range(w) if alpha.getpixel((col, row)) < threshold)
        if count / w >= col_row_pct:
            transparent_rows.append(row)

    if not transparent_cols or not transparent_rows:
        # 统计法没结果，回退到 getbbox 兜底
        mask = alpha.point(lambda x: 255 if x < 128 else 0)
        bbox = mask.getbbox()
        if not bbox:
            return None
        region = {
            'x': bbox[0], 'y': bbox[1],
            'width': bbox[2] - bbox[0], 'height': bbox[3] - bbox[1],
            'template_width': w, 'template_height': h
        }
        print(f"  [Template] Fallback bbox: ({region['x']},{region['y']}) "
              f"{region['width']}x{region['height']} in {w}x{h}")
        return region

    # 取透明列/行的最小~最大范围
    x1 = min(transparent_cols)
    x2 = max(transparent_cols) + 1  # 不含右边界
    y1 = min(transparent_rows)
    y2 = max(transparent_rows) + 1

    region = {
        'x': x1,
        'y': y1,
        'width': x2 - x1,
        'height': y2 - y1,
        'template_width': w,
        'template_height': h
    }

    print(f"  [Template] Detected transparent region: "
          f"({region['x']},{region['y']}) {region['width']}x{region['height']} "
          f"in {w}x{h} template "
          f"(cols: {len(transparent_cols)}/{w}, rows: {len(transparent_rows)}/{h})")

    return region


def process_video_with_template(input_path, template_path, region, output_path,
                                target_ratio=None):
    """使用套版合成视频

    核心逻辑（与 process_video 保持一致的缩放）：
      1. 输出分辨率 = 根据视频尺寸 + 目标比例计算（和无套版时完全一样）
      2. 视频缩放 = 和 process_video 完全一样（fit 在画布内，不放大）
      3. 位置 = 视频居中对齐到套版的透明区域（而非画布居中）
      4. 套版 PNG 缩放到输出尺寸，叠在最上层

    合成层次：
      底层: 黑色画布 (输出尺寸，和无套版时一致)
      中层: 源视频 (原始缩放，对齐透明区域)
      顶层: 套版 PNG (缩放至输出尺寸)
    """
    info = get_video_info(input_path)
    if not info:
        raise ValueError(f"无法读取视频信息: {input_path}")

    vid_w, vid_h = info['width'], info['height']

    # ━━━ 第1步：输出画布尺寸由视频决定（和 process_video 一致）━━━
    if target_ratio:
        out_w, out_h = calculate_output_dimensions(vid_w, vid_h, target_ratio)
    else:
        out_w, out_h = make_even(vid_w), make_even(vid_h)

    # ━━━ 第2步：视频缩放 — 和 process_video 完全一样 ━━━
    # process_video 用: scale=min(out_w,iw):min(out_h,ih):force_original_aspect_ratio=decrease
    # 等价于: fit 在画布内，不放大，保持比例
    vid_scale = min(out_w / vid_w, out_h / vid_h, 1.0)  # 不超过1.0=不放大
    scaled_vid_w = make_even(max(2, round(vid_w * vid_scale)))
    scaled_vid_h = make_even(max(2, round(vid_h * vid_scale)))

    # ━━━ 第3步：计算透明区域在输出坐标系中的中心位置 ━━━
    tpl_orig_w = int(region['template_width'])
    tpl_orig_h = int(region['template_height'])
    scale_x = out_w / tpl_orig_w
    scale_y = out_h / tpl_orig_h

    # 透明区域等比缩放到输出坐标系
    rx = int(region['x'] * scale_x)
    ry = int(region['y'] * scale_y)
    rw = math.ceil(region['width'] * scale_x)
    rh = math.ceil(region['height'] * scale_y)

    # 透明区域的中心点
    region_cx = rx + rw // 2
    region_cy = ry + rh // 2

    # ━━━ 第4步：视频对齐到透明区域中心（而非画布居中）━━━
    offset_x = region_cx - scaled_vid_w // 2
    offset_y = region_cy - scaled_vid_h // 2

    print(f"  [Template] Source video: {vid_w}x{vid_h}")
    print(f"  [Template] Output canvas: {out_w}x{out_h} (target_ratio={target_ratio})")
    print(f"  [Template] Video (same as blur mode): {scaled_vid_w}x{scaled_vid_h}")
    print(f"  [Template] Template orig: {tpl_orig_w}x{tpl_orig_h}")
    print(f"  [Template] Transparent region (scaled): ({rx},{ry}) {rw}x{rh}, "
          f"center=({region_cx},{region_cy})")
    print(f"  [Template] Video position: ({offset_x},{offset_y})")
    print(f"  [Template] Compare: blur mode would be "
          f"({(out_w-scaled_vid_w)//2},{(out_h-scaled_vid_h)//2})")

    # FFmpeg 滤镜：
    #   1. 视频缩放 — 和 process_video 一样的逻辑
    #   2. 黑色画布
    #   3. 视频放到透明区域中心位置
    #   4. 套版缩放到画布大小，叠在最上层
    filter_complex = (
        f"[0:v]scale='min({out_w},iw)':'min({out_h},ih)'"
        f":force_original_aspect_ratio=decrease[vid];"
        f"color=c=black:s={out_w}x{out_h}[base];"
        f"[base][vid]overlay={offset_x}:{offset_y}:shortest=1[withvid];"
        f"[1:v]scale={out_w}:{out_h}[tpl];"
        f"[withvid][tpl]overlay=0:0:format=auto:shortest=1[out]"
    )

    cmd = [
        FFMPEG_PATH, '-y',
        '-i', str(input_path),
        '-loop', '1', '-i', str(template_path),
        '-filter_complex', filter_complex,
        '-map', '[out]', '-map', '0:a?',
        '-c:v', 'libx264', '-crf', '18', '-preset', 'medium',
        '-c:a', 'copy',
        '-movflags', '+faststart',
        '-shortest',
        str(output_path)
    ]

    print(f"  [Template] FFmpeg filter: {filter_complex}")

    process = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding='utf-8', errors='replace',
        **_subprocess_kwargs
    )
    _, stderr = process.communicate()

    if process.returncode != 0:
        print(f"  [Template] FFmpeg FAILED: {stderr[:500]}")
        raise RuntimeError(f"FFmpeg 错误: {stderr}")

    print(f"  [Template] Success!")
    return output_path


def process_task(task_id, files_info, output_dir=None, templates=None):
    """后台任务：处理所有上传的视频（支持套版合成）
    templates: dict, 格式 {"9:16": {"path": "...", "region": {...}}, ...}
    """
    if templates is None:
        templates = {}

    actual_output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    actual_output_dir.mkdir(parents=True, exist_ok=True)

    total_jobs = sum(len(f['targets']) for f in files_info)
    completed = 0
    progress_store[task_id] = {
        'status': 'processing',
        'total': total_jobs,
        'completed': 0,
        'current_file': '',
        'results': [],
        'errors': [],
        'output_dir': str(actual_output_dir)
    }

    for file_info in files_info:
        input_path = Path(file_info['path'])
        original_name = file_info['original_name']

        for target_ratio in file_info['targets']:
            output_name = generate_output_filename(original_name, target_ratio)
            output_path = actual_output_dir / output_name

            counter = 1
            while output_path.exists():
                stem = Path(output_name).stem
                ext = Path(output_name).suffix
                output_path = actual_output_dir / f"{stem}_{counter}{ext}"
                counter += 1

            # 判断是否有对应比例的套版
            tpl = templates.get(target_ratio)
            mode_label = "套版" if tpl else "模糊"
            print(f"  [{mode_label}] {original_name} -> {target_ratio}, tpl={'YES path=' + tpl['path'] if tpl else 'NO'}")
            progress_store[task_id]['current_file'] = (
                f"{original_name} → {RATIO_LABELS[target_ratio]}（{mode_label}）"
            )

            try:
                if tpl and tpl.get('path') and tpl.get('region'):
                    # 使用套版合成
                    process_video_with_template(
                        input_path, tpl['path'], tpl['region'], output_path,
                        target_ratio=target_ratio
                    )
                else:
                    # 使用模糊背景
                    process_video(input_path, target_ratio, output_path)

                progress_store[task_id]['results'].append({
                    'filename': output_path.name,
                    'ratio': target_ratio,
                    'label': RATIO_LABELS[target_ratio]
                })
            except Exception as e:
                progress_store[task_id]['errors'].append({
                    'filename': original_name,
                    'target': target_ratio,
                    'error': str(e)
                })

            completed += 1
            progress_store[task_id]['completed'] = completed

    # 清理上传的临时视频文件
    for file_info in files_info:
        try:
            os.remove(file_info['path'])
        except OSError:
            pass

    # 清理临时套版文件
    for tpl in templates.values():
        try:
            tpl_path = tpl.get('path', '')
            if tpl_path and os.path.exists(tpl_path):
                os.remove(tpl_path)
        except OSError:
            pass

    progress_store[task_id]['status'] = 'done'
    progress_store[task_id]['current_file'] = ''


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 重命名工具 - 核心逻辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def classify_ratio_rename(w, h):
    """重命名工具的比例判定逻辑（按 PRD 规则）"""
    if w <= 0 or h <= 0:
        return '横'
    if abs(w - h) / max(w, h) < 0.1:
        return '方'
    elif h > w:
        return '竖'
    else:
        return '横'


# 重命名工具 - 本地文件名规则解析器
# 已知的业务标签集合
KNOWN_REGIONS = {'JP', 'TC', 'EN', 'TH', 'KR', 'VN', 'ID', 'ES'}
KNOWN_PLATFORMS = {'FB', 'GG', 'TT'}
KNOWN_CREATORS = {'ZHM', 'YY', 'ZSY', 'GJY', 'YHR', 'SY', 'DHY', 'CGY', 'QXY', 'CJY', 'WZC', 'RZB', 'LY', 'LWD'}
KNOWN_PROPERTIES = {'原创', '迭代', '竞品二创'}
KNOWN_AUDIENCES = {'男性向', '女性向'}
KNOWN_RATIOS = {'竖', '方', '横'}


def _is_noise_word(word):
    """判断一个词是否为干扰信息（日期/数字/哈希/已知代码等）"""
    w = word.strip()
    if not w:
        return True
    w_upper = w.upper()
    # 纯数字（日期片段、编号等）
    if re.match(r'^\d+$', w):
        return True
    # 版本后缀 1_2, 1_3 等
    if re.match(r'^\d+_\d+$', w):
        return True
    # 十六进制哈希（≥8位连续 hex 字符）
    if re.match(r'^[0-9a-fA-F]{8,}$', w):
        return True
    # 已知地区/平台/制作人代码
    if w_upper in KNOWN_REGIONS or w_upper in KNOWN_PLATFORMS or w_upper in KNOWN_CREATORS:
        return True
    # 比例/属性/受众标记
    if w in KNOWN_RATIOS or w in KNOWN_PROPERTIES or w in KNOWN_AUDIENCES:
        return True
    return False


def parse_filename_local(filename):
    """
    本地规则解析器：从文件名中提取已知字段，剩余部分作为核心词。
    命名规范: {日期}-{地区}-{属性}-{受众}-{核心词}-{平台}-{制作人}-{比例}-{版本}
    核心词限制: 最多 10 个字符
    """
    stem = Path(filename).stem
    parts = stem.split('-')

    result = {
        'date': '',
        'region': '',
        'property': '',
        'audience': '',
        'assetName': '',
        'platform': '',
        'creator': '',
        'ratio': '',
        'version': '1',
    }

    remaining = []

    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        upper = stripped.upper()

        # 6位日期 (YYMMDD)
        if re.match(r'^\d{6}$', stripped) and not result['date']:
            result['date'] = stripped
        # 地区代码（整段精确匹配）
        elif upper in KNOWN_REGIONS and not result['region']:
            result['region'] = upper
        # 平台代码（整段精确匹配）
        elif upper in KNOWN_PLATFORMS and not result['platform']:
            result['platform'] = upper
        # 制作人缩写（整段精确匹配）
        elif upper in KNOWN_CREATORS and not result['creator']:
            result['creator'] = upper
        # 属性标记
        elif stripped in KNOWN_PROPERTIES and not result['property']:
            result['property'] = stripped
        # 受众标记
        elif stripped in KNOWN_AUDIENCES and not result['audience']:
            result['audience'] = stripped
        # 比例标记
        elif stripped in KNOWN_RATIOS and not result['ratio']:
            result['ratio'] = stripped
        # 纯数字 1-2 位，暂存（最后判断是否为版本号）
        elif re.match(r'^\d{1,2}$', stripped):
            remaining.append(stripped)
        else:
            remaining.append(stripped)

    # 最后一个纯数字片段当作版本号
    if remaining and re.match(r'^\d{1,2}$', remaining[-1]):
        result['version'] = remaining.pop()

    # ── 清洗核心词：对复合段落逐词过滤干扰信息 ──
    cleaned_words = []
    for part in remaining:
        # 对含空格的复合段落，拆分后逐词检查
        words = part.split()
        for word in words:
            if not _is_noise_word(word):
                cleaned_words.append(word)

    asset_name = ' '.join(cleaned_words).strip()

    # 核心词上限 10 个字符，截断时不切断单词
    if len(asset_name) > 10:
        truncated = asset_name[:10]
        # 如果截断点在单词中间，回退到上一个空格
        if len(asset_name) > 10 and asset_name[10] != ' ' and ' ' in truncated:
            truncated = truncated[:truncated.rfind(' ')]
        asset_name = truncated.strip()

    result['assetName'] = asset_name
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 视频编辑 - 导出最后一帧
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def extract_last_frame(video_path, output_path):
    """用 ffmpeg 导出视频最后一帧为 PNG，返回 True 成功"""
    cmd = [
        FFMPEG_PATH, '-y',
        '-sseof', '-0.04', '-i', str(video_path),
        '-vframes', '1', '-update', '1',
        str(output_path)
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            timeout=60, **_subprocess_kwargs
        )
        return result.returncode == 0 and Path(output_path).exists()
    except Exception:
        return False


def _copy_image_to_clipboard_win(image_path):
    """Windows：将图片文件放入剪贴板（DIB 格式），成功返回 True"""
    if sys.platform != 'win32' or not HAS_PIL:
        return False
    try:
        with PILImage.open(image_path) as img:
            img = img.convert('RGB')
        w, h = img.size
        # DIB：BITMAPINFOHEADER 40 字节 + BGR 自底向上，每行 4 字节对齐
        stride = ((w * 3 + 3) // 4) * 4
        raw_size = 40 + stride * h
        buf = bytearray(raw_size)
        # BITMAPINFOHEADER
        buf[0:4] = (40).to_bytes(4, 'little')   # biSize
        buf[4:8] = w.to_bytes(4, 'little')      # biWidth
        buf[8:12] = (-h).to_bytes(4, 'little', signed=True)  # biHeight (负=自顶向下，避免上下颠倒)
        buf[12:14] = (1).to_bytes(2, 'little')  # biPlanes
        buf[14:16] = (24).to_bytes(2, 'little') # biBitCount
        buf[16:20] = (0).to_bytes(4, 'little')  # biCompression = BI_RGB
        pixels = img.tobytes()
        # PIL RGB 转 BGR，并按 stride 每行 4 字节对齐
        off = 40
        for y in range(h):
            row = pixels[y * w * 3:(y + 1) * w * 3]
            for x in range(w):
                buf[off] = row[x * 3 + 2]
                buf[off + 1] = row[x * 3 + 1]
                buf[off + 2] = row[x * 3]
                off += 3
            off += stride - w * 3
        ctypes = __import__('ctypes')
        ctypes.windll.user32.OpenClipboard(0)
        ctypes.windll.user32.EmptyClipboard()
        CF_DIB = 8
        GMEM_MOVEABLE = 0x0002
        hmem = ctypes.windll.kernel32.GlobalAlloc(GMEM_MOVEABLE, len(buf))
        if not hmem:
            ctypes.windll.user32.CloseClipboard()
            return False
        ptr = ctypes.windll.kernel32.GlobalLock(hmem)
        if ptr:
            src = (ctypes.c_char * len(buf)).from_buffer_copy(bytes(buf))
            ctypes.windll.kernel32.RtlMoveMemory(ptr, src, len(buf))
            ctypes.windll.kernel32.GlobalUnlock(hmem)
        ctypes.windll.user32.SetClipboardData(CF_DIB, hmem)
        ctypes.windll.user32.CloseClipboard()
        return True
    except Exception:
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Flask 路由 - 比例转换工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.route('/')
def index():
    return render_template('index.html', active_tab='converter')


@app.route('/rename')
def rename_redirect():
    return render_template('index.html', active_tab='rename')


@app.route('/editor')
def editor_redirect():
    return render_template('index.html', active_tab='editor')


@app.route('/settings')
def settings_redirect():
    return render_template('index.html', active_tab='settings')


@app.route('/upload', methods=['POST'])
def upload():
    """处理视频文件上传，返回文件信息和检测到的比例"""
    if 'files' not in request.files:
        return jsonify({'error': '没有选择文件'}), 400

    uploaded = []
    files = request.files.getlist('files')

    for f in files:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in VIDEO_EXTENSIONS:
            continue

        file_id = str(uuid.uuid4())
        safe_name = f"{file_id}{ext}"
        save_path = UPLOAD_DIR / safe_name
        f.save(str(save_path))

        info = get_video_info(save_path)
        if info is None:
            os.remove(save_path)
            continue

        ratio = classify_ratio(info['width'], info['height'])
        targets = get_target_ratios(ratio)

        uploaded.append({
            'file_id': file_id,
            'original_name': f.filename,
            'path': str(save_path),
            'width': info['width'],
            'height': info['height'],
            'ratio': ratio,
            'ratio_label': RATIO_LABELS[ratio],
            'targets': targets,
            'target_labels': [RATIO_LABELS[t] for t in targets]
        })

    return jsonify({'files': uploaded})


@app.route('/upload-template', methods=['POST'])
def upload_template():
    """上传套版 PNG，检测透明区域，返回区域信息和缩略图预览"""
    if 'file' not in request.files:
        return jsonify({'error': '没有选择文件'}), 400

    f = request.files['file']
    ratio_label = request.form.get('ratio', '')

    if not f.filename:
        return jsonify({'error': '文件名为空'}), 400

    ext = Path(f.filename).suffix.lower()
    if ext != '.png':
        return jsonify({'error': '套版必须是 PNG 格式（需要透明通道）'}), 400

    # 保存套版文件
    template_id = str(uuid.uuid4())
    save_path = TEMPLATE_DIR / f"template_{template_id}.png"
    f.save(str(save_path))

    # 检测透明区域
    try:
        region = detect_transparent_region(str(save_path))
    except Exception as e:
        save_path.unlink(missing_ok=True)
        return jsonify({'error': f'检测透明区域失败: {str(e)}'}), 400

    if not region:
        save_path.unlink(missing_ok=True)
        return jsonify({'error': '未在套版中检测到透明区域，请确保 PNG 包含透明（alpha=0）区域'}), 400

    # 生成缩略图 base64 供前端预览
    thumb_b64 = ''
    try:
        with PILImage.open(save_path) as img:
            thumb = img.copy()
            thumb.thumbnail((300, 300))
            buf = io.BytesIO()
            thumb.save(buf, format='PNG')
            thumb_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
    except Exception:
        pass

    return jsonify({
        'template_id': template_id,
        'path': str(save_path),
        'region': region,
        'thumbnail': f'data:image/png;base64,{thumb_b64}' if thumb_b64 else '',
        'ratio_label': ratio_label
    })


@app.route('/remove-template', methods=['POST'])
def remove_template():
    """移除已上传的套版文件"""
    data = request.get_json()
    tpl_path = data.get('path', '')
    if tpl_path:
        try:
            Path(tpl_path).unlink(missing_ok=True)
        except Exception:
            pass
    return jsonify({'ok': True})


@app.route('/process', methods=['POST'])
def process():
    """开始处理上传的视频（支持套版合成）"""
    data = request.get_json()
    files_info = data.get('files', [])
    custom_output_dir = data.get('output_dir', '').strip()
    raw_templates = data.get('templates', {})

    if not files_info:
        return jsonify({'error': '没有文件需要处理'}), 400

    if custom_output_dir:
        target_dir = Path(custom_output_dir)
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return jsonify({'error': f'无法创建输出目录: {custom_output_dir}'}), 400
    else:
        target_dir = OUTPUT_DIR

    # 将前端传来的 label-key 套版映射转换为 ratio-key 格式
    # 前端发送 {"竖": {...}, "方": {...}, "横": {...}}
    # 后端需要 {"9:16": {...}, "1:1": {...}, "16:9": {...}}
    templates = {}
    for label, tpl_data in raw_templates.items():
        ratio_key = LABEL_TO_RATIO.get(label, '')
        if ratio_key and tpl_data:
            templates[ratio_key] = tpl_data

    task_id = str(uuid.uuid4())
    thread = threading.Thread(
        target=process_task,
        args=(task_id, files_info, str(target_dir)),
        kwargs={'templates': templates}
    )
    thread.daemon = True
    thread.start()

    return jsonify({'task_id': task_id, 'output_dir': str(target_dir)})


@app.route('/progress/<task_id>')
def progress(task_id):
    """SSE 端点：处理进度推送"""
    def generate():
        import time
        while True:
            info = progress_store.get(task_id)
            if info is None:
                yield f"data: {json.dumps({'error': '任务不存在'})}\n\n"
                break
            yield f"data: {json.dumps(info, ensure_ascii=False)}\n\n"
            if info['status'] == 'done':
                break
            time.sleep(0.5)

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/download/<filename>')
def download(filename):
    """下载处理后的视频文件"""
    return send_from_directory(str(OUTPUT_DIR), filename, as_attachment=True)


@app.route('/output-files')
def output_files():
    """列出输出目录中的所有文件"""
    files = []
    for f in sorted(OUTPUT_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS:
            files.append({
                'filename': f.name,
                'size': f.stat().st_size
            })
    return jsonify({'files': files})


@app.route('/browse-folder', methods=['POST'])
def browse_folder():
    """打开系统文件夹选择对话框"""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        folder = filedialog.askdirectory(title='选择输出目录')
        root.destroy()
        if folder:
            return jsonify({'path': folder})
        return jsonify({'path': ''})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _open_folder_foreground(folder_path):
    """在系统文件管理器中打开文件夹，并尽量使窗口置前显示（Windows 下直接显示在桌面最前）"""
    target = Path(folder_path)
    if not target.exists():
        return False
    path_str = str(target.resolve())
    if sys.platform == 'win32':
        # 先打开文件夹
        subprocess.Popen(['explorer', path_str])
        # 延迟后查找 Explorer 窗口并置前
        def _bring_explorer_front():
            import time
            time.sleep(0.4)
            try:
                ctypes = __import__('ctypes')
                user32 = ctypes.windll.user32
                found = []

                def enum_cb(hwnd, _):
                    if user32.IsWindowVisible(hwnd):
                        buf = ctypes.create_unicode_buffer(260)
                        if user32.GetClassNameW(hwnd, buf, 260):
                            cls = buf.value
                            if cls in ('CabinetWClass', 'ExploreWClass'):
                                found.append(hwnd)
                    return True

                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
                if found:
                    user32.SetForegroundWindow(found[-1])
            except Exception:
                pass
        threading.Thread(target=_bring_explorer_front, daemon=True).start()
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', path_str])
    else:
        subprocess.Popen(['xdg-open', path_str])
    return True


@app.route('/open-folder', methods=['POST'])
def open_folder():
    """在系统文件管理器中打开文件夹（直接置前显示）"""
    data = request.get_json() or {}
    folder_path = (data.get('path') or '').strip() or str(OUTPUT_DIR)
    target = Path(folder_path)
    if not target.exists():
        return jsonify({'error': '目录不存在'}), 404
    _open_folder_foreground(folder_path)
    return jsonify({'ok': True})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Flask 路由 - 视频编辑
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.route('/api/video-editor/extract-last-frame', methods=['POST'])
def api_extract_last_frame():
    """上传视频，导出最后一帧到输出目录并复制到剪贴板"""
    if 'file' not in request.files:
        return jsonify({'error': '请选择视频文件'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': '请选择视频文件'}), 400
    ext = Path(f.filename).suffix.lower()
    if ext not in VIDEO_EXTENSIONS:
        return jsonify({'error': '仅支持视频格式：' + ', '.join(VIDEO_EXTENSIONS)}), 400

    output_dir = (request.form.get('output_dir') or '').strip() or str(OUTPUT_DIR)
    out_path = Path(output_dir)
    try:
        out_path.mkdir(parents=True, exist_ok=True)
    except Exception:
        return jsonify({'error': '无法创建输出目录'}), 400

    tmp_id = str(uuid.uuid4())
    tmp_video = UPLOAD_DIR_EDITOR / f"{tmp_id}{ext}"
    try:
        f.save(str(tmp_video))
    except Exception:
        return jsonify({'error': '保存临时文件失败'}), 500

    stem = Path(f.filename).stem
    out_name = f"{stem}_last_frame.png"
    out_file = out_path / out_name
    counter = 0
    while out_file.exists():
        counter += 1
        out_file = out_path / f"{stem}_last_frame_{counter}.png"

    if not extract_last_frame(tmp_video, out_file):
        try:
            tmp_video.unlink(missing_ok=True)
        except Exception:
            pass
        return jsonify({'error': '导出最后一帧失败，请检查视频是否有效'}), 500

    clipboard_ok = _copy_image_to_clipboard_win(out_file) if sys.platform == 'win32' else False
    try:
        tmp_video.unlink(missing_ok=True)
    except Exception:
        pass

    return jsonify({
        'ok': True,
        'path': str(out_file),
        'filename': out_file.name,
        'clipboard': clipboard_ok
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Flask 路由 - 素材重命名工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@app.route('/api/upload-for-rename', methods=['POST'])
def upload_for_rename():
    """上传素材文件，获取元数据（分辨率、比例）并用本地规则解析文件名"""
    if 'files' not in request.files:
        return jsonify({'error': '没有选择文件'}), 400

    uploaded = []
    files_list = request.files.getlist('files')

    for f in files_list:
        if not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext not in MEDIA_EXTENSIONS:
            continue

        file_id = str(uuid.uuid4())
        safe_name = f"{file_id}{ext}"
        save_path = RENAME_UPLOAD_DIR / safe_name
        f.save(str(save_path))

        # 获取分辨率
        info = None
        if ext in VIDEO_EXTENSIONS:
            info = get_video_info(save_path)
        elif ext in IMAGE_EXTENSIONS:
            info = get_image_info(save_path)

        if info is None:
            info = {'width': 0, 'height': 0}

        ratio_label = classify_ratio_rename(info['width'], info['height'])

        # 本地规则解析文件名
        parsed = parse_filename_local(f.filename)

        uploaded.append({
            'file_id': file_id,
            'original_name': f.filename,
            'path': str(save_path),
            'width': info.get('width', 0),
            'height': info.get('height', 0),
            'ratio_label': ratio_label,
            'parsed': parsed,
        })

    return jsonify({'files': uploaded})


@app.route('/api/export-renamed', methods=['POST'])
def export_renamed():
    """导出重命名后的文件到输出目录"""
    data = request.get_json()
    file_list = data.get('files', [])
    custom_output_dir = data.get('output_dir', '').strip()

    if not file_list:
        return jsonify({'error': '没有文件需要导出'}), 400

    actual_output_dir = Path(custom_output_dir) if custom_output_dir else OUTPUT_DIR
    try:
        actual_output_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return jsonify({'error': f'无法创建输出目录: {actual_output_dir}'}), 400

    results = []
    errors = []

    for item in file_list:
        src_path = Path(item['server_path'])
        new_name = item['new_filename']

        if not src_path.exists():
            errors.append({'filename': new_name, 'error': '源文件不存在'})
            continue

        dst_path = actual_output_dir / new_name

        # 处理重名
        counter = 1
        while dst_path.exists():
            stem = Path(new_name).stem
            ext = Path(new_name).suffix
            dst_path = actual_output_dir / f"{stem}_{counter}{ext}"
            counter += 1

        try:
            shutil.copy2(str(src_path), str(dst_path))
            results.append({'filename': dst_path.name})
            # 清理上传的临时文件
            try:
                src_path.unlink()
            except OSError:
                pass
        except Exception as e:
            errors.append({'filename': new_name, 'error': str(e)})

    return jsonify({
        'results': results,
        'errors': errors,
        'output_dir': str(actual_output_dir)
    })




# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 自动更新 — 基于 GitHub Releases
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GITHUB_REPO = 'oNa2O2o/video-ratio-converter'
GITHUB_API_URL = f'https://api.github.com/repos/{GITHUB_REPO}/releases/latest'

update_info = {'checked': False, 'available': False}


def _parse_version(v):
    """'v2.4.0' / '2.4.0' -> (2, 4, 0)"""
    return tuple(int(x) for x in re.sub(r'^v', '', v.strip()).split('.'))


# 定期检查间隔（秒），默认 30 分钟
UPDATE_CHECK_INTERVAL = 30 * 60


def check_update_background():
    """后台检查 GitHub 是否有新版本（仅打包模式执行）"""
    if not getattr(sys, 'frozen', False):
        return
    try:
        req = Request(GITHUB_API_URL, headers={'Accept': 'application/vnd.github.v3+json'})
        with urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        latest_tag = data.get('tag_name', '')
        if not latest_tag:
            return

        current_ver = _parse_version(APP_VERSION)
        latest_ver = _parse_version(latest_tag)

        if latest_ver <= current_ver:
            update_info.update({'checked': True, 'available': False})
            return

        download_url = ''
        for asset in data.get('assets', []):
            name = asset.get('name', '')
            if name.endswith('.zip'):
                download_url = asset.get('browser_download_url', '')
                break

        update_info.update({
            'checked': True,
            'available': True,
            'latest': latest_tag,
            'current': APP_VERSION,
            'download_url': download_url,
            'release_notes': data.get('body', '') or '',
            'html_url': data.get('html_url', ''),
            'downloaded': False
        })
        print(f"  [Update] New version available: {latest_tag}")

        # 自动后台下载 ZIP
        if download_url and not update_info.get('downloaded'):
            _auto_download_update(download_url)
    except HTTPError as e:
        if e.code == 404:
            # 仓库暂无任何 Release 时 GitHub 返回 404，属正常情况
            update_info.update({'checked': True, 'available': False})
        else:
            print(f"  [Update] Check failed (ignored): {e.code} {e.reason}")
            update_info.update({'checked': True, 'available': False})
    except Exception as e:
        print(f"  [Update] Check failed (ignored): {e}")
        update_info.update({'checked': True, 'available': False})


def _auto_download_update(download_url):
    """后台静默下载更新 ZIP 到 _update_temp/"""
    try:
        exe_dir = Path(sys.executable).parent
        temp_dir = exe_dir / '_update_temp'
        zip_path = temp_dir / 'update.zip'

        # 如果已经下载过，跳过
        if zip_path.exists() and zip_path.stat().st_size > 0:
            update_info['downloaded'] = True
            print("  [Update] ZIP already downloaded, skipping")
            return

        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        print(f"  [Update] Auto-downloading: {download_url}")
        req = Request(download_url, headers={'Accept': 'application/octet-stream'})
        with urlopen(req, timeout=120) as resp:
            zip_path.write_bytes(resp.read())
        update_info['downloaded'] = True
        print(f"  [Update] Auto-download complete: {zip_path.stat().st_size // 1024}KB")
    except Exception as e:
        print(f"  [Update] Auto-download failed (ignored): {e}")


def _periodic_update_check_loop():
    """后台循环：启动时检查一次，之后每隔 UPDATE_CHECK_INTERVAL 秒再检查（仅打包模式）"""
    if not getattr(sys, 'frozen', False):
        return
    import time
    while True:
        check_update_background()
        time.sleep(UPDATE_CHECK_INTERVAL)


@app.route('/api/check-update')
def api_check_update():
    """前端查询更新状态；若带 ?trigger=1 则先执行一次检查再返回"""
    if request.args.get('trigger') == '1':
        check_update_background()
    return jsonify(update_info)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 配置 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.route('/api/config')
def api_get_config():
    return jsonify(load_config())


@app.route('/api/config', methods=['POST'])
def api_save_config():
    data = request.get_json(force=True)
    try:
        cfg = load_config()
        if 'creators' in data and isinstance(data['creators'], list):
            cfg['creators'] = data['creators']
        if 'defaultRegion' in data:
            cfg['defaultRegion'] = data['defaultRegion']
        if 'defaultPlatform' in data:
            cfg['defaultPlatform'] = data['defaultPlatform']
        if 'defaultCreator' in data:
            cfg['defaultCreator'] = data['defaultCreator']
        save_config(cfg)
        sync_known_creators()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 状态保存/恢复 API（更新重启时使用）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_STATE_PATH = BASE_DIR / '_update_state.json'


@app.route('/api/save-state', methods=['POST'])
def api_save_state():
    try:
        state = request.get_json(force=True)
        with open(_STATE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/restore-state')
def api_restore_state():
    if not _STATE_PATH.exists():
        return jsonify({'state': None})
    try:
        with open(_STATE_PATH, 'r', encoding='utf-8') as f:
            state = json.load(f)
        _STATE_PATH.unlink(missing_ok=True)
        return jsonify({'state': state})
    except Exception as e:
        return jsonify({'state': None, 'error': str(e)})


@app.route('/api/release-notes')
def api_release_notes():
    """获取最近几个版本的更新日志"""
    try:
        url = f'https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=10'
        req = Request(url, headers={'Accept': 'application/vnd.github.v3+json'})
        with urlopen(req, timeout=10) as resp:
            releases = json.loads(resp.read().decode('utf-8'))

        notes = []
        for rel in releases:
            tag = rel.get('tag_name', '')
            body = rel.get('body', '') or ''
            published = rel.get('published_at', '')
            notes.append({
                'version': tag,
                'date': published[:10] if published else '',
                'body': body
            })
        return jsonify({'notes': notes, 'current': APP_VERSION})
    except Exception as e:
        # 如果获取失败，至少返回当前更新信息中的 release_notes
        single = []
        if update_info.get('release_notes'):
            single.append({
                'version': update_info.get('latest', ''),
                'date': '',
                'body': update_info.get('release_notes', '')
            })
        return jsonify({'notes': single, 'current': APP_VERSION})


@app.route('/api/do-update', methods=['POST'])
def api_do_update():
    """执行一键更新：下载 -> 解压 -> 生成 updater.bat -> 退出"""
    if not getattr(sys, 'frozen', False):
        return jsonify({'error': '开发模式不支持自动更新'}), 400

    if not update_info.get('available') or not update_info.get('download_url'):
        return jsonify({'error': '没有可用的更新'}), 400

    download_url = update_info['download_url']
    exe_dir = Path(sys.executable).parent
    temp_dir = exe_dir / '_update_temp'
    exe_name = Path(sys.executable).name

    try:
        zip_path = temp_dir / 'update.zip'
        already_downloaded = update_info.get('downloaded') and zip_path.exists() and zip_path.stat().st_size > 0

        if already_downloaded:
            print("  [Update] Using pre-downloaded ZIP")
        else:
            # 清理旧的临时目录
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)

            # 下载 ZIP
            print(f"  [Update] Downloading: {download_url}")
            req = Request(download_url, headers={'Accept': 'application/octet-stream'})
            with urlopen(req, timeout=120) as resp:
                zip_path.write_bytes(resp.read())
            print(f"  [Update] Downloaded: {zip_path.stat().st_size // 1024}KB")

        # 解压
        extract_dir = temp_dir / 'extracted'
        with zipfile.ZipFile(str(zip_path), 'r') as zf:
            zf.extractall(str(extract_dir))
        zip_path.unlink()

        # 找到解压后的实际内容目录（ZIP 可能有一层根目录）
        contents = list(extract_dir.iterdir())
        if len(contents) == 1 and contents[0].is_dir():
            source_dir = contents[0]
        else:
            source_dir = extract_dir

        # 将内容移到 temp_dir 根下
        for item in source_dir.iterdir():
            dest = temp_dir / item.name
            if dest.exists():
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
            shutil.move(str(item), str(dest))

        # 清理 extracted 目录
        if extract_dir.exists():
            shutil.rmtree(extract_dir)

        # 使用 exe 的短路径（8.3）时，bat 中可直接 start；否则用 VBS 启动 exe，bat 保持纯 ASCII 避免乱码
        exe_full = exe_dir / exe_name
        exe_to_start = _get_short_path(exe_full)
        use_short_path = exe_to_start != str(exe_full) and exe_to_start.isascii()

        # 等待主进程完全退出并释放 exe 后再覆盖，避免「覆盖失败/半覆盖导致闪退、重开仍是旧版」
        wait_sec = 10
        # 使用 robocopy 支持重试，避免文件仍被占用时一次覆盖失败
        bat_path = exe_dir / '_updater.bat'
        if use_short_path:
            bat_content = (
                '@echo off\r\n'
                'chcp 65001 >nul 2>&1\r\n'
                'cd /d "%~dp0"\r\n'
                'echo.\r\n'
                'echo  Waiting for app to exit...\r\n'
                f'timeout /t {wait_sec} /nobreak >nul\r\n'
                'echo  Copying files...\r\n'
                'robocopy "_update_temp" "." /E /IS /IT /R:5 /W:3 /NFL /NDL /NJH /NJS >nul\r\n'
                'if errorlevel 8 (echo  Copy failed. Retry later. & pause) else (\r\n'
                'rmdir /s /q "_update_temp" 2>nul\r\n'
                'echo  Done. Restarting...\r\n'
                f'start "" "{exe_to_start}"\r\n'
                'timeout /t 1 /nobreak >nul\r\n'
                ')\r\n'
                'del "%~f0"\r\n'
            )
            bat_path.write_text(bat_content, encoding='ascii')
        else:
            # 无 exe 短路径：用 VBS 启动 exe（VBS 支持 Unicode），bat 仅含 ASCII，彻底避免 cmd 乱码
            def _vbs_escape(s):
                return s.replace('"', '""')
            exe_path_str = _vbs_escape(str(exe_full.resolve()))
            exe_dir_str = _vbs_escape(str(exe_dir.resolve()))
            vbs_path = exe_dir / '_restart.vbs'
            vbs_content = (
                'Option Explicit\r\n'
                'Dim WshShell, exePath, exeDir\r\n'
                f'exePath = "{exe_path_str}"\r\n'
                f'exeDir = "{exe_dir_str}"\r\n'
                'Set WshShell = CreateObject("WScript.Shell")\r\n'
                'WshShell.CurrentDirectory = exeDir\r\n'
                'WshShell.Run Chr(34) & exePath & Chr(34), 1, False\r\n'
            )
            vbs_path.write_text(vbs_content, encoding='utf-16-le', errors='replace')
            bat_content = (
                '@echo off\r\n'
                'chcp 65001 >nul 2>&1\r\n'
                'cd /d "%~dp0"\r\n'
                'echo.\r\n'
                'echo  Waiting for app to exit...\r\n'
                f'timeout /t {wait_sec} /nobreak >nul\r\n'
                'echo  Copying files...\r\n'
                'robocopy "_update_temp" "." /E /IS /IT /R:5 /W:3 /NFL /NDL /NJH /NJS >nul\r\n'
                'if errorlevel 8 (echo  Copy failed. Retry later. & pause) else (\r\n'
                'rmdir /s /q "_update_temp" 2>nul\r\n'
                'echo  Restarting...\r\n'
                'wscript "%~dp0_restart.vbs"\r\n'
                'timeout /t 1 /nobreak >nul\r\n'
                'del "%~dp0_restart.vbs" 2>nul\r\n'
                ')\r\n'
                'del "%~f0"\r\n'
            )
            bat_path.write_text(bat_content, encoding='ascii')

        print(f"  [Update] Generated updater (short_path={use_short_path}), exe={exe_to_start!r}")

        # 用「目录短路径 + 纯英文 bat 名」调用，避免向 cmd 传入中文路径导致乱码
        exe_dir_short = _get_short_path(exe_dir)
        if exe_dir_short.isascii():
            cmd_line = f'cd /d "{exe_dir_short}" && _updater.bat'
        else:
            bat_short = _get_short_path(bat_path)
            cmd_line = bat_short if bat_short.isascii() else f'cd /d "{exe_dir}" && _updater.bat'
        subprocess.Popen(
            ['cmd', '/c', cmd_line],
            cwd=str(exe_dir),
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        print("  [Update] Updater launched, shutting down...")

        # 延迟退出，确保 bat 已启动且响应已返回前端，再结束进程释放 exe
        def _exit_later():
            import time
            time.sleep(2)
            os._exit(0)

        threading.Thread(target=_exit_later, daemon=True).start()
        return jsonify({'ok': True, 'message': '更新已开始，程序将自动重启'})

    except Exception as e:
        print(f"  [Update] Failed: {traceback.format_exc()}")
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({'error': f'更新失败: {str(e)}'}), 500


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 端口管理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _kill_port(port):
    """杀掉占用指定端口的进程（Windows）"""
    import socket
    # 先检测端口是否被占用
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1)
        sock.connect(('127.0.0.1', port))
        sock.close()
        # 端口被占用，尝试杀掉
        print(f"  [!] Port {port} is in use, killing old process...")
        try:
            result = subprocess.run(
                f'netstat -ano | findstr ":{port}" | findstr "LISTENING"',
                capture_output=True, text=True, shell=True,
                encoding='utf-8', errors='replace',
                **_subprocess_kwargs
            )
            for line in result.stdout.strip().split('\n'):
                parts = line.split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != os.getpid():
                        subprocess.run(
                            f'taskkill /F /PID {pid}',
                            capture_output=True, shell=True,
                            **_subprocess_kwargs
                        )
                        print(f"  [!] Killed old process PID {pid}")
            import time
            time.sleep(1)
        except Exception as e:
            print(f"  [!] Could not kill old process: {e}")
        return True
    except (ConnectionRefusedError, OSError):
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 启动入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == '__main__':
    try:
        PORT = 5000

        # 启动前清理旧进程
        _kill_port(PORT)

        print("\n  ========================================")
        print(f"  Asset Toolbox v{APP_VERSION}")
        print("  ========================================")
        print(f"  Web UI:  http://localhost:{PORT}")
        print(f"  Rename:  http://localhost:{PORT}/rename")
        print(f"  Output:  {OUTPUT_DIR}")
        print(f"  FFmpeg:  {FFMPEG_PATH}")
        print("  Close this window to exit.\n")

        # 后台定期检查更新（启动时一次，之后每 30 分钟，仅打包模式）
        threading.Thread(target=_periodic_update_check_loop, daemon=True).start()

        threading.Timer(1.5, lambda: webbrowser.open(f'http://localhost:{PORT}')).start()

        app.run(host='0.0.0.0', port=PORT, debug=False)
    except Exception as e:
        err_msg = f"Application crashed:\n{traceback.format_exc()}"
        try:
            log_path = BASE_DIR / 'error.log'
            log_path.write_text(err_msg, encoding='utf-8')
            print(f"\n[ERROR] {err_msg}")
            print(f"Error log saved: {log_path}")
        except Exception:
            print(f"\n[ERROR] {err_msg}")
        if getattr(sys, 'frozen', False):
            input("\nPress Enter to exit...")
        sys.exit(1)
