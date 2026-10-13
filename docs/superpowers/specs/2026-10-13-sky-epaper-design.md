# Sky – noční obloha pro e-paper: design

**Datum:** 2026-10-13
**Cíl:** Malá HTTP služba, která podle GPS souřadnic a směru vykreslí aktuální
oblohu (souhvězdí, planety, Slunce, Měsíc, ISS) s infopanelem (východy a západy,
nejbližší přelet ISS, kalendář úkazů z jantichy.cz) jako obrázek pro e-paper
displeje. Primárně pro Živý obraz (obrázek z URL), ale výstup je obecný:
PNG/BMP, palety BW/BWR/BWRY, libovolný rozměr na šířku i výšku.

---

## 1. Rozsah

Dělá se:

1. HTTP služba (FastAPI) s parametry v URL, výstup `.png` / `.bmp`.
2. Dvě projekce: `sky` (celá obloha, kruh, zenit uprostřed) a `horizon`
   (pohled z okna daným azimutem).
3. Noční a denní režim přepínaný podle polohy Slunce (pod/nad obzorem).
4. Infopanel: datum a čas, Slunce, Měsíc, ISS, úkazy.
5. CLI pro vykreslení bez serveru.
6. Docker image pro Coolify.

Nedělá se (viz §12): Mléčná dráha, deep-sky objekty, dithering, jiné satelity,
popisy úkazů, počasí, HTTPS (řeší reverzní proxy Coolify).

---

## 2. Technologie

| složka | volba | důvod |
|---|---|---|
| jazyk | Python 3.12+ | existující nástroje ve `firmware/tools/` jsou Python/Pillow |
| astronomie | Skyfield (+ vestavěný SGP4) | jedna knihovna na hvězdy, planety, východy/západy, fáze i ISS |
| efemerida | `de421.bsp` (~17 MB, stažena do cache) | pokrývá 1900–2050, Merkur–Saturn, Slunce, Měsíc |
| web | FastAPI + uvicorn | jednoduché, validace parametrů, zná se z makerclass editoru |
| kreslení | Pillow, obraz v režimu `P` s paletou | indexované barvy 1:1 s panelem, bez vyhlazování |
| fonty | Spleen BDF 8×16, 12×24, 16×32 (BSD) | stejné jako skolao, ostré na e-paperu |
| kalendář | `icalendar` + `recurring-ical-events` | ICS má RRULE a RECURRENCE-ID |
| časová zóna | `timezonefinder` + `zoneinfo` | zóna z GPS, bez konfigurace |
| data oblohy | d3-celestial `data/` (BSD-3) | čáry souhvězdí s inline RA/Dec, české názvy, hvězdy s magnitudou |
| testy | pytest | |

Repo `sky/` je samostatný git repozitář (jako `firmware/` a `skolao`), práce
rovnou na `main`.

---

## 3. Rozhraní

### 3.1 HTTP

```
GET /sky.png?lat=49.747&lon=13.378&az=180&view=sky&w=800&h=480&colors=bw
GET /sky.bmp?lat=49.747&lon=13.378&view=horizon&az=200&fov=120&colors=bwry&w=480&h=800
GET /health
```

| parametr | typ, rozsah | význam | výchozí |
|---|---|---|---|
| `lat` | float −90..90 | zeměpisná šířka WGS84 | env `SKY_LAT`, jinak 400 |
| `lon` | float −180..180 | zeměpisná délka | env `SKY_LON`, jinak 400 |
| `view` | `sky` \| `horizon` | projekce | `sky` |
| `az` | float 0..360 | `sky`: azimut dole (před pozorovatelem); `horizon`: střed pohledu | `180` |
| `fov` | float 30..180 | jen `horizon`: šířka zorného pole ve stupních | `120` |
| `w`, `h` | int 64..2000 | rozměr výstupu v px | `800`, `480` |
| `colors` | `bw` \| `bwr` \| `bwry` | paleta | `bw` |
| `rot` | `0` \| `90` \| `180` \| `270` | otočení hotového obrázku po směru hodin | `0` |
| `t` | ISO 8601 (s offsetem nebo bez = UTC) | čas vykreslení (testy, náhledy) | teď |
| `iss` | `0` \| `1` | sekce ISS | `1` |
| `events` | `0` \| `1` | sekce úkazů | `1` |
| `lang` | `cs` \| `en` | názvy souhvězdí a texty | `cs` |
| `token` | string | povinný, pokud je nastaven env `SKY_TOKEN` | – |

