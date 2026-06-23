"""Conjunto de ícones de linha (grade 24, traço consistente).

Adição do redesenho "Editorial Risk": o produto original é text-first e não tinha
ícones. Este set é inline (SVG), sem dependência de CDN/runtime. As strings são os
filhos do ``<svg>``; o macro ``icon()`` em ``_macros.html`` monta o ``<svg>`` ao redor.
"""

ICONS = {
    "umbrella": '<path d="M12 12v7a2.2 2.2 0 0 0 4.4 0"/><path d="M2.5 12a9.5 8.5 0 0 1 19 0 .5.5 0 0 1-.5.5H3a.5.5 0 0 1-.5-.5Z"/><path d="M12 12V3"/>',
    "alert": '<path d="M12 3.5 2.5 20.5h19L12 3.5Z"/><path d="M12 10v4.5"/><path d="M12 17.6h.01"/>',
    "shield": '<path d="M12 3 4.5 5.7v5.6c0 4.7 3.2 7.6 7.5 8.7 4.3-1.1 7.5-4 7.5-8.7V5.7L12 3Z"/><path d="M12 8.5v3.5"/><path d="M12 15.2h.01"/>',
    "calendar": '<rect x="3.2" y="4.6" width="17.6" height="16.2" rx="2.2"/><path d="M8 3v3.2M16 3v3.2M3.2 9.4h17.6"/>',
    "clock": '<circle cx="12" cy="12" r="8.6"/><path d="M12 7.4V12l3.2 2"/>',
    "check": '<path d="M4.8 12.6 9.6 17.4 19.2 7"/>',
    "checkCircle": '<circle cx="12" cy="12" r="8.6"/><path d="M8.4 12.2 11 14.8 15.8 9.4"/>',
    "users": '<circle cx="9" cy="8" r="3.3"/><path d="M3.4 19.2a5.6 5.6 0 0 1 11.2 0"/><circle cx="17.6" cy="8.6" r="2.7"/><path d="M16.2 13.4a4.7 4.7 0 0 1 4.4 4.6"/>',
    "building": '<rect x="4.5" y="3" width="11" height="18" rx="1.2"/><path d="M15.5 9h3.2a1 1 0 0 1 1 1v11"/><path d="M8 7h1.6M11.5 7h.4M8 10.5h1.6M11.5 10.5h.4M8 14h1.6M11.5 14h.4"/><path d="M9 21v-3.2h2V21"/>',
    "briefcase": '<rect x="3.2" y="7.4" width="17.6" height="12.4" rx="2"/><path d="M8.4 7.4V6a2 2 0 0 1 2-2h3.2a2 2 0 0 1 2 2v1.4"/><path d="M3.2 12.5h17.6"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4.3-4.3"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "arrowLeft": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "arrowUpRight": '<path d="M7 17 17 7M8.5 7H17v8.5"/>',
    "chevronDown": '<path d="M6 9.5 12 15.5 18 9.5"/>',
    "chevronRight": '<path d="M9.5 6 15.5 12 9.5 18"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2.6v2.4M12 19v2.4M2.6 12H5M19 12h2.4M5.4 5.4 7 7M17 17l1.6 1.6M18.6 5.4 17 7M7 17l-1.6 1.6"/>',
    "moon": '<path d="M20.5 13.2A8.4 8.4 0 1 1 10.8 3.5a6.6 6.6 0 0 0 9.7 9.7Z"/>',
    "panelLeft": '<rect x="3.2" y="4.4" width="17.6" height="15.2" rx="2.2"/><path d="M9.2 4.4v15.2"/>',
    "panelTop": '<rect x="3.2" y="4.4" width="17.6" height="15.2" rx="2.2"/><path d="M3.2 9.4h17.6"/>',
    "bell": '<path d="M6 9.5a6 6 0 0 1 12 0c0 6 2.4 6.5 2.4 6.5H3.6S6 15.5 6 9.5Z"/><path d="M10.2 20a2 2 0 0 0 3.6 0"/>',
    "filter": '<path d="M3.5 5.5h17l-6.6 7.6V20l-3.8-1.9v-5z"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "sliders": '<path d="M4 8h9M17 8h3M4 16h3M11 16h9"/><circle cx="15" cy="8" r="2.1"/><circle cx="9" cy="16" r="2.1"/>',
    "logout": '<path d="M9.5 21H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.5"/><path d="M16 16.5 20.5 12 16 7.5M20.5 12H9.5"/>',
    "trending": '<path d="M3.5 16.5 9.5 10.5 13 14 20.5 6.5"/><path d="M15.5 6.5h5v5"/>',
    "dot": '<circle cx="12" cy="12" r="3.2" fill="currentColor" stroke="none"/>',
    "flag": '<path d="M5 21V4M5 4h11l-2 3.5L16 11H5"/>',
    "hourglass": '<path d="M7 4h10M7 20h10M7.5 4c0 4 9 4.5 9 8s-9 4-9 8M16.5 4c0 4-9 4.5-9 8s9 4 9 8"/>',
    "list": '<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1.3" fill="currentColor" stroke="none"/><circle cx="4" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="4" cy="18" r="1.3" fill="currentColor" stroke="none"/>',
    "grid": '<rect x="3.5" y="3.5" width="7" height="7" rx="1.4"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.4"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.4"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.4"/>',
    "download": '<path d="M12 3.5v11M7.5 10 12 14.5 16.5 10"/><path d="M4.5 19.5h15"/>',
    "settings": '<circle cx="12" cy="12" r="3.2"/><path d="M19.4 13.5a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V20a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.11-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.03H4a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1.11 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H10a1.7 1.7 0 0 0 1.03-1.56V4a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V10a1.7 1.7 0 0 0 1.56 1.03H20a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.56 1.03Z"/>',
    "lock": '<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/><circle cx="12" cy="15.5" r="1.3" fill="currentColor" stroke="none"/>',
    "messageCircle": '<path d="M20.5 11.6a8 8 0 0 1-11.7 7.1L4 20l1.3-4.6A8 8 0 1 1 20.5 11.6Z"/><path d="M8.5 11.5h.01M12 11.5h.01M15.5 11.5h.01"/>',
}
