function initNewsPage() {
    // Clear old article cache to remove any stuck dummy data
    for (let i = localStorage.length - 1; i >= 0; i--) {
        const key = localStorage.key(i);
        if (key && key.startsWith('nm_article_')) {
            localStorage.removeItem(key);
        }
    }
    
    const themeToggle = document.getElementById('nm-theme-toggle');
    const savedTheme = localStorage.getItem('av_theme');
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    if (savedTheme === 'dark' || (savedTheme === null && prefersDark)) {
        if (themeToggle) themeToggle.innerHTML = '<i class="fa fa-sun-o"></i>';
    } else {
        if (themeToggle) themeToggle.innerHTML = '<i class="fa fa-moon-o"></i>';
    }

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const mainToggle = document.getElementById('av-dark-toggle');
            if (mainToggle) mainToggle.click();
        });

        // Watch for changes to the HTML data-theme attribute to instantly sync the icon
        const observer = new MutationObserver(() => {
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
            themeToggle.innerHTML = isDark ? '<i class="fa fa-sun-o"></i>' : '<i class="fa fa-moon-o"></i>';
        });
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    }

    // Ensure news navigation bar is always visible on news pages
    const newsNav = document.querySelector('.av-news-nav');
    if (newsNav && (window.location.pathname.startsWith('/news') || document.querySelector('.nm-news-page'))) {
        newsNav.style.display = 'block';
    }

    const categoryColors = {
        '#nm-global-news': '#00a69c',     // Teal
        '#nm-travel-guides': '#f39c12',   // Orange
        '#nm-must-read-list': '#e84393',  // Pink/Purple
        '#nm-gaming-section': '#e32636',  // Red
        '#nm-fitness-section': '#27ae60'  // Green
    };

    // ScrollSpy: Dynamically change active navbar link and accent color as user scrolls down
    function updateDynamicNavScroll() {
        const scrollY = window.scrollY || window.pageYOffset || 0;
        const navBar = document.querySelector('.av-news-nav');
        if (!navBar) return;

        // Dynamic Header glass/shadow effect on scroll
        if (scrollY > 20) {
            navBar.classList.add('nav-scrolled');
            navBar.style.boxShadow = '0 4px 15px rgba(0, 0, 0, 0.15)';
        } else {
            navBar.classList.remove('nav-scrolled');
            navBar.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.08)';
        }

        // Only run section highlight if we are on the main /news page
        if (window.location.pathname !== '/news' && window.location.pathname !== '/news/') {
            return;
        }

        const sections = [
            { id: '#nm-global-news', el: document.querySelector('#nm-global-news') },
            { id: '#nm-travel-guides', el: document.querySelector('#nm-travel-guides') },
            { id: '#nm-must-read-list', el: document.querySelector('#nm-must-read-list') },
            { id: '#nm-gaming-section', el: document.querySelector('#nm-gaming-section') },
            { id: '#nm-fitness-section', el: document.querySelector('#nm-fitness-section') }
        ];

        let currentActiveId = null;
        const headerOffset = 220;

        for (let sec of sections) {
            if (sec.el) {
                const rect = sec.el.getBoundingClientRect();
                if (rect.top <= headerOffset && rect.bottom > 80) {
                    currentActiveId = sec.id;
                }
            }
        }

        if (scrollY < 180 || !currentActiveId) {
            currentActiveId = 'HOME';
        }

        const links = document.querySelectorAll('.av-news-nav .av-cat-menu a');
        links.forEach(l => {
            const href = l.getAttribute('href');
            l.classList.remove('active');
            l.style.color = '';
            l.style.borderBottom = '';
            l.style.background = '';

            if (currentActiveId === 'HOME' && (href === '/news' || href === '/news/')) {
                l.classList.add('active');
            } else if (href && href.includes(currentActiveId)) {
                l.classList.add('active');
            }
        });
    }

    window.addEventListener('scroll', updateDynamicNavScroll, { passive: true });
    const wrapEl = document.getElementById('wrapwrap');
    if (wrapEl) {
        wrapEl.addEventListener('scroll', updateDynamicNavScroll, { passive: true });
    }
    setTimeout(updateDynamicNavScroll, 300);

    // Smooth scrolling & active state for News navigation menu (.av-news-nav .av-cat-menu a, .nm-nav-links a) using Event Delegation
    document.addEventListener('click', function(e) {
        const link = e.target.closest('.av-news-nav .av-cat-menu a, .nm-nav-links a');
        if (!link) return;

        const href = link.getAttribute('href');
        if (!href) return;
        
        const hashIndex = href.indexOf('#');
        if (hashIndex !== -1) {
            const hash = href.substring(hashIndex);
            if (hash && hash !== '#') {
                const targetEl = document.querySelector(hash);
                if (targetEl) {
                    e.preventDefault();
                    document.querySelectorAll('.av-news-nav .av-cat-menu a, .nm-nav-links a').forEach(l => l.classList.remove('active'));
                    link.classList.add('active');

                    // Ensure the URL remains /news without adding #hash to the address bar
                    if (history.replaceState) {
                        history.replaceState(null, null, '/news');
                    }

                    // 1. Scroll using scrollIntoView which respects CSS scroll-margin-top: 170px on any scrolling container
                    targetEl.scrollIntoView({ behavior: "smooth", block: "start" });

                    // 2. Also scroll #wrapwrap (Odoo's primary scrolling container) explicitly
                    const headerOffset = 160;
                    const wrapwrap = document.getElementById('wrapwrap');
                    if (wrapwrap) {
                        const wrapRect = wrapwrap.getBoundingClientRect();
                        const targetRect = targetEl.getBoundingClientRect();
                        const offset = targetRect.top - wrapRect.top + wrapwrap.scrollTop - headerOffset;
                        wrapwrap.scrollTo({
                            top: Math.max(0, offset),
                            behavior: "smooth"
                        });
                    }
                    window.scrollTo({
                        top: Math.max(0, (targetEl.getBoundingClientRect().top + (window.scrollY || window.pageYOffset || 0) - headerOffset)),
                        behavior: "smooth"
                    });

                    targetEl.style.transition = 'box-shadow 0.5s ease';
                    targetEl.style.boxShadow = '0 0 20px rgba(0, 141, 127, 0.4)';
                    setTimeout(() => {
                        targetEl.style.boxShadow = 'none';
                    }, 1500);
                    return;
                }
            }
        } else if ((href === '/news' || href === '/news/' || href === '#' || href === '') && (window.location.pathname === '/news' || window.location.pathname === '/news/')) {
            e.preventDefault();
            document.querySelectorAll('.av-news-nav .av-cat-menu a, .nm-nav-links a').forEach(l => l.classList.remove('active'));
            link.classList.add('active');
            if (history.replaceState) {
                history.replaceState(null, null, '/news');
            }
            // 1. Scroll the very top element (.av-topbar or #wrapwrap or body) into view
            const topEl = document.querySelector('.av-topbar') || document.querySelector('#wrapwrap') || document.body;
            if (topEl) {
                topEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            // 2. Also explicitly scroll all potential containers to 0
            const wrapwrap = document.getElementById('wrapwrap');
            if (wrapwrap) {
                wrapwrap.scrollTo({ top: 0, behavior: "smooth" });
            }
            const main = document.querySelector('main');
            if (main) {
                main.scrollTo({ top: 0, behavior: "smooth" });
            }
            window.scrollTo({
                top: 0,
                behavior: "smooth"
            });
            document.documentElement.scrollTo({
                top: 0,
                behavior: "smooth"
            });
            document.body.scrollTo({
                top: 0,
                behavior: "smooth"
            });
        }
    });

    // Handle hash on initial page load
    if (window.location.hash && window.location.hash !== '#') {
        setTimeout(() => {
            const targetEl = document.querySelector(window.location.hash);
            if (targetEl) {
                const headerOffset = 160;
                const elementPosition = targetEl.getBoundingClientRect().top;
                const offsetPosition = elementPosition + (window.scrollY || window.pageYOffset || document.documentElement.scrollTop) - headerOffset;
                window.scrollTo({
                    top: Math.max(0, offsetPosition),
                    behavior: "smooth"
                });
                targetEl.style.transition = 'box-shadow 0.5s ease';
                targetEl.style.boxShadow = '0 0 20px rgba(0, 141, 127, 0.4)';
                setTimeout(() => {
                    targetEl.style.boxShadow = 'none';
                }, 1500);
                document.querySelectorAll('.av-news-nav .av-cat-menu a, .nm-nav-links a').forEach(link => {
                    const href = link.getAttribute('href') || '';
                    if (href.endsWith(window.location.hash)) {
                        document.querySelectorAll('.av-news-nav .av-cat-menu a, .nm-nav-links a').forEach(l => l.classList.remove('active'));
                        link.classList.add('active');
                    }
                });
            }
        }, 300);
    }

    // Intercept clicks on article links to open them dynamically with a slug
    document.addEventListener('click', function(e) {
        const a = e.target.closest('a');
        if (a && a.href && a.href.includes('http') && !a.href.includes(window.location.host) && window.nmValidArticles) {
            const hrefAttr = a.getAttribute('href');
            const article = window.nmValidArticles.find(art => art.url === hrefAttr || art.url === a.href);
            if (article) {
                e.preventDefault();
                // Create a slug from the title (alphanumeric and dashes only)
                let slug = article.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)+/g, '');
                if(!slug) slug = 'article';
                
                // Save to localStorage using the slug as the key!
                localStorage.setItem('nm_article_' + slug, JSON.stringify(article));
                window.location.href = '/news/article/' + slug;
            }
        }
    });

    fetchNews();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNewsPage);
} else {
    initNewsPage();
}

