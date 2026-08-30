from __future__ import annotations

from funnelforge.config.settings import Settings
from funnelforge.domain.models import AdManifest, AdSlot, PageRole, VignetteCap

# distinct high hex id band for injected ad slots; never collides with the
# elementor builder's ids (which start at 0x00000001 and increment by widget).
_AD_ID_BASE = 0x0AD00000


def build_ad_manifest(settings: Settings, role: PageRole) -> AdManifest:
    """Deterministic AdManifest for `role` from config. Slots are typed by
    page role and carry a reserved min-height (CLS defense). Content-free:
    NEVER emits a <script> -- the publisher injects the approved ad stack
    against the declared anchors. A role with no configured slots yields an
    empty slot list (no ads > a crash)."""
    slots = [
        AdSlot(
            slot_id=c.slot_id, page_role=role, placement=c.placement,
            sizes=list(c.sizes), min_height_px=c.min_height_px,
            refresh_eligible=c.refresh_eligible, source_key=c.source_key,
        )
        for c in settings.ads.slots.get(role.value, [])
    ]
    v = settings.ads.vignette
    vignette = VignetteCap(
        enabled=v.enabled, max_per_window=v.max_per_window,
        window_seconds=v.window_seconds,
    )
    return AdManifest(slots=slots, vignette=vignette)


def slot_hint_html(slot: AdSlot) -> str:
    """Reserved, script-free anchor the publisher injects the approved ad unit
    against. `min-height` reserves layout space (CLS). Refresh and the GAM
    key-value are emitted ONLY for config-eligible slots / real source keys --
    over-refreshing risks the AdSense account and keys are never invented."""
    sizes = ",".join(slot.sizes)
    attrs = [
        'class="ff-ad-slot"',
        f'data-ad-slot="{slot.slot_id}"',
        f'data-ad-placement="{slot.placement}"',
        f'data-ad-sizes="{sizes}"',
    ]
    if slot.refresh_eligible:
        attrs.append('data-ad-refresh="true"')
    if slot.source_key:
        attrs.append(f'data-ad-kv="src={slot.source_key}"')
    return f'<div {" ".join(attrs)} style="min-height:{slot.min_height_px}px"></div>'


def vignette_meta(vignette: VignetteCap) -> str:
    """Script-free <meta> declaring the vignette/interstitial frequency cap
    (default 1 per 600s). The publisher/theme reads this to throttle the
    vignette -- a non-abusive cap protects the AdSense account."""
    if not vignette.enabled:
        return '<meta name="ff-ad-vignette" content="enabled=false">'
    return (
        '<meta name="ff-ad-vignette" content="'
        f"enabled=true;max_per_window={vignette.max_per_window};"
        f'window_seconds={vignette.window_seconds}">'
    )


def inject_ad_slots(elementor: list, manifest: AdManifest) -> list:
    """Append one reserved slot container (a text-editor holding the script-
    free slot-hint) per manifest slot to the first Elementor container, in the
    manifest's declared order. Mutates and returns `elementor` for chaining."""
    if not elementor:
        return elementor
    els = elementor[0].setdefault("elements", [])
    for i, slot in enumerate(manifest.slots):
        els.append({
            "id": f"{_AD_ID_BASE + i:08x}",
            "elType": "widget",
            "widgetType": "text-editor",
            "settings": {"editor": slot_hint_html(slot)},
            "elements": [],
        })
    return elementor
