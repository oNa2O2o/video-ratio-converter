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
from pathlib import Path

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
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024 * 1024  # 4GB
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # 禁用静态文件缓存


# ━━━ 版本号（用于缓存失效） ━━━
APP_VERSION = '2.1.0'


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
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                    **_subprocess_kwargs)
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
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                                **_subprocess_kwargs)
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


def get_target_ratios(current_ratio):
    """返回其他两种比例"""
    all_ratios = ["9:16", "1:1", "16:9"]
    return [r for r in all_ratios if r != current_ratio]


def make_even(n):
    """确保数字为偶数（FFmpeg 要求）"""
    return n if n % 2 == 0 else n + 1


def calculate_output_dimensions(orig_w, orig_h, target_ratio):
    """计算输出尺寸，保持原始视频完整大小"""
    if target_ratio == "16:9":
        h = orig_h
        w = int(h * 16 / 9)
        if w < orig_w:
            w = orig_w
            h = int(w * 9 / 16)
    elif target_ratio == "9:16":
        w = orig_w
        h = int(w * 16 / 9)
        if h < orig_h:
            h = orig_h
            w = int(h * 9 / 16)
    else:  # 1:1
        side = max(orig_w, orig_h)
        w = h = side
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
        **_subprocess_kwargs
    )
    _, stderr = process.communicate()

    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg 错误: {stderr.decode('utf-8', errors='replace')}")

    return output_path


def process_task(task_id, files_info, output_dir=None):
    """后台任务：处理所有上传的视频"""
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

            progress_store[task_id]['current_file'] = (
                f"{original_name} → {RATIO_LABELS[target_ratio]}"
            )

            try:
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

    for file_info in files_info:
        try:
            os.remove(file_info['path'])
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
KNOWN_CREATORS = {'ZHM', 'YY', 'ZSY', 'GJY', 'YHR', 'SY', 'DHY', 'CGY', 'QXY'}
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
# Flask 路由 - 比例转换工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.route('/')
def index():
    return render_template('index.html')


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


@app.route('/process', methods=['POST'])
def process():
    """开始处理上传的视频"""
    data = request.get_json()
    files_info = data.get('files', [])
    custom_output_dir = data.get('output_dir', '').strip()

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

    task_id = str(uuid.uuid4())
    thread = threading.Thread(target=process_task, args=(task_id, files_info, str(target_dir)))
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


@app.route('/open-folder', methods=['POST'])
def open_folder():
    """在系统文件管理器中打开文件夹"""
    data = request.get_json()
    folder_path = data.get('path', str(OUTPUT_DIR))
    target = Path(folder_path)
    if not target.exists():
        return jsonify({'error': '目录不存在'}), 404
    if sys.platform == 'win32':
        os.startfile(str(target))
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', str(target)])
    else:
        subprocess.Popen(['xdg-open', str(target)])
    return jsonify({'ok': True})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Flask 路由 - 素材重命名工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.route('/rename')
def rename_page():
    """素材重命名工具页面"""
    return render_template('rename.html')


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
        save_path = UPLOAD_DIR / safe_name
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
        print(f"  Video Ratio Converter & Rename Tool v{APP_VERSION}")
        print("  ========================================")
        print(f"  Web UI:  http://localhost:{PORT}")
        print(f"  Rename:  http://localhost:{PORT}/rename")
        print(f"  Output:  {OUTPUT_DIR}")
        print(f"  FFmpeg:  {FFMPEG_PATH}")
        print("  Close this window to exit.\n")

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