async function fetchNews() {
    try {
        let allArticles = [];
        let nextPage = '';
        
        // Fetch directly from our local Odoo API (much faster, no rate limits!)
        const urlParams = new URLSearchParams(window.location.search);
        const category = urlParams.get('category');
        let url = `/api/v1/news?limit=100`;
        if (category) {
            url += `&category=${category}`;
        }
        const res = await fetch(url);
        
        if (res.ok) {
            const data = await res.json();
            if (data.status === 'success' && data.data) {
                const mapped = data.data.map(r => ({
                    title: r.title,
                    url: r.link,
                    urlToImage: r.image_url,
                    publishedAt: r.date,
                    author: 'Staff Reporter',
                    source: { name: r.source || 'News' },
                    description: r.description,
                    content: r.description
                }));
                allArticles = mapped.filter(a => a.urlToImage && !a.urlToImage.includes('stimg.co') && a.title);
            }
        }
        
        const uniqueTitles = new Set();
        let validArticles = allArticles.filter(a => {
            if (uniqueTitles.has(a.title)) return false;
            uniqueTitles.add(a.title);
            return true;
        });

        if (validArticles.length < 55) {
            const defaults = getDefaultNewsArticles();
            defaults.forEach(def => {
                if (!uniqueTitles.has(def.title)) {
                    uniqueTitles.add(def.title);
                    validArticles.push(def);
                }
            });
        }

        window.nmValidArticles = validArticles;
        // Render as many sections as we have articles for.
        // Safe length checks so we don't crash if length is less than expected
        renderHero(validArticles.slice(0, 5));
        renderGlobalNews(validArticles.slice(5, 10));
        renderTravelGuides(validArticles.slice(10, 13));
        
        renderTwoCol(validArticles.slice(13, 17), 'nm-gadgets-section');
        renderTwoCol(validArticles.slice(17, 21), 'nm-recipes-section');
        renderFourCol(validArticles.slice(21, 25));
        
        renderFitnessList(validArticles.slice(25, 30), 'nm-fitness-section');
        renderGamingMain(validArticles.slice(30, 31), 'nm-gaming-section');
        
        renderLatestArticles(validArticles.slice(31, 37));
        
        renderPopularList(validArticles.slice(37, 47), 'nm-popular-list');
        
        renderMustReadList(validArticles.slice(47, 52), 'nm-must-read-list');
        
        renderYoutubePlaylist('nm-youtube-section');
        
    } catch (error) {
        console.error('Error fetching news:', error);
        // Remove spinners if there's a fatal error
        document.querySelectorAll('.fa-spinner').forEach(el => {
            el.parentElement.innerHTML = '<div style="color:red; text-align:center;">Failed to load dynamic news.</div>';
        });
    }
}

