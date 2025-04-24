# simple mcp demo
Simple demo that implment mcp client and mcp server
based on openrouter model
you need add your own api key

# how to run mcp client and mcp server demo together
it will automatically launch server.py which has MCP server implmentation 
```python
python client.py 
```
# how to run mcp server only with github copilot or cline, etc.
## mcp server tools inside
```
get_weekday_from_date
get_weather_for_date
google_search
get_web_content
```
## set below into MCP client tool
```json
{
  "mcpServers": {
    "simple_mcp": {
      "command": "python",
      "args": [
                "/<path>/server.py"
        ]
    }
  }
}
```
## talk with your agent
