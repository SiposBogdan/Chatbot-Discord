#!/usr/bin/env python3
import os
import re
import asyncio
import shlex
from collections import defaultdict

import requests
import random
from urllib.parse import urljoin
from datetime import datetime, timezone


import discord
from discord.ext import commands, tasks

from sqlalchemy import (
    create_engine, Column, Integer, Float, String,
    DateTime, ForeignKey, func, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship


DB_USER = os.getenv("DB_USER", "tracker")
DB_PASS = os.getenv("DB_PASS", "secret_password")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "book_tracker")

engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}/{DB_NAME}"
    "?charset=utf8mb4",
    future=True, echo=False
)
Session = sessionmaker(bind=engine, future=True)
Base    = declarative_base()

class Book(Base):
    __tablename__ = 'books'
    id            = Column(Integer, primary_key=True)
    url           = Column(String(512), unique=True, nullable=False)
    title         = Column(String(256), nullable=False)
    genre         = Column(String(64),  nullable=True)
    availability  = Column(String(64),  nullable=True)
    rating        = Column(String(16),  nullable=True)
    last_price    = Column(Float,       nullable=False)
    prev_price    = Column(Float,       nullable=True)
    price_change  = Column(Float,       nullable=True)
    last_checked  = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    history = relationship(
        "PriceHistory", back_populates="book",
        cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint('url', name='_url_uc'),)

class PriceHistory(Base):
    __tablename__ = 'price_history'
    id = Column(Integer, primary_key=True)
    book_id = Column(Integer, ForeignKey('books.id'), index=True)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    book = relationship("Book", back_populates="history")

Base.metadata.create_all(engine)

HEADERS = {"User-Agent": "BookTrackerBot/1.0"}

def scrape_books(max_pages: int = 50):
    all_links = []
    base = "http://books.toscrape.com/"

    for page in range(1, max_pages + 1):
        page_url = base + (f"catalogue/page-{page}.html" if page > 1 else "index.html")
        print(f"→ scraping page {page}: {page_url}")

        resp = requests.get(page_url, headers=HEADERS)
        resp.raise_for_status()
        html = resp.text

        matches = re.findall(r'<article class="product_pod">.*?<h3>.*?<a href="(.*?)"', html, re.S)
        if not matches:
            break

        for href in matches:
            full = urljoin(page_url, href)
            full = full.replace("https://books.toscrape.com/", "http://books.toscrape.com/")
            if full not in all_links:
                all_links.append(full)

    print(f"Found {len(all_links)} book URLs")
    return all_links

def parse_book_detail(url):
    """Fetch a book page and pull title, genre, price, availability, rating."""
    r = requests.get(url, headers=HEADERS)
    html = r.text

    title_match = re.search(r'<h1>([^<]+)</h1>', html)
    if title_match:
        title = title_match.group(1).strip()
    else:
        title_meta = re.search(r'<title>\s*(.*?)\s*\|\s*Books to Scrape', html, re.I)
        title = title_meta.group(1).strip() if title_meta else "Unknown"

    genre_match = re.findall(r'<ul class="breadcrumb">.*?<li>.*?</li>.*?<li>.*?</li>.*?<li>(.*?)</li>', html, re.S)
    genre = re.sub(r'<.*?>', '', genre_match[0].strip()) if genre_match else None

    pm = re.search(r"£\s*([\d]+\.[\d]{2})", html)
    price = float(pm.group(1)) if pm else None

    am = re.search(r'<p\s+class="instock availability">([\s\S]*?)</p>',
                   html, re.IGNORECASE)
    if am:
        availability = re.sub(r'<.*?>', '', am.group(1)).strip()
    else:
        availability = None

    rm = re.search(r"<p class=\"star-rating\s+(\w+)\">", html)
    rating = rm.group(1) if rm else None

    return {
        "url": url,
        "title": title,
        "genre": genre,
        "price": price,
        "availability": availability,
        "rating": rating
    }