function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
}

function renderHero(articles) {
    const heroMain = document.querySelector('.nm-hero-main');
    
    if (!articles || articles.length === 0) {
        const heroItems = document.querySelectorAll('.nm-hero-grid .nm-hero-item');
        for (let i = 0; i < heroItems.length; i++) {
            heroItems[i].style.display = 'none'; // hide empty placeholders
        }
        return;
    }
    if (heroMain && articles[0]) {
        heroMain.style.backgroundImage = `url('${articles[0].urlToImage}')`;
        heroMain.querySelector('.nm-article-title').innerHTML = `<a href="${articles[0].url}" style="color:white;" target="_blank">${articles[0].title}</a>`;
        heroMain.querySelector('.nm-author').textContent = articles[0].author || 'Editor';
        heroMain.querySelector('.nm-date').textContent = formatDate(articles[0].publishedAt);
        heroMain.querySelector('.nm-category-badge').textContent = (articles[0].source.name || 'NEWS').substring(0, 15);
    }
    
    const heroItems = document.querySelectorAll('.nm-hero-grid .nm-hero-item');
    for (let i = 0; i < heroItems.length; i++) {
        if (articles[i + 1]) {
            heroItems[i].style.backgroundImage = `url('${articles[i + 1].urlToImage}')`;
            heroItems[i].querySelector('.nm-article-title-small').innerHTML = `<a href="${articles[i + 1].url}" style="color:white;" target="_blank">${articles[i + 1].title}</a>`;
            heroItems[i].querySelector('.nm-category-badge').textContent = (articles[i + 1].source.name || 'TRENDING').substring(0, 15);
        } else {
            heroItems[i].style.display = 'none'; // hide empty placeholders
        }
    }
}

