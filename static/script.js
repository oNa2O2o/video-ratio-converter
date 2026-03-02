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

    openFolderBtn.addEventListener('click', async () => {
        try {
            await fetch('/open-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: lastOutputDir })
            });
        } catch (err) {
            alert('无法打开文件夹: ' + err.message);
        }
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
});
