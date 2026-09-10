"""Account-authorized existing single-image posts, resolved afresh before use.

Meta SDK AdCreative fields object_story_id/effective_object_story_id and
AdAccount.create_ad_creative(object_story_id) verified 2026-09-09:
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adcreative.py
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adaccount.py
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.trafego.meta import dominio as dom
from app.trafego.meta.adaptador import AdaptadorMetaSomenteLeitura
from .publicos import _conta_externa
from .contrato import ErroDeNascimentoMeta

_cache: dict[tuple, tuple[float, dict]] = {}


async def catalogo_cached(client, account_ref, page_ref, segredo, *, owner):
    # A short search cache never authorizes compilation. Include credential
    # fingerprint so changing/revoking a selected connection can't reuse it.
    key = (owner, account_ref, page_ref, hashlib.sha256(segredo.cabecalho_bearer().encode()).hexdigest())
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and cached[0] > now:
        return cached[1]
    result = await catalogo(client, account_ref, page_ref, segredo)
    for old in list(_cache):
        if _cache[old][0] <= now:
            _cache.pop(old, None)
    if len(_cache) >= 32:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (time.monotonic() + 30, result)
    return result


def reference(account: str, post: str) -> str:
    return "metapost_" + hashlib.sha256(f"{account}:{post}".encode()).hexdigest()[:32]


def _image_ref(account: str, image: str) -> str:
    return "metaasset_" + hashlib.sha256(f"META_ADS:{account}:image_asset:{image}".encode()).hexdigest()[:24]


def _https(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        return value if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password else None
    except ValueError:
        return None


def _unique_texts(values: Any, key: str | None = None) -> list[str]:
    """Return deterministic preview values; never a publication contract."""
    if not isinstance(values, list):
        return []
    result: set[str] = set()
    for item in values:
        value = item.get(key) if key and isinstance(item, dict) else item
        if isinstance(value, str) and value.strip():
            result.add(value.strip())
    return sorted(result)


def _normalize_flexible(creative: dict) -> dict | None:
    feed = creative.get("asset_feed_spec")
    if not isinstance(feed, dict) or feed.get("videos") or creative.get("video_id"):
        return None
    images = _unique_texts(feed.get("images"), "hash")
    links = _unique_texts(feed.get("link_urls"), "website_url")
    calls = _unique_texts(feed.get("call_to_action_types"))
    bodies = _unique_texts(feed.get("bodies"), "text")
    titles = _unique_texts(feed.get("titles"), "text")
    descriptions = _unique_texts(feed.get("descriptions"), "text")
    # Discovery only. A post id does not represent the entire dynamic feed;
    # show its variants, but never authorize reuse by flattening to this preview.
    if (not images or any(not re.fullmatch(r"[A-Za-z0-9_-]{6,160}", item) for item in images)
            or len(links) != 1 or not _https(links[0]) or len(calls) != 1
            or calls[0] not in {"LEARN_MORE", "SIGN_UP", "APPLY_NOW", "GET_QUOTE", "CONTACT_US"}
            or not bodies or not titles):
        return None
    return {
        "message": bodies[0],
        "headline": titles[0],
        "description": descriptions[0] if descriptions else "",
        "destination_url": links[0],
        "call_to_action_type": calls[0],
        "_image_hash": images[0],
        "_image_hashes": images,
        "is_flexible": True,
        "reuse_supported": False,
        "reuse_reason": "O ID desta publicação não garante preservar as variações do criativo. Monte um novo anúncio flexível com as peças desejadas.",
        "preview_only": True,
        "copy_variants": {"messages": bodies, "headlines": titles, "descriptions": descriptions},
        "_asset_feed_spec": feed,
        "image_variants": len(images),
        "text_variants": max(len(bodies), len(titles), len(descriptions)),
    }


def _normalize_groups(spec: Any) -> dict | None:
    """Ad-level flexible groups are previews, never a reusable static post.

    Meta SDK Ad.Field.creative_asset_groups_spec is on Ad, not AdCreative:
    https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/ad.py
    Preserve the legacy asset_feed_spec parser alongside this representation.
    """
    groups = spec.get("groups") if isinstance(spec, dict) else None
    if not isinstance(groups, list) or not groups:
        return None
    feed: dict[str, list] = {key: [] for key in
        ("images", "bodies", "titles", "descriptions", "link_urls", "call_to_action_types")}
    text_fields = {"primary_text": "bodies", "headline": "titles", "description": "descriptions"}
    for group in groups:
        if not isinstance(group, dict) or group.get("videos"):
            return None
        images, texts, cta = group.get("images"), group.get("texts", []), group.get("call_to_action")
        if (not isinstance(images, list) or not images or not isinstance(texts, list)
                or not isinstance(cta, dict) or not isinstance(cta.get("value"), dict)):
            return None
        if (not isinstance(cta.get("type"), str) or not _https(cta["value"].get("link"))):
            return None
        if any(not isinstance(item, dict) or not isinstance(item.get("hash"), str)
               or not re.fullmatch(r"[A-Za-z0-9_-]{6,160}", item["hash"]) for item in images):
            return None
        feed["images"].extend(images)
        feed["link_urls"].append({"website_url": cta["value"].get("link")})
        feed["call_to_action_types"].append(cta.get("type"))
        for item in texts:
            if (not isinstance(item, dict) or not isinstance(item.get("text_type"), str)
                    or item["text_type"] not in text_fields):
                return None
            if not isinstance(item.get("text"), str) or not item["text"].strip():
                return None
            feed[text_fields[item["text_type"]]].append({"text": item["text"]})
    result = _normalize_flexible({"asset_feed_spec": feed})
    if result:
        result.pop("_asset_feed_spec", None)
        result["_creative_asset_groups_spec"] = spec
    return result


def _has_flexible(row: dict) -> bool:
    creative = row.get("creative")
    return bool(row.get("creative_asset_groups_spec") or
                (isinstance(creative, dict) and creative.get("asset_feed_spec")))


def normalize(row: dict, account: str, page_ref: str) -> dict | None:
    creative = row.get("creative")
    if not isinstance(creative, dict) or creative.get("video_id"):
        return None
    post = creative.get("effective_object_story_id") or creative.get("object_story_id")
    if not isinstance(post, str) or not re.fullmatch(r"[0-9]+_[0-9]+", post):
        return None
    page = post.split("_", 1)[0]
    if dom.referencia_opaca_objeto(account, "page", page) != page_ref:
        return None
    story = creative.get("object_story_spec") or {}
    if not isinstance(story, dict) or str(story.get("page_id") or "") != page:
        return None
    if row.get("creative_asset_groups_spec"):
        normalized = _normalize_groups(row["creative_asset_groups_spec"])
        if not normalized:
            return None  # Never reinterpret malformed/unsupported groups as static.
    elif creative.get("asset_feed_spec"):
        normalized = _normalize_flexible(creative)
        if not normalized:
            return None
    else:
        link = story.get("link_data") if isinstance(story, dict) else None
        if not isinstance(link, dict) or link.get("child_attachments"):
            return None
        image = link.get("image_hash") or creative.get("image_hash")
        destination = _https(link.get("link"))
        if not isinstance(image, str) or not re.fullmatch(r"[A-Za-z0-9_-]{6,160}", image) or not destination:
            return None
        cta = link.get("call_to_action") or {}
        cta_type = cta.get("type") if isinstance(cta, dict) else None
        if not isinstance(cta_type, str) or cta_type not in {"LEARN_MORE", "SIGN_UP", "APPLY_NOW", "GET_QUOTE", "CONTACT_US"}:
            return None
        fields = {name: str(link.get(key) or "") for name, key in
                  (("message", "message"), ("headline", "name"), ("description", "description"))}
        if not all(fields.values()):
            return None
        normalized = dict(fields, destination_url=destination,
            call_to_action_type=cta_type, _image_hash=image, _image_hashes=[image],
            is_flexible=False, image_variants=1, text_variants=1, reuse_supported=True, preview_only=False)
    image = normalized["_image_hash"]
    return dict(normalized, post_ref=reference(account, post), asset_ref=_image_ref(account, image),
        label=str(row.get("name") or creative.get("name") or "Publicação existente")[:400],
        creative_name=str(creative.get("name") or "Publicação existente")[:400],
        source_ad_names=[str(row.get("name") or "Anúncio sem nome")[:400]],
        preview_url=_https(creative.get("image_url") or creative.get("thumbnail_url")),
        _post_id=post, _page_id=page)


async def catalogo(client, account_ref: str, page_ref: str, segredo) -> dict[str, dict]:
    account = await _conta_externa(AdaptadorMetaSomenteLeitura(client), account_ref, segredo)
    params = {"fields": "id,name,creative_asset_groups_spec,creative{id,name,object_story_id,effective_object_story_id,source_facebook_post_id,object_story_spec,image_hash,image_url,thumbnail_url,video_id,asset_feed_spec}", "limit": "100"}
    result: dict[str, dict] = {}
    flexible_posts: set[str] = set()
    cursors = set()
    for _ in range(100):
        try:
            response = await client.get(f"https://graph.facebook.com/v26.0/act_{account}/ads",
                params=params, headers={"Authorization": segredo.cabecalho_bearer()})
            body = response.json() if response.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("data"), list):
            raise ErroDeNascimentoMeta("META_EXISTING_POST_CATALOG_UNAVAILABLE", "Não foi possível ler as publicações desta conta. Tente novamente.")
        for row in body["data"]:
            if isinstance(row, dict) and _has_flexible(row):
                creative = row.get("creative")
                post = (creative.get("effective_object_story_id") or creative.get("object_story_id")) if isinstance(creative, dict) else None
                if (isinstance(post, str) and re.fullmatch(r"[0-9]+_[0-9]+", post)
                        and dom.referencia_opaca_objeto(account, "page", post.split("_", 1)[0]) == page_ref):
                    flexible_posts.add(reference(account, post))
            item = normalize(row, account, page_ref) if isinstance(row, dict) else None
            if item:
                previous = result.get(item["post_ref"])
                if previous:
                    names = list(dict.fromkeys(previous["source_ad_names"] + item["source_ad_names"]))
                    # A static fallback encountered first must not decide the
                    # capabilities of a post also referenced by a flexible ad.
                    if item["is_flexible"] and not previous["is_flexible"]:
                        result[item["post_ref"]] = item
                    result[item["post_ref"]]["source_ad_names"] = names
                else:
                    result[item["post_ref"]] = item
        paging = body.get("paging") or {}
        if isinstance(paging, dict) and not paging.get("next"):
            # Unsupported flexible rows can share a post with a valid static
            # fallback. Exclude that ambiguous static preview in either order.
            return {ref: item for ref, item in result.items()
                    if ref not in flexible_posts or item["is_flexible"]}
        page_cursors = paging.get("cursors") if isinstance(paging, dict) else None
        cursor = page_cursors.get("after") if isinstance(page_cursors, dict) else None
        if not isinstance(cursor, str) or not cursor or cursor in cursors:
            break
        cursors.add(cursor)
        params["after"] = cursor
    raise ErroDeNascimentoMeta("META_EXISTING_POST_CATALOG_INCOMPLETE", "A leitura das publicações não terminou. Nenhuma seleção parcial foi considerada completa.")


def publico(items: dict[str, dict], q: str = "", offset: int = 0, limit: int = 24) -> dict:
    term = q.strip().casefold()
    matches = [item for item in items.values() if not term or term in " ".join(
        [item["label"], item["creative_name"], *item["source_ad_names"]]).casefold()]
    return {"items": [{k:v for k,v in item.items() if not k.startswith("_")}
                      for item in matches[offset:offset+limit]], "total":len(matches),
            "offset":offset, "has_more":offset+limit<len(matches), "complete":True}