function renderGlobalNews(articles) {
    const container = document.getElementById('nm-global-news');
    if (!container) return;
    if (!articles || articles.length === 0) {
        container.innerHTML = '<p style="padding: 20px;">No global news available at the moment.</p>';
        return;
    }

    let mainHtml = `
        <div class="nm-gn-main">
            <img src="${articles[0].urlToImage}" onerror="this.style.display='none';" alt="">
            <span class="nm-category-text">${articles[0].source.name || 'GLOBAL'}</span>
            <h3 class="nm-post-title"><a href="${articles[0].url}" target="_blank">${articles[0].title}</a></h3>
            <div class="nm-article-meta nm-dark-meta"><span class="nm-author">${articles[0].author || 'Editor'}</span> - <span class="nm-date">${formatDate(articles[0].publishedAt)}</span></div>
            <p class="nm-post-excerpt">${(articles[0].description || '').substring(0, 100)}...</p>
        </div>
    `;

    let listHtml = '<div class="nm-gn-list">';
    for (let i = 1; i < Math.min(articles.length, 5); i++) {
        if (articles[i]) {
            listHtml += `
                <div class="nm-gn-list-item">
                    <img src="${articles[i].urlToImage}" alt="">
                    <div class="nm-gn-list-content">
                        <h3 class="nm-post-title"><a href="${articles[i].url}" target="_blank">${articles[i].title}</a></h3>
                        <div class="nm-article-meta nm-dark-meta"><span class="nm-date">${formatDate(articles[i].publishedAt)}</span></div>
                    </div>
                </div>
            `;
        }
    }
    listHtml += '</div>';
    
    container.innerHTML = mainHtml + listHtml;
}

function renderTravelGuides(articles) {
    const container = document.getElementById('nm-travel-guides');
    if(!container) return;
    if(!articles || articles.length === 0) {
        container.innerHTML = '<p style="padding: 20px;">No travel guides available at the moment.</p>';
        return;
    }
    
    container.innerHTML = articles.slice(0, 3).map(article => `
        <div class="nm-tg-item">
            <div class="nm-tg-img-wrap" style="background-image: url('${article.urlToImage}');"></div>
            <div class="nm-tg-info">
                <span class="nm-category-text">${(article.source.name || 'TRAVEL').substring(0, 15)}</span>
                <h3 class="nm-post-title"><a href="${article.url}" target="_blank">${article.title}</a></h3>
            </div>
        </div>
    `).join('');
}

