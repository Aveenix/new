/**
 * Trending headline ticker — the "TRENDING NOW" bar at the top of /news and
 * the article pages.
 *
 * The headlines used to swap in place: one title, faded out and replaced every
 * four seconds. This runs them past instead, as one continuous line on a rail.
 *
 * How the loop works: the track holds the headline list twice. Once it has
 * travelled the width of the first copy, x resets by exactly that width, and
 * because the second copy is identical the reset is invisible — so it reads as
 * one endless line rather than a list that restarts.
 *
 * Motion is driven from rAF rather than a CSS animation because the prev/next
 * buttons have to be able to jump the rail, which a running keyframe animation
 * will not let you do. To keep that honest about battery, the loop is only
 * scheduled while the bar is actually on screen and the tab is visible, and it
 * stops entirely for readers who ask for reduced motion.
 */
(function () {
    'use strict';

    var SPEED = 45;          // px per second — a readable walking pace
    var GAP_CLASS = 'nm-ticker-item';
    var MAX_DT = 0.05;       // clamp: a backgrounded tab must not jump the rail

    function esc(str) {
        return String(str == null ? '' : str).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function Ticker(root) {
        this.root = root;
        this.track = root.querySelector('.nm-ticker-track');
        this.x = 0;
        this.setWidth = 0;
        this.items = [];
        this.running = false;
        this.paused = false;
        this.visible = true;
        this.last = 0;
        this.frame = null;
        this.reduced = window.matchMedia
            && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    Ticker.prototype.render = function (items) {
        if (!this.track || !items || !items.length) {
            return;
        }
        this.items = items;

        // Two identical copies back to back: the second is what the eye is
        // looking at while the first is being reset behind it.
        var html = '';
        for (var copy = 0; copy < 2; copy++) {
            for (var i = 0; i < items.length; i++) {
                var item = items[i];
                var url = item.url || '/news';
                html += '<a class="' + GAP_CLASS + '" href="' + esc(url) + '"'
                     + (copy === 1 ? ' aria-hidden="true" tabindex="-1"' : '')
                     + '><span class="nm-ticker-dot"></span>'
                     + esc(item.title) + '</a>';
            }
        }
        this.track.innerHTML = html;
        this.root.classList.add('nm-ticker--ready');
        this.measure();
        this.observe();
        this.start();
    };

    Ticker.prototype.measure = function () {
        // Width of ONE copy: that is the distance after which the rail repeats.
        var nodes = this.track.querySelectorAll('.' + GAP_CLASS);
        var half = nodes.length / 2;
        var width = 0;
        for (var i = 0; i < half; i++) {
            width += nodes[i].getBoundingClientRect().width;
        }
        this.setWidth = width;
    };

    Ticker.prototype.apply = function () {
        this.track.style.transform = 'translate3d(' + this.x.toFixed(2) + 'px,0,0)';
    };

    Ticker.prototype.step = function (direction) {
        // Jump one headline. Snapping to an item boundary keeps a headline
        // aligned with the label instead of stopping mid-word.
        var nodes = this.track.querySelectorAll('.' + GAP_CLASS);
        if (!nodes.length) {
            return;
        }
        var width = nodes[0].getBoundingClientRect().width || 200;
        this.x -= direction * width;
        this.wrap();
        this.apply();
    };

    Ticker.prototype.wrap = function () {
        if (!this.setWidth) {
            return;
        }
        while (this.x <= -this.setWidth) {
            this.x += this.setWidth;
        }
        while (this.x > 0) {
            this.x -= this.setWidth;
        }
    };

    Ticker.prototype.tick = function (timestamp) {
        this.frame = null;
        if (!this.running) {
            return;
        }
        var dt = this.last ? Math.min((timestamp - this.last) / 1000, MAX_DT) : 0;
        this.last = timestamp;
        if (!this.paused) {
            this.x -= SPEED * dt;
            this.wrap();
            this.apply();
        }
        this.schedule();
    };

    Ticker.prototype.schedule = function () {
        if (this.frame || !this.running) {
            return;
        }
        this.frame = window.requestAnimationFrame(this.tick.bind(this));
    };

    Ticker.prototype.start = function () {
        if (this.reduced) {
            // No auto-scroll; the prev/next buttons still work.
            this.root.classList.add('nm-ticker--static');
            return;
        }
        if (this.running) {
            return;
        }
        this.running = true;
        this.last = 0;
        this.schedule();
    };

    Ticker.prototype.stop = function () {
        this.running = false;
        if (this.frame) {
            window.cancelAnimationFrame(this.frame);
            this.frame = null;
        }
    };

    Ticker.prototype.observe = function () {
        var self = this;

        // Hover / focus: hold still so a headline can be read and clicked.
        ['pointerenter', 'focusin'].forEach(function (evt) {
            self.root.addEventListener(evt, function () { self.paused = true; });
        });
        ['pointerleave', 'focusout'].forEach(function (evt) {
            self.root.addEventListener(evt, function () { self.paused = false; });
        });

        // Off screen or backgrounded tab: stop burning frames.
        if ('IntersectionObserver' in window) {
            new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    self.visible = entry.isIntersecting;
                    if (entry.isIntersecting) {
                        self.last = 0;
                        self.start();
                    } else {
                        self.stop();
                    }
                });
            }).observe(this.root);
        }
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                self.stop();
            } else if (self.visible) {
                self.last = 0;
                self.start();
            }
        });

        window.addEventListener('resize', function () {
            self.measure();
            self.wrap();
            self.apply();
        });

        // Prev / next live in the sibling controls block.
        var bar = this.root.closest('.nm-trending-container') || this.root.parentNode;
        if (!bar) {
            return;
        }
        bar.querySelectorAll('[data-nm-ticker]').forEach(function (btn) {
            btn.addEventListener('click', function (ev) {
                ev.preventDefault();
                self.step(btn.dataset.nmTicker === 'prev' ? -1 : 1);
            });
        });
    };

    function headlinesFor(root) {
        // /news renders the headlines into the markup; the article pages have
        // no server-side list, so they ask the API for one.
        var raw = root.dataset.headlines;
        if (raw) {
            try {
                var parsed = JSON.parse(raw);
                if (parsed && parsed.length) {
                    return Promise.resolve(parsed);
                }
            } catch (e) {
                /* fall through to the fetch */
            }
        }
        return fetch('/api/v1/news?limit=12')
            .then(function (res) { return res.ok ? res.json() : null; })
            .then(function (payload) {
                var rows = (payload && payload.data) || [];
                return rows.filter(function (r) { return r.title; })
                    .map(function (r) {
                        return { title: r.title, url: '/news/' + r.id };
                    });
            })
            .catch(function () { return []; });
    }

    function init() {
        document.querySelectorAll('.nm-ticker').forEach(function (root) {
            if (root.dataset.nmTickerReady) {
                return;
            }
            root.dataset.nmTickerReady = '1';
            var ticker = new Ticker(root);
            headlinesFor(root).then(function (items) {
                if (items && items.length) {
                    ticker.render(items);
                } else {
                    root.classList.add('nm-ticker--empty');
                }
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
