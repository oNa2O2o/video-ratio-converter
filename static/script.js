document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileList = document.getElementById('file-list');
    const fileItems = document.getElementById('file-items');
    const processBtn = document.getElementById('process-btn');
    const clearBtn = document.getElementById('clear-btn');
    const progressSection = document.getElementById('progress-section');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const resultsSection = document.getElementById('results-section');
    const resultItems = document.getElementById('result-items');
    const errorItems = document.getElementById('error-items');
    const outputPathInput = document.getElementById('output-path');
    const browseOutputBtn = document.getElementById('browse-output-btn');
    const openFolderBtn = document.getElementById('open-folder-btn');
    const openOutputFolderBtn = document.getElementById('open-output-folder-btn');

    let uploadedFiles = [];
    let lastOutputDir = '';

    // 标签样式映射
    const tagClass = { '竖': 'tag-vertical', '方': 'tag-square', '横': 'tag-horizontal' };

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 套版管理
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // templates[label] = { path, region, thumbnail }
    const templates = {};

    document.querySelectorAll('.template-slot').forEach(slot => {
        const ratio = slot.dataset.ratio;
        const dropZoneEl = slot.querySelector('.template-drop-zone');
        const fileInputEl = slot.querySelector('.template-file-input');
        const placeholder = slot.querySelector('.template-placeholder');
        const preview = slot.querySelector('.template-preview');
        const thumb = slot.querySelector('.template-thumb');
        const info = slot.querySelector('.template-info');
        const removeBtn = slot.querySelector('.template-remove-btn');

        // 点击上传
        dropZoneEl.addEventListener('click', (e) => {
            if (e.target === removeBtn || removeBtn.contains(e.target)) return;
            if (!templates[ratio]) fileInputEl.click();
        });

        // 拖拽
        dropZoneEl.addEventListener('dragover', e => {
            e.preventDefault();
            dropZoneEl.classList.add('drag-over');
        });
        dropZoneEl.addEventListener('dragleave', () => {
            dropZoneEl.classList.remove('drag-over');
        });
        dropZoneEl.addEventListener('drop', e => {
            e.preventDefault();
            dropZoneEl.classList.remove('drag-over');
            const file = e.dataTransfer.files[0];
            if (file) uploadTemplate(ratio, file, slot);
        });

        fileInputEl.addEventListener('change', () => {
            if (fileInputEl.files[0]) {
                uploadTemplate(ratio, fileInputEl.files[0], slot);
            }
            fileInputEl.value = '';
        });

        // 移除
        removeBtn.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (templates[ratio]) {
                try {
                    await fetch('/remove-template', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ path: templates[ratio].path })
                    });
                } catch (_) {}
                delete templates[ratio];
            }
            placeholder.style.display = '';
            preview.style.display = 'none';
            removeBtn.style.display = 'none';
            dropZoneEl.classList.remove('has-template');
        });
    });

    async function uploadTemplate(ratio, file, slotEl) {
        if (!file.name.toLowerCase().endsWith('.png')) {
            alert('套版必须是 PNG 格式（需要透明通道）');
            return;
        }

        const placeholder = slotEl.querySelector('.template-placeholder');
        const preview = slotEl.querySelector('.template-preview');
        const thumb = slotEl.querySelector('.template-thumb');
        const info = slotEl.querySelector('.template-info');
        const removeBtn = slotEl.querySelector('.template-remove-btn');
        const dropZoneEl = slotEl.querySelector('.template-drop-zone');

        placeholder.innerHTML = '<span>上传中...</span>';

        const formData = new FormData();
        formData.append('file', file);
        formData.append('ratio', ratio);

        try {
            const resp = await fetch('/upload-template', { method: 'POST', body: formData });
            const data = await resp.json();

            if (data.error) {
                alert(data.error);
                placeholder.innerHTML = `
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                        <rect x="4" y="4" width="16" height="16" rx="2"/>
                        <line x1="12" y1="9" x2="12" y2="15"/>
                        <line x1="9" y1="12" x2="15" y2="12"/>
                    </svg>
                    <span>拖入 PNG 套版</span>`;
                return;
            }

            // 保存套版数据
            templates[ratio] = {
                path: data.path,
                region: data.region
            };

            // 显示预览
            if (data.thumbnail) {
                thumb.src = data.thumbnail;
            }
            const r = data.region;
            info.textContent = `${r.template_width}×${r.template_height} | 视频区域: ${r.width}×${r.height} @ (${r.x},${r.y})`;

            placeholder.style.display = 'none';
            preview.style.display = '';
            removeBtn.style.display = '';
            dropZoneEl.classList.add('has-template');

        } catch (err) {
            alert('套版上传失败: ' + err.message);
            placeholder.innerHTML = `
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <rect x="4" y="4" width="16" height="16" rx="2"/>
                    <line x1="12" y1="9" x2="12" y2="15"/>
                    <line x1="9" y1="12" x2="15" y2="12"/>
                </svg>
                <span>拖入 PNG 套版</span>`;
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 视频上传
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', e => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });
    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });
    dropZone.addEventListener('drop', e => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
    });
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) uploadFiles(fileInput.files);
        fileInput.value = '';
    });

    clearBtn.addEventListener('click', () => {
        uploadedFiles = [];
        fileItems.innerHTML = '';
        fileList.style.display = 'none';
    });

    browseOutputBtn.addEventListener('click', async () => {
        try {
            const resp = await fetch('/browse-folder', { method: 'POST' });
            const data = await resp.json();
            if (data.path) {
                outputPathInput.value = data.path;
            }
        } catch (err) {
            alert('浏览失败: ' + err.message);
        }
    });

    function openOutputFolder() {
        const path = (outputPathInput && outputPathInput.value.trim()) || lastOutputDir;
        return fetch('/open-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path || '' })
        }).then(r => r.json()).then(data => {
            if (data.error) throw new Error(data.error);
        });
    }
    if (openFolderBtn) openFolderBtn.addEventListener('click', async () => {
        try { await openOutputFolder(); } catch (err) { alert('无法打开文件夹: ' + err.message); }
    });
    if (openOutputFolderBtn) openOutputFolderBtn.addEventListener('click', async () => {
        try { await openOutputFolder(); } catch (err) { alert('无法打开文件夹: ' + err.message); }
    });

    function resetUI() {
        processBtn.disabled = false;
        processBtn.textContent = '开始处理';
        uploadedFiles = [];
        fileItems.innerHTML = '';
        fileList.style.display = 'none';
        progressSection.style.display = 'none';
        progressBar.style.width = '0%';
        progressText.textContent = '';
    }

    async function uploadFiles(files) {
        const formData = new FormData();
        for (const file of files) {
            formData.append('files', file);
        }

        processBtn.disabled = true;
        processBtn.textContent = '上传中...';
        fileList.style.display = 'block';

        try {
            const resp = await fetch('/upload', { method: 'POST', body: formData });
            const data = await resp.json();

            if (data.error) {
                alert(data.error);
                return;
            }

            for (const f of data.files) {
                uploadedFiles.push(f);
                const div = document.createElement('div');
                div.className = 'file-item';

                // 为每个目标比例标注是套版还是模糊
                const targetTags = f.target_labels
                    .map(l => {
                        const hasTpl = !!templates[l];
                        const badge = hasTpl ? ' 🖼' : '';
                        return `<span class="tag ${tagClass[l]}" title="${hasTpl ? '使用套版' : '模糊背景'}">${l}${badge}</span>`;
                    })
                    .join(' ');

                div.innerHTML = `
                    <span class="file-name">${f.original_name}</span>
                    <span class="file-info">
                        <span class="tag ${tagClass[f.ratio_label]}">${f.ratio_label}</span>
                        <span class="tag-arrow">&rarr;</span>
                        ${targetTags}
                    </span>`;
                fileItems.appendChild(div);
            }
        } catch (err) {
            alert('上传失败: ' + err.message);
        } finally {
            processBtn.disabled = false;
            processBtn.textContent = '开始处理';
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 处理与进度
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    processBtn.addEventListener('click', async () => {
        if (!uploadedFiles.length) return;

        processBtn.disabled = true;
        processBtn.textContent = '处理中...';
        progressSection.style.display = 'block';
        resultsSection.style.display = 'none';
        resultItems.innerHTML = '';
        errorItems.innerHTML = '';
        progressBar.style.width = '0%';

        try {
            const resp = await fetch('/process', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    files: uploadedFiles,
                    output_dir: outputPathInput.value.trim(),
                    templates: templates
                })
            });
            const data = await resp.json();

            if (data.error) {
                alert(data.error);
                processBtn.disabled = false;
                processBtn.textContent = '开始处理';
                return;
            }

            lastOutputDir = data.output_dir || '';
            listenProgress(data.task_id);
        } catch (err) {
            alert('启动处理失败: ' + err.message);
            processBtn.disabled = false;
            processBtn.textContent = '开始处理';
        }
    });

    function listenProgress(taskId) {
        const evtSource = new EventSource(`/progress/${taskId}`);
        let taskDone = false;

        evtSource.onmessage = (event) => {
            const info = JSON.parse(event.data);

            if (info.error) {
                evtSource.close();
                alert(info.error);
                resetUI();
                return;
            }

            const pct = info.total > 0
                ? Math.round((info.completed / info.total) * 100) : 0;
            progressBar.style.width = pct + '%';
            progressText.textContent =
                `${info.completed}/${info.total} - ${info.current_file || '完成'}`;

            if (info.status === 'done') {
                taskDone = true;
                evtSource.close();
                showResults(info.results, info.errors);
                resetUI();
            }
        };

        evtSource.onerror = () => {
            evtSource.close();
            if (!taskDone) {
                progressText.textContent = '连接中断，请刷新页面重试';
                processBtn.disabled = false;
                processBtn.textContent = '开始处理';
            }
        };
    }

    function showResults(results, errors) {
        resultsSection.style.display = 'block';

        for (const r of results) {
            const div = document.createElement('div');
            div.className = 'result-item';
            div.innerHTML = `
                <span>
                    <span class="file-name">${r.filename}</span>
                    <span class="tag ${tagClass[r.label]}">${r.label}</span>
                </span>`;
            resultItems.appendChild(div);
        }

        for (const e of errors) {
            const div = document.createElement('div');
            div.className = 'error-item';
            div.textContent = `${e.filename} → ${e.target}: ${e.error}`;
            errorItems.appendChild(div);
        }
    }

    checkForUpdate();
    restoreAppState();
});