def update_database(limit=None):
    print("Running update_database…")
    sess = Session()
    now  = datetime.now(timezone.utc)

    urls = scrape_books(max_pages=50)
    if limit is not None:
        urls = urls[:limit]

    for url in urls:
        data = parse_book_detail(url)
        if data["price"] is None:
            continue

        book = sess.query(Book).filter_by(url=url).one_or_none()
        if book:
            book.prev_price = book.last_price
            book.last_price = data["price"]
            book.price_change = round(book.last_price - (book.prev_price or book.last_price), 2)
            book.title = data["title"]
            book.genre = data["genre"]
            book.availability = data["availability"]
            book.rating = data["rating"]
            book.last_checked = now
        else:
            book = Book(
                url = data["url"],
                title = data["title"],
                genre = data["genre"],
                availability = data["availability"],
                rating = data["rating"],
                last_price = data["price"],
                prev_price = None,
                price_change = None,
                last_checked = now
            )
            sess.add(book)

        sess.add(PriceHistory(book=book, price=data["price"], timestamp=now))

    sess.commit()
    sess.close()
    print("Database updated")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

book_of_the_day_cache = {"date": None, "book": None}
stats_pages         = {}
PAGE_SIZE           = 10
hl_games            = {}
hangman_games       = {}
_search_cache = defaultdict(lambda: {"results": [], "cursor": 0})


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await asyncio.get_running_loop().run_in_executor(None, update_database)
    if not scrape_and_update.is_running():
        scrape_and_update.start()

@tasks.loop(hours=12)
async def scrape_and_update():
    await asyncio.get_running_loop().run_in_executor(None, update_database)
    print(f"[{datetime.now(timezone.utc).isoformat()}] Database refreshed!")

@bot.command(name='info')
async def info(ctx):
    await ctx.send(
        "**BookTrackerBot Commands**\n"
        "`!search [--max-price X] [--min-rating R] [--genre G] [--in-stock]` — Filter and show first 10 matches\n"
        "`!more` — Next page of search results\n"
        "`!less` — Previous page of search results\n"
        "`!bookoftheday` — Today’s featured book (same for everyone)\n"
        "`!randombook` — A fresh random in-stock book\n"
        "`!cheapest [--genre G]` — Show the single cheapest book (optionally by genre)\n"
        "`!stats` — First page of pricing/stats (10 per page)\n"
        "`!next` — Next page of stats\n"
        "`!previous` — Previous page of stats\n"
        "`!higherlower` — Start higher/lower chain game\n"
        "`!hl <higher|lower>` — Guess in higher/lower game\n"
        "`!hangman` — Play hangman with a book title\n"
        "`!guess <letter>` — Guess a letter in Hangman\n"
    )

STAR_MAP = {"One":1, "Two":2, "Three":3, "Four":4, "Five":5}


@bot.command(name="search")
async def search(ctx, *, argstr: str = ""):
    """
    Usage:
      !search                     → 10 cheapest books
      !search --max-price 20      → books <= £20
      !search --min-rating Three  → only “Three”+ star
      !search --genre Poetry      → only Poetry
      !search --avail "In stock"  → only in stock
      combine flags freely, then use !next to see subsequent pages.
    """
    parts = shlex.split(argstr)
    filters = {
        "max_price":  None,
        "min_rating": None,
        "genre":      None,
        "avail":      None
    }
    i = 0
    while i < len(parts):
        p = parts[i]
        if p.startswith("--") and i+1 < len(parts):
            key = p[2:].replace("-", "_")  # normalize
            if key in filters:
                filters[key] = parts[i+1]
            i += 2
        else:
            i += 1

    sess = Session()
    q = sess.query(Book)
    if filters["max_price"] is not None:
        try:
            q = q.filter(Book.last_price <= float(filters["max_price"]))
        except ValueError:
            pass
    if filters["min_rating"]:
        q = q.filter(Book.rating.ilike(f"%{filters['min_rating']}%"))
    if filters["genre"]:
        q = q.filter(Book.genre.ilike(f"%{filters['genre']}%"))
    if filters["avail"]:
        q = q.filter(Book.availability.ilike(f"%{filters['avail']}%"))
    results = q.order_by(Book.last_price).all()
    sess.close()

    if not results:
        return await ctx.send("No books match your criteria.")
    _search_cache[ctx.channel.id] = {"results": results, "cursor": 0}
    await _send_search_page(ctx)

async def _send_search_page(ctx):
    cache = _search_cache[ctx.channel.id]
    start = cache['cursor']
    page = cache['results'][start:start+PAGE_SIZE]
    if not page:
        return await ctx.send("No more results.")

    header = f"Results {start+1}–{start+len(page)} of {len(cache['results'])}:\n\n"
    lines = []
    for b in page:
        lines.append(
            f"**{b.title}** — £{b.last_price:.2f}\n"
            f"Genre: {b.genre} | Rating: {b.rating} | {b.availability}\n"
            f"<{b.url}>\n"
        )
    msg = header
    for line in lines:
        if len(msg) + len(line) > 1900:
            await ctx.send(msg)
            msg = ""
        msg += line + "\n"
    if msg:
        await ctx.send(msg)

    cache['cursor'] += PAGE_SIZE