function renderTwoCol(articles, containerId) {
    const container = document.getElementById(containerId);
    if(!container) return;
    if(!articles || articles.length === 0) { container.innerHTML = '<p style="padding: 20px;">No articles available.</p>'; return; }

    let html = `
        <div class="nm-gn-main">
            <img src="${articles[0].urlToImage}" onerror="this.style.display='none';" alt="">
            <h3 class="nm-post-title"><a href="${articles[0].url}" target="_blank">${articles[0].title}</a></h3>
            <div class="nm-article-meta nm-dark-meta"><span class="nm-author">${articles[0].author || 'Editor'}</span> - <span class="nm-date">${formatDate(articles[0].publishedAt)}</span></div>
        </div>
        <div class="nm-gn-list" style="margin-top:20px;">
    `;
    
    for (let i = 1; i < Math.min(articles.length, 4); i++) {
        html += `
            <div class="nm-gn-list-item">
                <img src="${articles[i].urlToImage}" alt="">
                <div class="nm-gn-list-content">
                    <h3 class="nm-post-title"><a href="${articles[i].url}" target="_blank">${articles[i].title}</a></h3>
                    <div class="nm-article-meta nm-dark-meta"><span class="nm-date">${formatDate(articles[i].publishedAt)}</span></div>
                </div>
            </div>
        `;
    }
    html += '</div>';
    
    // Append to keep the title
    container.innerHTML += html;
}

function renderFourCol(articles) {
    const container = document.getElementById('nm-four-col-grid');
    if(!container) return;
    if(!articles || articles.length === 0) { container.innerHTML = '<p style="padding: 20px;">No articles available.</p>'; return; }
    
    container.innerHTML = articles.map(article => `
        <article class="nm-fc-card" style="background-image: url('${article.urlToImage}')">
            <div class="nm-overlay"></div>
            <div class="nm-article-content" style="padding: 15px;">
                <span class="nm-category-badge" style="background-color: #222;">${(article.source.name || 'TREND').substring(0, 15)}</span>
                <h3 class="nm-article-title-small" style="font-size: 13px;"><a href="${article.url}" style="color:white;" target="_blank">${article.title}</a></h3>
            </div>
        </article>
    `).join('');
}

function renderFitnessList(articles, containerId) {
    const container = document.getElementById(containerId);
    if(!container) return;
    if(!articles || articles.length === 0) { container.innerHTML = '<p style="padding: 20px;">No articles available.</p>'; return; }
    
    const html = articles.map(article => `
        <article class="nm-list-post" style="margin-bottom:20px; display: flex; gap: 20px; align-items: flex-start;">
            <a href="${article.url}" target="_blank" style="flex-shrink: 0;">
                <img src="${article.urlToImage}" onerror="this.style.display='none';" class="nm-post-img" style="width: 218px; height: 150px; object-fit: cover;" alt="">
            </a>
            <div class="nm-post-info" style="flex-grow: 1;">
                <div class="nm-article-meta nm-dark-meta" style="margin-bottom:5px;">
                    <a href="#" class="nm-category-text" style="color: #478fe0; margin-right:5px;">${(article.source.name || 'FITNESS').substring(0, 15)}</a>
                </div>
                <h3 class="nm-post-title" style="font-size:20px; font-weight:500; margin-bottom:10px; line-height:1.2;">
                    <a href="${article.url}" class="nm-fitness-link" target="_blank">${article.title}</a>
                </h3>
                <div class="nm-article-meta nm-dark-meta" style="margin-bottom:8px; font-size:11px;">
                    <span class="nm-author">${article.author || 'David Lee'}</span> - <span class="nm-date">${formatDate(article.publishedAt)}</span>
                </div>
                <p class="nm-post-excerpt" style="font-size:13px; line-height:1.6; margin:0;">${(article.description || '').substring(0, 120)}...</p>
            </div>
        </article>
    `).join('');
    
    container.innerHTML += html;
}

