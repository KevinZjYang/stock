/*
 * 公共 JavaScript - 股票基金监控系统
 * 包含所有页面共享的函数
 */

// ==================== Toast 提示 ====================

let toastTimer = null;

function showToast(message, type = 'info', duration = 3000) {
    let toast = document.getElementById('toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toast';
        document.body.appendChild(toast);
    }

    // 清除之前的定时器
    if (toastTimer) {
        clearTimeout(toastTimer);
        toastTimer = null;
    }

    // 设置样式
    toast.className = type;
    toast.textContent = message;

    // 显示
    toast.classList.add('show');

    // 自动隐藏
    toastTimer = setTimeout(() => {
        toast.classList.remove('show');
    }, duration);
}

// ==================== 确认对话框 ====================

let confirmCallback = null;

function showCustomConfirm(message, onConfirm, onCancel) {
    // 创建遮罩层
    const overlay = document.createElement('div');
    overlay.className = 'confirm-modal';
    overlay.id = 'customConfirmOverlay';

    // 创建对话框内容
    overlay.innerHTML = `
        <div class="confirm-modal-content">
            <div class="confirm-message">${message}</div>
            <div class="confirm-buttons">
                <button class="confirm-btn confirm" onclick="handleConfirmAction(true)">确定</button>
                <button class="confirm-btn cancel" onclick="handleConfirmAction(false)">取消</button>
            </div>
        </div>
    `;

    // 添加到页面
    document.body.appendChild(overlay);

    // 显示对话框
    overlay.style.display = 'flex';

    // 保存回调函数
    window.currentConfirmCallback = {
        onConfirm: onConfirm,
        onCancel: onCancel || (() => {})
    };
}

function handleConfirmAction(confirmed) {
    const overlay = document.getElementById('customConfirmOverlay');
    if (overlay) {
        overlay.remove();
    }

    if (window.currentConfirmCallback) {
        if (confirmed && window.currentConfirmCallback.onConfirm) {
            window.currentConfirmCallback.onConfirm();
        } else if (!confirmed && window.currentConfirmCallback.onCancel) {
            window.currentConfirmCallback.onCancel();
        }
        delete window.currentConfirmCallback;
    }
}

// ==================== 请求缓存（带去重） ====================

const requestCache = new Map();
const pendingPromises = new Map();

async function cachedFetch(url, options = {}, cacheDuration = 5000) {
    const cacheKey = url;

    // 检查是否有正在进行的相同请求
    if (pendingPromises.has(cacheKey)) {
        return pendingPromises.get(cacheKey);
    }

    // 检查缓存（默认5秒内有效）
    const cached = requestCache.get(cacheKey);
    if (cached && (Date.now() - cached.time < cacheDuration)) {
        return Promise.resolve(cached.data);
    }

    // 创建新的请求
    const promise = fetch(url, options)
        .then(res => {
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            return res.json();
        })
        .then(data => {
            // 存入缓存
            requestCache.set(cacheKey, { data, time: Date.now() });
            pendingPromises.delete(cacheKey);
            return data;
        })
        .catch(err => {
            pendingPromises.delete(cacheKey);
            throw err;
        });

    pendingPromises.set(cacheKey, promise);
    return promise;
}

// ==================== Loading 状态 ====================

function showLoading(selector = '#loadingOverlay') {
    const overlay = document.querySelector(selector);
    if (overlay) {
        overlay.style.display = 'flex';
    }
}

function hideLoading(selector = '#loadingOverlay') {
    const overlay = document.querySelector(selector);
    if (overlay) {
        overlay.style.display = 'none';
    }
}

// ==================== 日期格式化 ====================

function formatDate(dateStr) {
    if (!dateStr) return '--';

    // 如果已经是 "YYYY/MM/DD" 或 "YYYY-MM-DD" 格式，直接返回
    if ((dateStr.includes('/') || dateStr.includes('-')) && dateStr.length >= 10) {
        return dateStr.split(' ')[0];
    }

    try {
        const date = new Date(dateStr);
        if (isNaN(date.getTime())) return dateStr;

        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        return `${year}/${month}/${day}`;
    } catch (e) {
        return dateStr;
    }
}