@bot.command(name="more")
async def search_more(ctx):
    """Show the next page of your last !search."""
    await _send_search_page(ctx)


@bot.command(name="less")
async def search_less(ctx):
    """Show the previous page of your last !search."""
    cache = _search_cache.get(ctx.channel.id)
    if not cache or not cache["results"]:
        return await ctx.send("No active search—use `!search` first.")

    page_size = PAGE_SIZE
    cur = cache["cursor"]

    if cur <= page_size:
        return await ctx.send("You’re already at the first page.")

    prev_start = cur - 2 * page_size
    if prev_start < 0:
        prev_start = 0
    cache["cursor"] = prev_start

    await _send_search_page(ctx)




@bot.command(name='cheapest')
async def cheapest(ctx, *, argstr: str = ""):
    """
    Usage: !cheapest [--genre Poetry]
    Shows the cheapest book, optionally filtering by genre.
    """
    genre = None
    parts = shlex.split(argstr)
    for i, p in enumerate(parts):
        if p == "--genre" and i+1 < len(parts):
            genre = parts[i+1]

    sess = Session()
    q = sess.query(Book)
    if genre:
        q = q.filter(Book.genre.ilike(f"%{genre}%"))
    book = q.order_by(Book.last_price).first()
    sess.close()

    if not book:
        return await ctx.send("No matching book found.")
    await ctx.send(
        f"**Cheapest Book{' in '+genre if genre else ''}:** {book.title}\n"
        f"£{book.last_price:.2f} | Genre: {book.genre or 'N/A'} | Rating: {book.rating or '—'}\n"
        f"{book.availability or ''}\n"
        f"<{book.url}>"
    )



@bot.command(name='bookoftheday')
async def book_of_the_day(ctx):
    today = datetime.now(timezone.utc).date()
    if book_of_the_day_cache["date"] != today:
        sess = Session()
        books = sess.query(Book).filter(Book.availability.ilike("%In stock%")).all()
        sess.close()
        book_of_the_day_cache.update({
            "date": today,
            "book": random.choice(books) if books else None
        })

    b = book_of_the_day_cache["book"]
    if not b:
        return await ctx.send("No in-stock books available today.")
    await ctx.send(
        f"**Book of the Day ({today}):**\n"
        f"**{b.title}** — £{b.last_price:.2f}\n"
        f"Genre: {b.genre} | {b.availability} | ★{b.rating}\n"
        f"{b.url}"
    )

@bot.command(name='randombook')
async def random_book(ctx):
    sess = Session()
    books = sess.query(Book).filter(Book.availability.ilike("%In stock%")).all()
    sess.close()
    if not books:
        return await ctx.send("No in-stock books to choose from.")
    b = random.choice(books)
    await ctx.send(
        f"**Random Book:**\n"
        f"**{b.title}** — £{b.last_price:.2f}\n"
        f"Genre: {b.genre} | {b.availability} | ★{b.rating}\n"
        f"{b.url}"
    )

async def _send_stats_page(ctx, page: int):
    sess = Session()
    offset = page * PAGE_SIZE
    books = (sess.query(Book)
                .order_by(Book.last_price)
                .offset(offset)
                .limit(PAGE_SIZE)
                .all())
    sess.close()

    if not books:
        return await ctx.send("No more pages.")
    header = f"**Stats Page {page+1}** — showing {offset+1}–{offset+len(books)}"
    lines = [
        f"**{b.title}** — £{b.last_price:.2f} | {b.genre} | {b.availability}"
        for b in books
    ]
    await ctx.send(header + "\n" + "\n".join(lines))

@bot.command(name='stats')
async def stats(ctx):
    stats_pages[ctx.channel.id] = 0
    await _send_stats_page(ctx, 0)

@bot.command(name='next')
async def stats_next(ctx):
    page = stats_pages.get(ctx.channel.id, 0) + 1
    stats_pages[ctx.channel.id] = page
    await _send_stats_page(ctx, page)

