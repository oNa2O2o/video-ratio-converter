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

    // 拖拽上传
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
                const targetTags = f.target_labels
                    .map(l => `<span class="tag ${tagClass[l]}">${l}</span>`)
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
                    output_dir: outputPathInput.value.trim()
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