- Přípona volí formát. `.png`: indexované PNG s paletou přesně v barvách palety
  (§7). `.bmp`: `bw` → 1 bit/px, `bwr`/`bwry` → 8 bit/px indexované
  (Pillow režim `P` zapisuje 8 bpp; paleta v hlavičce má jen 3–4 barvy),
  bez komprese.
- `w`×`h` určuje orientaci; `rot` se použije až na hotový obrázek (pro
  firmwary s pevnou orientací framebufferu).
- Nevalidní parametr → HTTP 400 s textovým popisem. Chybějící/špatný token →
  HTTP 403.
- Odpověď nese `Cache-Control: no-store` (Živý obraz si cache řídí sám) a
  hlavičku `X-Sky-Mode: night|day`.

### 3.2 CLI

```
python -m sky render --lat 49.747 --lon 13.378 [--view sky|horizon] [--az 180]
                     [--fov 120] [--w 800] [--h 480] [--colors bw] [--rot 0]
                     [--t 2026-10-13T22:00+02:00] [--no-iss] [--no-events]
                     [--lang cs] --out out.png|out.bmp
python -m sky serve [--host 0.0.0.0] [--port 8080]
```

Stejná validace jako HTTP (společná funkce `params.parse(dict) -> Params`).

### 3.3 Konfigurace (env)

| proměnná | význam | výchozí |
|---|---|---|
| `SKY_CACHE_DIR` | adresář cache (efemerida, TLE, ICS) | `./cache` |
| `SKY_LAT`, `SKY_LON` | výchozí stanoviště | – |
| `SKY_TOKEN` | když nastaveno, vyžaduje se `?token=` | – |
| `SKY_EVENTS_URL` | ICS feed úkazů | jantichy.cz Google kalendář (§6.3) |
| `SKY_TLE_URL` | zdroj TLE | `https://celestrak.org/NORAD/elements/gp.php?CATNR=25544&FORMAT=tle` |
| `SKY_RENDER_CACHE_S` | TTL paměťové cache hotových obrázků | `300` |

---

## 4. Režimy a čas

- Čas vykreslení `t` = teď (UTC) nebo parametr. Místní zóna se odvodí z GPS;
  všechny časy na panelu jsou místní, formát `HH:MM`, datum `út 13. 10.`.
- **Režim** se určí z výšky Slunce v čase `t`: střed Slunce pod obzorem
  (výška < −0,833°, tj. standardní refrakce + poloměr) → `night`, jinak `day`.
- `night`: pozadí černé, hvězdy, čáry a texty bílé.
  `day`: pozadí bílé, čáry a texty černé. Obsah mapy je v obou režimech stejný
  (souhvězdí, planety, Měsíc nad obzorem), v `day` navíc symbol Slunce.
- Infopanel v `day` ukazuje „Noc od HH:MM“ (dnešní západ), v `night`
  „Svítá v HH:MM“ (příští východ).

---

## 5. Obsah mapy

### 5.1 Objekty

