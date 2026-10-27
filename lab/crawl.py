"""Rastrea la web de un concesionario: portada, páginas de stock, fichas de coche e info.

Uso: python lab/crawl.py lab/sites.json <slug> out/
Guarda HTML renderizado, texto, imágenes encontradas, enlaces y capturas.
"""
import json
import os
import re
import sys
import urllib.parse

from playwright.sync_api import sync_playwright

job = json.load(open(sys.argv[1]))
SLUG = sys.argv[2]
OUT = os.path.join(sys.argv[3], SLUG)
site = next(s for s in job["sites"] if s["slug"] == SLUG)
os.makedirs(os.path.join(OUT, "pages"), exist_ok=True)

STOCK_KEYS = ["stock", "vehiculo", "vehículo", "coches", "inventario", "ocasion", "ocasión", "catalog", "venta",
              "cars", "showroom", "collection", "coleccion", "colección", "exposicion", "disponible", "comprar", "garage", "seminuevo", "usados"]
INFO_KEYS = ["nosotros", "quienes", "quiénes", "empresa", "about", "contact", "servicio", "financ", "historia", "equipo", "garantia", "garantía"]
MAKES = ["porsche", "ferrari", "lamborghini", "mercedes", "amg", "bmw", "audi", "bentley", "rolls", "mclaren", "aston", "maserati",
         "land-rover", "range-rover", "rover", "jaguar", "lexus", "tesla", "cupra", "volvo", "mini", "toyota", "ford", "jeep", "alfa",
         "abarth", "maybach", "cayenne", "macan", "panamera", "911", "taycan", "urus", "huracan", "g63", "g-63", "clase", "defender",
         "volkswagen", "seat", "nissan", "hyundai", "kia", "peugeot", "renault", "corvette", "dodge", "ram", "cadillac", "lotus",
         "bugatti", "pagani", "koenigsegg", "genesis", "polestar", "smart", "fiat", "skoda", "opel", "citroen", "mustang", "brabus"]
DETAIL_HINTS = ["vehiculo/", "vehiculos/", "coche/", "coches/", "stock/", "ficha", "/car/", "/cars/", "/item", "detalle",
                "product", "/auto/", "/anuncio", "/vehicle", "/oferta", "/inventario/", "/ocasion/", "/listing"]

IMG_PROBE = """
() => {
  const out = [];
  const add = (u, w, h, alt, where) => { if (u && !u.startsWith('data:')) out.push({u, w, h, alt: (alt||'').slice(0,120), where}); };
  for (const im of document.querySelectorAll('img')) {
    const r = im.getBoundingClientRect();
    add(im.currentSrc || im.src, im.naturalWidth, im.naturalHeight, im.alt, 'img');
    for (const a of ['data-src', 'data-lazy-src', 'data-original', 'data-full', 'data-large_image', 'data-zoom-image', 'data-bg', 'data-image', 'data-pin-media']) {
      const v = im.getAttribute(a); if (v) add(new URL(v, location.href).href, 0, 0, im.alt, a);
    }
    const ss = im.getAttribute('srcset') || im.getAttribute('data-srcset') || '';
    for (const part of ss.split(',')) { const p = part.trim().split(' ')[0]; if (p) add(new URL(p, location.href).href, 0, 0, im.alt, 'srcset'); }
  }
  for (const s of document.querySelectorAll('source[srcset]')) {
    for (const part of s.srcset.split(',')) { const p = part.trim().split(' ')[0]; if (p) add(new URL(p, location.href).href, 0, 0, '', 'source'); }
  }
  for (const el of document.querySelectorAll('*')) {
    const bg = getComputedStyle(el).backgroundImage;
    if (bg && bg.startsWith('url(')) { const m = bg.match(/url\\(["']?([^"')]+)/); if (m) add(new URL(m[1], location.href).href, el.offsetWidth, el.offsetHeight, '', 'bg'); }
  }
  for (const a of document.querySelectorAll('a[href]')) {
    if (/\\.(jpe?g|png|webp)(\\?|$)/i.test(a.href)) add(a.href, 0, 0, '', 'a');
  }
  const meta = {};
  for (const m of document.querySelectorAll('meta[property], meta[name]')) meta[m.getAttribute('property') || m.getAttribute('name')] = (m.content || '').slice(0, 400);
  const ld = [...document.querySelectorAll('script[type="application/ld+json"]')].map(s => s.textContent.slice(0, 20000));
  const links = [...document.querySelectorAll('a[href]')].map(a => ({h: a.href, t: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 100),
    img: !!a.querySelector('img') || getComputedStyle(a).backgroundImage !== 'none', nav: !!a.closest('header, nav, footer')}));
  const logo = [...document.querySelectorAll('header img, nav img, [class*=logo] img, img[class*=logo], img[alt*=logo i], img[src*=logo i]')].slice(0, 6)
    .map(i => ({u: i.currentSrc || i.src, w: i.naturalWidth, h: i.naturalHeight, alt: i.alt}));
  const svgLogo = [...document.querySelectorAll('header svg, [class*=logo] svg')].slice(0, 2).map(s => s.outerHTML.slice(0, 30000));
  const st = getComputedStyle(document.body);
  const colors = {};
  for (const el of [...document.querySelectorAll('header, nav, footer, button, .btn, a.button, [class*=btn], h1, h2')].slice(0, 80)) {
    const s = getComputedStyle(el);
    for (const c of [s.backgroundColor, s.color]) colors[c] = (colors[c] || 0) + 1;
  }
  const fonts = [...new Set([...document.querySelectorAll('h1,h2,h3,p,a')].slice(0, 60).map(e => getComputedStyle(e).fontFamily))];
  return {title: document.title, images: out, meta, ld, links, logo, svgLogo, bodyBg: st.backgroundColor, bodyColor: st.color, colors, fonts,
          text: document.body.innerText.slice(0, 40000), height: document.documentElement.scrollHeight};
}
"""