function formatDateTime(dateStr) {
    if (!dateStr) return '--';

    try {
        const date = new Date(dateStr);
        if (isNaN(date.getTime())) return dateStr;

        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}/${month}/${day} ${hours}:${minutes}`;
    } catch (e) {
        return dateStr;
    }
}

// ==================== 金额格式化 ====================

function formatCurrency(amount, decimals = 2) {
    if (amount === null || amount === undefined || isNaN(amount)) {
        return '--';
    }
    return Number(amount).toFixed(decimals);
}

function formatPercent(value, decimals = 2) {
    if (value === null || value === undefined || isNaN(value)) {
        return '--';
    }
    return (Number(value) * 100).toFixed(decimals) + '%';
}

function formatMoney(value) {
    if (value === null || value === undefined || isNaN(value)) {
        return '--';
    }
    return '¥' + Number(value).toFixed(2);
}

// ==================== 颜色类名获取 ====================

function getValueClass(value) {
    if (value > 0) return 'profit-value';
    if (value < 0) return 'loss-value';
    return '';
}

function getCardClass(value) {
    if (value > 0) return 'profit';
    if (value < 0) return 'loss';
    return 'primary';
}

// ==================== 通用表格渲染 ====================

function renderTable(tableId, columns, data, rowClick = null) {
    const tbody = document.getElementById(tableId);
    if (!tbody) return;

    tbody.innerHTML = '';

    if (!data || data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${columns.length}" class="empty-state">暂无数据</td></tr>`;
        return;
    }

    data.forEach((row, index) => {
        const tr = document.createElement('tr');
        if (rowClick) {
            tr.style.cursor = 'pointer';
            tr.onclick = () => rowClick(row, index);
        }

        columns.forEach(col => {
            const td = document.createElement('td');
            let value = row[col.key];

            // 格式化
            if (col.format === 'currency') {
                value = formatCurrency(value);
            } else if (col.format === 'percent') {
                value = formatPercent(value);
            } else if (col.format === 'money') {
                value = formatMoney(value);
            } else if (col.format === 'date') {
                value = formatDate(value);
            } else if (col.format === 'datetime') {
                value = formatDateTime(value);
            }

            // 颜色类
            if (col.colorClass && row[col.key] !== null) {
                const colorClass = getValueClass(row[col.key]);
                if (colorClass) {
                    td.className = colorClass;
                }
            }

            td.textContent = value !== null && value !== undefined ? value : '--';
            tr.appendChild(td);
        });

        tbody.appendChild(tr);
    });
}

// ==================== 通用搜索组件 ====================

class SearchWidget {
    constructor(options = {}) {
        this.inputId = options.inputId;
        this.resultsId = options.resultsId;
        this.searchUrl = options.searchUrl || '/api/stock/search';
        this.onSelect = options.onSelect || (() => {});
        this.minLength = options.minLength || 1;
        this.debounceDelay = options.debounceDelay || 300;
        this.maxResults = options.maxResults || 10;

        this.input = document.getElementById(this.inputId);
        this.results = document.getElementById(this.resultsId);

        if (!this.input || !this.results) {
            console.error(`SearchWidget: 找不到元素 - input:${this.inputId}, results:${this.resultsId}`);
            return;
        }

        this.setupEvents();
    }