function renderGamingMain(articles, containerId) {
    const container = document.getElementById(containerId);
    if(!container) return;
    if(!articles || articles.length === 0) { container.innerHTML = '<p style="padding: 20px;">No articles available.</p>'; return; }
    
    const html = `
        <div class="nm-gn-main">
            <img src="${articles[0].urlToImage}" onerror="this.style.display='none';" alt="" style="width: 100%; height: auto; display: block; margin-bottom: 10px;">
            <div class="nm-article-meta nm-dark-meta" style="margin-bottom: 5px; font-size: 11px;">
                <span class="nm-category-text" style="color: #e86aa1; margin-right:10px;">${(articles[0].source.name || 'GAMING').substring(0, 15)}</span>
            </div>
            <h3 class="nm-post-title" style="font-size: 20px; margin-bottom: 10px; font-weight: 500; line-height: 1.2;">
                <a href="${articles[0].url}" class="nm-gaming-link" target="_blank">${articles[0].title}</a>
            </h3>
        </div>
    `;
    
    container.innerHTML += html;
}

function renderLatestArticles(articles) {
    const container = document.getElementById('nm-latest-articles');
    if(!container) return;
    if(!articles || articles.length === 0) { container.innerHTML = '<p style="padding: 20px;">No latest articles available.</p>'; return; }
    
    let html = '<div class="nm-latest-grid">';
    html += articles.map(article => `
        <article class="nm-latest-grid-item">
            <a href="${article.url}" target="_blank">
                <img src="${article.urlToImage}" onerror="this.style.display='none';" alt="">
            </a>
            <div class="nm-post-info">
                <a href="#" class="nm-category-text">${(article.source.name || 'LATEST').substring(0, 15)}</a>
                <h3 class="nm-post-title"><a href="${article.url}" target="_blank">${article.title}</a></h3>
                <div class="nm-article-meta nm-dark-meta" style="font-size: 11px;">
                    <span class="nm-author">${article.author || 'David Lee'}</span> - <span class="nm-date">${formatDate(article.publishedAt)}</span>
                </div>
            </div>
        </article>
    `).join('');
    html += '</div>';
    
    container.innerHTML = html;
}

function renderPopularList(articles, containerId) {
    const container = document.getElementById(containerId);
    if(!container) return;
    if(!articles || articles.length === 0) { container.innerHTML = '<p style="padding: 20px;">No articles available.</p>'; return; }
    
    container.innerHTML = articles.map(article => `
        <div class="nm-circle-post">
            <img src="${article.urlToImage}" onerror="this.style.display='none';" alt="Popular"/>
            <div class="nm-circle-post-info">
                <span class="nm-category-text">${(article.source.name || 'POPULAR').substring(0, 15)}</span>
                <h4 class="nm-small-title"><a href="${article.url}" target="_blank">${article.title}</a></h4>
            </div>
        </div>
    `).join('');
}

function renderMustReadList(articles, containerId) {
    const container = document.getElementById(containerId);
    if(!container) return;
    if(!articles || articles.length === 0) { container.innerHTML = '<p style="padding: 20px;">No articles available.</p>'; return; }
    
    container.innerHTML = articles.map(article => `
        <div class="nm-must-read-post">
            <img src="${article.urlToImage}" onerror="this.style.display='none';" alt="">
            <div class="nm-post-info">
                <a href="#" class="nm-category-text">${(article.source.name || 'READ').substring(0, 15)}</a>
                <h4 class="nm-post-title"><a href="${article.url}" target="_blank">${article.title}</a></h4>
                <div class="nm-article-meta nm-dark-meta" style="font-size: 11px;">
                    <span class="nm-date">${formatDate(article.publishedAt)}</span>
                </div>
            </div>
        </div>
    `).join('');
}

