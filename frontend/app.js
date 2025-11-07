// LS-DYNA 参数化系统 - 前端脚本

// API基础URL
const API_BASE = 'http://localhost:8000/api';

// 预设配置
const PRESETS = {
    default: {
        velocity_z: 1600,
        bullet_yield_stress: 1000,
        target_yield_stress: 800,
        friction_static: 0.25,
        friction_dynamic: 0.18,
        simulation_endtime: 30
    },
    low_speed: {
        velocity_z: 800,
        bullet_yield_stress: 1000,
        target_yield_stress: 600,
        friction_static: 0.3,
        friction_dynamic: 0.2,
        simulation_endtime: 60
    },
    high_speed: {
        velocity_z: 2500,
        bullet_yield_stress: 1500,
        target_yield_stress: 800,
        friction_static: 0.2,
        friction_dynamic: 0.15,
        simulation_endtime: 20
    },
    soft_target: {
        velocity_z: 1600,
        bullet_yield_stress: 1000,
        target_yield_stress: 300,
        friction_static: 0.25,
        friction_dynamic: 0.18,
        simulation_endtime: 30
    },
    hard_target: {
        velocity_z: 1600,
        bullet_yield_stress: 1500,
        target_yield_stress: 1000,
        friction_static: 0.25,
        friction_dynamic: 0.18,
        simulation_endtime: 30
    }
};

// Toast通知
function showToast(title, message, type = 'info') {
    const toastEl = document.getElementById('toast');
    const toastTitle = document.getElementById('toastTitle');
    const toastBody = document.getElementById('toastBody');

    toastTitle.textContent = title;
    toastBody.textContent = message;

    // 移除旧的样式类
    toastEl.classList.remove('bg-success', 'bg-danger', 'bg-warning', 'bg-info', 'text-white');

    // 添加新的样式
    if (type === 'success' || type === 'error') {
        toastEl.classList.add('text-white');
    }
    if (type === 'success') {
        toastEl.classList.add('bg-success');
    } else if (type === 'error') {
        toastEl.classList.add('bg-danger');
    } else if (type === 'warning') {
        toastEl.classList.add('bg-warning');
    }

    const toast = new bootstrap.Toast(toastEl);
    toast.show();
}

// 获取表单数据
function getFormData() {
    const form = document.getElementById('paramForm');
    const formData = new FormData(form);
    const data = {};

    for (let [key, value] of formData.entries()) {
        data[key] = parseFloat(value);
    }

    return data;
}

// 设置表单数据
function setFormData(data) {
    for (let [key, value] of Object.entries(data)) {
        const input = document.getElementById(key);
        if (input) {
            input.value = value;
        }
    }
}

// 验证参数
async function validateParameters() {
    const data = getFormData();
    const validationSummary = document.getElementById('validationSummary');
    const validationMessage = document.getElementById('validationMessage');

    try {
        const response = await fetch(`${API_BASE}/validate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();

        validationSummary.classList.remove('d-none', 'alert-success', 'alert-danger', 'alert-warning');

        if (result.valid) {
            validationSummary.classList.add('alert-success');
            validationMessage.innerHTML = '<i class="bi bi-check-circle-fill"></i> 参数验证通过！';
        } else if (result.warnings && result.warnings.length > 0) {
            validationSummary.classList.add('alert-warning');
            validationMessage.innerHTML = '<i class="bi bi-exclamation-triangle-fill"></i> ' +
                                         result.warnings.join('<br>');
        } else {
            validationSummary.classList.add('alert-danger');
            validationMessage.innerHTML = '<i class="bi bi-x-circle-fill"></i> ' +
                                         result.errors.join('<br>');
        }

        return result.valid;
    } catch (error) {
        console.error('验证失败:', error);
        showToast('错误', '参数验证失败: ' + error.message, 'error');
        return false;
    }
}

// 生成K文件
async function generateKFile() {
    const data = getFormData();
    const generateBtn = document.getElementById('generateBtn');

    // 禁用按钮，显示加载状态
    generateBtn.disabled = true;
    generateBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>生成中...';

    try {
        const response = await fetch(`${API_BASE}/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail.message || error.detail);
        }

        const result = await response.json();

        // 显示成功消息
        showToast('成功', result.message, 'success');

        // 如果有警告信息，额外显示
        if (result.warnings && result.warnings.length > 0) {
            setTimeout(() => {
                const warningMsg = '注意:\n' + result.warnings.join('\n');
                showToast('警告', warningMsg, 'warning');
            }, 1000);
        }

        // 刷新历史记录
        await loadHistory();

        // 自动下载
        downloadFile(result.filename);

    } catch (error) {
        console.error('生成失败:', error);
        showToast('错误', '生成K文件失败: ' + error.message, 'error');
    } finally {
        // 恢复按钮
        generateBtn.disabled = false;
        generateBtn.innerHTML = '<i class="bi bi-file-earmark-arrow-down"></i> 生成K文件';
    }
}