    setupEvents() {
        let searchTimeout = null;

        this.input.addEventListener('input', (e) => {
            const query = e.target.value.trim();

            if (searchTimeout) {
                clearTimeout(searchTimeout);
            }

            if (!query || query.length < this.minLength) {
                this.hideResults();
                return;
            }

            searchTimeout = setTimeout(() => {
                this.performSearch(query);
            }, this.debounceDelay);
        });

        this.input.addEventListener('focus', () => {
            if (this.input.value.trim().length >= this.minLength) {
                this.showResults();
            }
        });

        document.addEventListener('click', (e) => {
            if (!this.input.contains(e.target) && !this.results.contains(e.target)) {
                this.hideResults();
            }
        });

        this.input.addEventListener('keydown', (e) => {
            const items = this.results.querySelectorAll('.search-result-item');
            const current = this.results.querySelector('.search-result-item.active');

            if (e.key === 'Escape') {
                this.hideResults();
                return;
            }

            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                const index = Array.from(items).indexOf(current);
                const direction = e.key === 'ArrowDown' ? 1 : -1;
                const nextIndex = index + direction;

                if (current) current.classList.remove('active');

                if (nextIndex >= 0 && nextIndex < items.length) {
                    items[nextIndex].classList.add('active');
                    items[nextIndex].scrollIntoView({ block: 'nearest' });
                }
            }

            if (e.key === 'Enter' && current) {
                e.preventDefault();
                const code = current.dataset.code;
                const name = current.dataset.name;
                this.selectItem(code, name);
            }
        });
    }

    async performSearch(query) {
        try {
            const response = await fetch(`${this.searchUrl}?code=${encodeURIComponent(query)}`);
            if (!response.ok) throw new Error('搜索失败');

            const data = await response.json();
            const results = (data.excel_results || []).slice(0, this.maxResults);
            this.displayResults(results);
        } catch (error) {
            console.error('搜索错误:', error);
            this.results.innerHTML = '<div style="padding: 8px; color: #e74c3c;">搜索失败</div>';
            this.showResults();
        }
    }

    displayResults(results) {
        if (results.length === 0) {
            this.results.innerHTML = '<div class="search-result-item"><span class="no-result">未找到匹配结果</span></div>';
        } else {
            this.results.innerHTML = results.map(item => {
                // 根据类型确定样式类
                let typeClass = 'stock';
                if (item.type === 'fund' || item.type === '15') typeClass = 'fund';
                else if (item.type === 'index' || item.type === '20') typeClass = 'index';
                else if (item.type === 'hk_stock' || item.type === '13') typeClass = 'hk_stock';
                else if (item.type === 'us_stock' || item.type === '16') typeClass = 'us_stock';
                else if (item.type === 'sh_stock' || item.type === '11') typeClass = 'stock';
                else if (item.type === 'sz_stock' || item.type === '12') typeClass = 'stock';

                // 类型显示文本
                const typeMap = {
                    'sh_stock': '沪A', 'sz_stock': '深A', 'hk_stock': '港股',
                    'us_stock': '美股', 'index': '指数', 'fund': '基金',
                    '11': '沪A', '12': '深A', '13': '港股', '14': '转债',
                    '15': '基金', '16': '美股', '20': '指数'
                };

                return `
                    <div class="search-result-item"
                         data-code="${item.code}"
                         data-name="${item.name || ''}"
                         onclick="searchWidgets['${this.inputId}'].selectItem('${item.code}', '${(item.name || '').replace(/'/g, "\\'")}')">
                        <span class="result-code">${item.code}</span>
                        <span class="result-name">${item.name || '未知'}</span>
                        <span class="result-type ${typeClass}">${typeMap[item.type] || item.type || '股票'}</span>
                    </div>
                `;
            }).join('');
        }
        this.showResults();
    }

    selectItem(code, name) {
        this.input.value = `${code} - ${name}`;
        this.hideResults();
        this.onSelect(code, name);
    }

    showResults() {
        this.results.style.display = 'block';
        this.results.style.opacity = '0';
        this.results.style.transform = 'translateY(-8px)';
        this.results.style.transition = 'opacity 0.2s ease, transform 0.2s ease';

        // 触发重绘
        this.results.offsetHeight;

        this.results.style.opacity = '1';
        this.results.style.transform = 'translateY(0)';
    }

    hideResults() {
        this.results.style.opacity = '0';
        this.results.style.transform = 'translateY(-8px)';
        this.results.style.transition = 'opacity 0.15s ease, transform 0.15s ease';

        setTimeout(() => {
            this.results.style.display = 'none';
        }, 150);
    }

    clear() {
        this.input.value = '';
        this.hideResults();
    }
}

// 注册全局搜索组件管理器
const searchWidgets = {};