function checkForUpdate() {
    fetch('/api/check-update')
        .then(r => r.json())
        .then(data => {
            if (data.available) {
                const banner = document.getElementById('update-banner');
                const text = document.getElementById('update-text');
                const clBtn = document.getElementById('changelog-toggle-btn');
                if (banner && text) {
                    text.textContent = `发现新版本 ${data.latest}（当前 v${data.current}）`;
                    banner.style.display = 'flex';
                    if (clBtn) clBtn.style.display = '';
                }
            } else if (!data.checked) {
                setTimeout(checkForUpdate, 3000);
            }
        })
        .catch(() => {});
}

function manualCheckUpdate() {
    var btn = document.getElementById('check-update-btn');
    if (btn) { btn.disabled = true; btn.textContent = '检查中...'; }
    fetch('/api/check-update?trigger=1')
        .then(r => r.json())
        .then(function(data) {
            var banner = document.getElementById('update-banner');
            var text = document.getElementById('update-text');
            var updateBtn = document.getElementById('update-btn');
            if (data.available && banner && text) {
                text.textContent = '发现新版本 ' + data.latest + '（当前 v' + data.current + '）';
                if (updateBtn) updateBtn.style.display = '';
                var clBtn = document.getElementById('changelog-toggle-btn');
                if (clBtn) clBtn.style.display = '';
                banner.style.display = 'flex';
            } else if (banner && text) {
                text.textContent = '当前已是最新版本 v' + (data.current || '');
                if (updateBtn) updateBtn.style.display = 'none';
                banner.style.display = 'flex';
                setTimeout(function() {
                    banner.style.display = 'none';
                    if (updateBtn) updateBtn.style.display = '';
                }, 2500);
            }
        })
        .catch(function() {
            var banner = document.getElementById('update-banner');
            var text = document.getElementById('update-text');
            if (banner && text) { text.textContent = '检查更新失败，请稍后重试'; banner.style.display = 'flex'; }
        })
        .finally(function() {
            if (btn) { btn.disabled = false; btn.textContent = '检查更新'; }
        });
}

