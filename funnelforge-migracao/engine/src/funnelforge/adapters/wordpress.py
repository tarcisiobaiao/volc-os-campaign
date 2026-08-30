from __future__ import annotations
import json
import re

import httpx

# Astral-plane (4-byte / non-BMP) chars -- emojis like the redactor's 👉/👇.
# Elementor requires a utf8mb4 DB; on a utf8 (3-byte) `postmeta` column MySQL
# rejects 4-byte chars, surfacing as a 500 `rest_meta_database_error`. Strip
# them from `_elementor_data` before writing so publish works on either DB.
_ASTRAL_RE = re.compile(r"[\U00010000-\U0010FFFF]")


class WordPressPublisher:
    def __init__(self, base_url: str, user: str, app_token: str,
                 client: httpx.Client | None = None):
        self.base = base_url.rstrip("/")
        self._client = client or httpx.Client(auth=(user, app_token),
                                              timeout=120)

    def _url(self, path: str) -> str:
        return f"{self.base}/wp-json/wp/v2/{path}"

    def upload_media(self, data: bytes, filename: str, mime: str,
                     alt: str = "") -> dict:
        r = self._client.post(
            self._url("media"),
            content=data,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": mime
            })
        r.raise_for_status()
        media = r.json()
        # Alt text can't ride the raw binary upload, so set it as a follow-up
        # JSON write on the created attachment (best-effort, never fatal).
        if alt and media.get("id"):
            try:
                a = self._client.post(
                    self._url(f"media/{media['id']}"), json={"alt_text": alt})
                a.raise_for_status()
                media["alt_text"] = alt
            except Exception:  # noqa: BLE001 - alt is cosmetic; keep the upload
                pass
        return media

    def create_post(self, title, content, slug, status,
                    post_type, featured_media: int | None = None) -> dict:
        payload = {"title": title, "content": content, "slug": slug,
                   "status": status}
        if featured_media:
            payload["featured_media"] = featured_media
        r = self._client.post(self._url(post_type), json=payload)
        r.raise_for_status()
        return r.json()

    # semantic field -> Yoast's real postmeta key.
    _YOAST_KEYS = {
        "title": "_yoast_wpseo_title",
        "metadesc": "_yoast_wpseo_metadesc",
        "focuskw": "_yoast_wpseo_focuskw",
    }

    def set_yoast(self, post_id, post_type, fields, status=None) -> dict:
        """Write the Yoast SEO title / meta description / focus keyword to the
        post, mapping the semantic keys (title/metadesc/focuskw) to Yoast's
        actual postmeta keys (`_yoast_wpseo_*`).

        REQUIRES those meta keys to be registered with `show_in_rest` on the
        site (see docs/yoast-rest-meta.php) -- otherwise WordPress accepts the
        request (200) but SILENTLY ignores the unregistered meta, and nothing
        is stored. Empty values are skipped so we never blank an existing field.

        Re-asserts `status` (when given) on the SAME write: updating registered
        meta can flip a draft to `publish` on some setups (same class of issue
        as the Elementor `_elementor_data` write in create_elementor_page), so
        pinning the status back keeps a draft a draft.
        """
        meta = {self._YOAST_KEYS[k]: v for k, v in fields.items()
                if k in self._YOAST_KEYS and v}
        if not meta:
            return {}
        payload: dict = {"meta": meta}
        if status:
            payload["status"] = status
        r = self._client.post(
            self._url(f"{post_type}/{post_id}"),
            json=payload)
        r.raise_for_status()
        return r.json()

    def set_status(self, post_id, post_type, status) -> dict:
        """Explicitly pin a post's status. Used as the LAST publish write so a
        registered-meta side effect (Elementor/Yoast writes flip a draft to
        publish on some setups) can't leave the post in the wrong status."""
        r = self._client.post(
            self._url(f"{post_type}/{post_id}"),
            json={"status": status})
        r.raise_for_status()
        return r.json()

    def create_elementor_page(self, title, slug, elementor,
                              status, post_type="pages", page_settings=None) -> dict:
        """Create an Elementor entry (default WP `pages`; the LP uses the `r`
        post type -> /r/<slug>) via a TWO-STEP write.

        WordPress returns 500 `rest_meta_database_error` when the protected
        `_elementor_data` meta is written during the INSERT, but accepts it as
        an UPDATE on an already-created post. So: create bare, set
        `_elementor_edit_mode` + Canvas layout + `_elementor_page_settings`
        (hide_title), then set the (sanitized) `_elementor_data`. If the data
        write fails, the bare entry is deleted so no orphan is left.

        The `template=elementor_canvas` field makes the LP render with NO theme
        header/footer/title (guaranteed on every publish), and
        `_elementor_page_settings.hide_title=yes` hides the entry title. Both
        are set on the UPDATE writes (proven to persist over REST for the `r`
        type; the meta form of `_wp_page_template` does not).
        """
        r = self._client.post(
            self._url(post_type),
            json={"title": title, "slug": slug, "status": status})
        r.raise_for_status()
        pid = r.json().get("id")
        # Page settings: the template's own settings (incl. hide_title) plus a
        # hard hide_title guarantee. Stored as an OBJECT meta (Elementor reads
        # it as the page's settings model).
        ps = dict(page_settings or {})
        ps.setdefault("hide_title", "yes")
        try:
            self._client.post(
                self._url(f"{post_type}/{pid}"),
                json={"template": "elementor_canvas",
                      "meta": {"_elementor_edit_mode": "builder",
                               "_elementor_page_settings": ps}}
            ).raise_for_status()
            data = _ASTRAL_RE.sub("", json.dumps(elementor, ensure_ascii=False))
            # Re-assert `status` + Canvas on the final write: updating the
            # Elementor meta can flip the entry to `publish` on some setups, so
            # pin it back to the requested status (keeps the LP a DRAFT).
            r2 = self._client.post(
                self._url(f"{post_type}/{pid}"),
                json={"status": status, "template": "elementor_canvas",
                      "meta": {"_elementor_data": data}})
            r2.raise_for_status()
        except Exception:
            self._client.delete(self._url(f"{post_type}/{pid}"), params={"force": "true"})
            raise
        return r2.json()
