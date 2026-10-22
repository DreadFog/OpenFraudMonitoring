"""Curated metadata fields and labels used by graph construction."""

PROPERTY_FIELDS = {
    "platform": {"label": "Platform", "columns": ["device_platform"]},
    "timezone": {"label": "Timezone", "columns": ["locale_internationalization_timezone"]},
    "language": {"label": "Language", "columns": ["locale_languages_language"]},
    "screen_resolution": {
        "label": "Screen Resolution",
        "columns": ["device_screen_resolution_width", "device_screen_resolution_height"],
        "join": "x",
    },
    "cpu_count": {"label": "CPU Count", "columns": ["device_cpu_count"], "type": "number"},
    "webgl_vendor": {"label": "WebGL Vendor", "columns": ["graphics_web_gl_vendor"]},
    "webgl_renderer": {"label": "WebGL Renderer", "columns": ["graphics_web_gl_renderer"]},
    "locale_language": {
        "label": "Locale Language",
        "columns": ["locale_internationalization_locale_language"],
    },
    "hev_platform": {"label": "UA-CH Platform", "columns": ["browser_high_entropy_values_platform"]},
    "hev_architecture": {
        "label": "UA-CH Architecture",
        "columns": ["browser_high_entropy_values_architecture"],
    },
    "color_scheme": {
        "label": "Color Scheme",
        "columns": ["device_media_queries_prefers_color_scheme"],
    },
    "canvas_fingerprint": {
        "label": "Canvas Fingerprint",
        "columns": ["graphics_canvas_canvas_fingerprint"],
    },
    "pointer_type": {"label": "Pointer Type", "columns": ["device_media_queries_pointer"]},
}

STIX_TYPE_LABELS = {
    "ipv4-addr": "IPv4 Address",
    "ipv6-addr": "IPv6 Address",
    "user-agent": "User Agent",
    "autonomous-system": "Autonomous System",
    "location": "Country",
    "indicator": "Indicator",
    "malware": "Malware",
    "campaign": "Campaign",
    "intrusion-set": "Intrusion Set",
}

DEVICE_PROPERTY_FIELDS = {
    "platform": {"label": "Platform", "attr": "platform"},
    "screen_resolution": {"label": "Screen Resolution", "attr": ("screen_width", "screen_height"), "join": "x"},
    "webgl_vendor": {"label": "WebGL Vendor", "attr": "webgl_vendor"},
    "webgl_renderer": {"label": "WebGL Renderer", "attr": "webgl_renderer"},
    "hev_platform": {"label": "UA-CH Platform", "attr": "hev_platform"},
    "hev_architecture": {"label": "UA-CH Architecture", "attr": "hev_architecture"},
    "hev_bitness": {"label": "UA-CH Bitness", "attr": "hev_bitness"},
    "hev_model": {"label": "UA-CH Model", "attr": "hev_model"},
    "hev_platform_version": {"label": "UA-CH Platform Version", "attr": "hev_platform_version"},
    "timezone": {"label": "Timezone", "attr": "timezone"},
    "language": {"label": "Language", "attr": "language"},
    "pixel_depth": {"label": "Pixel Depth", "attr": "pixel_depth", "type": "number"},
    "color_depth": {"label": "Color Depth", "attr": "color_depth", "type": "number"},
}
