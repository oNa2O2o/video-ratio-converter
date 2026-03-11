/**
 * 视频编辑 - 导出最后一帧
 */
document.addEventListener('DOMContentLoaded', function() {
    var dropZone = document.getElementById('editor-drop-zone');
    var fileInput = document.getElementById('editor-file-input');
    var fileInfo = document.getElementById('editor-file-info');
    var filenameEl = document.getElementById('editor-filename');
    var extractBtn = document.getElementById('editor-extract-btn');
    var resultSection = document.getElementById('editor-result');
    var resultText = document.getElementById('editor-result-text');
    var outputPathInput = document.getElementById('editor-output-path');
    var browseBtn = document.getElementById('editor-browse-output-btn');
    var openFolderBtn = document.getElementById('editor-open-output-folder-btn');
    var openOutputFolderBtn = document.getElementById('editor-open-folder-btn');

    if (!dropZone || !fileInput) return;

    var currentFile = null;

    function openEditorOutputFolder() {
        var path = (outputPathInput && outputPathInput.value.trim()) || '';
        return fetch('/open-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: path || '' })
        }).then(function(r) { return r.json(); }).then(function(data) {
            if (data.error) throw new Error(data.error);
        });
    }

    dropZone.addEventListener('click', function() { fileInput.click(); });
    dropZone.addEventListener('dragover', function(e) { e.preventDefault(); dropZone.classList.add('drag-over'); });
    dropZone.addEventListener('dragleave', function() { dropZone.classList.remove('drag-over'); });
    dropZone.addEventListener('drop', function(e) {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', function() {
        if (fileInput.files.length) setFile(fileInput.files[0]);
        fileInput.value = '';
    });

    function setFile(file) {
        if (!file || !file.name.match(/\.(mp4|avi|mov|mkv|wmv|flv|webm|m4v|mpg|mpeg)$/i)) {
            alert('请选择视频文件');
            return;
        }
        currentFile = file;
        filenameEl.textContent = file.name;
        fileInfo.style.display = 'block';
        resultSection.style.display = 'none';
    }

    if (extractBtn) {
        extractBtn.addEventListener('click', function() {
            if (!currentFile) {
                alert('请先选择视频');
                return;
            }
            extractBtn.disabled = true;
            extractBtn.textContent = '导出中...';
            var formData = new FormData();
            formData.append('file', currentFile);
            if (outputPathInput && outputPathInput.value.trim())
                formData.append('output_dir', outputPathInput.value.trim());

            fetch('/api/video-editor/extract-last-frame', {
                method: 'POST',
                body: formData
            })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.error) throw new Error(data.error);
                    resultSection.style.display = 'block';
                    var msg = '已保存：' + data.filename;
                    if (data.clipboard) msg += '，已复制到剪贴板';
                    else msg += '（剪贴板仅支持 Windows 本机）';
                    resultText.textContent = msg;
                })
                .catch(function(err) {
                    alert('导出失败：' + (err.message || err));
                })
                .finally(function() {
                    extractBtn.disabled = false;
                    extractBtn.textContent = '导出最后一帧并复制到剪贴板';
                });
        });
    }

    if (browseBtn) {
        browseBtn.addEventListener('click', function() {
            fetch('/browse-folder', { method: 'POST' })
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (data.path && outputPathInput) outputPathInput.value = data.path;
                })
                .catch(function(err) { alert('浏览失败：' + err.message); });
        });
    }

    if (openFolderBtn) openFolderBtn.addEventListener('click', function() {
        openEditorOutputFolder().catch(function(err) { alert('无法打开文件夹：' + err.message); });
    });
    if (openOutputFolderBtn) openOutputFolderBtn.addEventListener('click', function() {
        openEditorOutputFolder().catch(function(err) { alert('无法打开文件夹：' + err.message); });
    });
});
