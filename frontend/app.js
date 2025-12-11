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

    // 动画表单提交
    document.getElementById('animationForm').addEventListener('submit', function(e) {
        e.preventDefault();
        createAnimationTask();
    });

    // 加载动画任务列表
    loadAnimationTasks();

    // 定期刷新动画任务列表（每5秒）
    setInterval(loadAnimationTasks, 5000);
});


// ==================== 动画生成相关函数 ====================

// 活动任务轮询器（存储轮询定时器ID）
const activeTaskPollers = {};

// 创建动画任务
async function createAnimationTask() {
    const btn = document.getElementById('createAnimationBtn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 创建中...';

    try {
        // 获取表单数据
        const d3plotPath = document.getElementById('d3plot_path').value;
        const view = document.getElementById('animation_view').value;
        const fringeVariable = document.getElementById('animation_fringe').value;
        const resolutionStr = document.getElementById('animation_resolution').value;
        const outputFormat = document.getElementById('animation_format').value;
        const startFrame = parseInt(document.getElementById('animation_start_frame').value) || 1;
        const endFrameValue = document.getElementById('animation_end_frame').value;
        const endFrame = endFrameValue ? parseInt(endFrameValue) : null;
        const showAllParts = document.getElementById('show_all_parts').checked;
        const showLegend = document.getElementById('show_legend').checked;
        const showTriad = document.getElementById('show_triad').checked;

        const resolution = resolutionStr.split(',').map(v => parseInt(v));

        const requestData = {
            d3plot_path: d3plotPath,
            view: view,
            fringe_variable: fringeVariable,
            resolution: resolution,
            output_format: outputFormat,
            start_frame: startFrame,
            end_frame: endFrame,
            show_all_parts: showAllParts,
            show_legend: showLegend,
            show_triad: showTriad
        };

        const response = await fetch(`${API_BASE}/animation/generate`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || '创建任务失败');
        }

        const task = await response.json();

        showToast('成功', `动画任务已创建！任务ID: ${task.task_id.substring(0, 8)}`, 'success');

        // 清空表单
        document.getElementById('d3plot_path').value = '';

        // 立即刷新任务列表
        await loadAnimationTasks();

        // 开始轮询这个任务的状态
        startTaskPolling(task.task_id);

    } catch (error) {
        showToast('错误', error.message, 'danger');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="bi bi-play-circle"></i> 开始生成动画';
    }
}

// 加载动画任务列表
async function loadAnimationTasks() {
    try {
        const response = await fetch(`${API_BASE}/animation/list`);
        if (!response.ok) {
            // 如果服务未配置，静默失败
            if (response.status === 503) {
                console.log('动画生成功能未配置');
                return;
            }
            throw new Error('获取任务列表失败');
        }

        const tasks = await response.json();
        renderAnimationTasks(tasks);

        // 为处理中的任务启动轮询
        tasks.forEach(task => {
            if (task.status === 'processing' && !activeTaskPollers[task.task_id]) {
                startTaskPolling(task.task_id);
            }
        });

    } catch (error) {
        console.error('加载动画任务列表失败:', error);
    }
}