| objekt | zdroj | kreslení |
|---|---|---|
| hvězdy do mag 4,5 | `stars.6.json` (RA/Dec J2000, mag) | tečka: mag ≤ 1 → 5 px kruh, ≤ 2 → 4 px, ≤ 3 → 3 px, ≤ 4,5 → 1–2 px |
| čáry souhvězdí | `constellations.lines.json` (MultiLineString, lon −180..180 = RA·15 přepočtené, lat = Dec) | 1 px čáry, oříznuté na obzor |
| názvy souhvězdí | `constellations.json` (`cz`/`en`, střed `geometry`) | font 8×16, jen souhvězdí s rank 1–2 a středem ≥ 10° nad obzorem; při kolizi popisků vynechat |
| planety Merkur–Saturn | Skyfield de421 | symbol: kruh 7 px s výplní + popisek jména (font 8×16); v `bwr`/`bwry` červeně |
| Měsíc | Skyfield | kotouč 16 px s vykreslenou fází (osvětlená část světlá/žlutá, tmavá část pozadí s 1px obrysem) |
| Slunce (jen `day`) | Skyfield | kruh 14 px s paprsky, v `bwry` žlutě, v `bwr` červeně |
| ISS (je-li nad obzorem v `t`) | SGP4 | křížek 9 px + „ISS“ |
| obzor, světové strany | – | kružnice/čára, popisky S V J Z (en: N E S W) font 12×24 |

Výšky a azimuty se počítají s refrakcí (`apparent().altaz(temperature_C=10, pressure_mbar=1010)`)
pro Slunce, Měsíc, planety; hvězdy bez refrakce (rozdíl pod 1 px kromě obzoru).

### 5.2 Projekce `sky`

Azimutální ekvidistantní: `r = (90 − alt) / 90 · R`, úhel = `az − az_param`
(azimut `az_param` míří dolů, sever vlevo nebo vpravo podle otočení tak, aby
východ byl vlevo, když je jih dole – stejně jako na otočné mapě držené nad
hlavou). Kreslí se jen objekty s `alt ≥ 0`; čáry se ořežou na obzorové kružnici
(lineární interpolace k alt = 0). Mapa je čtverec `s×s`, `R = s/2 − okraj`.

### 5.3 Projekce `horizon`

Rovnoběžná (ekvirektangulární) azimut × výška:
`x = (Δaz / fov + 0,5) · W_map`, `y = H_map − alt / alt_max · H_map`,
kde `Δaz` je rozdíl od `az_param` normalizovaný do −180..180 a
`alt_max = fov · H_map / W_map` (stejné měřítko ve stupních na obou osách;
při 800×300 a fov 120 je `alt_max = 45°`). Objekty mimo ořez se nekreslí,
čáry se ořežou obdélníkem (Liang–Barsky). Dole čára obzoru s popisky
světových stran u azimutů dělitelných 45°, které spadají do pole.

### 5.4 Rozložení (layout)

Vstup `(w, h, view)`, výstup zóny v px. Jednotka `u` = výška řádku fontu 8×16
(16 px), okraj 8 px.

| případ | mapa | infopanel |
|---|---|---|
| `sky`, na šířku (w ≥ h) | čtverec `h×h` vlevo | sloupec vpravo šířky `w − h`; je-li užší než 14 znaků (112 px), infopanel se vynechá |
| `sky`, na výšku (w < h) | čtverec `w×w` nahoře | pás dole výšky `h − w`; je-li nižší než 6 u, vynechá se |
| `horizon`, na šířku | pás nahoře výšky `max(h·0,6, h − 12 u)` přes celou šířku | 3 sloupce dole (Slunce+Měsíc, ISS, úkazy) |
| `horizon`, na výšku | pás nahoře výšky `w·0,6` | sloupec dole, sekce pod sebou |

Infopanel sekce v pořadí: hlavička (datum, čas, lat/lon), Slunce, Měsíc, ISS,
Úkazy. Každá sekce = ikona 16×16 + titulek (font 8×16 tučně = inverzně
nevykreslujeme, jen podtržení 1 px) + řádky. Co se nevejde na výšku, odpadne
odspodu (úkazy jako poslední sekce se zkrátí na kolik řádků zbývá). Text delší
než šířka sloupce se ořízne s „…“.