@bot.command(name='previous')
async def stats_previous(ctx):
    page = stats_pages.get(ctx.channel.id, 0)
    if page <= 0:
        return await ctx.send("You’re already on the first page.")
    page -= 1
    stats_pages[ctx.channel.id] = page
    await _send_stats_page(ctx, page)


@bot.command(name='higherlower')
async def higherlower(ctx):
    """Start a higher–lower chain showing both titles."""
    sess = Session()
    books = sess.query(Book).filter(Book.last_price != None).all()
    sess.close()
    if len(books) < 2:
        return await ctx.send("Not enough books to start a game.")
    b1, b2 = random.sample(books, 2)
    hl_games[ctx.channel.id] = {
        "current": b1,
        "next":    b2,
        "score":   0,
        "pool":    [b for b in books if b.id not in (b1.id, b2.id)]
    }

    await ctx.send(
        f"**Higher–Lower** start!\n"
        f"Is **\"{b1.title}\"** (£{b1.last_price:.2f}) higher or lower than **\"{b2.title}\"**?\n"
        f"Reply `!hl higher` or `!hl lower`."
    )

@bot.command(name='hl')
async def hl(ctx, guess: str):
    game = hl_games.get(ctx.channel.id)
    if not game:
        return await ctx.send("No game active—type `!higherlower` to start.")

    guess = guess.lower()
    if guess not in ("higher", "lower"):
        return await ctx.send("Please guess `higher` or `lower` (e.g. `!hl higher`).")

    b1 = game["current"]
    b2 = game["next"]
    correct = "higher" if b1.last_price < b2.last_price else "lower"

    if guess == correct:
        game["score"] += 1
        game["current"] = b2
        if not game["pool"]:
            return await ctx.send(
                f"Perfect run! You've guessed all {game['score']} correctly!"
            )
        next_book = random.choice(game["pool"])
        game["pool"].remove(next_book)
        game["next"] = next_book

        await ctx.send(
            f"**Correct!**\n"
            f"\"{b2.title}\" was £{b2.last_price:.2f} ({correct}).\n"
            f"Score: {game['score']}\n\n"
            f"Next: Is **\"{b2.title}\"** (£{b2.last_price:.2f}) higher or lower than **\"{next_book.title}\"**?"
        )

    else:
        await ctx.send(
            f"**Wrong!**\n"
            f"\"{b2.title}\" was £{b2.last_price:.2f} (it’s actually {correct} than £{b1.last_price:.2f}).\n"
            f"Final score: {game['score']}."
        )
        del hl_games[ctx.channel.id]

@bot.command(name='hangman')
async def hangman(ctx):
    sess = Session()
    books = sess.query(Book).all()
    sess.close()
    if not books:
        return await ctx.send("No books available for Hangman.")
    secret_full = random.choice(books).title.upper()
    secret = "".join(ch if ch.isalpha() else " " for ch in secret_full)
    display = ["·" if ch.isalpha() else " " for ch in secret]
    hangman_games[ctx.channel.id] = {
        "secret": secret,
        "display": display,
        "tries": 6,
        "guessed": set()
    }
    await ctx.send(f"Hangman: `{' '.join(display)}` — Tries left: 6")

@bot.command(name='guess')
async def guess(ctx, letter: str):
    game = hangman_games.get(ctx.channel.id)
    if not game:
        return await ctx.send("No game active—type `!hangman` to start.")
    l = letter.upper()
    if not (len(l) == 1 and l.isalpha()):
        return await ctx.send("Guess a single letter A–Z.")
    if l in game["guessed"]:
        return await ctx.send(f"You already tried **{l}**.")
    game["guessed"].add(l)

    if l in game["secret"]:
        for i, ch in enumerate(game["secret"]):
            if ch == l:
                game["display"][i] = l
        if "·" not in game["display"]:
            await ctx.send(f"You win: `{' '.join(game['display'])}`")
            del hangman_games[ctx.channel.id]
        else:
            await ctx.send(f"`{' '.join(game['display'])}` — Tries left: {game['tries']}")
    else:
        game["tries"] -= 1
        if game["tries"] <= 0:
            await ctx.send(f"Game over—answer was `{game['secret']}`.")
            del hangman_games[ctx.channel.id]
        else:
            await ctx.send(f"`{' '.join(game['display'])}` — Tries left: {game['tries']}")

if __name__ == "__main__":
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        print("Please set DISCORD_BOT_TOKEN")
    else:
        bot.run(token)