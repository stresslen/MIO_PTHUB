/**
 * MIO Market Intelligence Operations
 * Leads and source operations interface
 * Fully XSS-safe via DOM API construction.
 */

// ==========================================
// Application State
// ==========================================
const state = {
    currentPage: 'page-leads',
    leads: {
        page: 1,
        pageSize: 15,
        total: 0,
        totalPages: 1,
        query: '',
        action: '',
        source: '',
        sortBy: 'score_desc',
        items: []
    },
    sources: [],
    keywords: [],
    isLoading: false,
    isSavingKeywords: false,
    isSavingSources: false,
    linkedinMaxPostsPerKeyword: 1000,
    isSavingLinkedInConfig: false,
    defaultPrompts: { scoring: '', sales: '' },
    savingPromptType: null,
    activeCrawlJobIds: new Set(),
    activeCrawl: {
        job: null,
        elapsedSeconds: 0,
        timerInterval: null,
        pollTimeout: null,
        dismissedJobId: null
    }
};

// ==========================================
// DOM Elements Registry
// ==========================================
const elements = {
    // Navigation
    navItems: document.querySelectorAll('.nav-item'),
    pageViews: document.querySelectorAll('.page-view'),

    // Page 1: Leads
    leadsTableBody: document.getElementById('leads-tbody'),
    resultsCountText: document.getElementById('results-count-text'),
    emptyState: document.getElementById('empty-state'),
    paginationBar: document.getElementById('pagination-bar'),
    paginationInfo: document.getElementById('pagination-info'),
    btnPrevPage: document.getElementById('btn-prev-page'),
    btnNextPage: document.getElementById('btn-next-page'),
    filterQuery: document.getElementById('filter-query'),
    filterAction: document.getElementById('filter-action'),
    filterSource: document.getElementById('filter-source'),
    filterSort: document.getElementById('filter-sort'),
    btnRefresh: document.getElementById('btn-refresh'),
    btnExportCsv: document.getElementById('btn-export-csv'),

    // Separate Gemini scoring and Sales prompts
    btnOpenScoringPrompt: document.getElementById('btn-open-scoring-prompt'),
    scoringPromptModal: document.getElementById('scoring-prompt-modal'),
    scoringPromptForm: document.getElementById('scoring-prompt-form'),
    btnCloseScoringPrompt: document.getElementById('btn-close-scoring-prompt'),
    btnCancelScoringPrompt: document.getElementById('btn-cancel-scoring-prompt'),
    btnDefaultScoringPrompt: document.getElementById('btn-default-scoring-prompt'),
    btnSaveScoringPrompt: document.getElementById('btn-save-scoring-prompt'),
    scoringPromptInput: document.getElementById('scoring-prompt-input'),
    scoringPromptCount: document.getElementById('scoring-prompt-count'),
    scoringPromptStatus: document.getElementById('scoring-prompt-status'),
    btnOpenSalesPrompt: document.getElementById('btn-open-sales-prompt'),
    salesPromptModal: document.getElementById('sales-prompt-modal'),
    salesPromptForm: document.getElementById('sales-prompt-form'),
    btnCloseSalesPrompt: document.getElementById('btn-close-sales-prompt'),
    btnCancelSalesPrompt: document.getElementById('btn-cancel-sales-prompt'),
    btnDefaultSalesPrompt: document.getElementById('btn-default-sales-prompt'),
    btnSaveSalesPrompt: document.getElementById('btn-save-sales-prompt'),
    salesPromptInput: document.getElementById('sales-prompt-input'),
    salesPromptCount: document.getElementById('sales-prompt-count'),
    salesPromptStatus: document.getElementById('sales-prompt-status'),

    // Page 2: Crawlers
    sourcesGrid: document.getElementById('sources-grid'),
    btnRefreshSources: document.getElementById('btn-refresh-sources'),
    btnOpenKeywords: document.getElementById('btn-open-keywords'),
    sourceCountKicker: document.getElementById('source-count-kicker'),

    // Source registry
    btnOpenSources: document.getElementById('btn-open-sources'),
    sourceModal: document.getElementById('source-modal'),
    sourceForm: document.getElementById('source-form'),
    btnCloseSourceModal: document.getElementById('btn-close-source-modal'),
    btnCancelSource: document.getElementById('btn-cancel-source'),
    btnSaveSource: document.getElementById('btn-save-source'),
    sourceNameInput: document.getElementById('source-name-input'),
    sourceUrlInput: document.getElementById('source-url-input'),
    sourceIncludeSchedule: document.getElementById('source-include-schedule'),
    sourceUrlPreview: document.getElementById('source-url-preview'),
    sourceFormStatus: document.getElementById('source-form-status'),

    // Keyword registry
    keywordModal: document.getElementById('keyword-modal'),
    keywordForm: document.getElementById('keyword-form'),
    btnCloseKeywordModal: document.getElementById('btn-close-keyword-modal'),
    btnCancelKeywords: document.getElementById('btn-cancel-keywords'),
    btnSaveKeywords: document.getElementById('btn-save-keywords'),
    btnRefreshKeywords: document.getElementById('btn-refresh-keywords'),
    keywordInput: document.getElementById('keyword-input'),
    keywordFile: document.getElementById('keyword-file'),
    keywordFileName: document.getElementById('keyword-file-name'),
    keywordUseDiscovery: document.getElementById('keyword-use-discovery'),
    keywordPreviewCount: document.getElementById('keyword-preview-count'),
    keywordSourceLabel: document.getElementById('keyword-source-label'),
    keywordFilter: document.getElementById('keyword-filter'),
    keywordList: document.getElementById('keyword-list'),
    keywordFormStatus: document.getElementById('keyword-form-status'),

    // Global Modals
    leadModal: document.getElementById('lead-modal'),
    modalTitle: document.getElementById('modal-title'),
    modalActionBadge: document.getElementById('modal-action-badge'),
    modalBody: document.getElementById('modal-body'),
    btnCloseModal: document.getElementById('btn-close-modal'),

    crawlModal: document.getElementById('crawl-modal'),
    btnTriggerCrawlButtons: document.querySelectorAll('.btn-trigger-crawl'),
    btnCloseCrawlModal: document.getElementById('btn-close-crawl-modal'),
    btnCancelCrawl: document.getElementById('btn-cancel-crawl'),
    btnStartCrawl: document.getElementById('btn-start-crawl'),
    crawlSourceSelect: document.getElementById('crawl-source-select'),
    crawlTimeframeSelect: document.getElementById('crawl-timeframe-select'),
    crawlProgressBox: document.getElementById('crawl-progress-box'),
    crawlProgressText: document.getElementById('crawl-progress-text'),
    crawlModalActiveNotice: document.getElementById('crawl-modal-active-notice'),
    crawlModalNoticeTitle: document.getElementById('crawl-modal-notice-title'),
    crawlModalNoticeDesc: document.getElementById('crawl-modal-notice-desc'),

    // Crawl Status Banner
    crawlStatusBanner: document.getElementById('crawl-status-banner'),
    crawlBannerBadge: document.getElementById('crawl-banner-badge'),
    crawlBannerTitle: document.getElementById('crawl-banner-title'),
    crawlBannerTimer: document.getElementById('crawl-banner-timer'),
    crawlBannerTimeframe: document.getElementById('crawl-banner-timeframe'),
    crawlBannerTrigger: document.getElementById('crawl-banner-trigger'),
    crawlBannerDetails: document.getElementById('crawl-banner-details'),
    btnBannerRefresh: document.getElementById('btn-banner-refresh'),
    btnCloseCrawlBanner: document.getElementById('btn-close-crawl-banner'),
    btnPauseActiveCrawl: document.getElementById('btn-pause-active-crawl'),
    btnResumeActiveCrawl: document.getElementById('btn-resume-active-crawl'),
    btnStopActiveCrawl: document.getElementById('btn-stop-active-crawl') || document.getElementById('btn-pause-active-crawl'),
    btnDeleteActiveCrawl: document.getElementById('btn-delete-active-crawl'),
    btnResumeRecentCrawl: document.getElementById('btn-resume-recent-crawl'),
    btnToggleQueueList: document.getElementById('btn-toggle-queue-list'),
    queueCountLabel: document.getElementById('queue-count-label'),
    crawlQueuePanel: document.getElementById('crawl-queue-panel'),
    badgeQueuedCount: document.getElementById('badge-queued-count'),
    btnPauseAllQueue: document.getElementById('btn-pause-all-queue'),
    labelPauseAllQueue: document.getElementById('label-pause-all-queue'),
    btnClearCrawlQueue: document.getElementById('btn-clear-crawl-queue'),
    crawlQueueList: document.getElementById('crawl-queue-list'),

    // Scheduler Card
    btnToggleScheduler: document.getElementById('btn-toggle-scheduler'),
    schStatusText: document.getElementById('sch-status-text'),
    schNextRun: document.getElementById('sch-next-run'),
    schLastRun: document.getElementById('sch-last-run'),
    schTotalRuns: document.getElementById('sch-total-runs'),
    schedulerStatusDot: document.getElementById('scheduler-status-dot'),
    schedulerToggleText: document.getElementById('scheduler-toggle-text'),
    btnConfigureScheduler: document.getElementById('btn-configure-scheduler'),
    scheduleModal: document.getElementById('schedule-modal'),
    scheduleForm: document.getElementById('schedule-form'),
    btnCloseScheduleModal: document.getElementById('btn-close-schedule-modal'),
    btnCancelSchedule: document.getElementById('btn-cancel-schedule'),
    scheduleTime: document.getElementById('schedule-time'),

    toastContainer: document.getElementById('toast-container')
};

// ==========================================
// SPA Router & Tab Navigation
// ==========================================
function initRouter() {
    function handleRouteChange() {
        const hash = window.location.hash.replace('#', '') || 'leads';
        let targetPageId = 'page-leads';
        if (hash === 'crawlers') targetPageId = 'page-crawlers';

        switchTab(targetPageId, false);
    }

    elements.navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const targetPageId = item.getAttribute('data-target');
            const targetHash = item.getAttribute('href');
            window.location.hash = targetHash;
            switchTab(targetPageId, true);
        });
    });

    window.addEventListener('hashchange', handleRouteChange);
    handleRouteChange();
}

