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
    isSavingSources: false
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
async function openLeadModal(lead) {
    try {
        const response = await fetch(`/api/leads/${encodeURIComponent(lead.id)}`);
        if (response.ok) lead = await response.json();
    } catch (error) {
        console.warn('Không tải được Company Profile chi tiết:', error);
    }
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

    // Company Profile from verified round-two crawl.
    if (lead.company_profile || lead.enrichment_status) {
        const profile = lead.company_profile;
        const secProfile = document.createElement('div');
        secProfile.className = 'detail-section';
        const hProfile = document.createElement('h4');
        hProfile.textContent = 'Hồ sơ tổ chức · Crawl vòng 2';
        secProfile.appendChild(hProfile);

        const profileGrid = document.createElement('div');
        profileGrid.className = 'detail-grid';
        const addProfileItem = (label, value) => {
            const item = document.createElement('div');
            item.className = 'detail-item';
            const key = document.createElement('span');
            key.className = 'detail-label';
            key.textContent = label;
            const text = document.createElement('span');
            text.className = 'detail-value';
            text.textContent = value || 'Chưa tìm thấy';
            item.append(key, text);
            profileGrid.appendChild(item);
        };
        addProfileItem('Trạng thái:', profile?.profile_status || lead.enrichment_status);
        addProfileItem('Ngành:', profile?.industry);
        addProfileItem('Quy mô:', profile?.size);
        addProfileItem('Nhân sự:', profile?.employee_count);
        addProfileItem('Địa điểm:', Array.isArray(profile?.locations) ? profile.locations.join(', ') : profile?.locations);
        addProfileItem('Công nghệ công bố:', Array.isArray(profile?.technologies) ? profile.technologies.join(', ') : profile?.technologies);
        secProfile.appendChild(profileGrid);

        if (profile?.official_url) {
            const officialLink = document.createElement('a');
            officialLink.className = 'btn btn-quiet btn-sm';
            officialLink.href = profile.official_url;
            officialLink.target = '_blank';
            officialLink.rel = 'noopener noreferrer';
            officialLink.textContent = 'Mở website đã xác minh';
            secProfile.appendChild(officialLink);
        }
        if (profile?.contacts?.length) {
            const contactTitle = document.createElement('h4');
            contactTitle.textContent = 'Đầu mối công khai và khả năng quyết định';
            secProfile.appendChild(contactTitle);
            profile.contacts.forEach(contact => {
                const card = document.createElement('div');
                card.className = 'evidence-box';
                const headline = [contact.full_name, contact.raw_title].filter(Boolean).join(' · ') || 'Đầu mối công khai';
                const score = Number.isFinite(contact.decision_score) ? ` · ${contact.decision_score}/100` : '';
                card.textContent = `${headline}${score}
${contact.email || ''} ${contact.phone || ''}
${contact.evidence_text || ''}`.trim();
                const source = document.createElement('a');
                source.href = contact.source_url;
                source.target = '_blank';
                source.rel = 'noopener noreferrer';
                source.textContent = 'Xem bằng chứng';
                card.appendChild(document.createElement('br'));
                card.appendChild(source);
                secProfile.appendChild(card);
            });
        }
        const incomplete = profile?.missing_information || [];
        if (incomplete.length || lead.enrichment_message) {
            const note = document.createElement('div');
            note.className = 'evidence-box';
            note.textContent = [
                incomplete.length ? `Chưa tìm thấy: ${incomplete.join(', ')}` : '',
                lead.enrichment_message || profile?.error_message || ''
            ].filter(Boolean).join(' · ');
            secProfile.appendChild(note);
        }
        modalBody.appendChild(secProfile);
    }

    // Contact Info & Action Link
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
        syncCrawlSourceOptions();
        if (elements.sourceCountKicker) {
            elements.sourceCountKicker.textContent = state.sources.length + ' kết nối';
        }
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function syncCrawlSourceOptions() {
    const selected = elements.crawlSourceSelect.value;
    elements.crawlSourceSelect.replaceChildren();
    const allOption = document.createElement('option');
    allOption.value = '';
    allOption.textContent = 'Tất cả nguồn đang bật';
    elements.crawlSourceSelect.appendChild(allOption);
    state.sources.forEach(source => {
        const option = document.createElement('option');
        option.value = source.id;
        option.textContent = source.name;
        option.disabled = !source.enabled;
        elements.crawlSourceSelect.appendChild(option);
    });
    if ([...elements.crawlSourceSelect.options].some(option => option.value === selected && !option.disabled)) {
        elements.crawlSourceSelect.value = selected;
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
        seedP.textContent = `URL nguồn: ${src.base_url || 'Chưa cấu hình'}`;
        seedP.className = 'source-url';
        meta.appendChild(seedP);

        const lastP = document.createElement('p');
        lastP.textContent = 'Cập nhật gần nhất: ' + (src.last_crawl_at ? formatDate(src.last_crawl_at) : 'Chưa chạy');
        lastP.className = 'source-last-run';
        meta.appendChild(lastP);
        if (src.last_error) {
            const errorNote = document.createElement('p');
            errorNote.className = 'source-error-note';
            errorNote.textContent = 'Nguồn chưa crawl được · cần cập nhật sau';
            meta.appendChild(errorNote);
        }
        card.appendChild(meta);

        // Action Button
        const btnRow = document.createElement('div');
        btnRow.className = 'source-card-actions';

        const runBtn = document.createElement('button');
        runBtn.className = 'btn btn-xs btn-outline';
        runBtn.textContent = src.enabled ? 'Thu thập nguồn này' : 'Cần cập nhật sau';
        runBtn.disabled = !src.enabled;
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
    elements.sourceUrlPreview.textContent = url
        ? (validUrl ? 'URL hợp lệ và sẽ được kiểm tra sau khi lưu.' : 'URL cần bắt đầu bằng http:// hoặc https://.')
        : 'Mỗi lần thêm một URL, hỗ trợ HTTP và HTTPS.';
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
    elements.sourceFormStatus.textContent =
        'URL đã được gửi lên backend. Quá trình kiểm tra có thể mất vài giây.';
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
            showToast('Đã lưu và kiểm tra nguồn “' + name + '”.', 'success');
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
        ? 'Đang đồng bộ lại từ Google Sheets...'
        : 'Đang đọc dữ liệu...';
    try {
        const endpoint = refreshFromSheet ? '/api/keywords/refresh' : '/api/keywords';
        const res = await fetch(endpoint, { method: refreshFromSheet ? 'POST' : 'GET' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Không thể tải keyword');
        state.keywords = Array.isArray(data.items) ? data.items : [];
        elements.keywordSourceLabel.textContent =
            (data.total || 0) + ' keyword · ' + (data.discovery_total || 0) + ' dùng cho search';
        renderKeywordList();
        if (refreshFromSheet) showToast('Đã đồng bộ keyword từ Google Sheets.', 'success');
    } catch (error) {
        elements.keywordSourceLabel.textContent = 'Không thể kết nối Google Sheets';
        elements.keywordList.replaceChildren();
        const stateNode = document.createElement('div');
        stateNode.className = 'keyword-list-state error';
        stateNode.textContent = error.message + '. Kiểm tra worksheet Keywords rồi thử đồng bộ lại.';
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
        showToast('File keyword phải nhỏ hơn hoặc bằng 1 MB.', 'error');
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
    elements.keywordFormStatus.textContent = 'Đang cập nhật worksheet Keywords.';
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
                ? 'Đã cập nhật ' + changed + ' keyword; bỏ qua ' + (data.duplicates || 0) + ' mục trùng.'
                : 'Không có thay đổi; ' + (data.duplicates || 0) + ' keyword đã tồn tại.',
            changed > 0 ? 'success' : 'info'
        );
        updateKeywordPreview();
        await loadKeywords(false);
    } catch (error) {
        elements.keywordFormStatus.textContent =
            error.message + '. Nội dung nhập vẫn được giữ để bạn thử lại.';
    } finally {
        state.isSavingKeywords = false;
        elements.btnSaveKeywords.textContent = 'Thêm vào Google Sheets';
        updateKeywordPreview();
    }
}

// ==========================================
// Crawl Trigger Execution
// ==========================================
async function executeCrawl() {
    const sourceId = elements.crawlSourceSelect.value || null;
    const timeframe = elements.crawlTimeframeSelect ? elements.crawlTimeframeSelect.value : '1_week';
    const force = false;

    elements.btnStartCrawl.disabled = true;
    elements.btnCancelCrawl.disabled = true;
    elements.crawlProgressBox.classList.remove('hidden');
    elements.crawlProgressText.textContent = `Đang thu thập từ ${sourceId || '10 nguồn'} · ${timeframe}...`;

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

    elements.btnRefreshSources.addEventListener('click', async () => {
        elements.btnRefreshSources.disabled = true;
        try {
            const response = await fetch('/api/sources/refresh', { method: 'POST' });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Không thể đồng bộ Sources');
            await loadSources();
            await loadSchedulerStatus();
            showToast('Đã đồng bộ nguồn từ Google Sheets.', 'success');
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
