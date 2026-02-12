import os
import sys
import json
import uuid
import re
import subprocess
import threading
import webbrowser
import shutil
from pathlib import Path
from flask import Flask, request, jsonify, render_template, send_from_directory, Response

import imageio_ffmpeg

# 可选依赖
try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PyInstaller 兼容支持：区分执行模式和开发模式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if getattr(sys, 'frozen', False):
    _BUNDLE_DIR = Path(sys._MEIPASS)
    BASE_DIR = Path(sys.executable).parent
    app = Flask(__name__,
                template_folder=str(_BUNDLE_DIR / 'templates'),
                static_folder=str(_BUNDLE_DIR / 'static'))
else:
    BASE_DIR = Path(__file__).parent.resolve()
    app = Flask(__name__)

UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 4 * 1024 * 1024 * 1024  # 4GB

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


# Gemini AI 分析 Prompt
GEMINI_PROMPT = """你是一个广告素材文件名分析助手。请分析以下原始文件名，提取关键信息。

原始文件名: {filename}
文件分辨率: {width}x{height}

请执行以下操作：
1. 清洗文件名：移除以下干扰信息：
   - 日期（如 260129, 240522, 2024-05-22 等各种格式）
   - 地区代码（JP/TC/EN/TH/KR/VN/ID/ES）
   - 制作人缩写（ZHM/YY/ZSY/GJY/YHR/SY/DHY/CGY/QXY）
   - 平台代码（FB/GG/TT）
   - 比例标记（竖/方/横）
   - 版本号（如 -1, -2, v1, v2）
   - 属性标记（原创/迭代/竞品二创/原品/品牌/竞品）
   - 受众标记（男性向/女性向/男/女）
   - 无意义的分隔符和编号

2. 提取核心词(assetName)：保留核心业务描述，用简短的中文或英文表达。去掉多余空格，用空格分隔多个词。

3. 判断受众(audience)：根据内容判断是 "男性向" 还是 "女性向"。如果无法判断，默认 "男性向"。

4. 判断属性(property)：判断是 "原创"、"迭代" 还是 "竞品二创"。如果无法判断，默认 "原创"。

5. 识别平台(platform)：从文件名中识别 FB、GG 或 TT。如果无法识别，返回空字符串。

请严格以JSON格式返回，不要包含markdown代码块标记或任何其他内容：
{{"assetName": "核心描述词", "audience": "男性向", "property": "原创", "platform": ""}}"""


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
    """上传素材文件并获取元数据（分辨率、比例）"""
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

        uploaded.append({
            'file_id': file_id,
            'original_name': f.filename,
            'path': str(save_path),
            'width': info.get('width', 0),
            'height': info.get('height', 0),
            'ratio_label': ratio_label
        })

    return jsonify({'files': uploaded})


@app.route('/api/analyze-filename', methods=['POST'])
def analyze_filename_api():
    """调用 Gemini AI 分析文件名，提取核心信息"""
    data = request.get_json()
    filename = data.get('filename', '')
    width = data.get('width', 0)
    height = data.get('height', 0)
    api_key = data.get('api_key', '')

    # 尝试从配置文件获取 API Key
    if not api_key:
        config = load_config()
        api_key = config.get('gemini_api_key', '')

    if not api_key:
        return jsonify({'error': '请先设置 Gemini API Key'}), 400

    if not HAS_GENAI:
        return jsonify({
            'error': '缺少 google-generativeai 库，请运行: pip install google-generativeai'
        }), 500

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')

        prompt = GEMINI_PROMPT.format(
            filename=filename,
            width=width,
            height=height
        )
        response = model.generate_content(prompt)

        # 解析 JSON 响应
        text = response.text.strip()
        # 尝试提取 JSON（可能被 markdown 代码块包裹）
        if '```' in text:
            parts = text.split('```')
            for part in parts:
                cleaned = part.strip()
                if cleaned.startswith('json'):
                    cleaned = cleaned[4:].strip()
                if cleaned.startswith('{'):
                    text = cleaned
                    break

        result = json.loads(text)
        return jsonify(result)

    except json.JSONDecodeError:
        resp_text = response.text[:300] if 'response' in dir() else '无响应'
        return jsonify({'error': f'AI 返回格式错误: {resp_text}'}), 500
    except Exception as e:
        return jsonify({'error': f'AI 分析失败: {str(e)}'}), 500


@app.route('/api/batch-analyze', methods=['POST'])
def batch_analyze_api():
    """批量分析多个文件名（串行调用 Gemini）"""
    data = request.get_json()
    items = data.get('items', [])
    api_key = data.get('api_key', '')

    if not api_key:
        config = load_config()
        api_key = config.get('gemini_api_key', '')

    if not api_key:
        return jsonify({'error': '请先设置 Gemini API Key'}), 400

    if not HAS_GENAI:
        return jsonify({
            'error': '缺少 google-generativeai 库，请运行: pip install google-generativeai'
        }), 500

    results = []
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')

        for item in items:
            try:
                prompt = GEMINI_PROMPT.format(
                    filename=item.get('filename', ''),
                    width=item.get('width', 0),
                    height=item.get('height', 0)
                )
                response = model.generate_content(prompt)
                text = response.text.strip()

                if '```' in text:
                    parts = text.split('```')
                    for part in parts:
                        cleaned = part.strip()
                        if cleaned.startswith('json'):
                            cleaned = cleaned[4:].strip()
                        if cleaned.startswith('{'):
                            text = cleaned
                            break

                result = json.loads(text)
                result['file_id'] = item.get('file_id', '')
                result['success'] = True
                results.append(result)
            except Exception as e:
                results.append({
                    'file_id': item.get('file_id', ''),
                    'success': False,
                    'error': str(e)
                })
    except Exception as e:
        return jsonify({'error': f'AI 服务初始化失败: {str(e)}'}), 500

    return jsonify({'results': results})


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


@app.route('/api/save-api-key', methods=['POST'])
def save_api_key():
    """保存 Gemini API Key 到配置文件"""
    data = request.get_json()
    key = data.get('key', '').strip()
    config = load_config()
    config['gemini_api_key'] = key
    save_config_file(config)
    return jsonify({'ok': True})


@app.route('/api/load-api-key', methods=['GET'])
def load_api_key():
    """加载已保存的 API Key（脱敏返回）"""
    config = load_config()
    key = config.get('gemini_api_key', '')
    if key:
        # 脱敏：只返回前4位和后4位
        masked = key[:4] + '*' * max(0, len(key) - 8) + key[-4:] if len(key) > 8 else '****'
        return jsonify({'has_key': True, 'masked_key': masked, 'key': key})
    return jsonify({'has_key': False})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 启动入口
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == '__main__':
    print(f"\n  视频比例转换 & 素材重命名工具已启动！")
    print(f"  浏览器中打开: http://localhost:5000")
    print(f"  素材重命名:   http://localhost:5000/rename")
    print(f"  输出目录: {OUTPUT_DIR}")
    print(f"  FFmpeg: {FFMPEG_PATH}")
    print(f"  关闭此窗口即可退出程序\n")

    threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5000')).start()

    app.run(host='0.0.0.0', port=5000, debug=False)