// 下载文件
function downloadFile(filename) {
    const url = `${API_BASE}/download/${filename}`;
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

// 删除文件
async function deleteFile(filename) {
    if (!confirm(`确定要删除文件 "${filename}" 吗？`)) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/files/${filename}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            throw new Error('删除失败');
        }

        showToast('成功', '文件已删除', 'success');
        await loadHistory();

    } catch (error) {
        console.error('删除失败:', error);
        showToast('错误', '删除文件失败: ' + error.message, 'error');
    }
}

// 加载生成历史
async function loadHistory() {
    try {
        const response = await fetch(`${API_BASE}/files`);
        const files = await response.json();

        const tbody = document.getElementById('historyTableBody');

        if (files.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="text-center text-muted">暂无生成记录</td></tr>';
            return;
        }

        tbody.innerHTML = files.map(file => `
            <tr>
                <td>${file.created}</td>
                <td>${file.metadata.velocity_z || '-'}</td>
                <td>${file.metadata.bullet_yield_stress || '-'}</td>
                <td>${file.metadata.target_yield_stress || '-'}</td>
                <td>${file.metadata.friction_static || '-'}</td>
                <td>${file.metadata.simulation_endtime || '-'}</td>
                <td>${(file.size / 1024 / 1024).toFixed(2)} MB</td>
                <td>
                    <button class="btn btn-sm btn-primary me-1" onclick="downloadFile('${file.filename}')">
                        <i class="bi bi-download"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteFile('${file.filename}')">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            </tr>
        `).join('');

    } catch (error) {
        console.error('加载历史失败:', error);
    }
}

// 格式化文件大小
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(2) + ' KB';
    return (bytes / 1024 / 1024).toFixed(2) + ' MB';
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 预设选择器
    document.getElementById('presetSelector').addEventListener('change', function(e) {
        const preset = PRESETS[e.target.value];
        if (preset) {
            setFormData(preset);
            showToast('提示', '已加载预设配置', 'info');
        }
    });

    // 重置按钮
    document.getElementById('resetBtn').addEventListener('click', function() {
        setFormData(PRESETS.default);
        document.getElementById('validationSummary').classList.add('d-none');
    });

    // 验证按钮
    document.getElementById('validateBtn').addEventListener('click', validateParameters);

    // 表单提交
    document.getElementById('paramForm').addEventListener('submit', function(e) {
        e.preventDefault();
        generateKFile();
    });

    // 实时验证（输入变化时）
    const inputs = document.querySelectorAll('input[type="number"]');
    inputs.forEach(input => {
        input.addEventListener('change', function() {
            // 清空旧的验证消息
            const errorDiv = document.getElementById(this.id + '_error');
            if (errorDiv) {
                errorDiv.textContent = '';
            }
            this.classList.remove('is-invalid');
        });
    });

    // 加载历史记录
    loadHistory();

    // 定期刷新历史（每30秒）
    setInterval(loadHistory, 30000);
});
