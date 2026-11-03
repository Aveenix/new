/** @odoo-module **/

import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

// Google's rating, hours and photos for a listing linked to a Google place.
// The Google Maps Platform terms don't allow storing this content, so it is
// fetched live in the visitor's browser with the website's Maps key; Odoo
// only knows the place ID.

const PLACE_FIELDS = [
    "rating",
    "userRatingCount",
    "regularOpeningHours",
    "utcOffsetMinutes",
    "businessStatus",
    "photos",
    "googleMapsURI",
];
const MAX_PHOTOS = 4;

let mapsReady;

function loadGoogleMaps(key) {
    if (!mapsReady) {
        mapsReady = new Promise((resolve, reject) => {
            if (window.google?.maps?.importLibrary) {
                resolve();
                return;
            }
            const callback = "__avcGoogleMapsReady";
            window[callback] = () => {
                delete window[callback];
                resolve();
            };
            const script = document.createElement("script");
            script.src =
                "https://maps.googleapis.com/maps/api/js?v=weekly&loading=async" +
                `&key=${encodeURIComponent(key)}&callback=${callback}`;
            script.async = true;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    return mapsReady;
}

function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) {
        el.className = className;
    }
    if (text !== undefined) {
        el.textContent = text;
    }
    return el;
}

function link(href, text) {
    const a = node("a", "", text);
    a.href = href;
    a.target = "_blank";
    a.rel = "noopener";
    return a;
}

function stars(value) {
    const wrap = node("span", "avc-stars");
    for (let star = 1; star <= 5; star++) {
        const icon =
            value >= star - 0.25 ? "fa-star" : value >= star - 0.75 ? "fa-star-half-o" : "fa-star-o";
        wrap.append(node("i", `fa ${icon}`));
    }
    return wrap;
}

export class ConnectGooglePlace extends Interaction {
    static selector = ".avc-google[data-place-id][data-maps-key]";

    async willStart() {
        const { placeId, mapsKey } = this.el.dataset;
        try {
            await this.waitFor(loadGoogleMaps(mapsKey));
            const { Place } = await this.waitFor(google.maps.importLibrary("places"));
            this.place = new Place({ id: placeId });
            await this.waitFor(this.place.fetchFields({ fields: PLACE_FIELDS }));
            this.isOpen = await this.waitFor(this.place.isOpen().catch(() => undefined));
        } catch {
            // Bad key, API not enabled, unknown place: drop the card rather
            // than show a broken one.
            this.place = null;
        }
    }

    start() {
        if (!this.place) {
            this.el.classList.add("d-none");
            return;
        }
        const place = this.place;
        const body = this.el.querySelector(".avc-google-body");
        body.replaceChildren();

        if (place.rating) {
            const rating = node("div", "avc-google-rating");
            rating.append(
                node("strong", "", place.rating.toFixed(1)),
                stars(place.rating),
                node("span", "", _t("(%s reviews)", place.userRatingCount || 0))
            );
            body.append(rating);
        }
        if (place.businessStatus === "CLOSED_PERMANENTLY") {
            body.append(node("div", "avc-google-status is-closed", _t("Permanently closed")));
        } else if (this.isOpen !== undefined) {
            body.append(
                node(
                    "div",
                    `avc-google-status ${this.isOpen ? "is-open" : "is-closed"}`,
                    this.isOpen ? _t("Open now") : _t("Closed now")
                )
            );
        }
        const days = place.regularOpeningHours?.weekdayDescriptions || [];
        if (days.length) {
            const list = node("ul", "avc-google-hours");
            list.append(...days.map((day) => node("li", "", day)));
            body.append(list);
        }

        const photos = (place.photos || []).slice(0, MAX_PHOTOS);
        if (photos.length) {
            const grid = node("div", "avc-google-photos");
            for (const photo of photos) {
                const img = node("img");
                img.src = photo.getURI({ maxWidth: 480 });
                img.alt = "";
                img.loading = "lazy";
                grid.append(img);
            }
            body.append(grid);
        }

        // Attribution the Google terms ask for: the source, and photo authors.
        const attribution = node("div", "avc-google-attr");
        attribution.append(_t("From "), link(place.googleMapsURI, "Google Maps"));
        const authors = photos.flatMap((photo) => photo.authorAttributions || []);
        if (authors.length) {
            attribution.append(" · ", _t("Photos: "));
            authors.forEach((author, index) => {
                attribution.append(index ? ", " : "", author.uri ? link(author.uri, author.displayName) : author.displayName);
            });
        }
        body.append(attribution);
    }
}

registry.category("public.interactions").add("aveenix_connect.google_place", ConnectGooglePlace);