function renderYoutubePlaylist(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const videos = [
        { id: 'fwOy8rVN_9Y', title: 'Ibiza Summer Mix 2026 🍓 Best Of Tropical Deep House Music Chill Out Mix By Deep Legacy #314', time: '02:45:17' },
        { id: 'Bb3fNYdkctM', title: 'Chill Deep House Music 2026 🌱 The Best Of Vocal Deep House Music Mix 2026 🌱 Chill Mix #313', time: '02:35:47' },
        { id: 'WlOFEU97ErQ', title: 'Summer Music Mix 2026 🌱 The Best Of Vocal Deep House Music Mix 2026 🌱 Mega Hits 2026 #312', time: '02:38:47' },
        { id: 'v8SkkEGoh9Q', title: 'Summer Hits 2026 🌱 The Best Of Vocal Deep House Music Mix 2026 🌱 Chillout Lounge #311', time: '02:34:26' },
        { id: 'fDuwNQiDj7s', title: 'Mega Hits 2026 🌱 The Best Of Vocal Deep House Music Mix 2026 🌱 Summer Music Mix 2026 #310', time: '02:33:36' }
    ];

    let currentVideo = videos[0];

    const render = () => {
        container.innerHTML = `
            <div class="nm-yt-container">
                <div class="nm-yt-main">
                    <iframe src="https://www.youtube.com/embed/${currentVideo.id}?autoplay=1" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
                </div>
                <div class="nm-yt-sidebar">
                    <div class="nm-yt-controls">
                        <span style="font-weight:bold; margin-right: 15px;">PLAYING:</span>
                        <span style="opacity: 0.8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">${currentVideo.title}</span>
                    </div>
                    <ul class="nm-yt-list">
                        ${videos.map((vid) => `
                            <li class="nm-yt-item ${vid.id === currentVideo.id ? 'active' : ''}" data-id="${vid.id}">
                                <img src="https://img.youtube.com/vi/${vid.id}/default.jpg" alt="thumbnail">
                                <div>
                                    <div class="nm-yt-item-title">${vid.title}</div>
                                    <div class="nm-yt-item-time">${vid.time}</div>
                                </div>
                            </li>
                        `).join('')}
                    </ul>
                </div>
            </div>
        `;

        // Add event listeners after render
        const items = container.querySelectorAll('.nm-yt-item');
        items.forEach(item => {
            item.addEventListener('click', (e) => {
                const id = e.currentTarget.getAttribute('data-id');
                const selected = videos.find(v => v.id === id);
                if (selected) {
                    currentVideo = selected;
                    render();
                }
            });
        });
    };

    render();
}

