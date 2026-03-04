# -*- coding: utf-8 -*-
"""创建 GitHub Release 并上传 ZIP，用于一键更新"""
import os
import sys
import json
import zipfile
import subprocess
from pathlib import Path
from urllib.request import urlopen, Request

REPO = 'oNa2O2o/video-ratio-converter'
TAG = 'v2.5.2'
ZIP_NAME = 'AssetToolbox-v2.5.2.zip'  # 英文名避免上传编码问题

def get_token():
    token = os.environ.get('GITHUB_TOKEN', '')
    if token:
        return token
    try:
        proc = subprocess.Popen(
            ['git', 'credential', 'fill'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        out, _ = proc.communicate(input='protocol=https\nhost=github.com\n\n')
        for line in out.strip().split('\n'):
            if line.startswith('password='):
                return line.split('=', 1)[1]
    except Exception:
        pass
    return None

def main():
    base = Path(__file__).parent
    dist_dir = base / 'dist'
    dirs = list(dist_dir.iterdir()) if dist_dir.exists() else []
    app_dir = None
    for d in dirs:
        if d.is_dir():
            app_dir = d
            break
    if not app_dir or not (app_dir / '素材工具箱.exe').exists():
        print('未找到 dist/素材工具箱/ 或 素材工具箱.exe，请先执行打包。')
        sys.exit(1)

    zip_path = base / ZIP_NAME
    if zip_path.exists():
        zip_path.unlink()
    print(f'正在打包: {app_dir.name} -> {ZIP_NAME}')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in app_dir.rglob('*'):
            if f.is_file():
                arcname = f.relative_to(app_dir.parent)
                zf.write(f, arcname)
    print(f'  OK, 大小: {zip_path.stat().st_size // 1024 // 1024} MB')

    token = get_token()
    if not token:
        print('需要 GitHub token (GITHUB_TOKEN 或 git credential)。')
        sys.exit(1)

    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': f'token {token}',
    }

    # 创建或获取 Release
    url = f'https://api.github.com/repos/{REPO}/releases'
    release = None
    try:
        req = Request(f'https://api.github.com/repos/{REPO}/releases/tags/{TAG}', headers=headers)
        resp = urlopen(req, timeout=10)
        release = json.loads(resp.read().decode('utf-8'))
        print(f'使用已有 Release: {TAG}')
    except Exception:
        pass
    if not release:
        payload = json.dumps({
            'tag_name': TAG,
            'name': f'素材工具箱 {TAG}',
            'body': '一键更新：下载 ZIP 后由程序自动解压替换。',
            'draft': False,
        }).encode('utf-8')
        req = Request(url, data=payload, method='POST', headers={**headers, 'Content-Type': 'application/json'})
        try:
            resp = urlopen(req, timeout=15)
            release = json.loads(resp.read().decode('utf-8'))
            print(f'已创建 Release: {TAG}')
        except Exception as e:
            print(f'创建 Release 失败: {e}')
            sys.exit(1)

    upload_url = release['upload_url'].split('{')[0] + '?name=' + ZIP_NAME
    print(f'正在上传: {ZIP_NAME}')
    with open(zip_path, 'rb') as f:
        data = f.read()
    req = Request(upload_url, data=data, method='POST', headers={
        **headers,
        'Content-Type': 'application/zip',
        'Content-Length': len(data),
    })
    try:
        urlopen(req, timeout=120)
    except Exception as e:
        print(f'上传失败: {e}')
        sys.exit(1)

    zip_path.unlink()
    print(f'完成: https://github.com/{REPO}/releases/tag/{TAG}')

if __name__ == '__main__':
    main()