function doUpdate() {
    const btn = document.getElementById('update-btn');
    const text = document.getElementById('update-text');
    if (btn) { btn.disabled = true; btn.textContent = '更新中...'; }
    if (text) { text.textContent = '正在下载并安装更新，请勿关闭...'; }

    // 先保存状态再更新
    saveAppState().finally(() => {
        fetch('/api/do-update', { method: 'POST' })
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    if (text) text.textContent = '更新完成，程序正在重启，请稍后刷新页面...';
                    if (btn) btn.style.display = 'none';
                } else {
                    if (text) text.textContent = `更新失败: ${data.error}`;
                    if (btn) { btn.disabled = false; btn.textContent = '重试'; }
                }
            })
            .catch(() => {
                if (text) text.textContent = '更新完成，程序正在重启...';
                if (btn) btn.style.display = 'none';
            });
    });
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 更新日志
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
var _changelogLoaded = false;

function toggleChangelog() {
    var panel = document.getElementById('changelog-panel');
    if (!panel) return;
    if (panel.style.display === 'none') {
        panel.style.display = 'block';
        if (!_changelogLoaded) loadChangelog();
    } else {
        panel.style.display = 'none';
    }
}

function loadChangelog() {
    var content = document.getElementById('changelog-content');
    fetch('/api/release-notes')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            _changelogLoaded = true;
            if (!data.notes || !data.notes.length) {
                content.innerHTML = '<p style="color:#888">暂无更新日志</p>';
                return;
            }
            var html = '';
            data.notes.forEach(function(n) {
                var dateStr = n.date ? ' (' + n.date + ')' : '';
                var isCurrent = n.version && data.current && n.version.replace(/^v/, '') === data.current;
                var badge = isCurrent ? ' <span class="changelog-current">当前版本</span>' : '';
                html += '<div class="changelog-item">';
                html += '<h4>' + escapeHtmlGlobal(n.version) + dateStr + badge + '</h4>';
                html += '<pre class="changelog-body">' + escapeHtmlGlobal(n.body || '无说明') + '</pre>';
                html += '</div>';
            });
            content.innerHTML = html;
        })
        .catch(function() {
            content.innerHTML = '<p style="color:#f87171">加载失败</p>';
        });
}