Při výšce panelu ≥ 2× výšky fontu 16×32 pro hlavičku (tj. standardní 800×480
a 480×800) se hlavička kreslí fontem 16×32, jinak 8×16.

---

## 6. Datové zdroje a cache

### 6.1 Efemerida a hvězdy

- `de421.bsp` se stáhne při prvním použití do `SKY_CACHE_DIR` (Skyfield
  `Loader`). V Dockerfile je stažení součástí buildu, aby start byl rychlý.
- Hvězdy a souhvězdí jsou soubory v `sky/data/` v repu (BSD-3, soubor
  `LICENSE-d3-celestial`). Načtou se jednou při startu procesu, hvězdy se
  předfiltrují na mag ≤ 4,5 a připraví jako jeden vektorový `Star` objekt
  Skyfieldu (jeden výpočet alt/az pro všechny hvězdy).

### 6.2 ISS

- TLE ze `SKY_TLE_URL`, uloženo v `cache/iss.tle` s časem stažení; obnova,
  když je starší než 24 h. Při selhání stažení se použije stará cache bez
  omezení stáří; bez cache sekce ISS zobrazí „nedostupné“.
- Nejbližší viditelný přelet: `EarthSatellite.find_events(topos, t, t+48 h,
  altitude_degrees=10)`; přelet je viditelný, když v kulminaci je ISS
  osvětlená (`is_sunlit`) a Slunce je pod −6° (občanský soumrak). Zobrazí se
  první takový: `st 14. 10. 19:42–19:48, max 61° J` (začátek nad 10°, konec
  pod 10°, max výška, azimut kulminace jako světová strana).
- Aktuální poloha pro mapu: `satellite.at(t)` vůči topos; kreslí se, je-li
  `alt > 0`.

### 6.3 Úkazy

- ICS z `SKY_EVENTS_URL`, výchozí
  `https://calendar.google.com/calendar/ical/c_f45884b2c6eaf4644407e4587ff09bc7205bb9b47cb965f5566c02083578eecb%40group.calendar.google.com/public/basic.ics`,
  cache `cache/events.ics`, obnova po 24 h, stejná politika selhání jako TLE.
- Parsování: `icalendar` + `recurring-ical-events.of(cal).between(dnes, dnes+60 d)`;
  všechny události jsou celodenní. Z `SUMMARY` se odstraní úvodní emoji a
  převede na typ:

  | emoji | typ | ikona |
  |---|---|---|
  | 👁️ | `eye` | oko |
  | 🔭 | `scope` | dalekohled |
  | ⚠️ | `warn` | trojúhelník s vykřičníkem |
  | 🌑 🌒 🌓 🌔 🌕 🌖 🌗 🌘 | `moon` | fáze |
  | ⛒ | `none` | – (výchozí filtr vynechá) |
  | ℹ️ | `info` | – (výchozí filtr vynechá) |

  Konfigurace filtru env `SKY_EVENT_TYPES` (výchozí `eye,scope,warn,moon`).
- Zobrazení: dalších N událostí od dneška (včetně), formát `14. 10.  Tauridy`;
  dnešní v `bwr`/`bwry` červeně, v `bw` s rámečkem. Popisy se nezobrazují.
- V README uvést zdroj (Jan Tichý, jantichy.cz/ukazy); licence není uvedena,
  použití jen pro soukromé displeje.

### 6.4 Cache hotových obrázků

V paměti procesu, klíč = všechny parametry + `t` zaokrouhlené na 5 min,
TTL `SKY_RENDER_CACHE_S`. Chrání před Živým obrazem, který se při chybě ptá
opakovaně.

---

## 7. Palety a formát výstupu

Obrázek se kreslí v režimu `P` s rolemi barev; modul `palette` mapuje role na
index a paleta se zapíše do PNG/BMP.

