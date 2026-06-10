# Fishingshop Pike Scraper

Python scraper за продукти от [fishingshop-pike.com](https://fishingshop-pike.com/).

Скриптът може да:

- обхожда конкретна категория;
- открива категории от началната страница;
- събира продуктови URL-и от категорийни страници;
- извлича продуктов ID от URL-а, име, категория, описание, URL, цена, тегло и наличност;
- извлича **всички URL-и на изображенията** от продуктовата страница;
- записва всяка информация в отделна CSV колона;
- записва изображенията в отделни CSV колони: `image_1`, `image_2`, `image_3`, ...
- записва резултатите и в JSONL, където изображенията са в списък `image_urls`.

> Използвай скрейпъра отговорно: сложи delay между заявките и не претоварвай сайта.

## Инсталация

```bash
python -m venv .venv
```

### Windows

```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

### macOS / Linux

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Бърз старт

Скрейпване на една категория:

```bash
python main.py --start https://fishingshop-pike.com/category/383/prati.html --max-pages 3
```

Автоматично откриване на категории от началната страница:

```bash
python main.py --discover-categories --max-pages 2 --delay 1.5
```

Скрейпване на конкретен продукт:

```bash
python main.py --start https://fishingshop-pike.com/product/17529/sharanski-montazh-mistrall-in-line-carp-set-70-gr-kuka-4.html
```

## Изходни файлове

По подразбиране се създават:

```text
fishingshop_pike_products.csv
fishingshop_pike_products.jsonl
```

Може да зададеш собствени имена:

```bash
python main.py \
  --start https://fishingshop-pike.com/category/383/prati.html \
  --csv products.csv \
  --jsonl products.jsonl
```

## Полета в CSV експорта

| Колона | Описание |
|---|---|
| `product_number` | Продуктов ID от URL-а, например `/product/17529/...` → `17529` |
| `product_name` | Име на продукта |
| `category` | Категория/категориен път |
| `description` | Описание |
| `product_url` | URL на продукта |
| `price_eur` | Цена в EUR |
| `price_bgn` | Цена в BGN/лв. |
| `weight` | Тегло на продукта, когато е налично/разпознаваемо |
| `availability` | Дали е наличен |
| `image_1` | Първи URL на изображение |
| `image_2` | Втори URL на изображение |
| `image_3` ... | Следващи изображения, автоматично добавени според продукта с най-много снимки |

CSV файлът се записва с `utf-8-sig`, за да се отваря по-лесно в Excel.

## JSONL формат

В JSONL файла изображенията са в една структура като списък:

```json
{
  "product_number": "17529",
  "product_name": "Шарански монтаж Mistrall In-Line Carp Set 70 гр,Кука №4",
  "category": "Монтажи за риболов",
  "description": "...",
  "product_url": "https://fishingshop-pike.com/product/...html",
  "price_eur": "5.11",
  "price_bgn": "9.99",
  "weight": "70 гр",
  "availability": "В наличност",
  "image_urls": [
    "https://fishingshop-pike.com/userfiles/productlargeimages/product_29646.jpg",
    "https://fishingshop-pike.com/userfiles/productlargeimages/product_29647.jpg"
  ]
}
```

## Аргументи

```text
--start                 Един или повече URL-и: категория или продукт
--discover-categories   Открива категории от началната страница
--max-pages             Максимален брой страници за всяка категория
--delay                 Пауза между заявките в секунди
--csv                   Име на CSV файла
--jsonl                 Име на JSONL файла
```


## GitHub Actions — генериране на CSV за Excel

Workflow-ът е настроен да се стартира ръчно от **Actions → Run scraper → Run workflow**.
След успешен run CSV файлът се сваля от **Artifacts**.

По подразбиране командата за пълно обхождане е:

```bash
python main.py --discover-categories --max-pages 100 --delay 1.2
```

За кратък тест можеш временно да я смениш с:

```bash
python main.py --start https://fishingshop-pike.com/category/383/prati.html --max-pages 1 --delay 1.5
```

## Качване в GitHub

1. Създай ново repository в GitHub.
2. Разархивирай този проект в папка на компютъра си.
3. Отвори Terminal / CMD в папката.
4. Изпълни:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/fishingshop-pike-scraper.git
git push -u origin main
```

Замени `YOUR-USERNAME` с твоя GitHub username.

## Бележки

- Ако искаш всички продукти, увеличи `--max-pages` или го пусни с достатъчно голяма стойност.
- Ако сайтът промени HTML структурата си, може да се наложат малки промени в CSS селекторите/regex правилата.
- Проектът е предназначен за образователна и вътрешна употреба.
