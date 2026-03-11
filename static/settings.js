/**
 * 设置页面交互逻辑
 */
document.addEventListener('DOMContentLoaded', () => {

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

    const creatorList = document.getElementById('settings-creator-list');
    const addBtn = document.getElementById('settings-add-btn');
    const newNameInput = document.getElementById('settings-new-name');
    const newCodeInput = document.getElementById('settings-new-code');
    const saveBtn = document.getElementById('settings-save-btn');
    const statusEl = document.getElementById('settings-status');
    const defaultRegion = document.getElementById('settings-default-region');
    const defaultPlatform = document.getElementById('settings-default-platform');
    const defaultCreator = document.getElementById('settings-default-creator');

    if (!creatorList) return;

    let creators = [];

    function loadSettings() {
        fetch('/api/config')
            .then(r => r.json())
            .then(cfg => {
                creators = cfg.creators || [];
                renderCreators();

                // 填充默认参数下拉框
                fillSelect(defaultRegion, REGIONS.map(r => ({
                    value: r.value, label: r.label + ' (' + r.value + ')'
                })), cfg.defaultRegion || 'JP');

                fillSelect(defaultPlatform, PLATFORMS.map(p => ({
                    value: p, label: p
                })), cfg.defaultPlatform || 'GG');

                refreshCreatorSelect(cfg.defaultCreator || 'ZHM');
            })
            .catch(() => {
                statusEl.textContent = '加载配置失败';
                statusEl.style.color = '#f87171';
            });
    }

    function fillSelect(sel, options, defaultVal) {
        sel.innerHTML = options.map(o =>
            '<option value="' + o.value + '"' + (o.value === defaultVal ? ' selected' : '') + '>' + o.label + '</option>'
        ).join('');
    }

    function refreshCreatorSelect(defaultVal) {
        fillSelect(defaultCreator, creators.map(c => ({
            value: c.value, label: c.label + ' (' + c.value + ')'
        })), defaultVal);
    }

    function renderCreators() {
        creatorList.innerHTML = '';
        creators.forEach((c, idx) => {
            const row = document.createElement('div');
            row.className = 'settings-creator-row';
            row.innerHTML =
                '<span class="settings-creator-name">' + escapeHtml(c.label) + '</span>' +
                '<span class="settings-creator-code">' + escapeHtml(c.value) + '</span>' +
                '<button class="settings-creator-del" data-idx="' + idx + '">&times;</button>';
            creatorList.appendChild(row);
        });

        creatorList.querySelectorAll('.settings-creator-del').forEach(btn => {
            btn.onclick = () => {
                creators.splice(parseInt(btn.dataset.idx), 1);
                renderCreators();
                refreshCreatorSelect(defaultCreator.value);
            };
        });
    }

    addBtn.addEventListener('click', () => {
        const name = newNameInput.value.trim();
        const code = newCodeInput.value.trim().toUpperCase();
        if (!name || !code) { alert('请填写姓名和缩写'); return; }
        if (creators.some(c => c.value === code)) { alert('缩写已存在'); return; }
        creators.push({ label: name, value: code });
        newNameInput.value = '';
        newCodeInput.value = '';
        renderCreators();
        refreshCreatorSelect(defaultCreator.value);
    });

    saveBtn.addEventListener('click', () => {
        saveBtn.disabled = true;
        saveBtn.textContent = '保存中...';
        statusEl.textContent = '';

        const data = {
            creators: creators,
            defaultRegion: defaultRegion.value,
            defaultPlatform: defaultPlatform.value,
            defaultCreator: defaultCreator.value
        };

        fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
        .then(r => r.json())
        .then(resp => {
            if (resp.ok) {
                statusEl.textContent = '保存成功！';
                statusEl.style.color = '#6ee7b7';
                setTimeout(() => { statusEl.textContent = ''; }, 2000);
            } else {
                statusEl.textContent = '保存失败: ' + (resp.error || '未知错误');
                statusEl.style.color = '#f87171';
            }
        })
        .catch(err => {
            statusEl.textContent = '保存失败: ' + err.message;
            statusEl.style.color = '#f87171';
        })
        .finally(() => {
            saveBtn.disabled = false;
            saveBtn.textContent = '保存设置';
        });
    });

    function escapeHtml(str) {
        if (!str) return '';
        var d = document.createElement('div');
        d.textContent = str;
        return d.innerHTML;
    }

    loadSettings();
});