function getDefaultNewsArticles() {
    const categories = ['GLOBAL', 'LIFESTYLE', 'FASHION', 'GAMING', 'FITNESS', 'GADGETS', 'RECIPES', 'POPULAR'];
    const authors = ['Sarah Jenkins', 'Michael Chang', 'David Lee', 'Elena Rostova', 'Marcus Vance', 'Amina Diop', 'Lucas Wright', 'Jessica Alba'];
    const images = [
        'https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1519681393784-d120267933ba?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1470071459604-3b5ec3a7fe05?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1511512578047-dfb367046420?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1517838277536-f5f99be501cd?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1526772662000-3f88f10405ff?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1483985988355-763728e1935b?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1492707892479-7bc8d5a4ee93?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1550745165-9bc0b252726f?w=800&auto=format&fit=crop',
        'https://images.unsplash.com/photo-1542751371-adc38448a05e?w=800&auto=format&fit=crop'
    ];
    const titles = [
        "Global Tech Leaders Assemble in Geneva for AI Summit 2026",
        "Renewable Energy Milestones Shattered Across Europe This Season",
        "Oceanic Conservation Project Reports Breakthrough in Reef Recovery",
        "New High-Speed Rail Network Connects Major Scandinavian Hubs",
        "Global Architecture Biennale Spotlights Eco-Friendly Skyscrapers",
        "7 Minimalist Daily Habits for Serious Mental Clarity and Calm",
        "Why Coastal Slow-Living is the Biggest Trend in Modern Home Design",
        "The Ultimate Weekend Itinerary for Exploring Kyoto in Autumn",
        "How Digital Nomads Are Redefining Work-Life Balance Globally",
        "Autumn 2026 Couture: Elegant Silhouettes and Earthy Muted Tones",
        "Sustainable Luxury: Why Heritage Brands Are Embracing Upcycling",
        "The Return of Tailored Linens in Contemporary Urban Menswear",
        "Next-Gen Virtual Reality Headset Redefines Immersion in RPGs",
        "Indie Game Studio Wins Game of the Year with Emotional Narrative",
        "Esports World Cup Sets New Viewership Record in Tokyo Finals",
        "High-Intensity Interval Training vs. Low-Impact Pilates: New Study",
        "The Role of Micro-Nutrients in Accelerating Post-Workout Recovery",
        "Smart Wearables in 2026: Tracking Sleep Stages More Than Workouts",
        "Hands-On with the Ultralight Solar-Powered Notebook for Travelers",
        "Artisanal Sourdough: 5 Secret Techniques from Parisian Bakers",
        "Exploring Hidden Glaciers: A Guide to Responsible Arctic Tourism",
        "The Evolution of Smart Kitchen Appliances in Modern Homes",
        "Top 10 Hidden Gem Destinations in the Mediterranean for 2026",
        "How AI is Revolutionizing Personalized Nutrition and Health Plans",
        "Vintage Fashion Revival: Collecting Timeless Wardrobe Pieces",
        "Competitive Gaming Leagues Introduce Sustainable Tournament Venues",
        "Mindfulness Meditation: Science-Backed Benefits for Daily Productivity",
        "The Future of Electric Aviation: Short-Haul Flights Transformed",
        "Mastering French Cuisine at Home: Simplified Classic Gourmet Recipes",
        "Urban Rooftop Gardens: Transforming City Skylines with Greenery",
        "Innovative Eco-Materials Dominating International Design Fairs",
        "The Rise of Boutique Fitness Studios in Major Cosmopolitan Cities",
        "Understanding Quantum Computing: What It Means for Consumer Tech",
        "Weekend Getaways: Charming Countryside Retreats Near You",
        "Essential Wardrobe Staples for Sustainable Seasonal Transitions",
        "Deep-Sea Exploration: New Discoveries in Marine Biology",
        "How Contemporary Artists Are Blending Traditional Crafts with Tech",
        "The Science of Better Sleep: Ambient Temperature and Lighting",
        "Zero-Waste Culinary Trends Revolutionizing Fine Dining",
        "Next-Generation Smartphones: Foldables Reaching New Maturity",
        "Historic Landmarks Restored Using Advanced 3D Laser Scanning",
        "The Best Scenic Hiking Trails to Experience This Spring",
        "The Psychology of Color in Interior Design for Serenity",
        "Breakthroughs in Battery Tech Enable Days-Long Laptop Battery Life",
        "Superfoods Explained: Separating Marketing Hype from Nutritional Fact",
        "The Aesthetic Revival of Mid-Century Modern Furniture",
        "Virtual Museums: Interactive Art Exhibitions Available Worldwide",
        "Cross-Training Strategies for Injury-Free Marathon Preparation",
        "Global Coffee Culture: From Farm to Specialty Artisan Roasts",
        "Exploring Space Tourism: What the First Commercial Travelers Can Expect",
        "How Smart Cities Are Redesigning Public Transit for Accessibility",
        "The Renaissance of Vinyl Records in an Era of Digital Streaming",
        "Architecture of Tomorrow: Floating Structures for Coastal Regions",
        "Plant-Based Gastronomy Wins Acclaim at Michelin Star Awards",
        "Minimalist Travel Packing: How to Travel for Weeks with One Carry-On",
        "The Best Ergonomic Workspace Setups for Long-Term Spinal Health",
        "Behind the Scenes of Motion Capture in AAA Video Game Production",
        "Natural Skincare Ingredients Proven by Dermatological Science",
        "How Solar Desalination Could Solve Clean Water Shortages",
        "The Cultural Impact of Contemporary African Art on Global Galleries"
    ];

    return titles.map((title, index) => {
        const cat = categories[index % categories.length];
        const img = images[index % images.length];
        const author = authors[index % authors.length];
        const day = 28 - (index % 25);
        return {
            title: title,
            url: 'https://aveenix.com/news/article/' + (index + 1),
            urlToImage: img,
            publishedAt: `2026-07-${day < 10 ? '0' + day : day}T10:00:00Z`,
            author: author,
            source: { name: cat },
            description: `${title}. Comprehensive analysis, expert insights, and indepth coverage of the latest developments shaping ${cat.toLowerCase()} around the world today.`
        };
    });
}
