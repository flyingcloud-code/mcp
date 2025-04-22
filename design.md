# Design for `get_web_content` Tool

## Purpose

To provide a tool that can fetch the main content of a web page given its URL and return it in a specified format (HTML, Markdown, or potentially JSON if the source is structured).
This tool is intended to be used by an LLM, particularly after a `google_search` tool returns a list of relevant URLs, allowing the LLM to retrieve and process the content of a specific search result.

## Tool Definition (`server.py`)

```python
@mcp.tool()
def get_web_content(url: str, format: str = 'markdown') -> str:
    '''
    Fetches the main content of a web page and returns it in the specified format.
    Attempts to remove common boilerplate like headers, footers, and navigation.
    :param url: The URL of the web page to fetch.
    :param format: The desired output format ('markdown', 'html', 'text'). Defaults to 'markdown'.
    :return: The extracted main content in the specified format, or an error message.
    '''
    # Implementation details below
```

## Parameters

-   `url` (string, required): The URL of the web page to fetch.
-   `format` (string, optional, default: 'markdown'): The desired output format. Supported values: 'markdown', 'html', 'text'.

## Implementation Strategy

1.  **Fetching:** Use the `requests` library to fetch the HTML content of the URL.
2.  **Parsing:** Use `BeautifulSoup` (from `bs4`) to parse the HTML structure.
3.  **Content Extraction (Heuristics):**
    *   Identify common tags likely containing main content (e.g., `<article>`, `<main>`, `div` with specific IDs/classes like `content`, `main-content`).
    *   Attempt to remove common boilerplate tags (e.g., `<header>`, `<footer>`, `<nav>`, `<aside>`, elements with IDs/classes like `sidebar`, `menu`, `header`, `footer`).
    *   This will be a best-effort extraction and might not be perfect for all websites.
4.  **Formatting:**
    *   **HTML:** Return the cleaned HTML content.
    *   **Markdown:** Use the `markdownify` library to convert the cleaned HTML to Markdown.
    *   **Text:** Extract the text content from the cleaned HTML using BeautifulSoup's `.get_text()` method.
5.  **Error Handling:** Include `try...except` blocks to handle network errors (`requests.exceptions.RequestException`), parsing errors, invalid URLs, and unsupported formats.

## Dependencies

-   `requests` (already likely present)
-   `beautifulsoup4`
-   `markdownify`

These dependencies need to be installed (`pip install beautifulsoup4 markdownify`).

## LLM Guidance

### System Prompt Strategy

The system prompt should be generic and empower the LLM to achieve the user's goal. It should:

1.  **Clearly State the Assistant's Role:** Define the overall purpose of the assistant (e.g., "You are a helpful assistant.").
2.  **Highlight Available Capabilities (Tools):** Inform the LLM about the tools it has access to and their general functions, without prescribing a specific sequence.
3.  **Encourage Autonomous Decision-Making:** Guide the LLM to analyze the user's request and determine the best course of action, including whether to use no tools, a single tool, or multiple tools in sequence or combination.

**Example Generic System Prompt Snippet:**

```
You are a helpful assistant equipped with several tools to aid users. Analyze the user's request and utilize the available tools (`google_search`, `get_web_content`, etc.) as needed to provide the best possible response. Decide whether to use a tool, which tool(s) to use, and in what order, based on the specific query.

**Workflow Guidance:**
1. If the user asks a question that requires current information or details from the web, first use `google_search` to find relevant URLs.
2. If the search results provide promising URLs, consider using `get_web_content` on the most relevant URL to fetch its detailed content.
3. Finally, synthesize the information from the search results and/or the fetched web content to answer the user's question.
```

### Tool Description Guidance

The tool's description should clearly state its purpose: fetching *main* web content from a URL, emphasizing it's often used *after* a search. The parameter description should guide the LLM on how to specify the URL (obtained from a previous search result) and the desired format.

Example Interaction Flow:

1.  User asks: "What are the latest features of OpenAI's GPT-4o model?"
2.  LLM uses `google_search` with query "OpenAI GPT-4o features".
3.  Search results include a link like `https://openai.com/blog/gpt-4o`.
4.  LLM uses `get_web_content` with `url="https://openai.com/blog/gpt-4o"`.
5.  LLM synthesizes the content fetched from the blog post to answer the user's question about GPT-4o features.