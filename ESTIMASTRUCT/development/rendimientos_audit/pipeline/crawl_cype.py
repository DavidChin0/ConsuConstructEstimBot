#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Crawl CYPE Honduras public unit-of-work pages (obra_nueva) and cache HTML.
Goal-21170 source #3. Public reference project only (no login). Cache to disk
so reruns are free and idempotent. Records discovery manifest.
"""
import os, json, re, time
import requests
from bs4 import BeautifulSoup

BASE = "https://honduras.generadordeprecios.info"
START = BASE + "/obra_nueva/"
CACHE = r"D:\GitHub\EstimBot\ConsuConstructEstimBot\ESTIMASTRUCT\development\rendimientos_audit\pipeline\data\downloads\cype_units"
os.makedirs(CACHE, exist_ok=True)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (research; rendimientos audit EstimaStruct)"})

# Nav / non-unit pages to skip
SKIP = ("access.html", "login", "sugerencias", "manualdeusoymantenimiento",
        "manualdeusoymantenimiento", "aviso", "privacidad", "cookies")

def get(url, retry=3):
    fn = re.sub(r'[^A-Za-z0-9_.-]', '_', url.split("generadordeprecios.info/")[-1]) + ".html"
    path = os.path.join(CACHE, fn)
    if os.path.exists(path) and os.path.getsize(path) > 2000:
        return open(path, encoding="utf-8", errors="replace").read(), True
    for _ in range(retry):
        try:
            r = SESSION.get(url, timeout=40)
            if r.status_code == 200:
                txt = r.text
                open(path, "w", encoding="utf-8").write(txt)
                time.sleep(0.3)
                return txt, False
        except Exception as e:
            time.sleep(1.5)
    return None, False

def is_unit(html):
    return "Justificaci" in html and "Rendimiento" in html

def links_from(html, base_url):
    out = []
    for a in BeautifulSoup(html, "lxml").find_all("a", href=True):
        h = a["href"]
        if "/obra_nueva/" not in h:
            continue
        if any(s in h for s in SKIP):
            continue
        if not h.endswith(".html"):
            continue
        if h.startswith("//"):
            h = "https:" + h
        elif h.startswith("/"):
            h = BASE + h
        elif not h.startswith("http"):
            h = BASE + "/" + h.lstrip("/")
        out.append(h)
    return out

def extract_unit_meta(html, url):
    soup = BeautifulSoup(html, "lxml")
    # unit code + title: pattern "CSL010" then "Placa de cimientos"
    code = None
    m = re.search(r"([A-Z]{2,4}\d{2,4})", html)
    if m:
        code = m.group(1)
    # title of unit
    title = None
    for tag in soup.find_all(["h1", "h2", "h3"]):
        t = tag.get_text(" ", strip=True)
        if t and t.lower() not in ("obra nueva", "buscar unidades de obra", "generador de precios"):
            title = t
            break
    # unit of activity: e.g. "m³ Placa de cimientos" near code
    um = re.search(r"(m[²³]|m2|m3|kg|t|ud|u\.d\.|ml|m)\s*</[^>]+>\s*([A-Za-zÁ-ú ].+?)</", html)
    unidad = None
    return code, title

# BFS
visited = set()
units = []          # list of dicts {url, code, title, chapter}
queue = [(START, 0, "raiz")]
max_units = 500
while queue and len(units) < max_units:
    url, depth, chap = queue.pop(0)
    if url in visited:
        continue
    visited.add(url)
    html, cached = get(url)
    if not html:
        print("FAIL", url)
        continue
    if is_unit(html):
        code, title = extract_unit_meta(html, url)
        units.append({"url": url, "code": code, "title": title, "chapter": chap})
        continue
    # not a unit: enqueue children up to depth 3
    if depth < 3:
        for l in links_from(html, url):
            if l not in visited:
                # derive chapter name from path segment
                seg = l.split("/obra_nueva/")[-1].split("/")[0].replace(".html","")
                queue.append((l, depth+1, seg))

print("Discovered unit pages:", len(units))
with open(os.path.join(CACHE, "..", "cype_units_index.json"), "w", encoding="utf-8") as f:
    json.dump(units, f, ensure_ascii=False, indent=1)
print("Saved index.")