function escapeHtmlGlobal(str) {
    if (!str) return '';
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
// 保存和恢复应用状态（更新时使用）
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
function saveAppState() {
    // 获取当前活跃 tab
    var activeTab = 'converter';
    var activeLink = document.querySelector('.nav-link.active');
    if (activeLink) activeTab = activeLink.dataset.tab || 'converter';

    var state = { activeTab: activeTab };

    // 收集重命名工具的状态
    if (typeof window.renameGetState === 'function') {
        state.rename = window.renameGetState();
    }

    // 收集各输出目录
    var convOutput = document.getElementById('output-path');
    if (convOutput) state.converterOutputDir = convOutput.value;
    var editorOutput = document.getElementById('editor-output-path');
    if (editorOutput) state.editorOutputDir = editorOutput.value;

    return fetch('/api/save-state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state)
    }).then(function(r) { return r.json(); }).catch(function() { return {}; });
}

function restoreAppState() {
    fetch('/api/restore-state')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data || !data.state) return;
            var s = data.state;

            // 恢复 tab
            if (s.activeTab && typeof switchTab === 'function') {
                switchTab(s.activeTab);
            }

            // 恢复输出目录
            if (s.converterOutputDir) {
                var convOutput = document.getElementById('output-path');
                if (convOutput) convOutput.value = s.converterOutputDir;
            }
            if (s.editorOutputDir) {
                var editorOutput = document.getElementById('editor-output-path');
                if (editorOutput) editorOutput.value = s.editorOutputDir;
            }

            // 恢复重命名工具状态
            if (s.rename && typeof window.renameRestoreState === 'function') {
                window.renameRestoreState(s.rename);
            }
        })
        .catch(function() {});
}
