# Sky – aktuální obloha pro e-paper

Malá HTTP služba (a CLI), která podle GPS souřadnic a směru vykreslí **aktuální
oblohu** – souhvězdí, planety, Slunce, Měsíc s fází a ISS – a vedle ní infopanel
s východy a západy, nejbližším viditelným přeletem ISS a kalendářem úkazů.
Výstup je **PNG nebo BMP** v paletě **BW / BWR / BWRY**, libovolný rozměr na šířku
i na výšku, bez vyhlazování – přímo pro e-paper (Živý obraz, Paperboard, …).

Přes den (Slunce nad obzorem) se kreslí světlý režim: bílé pozadí, černé čáry,
Slunce, Měsíc a planety, které jsou právě nad obzorem. V noci tmavý režim.

![ukázka](docs/example-sky.png)

## Rychlý start

```bash
pip install .                       # nebo pip install -e .[dev] pro vývoj
python -m sky warmup                # stáhne efemeridu de421.bsp (~17 MB) do ./cache
python -m sky render --lat 49.747 --lon 13.378 --out obloha.png
python -m sky serve --port 8080     # http://127.0.0.1:8080/sky.png?lat=49.747&lon=13.378
```

## HTTP rozhraní

```
GET /sky.png?lat=49.747&lon=13.378&az=180&view=sky&w=800&h=480&colors=bw
GET /sky.bmp?lat=49.747&lon=13.378&view=horizon&az=200&fov=120&colors=bwry&w=480&h=800
GET /health
```

| parametr | hodnoty | význam | výchozí |
|---|---|---|---|
| `lat`, `lon` | −90..90, −180..180 | stanoviště (WGS84) | env `SKY_LAT`/`SKY_LON`, jinak povinné |
| `view` | `sky` \| `horizon` | celá obloha (kruh, zenit uprostřed) nebo pohled z okna | `sky` |
| `az` | 0..360 | `sky`: azimut dole (co máte před sebou); `horizon`: střed pohledu | `180` (jih) |
| `fov` | 30..180 | jen `horizon`: šířka zorného pole ve stupních | `120` |
| `w`, `h` | 64..2000 | rozměr v px; poměr stran určuje rozložení | `800`, `480` |
| `colors` | `bw` \| `bwr` \| `bwry` | paleta (červeně planety, ISS, dnešní úkaz; žlutě Slunce a Měsíc) | `bw` |
| `rot` | 0 \| 90 \| 180 \| 270 | otočení hotového obrázku po směru hodin | `0` |
| `t` | ISO 8601 | čas vykreslení (náhledy, testy); bez zóny = UTC | teď |
| `iss`, `events` | 0 \| 1 | vypnutí sekce ISS / úkazů | `1` |
| `lang` | `cs` \| `en` | jazyk popisků a textů | `cs` |
| `token` | | povinný, když je nastaven `SKY_TOKEN` | – |

Přípona určuje formát: `.png` je indexované PNG s paletou v barvách panelu
(1 bit pro `bw`, 2 bity jinak), `.bmp` je 1 bpp pro `bw` a 8 bpp indexované pro
`bwr`/`bwry`. Odpověď nese hlavičku `X-Sky-Mode: night|day`. Chybné parametry
vrací 400 s popisem, špatný token 403, chybějící efemerida 503.

Hotové obrázky se cachují v paměti 5 minut (`SKY_RENDER_CACHE_S`); TLE a ICS se
stahují nejvýš jednou za den a při výpadku sítě se použije poslední stažená
verze. Vykreslení trvá zhruba 0,6 s.

## CLI

```bash
python -m sky render --lat 49.747 --lon 13.378 [--view sky|horizon] [--az 180] [--fov 120]
                     [--w 800] [--h 480] [--colors bw|bwr|bwry] [--rot 0] [--t 2026-10-13T22:00+02:00]
                     [--no-iss] [--no-events] [--lang cs|en] --out obloha.png|obloha.bmp
python -m sky serve [--host 127.0.0.1] [--port 8080]
python -m sky warmup
```

## Konfigurace (env)

