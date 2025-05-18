# Financial MCP Server

A custom Model Context Protocol (MCP) server for advanced financial analysis, stock monitoring, and real-time market intelligence. This server provides a suite of tools and API endpoints for portfolio management, market summaries, stock alerts, and contextual financial insights, designed for seamless integration with Claude Desktop and other MCP-compatible clients.

---

## Key Features

- **Real-time Stock Price Monitoring**: Track and alert on price movements for user-defined stocks and thresholds.
- **Portfolio Management**: Add, remove, and view tracked stocks in a persistent portfolio.
- **Market Summaries**: Retrieve live global market data, including indices, top gainers/losers, and news headlines.
- **Contextual Financial Insights**: Analyze user queries, extract financial entities, fetch and summarize relevant news, and generate actionable prompts.
- **Automated Alerts**: Receive Telegram notifications for price thresholds, trading opportunities, and system errors.
- **Customizable Configuration**: JSON-based sector and stock configuration for flexible alerting.
- **Robust Logging & Error Handling**: Detailed logs and error messages for transparency and troubleshooting.

---

## System Overview

### Core Endpoints & Tools

- **financial_context(query: str)**
  - Extracts tickers and keywords from a user query, fetches and summarizes relevant news, and returns a structured context and prompt for downstream analysis.
- **market_summary()**
  - Returns a live summary of global markets, including indices, top movers, and news headlines.
- **get_portfolio()**
  - Retrieves the current list of tracked stocks in the user's portfolio.
- **add_stock(ticker: str)** / **remove_stock(ticker: str)**
  - Add or remove a stock from the portfolio, with cache invalidation and verification.
- **portfolio_alerts(random_string: str)**
  - Returns all triggered alerts for the portfolio, or for a specific ticker if provided.
- **check_stock_alerts(ticker: str)** / **single_stock_alert(ticker: str)**
  - Returns alerts for a specific stock, with detailed error handling.

### Automated Alerting
- **Telegram Integration**: Sends formatted alerts and summaries to a configured Telegram chat.
- **Trading Opportunities**: Detects and notifies about actionable trading signals.

### Contextual Summarization
- **News Summarizer**: Uses a local LLM (Ollama/Mistral) to generate detailed, sentiment-tagged summaries of financial news articles.
- **Prompt Builder**: Constructs a market-aware prompt for use in downstream LLMs or assistants.

---

## File Structure

```
config/
  alerts_config.json         # Main alert configuration (sector/ticker/thresholds)
  tech_alerts_config.json    # Tech sector-specific alerts
services/
  alerts.py                  # Core alert logic
  tech_alerts.py             # Tech sector alert logic
  telegram_alerts.py         # Telegram integration
  market_summary.py          # Market data and news
  summarizer.py              # News summarization (LLM)
  fetcher.py                 # Web data fetching
  context_builder.py         # Prompt/context construction
  intent_parser.py           # Financial entity extraction
  portfolio.py               # Portfolio management
server.py                    # MCP server entry point and API definitions
requirements.txt             # Python dependencies
```

---

## Configuration & Customization

### Alert Configuration (`config/alerts_config.json`)

- Organize stocks by sector, with customizable upper/lower price thresholds and descriptions.
- Example structure:

```json
{
  "Tech Giants": {
    "AAPL": {"above": 200, "below": 180, "description": "Apple Inc."}
  },
  "Financial": {
    "JPM": {"above": 160, "below": 140, "description": "JPMorgan Chase"}
  }
}
```

### Environment Variables

Set these in a `.env` file or your system environment:

```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
SERPAPI_API_KEY=your_serpapi_key
```

---

## Installation & Running from Claude Desktop

### Prerequisites
- Python 3.7+
- [Claude Desktop](https://www.anthropic.com/claude-desktop) (or any MCP-compatible client)
- Telegram bot credentials (for alerting)
- Internet connection (for market/news data)

### Step-by-Step Guide

1. **Clone the Repository**
   ```bash
   git clone <this-repo-url>
   cd Finance_MCP_Server
   ```

2. **Create and Activate a Virtual Environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables**
   - Create a `.env` file in the project root with your API keys and tokens:
     ```
     TELEGRAM_BOT_TOKEN=your_bot_token
     TELEGRAM_CHAT_ID=your_chat_id
     SERPAPI_API_KEY=your_serpapi_key
     ```

5. **Edit Alert Configurations**
   - Modify `config/alerts_config.json` and `config/tech_alerts_config.json` to set your stocks, sectors, and thresholds.

6. **Install the MCP Server with the CLI**
   - Use the MCP CLI to install and register the server for Claude Desktop:
     ```bash
     mcp install server.py --name "Financial MCP Server"
     ```
   - This will register the server as a custom MCP tool, making it discoverable by Claude Desktop and other MCP clients.

7. **Run the MCP Server via MCP CLI**
   - Start the server using the MCP CLI:
     ```bash
     mcp run server.py
     ```
   - The server will start and listen for MCP requests via stdio.

8. **Connect from Claude Desktop**
   - In Claude Desktop, add a new custom MCP server connection.
   - Set the executable/command to `mcp run server.py` (or select the registered "Financial MCP Server" from the MCP CLI list).
   - Claude Desktop will communicate with the server using the MCP protocol, enabling all the described tools and endpoints.

---

### Example: Claude Desktop MCP Server Configuration

After installing and registering the Financial MCP Server, you can add it to your Claude Desktop configuration. Here is a sample `claude_desktop_config.json` snippet:

```json
{
  "mcpServers": {
    "Financial-MCP-Server": {
      "command": "uv",
      "args": [
        "run",
        "--with",
        "mcp[cli]",
        "mcp",
        "run",
        "server.py"
      ],
      "env": {
        "SERPAPI_API_KEY": "",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_USER_ID": "",
        "OPENAI_API_KEY": "",
        "ALPHA_VANTAGE_API_KEY": ""
      }
    }
  }
}
```

- Update the `env` section with your actual API keys and tokens as needed.
- This configuration ensures Claude Desktop can launch and communicate with your Financial MCP Server using the correct environment and command-line arguments.

---

## Using Your Tools in Claude Desktop

After installing and connecting your custom Financial MCP Server, all available tools will automatically appear in Claude Desktop's tool menu. You can enable or disable each tool individually, making it easy to access functionalities such as financial context analysis, market summaries, portfolio management, and stock alerts directly from the Claude interface.

Below is a screenshot showing how the tools from your MCP server will be listed and toggled in Claude Desktop:

![Claude Desktop MCP Tools Example](./screenshot_claude_tools.png)

- Each tool (e.g., `financial_context`, `market_summary`, `add_stock`, etc.) can be enabled or disabled as needed.
- This seamless integration allows you to interact with your financial analysis server using natural language and tool-based workflows within Claude Desktop.

---

## Usage Examples

- **Get Market Summary**: Use the `market_summary` tool to fetch live indices, movers, and news.
- **Manage Portfolio**: Use `add_stock`, `remove_stock`, and `get_portfolio` to update and view your tracked stocks.
- **Receive Alerts**: Configure thresholds and receive Telegram notifications for price movements and trading opportunities.
- **Contextual Analysis**: Use `financial_context` to analyze a query, extract tickers, and get summarized news and a market-aware prompt.

---

## Troubleshooting & Logs

- All logs are written to `financial_mcp.log` in the project root.
- For debugging, check the log file and ensure your environment variables and configuration files are correct.
- If you encounter issues with Telegram or news fetching, verify your API keys and internet connection.

---