import glob
import pathlib
import re
from datetime import datetime
from typing import Optional

import fire
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

DATA_DIR = pathlib.Path(__file__).parent.parent.resolve() / "data"

CACHE_DIR = DATA_DIR / "cache"

TODAY = datetime.today()


def _get_cached_html(filename: str) -> Optional[str]:
    filepath = CACHE_DIR / filename
    if filepath.is_file():
        with open(filepath, "r") as fp:
            return fp.read()


def _write_to_cache(filename: str, content: str):
    with open(CACHE_DIR / filename, "w+") as fp:
        fp.write(content)


def clear_cache():
    for name in glob.glob(str(CACHE_DIR / "*.html")):
        pathlib.Path(name).unlink()
    print("🧹 cache cleaned")


def _get_webpage(
    make: str, model: str, post_code: str, page: Optional[str] = None
) -> BeautifulSoup:
    cache_prefix = TODAY.strftime("%Y-%m-%d_%Hh")
    cache_filename = f"{cache_prefix}_{make.lower()}_{model.lower()}_{post_code}_page-{page}.html"

    if html := _get_cached_html(cache_filename):
        return BeautifulSoup(html, "html.parser")
    else:
        headers = {
            "Accept": "text/html",
            "Accept-Language": "en-GB,en;q=0.7",
            "Cache-Control": "no-cache",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
                " AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
            ),
        }

        params = {
            "postcode": post_code,
            "make": make,
            "model": model,
        }
        if page:
            params["page"] = str(page)

        url = "https://www.autotrader.co.uk/car-search"
        r = requests.get(url, headers=headers, params=params)
        if not r.ok:
            raise SystemExit("failed to make the request for the web page")
        _write_to_cache(cache_filename, r.text)
        return BeautifulSoup(r.text, "html.parser")


def scrape(make: str, model: str, post_code: str, pages: Optional[str] = None):
    # page = _get_webpage(make, model, post_code)
    # df = _parse(page)
    # print(df.head())
    page = None
    if pages:
        page_frames = []
        for n in pages:
            page_frames.append(_parse(_get_webpage(make, model, post_code, n)))
        page = pd.concat(page_frames, ignore_index=True)
    else:
        page = _parse(_get_webpage(make, model, post_code))

    filename = f"{TODAY.strftime('%Y-%m-%d')}_{make}_{model}.json"
    page.to_json(DATA_DIR / f"clean/{filename}")

def _parse(page: BeautifulSoup) -> pd.DataFrame:
    """
    Parse a page into a data frame
    """
    items = []

    year_re = re.compile(r"(\d{4})\s\(")
    style_re = re.compile(
        r"(Saloon|Hatchback|Convertible|Coupe|Estate|MPV|SUV)", re.IGNORECASE
    )
    mileage_re = re.compile(r"(\d+,?\d+)\smiles", re.IGNORECASE)
    engine_re = re.compile(r"(\d\.?\d?L)")
    trans_re = re.compile(r"(Manual|Automatic)", re.IGNORECASE)
    fuel_re = re.compile(
        r"(Diesel|Petrol|Electric|Diesel Hybrid|Petrol Hybrid|Petrol Plug-in Hybrid)",
        re.IGNORECASE,
    )

    selector = ".search-page__results ul li.search-page__result"
    for result in page.select(selector):
        content = result.select_one(".product-card-content")
        assert content

        price = content.select_one(".product-card-pricing__price")
        product_title = content.select_one(".product-card-details__title")
        product_subtitle = content.select_one(".product-card-details__subtitle")

        assert price
        assert product_title
        assert product_subtitle

        year = np.nan
        style = pd.NA
        mileage = np.nan
        engine = np.nan
        transmission = pd.NA
        fuel = pd.NA
        for spec in content.select("ul.listing-key-specs li"):
            text = spec.text.strip()
            if m := year_re.match(text):
                year = m.group(1)

            if m := style_re.match(text):
                style = m.group(1)

            if m := mileage_re.match(text):
                mileage = int(m.group(1).replace(",", ""))

            if m := engine_re.match(text):
                engine = float(m.group(1).strip("L"))

            if m := trans_re.match(text):
                transmission = m.group(1)

            if m := fuel_re.match(text):
                fuel = m.group(1)

        items.append(
            {
                "price": price.get_text().strip("\n£").replace(",", ""),
                "title": product_title.get_text().strip(),
                "subtitle": product_subtitle.get_text().strip(),
                "year": year,
                "style": style,
                "mileage": mileage,
                "engine": engine,
                "transmission": transmission,
                "fuel": fuel,
            }
        )

    df = pd.DataFrame(data=items)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df[["make", "model"]] = df["title"].str.split(" ", n=1, expand=True)

    return df


if __name__ == "__main__":
    fire.Fire()