| index | `bw` | `bwr` | `bwry` |
|---|---|---|---|
| 0 | bílá `#FFFFFF` | bílá | bílá |
| 1 | černá `#000000` | černá | černá |
| 2 | – | červená `#FF0000` | červená `#FF0000` |
| 3 | – | – | žlutá `#FFFF00` |

Role (`bg`, `fg`, `star`, `line`, `label`, `planet`, `sun`, `moon_lit`,
`moon_dark`, `iss`, `today`, `horizon`):

- `bw`: night `bg=1, fg=0`, day `bg=0, fg=1`; všechny role = `fg` kromě `bg`.
- `bwr`: jako `bw`, navíc `planet, sun, iss, today = 2`.
- `bwry`: jako `bwr`, navíc `sun, moon_lit = 3` (Slunce žluté, planety červené).

PNG: `Image.save(format="PNG", optimize=True)`, bity na pixel podle počtu
barev (1 bit pro `bw`, 2 bity pro ostatní – Pillow volí automaticky podle
délky palety). BMP: pro `bw` převést na režim `1` (1 bpp), pro ostatní
ponechat `P` (Pillow zapíše 8 bpp; firmware si načte paletu z hlavičky). Rotace `rot` před enkódováním (`Image.rotate(-rot, expand=True)`).

---

## 8. Architektura

```
sky/
  sky/
    __init__.py
    __main__.py      # `python -m sky` → cli.main()
    params.py        # Params dataclass, parse(dict) s validací (sdílí HTTP i CLI)
    config.py        # env proměnné
    geo.py           # časová zóna z GPS (timezonefinder), formátování datumů/časů cs/en
    astro.py         # Skyfield: SkyModel(t, lat, lon) → objekty s alt/az; Slunce/Měsíc časy; fáze; režim
    iss.py           # TLE cache, aktuální poloha, nejbližší viditelný přelet
    events.py        # ICS cache, parse, filtr, dalších N
    projection.py    # čisté: altaz → xy pro sky/horizon, ořez čar
    layout.py        # čisté: (w,h,view) → Zones
    palette.py       # role → index, paleta pro PNG/BMP
    fonts.py         # Spleen BDF → ImageFont (cache); text width; ořez s „…“
    icons.py         # 16×16 pixelové ikony (slunce, měsíc, iss, oko, dalekohled, varování)
    render.py        # Pillow: draw_map(), draw_info(); vstup = SkyModel + IssInfo + Events + Zones
    output.py        # encode(image, fmt, rot) → bytes, mime
    app.py           # FastAPI, cache odpovědí, token
    cli.py           # argparse: render / serve
    data/            # constellations.lines.json, constellations.json, stars.6.json, LICENSE-d3-celestial
    fonts/           # spleen-8x16.bdf, spleen-12x24.bdf, spleen-16x32.bdf, LICENSE
  tests/
  docs/superpowers/specs/, docs/superpowers/plans/
  Dockerfile, pyproject.toml, README.md, .gitignore (cache/, *.pil, __pycache__)
```

Tok požadavku:

```
app/cli → params.parse → astro.compute(params) ─┐
                         iss.info(params)       ├→ render.draw(model, zones, palette) → output.encode → bytes
                         events.upcoming(params)┘
```

Zásady:

- `projection`, `layout`, `palette`, `params`, `events.parse` jsou čisté
  funkce bez IO, testované jednotkově.
- `render` nezná síť ani čas „teď“; dostává hotové struktury
  (`SkyModel`, `IssInfo | None`, `list[Event]`, `Zones`, `Palette`).
- Síťové moduly (`iss`, `events`, efemerida) mají jediný vstupní bod s
  diskovou cache a politikou „stará cache lépe než nic“.
- Vektorové výpočty (hvězdy) přes Skyfield `Star` s poli RA/Dec; cíl je
  vykreslení 800×480 pod 1 s na běžném serveru (po prvním načtení).

---

## 9. Chyby a okraje