def norm(u):
    u = u.split("#")[0]
    return u.rstrip("/") if u.count("/") > 3 else u


BASE = urllib.parse.urlparse(site["url"]).netloc.replace("www.", "")


def same(u):
    p = urllib.parse.urlparse(u)
    return p.scheme in ("http", "https") and p.netloc.replace("www.", "") == BASE and not re.search(r"\.(jpe?g|png|webp|pdf|gif|svg|mp4)(\?|$)", p.path, re.I)


def cookies(page):
    for text in ["Aceptar todo", "Aceptar todas", "Aceptar", "Accept all", "Accept", "Acepto", "Permitir todo", "Entendido", "OK", "Got it", "Allow all"]:
        try:
            loc = page.get_by_role("button", name=text, exact=False)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=2000)
                page.wait_for_timeout(600)
                return
        except Exception:
            pass


def scroll(page, steps=45):
    last = -1
    for _ in range(steps):
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(280)
        y = page.evaluate("scrollY + innerHeight >= document.documentElement.scrollHeight - 5")
        if y:
            h = page.evaluate("document.documentElement.scrollHeight")
            if h == last:
                break
            last = h
            page.wait_for_timeout(900)
    page.wait_for_timeout(1200)


index = []
seen = set()


def visit(page, url, name, shot=False, deep=True):
    url = norm(url)
    if url in seen:
        return None
    seen.add(url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        cookies(page)
        if deep:
            scroll(page)
        data = page.evaluate(IMG_PROBE)
        html = page.content()
    except Exception as e:
        print("ERROR", url, e)
        index.append({"name": name, "url": url, "error": str(e)[:300]})
        return None
    open(os.path.join(OUT, "pages", name + ".html"), "w").write(html)
    json.dump(data, open(os.path.join(OUT, "pages", name + ".json"), "w"), ensure_ascii=False)
    if shot:
        try:
            page.evaluate("scrollTo(0,0)")
            page.wait_for_timeout(800)
            h = min(page.evaluate("document.documentElement.scrollHeight"), 9000)
            page.screenshot(path=os.path.join(OUT, "pages", name + ".jpg"), full_page=True, type="jpeg", quality=50,
                            clip={"x": 0, "y": 0, "width": 1440, "height": h})
        except Exception as e:
            print("shot", e)
    index.append({"name": name, "url": url, "final": page.url, "title": data["title"], "n_img": len(data["images"]), "n_links": len(data["links"])})
    print("ok", name, url, len(data["images"]), len(data["links"]))
    return data


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="es-ES",
                              user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36")
    page = ctx.new_page()
    home = visit(page, site["url"], "home", shot=True)
    links = home["links"] if home else []
    for i, u in enumerate(site.get("extra", [])):
        d = visit(page, u, f"extra{i}", shot=True)
        if d:
            links += d["links"]

    def score_stock(l):
        h = l["h"].lower()
        t = l["t"].lower()
        return sum(k in h for k in STOCK_KEYS) * 2 + sum(k in t for k in STOCK_KEYS)

    stock_cands = []
    for l in sorted(links, key=score_stock, reverse=True):
        if same(l["h"]) and score_stock(l) > 0 and norm(l["h"]) not in [norm(x) for x in stock_cands]:
            stock_cands.append(l["h"])
    info_cands = []
    for l in links:
        h = l["h"].lower()
        t = l["t"].lower()
        if same(l["h"]) and any(k in h or k in t for k in INFO_KEYS) and norm(l["h"]) not in [norm(x) for x in info_cands]:
            info_cands.append(l["h"])

    stock_links = []
    for i, u in enumerate(stock_cands[:5]):
        d = visit(page, u, f"stock{i}", shot=(i < 2))
        if d:
            stock_links += d["links"]
            # paginación
            pages = [l["h"] for l in d["links"] if same(l["h"]) and re.search(r"(page[/=]\d|/pagina/\d|[?&]pag(e|ina)?=\d|/p/\d)", l["h"], re.I)]
            for j, pu in enumerate(dict.fromkeys(pages)):
                if j >= 6:
                    break
                d2 = visit(page, pu, f"stock{i}p{j}")
                if d2:
                    stock_links += d2["links"]
    for i, u in enumerate(info_cands[:5]):
        visit(page, u, f"info{i}", deep=False)

    nav = {norm(l["h"]) for l in (home["links"] if home else []) if l.get("nav")}

    def is_detail(l):
        h = l["h"]
        if not same(h) or norm(h) in nav:
            return False
        path = urllib.parse.urlparse(h).path.lower()
        if path.count("/") < 1 or len(path) < 6:
            return False
        if any(k in path for k in ["page/", "/pagina/", "/tag/", "/category/", "/categoria/", "/author/", "/wp-", "/feed", "/cart", "/carrito", "/login", "/cuenta"]):
            return False
        return any(k in path for k in DETAIL_HINTS) or any(m in path for m in MAKES)

    det = []
    for l in stock_links + links:
        if is_detail(l) and norm(l["h"]) not in det and norm(l["h"]) not in [norm(s) for s in stock_cands[:5]]:
            det.append(norm(l["h"]))
    json.dump({"stock_cands": stock_cands, "info_cands": info_cands, "details": det}, open(os.path.join(OUT, "cands.json"), "w"), indent=1)
    for i, u in enumerate(det[: site.get("max_details", 45)]):
        visit(page, u, f"car{i:02d}", shot=(i < 2))
    browser.close()

json.dump(index, open(os.path.join(OUT, "index.json"), "w"), indent=1, ensure_ascii=False)
print("total pages", len(index))
