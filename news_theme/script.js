document.addEventListener('DOMContentLoaded', () => {
    const themeToggle = document.getElementById('theme-toggle');
    const body = document.body;
    
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        body.classList.add('dark-theme');
        themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
    } else {
        themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
    }

    themeToggle.addEventListener('click', () => {
        body.classList.toggle('dark-theme');
        if (body.classList.contains('dark-theme')) {
            localStorage.setItem('theme', 'dark');
            themeToggle.innerHTML = '<i class="fas fa-sun"></i>';
        } else {
            localStorage.setItem('theme', 'light');
            themeToggle.innerHTML = '<i class="fas fa-moon"></i>';
        }
    });

    fetchNews();
});

async function fetchNews() {
    try {
        const response = await fetch('https://saurav.tech/NewsAPI/top-headlines/category/general/us.json');
        const data = await response.json();
        
        if (data.status === 'ok' && data.articles) {
            const validArticles = data.articles.filter(a => a.urlToImage && a.title);
            
            // Avoid errors if API returns less items than expected
            if (validArticles.length < 10) return; 
            
            renderHero(validArticles.slice(0, 5));
            renderGlobalNews(validArticles.slice(5, 10));
            
            if(validArticles.length > 13) renderTravelGuides(validArticles.slice(10, 13));
            if(validArticles.length > 17) renderTwoCol(validArticles.slice(13, 17), 'gadgets-section');
            if(validArticles.length > 21) renderTwoCol(validArticles.slice(17, 21), 'recipes-section');
            if(validArticles.length > 25) renderFourCol(validArticles.slice(21, 25));
            if(validArticles.length > 29) renderTwoCol(validArticles.slice(25, 29), 'fitness-section');
            if(validArticles.length > 33) renderTwoCol(validArticles.slice(29, 33), 'gaming-section');
            if(validArticles.length > 34) renderLatestArticles(validArticles.slice(33, 40));
            
            // Sidebar widgets
            renderPopularList(validArticles.slice(0, 5), 'popular-list');
            renderMustReadList(validArticles.slice(5, 9), 'must-read-list');
        }
    } catch (error) {
        console.error('Error fetching news:', error);
    }
}

function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
}

function renderHero(articles) {
    if (articles.length < 5) return;
    
    const heroMain = document.querySelector('.hero-main');
    if (heroMain) {
        heroMain.style.backgroundImage = `url('${articles[0].urlToImage}')`;
        heroMain.querySelector('.article-title').textContent = articles[0].title;
        heroMain.querySelector('.author').textContent = articles[0].author || 'Editor';
        heroMain.querySelector('.date').textContent = formatDate(articles[0].publishedAt);
        heroMain.querySelector('.category-badge').textContent = (articles[0].source.name || 'NEWS').substring(0, 15);
    }
    
    const heroItems = document.querySelectorAll('.hero-grid .hero-item');
    for (let i = 0; i < heroItems.length; i++) {
        if (articles[i + 1]) {
            heroItems[i].style.backgroundImage = `url('${articles[i + 1].urlToImage}')`;
            heroItems[i].querySelector('.article-title-small').textContent = articles[i + 1].title;
            heroItems[i].querySelector('.category-badge').textContent = (articles[i + 1].source.name || 'TRENDING').substring(0, 15);
        }
    }
}

function renderGlobalNews(articles) {
    if (articles.length < 5) return;
    const container = document.getElementById('global-news');
    if (!container) return;

    let mainHtml = `
        <div class="gn-main">
            <img src="${articles[0].urlToImage}" alt="">
            <span class="category-text">${articles[0].source.name || 'GLOBAL'}</span>
            <h3 class="post-title"><a href="${articles[0].url}" target="_blank">${articles[0].title}</a></h3>
            <div class="article-meta dark-meta"><span class="author">${articles[0].author || 'Editor'}</span> - <span class="date">${formatDate(articles[0].publishedAt)}</span></div>
            <p class="post-excerpt">${(articles[0].description || '').substring(0, 100)}...</p>
        </div>
    `;

    let listHtml = '<div class="gn-list">';
    for (let i = 1; i < 5; i++) {
        listHtml += `
            <div class="gn-list-item">
                <img src="${articles[i].urlToImage}" alt="">
                <div class="gn-list-content">
                    <h3 class="post-title"><a href="${articles[i].url}" target="_blank">${articles[i].title}</a></h3>
                    <div class="article-meta dark-meta"><span class="date">${formatDate(articles[i].publishedAt)}</span></div>
                </div>
            </div>
        `;
    }
    listHtml += '</div>';
    
    container.innerHTML = mainHtml + listHtml;
}

