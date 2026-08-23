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
    isLoading: false
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


    // Page 2: Crawlers
    sourcesGrid: document.getElementById('sources-grid'),
    btnRefreshSources: document.getElementById('btn-refresh-sources'),

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
    if (pageId === 'page-leads') {
        loadLeads();
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
// Lead Detail Modal Logic
// ==========================================
function openLeadModal(lead) {
    elements.modalTitle.textContent = lead.title;
    
    // Set Action Badge
    elements.modalActionBadge.className = `badge badge-${lead.recommended_action.toLowerCase()}`;
    elements.modalActionBadge.textContent = lead.recommended_action;

    const modalBody = elements.modalBody;
    while (modalBody.firstChild) modalBody.removeChild(modalBody.firstChild);

    // Section 1: Overview Grid
    const secOverview = document.createElement('div');
    secOverview.className = 'detail-section';
    const hOverview = document.createElement('h4');
    hOverview.textContent = 'Thông tin đơn vị và ngân sách';
    secOverview.appendChild(hOverview);

    const grid = document.createElement('div');
    grid.className = 'detail-grid';

    const addDetailItem = (label, value) => {
        const item = document.createElement('div');
        item.className = 'detail-item';
        const l = document.createElement('span');
        l.className = 'detail-label';
        l.textContent = label;
        const v = document.createElement('span');
        v.className = 'detail-value';
        v.textContent = value || 'Chưa cập nhật';
        item.appendChild(l);
        item.appendChild(v);
        grid.appendChild(item);
    };

    addDetailItem('Cơ quan / Đơn vị:', lead.organization_name);
    addDetailItem('Ngân sách dự kiến:', formatCurrency(lead.budget_value) || lead.budget_text || 'Chưa xác định');
    addDetailItem('Địa bàn triển khai:', lead.location || 'Toàn quốc');
    addDetailItem('Cổng thông tin nguồn:', formatSourceBadge(lead.source).name);
    addDetailItem('Ngày xuất bản:', formatDate(lead.published_at));
    addDetailItem('Hạn nộp hồ sơ / Tiếp cận:', formatDate(lead.deadline));
    secOverview.appendChild(grid);
    modalBody.appendChild(secOverview);

    // Section 2: AI Need Summary
    const secNeed = document.createElement('div');
    secNeed.className = 'detail-section';
    const hNeed = document.createElement('h4');
    hNeed.textContent = 'Nhu cầu được ghi nhận';
    secNeed.appendChild(hNeed);
    const pNeed = document.createElement('p');
    pNeed.style.lineHeight = '1.6';
    pNeed.textContent = lead.need_summary || lead.title;
    secNeed.appendChild(pNeed);
    modalBody.appendChild(secNeed);

    // Section 3: AI Sales Strategy
    if (lead.sales_strategy) {
        const secStrat = document.createElement('div');
        secStrat.className = 'detail-section';
        const hStrat = document.createElement('h4');
        hStrat.textContent = 'Gợi ý hướng tiếp cận';
        secStrat.appendChild(hStrat);
        const boxStrat = document.createElement('div');
        boxStrat.className = 'evidence-box';
        boxStrat.classList.add('strategy-box');
        boxStrat.textContent = lead.sales_strategy;
        secStrat.appendChild(boxStrat);
        modalBody.appendChild(secStrat);
    }

    // Section 4: Score Reasons Breakdown
    if (lead.score_reasons && lead.score_reasons.length > 0) {
        const secReasons = document.createElement('div');
        secReasons.className = 'detail-section';
        const hReasons = document.createElement('h4');
        hReasons.textContent = `Cơ sở chấm điểm · ${lead.score}/100`;
        secReasons.appendChild(hReasons);

        const rList = document.createElement('div');
        rList.className = 'score-breakdown-list';
        lead.score_reasons.forEach(r => {
            const rItem = document.createElement('div');
            rItem.className = 'score-breakdown-item';
            rItem.textContent = r;
            rList.appendChild(rItem);
        });
        secReasons.appendChild(rList);
        modalBody.appendChild(secReasons);
    }

    // Section 5: Evidence
    if (lead.evidence && lead.evidence.length > 0) {
        const secEv = document.createElement('div');
        secEv.className = 'detail-section';
        const hEv = document.createElement('h4');
        hEv.textContent = 'Minh chứng và nguồn tham chiếu';
        secEv.appendChild(hEv);
        lead.evidence.forEach(ev => {
            const evBox = document.createElement('div');
            evBox.className = 'evidence-box';
            evBox.textContent = `“${ev}”`;
            secEv.appendChild(evBox);
        });
        modalBody.appendChild(secEv);
    }

    // Section 6: Contact Info & Action Link
    const secContact = document.createElement('div');
    secContact.className = 'detail-section';
    const hContact = document.createElement('h4');
    hContact.textContent = 'Liên hệ và nguồn gốc';
    secContact.appendChild(hContact);

    const contactDiv = document.createElement('div');
    contactDiv.className = 'contact-row';

    const cText = document.createElement('div');
    cText.textContent = `Email: ${lead.contact_email || 'Chưa rõ'} | SĐT: ${lead.contact_phone || 'Chưa rõ'}`;
    contactDiv.appendChild(cText);

    const openLinkBtn = document.createElement('a');
    openLinkBtn.className = 'btn btn-primary btn-sm';
    openLinkBtn.href = lead.source_url;
    openLinkBtn.target = '_blank';
    openLinkBtn.rel = 'noopener noreferrer';
    openLinkBtn.textContent = 'Mở nguồn gốc';
    contactDiv.appendChild(openLinkBtn);

    secContact.appendChild(contactDiv);
    modalBody.appendChild(secContact);

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
        renderSourcesGrid();
    } catch (err) {
        showToast(err.message, 'error');
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
        sDot.className = `status-dot ${src.enabled ? 'online' : 'offline'}`;
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
        seedP.textContent = `URL nguồn: ${src.base_url || 'Chưa cấu hình'}`;
        seedP.className = 'source-url';
        meta.appendChild(seedP);

        const lastP = document.createElement('p');
        lastP.textContent = `Cập nhật gần nhất: ${src.last_crawl_at ? formatDate(src.last_crawl_at) : 'Chưa chạy'}`;
        lastP.className = 'source-last-run';
        meta.appendChild(lastP);
        card.appendChild(meta);

        // Action Button
        const btnRow = document.createElement('div');
        btnRow.className = 'source-card-actions';

        const runBtn = document.createElement('button');
        runBtn.className = 'btn btn-xs btn-outline';
        runBtn.textContent = 'Thu thập nguồn này';
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
// Crawl Trigger Execution
// ==========================================
async function executeCrawl() {
    const sourceId = elements.crawlSourceSelect.value || null;
    const timeframe = elements.crawlTimeframeSelect ? elements.crawlTimeframeSelect.value : '1_week';
    const maxItems = 20;
    const force = false;

    elements.btnStartCrawl.disabled = true;
    elements.btnCancelCrawl.disabled = true;
    elements.crawlProgressBox.classList.remove('hidden');
    elements.crawlProgressText.textContent = `Đang thu thập từ ${sourceId || '10 nguồn'} · ${timeframe}...`;

    try {
        const payload = {
            source_id: sourceId,
            timeframe: timeframe,
            max_items: maxItems,
            force_recrawl: force
        };

        const res = await fetch('/api/crawl/run?sync=false', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error('Yêu cầu crawl không thành công');

        const runs = await res.json();
        if (runs.length === 0) {
            showToast('Đã bắt đầu thu thập dữ liệu trong nền.', 'success');
        } else {
            let totalNew = 0;
            let totalDisc = 0;
            runs.forEach(r => {
                totalNew += r.new_leads || 0;
                totalDisc += r.total_discovered || 0;
            });
            showToast(`Hoàn tất: ${totalDisc} liên kết, thêm ${totalNew} cơ hội mới.`, 'success');
        }
        elements.crawlModal.classList.add('hidden');

        // Refresh currently active page
        if (state.currentPage === 'page-leads') {
            state.leads.page = 1;
            loadLeads();
            } else if (state.currentPage === 'page-crawlers') {
            loadSources();
            }
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

    elements.btnRefreshSources.addEventListener('click', () => {
        loadSources();
        loadSchedulerStatus();
        showToast('Đã làm mới trạng thái nguồn và lịch chạy.', 'info');
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
        btn.addEventListener('click', () => elements.crawlModal.classList.remove('hidden'));
    });
    elements.btnCloseCrawlModal.addEventListener('click', () => elements.crawlModal.classList.add('hidden'));
    elements.btnCancelCrawl.addEventListener('click', () => elements.crawlModal.classList.add('hidden'));
    elements.crawlModal.addEventListener('click', (e) => {
        if (e.target === elements.crawlModal) elements.crawlModal.classList.add('hidden');
    });
    elements.btnStartCrawl.addEventListener('click', executeCrawl);
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
            } else {
                elements.schStatusText.textContent = 'Đang tạm dừng';
                elements.schStatusText.className = 'text-secondary';
                elements.schedulerStatusDot.className = 'dot-indicator offline';
                elements.schedulerToggleText.textContent = 'Đang tắt';
            }
        }

        if (elements.schNextRun) {
            elements.schNextRun.textContent = data.next_run_display || 'Chưa xác định';
        }

        if (elements.schLastRun) {
            if (data.last_run_at) {
                const summary = data.last_run_summary || {};
                elements.schLastRun.textContent = `${new Date(data.last_run_at).toLocaleTimeString('vi-VN')} (+${summary.new_leads || 0} lead mới)`;
            } else {
                elements.schLastRun.textContent = 'Chưa có phiên gần đây';
            }
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
});