| situace | chování |
|---|---|
| Celestrak/ICS nedostupné, cache existuje | použije se stará cache, do logu varování |
| nedostupné, cache neexistuje | sekce vykreslí „ISS: nedostupné“ / „Úkazy: nedostupné“, HTTP 200 |
| Slunce bez východu/západu (polární) | časy „–“; režim podle aktuální výšky |
| Měsíc bez východu nebo západu v daný den | odpovídající čas „–“ |
| ISS bez viditelného přeletu do 48 h | „žádný do 48 h“ |
| `lat`/`lon` chybí a env také | HTTP 400 |
| `w`/`h` mimo 64..2000, `fov` mimo 30..180 | HTTP 400 |
| infopanel příliš úzký/nízký (§5.4) | vynechá se, kreslí se jen mapa |
| efemerida nejde stáhnout při startu | služba vrátí 503 na `/sky.*`, `/health` hlásí `ephemeris: missing` |

Logování: standardní `logging`, INFO pro požadavky (parametry, dobu
vykreslení, režim), WARNING pro cache fallbacky.

---

## 10. Testy

- `tests/test_projection.py`: zenit → střed; `alt=0, az=az_param` → bod dole na
  kružnici; `horizon`: střed pohledu dole uprostřed, `alt_max` nahoře; ořez
  úsečky přes obzor a přes okraj obdélníku.
- `tests/test_layout.py`: zóny pro 800×480, 480×800, 800×300, 296×128 (malý
  panel → bez infopanelu), obě projekce.
- `tests/test_params.py`: výchozí hodnoty, env fallback, chybové případy,
  parsování `t`.
- `tests/test_events.py`: uložený vzorek ICS (`tests/data/events_sample.ics`,
  ~20 událostí včetně Tauridy s RRULE+RECURRENCE-ID a HTML v popisu) →
  správné typy, filtr, pořadí, dnešní.
- `tests/test_palette_output.py`: paleta pro každé `colors`, PNG má správný
  počet barev, BMP `bw` je 1 bpp, rotace mění rozměr.
- `tests/test_astro.py` (vyžaduje efemeridu v cache, označeno `@pytest.mark.ephem`):
  Plzeň 2026-10-13 00:00 UTC: Slunce pod obzorem, režim `night`; Polárka
  alt ≈ 49,7 ± 1°, az ≈ 0 ± 1°; západ Slunce 13. 10. 2026 v Plzni mezi 18:10
  a 18:30 místního času.
- `tests/test_render.py`: vykreslení 800×480 a 480×800 s pevným modelem
  (bez sítě, falešné `IssInfo` a události) proběhne bez výjimky, rozměry a
  režim sedí, v `bw` jen 2 barvy.
- Ruční: `python -m sky render` pro 6 kombinací (sky/horizon × bw/bwr/bwry,
  oba rozměry) a prohlédnout PNG; poté nasazení do Coolify a zapojení do
  Živého obrazu.

---

## 11. Nasazení

`Dockerfile`: `python:3.12-slim`, `pip install .`, při buildu
`python -m sky warmup` (stáhne `de421.bsp` do `/app/cache-seed` a zkopíruje do
`SKY_CACHE_DIR` při startu, pokud chybí), `CMD uvicorn sky.app:app --host
0.0.0.0 --port 8080`. Persistent volume `/cache` → `SKY_CACHE_DIR`.
Env: `SKY_TOKEN`, volitelně `SKY_LAT`/`SKY_LON`. Veřejná doména přes Coolify,
Živý obraz dostane URL včetně parametrů a tokenu.

---

## 12. Mimo rozsah

Mléčná dráha, deep-sky objekty, asterismy, jiné satelity než ISS, popisy
úkazů, předpověď počasí/oblačnosti, dithering obrázků, HTTPS v aplikaci,
vlastní uživatelské účty, Z2/pbin výstup (přidat lze v `output.py`, formát je
popsaný ve `firmware/docs/`).