// ==================== 分页相关 ====================

class Pagination {
    constructor(options = {}) {
        this.page = 1;
        this.pageSize = options.pageSize || 20;
        this.total = 0;
        this.onChange = options.onChange || (() => {});
    }

    get totalPages() {
        return Math.ceil(this.total / this.pageSize);
    }

    setPage(page) {
        page = Math.max(1, Math.min(page, this.totalPages));
        if (page !== this.page) {
            this.page = page;
            this.onChange(page);
        }
    }

    setTotal(total) {
        this.total = total;
    }

    render(containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;

        const totalPages = this.totalPages;
        if (totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        let html = `
            <div class="pagination">
                <button class="btn btn-sm ${this.page === 1 ? 'btn-secondary' : 'btn-primary'}"
                        onclick="paginationInstance.setPage(${this.page - 1})"
                        ${this.page === 1 ? 'disabled' : ''}>
                    上一页
                </button>
                <span class="pagination-info">第 ${this.page} / ${totalPages} 页</span>
                <button class="btn btn-sm ${this.page === totalPages ? 'btn-secondary' : 'btn-primary'}"
                        onclick="paginationInstance.setPage(${this.page + 1})"
                        ${this.page === totalPages ? 'disabled' : ''}>
                    下一页
                </button>
            </div>
        `;

        container.innerHTML = html;
    }
}

// ==================== 搜索防抖 ====================

function debounce(fn, delay = 300) {
    let timer = null;
    return function (...args) {
        if (timer) {
            clearTimeout(timer);
        }
        timer = setTimeout(() => {
            fn.apply(this, args);
        }, delay);
    };
}

// ==================== 复制到剪贴板 ====================

async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('已复制到剪贴板', 'success');
        return true;
    } catch (err) {
        showToast('复制失败', 'error');
        return false;
    }
}

// ==================== URL 参数获取 ====================

function getUrlParam(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

// ==================== 页面可见性控制 ====================

let pageVisibility = {
    isHidden: false,
    onVisibilityChange: null
};

function initPageVisibility() {
    document.addEventListener('visibilitychange', () => {
        pageVisibility.isHidden = document.hidden;
        if (pageVisibility.onVisibilityChange) {
            pageVisibility.onVisibilityChange(document.hidden);
        }
    });
}

function isPageHidden() {
    return pageVisibility.isHidden;
}

// ==================== 刷新控制 ====================

class RefreshController {
    constructor(options = {}) {
        this.isPaused = false;
        this.interval = options.interval || 30000; // 默认30秒
        this.onRefresh = options.onRefresh || (() => {});
        this.timer = null;
        this.lastManualRefresh = 0;
    }

    start(autoStart = true) {
        if (autoStart && !this.isPaused) {
            this.scheduleRefresh();
        }
    }

    stop() {
        if (this.timer) {
            clearTimeout(this.timer);
            this.timer = null;
        }
    }

    scheduleRefresh() {
        this.stop();
        if (this.isPaused) return;

        this.timer = setTimeout(() => {
            // 防止在页面不可见时频繁刷新
            if (!isPageHidden()) {
                this.onRefresh();
            }
            this.scheduleRefresh();
        }, this.interval);
    }

    manualRefresh() {
        // 防抖：30秒内只能手动刷新一次
        const now = Date.now();
        if (now - this.lastManualRefresh < 30000) {
            return false;
        }
        this.lastManualRefresh = now;
        this.onRefresh();
        return true;
    }

    pause() {
        this.isPaused = true;
        this.stop();
    }

    resume() {
        this.isPaused = false;
        this.scheduleRefresh();
    }

    toggle() {
        if (this.isPaused) {
            this.resume();
        } else {
            this.pause();
        }
        return this.isPaused;
    }
}

// ==================== 通用 API 调用 ====================

async function apiGet(url, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const fullUrl = queryString ? `${url}?${queryString}` : url;
    return cachedFetch(fullUrl);
}

async function apiPost(url, data = {}) {
    return fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
    }).then(res => res.json());
}

// ==================== 初始化 ====================

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initPageVisibility();
});