function switchTab(pageId, updateUrl = true) {
    state.currentPage = pageId;

    // Update Nav Active State
    elements.navItems.forEach(item => {
        if (item.getAttribute('data-target') === pageId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });

    // Update Page View Visibility
    elements.pageViews.forEach(view => {
        if (view.id === pageId) {
            view.style.display = 'block';
            view.classList.add('active');
        } else {
            view.style.display = 'none';
            view.classList.remove('active');
        }
    });

    // Load page-specific data
    checkActiveCrawlStatus();
    if (pageId === 'page-leads') {
        loadLeads();
        if (state.sources.length === 0) loadSources();
    } else if (pageId === 'page-crawlers') {
        loadSources();
        loadSchedulerStatus();
    }
}

// ==========================================
// Toast Notification Utility
// ==========================================
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const spanIcon = document.createElement('span');
    spanIcon.className = 'toast-mark';
    spanIcon.setAttribute('aria-hidden', 'true');

    const spanText = document.createElement('span');
    spanText.textContent = message;

    toast.appendChild(spanIcon);
    toast.appendChild(spanText);
    elements.toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ==========================================
// Formatting Helpers
// ==========================================
function formatCurrency(num) {
    if (!num || isNaN(num) || num <= 0) return null;
    if (num >= 1_000_000_000) {
        return (num / 1_000_000_000).toLocaleString('vi-VN', { maximumFractionDigits: 2 }) + ' tỷ VNĐ';
    }
    if (num >= 1_000_000) {
        return (num / 1_000_000).toLocaleString('vi-VN', { maximumFractionDigits: 1 }) + ' triệu VNĐ';
    }
    return num.toLocaleString('vi-VN') + ' VNĐ';
}

function formatDate(dateStr) {
    if (!dateStr) return 'Chưa rõ';
    try {
        const d = new Date(dateStr);
        return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch {
        return dateStr;
    }
}

function formatSourceBadge(sourceId) {
    const map = {
        'baodauthau': { name: 'Báo Đấu thầu', cls: 'badge-src-baodauthau' },
        'muasamcong': { name: 'Mua Sắm Công', cls: 'badge-src-muasamcong' },
        'dauthau_asia': { name: 'DauThau.info', cls: 'badge-src-dauthau' },
        'chinhphu': { name: 'Cổng Chính phủ', cls: 'badge-src-chinhphu' },
        'xaydungchinhsach': { name: 'Xây dựng CS', cls: 'badge-src-chinhphu' },
        'congbao': { name: 'Công báo CP', cls: 'badge-src-chinhphu' },
        'most_gov': { name: 'Bộ KH&CN', cls: 'badge-src-hanoi' },
        'vietnamnet': { name: 'VietnamNet', cls: 'badge-src-vietnamnet' },
        'vnexpress': { name: 'VnExpress', cls: 'badge-src-vnexpress' },
        'hanoi_gov': { name: 'Cổng Hà Nội', cls: 'badge-src-hanoi' }
    };
    return map[sourceId] || { name: sourceId, cls: 'badge-outline' };
}

// ==========================================
// PAGE 1: Leads Data Table Logic
// ==========================================
async function loadLeads() {
    try {
        const sortSeparator = state.leads.sortBy.lastIndexOf("_");
        const sortField = sortSeparator > 0
            ? state.leads.sortBy.slice(0, sortSeparator)
            : state.leads.sortBy;
        const sortOrder = state.leads.sortBy.slice(sortSeparator + 1) === "asc" ? "asc" : "desc";
        const params = new URLSearchParams({
            page: state.leads.page,
            page_size: state.leads.pageSize,
            sort_by: sortField,
            sort_order: sortOrder
        });

        if (state.leads.query) params.append('query', state.leads.query);
        if (state.leads.action) params.append('action', state.leads.action);
        if (state.leads.source) params.append('source', state.leads.source);

        const res = await fetch(`/api/leads?${params.toString()}`);
        if (!res.ok) throw new Error('Không thể tải danh sách cơ hội');

        const data = await res.json();
        state.leads.items = data.items;
        state.leads.total = data.total;
        state.leads.totalPages = data.total_pages;

        renderLeadsTable();
        updatePagination();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function renderLeadsTable() {
    const tbody = elements.leadsTableBody;
    while (tbody.firstChild) tbody.removeChild(tbody.firstChild);

    if (!state.leads.items || state.leads.items.length === 0) {
        elements.emptyState.classList.remove('hidden');
        elements.resultsCountText.textContent = 'Hiển thị 0 cơ hội';
        return;
    }

    elements.emptyState.classList.add('hidden');
    elements.resultsCountText.textContent = `Hiển thị ${state.leads.items.length} / ${state.leads.total} cơ hội`;

    state.leads.items.forEach(lead => {
        const tr = document.createElement('tr');

        // Column 1: Score
        const tdScore = document.createElement('td');
        const scoreBadge = document.createElement('div');
        scoreBadge.className = `score-badge ${lead.score >= 90 ? 'score-hot' : (lead.score >= 80 ? 'score-qualified' : 'score-nurture')}`;
        scoreBadge.textContent = lead.score;
        tdScore.appendChild(scoreBadge);
        tr.appendChild(tdScore);


        // Column 2: Organization
        const tdOrg = document.createElement('td');
        const orgDiv = document.createElement('div');
        orgDiv.className = 'org-name';
        orgDiv.textContent = lead.organization_name || 'Cơ quan / Doanh nghiệp';
        const titleDiv = document.createElement('div');
        titleDiv.className = 'lead-title-sub';
        titleDiv.textContent = lead.title;
        tdOrg.appendChild(orgDiv);
        tdOrg.appendChild(titleDiv);
        tr.appendChild(tdOrg);

        // Column 3: Need Summary
        const tdNeed = document.createElement('td');
        tdNeed.className = 'need-summary-cell';
        tdNeed.textContent = lead.need_summary || lead.title;
        tr.appendChild(tdNeed);

        // Column 4: Budget
        const tdBudget = document.createElement('td');
        const bFormatted = formatCurrency(lead.budget_value);
        if (bFormatted) {
            const bSpan = document.createElement('span');
            bSpan.className = 'budget-tag';
            bSpan.textContent = bFormatted;
            tdBudget.appendChild(bSpan);
        } else if (lead.budget_text) {
            tdBudget.textContent = lead.budget_text;
        } else {
            tdBudget.textContent = '—';
            tdBudget.style.color = '#94a3b8';
        }
        tr.appendChild(tdBudget);

        // Column 5: Location
        const tdLoc = document.createElement('td');
        tdLoc.textContent = lead.location || 'Toàn quốc';
        tr.appendChild(tdLoc);


        // Column 6: Published Date
        const tdDate = document.createElement('td');
        tdDate.textContent = formatDate(lead.published_at);
        tr.appendChild(tdDate);

        // Column 7: Action Button
        const tdBtn = document.createElement('td');
        tdBtn.style.textAlign = 'center';
        const viewBtn = document.createElement('button');
        viewBtn.className = 'btn btn-xs btn-outline';
        viewBtn.textContent = 'Chi tiết';
        viewBtn.addEventListener('click', () => openLeadModal(lead));
        tdBtn.appendChild(viewBtn);
        tr.appendChild(tdBtn);

        tbody.appendChild(tr);
    });
}

function updatePagination() {
    elements.paginationInfo.textContent = `Trang ${state.leads.page} / ${state.leads.totalPages || 1}`;
    elements.btnPrevPage.disabled = state.leads.page <= 1;
    elements.btnNextPage.disabled = state.leads.page >= state.leads.totalPages;
}


// ==========================================
// Separate Gemini Scoring & Sales Prompts
// ==========================================
function getPromptEditor(promptType) {
    if (promptType === 'scoring') {
        return {
            modal: elements.scoringPromptModal,
            form: elements.scoringPromptForm,
            openButton: elements.btnOpenScoringPrompt,
            closeButton: elements.btnCloseScoringPrompt,
            cancelButton: elements.btnCancelScoringPrompt,
            defaultButton: elements.btnDefaultScoringPrompt,
            saveButton: elements.btnSaveScoringPrompt,
            input: elements.scoringPromptInput,
            count: elements.scoringPromptCount,
            status: elements.scoringPromptStatus,
            label: 'prompt chấm điểm'
        };
    }
    return {
        modal: elements.salesPromptModal,
        form: elements.salesPromptForm,
        openButton: elements.btnOpenSalesPrompt,
        closeButton: elements.btnCloseSalesPrompt,
        cancelButton: elements.btnCancelSalesPrompt,
        defaultButton: elements.btnDefaultSalesPrompt,
        saveButton: elements.btnSaveSalesPrompt,
        input: elements.salesPromptInput,
        count: elements.salesPromptCount,
        status: elements.salesPromptStatus,
        label: 'prompt kịch bản Sales'
    };
}

function setPromptStatus(promptType, message = '', type = '') {
    const editor = getPromptEditor(promptType);
    if (!editor.status) return;
    editor.status.textContent = message;
    editor.status.dataset.type = type;
}

function updatePromptCount(promptType) {
    const editor = getPromptEditor(promptType);
    if (!editor.input || !editor.count) return;
    const length = editor.input.value.length;
    editor.count.textContent = length.toLocaleString('vi-VN') + ' / 30.000 ký tự';
    if (editor.saveButton) {
        editor.saveButton.disabled =
            state.savingPromptType !== null || length < 100 || length > 30000;
    }
}

async function openPromptModal(promptType) {
    const editor = getPromptEditor(promptType);
    if (!editor.modal || !editor.input) return;
    editor.modal.classList.remove('hidden');
    editor.input.disabled = true;
    setPromptStatus(promptType, 'Đang tải…');
    updatePromptCount(promptType);

    try {
        const response = await fetch('/api/scoring/prompts/' + promptType, {
            headers: { 'Cache-Control': 'no-cache' }
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Không thể tải ' + editor.label);
        editor.input.value = data.prompt || '';
        state.defaultPrompts[promptType] = data.default_prompt || '';
        editor.input.disabled = false;
        setPromptStatus(promptType);
        updatePromptCount(promptType);
        editor.input.focus();
    } catch (error) {
        editor.input.disabled = true;
        setPromptStatus(promptType, error.message, 'error');
    }
}

function closePromptModal(promptType) {
    const editor = getPromptEditor(promptType);
    if (!editor.modal || state.savingPromptType === promptType) return;
    editor.modal.classList.add('hidden');
}

async function savePrompt(promptType, event) {
    event.preventDefault();
    const editor = getPromptEditor(promptType);
    const prompt = editor.input.value.trim();
    if (prompt.length < 100) {
        setPromptStatus(promptType, 'Prompt cần ít nhất 100 ký tự.', 'error');
        updatePromptCount(promptType);
        return;
    }

    state.savingPromptType = promptType;
    editor.input.disabled = true;
    setPromptStatus(promptType, 'Đang lưu…');
    updatePromptCount(promptType);

    try {
        const response = await fetch('/api/scoring/prompts/' + promptType, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: prompt })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Không thể lưu ' + editor.label);
        editor.input.value = data.prompt || prompt;
        showToast('Đã lưu ' + editor.label + '.', 'success');
        editor.modal.classList.add('hidden');
    } catch (error) {
        setPromptStatus(
            promptType,
            error.message + '. Nội dung bạn nhập vẫn được giữ nguyên.',
            'error'
        );
    } finally {
        state.savingPromptType = null;
        editor.input.disabled = false;
        updatePromptCount('scoring');
        updatePromptCount('sales');
    }
}

function restoreDefaultPrompt(promptType) {
    const editor = getPromptEditor(promptType);
    if (!state.defaultPrompts[promptType] || !editor.input) return;
    editor.input.value = state.defaultPrompts[promptType];
    setPromptStatus(
        promptType,
        'Đã nạp gợi ý mặc định. Nhấn nút Lưu để áp dụng.',
        'warning'
    );
    updatePromptCount(promptType);
    editor.input.focus();
}

function bindPromptEditor(promptType) {
    const editor = getPromptEditor(promptType);
    if (editor.openButton) {
        editor.openButton.addEventListener('click', () => openPromptModal(promptType));
    }
    if (editor.closeButton) {
        editor.closeButton.addEventListener('click', () => closePromptModal(promptType));
    }
    if (editor.cancelButton) {
        editor.cancelButton.addEventListener('click', () => closePromptModal(promptType));
    }
    if (editor.defaultButton) {
        editor.defaultButton.addEventListener('click', () => restoreDefaultPrompt(promptType));
    }
    if (editor.form) {
        editor.form.addEventListener('submit', event => savePrompt(promptType, event));
    }
    if (editor.input) {
        editor.input.addEventListener('input', () => {
            setPromptStatus(promptType);
            updatePromptCount(promptType);
        });
    }
    if (editor.modal) {
        editor.modal.addEventListener('click', event => {
            if (event.target === editor.modal) closePromptModal(promptType);
        });
    }
}


// ==========================================
// Lead Detail Modal Logic
// ==========================================
async function openLeadModal(lead) {
    try {
        const response = await fetch('/api/leads/' + encodeURIComponent(lead.id));
        if (response.ok) lead = await response.json();
    } catch (error) {
        console.warn('Không tải được thông tin bổ sung:', error);
    }

    const profile = lead.company_profile || null;
    const contacts = Array.isArray(profile?.contacts) ? profile.contacts : [];
    const namedContact = contacts.find(contact => contact.full_name) || contacts[0] || {};
    const emailContact = contacts.find(contact => contact.email) || {};
    const phoneContact = contacts.find(contact => contact.phone) || {};
    const contactName = lead.contact_name || namedContact.full_name || '';
    const contactEmail = lead.contact_email || emailContact.email || '';
    const contactPhone = lead.contact_phone || phoneContact.phone || '';
    const action = String(lead.recommended_action || 'NURTURE').toUpperCase();

    elements.modalTitle.textContent = lead.title || 'Chi tiết cơ hội';
    elements.modalActionBadge.className = 'badge badge-' + action.toLowerCase();
    elements.modalActionBadge.textContent = action;
    const modalBody = elements.modalBody;
    modalBody.replaceChildren();

    const createHeading = (text) => {
        const heading = document.createElement('h4');
        heading.textContent = text;
        return heading;
    };
    const createDetailItem = (label, value) => {
        const item = document.createElement('div');
        item.className = 'detail-item';
        const key = document.createElement('span');
        key.className = 'detail-label';
        key.textContent = label;
        const content = document.createElement('span');
        content.className = 'detail-value';
        content.textContent = value || 'Chưa cập nhật';
        item.append(key, content);
        return item;
    };

    const overview = document.createElement('section');
    overview.className = 'detail-section';
    overview.appendChild(createHeading('Thông tin đơn vị và ngân sách'));
    const overviewGrid = document.createElement('div');
    overviewGrid.className = 'detail-grid';
    overviewGrid.append(
        createDetailItem('Cơ quan / Đơn vị', lead.organization_name),
        createDetailItem('Ngân sách dự kiến', formatCurrency(lead.budget_value) || lead.budget_text || 'Chưa xác định'),
        createDetailItem('Người liên hệ', contactName),
        createDetailItem('Email', contactEmail),
        createDetailItem('Số điện thoại', contactPhone),
        createDetailItem('Địa bàn triển khai', lead.location || 'Toàn quốc'),
        createDetailItem('Ngày xuất bản', formatDate(lead.published_at)),
        createDetailItem('Hạn nộp hồ sơ / Tiếp cận', formatDate(lead.deadline))
    );
    const isTechnicalEnrichmentMessage = value => {
        const text = String(value || "").toLowerCase();
        return text.includes("discovery_failed") ||
            text.includes("crawl vòng 2") ||
            text.includes("xah không trả") ||
            text.includes("httpsconnectionpool") ||
            text.includes("read timed out");
    };
    const mergedProfileItems = [
        ["Ngành hoạt động", profile?.industry],
        ["Quy mô", profile?.size],
        ["Nhân sự", profile?.employee_count],
        ["Địa điểm hồ sơ", Array.isArray(profile?.locations) ? profile.locations.join(", ") : profile?.locations],
        ["Công nghệ", Array.isArray(profile?.technologies) ? profile.technologies.join(", ") : profile?.technologies],
        ["Website chính thức", profile?.official_url]
    ].filter(([, value]) => String(value || "").trim() && !isTechnicalEnrichmentMessage(value));
    if (mergedProfileItems.length) {
        overviewGrid.append(...mergedProfileItems.map(([label, value]) => createDetailItem(label, value)));
    }
    overview.appendChild(overviewGrid);
    modalBody.appendChild(overview);

    const need = document.createElement('section');
    need.className = 'detail-section';
    need.appendChild(createHeading('Nhu cầu được ghi nhận'));
    const needCopy = document.createElement('p');
    needCopy.className = 'detail-copy';
    needCopy.textContent = lead.need_summary || lead.title || 'Chưa có mô tả nhu cầu.';
    need.appendChild(needCopy);
    modalBody.appendChild(need);

    const strategy = document.createElement('section');
    strategy.className = 'detail-section';
    const strategyHeading = document.createElement('div');
    strategyHeading.className = 'strategy-heading-row';
    strategyHeading.appendChild(createHeading('Kịch bản tiếp cận đề xuất'));
    const strategyMeta = document.createElement('div');
    strategyMeta.className = 'strategy-meta';
    const strategyAction = document.createElement('span');
    strategyAction.className = 'strategy-action';
    strategyAction.textContent = 'Kênh Gemini đề xuất: ' + action;
    strategyMeta.appendChild(strategyAction);
    strategyHeading.appendChild(strategyMeta);
    strategy.appendChild(strategyHeading);
    const strategyBox = document.createElement('div');
    strategyBox.className = 'strategy-box';
    strategyBox.textContent = lead.sales_strategy ||
        'Gemini chưa tạo được kịch bản cho cơ hội này. Hãy chạy lại pipeline sau khi kiểm tra cấu hình AI và minh chứng đầu vào.';
    strategy.appendChild(strategyBox);
    modalBody.appendChild(strategy);

    const evidenceItems = Array.isArray(lead.evidence)
        ? lead.evidence.filter(item => String(item || '').trim())
        : [];
    const evidenceSection = document.createElement('section');
    evidenceSection.className = 'detail-section';
    evidenceSection.appendChild(createHeading('Minh chứng từ nội dung thu thập'));
    if (evidenceItems.length) {
        const evidenceList = document.createElement('div');
        evidenceList.className = 'evidence-list';
        evidenceItems.forEach((evidence, index) => {
            const row = document.createElement('div');
            row.className = 'evidence-item';
            const number = document.createElement('span');
            number.className = 'evidence-index';
            number.textContent = String(index + 1).padStart(2, '0');
            const quote = document.createElement('p');
            quote.className = 'evidence-quote';
            quote.textContent = evidence;
            row.append(number, quote);
            evidenceList.appendChild(row);
        });
        evidenceSection.appendChild(evidenceList);
    } else {
        const emptyEvidence = document.createElement('p');
        emptyEvidence.className = 'detail-empty-note';
        emptyEvidence.textContent = 'Chưa có đoạn minh chứng đủ rõ để hiển thị.';
        evidenceSection.appendChild(emptyEvidence);
    }
    modalBody.appendChild(evidenceSection);

    if (lead.source_url) {
        const sourceFooter = document.createElement('section');
        sourceFooter.className = 'detail-source-footer';
        const sourceTitle = document.createElement('strong');
        sourceTitle.textContent = 'Nguồn tham chiếu';

        const sourceLink = document.createElement('a');
        sourceLink.className = 'btn btn-source-origin';
        sourceLink.href = lead.source_url;
        sourceLink.target = '_blank';
        sourceLink.rel = 'noopener noreferrer';
        sourceLink.textContent = 'Xem nguồn gốc';
        sourceFooter.append(sourceTitle, sourceLink);
        modalBody.appendChild(sourceFooter);
    }

    elements.leadModal.classList.remove('hidden');
}


// ==========================================
// PAGE 2: Crawler Management Logic
// ==========================================
async function loadSources() {
    try {
        const res = await fetch('/api/sources');
        if (!res.ok) throw new Error('Không thể tải thông tin nguồn crawler');
        state.sources = await res.json();
        try {
            const configResponse = await fetch('/api/sources/linkedin/config');
            if (configResponse.ok) {
                const config = await configResponse.json();
                state.linkedinMaxPostsPerKeyword = config.max_posts_per_keyword || 1000;
            }
        } catch (_) {
            state.linkedinMaxPostsPerKeyword = state.linkedinMaxPostsPerKeyword || 1000;
        }
        renderSourcesGrid();
        syncSourceOptions();
        if (elements.sourceCountKicker) {
            elements.sourceCountKicker.textContent = state.sources.length + ' kết nối';
        }
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function populateSourceSelect(select, { enabledOnly = false } = {}) {
    if (!select) return;
    const selected = select.value;
    select.replaceChildren();
    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = "All";
    select.appendChild(allOption);
    state.sources.forEach(source => {
        if (enabledOnly && !source.enabled) return;
        const option = document.createElement("option");
        option.value = source.id;
        option.textContent = source.name;
        select.appendChild(option);
    });
    if ([...select.options].some(option => option.value === selected)) {
        select.value = selected;
    }
}

function syncSourceOptions() {
    // Lead history can be filtered by every registered source, including disabled ones.
    populateSourceSelect(elements.filterSource);
    // Manual "All" follows backend behavior and runs only enabled sources.
    populateSourceSelect(elements.crawlSourceSelect, { enabledOnly: true });
}

async function saveLinkedInPostLimit(input, button, status) {
    const value = Number(input.value);
    if (!Number.isInteger(value) || value < 1 || value > 1000) {
        status.textContent = 'Nhập số nguyên từ 1 đến 1.000.';
        status.dataset.type = 'error';
        input.focus();
        return;
    }
    state.isSavingLinkedInConfig = true;
    input.disabled = true;
    button.disabled = true;
    status.textContent = 'Đang lưu…';
    status.dataset.type = '';
    try {
        const response = await fetch('/api/sources/linkedin/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ max_posts_per_keyword: value })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Không thể lưu giới hạn LinkedIn');
        state.linkedinMaxPostsPerKeyword = data.max_posts_per_keyword;
        input.value = data.max_posts_per_keyword;
        status.textContent = 'Đã lưu.';
        status.dataset.type = 'success';
        showToast('Đã cập nhật số bài LinkedIn mỗi keyword.', 'success');
    } catch (error) {
        status.textContent = error.message;
        status.dataset.type = 'error';
    } finally {
        state.isSavingLinkedInConfig = false;
        input.disabled = false;
        button.disabled = false;
    }
}

function renderSourcesGrid() {
    const grid = elements.sourcesGrid;
    while (grid.firstChild) grid.removeChild(grid.firstChild);

    state.sources.forEach(src => {
        const card = document.createElement('div');
        card.className = 'source-card';

        const header = document.createElement('div');
        header.className = 'source-header';

        const titleGroup = document.createElement('div');
        titleGroup.className = 'source-title-group';

        const sDot = document.createElement('span');
        const crawlBusy = ["QUEUED", "RUNNING"].includes(src.status);
        const sourceReady = src.enabled && !['NEEDS_ADAPTER', 'ERROR', 'BLOCKED'].includes(src.status);
        sDot.className = 'status-dot ' + (sourceReady ? 'online' : 'offline');
        titleGroup.appendChild(sDot);

        const h3 = document.createElement('h3');
        h3.textContent = src.name;
        titleGroup.appendChild(h3);
        header.appendChild(titleGroup);

        const countBadge = document.createElement('span');
        countBadge.className = 'source-count-badge';
        countBadge.textContent = `${src.total_leads_count || 0} cơ hội`;
        header.appendChild(countBadge);
        card.appendChild(header);

        // Seed URLs
        const meta = document.createElement('div');
        meta.className = 'source-meta';
        const seedP = document.createElement('p');
        let sourceHost = 'Chưa cấu hình';
        if (src.base_url) {
            try {
                sourceHost = new URL(src.base_url).hostname.replace(/^www\./, '');
            } catch (_) {
                sourceHost = src.base_url;
            }
        }
        seedP.textContent = sourceHost;
        seedP.title = src.base_url || '';
        seedP.className = 'source-url';
        meta.appendChild(seedP);

        const lastP = document.createElement('p');
        lastP.textContent = src.last_crawl_at ? 'Lần chạy · ' + formatDate(src.last_crawl_at) : 'Chưa có lần chạy';
        lastP.className = 'source-last-run';
        meta.appendChild(lastP);
        if (src.last_error) {
            const errorNote = document.createElement('p');
            errorNote.className = 'source-error-note';
            errorNote.textContent = 'Nguồn chưa crawl được · cần cập nhật sau';
            meta.appendChild(errorNote);
        }
        card.appendChild(meta);

        if (src.id === 'linkedin_apify') {
            card.classList.add('source-card-linkedin');
            const configRow = document.createElement('div');
            configRow.className = 'source-runtime-config';
            const configCopy = document.createElement('div');
            configCopy.className = 'source-runtime-copy';
            const configLabel = document.createElement('label');
            configLabel.htmlFor = 'linkedin-post-limit';
            configLabel.textContent = 'Bài viết / keyword';
            const configHint = document.createElement('span');
            configHint.textContent = '1–1.000 bài mỗi từ khóa';
            configCopy.append(configLabel, configHint);

            const configControls = document.createElement('div');
            configControls.className = 'source-runtime-controls';
            const configInput = document.createElement('input');
            configInput.id = 'linkedin-post-limit';
            configInput.className = 'source-limit-input';
            configInput.type = 'number';
            configInput.min = '1';
            configInput.max = '1000';
            configInput.step = '50';
            configInput.inputMode = 'numeric';
            configInput.value = String(state.linkedinMaxPostsPerKeyword || 1000);
            configInput.setAttribute('aria-label', 'Số bài LinkedIn mỗi keyword');
            const configButton = document.createElement('button');
            configButton.className = 'btn btn-sm btn-save-source-config';
            configButton.type = 'button';
            configButton.textContent = 'Lưu';
            configControls.append(configInput, configButton);

            const configStatus = document.createElement('p');
            configStatus.className = 'source-runtime-status';
            configStatus.setAttribute('aria-live', 'polite');
            configButton.addEventListener('click', () => {
                saveLinkedInPostLimit(configInput, configButton, configStatus);
            });
            configInput.addEventListener('keydown', event => {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    saveLinkedInPostLimit(configInput, configButton, configStatus);
                }
            });
            configRow.append(configCopy, configControls, configStatus);
            card.appendChild(configRow);
        }

        // Action Button
        const btnRow = document.createElement('div');
        btnRow.className = 'source-card-actions';

        const runBtn = document.createElement('button');
        runBtn.className = 'btn btn-xs btn-outline';
        runBtn.textContent = !src.enabled
            ? "Cần cập nhật sau"
            : src.status === "RUNNING"
                ? "Đang thu thập"
                : crawlBusy ? "Đang chờ worker" : "Thu thập nguồn này";
        runBtn.disabled = !src.enabled || crawlBusy;
        runBtn.addEventListener('click', () => {
            elements.crawlSourceSelect.value = src.id;
            elements.crawlModal.classList.remove('hidden');
        });
        btnRow.appendChild(runBtn);
        card.appendChild(btnRow);

        grid.appendChild(card);
    });
}

// ==========================================
// Google Sheets Source Registry
// ==========================================
function isValidSourceUrl(value) {
    try {
        const parsed = new URL(String(value || '').trim());
        return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch (_) {
        return false;
    }
}

function updateSourcePreview() {
    const name = elements.sourceNameInput.value.trim();
    const url = elements.sourceUrlInput.value.trim();
    const validUrl = isValidSourceUrl(url);
    elements.sourceUrlPreview.textContent = url && !validUrl
        ? 'URL cần bắt đầu bằng http:// hoặc https://.'
        : '';
    elements.btnSaveSource.disabled = !name || !validUrl || state.isSavingSources;
}

function openSourceModal() {
    elements.sourceModal.classList.remove('hidden');
    elements.sourceFormStatus.textContent = '';
    window.setTimeout(() => elements.sourceNameInput.focus(), 60);
}

function closeSourceModal() {
    if (state.isSavingSources) return;
    elements.sourceModal.classList.add('hidden');
}

async function saveSources(event) {
    event.preventDefault();
    const name = elements.sourceNameInput.value.trim();
    const url = elements.sourceUrlInput.value.trim();
    if (!name || !isValidSourceUrl(url) || state.isSavingSources) {
        elements.sourceForm.reportValidity();
        return;
    }

    state.isSavingSources = true;
    elements.btnSaveSource.disabled = true;
    elements.btnSaveSource.textContent = 'Đang lưu và kiểm tra...';
    elements.sourceFormStatus.textContent = '';
    try {
        const response = await fetch('/api/sources/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                url: url,
                include_in_schedule: elements.sourceIncludeSchedule.checked
            })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Không thể lưu URL');

        const needsUpdate = data.needs_update || 0;
        elements.sourceNameInput.value = '';
        elements.sourceUrlInput.value = '';
        elements.sourceIncludeSchedule.checked = false;
        updateSourcePreview();
        elements.sourceModal.classList.add('hidden');
        await loadSources();
        if (needsUpdate > 0) {
            showToast(
                'Đã lưu URL. ' + needsUpdate + ' nguồn chưa crawl được và cần cập nhật sau.',
                'info'
            );
        } else if ((data.added || 0) > 0) {
            showToast('Đã lưu “' + name + '” và xếp lệnh kiểm tra cho crawl worker.', 'success');
        } else {
            showToast('URL này đã tồn tại trong danh sách nguồn.', 'info');
        }
    } catch (error) {
        elements.sourceFormStatus.textContent =
            error.message + '. Nội dung URL vẫn được giữ để bạn thử lại.';
    } finally {
        state.isSavingSources = false;
        elements.btnSaveSource.textContent = 'Lưu và kiểm tra URL';
        updateSourcePreview();
    }
}

// ==========================================
// Google Sheets Keyword Registry
// ==========================================
function parseKeywordPreview(content) {
    const seen = new Set();
    return String(content || '')
        .split(/[,;\r\n]+/)
        .map(value => value.normalize('NFKC').replace(/\s+/g, ' ').trim())
        .filter(value => {
            if (!value) return false;
            const key = value.toLocaleLowerCase('vi-VN');
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
}

function updateKeywordPreview() {
    const parsed = parseKeywordPreview(elements.keywordInput.value);
    elements.keywordPreviewCount.textContent = parsed.length + ' mục';
    elements.btnSaveKeywords.disabled = parsed.length === 0 || state.isSavingKeywords;
    elements.keywordFormStatus.textContent = parsed.length > 1000
        ? 'Mỗi lần chỉ được thêm tối đa 1.000 từ khóa.'
        : '';
}

function renderKeywordList() {
    const query = elements.keywordFilter.value.trim().toLocaleLowerCase('vi-VN');
    const items = state.keywords.filter(item =>
        !query || String(item.keyword || '').toLocaleLowerCase('vi-VN').includes(query)
    );
    elements.keywordList.replaceChildren();
    if (items.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'keyword-list-state';
        empty.textContent = query ? 'Không có từ khóa khớp bộ lọc.' : 'Chưa có từ khóa hoạt động.';
        elements.keywordList.appendChild(empty);
        return;
    }
    items.forEach(item => {
        const row = document.createElement('div');
        row.className = 'keyword-list-row';
        const copy = document.createElement('div');
        const name = document.createElement('strong');
        name.textContent = item.keyword;
        const group = document.createElement('small');
        group.textContent = item.group_name || 'Từ khóa tùy chỉnh';
        copy.append(name, group);
        const usage = document.createElement('span');
        usage.className = item.use_for_discovery ? 'keyword-usage search' : 'keyword-usage';
        usage.textContent = item.use_for_discovery ? 'SEARCH + LỌC' : 'LỌC';
        row.append(copy, usage);
        elements.keywordList.appendChild(row);
    });
}

async function loadKeywords(refreshFromSheet = false) {
    elements.btnRefreshKeywords.disabled = true;
    elements.keywordSourceLabel.textContent = refreshFromSheet
        ? 'Đang đồng bộ…'
        : 'Đang tải…';
    try {
        const endpoint = refreshFromSheet ? '/api/keywords/refresh' : '/api/keywords';
        const res = await fetch(endpoint, { method: refreshFromSheet ? 'POST' : 'GET' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Không thể tải từ khóa');
        state.keywords = Array.isArray(data.items) ? data.items : [];
        elements.keywordSourceLabel.textContent =
            (data.total || 0) + ' từ khóa · ' + (data.discovery_total || 0) + ' tìm kiếm trực tiếp';
        renderKeywordList();
        if (refreshFromSheet) showToast('Đã đồng bộ từ khóa.', 'success');
    } catch (error) {
        elements.keywordSourceLabel.textContent = 'Không thể tải từ khóa';
        elements.keywordList.replaceChildren();
        const stateNode = document.createElement('div');
        stateNode.className = 'keyword-list-state error';
        stateNode.textContent = error.message;
        elements.keywordList.appendChild(stateNode);
    } finally {
        elements.btnRefreshKeywords.disabled = false;
    }
}

function openKeywordModal() {
    elements.keywordModal.classList.remove('hidden');
    elements.keywordFormStatus.textContent = '';
    loadKeywords(false);
    window.setTimeout(() => elements.keywordInput.focus(), 60);
}

function closeKeywordModal() {
    if (state.isSavingKeywords) return;
    elements.keywordModal.classList.add('hidden');
}

async function handleKeywordFile(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    const allowed = /\.(txt|csv)$/i.test(file.name) || ['text/plain', 'text/csv'].includes(file.type);
    if (!allowed) {
        elements.keywordFileName.textContent = 'File không hợp lệ';
        showToast('Chỉ chấp nhận file TXT hoặc CSV.', 'error');
        event.target.value = '';
        return;
    }
    if (file.size > 1024 * 1024) {
        elements.keywordFileName.textContent = 'File vượt quá 1 MB';
        showToast('File từ khóa phải nhỏ hơn hoặc bằng 1 MB.', 'error');
        event.target.value = '';
        return;
    }
    try {
        const content = await file.text();
        if (!content.trim()) throw new Error('File không có nội dung');
        elements.keywordInput.value = [elements.keywordInput.value.trim(), content.trim()]
            .filter(Boolean)
            .join('\n');
        elements.keywordFileName.textContent = file.name + ' · ' + (file.size / 1024).toFixed(1) + ' KB';
        updateKeywordPreview();
    } catch (error) {
        elements.keywordFileName.textContent = 'Không đọc được file';
        showToast(error.message + '. Hãy lưu file ở định dạng UTF-8 rồi thử lại.', 'error');
    }
}

async function saveKeywords(event) {
    event.preventDefault();
    const keywords = parseKeywordPreview(elements.keywordInput.value);
    if (keywords.length === 0 || state.isSavingKeywords) return;
    if (keywords.length > 1000) {
        elements.keywordFormStatus.textContent = 'Mỗi lần chỉ được thêm tối đa 1.000 từ khóa.';
        return;
    }
    state.isSavingKeywords = true;
    elements.btnSaveKeywords.disabled = true;
    elements.btnSaveKeywords.textContent = 'Đang lưu...';
    elements.keywordFormStatus.textContent = 'Đang lưu…';
    try {
        const res = await fetch('/api/keywords/import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: elements.keywordInput.value,
                use_for_discovery: elements.keywordUseDiscovery.checked
            })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Không thể lưu keyword');
        const changed = (data.added || 0) + (data.promoted || 0);
        elements.keywordInput.value = '';
        elements.keywordFile.value = '';
        elements.keywordFileName.textContent = 'Tối đa 1 MB';
        elements.keywordFormStatus.textContent = '';
        showToast(
            changed > 0
                ? 'Đã cập nhật ' + changed + ' từ khóa; bỏ qua ' + (data.duplicates || 0) + ' mục trùng.'
                : 'Không có thay đổi; ' + (data.duplicates || 0) + ' từ khóa đã tồn tại.',
            changed > 0 ? 'success' : 'info'
        );
        updateKeywordPreview();
        await loadKeywords(false);
    } catch (error) {
        elements.keywordFormStatus.textContent =
            error.message + '. Nội dung nhập vẫn được giữ để bạn thử lại.';
    } finally {
        state.isSavingKeywords = false;
        elements.btnSaveKeywords.textContent = 'Thêm từ khóa';
        updateKeywordPreview();
    }
}

// ==========================================
// Crawl Monitoring & Status Banner
// ==========================================
function wait(milliseconds) {
    return new Promise(resolve => window.setTimeout(resolve, milliseconds));
}

function formatSeconds(seconds) {
    const s = Math.max(0, Math.floor(seconds || 0));
    const mins = Math.floor(s / 60);
    const secs = s % 60;
    return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

function formatFriendlyTime(isoStr) {
    if (!isoStr) return '';
    try {
        let parseable = isoStr;
        // If naive ISO string (no Z or +/- offset), treat as UTC
        if (!parseable.includes('Z') && !parseable.includes('+') && !/(-\d\d:\d\d)$/.test(parseable)) {
            parseable += 'Z';
        }
        const d = new Date(parseable);
        if (isNaN(d.getTime())) return '';
        const now = new Date();
        const diffMs = now.getTime() - d.getTime();
        const diffMins = Math.floor(diffMs / 60000);

        if (diffMins < 1 && diffMins >= 0) return 'Vừa gửi';
        if (diffMins < 60 && diffMins >= 1) return `${diffMins} phút trước`;

        const vnFormatter = new Intl.DateTimeFormat('vi-VN', {
            timeZone: 'Asia/Ho_Chi_Minh',
            hour: '2-digit',
            minute: '2-digit',
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour12: false
        });
        const parts = Object.fromEntries(
            vnFormatter.formatToParts(d).map(p => [p.type, p.value])
        );
        const timeStr = `${parts.hour}:${parts.minute}`;

        const nowParts = Object.fromEntries(
            vnFormatter.formatToParts(now).map(p => [p.type, p.value])
        );
        const isToday = (parts.day === nowParts.day && parts.month === nowParts.month && parts.year === nowParts.year);

        if (isToday) return `Gửi lúc ${timeStr} hôm nay`;
        return `Gửi lúc ${timeStr} ${parts.day}/${parts.month}`;
    } catch (_) {
        return '';
    }
}

function updateCrawlModalNotice() {
    if (!elements.crawlModalActiveNotice) return;
    const current = state.activeCrawl.job;
    if (current && ['QUEUED', 'RUNNING'].includes(current.status)) {
        elements.crawlModalActiveNotice.classList.remove('hidden');
        if (elements.crawlModalNoticeTitle) {
            elements.crawlModalNoticeTitle.textContent = current.status === 'RUNNING'
                ? `Đang có luồng crawl chạy: ${current.source_name}`
                : `Có luồng đang chờ: ${current.source_name}`;
        }
        if (elements.crawlModalNoticeDesc) {
            const timeInfo = current.timeframe_label || current.timeframe || '7 ngày qua';
            const trigInfo = current.trigger_label || current.trigger || 'Thủ công';
            elements.crawlModalNoticeDesc.textContent = `Phạm vi ${timeInfo} (${trigInfo}). Yêu cầu mới của bạn sẽ được xếp vào hàng đợi.`;
        }
    } else {
        elements.crawlModalActiveNotice.classList.add('hidden');
    }
}

function dismissCrawlBanner() {
    if (!elements.crawlStatusBanner) return;
    elements.crawlStatusBanner.classList.add('hidden');
    if (state.activeCrawl.job && state.activeCrawl.job.id) {
        state.activeCrawl.dismissedJobId = state.activeCrawl.job.id;
    }
}

function renderQueuedJobs(queuedJobs) {
    if (!elements.crawlQueueList || !elements.btnToggleQueueList) return;

    const count = (queuedJobs && Array.isArray(queuedJobs)) ? queuedJobs.length : 0;

    if (count === 0) {
        elements.btnToggleQueueList.classList.add('hidden');
        if (elements.crawlQueuePanel) elements.crawlQueuePanel.classList.add('hidden');
        return;
    }

    elements.btnToggleQueueList.classList.remove('hidden');
    if (elements.queueCountLabel) {
        elements.queueCountLabel.textContent = `${count} lệnh đang chờ`;
    }
    if (elements.badgeQueuedCount) {
        elements.badgeQueuedCount.textContent = `${count} yêu cầu`;
    }

    const allPaused = count > 0 && queuedJobs.every(j => j.status === 'PAUSED');
    state.activeCrawl.allPaused = allPaused;
    if (elements.labelPauseAllQueue) {
        elements.labelPauseAllQueue.textContent = allPaused ? 'Tiếp tục tất cả' : 'Tạm dừng tất cả';
    }

    elements.crawlQueueList.replaceChildren();

    queuedJobs.forEach((job, index) => {
        const item = document.createElement('div');
        item.className = 'crawl-queue-item';

        const mainDiv = document.createElement('div');
        mainDiv.className = 'crawl-queue-item-main';

        const orderBadge = document.createElement('span');
        orderBadge.className = 'crawl-queue-order-badge' + (index === 0 ? ' is-next' : '');
        orderBadge.textContent = index === 0 ? '#1 (Kế tiếp)' : `#${index + 1}`;
        mainDiv.appendChild(orderBadge);

        const infoDiv = document.createElement('div');
        infoDiv.className = 'crawl-queue-item-info';

        const nameDiv = document.createElement('div');
        nameDiv.className = 'crawl-queue-item-name';
        nameDiv.textContent = job.source_name || 'Tất cả các nguồn dữ liệu';
        infoDiv.appendChild(nameDiv);

        const metaDiv = document.createElement('div');
        metaDiv.className = 'crawl-queue-item-meta';

        const tfSpan = document.createElement('span');
        tfSpan.textContent = `Phạm vi: ${job.timeframe_label || '24 giờ qua'}`;
        metaDiv.appendChild(tfSpan);

        const dot1 = document.createElement('span');
        dot1.textContent = '·';
        metaDiv.appendChild(dot1);

        const trigSpan = document.createElement('span');
        trigSpan.textContent = job.trigger_label || 'Thủ công';
        metaDiv.appendChild(trigSpan);

        if (job.requested_at) {
            const timeText = formatFriendlyTime(job.requested_at);
            if (timeText) {
                const dot2 = document.createElement('span');
                dot2.textContent = '·';
                metaDiv.appendChild(dot2);

                const timeSpan = document.createElement('span');
                timeSpan.textContent = timeText;
                metaDiv.appendChild(timeSpan);
            }
        }

        infoDiv.appendChild(metaDiv);
        mainDiv.appendChild(infoDiv);
        item.appendChild(mainDiv);

        const sideDiv = document.createElement('div');
        sideDiv.className = 'crawl-queue-item-side';

        const isPaused = job.status === 'PAUSED';
        const statusTag = document.createElement('span');
        statusTag.className = 'crawl-queue-status-tag ' + (isPaused ? 'is-paused' : 'is-queued');
        statusTag.textContent = isPaused ? 'Tạm dừng' : 'Chờ lượt';
        sideDiv.appendChild(statusTag);

        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'crawl-queue-item-actions';

        // 1. Pause / Resume Button
        const btnPauseResume = document.createElement('button');
        btnPauseResume.type = 'button';
        btnPauseResume.className = 'btn-item-action' + (isPaused ? ' is-resume' : '');
        btnPauseResume.title = isPaused ? 'Tiếp tục lệnh này' : 'Tạm dừng lệnh này';
        btnPauseResume.innerHTML = isPaused
            ? `<svg viewBox="0 0 24 24" style="width:12px;height:12px;stroke:currentColor;fill:none;stroke-width:2;"><polygon points="5 3 19 12 5 21 5 3"/></svg>`
            : `<svg viewBox="0 0 24 24" style="width:12px;height:12px;fill:currentColor;"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`;
        btnPauseResume.addEventListener('click', async (e) => {
            e.stopPropagation();
            try {
                const endpoint = isPaused ? `/api/crawl/jobs/${job.id}/resume` : `/api/crawl/jobs/${job.id}/pause`;
                const res = await fetch(endpoint, { method: 'POST' });
                if (res.ok) {
                    showToast(isPaused ? 'Đã tiếp tục lệnh' : 'Đã tạm dừng lệnh', 'info');
                    pollActiveCrawlStatus();
                } else {
                    showToast('Không thể cập nhật lệnh', 'error');
                }
            } catch (_) {
                showToast('Lỗi kết nối', 'error');
            }
        });
        actionsDiv.appendChild(btnPauseResume);

        // 2. Promote to front (if not first)
        if (index > 0) {
            const btnPromote = document.createElement('button');
            btnPromote.type = 'button';
            btnPromote.className = 'btn-item-action is-run';
            btnPromote.title = 'Chạy lệnh này trước (Ưu tiên)';
            btnPromote.innerHTML = `<svg viewBox="0 0 24 24" style="width:12px;height:12px;fill:currentColor;"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`;
            btnPromote.addEventListener('click', async (e) => {
                e.stopPropagation();
                try {
                    const res = await fetch(`/api/crawl/jobs/${job.id}/promote`, { method: 'POST' });
                    if (res.ok) {
                        showToast('Đã đưa lệnh lên vị trí kế tiếp', 'info');
                        pollActiveCrawlStatus();
                    } else {
                        showToast('Không thể đẩy lệnh lên', 'error');
                    }
                } catch (_) {
                    showToast('Lỗi kết nối', 'error');
                }
            });
            actionsDiv.appendChild(btnPromote);
        }

        // 3. Delete single job
        const btnDelete = document.createElement('button');
        btnDelete.type = 'button';
        btnDelete.className = 'btn-item-action is-delete';
        btnDelete.title = 'Xóa lệnh này';
        btnDelete.innerHTML = `<svg viewBox="0 0 24 24" style="width:12px;height:12px;stroke:currentColor;fill:none;stroke-width:2;"><path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>`;
        btnDelete.addEventListener('click', async (e) => {
            e.stopPropagation();
            if (!confirm(`Bạn có chắc muốn xóa lệnh "${job.source_name || 'Tất cả các nguồn'}" khỏi hàng đợi?`)) return;
            try {
                const res = await fetch(`/api/crawl/jobs/${job.id}`, { method: 'DELETE' });
                if (res.ok) {
                    showToast('Đã xóa lệnh khỏi hàng đợi', 'info');
                    pollActiveCrawlStatus();
                } else {
                    showToast('Không thể xóa lệnh', 'error');
                }
            } catch (_) {
                showToast('Lỗi kết nối', 'error');
            }
        });
        actionsDiv.appendChild(btnDelete);

        sideDiv.appendChild(actionsDiv);
        item.appendChild(sideDiv);

        elements.crawlQueueList.appendChild(item);
    });
}

function renderCrawlStatusBanner(activeJob, recentJob, queueDepth, queuedJobs) {
    if (!elements.crawlStatusBanner) return;

    // Render queued jobs panel & button
    renderQueuedJobs(queuedJobs);

    if (activeJob && ['QUEUED', 'RUNNING', 'PAUSED'].includes(activeJob.status)) {
        state.activeCrawl.job = activeJob;
        const isQueued = activeJob.status === 'QUEUED';
        const isPaused = activeJob.status === 'PAUSED';

        elements.crawlStatusBanner.className = 'crawl-status-banner' + (isPaused ? ' is-paused' : (isQueued ? ' is-queued' : ''));
        elements.crawlStatusBanner.classList.remove('hidden');

        if (elements.crawlBannerBadge) {
            elements.crawlBannerBadge.textContent = isPaused ? 'Tạm dừng' : (isQueued ? 'Chờ worker' : 'Đang thu thập');
        }

        if (elements.crawlBannerTitle) {
            elements.crawlBannerTitle.textContent = activeJob.source_name || 'Tất cả các nguồn dữ liệu';
            elements.crawlBannerTitle.title = activeJob.source_name || '';
        }

        if (elements.crawlBannerTimeframe) {
            const tf = activeJob.timeframe_label || activeJob.timeframe || '7 ngày qua';
            elements.crawlBannerTimeframe.textContent = `Khoảng: ${tf}`;
        }

        if (elements.crawlBannerTrigger) {
            const tr = activeJob.trigger_label || activeJob.trigger || 'Thủ công';
            elements.crawlBannerTrigger.textContent = `Hình thức: ${tr}`;
        }

        if (elements.crawlBannerDetails) {
            if (isPaused) {
                elements.crawlBannerDetails.textContent = 'Tiến trình cào đang tạm dừng; dữ liệu đã quét được bảo toàn 100%. Bấm "Tiếp tục chạy" để cào tiếp.';
            } else if (isQueued) {
                elements.crawlBannerDetails.textContent = 'Đang xếp hàng chờ đến lượt xử lý...';
            } else if (activeJob.active_runs && activeJob.active_runs.length > 0) {
                const runNames = activeJob.active_runs.map(r => r.source_name).filter(Boolean).join(', ');
                const totalLeads = activeJob.active_runs.reduce((acc, r) => acc + (r.new_leads || 0), 0);
                elements.crawlBannerDetails.textContent = `Đang xử lý: ${runNames}${totalLeads > 0 ? ` · Đã tìm thấy +${totalLeads} cơ hội` : ''}`;
            } else {
                elements.crawlBannerDetails.textContent = 'Đang thu thập và phân tích dữ liệu...';
            }
        }

        if (elements.crawlBannerTimer) {
            if (isPaused) {
                elements.crawlBannerTimer.textContent = `⏱️ ${formatSeconds(state.activeCrawl.elapsedSeconds)} (Tạm dừng)`;
            } else {
                elements.crawlBannerTimer.textContent = `⏱️ ${formatSeconds(state.activeCrawl.elapsedSeconds)}`;
            }
        }

        if (elements.btnBannerRefresh) {
            elements.btnBannerRefresh.classList.add('hidden');
        }
        if (elements.btnPauseActiveCrawl) {
            elements.btnPauseActiveCrawl.classList.toggle('hidden', isPaused || isQueued);
        }
        if (elements.btnResumeActiveCrawl) {
            elements.btnResumeActiveCrawl.classList.toggle('hidden', !isPaused);
        }
        if (elements.btnStopActiveCrawl && !elements.btnPauseActiveCrawl) {
            elements.btnStopActiveCrawl.classList.toggle('hidden', isPaused || isQueued);
        }
        if (elements.btnDeleteActiveCrawl) {
            elements.btnDeleteActiveCrawl.classList.remove('hidden');
        }
        if (elements.btnResumeRecentCrawl) {
            elements.btnResumeRecentCrawl.classList.add('hidden');
        }

        updateCrawlModalNotice();
        return;
    }

    // No active job
    updateCrawlModalNotice();

    // Check recent completed job (within 90 seconds, and not explicitly dismissed)
    if (
        recentJob &&
        recentJob.id &&
        recentJob.id !== state.activeCrawl.dismissedJobId &&
        recentJob.completed_seconds_ago !== undefined &&
        recentJob.completed_seconds_ago < (recentJob.status === 'INTERRUPTED' ? 300 : 90)
    ) {
        state.activeCrawl.job = recentJob;
        const isSuccess = recentJob.status === 'SUCCESS';
        const isPartial = recentJob.status === 'PARTIAL';
        const isInterrupted = recentJob.status === 'INTERRUPTED';

        elements.crawlStatusBanner.className = 'crawl-status-banner ' + (isSuccess || isPartial ? 'is-success' : (isInterrupted ? 'is-queued' : 'is-failed'));
        elements.crawlStatusBanner.classList.remove('hidden');

        if (elements.crawlBannerBadge) {
            elements.crawlBannerBadge.textContent = isSuccess ? 'Hoàn tất' : (isPartial ? 'Xong 1 phần' : (isInterrupted ? 'Đã dừng' : 'Thất bại'));
        }

        if (elements.crawlBannerTitle) {
            const prefix = isInterrupted ? 'Đã dừng' : (isSuccess || isPartial ? 'Hoàn tất' : 'Thất bại');
            elements.crawlBannerTitle.textContent = `${prefix}: ${recentJob.source_name || 'Thu thập dữ liệu'}`;
        }

        if (elements.crawlBannerTimeframe) {
            const tf = recentJob.timeframe_label || recentJob.timeframe || '7 ngày qua';
            elements.crawlBannerTimeframe.textContent = `Khoảng: ${tf}`;
        }

        if (elements.crawlBannerTrigger) {
            const tr = recentJob.trigger_label || recentJob.trigger || 'Thủ công';
            elements.crawlBannerTrigger.textContent = `Hình thức: ${tr}`;
        }

        if (elements.crawlBannerDetails) {
            if (isInterrupted) {
                elements.crawlBannerDetails.textContent = 'Phiên cào dữ liệu đã được dừng lại. Bạn có thể bấm nút "Tiếp tục chạy lại" ở bên phải.';
            } else {
                const res = recentJob.result || {};
                const leads = res.new_leads || 0;
                const errs = res.error_count || 0;
                elements.crawlBannerDetails.textContent = `Đã hoàn thành phiên cào dữ liệu · +${leads} cơ hội mới${errs > 0 ? ` · ${errs} lỗi` : ''}`;
            }
        }

        if (elements.crawlBannerTimer) {
            elements.crawlBannerTimer.textContent = 'Vừa xong';
        }

        if (elements.btnBannerRefresh) {
            elements.btnBannerRefresh.classList.remove('hidden');
        }
        if (elements.btnStopActiveCrawl) {
            elements.btnStopActiveCrawl.classList.add('hidden');
        }
        if (elements.btnDeleteActiveCrawl) {
            elements.btnDeleteActiveCrawl.classList.add('hidden');
        }
        if (elements.btnResumeRecentCrawl) {
            const canResume = ['INTERRUPTED', 'FAILED'].includes(recentJob.status);
            elements.btnResumeRecentCrawl.classList.toggle('hidden', !canResume);
        }

        return;
    }

    // If no active job and no recent job, but there are queued jobs:
    if (queuedJobs && queuedJobs.length > 0) {
        elements.crawlStatusBanner.className = 'crawl-status-banner is-queued';
        elements.crawlStatusBanner.classList.remove('hidden');

        if (elements.crawlBannerBadge) {
            elements.crawlBannerBadge.textContent = 'Hàng đợi';
        }
        if (elements.crawlBannerTitle) {
            elements.crawlBannerTitle.textContent = `${queuedJobs.length} yêu cầu đang chờ xử lý`;
        }
        if (elements.crawlBannerTimeframe) {
            elements.crawlBannerTimeframe.textContent = `Kế tiếp: ${queuedJobs[0].source_name}`;
        }
        if (elements.crawlBannerTrigger) {
            elements.crawlBannerTrigger.textContent = `Hình thức: ${queuedJobs[0].trigger_label || 'Thủ công'}`;
        }
        if (elements.crawlBannerDetails) {
            elements.crawlBannerDetails.textContent = 'Các yêu cầu đang xếp hàng chờ crawl worker tiếp nhận...';
        }
        if (elements.crawlBannerTimer) {
            elements.crawlBannerTimer.textContent = 'Chờ lượt';
        }
        if (elements.btnBannerRefresh) {
            elements.btnBannerRefresh.classList.add('hidden');
        }
        if (elements.btnStopActiveCrawl) {
            elements.btnStopActiveCrawl.classList.add('hidden');
        }
        if (elements.btnDeleteActiveCrawl) {
            elements.btnDeleteActiveCrawl.classList.add('hidden');
        }
        if (elements.btnResumeRecentCrawl) {
            elements.btnResumeRecentCrawl.classList.add('hidden');
        }
        return;
    }

    // Otherwise hide banner
    state.activeCrawl.job = null;
    elements.crawlStatusBanner.classList.add('hidden');
    if (elements.btnStopActiveCrawl) elements.btnStopActiveCrawl.classList.add('hidden');
    if (elements.btnDeleteActiveCrawl) elements.btnDeleteActiveCrawl.classList.add('hidden');
    if (elements.btnResumeRecentCrawl) elements.btnResumeRecentCrawl.classList.add('hidden');
    if (elements.btnBannerRefresh) {
        elements.btnBannerRefresh.classList.add('hidden');
    }
}

async function checkActiveCrawlStatus() {
    try {
        const res = await fetch('/api/crawl/active', {
            headers: { 'Cache-Control': 'no-cache' }
        });
        if (!res.ok) return null;
        const data = await res.json();
        const activeJob = data.has_active ? data.active_job : null;
        const wasActive = state.activeCrawl.job && ['QUEUED', 'RUNNING'].includes(state.activeCrawl.job.status);

        if (activeJob) {
            state.activeCrawl.job = activeJob;
            state.activeCrawl.elapsedSeconds = activeJob.elapsed_seconds || 0;
            if (!state.activeCrawl.timerInterval) {
                state.activeCrawl.timerInterval = window.setInterval(() => {
                    state.activeCrawl.elapsedSeconds += 1;
                    if (elements.crawlBannerTimer && state.activeCrawl.job && state.activeCrawl.job.status === 'RUNNING') {
                        elements.crawlBannerTimer.textContent = `⏱️ ${formatSeconds(state.activeCrawl.elapsedSeconds)}`;
                    }
                }, 1000);
            }
        } else {
            if (state.activeCrawl.timerInterval) {
                window.clearInterval(state.activeCrawl.timerInterval);
                state.activeCrawl.timerInterval = null;
            }
            if (wasActive) {
                if (state.currentPage === 'page-leads') {
                    loadLeads();
                } else if (state.currentPage === 'page-crawlers') {
                    loadSources();
                }
            }
        }

        renderCrawlStatusBanner(activeJob, data.recent_job, data.queue_depth, data.queued_jobs);
        return data;
    } catch (_) {
        return null;
    }
}

function pollActiveCrawlStatus() {
    return checkActiveCrawlStatus();
}

function startActiveCrawlMonitoring() {
    if (state.activeCrawl.pollTimeout) {
        window.clearTimeout(state.activeCrawl.pollTimeout);
        state.activeCrawl.pollTimeout = null;
    }

    const poll = async () => {
        const data = await checkActiveCrawlStatus();
        const interval = (data && (data.has_active || data.queue_depth > 0)) ? 3000 : 5000;
        state.activeCrawl.pollTimeout = window.setTimeout(poll, interval);
    };

    poll();
}

async function monitorCrawlJob(jobId) {
    if (!jobId || state.activeCrawlJobIds.has(jobId)) return;
    state.activeCrawlJobIds.add(jobId);
    let consecutiveErrors = 0;
    try {
        while (state.activeCrawlJobIds.has(jobId)) {
            await wait(3500);
            try {
                const response = await fetch('/api/crawl/jobs/' + encodeURIComponent(jobId), {
                    headers: { 'Cache-Control': 'no-cache' }
                });
                if (response.status === 404) {
                    state.activeCrawlJobIds.delete(jobId);
                    checkActiveCrawlStatus();
                    break;
                }
                if (!response.ok) throw new Error('Không đọc được trạng thái job');
                const job = await response.json();
                consecutiveErrors = 0;

                // Refresh the banner with latest status
                checkActiveCrawlStatus();

                if (!['SUCCESS', 'PARTIAL', 'FAILED', 'INTERRUPTED'].includes(job.status)) {
                    continue;
                }

                state.activeCrawlJobIds.delete(jobId);

                const result = job.result || {};
                if (job.status === 'SUCCESS') {
                    showToast(
                        'Thu thập hoàn tất: ' + (result.total_discovered || 0) +
                        ' liên kết, thêm ' + (result.new_leads || 0) + ' cơ hội mới.',
                        'success'
                    );
                } else if (job.status === 'PARTIAL') {
                    showToast(
                        'Thu thập đã xong một phần; có ' + (result.error_count || 0) +
                        ' lỗi cần kiểm tra.',
                        'warning'
                    );
                } else if (job.status === 'INTERRUPTED') {
                    showToast('Đã dừng luồng thu thập.', 'info');
                } else {
                    showToast(job.error_message || 'Job thu thập không hoàn tất.', 'error');
                }
                if (state.currentPage === 'page-leads') {
                    state.leads.page = 1;
                    loadLeads();
                } else if (state.currentPage === 'page-crawlers') {
                    loadSources();
                }
                return;
            } catch (error) {
                consecutiveErrors += 1;
                if (consecutiveErrors >= 3) {
                    showToast('Job vẫn chạy nhưng tạm mất kết nối cập nhật trạng thái.', 'info');
                    return;
                }
            }
        }
    } finally {
        state.activeCrawlJobIds.delete(jobId);
    }
}

async function executeCrawl() {
    const sourceId = elements.crawlSourceSelect.value || null;
    const timeframe = elements.crawlTimeframeSelect ? elements.crawlTimeframeSelect.value : '1_week';
    const force = false;

    elements.btnStartCrawl.disabled = true;
    elements.btnCancelCrawl.disabled = true;
    elements.crawlProgressBox.classList.remove('hidden');
    elements.crawlProgressText.textContent = "Đang gửi lệnh sang crawl worker…";

    try {
        const payload = {
            source_id: sourceId,
            timeframe: timeframe,
            force_recrawl: force
        };

        const res = await fetch('/api/crawl/run?sync=false', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error('Yêu cầu crawl không thành công');

        const job = await res.json();
        showToast(
            "Đã xếp lệnh thu thập " + (sourceId || "tất cả nguồn") +
            ". Bạn có thể tiếp tục thao tác.",
            "success"
        );
        elements.crawlModal.classList.add("hidden");
        if (state.currentPage === 'page-crawlers') loadSources();

        // Immediately update active status banner
        checkActiveCrawlStatus();
        monitorCrawlJob(job.id);
    } catch (err) {
        showToast(`Lỗi: ${err.message}`, 'error');
    } finally {
        elements.btnStartCrawl.disabled = false;
        elements.btnCancelCrawl.disabled = false;
        elements.crawlProgressBox.classList.add('hidden');
    }
}


// ==========================================
// Configurable Scheduler Modal
// ==========================================
async function openScheduleModal() {
    try {
        const res = await fetch('/api/scheduler/status');
        const data = await res.json();
        const schedule = data.schedule || {};
        const hour = String(schedule.hour ?? 6).padStart(2, '0');
        const minute = String(schedule.minute ?? 0).padStart(2, '0');
        elements.scheduleTime.value = `${hour}:${minute}`;
    } catch (_) {
        // Keep safe defaults when status is temporarily unavailable.
    }
    elements.scheduleModal.classList.remove('hidden');
}

async function saveSchedule(event) {
    event.preventDefault();
    const [hour, minute] = elements.scheduleTime.value.split(':').map(Number);
    const payload = { enabled: true, hour, minute };
    try {
        const res = await fetch('/api/scheduler/config', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Không thể lưu lịch');
        elements.scheduleModal.classList.add('hidden');
        showToast('Đã lưu và bật lịch thu thập.', 'success');
        loadSchedulerStatus();
    } catch (error) {
        showToast(`Lỗi đặt lịch: ${error.message}`, 'error');
    }
}

// ==========================================
// Event Listeners Setup
// ==========================================
function initEvents() {
    // Search with debounce
    let debounceTimer;
    elements.filterQuery.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            state.leads.query = e.target.value.trim();
            state.leads.page = 1;
            loadLeads();
        }, 350);
    });

    // Action filter
    elements.filterAction.addEventListener('change', (e) => {
        state.leads.action = e.target.value;
        state.leads.page = 1;
        loadLeads();
    });

    // Source filter
    elements.filterSource.addEventListener('change', (e) => {
        state.leads.source = e.target.value;
        state.leads.page = 1;
        loadLeads();
    });

    // Sort filter
    elements.filterSort.addEventListener('change', (e) => {
        state.leads.sortBy = e.target.value;
        state.leads.page = 1;
        loadLeads();
    });

    // Pagination buttons
    elements.btnPrevPage.addEventListener('click', () => {
        if (state.leads.page > 1) {
            state.leads.page--;
            loadLeads();
        }
    });

    elements.btnNextPage.addEventListener('click', () => {
        if (state.leads.page < state.leads.totalPages) {
            state.leads.page++;
            loadLeads();
        }
    });

    // Source registry events
    if (elements.btnOpenSources) elements.btnOpenSources.addEventListener('click', openSourceModal);
    if (elements.btnCloseSourceModal) elements.btnCloseSourceModal.addEventListener('click', closeSourceModal);
    if (elements.btnCancelSource) elements.btnCancelSource.addEventListener('click', closeSourceModal);
    if (elements.sourceForm) elements.sourceForm.addEventListener('submit', saveSources);
    if (elements.sourceNameInput) elements.sourceNameInput.addEventListener('input', () => {
        elements.sourceFormStatus.textContent = '';
        updateSourcePreview();
    });
    if (elements.sourceUrlInput) elements.sourceUrlInput.addEventListener('input', () => {
        elements.sourceFormStatus.textContent = '';
        updateSourcePreview();
    });
    if (elements.sourceModal) {
        elements.sourceModal.addEventListener('click', event => {
            if (event.target === elements.sourceModal) closeSourceModal();
        });
    }

    // Keyword registry events
    if (elements.btnOpenKeywords) elements.btnOpenKeywords.addEventListener('click', openKeywordModal);
    if (elements.btnCloseKeywordModal) elements.btnCloseKeywordModal.addEventListener('click', closeKeywordModal);
    if (elements.btnCancelKeywords) elements.btnCancelKeywords.addEventListener('click', closeKeywordModal);
    if (elements.keywordForm) elements.keywordForm.addEventListener('submit', saveKeywords);
    if (elements.keywordInput) elements.keywordInput.addEventListener('input', updateKeywordPreview);
    if (elements.keywordFile) elements.keywordFile.addEventListener('change', handleKeywordFile);
    if (elements.keywordFilter) elements.keywordFilter.addEventListener('input', renderKeywordList);
    if (elements.btnRefreshKeywords) {
        elements.btnRefreshKeywords.addEventListener('click', () => loadKeywords(true));
    }
    if (elements.keywordModal) {
        elements.keywordModal.addEventListener('click', event => {
            if (event.target === elements.keywordModal) closeKeywordModal();
        });
    }
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && elements.keywordModal && !elements.keywordModal.classList.contains('hidden')) {
            closeKeywordModal();
        }
        if (event.key === 'Escape' && elements.sourceModal && !elements.sourceModal.classList.contains('hidden')) {
            closeSourceModal();
        }
        if (event.key === 'Escape' && elements.scoringPromptModal && !elements.scoringPromptModal.classList.contains('hidden')) {
            closePromptModal('scoring');
        }
        if (event.key === 'Escape' && elements.salesPromptModal && !elements.salesPromptModal.classList.contains('hidden')) {
            closePromptModal('sales');
        }
    });

    // Independent prompt editors
    bindPromptEditor('scoring');
    bindPromptEditor('sales');

    // Scheduler Events
    if (elements.btnConfigureScheduler) elements.btnConfigureScheduler.addEventListener('click', openScheduleModal);
    if (elements.scheduleForm) elements.scheduleForm.addEventListener('submit', saveSchedule);
    if (elements.btnCloseScheduleModal) elements.btnCloseScheduleModal.addEventListener('click', () => elements.scheduleModal.classList.add('hidden'));
    if (elements.btnCancelSchedule) elements.btnCancelSchedule.addEventListener('click', () => elements.scheduleModal.classList.add('hidden'));
    if (elements.scheduleModal) elements.scheduleModal.addEventListener('click', (event) => {
        if (event.target === elements.scheduleModal) elements.scheduleModal.classList.add('hidden');
    });
    if (elements.btnToggleScheduler) {
        elements.btnToggleScheduler.addEventListener('click', toggleScheduler);
    }

    // Refresh buttons
    elements.btnRefresh.addEventListener('click', () => {
        loadLeads();
        showToast('Đã làm mới danh sách lead.', 'info');
    });

    elements.btnRefreshSources.addEventListener('click', async () => {
        elements.btnRefreshSources.disabled = true;
        try {
            const response = await fetch('/api/sources/refresh', { method: 'POST' });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Không thể đồng bộ Sources');
            await loadSources();
            await loadSchedulerStatus();
            showToast('Đã đồng bộ danh sách nguồn.', 'success');
        } catch (error) {
            showToast(error.message + '. Dữ liệu đang hiển thị vẫn được giữ nguyên.', 'error');
        } finally {
            elements.btnRefreshSources.disabled = false;
        }
    });

    // Export CSV
    const triggerExport = () => {
        window.location.href = '/api/export/csv';
        showToast('Đang chuẩn bị tệp CSV...', 'success');
    };
    elements.btnExportCsv.addEventListener('click', triggerExport);

    // Modal Close
    elements.btnCloseModal.addEventListener('click', () => elements.leadModal.classList.add('hidden'));
    elements.leadModal.addEventListener('click', (e) => {
        if (e.target === elements.leadModal) elements.leadModal.classList.add('hidden');
    });

    // Crawl Trigger Modal
    elements.btnTriggerCrawlButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            updateCrawlModalNotice();
            elements.crawlModal.classList.remove('hidden');
        });
    });
    elements.btnCloseCrawlModal.addEventListener('click', () => elements.crawlModal.classList.add('hidden'));
    elements.btnCancelCrawl.addEventListener('click', () => elements.crawlModal.classList.add('hidden'));
    elements.crawlModal.addEventListener('click', (e) => {
        if (e.target === elements.crawlModal) elements.crawlModal.classList.add('hidden');
    });
    elements.btnStartCrawl.addEventListener('click', executeCrawl);

    if (elements.btnCloseCrawlBanner) {
        elements.btnCloseCrawlBanner.addEventListener('click', dismissCrawlBanner);
    }
    if (elements.btnToggleQueueList) {
        elements.btnToggleQueueList.addEventListener('click', () => {
            if (!elements.crawlQueuePanel) return;
            const isHidden = elements.crawlQueuePanel.classList.toggle('hidden');
            elements.btnToggleQueueList.classList.toggle('is-active', !isHidden);
            elements.btnToggleQueueList.setAttribute('aria-expanded', String(!isHidden));
        });
    }
    if (elements.btnBannerRefresh) {
        elements.btnBannerRefresh.addEventListener('click', () => {
            if (state.currentPage === 'page-leads') {
                loadLeads();
            } else if (state.currentPage === 'page-crawlers') {
                loadSources();
            }
            elements.btnBannerRefresh.classList.add('hidden');
        });
    }
    if (elements.btnClearCrawlQueue) {
        elements.btnClearCrawlQueue.addEventListener('click', async () => {
            if (!confirm('Bạn có chắc muốn xóa tất cả các lệnh đang chờ trong hàng đợi không?')) return;
            try {
                const res = await fetch('/api/crawl/queue', { method: 'DELETE' });
                if (res.ok) {
                    showToast('Đã xóa tất cả các lệnh đang chờ trong hàng đợi', 'info');
                    pollActiveCrawlStatus();
                } else {
                    showToast('Không thể xóa hàng đợi', 'error');
                }
            } catch (err) {
                console.error('Lỗi khi xóa hàng đợi:', err);
                showToast('Lỗi kết nối khi xóa hàng đợi', 'error');
            }
        });
    }
    // Pause Active Crawl
    const handlePause = async () => {
        try {
            const res = await fetch('/api/crawl/active/pause', { method: 'POST' });
            if (res.ok) {
                showToast('Đã tạm dừng luồng crawl (dữ liệu đã quét được bảo lưu 100%)', 'info');
                pollActiveCrawlStatus();
            } else {
                showToast('Không thể tạm dừng luồng crawl', 'error');
            }
        } catch (err) {
            showToast('Lỗi kết nối khi tạm dừng', 'error');
        }
    };
    if (elements.btnPauseActiveCrawl) {
        elements.btnPauseActiveCrawl.addEventListener('click', handlePause);
    }
    if (elements.btnStopActiveCrawl && elements.btnStopActiveCrawl !== elements.btnPauseActiveCrawl) {
        elements.btnStopActiveCrawl.addEventListener('click', handlePause);
    }

    // Resume Active Crawl
    if (elements.btnResumeActiveCrawl) {
        elements.btnResumeActiveCrawl.addEventListener('click', async () => {
            try {
                const res = await fetch('/api/crawl/active/resume', { method: 'POST' });
                if (res.ok) {
                    showToast('Đang tiếp tục cào dữ liệu...', 'info');
                    pollActiveCrawlStatus();
                } else {
                    showToast('Không thể tiếp tục luồng crawl', 'error');
                }
            } catch (err) {
                showToast('Lỗi kết nối khi tiếp tục', 'error');
            }
        });
    }

    // Delete Active Crawl (Cancels immediately and deletes from queue/DB)
    if (elements.btnDeleteActiveCrawl) {
        elements.btnDeleteActiveCrawl.addEventListener('click', async () => {
            if (!confirm('Bạn có chắc muốn hủy bỏ và xóa hoàn toàn luồng crawl này không?\n\n- Tiến trình cào sẽ dừng hẳn và đóng trình duyệt.\n- Nếu có lệnh trong hàng đợi, hệ thống sẽ tự động chạy lệnh tiếp theo.')) return;
            try {
                const res = await fetch('/api/crawl/active', { method: 'DELETE' });
                if (res.ok) {
                    showToast('Đã hủy và xóa luồng crawl thành công', 'info');
                    pollActiveCrawlStatus();
                } else {
                    showToast('Không thể xóa luồng crawl', 'error');
                }
            } catch (err) {
                showToast('Lỗi kết nối khi xóa luồng', 'error');
            }
        });
    }
    if (elements.btnResumeRecentCrawl) {
        elements.btnResumeRecentCrawl.addEventListener('click', async () => {
            const recent = state.activeCrawl.job;
            if (!recent) return;
            try {
                let res;
                if (recent.id) {
                    res = await fetch(`/api/crawl/jobs/${recent.id}/resume`, { method: 'POST' });
                }
                if (!res || !res.ok) {
                    const payload = {
                        source_id: recent.source_id || null,
                        timeframe: recent.timeframe || '1_week',
                        force_recrawl: false
                    };
                    res = await fetch('/api/crawl/run', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                }
                if (res && res.ok) {
                    showToast('Đã tiếp tục kích hoạt phiên cào mới', 'info');
                    pollActiveCrawlStatus();
                } else {
                    showToast('Không thể tiếp tục phiên cào', 'error');
                }
            } catch (err) {
                showToast('Lỗi kết nối', 'error');
            }
        });
    }
    if (elements.btnPauseAllQueue) {
        elements.btnPauseAllQueue.addEventListener('click', async () => {
            const isAllPaused = state.activeCrawl.allPaused;
            const endpoint = isAllPaused ? '/api/crawl/queue/resume-all' : '/api/crawl/queue/pause-all';
            try {
                const res = await fetch(endpoint, { method: 'POST' });
                if (res.ok) {
                    showToast(isAllPaused ? 'Đã tiếp tục tất cả các lệnh trong hàng đợi' : 'Đã tạm dừng tất cả các lệnh trong hàng đợi', 'info');
                    pollActiveCrawlStatus();
                } else {
                    showToast('Không thể thao tác hàng đợi', 'error');
                }
            } catch (err) {
                showToast('Lỗi kết nối', 'error');
            }
        });
    }
}

// ==========================================
// Scheduler API & UI Helpers
// ==========================================
async function loadSchedulerStatus() {
    try {
        const res = await fetch('/api/scheduler/status');
        if (!res.ok) return;
        const data = await res.json();

        if (elements.schStatusText) {
            if (data.enabled && data.is_running) {
                elements.schStatusText.textContent = `Đang chạy · ${data.schedule_label}`;
                elements.schStatusText.className = 'text-success';
                elements.schedulerStatusDot.className = 'dot-indicator online';
                elements.schedulerToggleText.textContent = 'Đang bật';
            } else if (data.enabled) {
                elements.schStatusText.textContent = 'Đã bật lịch · crawl worker chưa chạy';
                elements.schStatusText.className = 'text-secondary';
                elements.schedulerStatusDot.className = 'dot-indicator offline';
                elements.schedulerToggleText.textContent = 'Đang bật';
            } else {
                elements.schStatusText.textContent = 'Đang tạm dừng';
                elements.schStatusText.className = 'text-secondary';
                elements.schedulerStatusDot.className = 'dot-indicator offline';
                elements.schedulerToggleText.textContent = 'Đang tắt';
            }
        }

        if (elements.schNextRun) {
            elements.schNextRun.textContent = data.next_run_display || 'Chưa thiết lập';
        }
        if (elements.schLastRun) {
            elements.schLastRun.textContent = data.last_run_at ? formatDate(data.last_run_at) : 'Chưa có dữ liệu';
        }
        if (elements.schTotalRuns) {
            elements.schTotalRuns.textContent = `${data.total_automated_runs || 0} phiên`;
        }
    } catch (e) {
        console.warn('Could not load scheduler status:', e);
    }
}

async function toggleScheduler() {
    try {
        const res = await fetch('/api/scheduler/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        if (data.enabled) {
            showToast('Đã bật lịch thu thập tự động.', 'success');
        } else {
            showToast('Đã tắt lịch thu thập tự động.', 'info');
        }
        loadSchedulerStatus();
    } catch (err) {
        showToast('Lỗi khi chuyển trạng thái scheduler: ' + err.message, 'error');
    }
}

// ==========================================
// Initialization
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    initEvents();
    initRouter();
    loadSchedulerStatus();
    startActiveCrawlMonitoring();
});
