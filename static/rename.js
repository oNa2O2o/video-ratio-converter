/**
 * 素材重命名工具 - 前端逻辑（纯本地版，无 AI 依赖）
 * 流程：拖拽上传 → 服务端检测分辨率+本地解析文件名 → 手动校对 → 导出
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
    // DOM 元素
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

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 应用状态
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    let files = [];
    let lastOutputDir = '';

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 初始化
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function init() {
        const now = new Date();
        const yy = String(now.getFullYear()).slice(2);
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        cfgDate.value = `${yy}${mm}${dd}`;

        populateSelect(cfgRegion, REGIONS.map(r => ({
            value: r.value, label: `${r.label} (${r.value})`
        })), 'JP');

        populateSelect(cfgPlatform, PLATFORMS.map(p => ({
            value: p, label: p
        })), 'GG');

        populateSelect(cfgCreator, CREATORS.map(c => ({
            value: c.value, label: `${c.label} (${c.value})`
        })), 'ZHM');
    }

    function populateSelect(select, options, defaultValue) {
        select.innerHTML = options.map(o =>
            `<option value="${o.value}" ${o.value === defaultValue ? 'selected' : ''}>${o.label}</option>`
        ).join('');
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 全局配置变更 → 同步更新所有素材
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    [cfgDate, cfgRegion, cfgPlatform, cfgCreator].forEach(el => {
        el.addEventListener('change', () => {
            files.forEach(f => {
                f.date = cfgDate.value;
                f.region = cfgRegion.value;
                if (!f.detectedPlatform) f.platform = cfgPlatform.value;
                f.creator = cfgCreator.value;
            });
            renderFiles();
        });
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 拖拽上传
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('drag-over'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
    dropZone.addEventListener('drop', e => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
    });
    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) handleFiles(fileInput.files);
        fileInput.value = '';
    });

    clearBtn.addEventListener('click', () => {
        files = [];
        fileItems.innerHTML = '';
        fileListSection.style.display = 'none';
        resultsSection.style.display = 'none';
    });

    browseOutputBtn.addEventListener('click', async () => {
        try {
            const resp = await fetch('/browse-folder', { method: 'POST' });
            const data = await resp.json();
            if (data.path) outputPathInput.value = data.path;
        } catch (err) { alert('浏览失败: ' + err.message); }
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 文件上传 → 服务端返回分辨率 + 本地解析结果
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    async function handleFiles(fileObjs) {
        fileListSection.style.display = 'block';
        resultsSection.style.display = 'none';

        const formData = new FormData();
        for (const f of fileObjs) formData.append('files', f);

        try {
            const resp = await fetch('/api/upload-for-rename', { method: 'POST', body: formData });
            const data = await resp.json();
            if (data.error) { alert(data.error); return; }

            for (const sf of data.files) {
                const ext = sf.original_name.split('.').pop().toLowerCase();
                const p = sf.parsed || {};

                // 从解析结果和全局配置合并
                const fileObj = {
                    id: sf.file_id,
                    originalName: sf.original_name,
                    serverPath: sf.path,
                    width: sf.width,
                    height: sf.height,
                    ext: ext,
                    // 优先用解析到的值，否则用全局配置
                    date: p.date || cfgDate.value,
                    region: p.region || cfgRegion.value,
                    property: p.property || '原创',
                    audience: p.audience || '男性向',
                    assetName: p.assetName || '',
                    platform: p.platform || cfgPlatform.value,
                    creator: p.creator || cfgCreator.value,
                    ratio: sf.ratio_label || p.ratio || '横',
                    version: p.version || '1',
                    detectedPlatform: p.platform || '',
                    status: 'done'
                };
                files.push(fileObj);
            }
            renderFiles();
        } catch (err) {
            alert('上传失败: ' + err.message);
        }
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 文件名生成
    // {日期}-{地区}-{属性}-{受众}-{核心词}-{平台}-{制作人}-{比例}-{版本}.{后缀}
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function generateFilename(f) {
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

            const resText = f.width > 0 ? `${f.width}×${f.height}` : '';

            card.innerHTML = `
                <button class="rename-card-delete" data-idx="${idx}" title="移除">&times;</button>
                <div class="rename-card-header">
                    <span>
                        <span class="rename-card-original">${escapeHtml(f.originalName)}</span>
                        <span class="rename-card-resolution">${resText}</span>
                    </span>
                    <span class="rename-card-status status-done">就绪</span>
                </div>
                <div class="rename-card-fields">
                    <div class="rename-field rename-field-asset-name">
                        <label>核心词</label>
                        <input type="text" value="${escapeAttr(f.assetName)}"
                               data-idx="${idx}" data-field="assetName"
                               placeholder="输入素材核心描述">
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

        bindCardEvents();
    }

    function bindCardEvents() {
        // 事件委托
        fileItems.onchange = fileItems.oninput = (e) => {
            const t = e.target;
            const idx = parseInt(t.dataset.idx);
            const field = t.dataset.field;
            if (field !== undefined && files[idx]) {
                files[idx][field] = t.value;
                updatePreview(idx);
            }
        };

        fileItems.querySelectorAll('.rename-card-delete').forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                files.splice(parseInt(btn.dataset.idx), 1);
                renderFiles();
                if (!files.length) fileListSection.style.display = 'none';
            };
        });
    }

    function updatePreview(idx) {
        const preview = fileItems.querySelector(`.rename-card-preview[data-idx="${idx}"]`);
        if (preview && files[idx]) preview.textContent = generateFilename(files[idx]);
    }

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 导出
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    exportBtn.addEventListener('click', async () => {
        const validFiles = files.filter(f => f.serverPath);
        if (!validFiles.length) { alert('没有可导出的文件'); return; }

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
            if (data.error) { alert(data.error); return; }

            lastOutputDir = data.output_dir || '';
            resultsSection.style.display = 'block';
            resultItems.innerHTML = '';
            errorItems.innerHTML = '';

            (data.results || []).forEach(r => {
                const div = document.createElement('div');
                div.className = 'result-item';
                div.innerHTML = `<span class="file-name">${escapeHtml(r.filename)}</span>`;
                resultItems.appendChild(div);
            });

            (data.errors || []).forEach(e => {
                const div = document.createElement('div');
                div.className = 'error-item';
                div.textContent = `${e.filename}: ${e.error}`;
                errorItems.appendChild(div);
            });

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

    openFolderBtn.addEventListener('click', async () => {
        try {
            await fetch('/open-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: lastOutputDir })
            });
        } catch (err) { alert('无法打开文件夹: ' + err.message); }
    });

    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    // 工具函数
    // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    function escapeHtml(str) {
        if (!str) return '';
        const d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    function escapeAttr(str) {
        if (!str) return '';
        return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    init();
});
