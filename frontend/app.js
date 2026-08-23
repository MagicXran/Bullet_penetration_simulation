// LS-DYNA 参数化系统 - 前端脚本
// 简化版：专注于参数输入和任务提交

// API基础URL - 动态获取，自适应任意 IP:Port 配置
// 重要：使用 window.location.origin 自动获取当前访问地址（含端口）
// 不要手动改成硬编码 IP！浏览器会自动知道服务器地址
const API_BASE = `${window.location.origin}/api`;

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
        friction_static: 0.30,
        friction_dynamic: 0.20,
        simulation_endtime: 60
    },
    high_speed: {
        velocity_z: 2500,
        bullet_yield_stress: 1500,
        target_yield_stress: 800,
        friction_static: 0.20,
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

// ==================== 工具函数 ====================

/**
 * 显示Toast通知
 */
function showToast(title, message, type = 'info') {
    const toastEl = document.getElementById('toast');
    if (!toastEl) return;

    const toastTitle = document.getElementById('toastTitle');
    const toastBody = document.getElementById('toastBody');

    toastTitle.textContent = title;
    toastBody.textContent = message;

    // 移除旧样式
    toastEl.classList.remove('bg-success', 'bg-danger', 'bg-warning', 'bg-info', 'text-white');

    // 添加新样式
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

/**
 * 显示/隐藏加载遮罩
 */
function showLoading(show, text = '正在提交计算任务...') {
    const overlay = document.getElementById('loadingOverlay');
    const loadingText = document.getElementById('loadingText');

    if (!overlay) return;

    if (show) {
        overlay.classList.remove('d-none');
        if (loadingText) loadingText.textContent = text;
    } else {
        overlay.classList.add('d-none');
    }
}

/**
 * 获取表单数据
 */
function getFormData() {
    const form = document.getElementById('paramForm');
    const formData = new FormData(form);
    const data = {};

    for (let [key, value] of formData.entries()) {
        data[key] = parseFloat(value);
    }

    return data;
}

/**
 * 设置表单数据
 */
function setFormData(data) {
    for (let [key, value] of Object.entries(data)) {
        const input = document.getElementById(key);
        if (input) {
            input.value = value;
        }
    }
}

/**
 * 生成任务ID
 */
function generateTaskId() {
    const now = new Date();
    const timestamp = now.getFullYear().toString() +
        String(now.getMonth() + 1).padStart(2, '0') +
        String(now.getDate()).padStart(2, '0') +
        String(now.getHours()).padStart(2, '0') +
        String(now.getMinutes()).padStart(2, '0') +
        String(now.getSeconds()).padStart(2, '0');
    const random = Math.random().toString(36).substring(2, 10);
    return `task_${random}_${timestamp}`;
}

// ==================== 历史任务 ====================

/**
 * 状态码 → CSS 类名映射
 */
function getStatusClass(status) {
    if (status === 3) return 'status-completed';
    if (status === 4 || status === 5) return 'status-failed';
    if (status >= 1 && status <= 2 || status === 6 || status === 7) return 'status-running';
    return 'status-pending';
}

/**
 * 格式化时间为简短显示
 */
function formatTime(isoStr) {
    if (!isoStr) return '-';
    const d = new Date(isoStr);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * 折叠/展开历史面板
 */
function toggleHistory() {
    const content = document.getElementById('historyContent');
    const chevron = document.getElementById('historyChevron');
    if (!content) return;
    const hidden = content.style.display === 'none';
    content.style.display = hidden ? '' : 'none';
    if (chevron) {
        chevron.className = hidden ? 'bi bi-chevron-up ms-auto' : 'bi bi-chevron-down ms-auto';
    }
}

/**
 * 加载历史任务列表
 */
async function loadTaskHistory() {
    try {
        const resp = await fetch(`${API_BASE}/tasks?limit=30`);
        if (!resp.ok) {
            console.warn('[历史] 获取任务列表失败:', resp.status);
            return;
        }
        const data = await resp.json();
        const tasks = data.tasks || [];
        renderTaskHistory(tasks);
    } catch (err) {
        console.error('[历史] 网络错误:', err);
        const listEl = document.getElementById('historyList');
        if (listEl) {
            listEl.innerHTML = '<div class="history-empty"><i class="bi bi-wifi-off"></i> 无法加载历史</div>';
        }
    }
}

/**
 * 渲染历史任务列表到 #historyList
 */
function renderTaskHistory(tasks) {
    const listEl = document.getElementById('historyList');
    if (!listEl) return;

    if (!tasks || tasks.length === 0) {
        listEl.innerHTML = '<div class="history-empty"><i class="bi bi-inbox"></i> 暂无历史任务</div>';
        return;
    }

    listEl.innerHTML = tasks.map(task => {
        const statusClass = getStatusClass(task.status);
        const statusName = task.status_name || '未知';
        const time = formatTime(task.created_at);
        const taskIdShort = task.task_id.length > 20
            ? task.task_id.substring(0, 20) + '...'
            : task.task_id;

        // 解析参数摘要
        let paramSummary = '';
        try {
            const p = typeof task.input_params === 'string'
                ? JSON.parse(task.input_params)
                : task.input_params;
            if (p && p.velocity_z) {
                paramSummary = `${p.velocity_z}m/s`;
                if (p.target_yield_stress) paramSummary += ` · ${p.target_yield_stress}MPa`;
            }
        } catch (_) { /* 解析失败静默跳过 */ }

        return `<div class="history-item" onclick="window.location.href='output.html?task_id=${task.task_id}'">
            <div class="task-info">
                <div class="task-id" title="${task.task_id}">${taskIdShort}</div>
                <div class="task-meta">${time}${paramSummary ? ' · ' + paramSummary : ''}</div>
            </div>
            <span class="status-badge ${statusClass}">${statusName}</span>
        </div>`;
    }).join('');
}


// ==================== 核心功能 ====================

/**
 * 提交计算任务
 * 工作流程：保存参数 → 加入队列 → 立即跳转结果页（结果页显示进度）
 */
async function submitCalculation() {
    const data = getFormData();
    const submitBtn = document.getElementById('submitBtn');
    const enablePostprocess = document.getElementById('enable_postprocess')?.checked || false;

    // 后处理使用后端配置文件的默认值，前端不再传递参数
    if (enablePostprocess) {
        console.log('[提交计算] 启用后处理（使用后端默认配置）');
    }

    // 禁用按钮防止重复提交
    if (submitBtn) submitBtn.disabled = true;

    // 获取任务ID：优先用URL传入的 → 否则自动生成
    const taskId = window.incomingTaskId || generateTaskId();
    console.log(`[提交计算] 任务ID: ${taskId}`);

    try {
        // 1. 保存参数（必须等待成功）
        const saveResponse = await fetch(`${API_BASE}/task/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_id: taskId,
                params: data,
                enable_postprocess: enablePostprocess,
                is_platform_mode: false
            })
        });

        if (!saveResponse.ok) {
            const error = await saveResponse.json();
            throw new Error(error.detail || '保存参数失败');
        }
        console.log('[提交计算] 参数保存成功');

        // 2. 触发执行
        fetch(`${API_BASE}/task/${taskId}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        }).catch(err => {
            console.error('[提交计算] 执行请求发送失败:', err);
        });
        console.log('[提交计算] 已触发执行');

        // 3. 立即跳转到结果页（结果页会轮询状态）
        console.log('[提交计算] 立即跳转到结果页');
        window.location.href = `output.html?task_id=${taskId}`;

    } catch (error) {
        console.error('[提交计算] 失败:', error);
        showToast('错误', '提交计算失败: ' + error.message, 'error');
        if (submitBtn) submitBtn.disabled = false;
    }
}

// ==================== 页面初始化 ====================

document.addEventListener('DOMContentLoaded', function() {
    console.log('[app.js] 页面加载完成，初始化中...');

    // ========== task_id 检测与历史加载 ==========
    const urlParams = new URLSearchParams(window.location.search);
    const urlTaskId = urlParams.get('task_id');
    // 始终使用独立模式，task_id 仅用于标识任务
    window.platformTaskId = null;

    if (urlTaskId) {
        console.log('[app.js] URL携带task_id:', urlTaskId, '检查是否为历史任务...');
        // 检查该 task_id 是否已存在于数据库
        fetch(`${API_BASE}/task/${urlTaskId}`)
            .then(resp => {
                if (resp.ok) {
                    // 任务存在 → 跳转到结果页查看历史
                    console.log('[app.js] 历史任务存在，跳转结果页');
                    window.location.href = `output.html?task_id=${urlTaskId}`;
                } else if (resp.status === 404) {
                    // 任务不存在 → 保存task_id供新建提交使用
                    window.incomingTaskId = urlTaskId;
                    console.log('[app.js] 新任务，使用传入的task_id:', urlTaskId);
                } else {
                    console.warn('[app.js] 检查task_id失败，状态:', resp.status);
                }
            })
            .catch(err => {
                console.error('[app.js] 检查task_id网络错误:', err);
                // 网络错误时当作新任务处理
                window.incomingTaskId = urlTaskId;
            });
    } else {
        console.log('[app.js] 独立模式，无URL task_id');
    }

    // 加载历史任务列表
    loadTaskHistory();

    // 预设选择器
    const presetSelector = document.getElementById('presetSelector');
    if (presetSelector) {
        presetSelector.addEventListener('change', function(e) {
            const preset = PRESETS[e.target.value];
            if (preset) {
                setFormData(preset);
                showToast('提示', '已加载预设配置', 'info');
            }
        });
        console.log('[app.js] 预设选择器绑定成功');
    }

    // 表单提交
    const paramForm = document.getElementById('paramForm');
    if (paramForm) {
        paramForm.addEventListener('submit', function(e) {
            e.preventDefault();
            submitCalculation();
        });
        console.log('[app.js] 表单提交事件绑定成功');
    } else {
        console.error('[app.js] 错误：找不到 paramForm 元素');
    }

    // 后处理选项默认勾选，参数使用后端配置文件默认值
    // （前端已移除参数面板，无需切换逻辑）

    // 输入验证反馈（清除错误状态）
    const inputs = document.querySelectorAll('input[type="number"]');
    inputs.forEach(input => {
        input.addEventListener('input', function() {
            this.classList.remove('is-invalid');
        });
    });

    console.log('[app.js] 初始化完成');
});
