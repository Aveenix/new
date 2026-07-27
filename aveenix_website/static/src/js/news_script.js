document.addEventListener('DOMContentLoaded', () => {
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

    // Handle nav link active state for the top red border
    const navLinks = document.querySelectorAll('.nm-nav-links a');
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            if (this.getAttribute('href') === '#') {
                e.preventDefault();
            }
            navLinks.forEach(l => l.classList.remove('active'));
            this.classList.add('active');
        });
    });

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
});

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

        // Duplication code removed, we now fetch enough articles from the backend

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
