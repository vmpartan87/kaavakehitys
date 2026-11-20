# Kaavapotentiaali

Etsii Helsingistä, Espoosta ja Vantaalta asemakaavan K- ja T-alueita (liike, toimisto, teollisuus, työpaikat), joilla yleiskaava osoittaa asumista ja joista voisi saada vähintään 2 500 k-m² AK-rakennusoikeutta.

## Tiedostot

- `pipeline.py` laskee ehdokkaat ja pisteet raakadatasta (`raw/*.json`, EPSG:3879) ja kirjoittaa `out/data.json`.
- `vapaat.py` paikantaa Kauppalehti Toimitilojen vapaiden tilojen viennit (`raw/kauppalehti-*.xlsx`) pääkaupunkiseudun osoiteluettelon avulla ja kirjoittaa `raw/vapaat.json`. `pipeline.py` liittää ne tontteihin ("Toimitiloja vuokrattavana").
- `config.json` sisältää yleiskaavamerkintöjen tehokkuusoletukset, vajaakäytön rajat ja pisteytyksen painot. Näitä voi muokata ilman koodia.
- `index.html` on karttaportaali. Se lukee `data.json`-tiedoston samasta kansiosta.

## Julkaisu GitHub Pagesiin

1. Luo GitHubiin uusi repo (esim. `kaavapotentiaali`) ja lisää siihen `index.html` ja `data.json`.
2. Repon asetuksista: Settings → Pages → Source: *Deploy from a branch* → Branch `main`, kansio `/ (root)` → Save.
3. Sivu aukeaa noin minuutin päästä osoitteessa `https://<käyttäjä>.github.io/kaavapotentiaali/`.

Huom: GitHub Pages -sivu on julkinen kaikille, joilla on linkki, ellei käytössä ole GitHub Enterprise -tiliä.
Paikallinen testaus: `python -m http.server` kansiossa ja selaimella `http://localhost:8000`.

## Taustakartat ja kiinteistörajat

| Taso | Lähde | Kattavuus | Avain |
|---|---|---|---|
| Karttasarja harmaa / värillinen | kartta.hel.fi WMS `Karttasarja_PKS_harmaasavy`, `Karttasarja_PKS` | Helsinki, Espoo, Vantaa, Kauniainen | ei |
| Ilmakuva HSY 2023 | kartta.hel.fi WMS `Ortoilmakuva_2023_HSY_5cm` | pääkaupunkiseutu | ei |
| MML taustakartta, MML ilmakuva | avoin-karttakuva.maanmittauslaitos.fi WMTS | koko Suomi | kyllä |
| Kiinteistöjaotus (MML) | MML:n avoimet vektoritiilet `kiinteisto-avoin/styles/v3/kiinteistojaotus_pelkistetty.json` | koko Suomi | kyllä |
| Kiinteistöt, Helsinki | kartta.hel.fi WMS `Kiinteistot` | Helsinki | ei |
| Asemakaava / yleiskaava | kartta.hel.fi WMS `Ajantasa_asemakaava`, `Yleiskaava_2016`; gis.vantaa.fi WMS `asemakaava_varipinta`, `Yleiskaavayhdistelma_11012023` | Helsinki, Vantaa | ei |
| OpenStreetMap | tile.openstreetmap.org | maailma | ei |

**MML:n API-avain:** portaalin tiedostoissa ei ole avainta. Jokainen käyttäjä lisää oman avaimensa portaalin **Asetukset**-ikkunasta. Avain tallentuu vain kyseisen selaimen muistiin (localStorage) ja toimii vain sillä koneella ja selaimella. Ilman avainta MML:n tasot ovat pois käytöstä, muut tasot toimivat. Avaimen saa rekisteröitymällä MML:n Oma tili -palveluun avoimille rajapinnoille.


## Tietolähteet (19.11.2026)

| Kunta | Asemakaava | Yleiskaava | Rakennukset | Vireillä |
|---|---|---|---|---|
| Helsinki | WFS `avoindata:Kaavayksikot` (K, T) | WFS `avoindata:Yleiskaava2016_100m_ruudut` | WFS `avoindata:Rakennukset_piste_rekisteritiedot` | WFS `avoindata:Kaavahakemisto_alue_kaava_vireilla` |
| Espoo | WFS `GIS:Maankayttoalueet` (kartat.espoo.fi/teklaogcweb) | Ei avoimena (401) | WFS `GIS:Rakennukset` | WFS `GIS:Kaavoitushankkeet` |
| Vantaa | WMS `kaava:asemakaava_varipinta` (GeoRSS, käyttötarkoitus tulkittu väristä) | WMS `kaava:Yleiskaavayhdistelma_11012023` (rasteri, tulkittu väristä) | WFS `gis:rakennukset` | WFS `kaava:asemakaavat_vireilla` |

Seutukartta (kuntarajat, meri, väylät, asemat) ja nimistö: kartta.hel.fi `avoindata:Seutukartta_*`.

## Tunnetut rajoitteet

- Espoon yleiskaava ei ole avoimena datana: Espoon kohteet on laskettu oletustehokkuudella 1,0.
- Vantaan asemakaavan käyttötarkoitus ja yleiskaavamerkinnät on tulkittu karttavärien perusteella.
- Helsingin yleiskaava on saatavilla vain 100 m ruutuina.
- Maanomistus puuttuu (Espoon omistajataso vaatii tunnukset).

## Seuraava vaihe (GitHub)

1. Kirjoita haku Python-moduuleiksi (`adapters/helsinki.py`, `espoo.py`, `vantaa.py`). Selaimessa käytetyt kyselyt on listattu yllä.
2. GitHub Actions ajaa haun ja `pipeline.py`:n kuukausittain ja julkaisee `index.html` + `data.json` GitHub Pagesiin.
