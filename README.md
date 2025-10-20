# 📚 BookTracker Discord Bot

A feature-rich **Discord bot** built with **Python** that automatically scrapes, structures and analyzes book data from [Books to Scrape](http://books.toscrape.com/).  
It keeps the data updated in a **MySQL** database and provides interactive text commands and games directly in Discord.

---

## 🧠 Overview

**BookTrackerBot** combines data collection, processing and user interaction in one system.  
It continuously scrapes book information (title, genre, price, availability, rating), stores it in a structured database, and provides users with access to data and games through Discord commands.

### 🪄 Key Capabilities
- Automated web scraping and data extraction  
- Database management with SQLAlchemy  
- Asynchronous scheduling and updates  
- Interactive command handling via Discord API  
- Two text-based games: **Higher–Lower** and **Hangman**

---

## ⚙️ Technologies Used

| Category | Tools |
|-----------|-------|
| **Language** | Python 3.9+ |
| **Frameworks / Libraries** | `discord.py`, `SQLAlchemy`, `requests`, `asyncio`, `re`, `shlex`, `random` |
| **Database** | MySQL (via `pymysql`) |
| **Architecture** | Asynchronous, event-driven, database-backed |
| **Environment** | Cross-platform (Windows / Linux / Docker) |

---

## 🕸️ Data Scraping and Processing

The bot gathers data from [Books to Scrape](http://books.toscrape.com/) and organizes it in a structured format.

### 🔍 Crawling
- Iterates through up to **50 pages** of book listings  
- Extracts book URLs using **regular expressions**  
- Uses `requests` for HTTP GET calls and `urljoin` to resolve relative URLs  

### 🧩 Parsing
Each book’s page is analyzed to extract:
- **Title** → from `<h1>` or `<title>` tags  
- **Genre** → from breadcrumb navigation hierarchy  
- **Price** → parsed from patterns like `£19.99`  
- **Availability** → cleaned from `<p class="instock availability">`  
- **Rating** → extracted from class names (`One`, `Two`, etc.)  

### 🧹 Data Cleaning
- Removes HTML tags and whitespace with regex  
- Converts rating words into numeric equivalents  
- Normalizes fields for consistent database storage  

### 🗄️ Database Integration
Data stored in **MySQL** using **SQLAlchemy ORM** models:
- `Book` → current book details  
- `PriceHistory` → historical price entries  

Database updates run automatically every **12 hours** via background task: @tasks.loop(hours=12)

## 🗄️ Database Schema

### 📘 Table: `books`
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `url` | String | Unique book URL |
| `title` | String | Book title |
| `genre` | String | Book category |
| `availability` | String | Stock status |
| `rating` | String | Rating level |
| `last_price` | Float | Current price |
| `prev_price` | Float | Previous price |
| `price_change` | Float | Difference in price |
| `last_checked` | DateTime | Last scrape timestamp |

### 💰 Table: `price_history`
| Field | Type | Description |
|-------|------|-------------|
| `id` | Integer | Primary key |
| `book_id` | Integer (FK) | Linked to `books.id` |
| `price` | Float | Recorded price |
| `timestamp` | DateTime | Time of recording |

---

## 💬 Discord Commands

| Command | Description |
|----------|--------------|
| `!info` | Show all available commands |
| `!search [--max-price X] [--min-rating R] [--genre G] [--avail "In stock"]` | Search books using filters |
| `!more` / `!less` | Navigate through paginated search results |
| `!cheapest [--genre G]` | Display the cheapest book (optional filter by genre) |
| `!bookoftheday` | Display a random featured book for the day |
| `!randombook` | Get a random book currently in stock |
| `!stats`, `!next`, `!previous` | View paginated list of books with prices |
| `!higherlower`, `!hl higher`, `!hl lower` | Play Higher–Lower guessing game |
| `!hangman`, `!guess <letter>` | Play Hangman with book titles |

---

## 🎮 Interactive Features

### 🕹️ Higher–Lower

A simple **price-based guessing game**.  
The bot shows two book titles and their prices — the player guesses whether the next one is **higher** or **lower**.

- Tracks score and progress per session  
- Supports multiple sessions per channel/server  

---

### 🔡 Hangman

A **book title guessing game** where players guess letters to reveal a hidden title.

- Randomly selects a book from the database  
- Tracks per-channel game state  

---

## 🔑 Environment Variables

Before running the bot, configure the following in your `.env` file:

```env
DB_USER=tracker
DB_PASS=secret_password
DB_HOST=localhost
DB_NAME=book_tracker
DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN
```

## 🚀 Possible Improvements

- **Add real-time notifications** for price changes  
- **Implement CSV/JSON export options** for book data  
- **Create a web dashboard** for visual analytics  
- **Add genre-based statistics and recommendations**  
- **Deploy using Docker or cloud-based hosting**

---

## 🧾 Learning Outcomes

This project demonstrates:

- Writing structured, maintainable **Python code**  
- Handling asynchronous tasks with **asyncio**  
- Building **database-integrated applications**  
- Managing **user interaction and state** in Discord bots  
- Extracting and transforming **data from web sources**