// 渲染动画任务列表
function renderAnimationTasks(tasks) {
    const container = document.getElementById('animationTasksContainer');

    if (!tasks || tasks.length === 0) {
        container.innerHTML = '<p class="text-center text-muted">暂无动画任务</p>';
        return;
    }

    const html = tasks.map(task => {
        const statusBadge = getStatusBadge(task.status);
        const progressBar = task.status === 'processing' ? `
            <div class="progress mt-2" style="height: 5px;">
                <div class="progress-bar progress-bar-striped progress-bar-animated"
                     role="progressbar"
                     style="width: ${task.progress}%"></div>
            </div>
        ` : '';

        const actions = task.status === 'completed' ? `
            <button class="btn btn-sm btn-primary" onclick="playVideo('${task.task_id}')">
                <i class="bi bi-play-fill"></i> 播放
            </button>
            <button class="btn btn-sm btn-success" onclick="downloadVideo('${task.task_id}')">
                <i class="bi bi-download"></i> 下载
            </button>
        ` : task.status === 'failed' ? `
            <span class="text-danger small">
                <i class="bi bi-exclamation-circle"></i> ${task.error_message || '生成失败'}
            </span>
        ` : `
            <span class="text-muted small">
                <span class="spinner-border spinner-border-sm"></span> 处理中...
            </span>
        `;

        return `
            <div class="card mb-3" id="task-${task.task_id}">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <h6 class="card-subtitle mb-2">
                                <i class="bi bi-film"></i>
                                任务 ${task.task_id.substring(0, 8)}
                                ${statusBadge}
                            </h6>
                            <p class="card-text small text-muted mb-1">
                                <strong>d3plot:</strong> ${task.d3plot_path}
                            </p>
                            <p class="card-text small text-muted mb-1">
                                <strong>视角:</strong> ${task.config.view} |
                                <strong>变量:</strong> ${task.config.fringe_variable} |
                                <strong>分辨率:</strong> ${task.config.resolution[0]}x${task.config.resolution[1]} |
                                <strong>格式:</strong> ${task.config.output_format.toUpperCase()}
                            </p>
                            <p class="card-text small text-muted mb-0">
                                <i class="bi bi-clock"></i> 创建于 ${task.created_at}
                                ${task.completed_at ? ` | 完成于 ${task.completed_at}` : ''}
                            </p>
                            ${progressBar}
                        </div>
                        <div class="ms-3">
                            ${actions}
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// 获取状态徽章
function getStatusBadge(status) {
    const badges = {
        'pending': '<span class="badge bg-secondary">等待中</span>',
        'processing': '<span class="badge bg-primary">处理中</span>',
        'completed': '<span class="badge bg-success">已完成</span>',
        'failed': '<span class="badge bg-danger">失败</span>'
    };
    return badges[status] || '<span class="badge bg-secondary">未知</span>';
}

// 开始轮询任务状态
function startTaskPolling(taskId) {
    // 如果已经在轮询，不重复启动
    if (activeTaskPollers[taskId]) {
        return;
    }

    console.log(`开始轮询任务 ${taskId}`);

    // 每3秒查询一次状态
    const pollerId = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE}/animation/status/${taskId}`);
            if (!response.ok) {
                throw new Error('查询任务状态失败');
            }

            const task = await response.json();

            // 如果任务已完成或失败，停止轮询
            if (task.status === 'completed' || task.status === 'failed') {
                console.log(`任务 ${taskId} 状态: ${task.status}，停止轮询`);
                stopTaskPolling(taskId);

                // 刷新任务列表
                await loadAnimationTasks();

                // 显示通知
                if (task.status === 'completed') {
                    showToast('成功', `动画生成完成！任务 ${taskId.substring(0, 8)}`, 'success');
                } else {
                    showToast('失败', `动画生成失败: ${task.error_message}`, 'danger');
                }
            } else {
                // 更新任务卡片（仅更新进度）
                const taskCard = document.getElementById(`task-${taskId}`);
                if (taskCard) {
                    const progressBar = taskCard.querySelector('.progress-bar');
                    if (progressBar) {
                        progressBar.style.width = `${task.progress}%`;
                    }
                }
            }

        } catch (error) {
            console.error(`轮询任务 ${taskId} 失败:`, error);
            // 出错后停止轮询
            stopTaskPolling(taskId);
        }
    }, 3000);

    activeTaskPollers[taskId] = pollerId;
}

// 停止轮询任务状态
function stopTaskPolling(taskId) {
    if (activeTaskPollers[taskId]) {
        clearInterval(activeTaskPollers[taskId]);
        delete activeTaskPollers[taskId];
        console.log(`停止轮询任务 ${taskId}`);
    }
}

// 播放视频
async function playVideo(taskId) {
    try {
        const response = await fetch(`${API_BASE}/animation/status/${taskId}`);
        if (!response.ok) {
            throw new Error('获取任务信息失败');
        }

        const task = await response.json();

        if (task.status !== 'completed') {
            showToast('提示', '动画尚未完成', 'warning');
            return;
        }

        // 获取输出格式
        const format = task.config.output_format || 'gif';
        const videoUrl = `${API_BASE}/animation/download/${taskId}`;

        // 根据格式选择显示方式
        const modalBody = document.querySelector('#videoModal .modal-body');

        if (format === 'gif') {
            // GIF使用img标签
            modalBody.innerHTML = `
                <img id="gifPlayer" src="${videoUrl}"
                     style="width: 100%; max-height: 70vh; object-fit: contain;"
                     alt="动画预览">
            `;
        } else {
            // AVI/MPEG使用video标签
            const mimeType = format === 'avi' ? 'video/x-msvideo' : 'video/mpeg';
            modalBody.innerHTML = `
                <video id="videoPlayer" controls style="width: 100%; max-height: 70vh;">
                    <source src="${videoUrl}" type="${mimeType}">
                    您的浏览器不支持该视频格式
                </video>
            `;
        }

        // 设置下载链接
        const downloadBtn = document.getElementById('downloadVideoBtn');
        downloadBtn.href = videoUrl;
        downloadBtn.download = `animation_${taskId.substring(0, 8)}.${format}`;

        // 显示模态框
        const videoModal = new bootstrap.Modal(document.getElementById('videoModal'));
        videoModal.show();

        // 如果是视频格式，自动播放
        if (format !== 'gif') {
            setTimeout(() => {
                const player = document.getElementById('videoPlayer');
                if (player) player.play();
            }, 300);
        }

    } catch (error) {
        showToast('错误', error.message, 'danger');
    }
}

// 下载视频
async function downloadVideo(taskId) {
    try {
        // 先获取任务信息以确定文件格式
        const response = await fetch(`${API_BASE}/animation/status/${taskId}`);
        if (!response.ok) {
            throw new Error('获取任务信息失败');
        }

        const task = await response.json();
        const format = task.config.output_format || 'gif';

        const url = `${API_BASE}/animation/download/${taskId}`;
        const a = document.createElement('a');
        a.href = url;
        a.download = `animation_${taskId.substring(0, 8)}.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        showToast('提示', '动画下载已开始', 'info');

    } catch (error) {
        showToast('错误', error.message, 'danger');
    }
}