function renderTravelGuides(articles) {
    if(articles.length < 3) return;
    const container = document.getElementById('travel-guides');
    if(!container) return;
    
    container.innerHTML = articles.map(article => `
        <article class="tg-card" style="background-image: url('${article.urlToImage}')">
            <div class="overlay"></div>
            <div class="article-content">
                <span class="category-badge" style="background-color: var(--primary);">${(article.source.name || 'GUIDE').substring(0, 15)}</span>
                <h3 class="article-title-small">${article.title}</h3>
            </div>
        </article>
    `).join('');
}

function renderTwoCol(articles, containerId) {
    if(articles.length < 4) return;
    const container = document.getElementById(containerId);
    if(!container) return;

    let html = `
        <div class="gn-main">
            <img src="${articles[0].urlToImage}" alt="">
            <h3 class="post-title"><a href="${articles[0].url}" target="_blank">${articles[0].title}</a></h3>
            <div class="article-meta dark-meta"><span class="author">${articles[0].author || 'Editor'}</span> - <span class="date">${formatDate(articles[0].publishedAt)}</span></div>
        </div>
        <div class="gn-list">
    `;
    
    for (let i = 1; i < 4; i++) {
        html += `
            <div class="gn-list-item">
                <img src="${articles[i].urlToImage}" alt="">
                <div class="gn-list-content">
                    <h3 class="post-title"><a href="${articles[i].url}" target="_blank">${articles[i].title}</a></h3>
                    <div class="article-meta dark-meta"><span class="date">${formatDate(articles[i].publishedAt)}</span></div>
                </div>
            </div>
        `;
    }
    html += '</div>';
    
    container.innerHTML += html;
}

function renderFourCol(articles) {
    if(articles.length < 4) return;
    const container = document.getElementById('four-col-grid');
    if(!container) return;
    
    container.innerHTML = articles.map(article => `
        <article class="fc-card" style="background-image: url('${article.urlToImage}')">
            <div class="overlay"></div>
            <div class="article-content" style="padding: 15px;">
                <span class="category-badge" style="background-color: #222;">${(article.source.name || 'TREND').substring(0, 15)}</span>
                <h3 class="article-title-small" style="font-size: 13px;">${article.title}</h3>
            </div>
        </article>
    `).join('');
}

function renderLatestArticles(articles) {
    if(!articles.length) return;
    const container = document.getElementById('latest-articles');
    if(!container) return;
    
    container.innerHTML = articles.map(article => `
        <article class="list-post">
            <img src="${article.urlToImage}" class="post-img" alt="">
            <div class="post-info">
                <span class="category-text">${article.source.name || 'LATEST'}</span>
                <h3 class="post-title"><a href="${article.url}" target="_blank">${article.title}</a></h3>
                <div class="article-meta dark-meta">
                    <span class="author">${article.author || 'Editor'}</span> - <span class="date">${formatDate(article.publishedAt)}</span>
                </div>
                <p class="post-excerpt">${(article.description || '').substring(0, 150)}...</p>
            </div>
        </article>
    `).join('');
}

function renderPopularList(articles, containerId) {
    const container = document.getElementById(containerId);
    if(!container) return;
    
    container.innerHTML = articles.map(article => `
        <div class="popular-list-item">
            <img src="${article.urlToImage}" alt="">
            <div class="popular-list-content">
                <span class="category-text" style="font-size: 9px; margin-bottom: 2px;">${(article.source.name || 'POPULAR').substring(0, 15)}</span>
                <h3 class="post-title"><a href="${article.url}" target="_blank">${article.title}</a></h3>
            </div>
        </div>
    `).join('');
}

function renderMustReadList(articles, containerId) {
    const container = document.getElementById(containerId);
    if(!container) return;
    
    container.innerHTML = articles.map(article => `
        <div class="must-read-item">
            <img src="${article.urlToImage}" alt="">
            <div class="must-read-content">
                <span class="category-text" style="font-size: 9px; margin-bottom: 2px;">${(article.source.name || 'READ').substring(0, 15)}</span>
                <h3 class="post-title"><a href="${article.url}" target="_blank">${article.title}</a></h3>
                <div class="article-meta dark-meta"><span class="date" style="font-size: 10px;">${formatDate(article.publishedAt)}</span></div>
            </div>
        </div>
    `).join('');
}
