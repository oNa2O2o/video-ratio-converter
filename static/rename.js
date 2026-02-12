/**
 * 素材重命名工具 - 前端逻辑
 * 功能：拖拽上传 → AI 智能分析 → 字段编辑 → 标准化命名 → 导出
 */
document.addEventListener('DOMContentLoaded', () => {

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 业务常量
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const REGIONS = [
        { label: '日本', value: 'JP' },
        { label: '台湾', value: 'TC' },
        { label: '英语', value: 'EN' },
        { label: '泰国', value: 'TH' },
        { label: '韩国', value: 'KR' },
        { label: '越南', value: 'VN' },
        { label: '印尼', value: 'ID' },
        { label: '西语', value: 'ES' }
    ];

    const PLATFORMS = ['FB', 'GG', 'TT'];
    const PROPERTIES = ['原创', '迭代', '竞品二创'];
    const AUDIENCES = ['男性向', '女性向'];
    const RATIOS = ['竖', '方', '横'];

    const CREATORS = [
        { label: '钟海明', value: 'ZHM' },
        { label: '杨懿', value: 'YY' },
        { label: '赵晟悦', value: 'ZSY' },
        { label: '高娇阳', value: 'GJY' },
        { label: '杨皓然', value: 'YHR' },
        { label: '盛妍', value: 'SY' },
        { label: '董慧媛', value: 'DHY' },
        { label: '常广瑜', value: 'CGY' },
        { label: '乔翾宇', value: 'QXY' }
    ];

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // DOM 元素引用
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    const dropZone = document.getElementById('rename-drop-zone');
    const fileInput = document.getElementById('rename-file-input');
    const fileListSection = document.getElementById('rename-file-list');
    const fileItems = document.getElementById('rename-file-items');
    const fileCount = document.getElementById('file-count');
    const clearBtn = document.getElementById('rename-clear-btn');
    const exportBtn = document.getElementById('rename-export-btn');
    const resultsSection = document.getElementById('rename-results');
    const resultItems = document.getElementById('rename-result-items');
    const errorItems = document.getElementById('rename-error-items');
    const openFolderBtn = document.getElementById('rename-open-folder-btn');
    const outputPathInput = document.getElementById('rename-output-path');
    const browseOutputBtn = document.getElementById('rename-browse-output-btn');

    const cfgDate = document.getElementById('cfg-date');
    const cfgRegion = document.getElementById('cfg-region');
    const cfgPlatform = document.getElementById('cfg-platform');
    const cfgCreator = document.getElementById('cfg-creator');
    const cfgApiKey = document.getElementById('cfg-api-key');
    const saveApiKeyBtn = document.getElementById('save-api-key');
    const toggleKeyVisBtn = document.getElementById('toggle-key-vis');
    const apiKeyStatus = document.getElementById('api-key-status');

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 应用状态
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    let files = [];
    let lastOutputDir = '';

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 初始化
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function init() {
        // 设置日期为今天 YYMMDD
        const now = new Date();
        const yy = String(now.getFullYear()).slice(2);
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        cfgDate.value = `${yy}${mm}${dd}`;

        // 填充下拉选项
        populateSelect(cfgRegion, REGIONS.map(r => ({
            value: r.value, label: `${r.label} (${r.value})`
        })), 'JP');

        populateSelect(cfgPlatform, PLATFORMS.map(p => ({
            value: p, label: p
        })), 'GG');

        populateSelect(cfgCreator, CREATORS.map(c => ({
            value: c.value, label: `${c.label} (${c.value})`
        })), 'ZHM');

        // 加载已保存的 API Key
        loadSavedApiKey();
    }

    function populateSelect(select, options, defaultValue) {
        select.innerHTML = options.map(o =>
            `<option value="${o.value}" ${o.value === defaultValue ? 'selected' : ''}>${o.label}</option>`
        ).join('');
    }

    async function loadSavedApiKey() {
        try {
            const resp = await fetch('/api/load-api-key');
            const data = await resp.json();
            if (data.has_key) {
                cfgApiKey.value = data.key;
                apiKeyStatus.textContent = '已保存';
                apiKeyStatus.className = 'config-hint success';
            }
        } catch (_) {
            // 忽略
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // API Key 管理
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    saveApiKeyBtn.addEventListener('click', async () => {
        const key = cfgApiKey.value.trim();
        if (!key) {
            apiKeyStatus.textContent = '请输入 API Key';
            apiKeyStatus.className = 'config-hint error';
            return;
        }
        try {
            await fetch('/api/save-api-key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key })
            });
            apiKeyStatus.textContent = '已保存';
            apiKeyStatus.className = 'config-hint success';
        } catch (err) {
            apiKeyStatus.textContent = '保存失败';
            apiKeyStatus.className = 'config-hint error';
        }
    });

    toggleKeyVisBtn.addEventListener('click', () => {
        const isPassword = cfgApiKey.type === 'password';
        cfgApiKey.type = isPassword ? 'text' : 'password';
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 全局配置变更 → 同步更新所有素材
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    [cfgDate, cfgRegion, cfgPlatform, cfgCreator].forEach(el => {
        el.addEventListener('change', () => {
            files.forEach(f => {
                f.date = cfgDate.value;
                f.region = cfgRegion.value;
                // 仅当没有从 AI 检测到平台时才同步
                if (!f.detectedPlatform) {
                    f.platform = cfgPlatform.value;
                }
                f.creator = cfgCreator.value;
            });
            renderFiles();
        });
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 拖拽上传
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
        if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) handleFiles(fileInput.files);
        fileInput.value = '';
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 清空列表
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    clearBtn.addEventListener('click', () => {
        files = [];
        fileItems.innerHTML = '';
        fileListSection.style.display = 'none';
        resultsSection.style.display = 'none';
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 浏览输出目录
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    browseOutputBtn.addEventListener('click', async () => {
        try {
            const resp = await fetch('/browse-folder', { method: 'POST' });
            const data = await resp.json();
            if (data.path) outputPathInput.value = data.path;
        } catch (err) {
            alert('浏览失败: ' + err.message);
        }
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 文件上传与分析
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    async function handleFiles(fileObjs) {
        fileListSection.style.display = 'block';
        resultsSection.style.display = 'none';

        const formData = new FormData();
        const newFileEntries = [];

        for (const f of fileObjs) {
            formData.append('files', f);
            newFileEntries.push(f.name);
        }

        // 先添加占位卡片（状态：分析中）
        const tempIds = [];
        for (const name of newFileEntries) {
            const ext = name.split('.').pop().toLowerCase();
            const tempFile = {
                id: 'temp-' + Date.now() + '-' + Math.random().toString(36).slice(2),
                originalName: name,
                status: 'analyzing',
                date: cfgDate.value,
                region: cfgRegion.value,
                platform: cfgPlatform.value,
                creator: cfgCreator.value,
                assetName: '',
                audience: '男性向',
                property: '原创',
                ratio: '横',
                version: '1',
                ext: ext,
                detectedPlatform: '',
                serverPath: '',
                width: 0,
                height: 0
            };
            files.push(tempFile);
            tempIds.push(tempFile.id);
        }
        renderFiles();

        // 1. 上传文件到服务器
        let serverFiles;
        try {
            const resp = await fetch('/api/upload-for-rename', {
                method: 'POST',
                body: formData
            });
            const data = await resp.json();

            if (data.error) {
                markTempFilesError(tempIds, data.error);
                return;
            }
            serverFiles = data.files;
        } catch (err) {
            markTempFilesError(tempIds, '上传失败: ' + err.message);
            return;
        }

        // 2. 更新服务器返回的元数据
        for (let i = 0; i < serverFiles.length; i++) {
            const sf = serverFiles[i];
            const tempId = tempIds[i];
            const fileObj = files.find(f => f.id === tempId);
            if (!fileObj) continue;

            fileObj.serverId = sf.file_id;
            fileObj.serverPath = sf.path;
            fileObj.width = sf.width;
            fileObj.height = sf.height;
            fileObj.ratio = sf.ratio_label;
        }
        renderFiles();

        // 3. 批量调用 AI 分析
        const apiKey = cfgApiKey.value.trim();
        const batchItems = serverFiles.map((sf, i) => ({
            file_id: tempIds[i],
            filename: newFileEntries[i],
            width: sf.width,
            height: sf.height
        }));

        try {
            const resp = await fetch('/api/batch-analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ items: batchItems, api_key: apiKey })
            });
            const data = await resp.json();

            if (data.error) {
                markTempFilesError(tempIds, data.error);
                return;
            }

            // 更新每个文件的分析结果
            for (const result of data.results) {
                const fileObj = files.find(f => f.id === result.file_id);
                if (!fileObj) continue;

                if (result.success) {
                    fileObj.assetName = result.assetName || '';
                    fileObj.audience = result.audience || '男性向';
                    fileObj.property = result.property || '原创';
                    if (result.platform) {
                        fileObj.platform = result.platform;
                        fileObj.detectedPlatform = result.platform;
                    }
                    fileObj.status = 'done';
                } else {
                    fileObj.status = 'error';
                    fileObj.errorMsg = result.error || '分析失败';
                }
            }
        } catch (err) {
            markTempFilesError(tempIds, 'AI 分析失败: ' + err.message);
            return;
        }

        renderFiles();
    }

    function markTempFilesError(tempIds, errorMsg) {
        tempIds.forEach(id => {
            const f = files.find(f => f.id === id);
            if (f) {
                f.status = 'error';
                f.errorMsg = errorMsg;
            }
        });
        renderFiles();
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 文件名生成
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function generateFilename(f) {
        // {日期}-{地区}-{属性}-{受众}-{核心词}-{平台}-{制作人}-{比例}-{迭代版本}.{后缀}
        const parts = [
            f.date || '000000',
            f.region || 'JP',
            f.property || '原创',
            f.audience || '男性向',
            (f.assetName || '未命名').replace(/\s+/g, ' ').trim(),
            f.platform || 'GG',
            f.creator || 'ZHM',
            f.ratio || '横',
            f.version || '1'
        ];
        return parts.join('-') + '.' + (f.ext || 'mp4');
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 渲染文件列表
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function renderFiles() {
        fileItems.innerHTML = '';
        fileCount.textContent = files.length > 0 ? `(${files.length} 个)` : '';

        files.forEach((f, idx) => {
            const card = document.createElement('div');
            card.className = 'rename-card';
            card.dataset.idx = idx;

            const statusClass = f.status === 'analyzing' ? 'status-analyzing' :
                                f.status === 'done' ? 'status-done' : 'status-error';
            const statusText = f.status === 'analyzing' ? '分析中...' :
                              f.status === 'done' ? '就绪' : '错误';
            const resText = f.width > 0 ? `${f.width}×${f.height}` : '';

            card.innerHTML = `
                <button class="rename-card-delete" data-idx="${idx}" title="移除">&times;</button>
                <div class="rename-card-header">
                    <span>
                        <span class="rename-card-original">${escapeHtml(f.originalName)}</span>
                        <span class="rename-card-resolution">${resText}</span>
                    </span>
                    <span class="rename-card-status ${statusClass}">${statusText}</span>
                </div>
                ${f.status === 'error' ? `<div class="error-item" style="margin-bottom:12px">${escapeHtml(f.errorMsg || '分析失败')}</div>` : ''}
                <div class="rename-card-fields">
                    <div class="rename-field rename-field-asset-name">
                        <label>核心词</label>
                        <input type="text" value="${escapeHtml(f.assetName)}"
                               data-idx="${idx}" data-field="assetName"
                               placeholder="AI 提取的核心描述">
                    </div>
                    <div class="rename-field">
                        <label>受众</label>
                        <select data-idx="${idx}" data-field="audience">
                            ${AUDIENCES.map(a => `<option value="${a}" ${a === f.audience ? 'selected' : ''}>${a}</option>`).join('')}
                        </select>
                    </div>
                    <div class="rename-field">
                        <label>属性</label>
                        <select data-idx="${idx}" data-field="property">
                            ${PROPERTIES.map(p => `<option value="${p}" ${p === f.property ? 'selected' : ''}>${p}</option>`).join('')}
                        </select>
                    </div>
                    <div class="rename-field">
                        <label>平台</label>
                        <select data-idx="${idx}" data-field="platform">
                            ${PLATFORMS.map(p => `<option value="${p}" ${p === f.platform ? 'selected' : ''}>${p}</option>`).join('')}
                        </select>
                    </div>
                    <div class="rename-field">
                        <label>比例</label>
                        <select data-idx="${idx}" data-field="ratio">
                            ${RATIOS.map(r => `<option value="${r}" ${r === f.ratio ? 'selected' : ''}>${r}</option>`).join('')}
                        </select>
                    </div>
                    <div class="rename-field rename-field-version">
                        <label>版本</label>
                        <input type="number" value="${f.version}"
                               data-idx="${idx}" data-field="version"
                               min="1" max="99">
                    </div>
                </div>
                <div class="rename-card-preview" data-idx="${idx}">${escapeHtml(generateFilename(f))}</div>
            `;

            fileItems.appendChild(card);
        });

        // 绑定编辑事件（使用事件委托）
        bindCardEvents();
    }

    function bindCardEvents() {
        // 使用事件委托：所有 input/select 变更
        fileItems.onchange = (e) => {
            const target = e.target;
            const idx = parseInt(target.dataset.idx);
            const field = target.dataset.field;
            if (field !== undefined && files[idx]) {
                files[idx][field] = target.value;
                updatePreview(idx);
            }
        };

        fileItems.oninput = (e) => {
            const target = e.target;
            if (target.tagName === 'INPUT') {
                const idx = parseInt(target.dataset.idx);
                const field = target.dataset.field;
                if (field !== undefined && files[idx]) {
                    files[idx][field] = target.value;
                    updatePreview(idx);
                }
            }
        };

        // 删除按钮
        fileItems.querySelectorAll('.rename-card-delete').forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                const idx = parseInt(btn.dataset.idx);
                files.splice(idx, 1);
                renderFiles();
                if (files.length === 0) {
                    fileListSection.style.display = 'none';
                }
            };
        });
    }

    function updatePreview(idx) {
        const preview = fileItems.querySelector(`.rename-card-preview[data-idx="${idx}"]`);
        if (preview && files[idx]) {
            preview.textContent = generateFilename(files[idx]);
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 导出
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    exportBtn.addEventListener('click', async () => {
        const validFiles = files.filter(f => f.serverPath);
        if (!validFiles.length) {
            alert('没有可导出的文件（请确保文件已上传成功）');
            return;
        }

        exportBtn.disabled = true;
        exportBtn.textContent = '导出中...';

        try {
            const exportData = validFiles.map(f => ({
                server_path: f.serverPath,
                new_filename: generateFilename(f)
            }));

            const resp = await fetch('/api/export-renamed', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    files: exportData,
                    output_dir: outputPathInput.value.trim()
                })
            });
            const data = await resp.json();

            if (data.error) {
                alert(data.error);
                return;
            }

            lastOutputDir = data.output_dir || '';

            // 显示结果
            resultsSection.style.display = 'block';
            resultItems.innerHTML = '';
            errorItems.innerHTML = '';

            if (data.results) {
                data.results.forEach(r => {
                    const div = document.createElement('div');
                    div.className = 'result-item';
                    div.innerHTML = `<span class="file-name">${escapeHtml(r.filename)}</span>`;
                    resultItems.appendChild(div);
                });
            }

            if (data.errors && data.errors.length > 0) {
                data.errors.forEach(e => {
                    const div = document.createElement('div');
                    div.className = 'error-item';
                    div.textContent = `${e.filename}: ${e.error}`;
                    errorItems.appendChild(div);
                });
            }

            // 清空文件列表
            files = [];
            fileItems.innerHTML = '';
            fileListSection.style.display = 'none';

        } catch (err) {
            alert('导出失败: ' + err.message);
        } finally {
            exportBtn.disabled = false;
            exportBtn.textContent = '导出文件';
        }
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 打开输出文件夹
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 工具函数
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function escapeHtml(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // 启动
    init();
});
