// LS-DYNA 参数化系统 - 前端脚本
// 简化版：专注于参数输入和任务提交

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

// ==================== 核心功能 ====================

/**
 * 提交计算任务
 * 工作流程：保存参数 → 加入队列 → 跳转结果页
 */
async function submitCalculation() {
    const data = getFormData();
    const submitBtn = document.getElementById('submitBtn');
    const enablePostprocess = document.getElementById('enable_postprocess')?.checked || false;

    // 显示加载遮罩
    showLoading(true, '正在提交计算任务...');
    if (submitBtn) submitBtn.disabled = true;

    try {
        // 生成任务ID
        const taskId = generateTaskId();
        console.log('[提交计算] 任务ID:', taskId);

        // 1. 保存参数
        showLoading(true, '正在保存参数...');
        const saveResponse = await fetch(`${API_BASE}/task/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_id: taskId,
                params: data,
                enable_postprocess: enablePostprocess
            })
        });

        if (!saveResponse.ok) {
            const error = await saveResponse.json();
            throw new Error(error.detail || '保存参数失败');
        }
        console.log('[提交计算] 参数保存成功');

        // 2. 触发执行（加入队列）
        showLoading(true, '正在加入执行队列...');
        const execResponse = await fetch(`${API_BASE}/task/${taskId}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!execResponse.ok) {
            const error = await execResponse.json();
            throw new Error(error.detail || '触发执行失败');
        }
        console.log('[提交计算] 任务已加入执行队列');

        // 3. 成功，跳转到结果页
        showLoading(true, '任务已提交，正在跳转...');
        showToast('成功', '任务已提交，正在跳转到结果页面...', 'success');

        // 短暂延迟让用户看到提示
        setTimeout(() => {
            window.location.href = `output.html?task_id=${taskId}`;
        }, 500);

    } catch (error) {
        console.error('[提交计算] 失败:', error);
        showToast('错误', '提交计算失败: ' + error.message, 'error');
        showLoading(false);
        if (submitBtn) submitBtn.disabled = false;
    }
}

// ==================== 页面初始化 ====================

document.addEventListener('DOMContentLoaded', function() {
    console.log('[app.js] 页面加载完成，初始化中...');

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

    // 输入验证反馈（清除错误状态）
    const inputs = document.querySelectorAll('input[type="number"]');
    inputs.forEach(input => {
        input.addEventListener('input', function() {
            this.classList.remove('is-invalid');
        });
    });

    console.log('[app.js] 初始化完成');
});