| proměnná | význam | výchozí |
|---|---|---|
| `SKY_CACHE_DIR` | adresář pro efemeridu, TLE a ICS | `./cache` |
| `SKY_LAT`, `SKY_LON` | výchozí stanoviště | – |
| `SKY_TOKEN` | když je nastaven, vyžaduje se `?token=` | – |
| `SKY_EVENTS_URL` | ICS kalendář úkazů | sdílený kalendář Jana Tichého |
| `SKY_TLE_URL` | zdroj TLE pro ISS | Celestrak, NORAD 25544 |
| `SKY_RENDER_CACHE_S` | TTL cache hotových obrázků v sekundách | `300` |
| `SKY_EVENT_TYPES` | typy úkazů k zobrazení: `eye,scope,warn,moon,none,info` | `eye,scope,warn,moon` |

## Nasazení v Coolify

1. Nový zdroj typu **Dockerfile** (repozitář nebo vložený obsah `Dockerfile`).
2. **Persistent Storage**: volume → `/cache` (efemerida, TLE, ICS přežijí redeploy).
3. **Port**: `8080`.
4. **Environment Variables**: `SKY_TOKEN` (`php -r "echo bin2hex(random_bytes(16));"`),
   volitelně `SKY_LAT`, `SKY_LON`.
5. Health check: `GET /health` → `{"status": "ok", "ephemeris": "ok"}`.

Lokálně:

```bash
docker build -t sky-epaper .
docker run --rm -p 8080:8080 -e SKY_TOKEN=tajne sky-epaper
curl "http://localhost:8080/sky.png?lat=49.747&lon=13.378&token=tajne" -o obloha.png
```

## Zapojení do Živého obrazu

V administraci Živého obrazu nastavte zdroj **obrázek z URL** a zadejte adresu
služby včetně parametrů pro svůj panel, např.

```
https://sky.vase-domena.cz/sky.png?lat=49.747&lon=13.378&az=200&w=800&h=480&colors=bw&token=…
```

Server Živého obrazu musí na službu dosáhnout z internetu. Pro BWR/BWRY panely
použijte odpovídající `colors`; obrázek je už v barvách panelu, dithering není
potřeba. Paperboard firmware (`[remote_image]`) umí stejné PNG z LAN.

## Co je na obrázku

- **Mapa**: hvězdy do 4,5 mag (velikost podle jasnosti), čáry a názvy souhvězdí,
  Merkur až Saturn, Měsíc s vykreslenou fází, přes den Slunce, ISS je-li nad
  obzorem. `sky` je azimutální mapa (obzor = kružnice, světové strany kolem),
  `horizon` je panorama azimut × výška s obzorem dole.
- **Infopanel**: datum a čas, Slunce (východ, západ, kdy začíná noc / svítá),
  Měsíc (východ, západ, fáze), ISS (nejbližší viditelný přelet do 48 h: nad 10°,
  osvětlená, za občanského soumraku), úkazy (dalších 12 z kalendáře, dnešní
  zvýrazněný). Rozložení se přizpůsobí rozměru; na malé panely jde jen mapa.

## Zdroje dat a licence

- Hvězdy, čáry a názvy souhvězdí: [d3-celestial](https://github.com/ofrohn/d3-celestial)
  (BSD-3, `sky/data/LICENSE-d3-celestial`); hvězdy z katalogu XHIP, čáry podle IAU.
- Efemerida JPL DE421 a výpočty: [Skyfield](https://rhodesmill.org/skyfield/) (MIT).
- Dráha ISS: TLE z [Celestrak](https://celestrak.org/).
- Kalendář úkazů: sdílený český kalendář nebeských úkazů Jana Tichého,
  [jantichy.cz/ukazy](https://www.jantichy.cz/ukazy). Licence není uvedena;
  určeno pro soukromé displeje, při zveřejnění uveďte zdroj.
- Fonty: [Spleen](https://github.com/fcambus/spleen) (BSD-2, `sky/fonts/LICENSE`).

## Vývoj

```bash
pip install -e .[dev]
python -m sky warmup            # testy označené `ephem` potřebují de421.bsp v ./cache
python -m pytest -q
```

Architektura: čisté moduly (`params`, `palette`, `projection`, `layout`, `fonts`,
`icons`, `geo`, `catalog`, `events`) bez IO; `astro` (Skyfield), `iss` a
`events` se síťovou cache (`netcache`); `render` kreslí do Pillow obrazu
v režimu `P`; `output` kóduje PNG/BMP; `service` skládá pipeline s cache;
`app` (FastAPI) a `cli` jsou tenké obálky. Návrh je v
`docs/superpowers/specs/2026-10-13-sky-epaper-design.md`.
